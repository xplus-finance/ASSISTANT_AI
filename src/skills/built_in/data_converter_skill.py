"""Data format conversion skill — CSV, JSON, YAML, XML."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import xml.dom.minidom
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import structlog

from src.skills.base_skill import BaseSkill, SkillResult

log = structlog.get_logger("assistant.skills.data_converter")

_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
_OUTPUT_DIR = Path("/tmp/ASSISTANT_AI/output/data")
_MAX_DISPLAY = 4000

# ---------- YAML helpers (optional dependency) ----------

try:
    import yaml as _yaml

    _HAS_YAML = True
except ImportError:
    _yaml = None  # type: ignore[assignment]
    _HAS_YAML = False


def _yaml_loads(text: str) -> Any:
    """Parse YAML text, falling back to basic key:value if PyYAML missing."""
    if _HAS_YAML:
        return _yaml.safe_load(text)
    # Minimal fallback: flat key: value lines
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            result[key.strip()] = val.strip()
    return result


def _yaml_dumps(obj: Any) -> str:
    if _HAS_YAML:
        return _yaml.dump(obj, allow_unicode=True, default_flow_style=False, sort_keys=False)
    # Minimal fallback for list-of-dicts (most common conversion output)
    if isinstance(obj, list):
        lines: list[str] = []
        for item in obj:
            if isinstance(item, dict):
                first = True
                for k, v in item.items():
                    prefix = "- " if first else "  "
                    lines.append(f"{prefix}{k}: {v}")
                    first = False
            else:
                lines.append(f"- {item}")
        return "\n".join(lines) + "\n"
    if isinstance(obj, dict):
        return "\n".join(f"{k}: {v}" for k, v in obj.items()) + "\n"
    return str(obj)


# ---------- File I/O helpers ----------


def _read_file(path: str) -> str:
    """Read file with encoding fallback."""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"Archivo no encontrado: {p}")
    if p.stat().st_size > _MAX_FILE_SIZE:
        raise ValueError(f"Archivo demasiado grande (>{_MAX_FILE_SIZE // 1024 // 1024}MB): {p}")
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return p.read_text(encoding="latin-1")


def _write_output(name: str, content: str) -> Path:
    """Write content to output directory, return path."""
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = _OUTPUT_DIR / name
    out.write_text(content, encoding="utf-8")
    return out


def _parse_csv(text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def _dicts_to_csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


# ---------- JSON <-> XML ----------


def _dict_to_xml_element(tag: str, data: Any) -> ET.Element:
    """Recursively convert a dict/list/scalar to XML elements."""
    elem = ET.Element(tag)
    if isinstance(data, dict):
        for key, val in data.items():
            child = _dict_to_xml_element(key, val)
            elem.append(child)
    elif isinstance(data, list):
        for item in data:
            child = _dict_to_xml_element("item", item)
            elem.append(child)
    else:
        elem.text = str(data) if data is not None else ""
    return elem


def _xml_element_to_dict(elem: ET.Element) -> Any:
    """Recursively convert an XML element to dict."""
    children = list(elem)
    if not children:
        return elem.text or ""
    # Check if all children share the same tag (list-like)
    tags = [c.tag for c in children]
    if len(set(tags)) == 1 and len(tags) > 1:
        return {tags[0] + "s": [_xml_element_to_dict(c) for c in children]}
    result: dict[str, Any] = {}
    for child in children:
        key = child.tag
        val = _xml_element_to_dict(child)
        if key in result:
            existing = result[key]
            if isinstance(existing, list):
                existing.append(val)
            else:
                result[key] = [existing, val]
        else:
            result[key] = val
    return result


def _json_to_xml_string(data: Any) -> str:
    root_data = data
    root_tag = "root"
    if isinstance(data, list):
        wrapper = ET.Element("root")
        for item in data:
            wrapper.append(_dict_to_xml_element("item", item))
        raw = ET.tostring(wrapper, encoding="unicode")
    elif isinstance(data, dict):
        elem = _dict_to_xml_element(root_tag, root_data)
        raw = ET.tostring(elem, encoding="unicode")
    else:
        elem = ET.Element("value")
        elem.text = str(data)
        raw = ET.tostring(elem, encoding="unicode")
    dom = xml.dom.minidom.parseString(raw)
    return dom.toprettyxml(indent="  ", encoding=None)  # type: ignore[return-value]


def _xml_string_to_json(text: str) -> Any:
    root = ET.fromstring(text)
    return {root.tag: _xml_element_to_dict(root)}


# ---------- Stats / filtering helpers ----------


def _numeric(val: Any) -> float | None:
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _compute_stats(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "Sin datos."
    cols = list(rows[0].keys())
    lines: list[str] = ["**Estadisticas:**\n"]
    found_numeric = False
    for col in cols:
        nums = [n for r in rows if (n := _numeric(r.get(col))) is not None]
        if not nums:
            continue
        found_numeric = True
        lines.append(f"  **{col}**: count={len(nums)}, min={min(nums):.4g}, max={max(nums):.4g}, avg={sum(nums)/len(nums):.4g}")
    if not found_numeric:
        lines.append("No se encontraron columnas numericas.")
    return "\n".join(lines)


def _filter_rows(rows: list[dict[str, Any]], column: str, value: str) -> list[dict[str, Any]]:
    return [r for r in rows if str(r.get(column, "")).strip().lower() == value.strip().lower()]


def _sort_rows(rows: list[dict[str, Any]], column: str, descending: bool) -> list[dict[str, Any]]:
    def sort_key(r: dict[str, Any]) -> tuple[int, float | str]:
        val = r.get(column, "")
        n = _numeric(val)
        if n is not None:
            return (0, n)
        return (1, str(val).lower())

    return sorted(rows, key=sort_key, reverse=descending)


def _format_table(rows: list[dict[str, Any]], max_rows: int = 20) -> str:
    """Format rows as a readable text table."""
    if not rows:
        return "(vacio)"
    cols = list(rows[0].keys())
    display = rows[:max_rows]
    widths = {c: len(c) for c in cols}
    for r in display:
        for c in cols:
            widths[c] = max(widths[c], len(str(r.get(c, ""))))
    # Cap column width
    for c in cols:
        widths[c] = min(widths[c], 30)

    header = " | ".join(c.ljust(widths[c])[:widths[c]] for c in cols)
    sep = "-+-".join("-" * widths[c] for c in cols)
    lines = [header, sep]
    for r in display:
        lines.append(" | ".join(str(r.get(c, "")).ljust(widths[c])[:widths[c]] for c in cols))
    if len(rows) > max_rows:
        lines.append(f"... y {len(rows) - max_rows} filas mas")
    return "```\n" + "\n".join(lines) + "\n```"


# ---------- Data loader (auto-detect) ----------


def _detect_and_load(text: str, path: str | None = None) -> tuple[str, list[dict[str, Any]]]:
    """Detect format and return (format_name, rows_as_dicts)."""
    ext = Path(path).suffix.lower() if path else ""

    # JSON
    if ext == ".json" or (not ext and text.lstrip().startswith(("{", "["))):
        data = json.loads(text)
        if isinstance(data, list):
            return "json", data
        if isinstance(data, dict):
            return "json", [data]
        return "json", [{"value": data}]

    # XML
    if ext == ".xml" or (not ext and text.lstrip().startswith("<")):
        parsed = _xml_string_to_json(text)
        if isinstance(parsed, dict) and len(parsed) == 1:
            inner = list(parsed.values())[0]
            if isinstance(inner, list):
                return "xml", inner
            if isinstance(inner, dict):
                # Unwrap single list child
                for v in inner.values():
                    if isinstance(v, list) and v and isinstance(v[0], dict):
                        return "xml", v
                return "xml", [inner]
        return "xml", [parsed] if not isinstance(parsed, list) else parsed

    # YAML
    if ext in (".yaml", ".yml"):
        data = _yaml_loads(text)
        if isinstance(data, list):
            return "yaml", data
        if isinstance(data, dict):
            return "yaml", [data]
        return "yaml", [{"value": data}]

    # CSV (default)
    rows = _parse_csv(text)
    if rows:
        return "csv", rows

    # Last resort: try JSON anyway
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return "json", data
        return "json", [data]
    except (json.JSONDecodeError, ValueError):
        pass

    return "unknown", []


def _file_info(path: str) -> str:
    """Detect format and show summary info."""
    text = _read_file(path)
    fmt, rows = _detect_and_load(text, path)
    p = Path(path).resolve()
    size = p.stat().st_size
    cols = list(rows[0].keys()) if rows else []
    lines = [
        f"**Archivo:** {p.name}",
        f"**Formato detectado:** {fmt.upper()}",
        f"**Tamano:** {size:,} bytes ({size / 1024:.1f} KB)",
        f"**Filas:** {len(rows)}",
        f"**Columnas ({len(cols)}):** {', '.join(cols)}",
    ]
    return "\n".join(lines)


# ---------- Conversion functions ----------


def _csv2json(path: str) -> tuple[str, Path]:
    text = _read_file(path)
    rows = _parse_csv(text)
    out_name = Path(path).stem + ".json"
    content = json.dumps(rows, indent=2, ensure_ascii=False)
    out = _write_output(out_name, content)
    return f"CSV -> JSON: {len(rows)} filas convertidas.\nArchivo: `{out}`", out


def _json2csv(path: str) -> tuple[str, Path]:
    text = _read_file(path)
    data = json.loads(text)
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not data:
        raise ValueError("El JSON debe contener un array de objetos.")
    content = _dicts_to_csv(data)
    out_name = Path(path).stem + ".csv"
    out = _write_output(out_name, content)
    return f"JSON -> CSV: {len(data)} filas convertidas.\nArchivo: `{out}`", out


def _json2yaml(path: str) -> tuple[str, Path]:
    text = _read_file(path)
    data = json.loads(text)
    content = _yaml_dumps(data)
    out_name = Path(path).stem + ".yaml"
    out = _write_output(out_name, content)
    rows = len(data) if isinstance(data, list) else 1
    return f"JSON -> YAML: {rows} elementos convertidos.\nArchivo: `{out}`", out


def _yaml2json(path: str) -> tuple[str, Path]:
    text = _read_file(path)
    data = _yaml_loads(text)
    content = json.dumps(data, indent=2, ensure_ascii=False)
    out_name = Path(path).stem + ".json"
    out = _write_output(out_name, content)
    rows = len(data) if isinstance(data, list) else 1
    return f"YAML -> JSON: {rows} elementos convertidos.\nArchivo: `{out}`", out


def _json2xml(path: str) -> tuple[str, Path]:
    text = _read_file(path)
    data = json.loads(text)
    content = _json_to_xml_string(data)
    out_name = Path(path).stem + ".xml"
    out = _write_output(out_name, content)
    return f"JSON -> XML convertido.\nArchivo: `{out}`", out


def _xml2json(path: str) -> tuple[str, Path]:
    text = _read_file(path)
    data = _xml_string_to_json(text)
    content = json.dumps(data, indent=2, ensure_ascii=False)
    out_name = Path(path).stem + ".json"
    out = _write_output(out_name, content)
    return f"XML -> JSON convertido.\nArchivo: `{out}`", out


def _csv2yaml(path: str) -> tuple[str, Path]:
    text = _read_file(path)
    rows = _parse_csv(text)
    content = _yaml_dumps(rows)
    out_name = Path(path).stem + ".yaml"
    out = _write_output(out_name, content)
    return f"CSV -> YAML: {len(rows)} filas convertidas.\nArchivo: `{out}`", out


# ---------- Skill class ----------


_HELP = """**Data Converter — Subcomandos:**

`csv2json <archivo>` — CSV a JSON
`json2csv <archivo>` — JSON a CSV
`json2yaml <archivo>` — JSON a YAML
`yaml2json <archivo>` — YAML a JSON
`json2xml <archivo>` — JSON a XML
`xml2json <archivo>` — XML a JSON
`csv2yaml <archivo>` — CSV a YAML
`formato <archivo>` — Detectar formato y mostrar info
`preview <archivo>` — Primeras 5 filas
`stats <archivo>` — Estadisticas de columnas numericas
`filtrar <archivo> | <columna> | <valor>` — Filtrar filas
`ordenar <archivo> | <columna> [asc|desc]` — Ordenar por columna
`texto <datos>` — Parsear datos inline y mostrar formateado"""


class DataConverterSkill(BaseSkill):

    @property
    def name(self) -> str:
        return "data_converter"

    @property
    def description(self) -> str:
        return "Convertir entre CSV, JSON, YAML y XML. Estadisticas, filtrado y preview de datos."

    @property
    def natural_patterns(self) -> dict[str, list[str]]:
        return {
            "csv2json": [
                r"(?:convierte|pasa|transforma)\s+(?:el\s+|ese\s+|este\s+)?csv\s+a\s+json(?:\s+(?P<args>\S+))?",
                r"(?:convierte|pasa|transforma)\s+(?P<args>\S+\.csv)\s+a\s+json",
            ],
            "json2csv": [
                r"(?:convierte|pasa|transforma)\s+(?:el\s+|ese\s+|este\s+)?json\s+a\s+csv(?:\s+(?P<args>\S+))?",
                r"(?:convierte|pasa|transforma)\s+(?P<args>\S+\.json)\s+a\s+csv",
            ],
            "json2yaml": [
                r"(?:convierte|pasa|transforma)\s+(?:el\s+|ese\s+|este\s+)?json\s+a\s+yaml(?:\s+(?P<args>\S+))?",
                r"(?:convierte|pasa|transforma)\s+(?P<args>\S+\.json)\s+a\s+yaml",
            ],
            "yaml2json": [
                r"(?:convierte|pasa|transforma)\s+(?:el\s+|ese\s+|este\s+)?yaml\s+a\s+json(?:\s+(?P<args>\S+))?",
                r"(?:convierte|pasa|transforma)\s+(?P<args>\S+\.ya?ml)\s+a\s+json",
            ],
            "formato": [
                r"(?:qu[eé]\s+formato|detecta|identifica)\s+(?:es|tiene)\s+(?:el\s+archivo\s+)?(?P<args>\S+)",
            ],
            "stats": [
                r"(?:estad[ií]sticas?|stats?|an[aá]lisis)\s+(?:del?\s+)?(?:archivo\s+)?(?P<args>\S+\.\w+)",
            ],
            "preview": [
                r"(?:mu[eé]strame|preview|vista\s+previa|primeras?\s+filas?)\s+(?:del?\s+)?(?P<args>\S+\.\w+)",
            ],
        }

    @property
    def triggers(self) -> list[str]:
        return ["!convertir", "!convert", "!csv", "!json", "!yaml", "!xml", "!datos", "!data"]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        if not args.strip():
            return SkillResult(success=True, message=_HELP)

        parts = args.strip().split(None, 1)
        subcmd = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""

        try:
            return await self._dispatch(subcmd, rest)
        except FileNotFoundError as exc:
            log.warning("data_converter.file_not_found", error=str(exc))
            return SkillResult(success=False, message=str(exc))
        except (json.JSONDecodeError, ET.ParseError) as exc:
            log.warning("data_converter.parse_error", error=str(exc))
            return SkillResult(success=False, message=f"Error de parseo: {exc}")
        except ValueError as exc:
            log.warning("data_converter.value_error", error=str(exc))
            return SkillResult(success=False, message=str(exc))
        except Exception as exc:
            log.error("data_converter.unexpected", error=str(exc), exc_info=True)
            return SkillResult(success=False, message=f"Error inesperado: {exc}")

    async def _dispatch(self, subcmd: str, rest: str) -> SkillResult:
        converters: dict[str, Any] = {
            "csv2json": _csv2json,
            "json2csv": _json2csv,
            "json2yaml": _json2yaml,
            "yaml2json": _yaml2json,
            "json2xml": _json2xml,
            "xml2json": _xml2json,
            "csv2yaml": _csv2yaml,
        }

        if subcmd in converters:
            if not rest:
                return SkillResult(success=False, message=f"Uso: `{subcmd} <archivo>`")
            msg, out_path = await asyncio.to_thread(converters[subcmd], rest)
            log.info("data_converter.converted", subcmd=subcmd, output=str(out_path))
            return SkillResult(success=True, message=msg, data={"output_path": str(out_path)})

        if subcmd == "formato":
            if not rest:
                return SkillResult(success=False, message="Uso: `formato <archivo>`")
            msg = await asyncio.to_thread(_file_info, rest)
            return SkillResult(success=True, message=msg)

        if subcmd == "preview":
            if not rest:
                return SkillResult(success=False, message="Uso: `preview <archivo>`")
            msg = await asyncio.to_thread(self._preview, rest)
            return SkillResult(success=True, message=msg)

        if subcmd == "stats":
            if not rest:
                return SkillResult(success=False, message="Uso: `stats <archivo>`")
            msg = await asyncio.to_thread(self._stats, rest)
            return SkillResult(success=True, message=msg)

        if subcmd == "filtrar":
            return await self._handle_filter(rest)

        if subcmd == "ordenar":
            return await self._handle_sort(rest)

        if subcmd == "texto":
            if not rest:
                return SkillResult(success=False, message="Uso: `texto <datos>`")
            msg = await asyncio.to_thread(self._parse_inline, rest)
            return SkillResult(success=True, message=msg)

        # Unknown subcommand — maybe it's a direct file path for auto-detect
        if os.path.exists(rest) or os.path.exists(subcmd):
            file_path = rest if rest and os.path.exists(rest) else subcmd
            msg = await asyncio.to_thread(_file_info, file_path)
            return SkillResult(success=True, message=msg)

        return SkillResult(success=True, message=_HELP)

    # ---------- Subcommand implementations ----------

    @staticmethod
    def _preview(path: str) -> str:
        text = _read_file(path)
        fmt, rows = _detect_and_load(text, path)
        if not rows:
            return f"No se pudieron leer datos de `{path}` (formato: {fmt})."
        preview_rows = rows[:5]
        header = f"**Preview** ({fmt.upper()}) — {len(rows)} filas totales, mostrando {len(preview_rows)}:\n"
        return header + _format_table(preview_rows, max_rows=5)

    @staticmethod
    def _stats(path: str) -> str:
        text = _read_file(path)
        fmt, rows = _detect_and_load(text, path)
        if not rows:
            return f"No se pudieron leer datos de `{path}`."
        header = f"**{Path(path).name}** ({fmt.upper()}, {len(rows)} filas)\n\n"
        return header + _compute_stats(rows)

    async def _handle_filter(self, rest: str) -> SkillResult:
        if "|" not in rest:
            return SkillResult(
                success=False,
                message="Uso: `filtrar <archivo> | <columna> | <valor>`",
            )
        segments = [s.strip() for s in rest.split("|")]
        if len(segments) < 3:
            return SkillResult(
                success=False,
                message="Uso: `filtrar <archivo> | <columna> | <valor>`",
            )
        file_path, column, value = segments[0], segments[1], segments[2]

        def do_filter() -> str:
            text = _read_file(file_path)
            fmt, rows = _detect_and_load(text, file_path)
            if not rows:
                return f"No se pudieron leer datos de `{file_path}`."
            filtered = _filter_rows(rows, column, value)
            header = f"**Filtrado:** `{column}` = `{value}` — {len(filtered)}/{len(rows)} filas\n"
            return header + _format_table(filtered)

        msg = await asyncio.to_thread(do_filter)
        return SkillResult(success=True, message=msg)

    async def _handle_sort(self, rest: str) -> SkillResult:
        if "|" not in rest:
            return SkillResult(
                success=False,
                message="Uso: `ordenar <archivo> | <columna> [asc|desc]`",
            )
        segments = [s.strip() for s in rest.split("|")]
        if len(segments) < 2:
            return SkillResult(
                success=False,
                message="Uso: `ordenar <archivo> | <columna> [asc|desc]`",
            )
        file_path = segments[0]
        col_parts = segments[1].split()
        column = col_parts[0]
        descending = len(col_parts) > 1 and col_parts[1].lower() == "desc"

        def do_sort() -> str:
            text = _read_file(file_path)
            fmt, rows = _detect_and_load(text, file_path)
            if not rows:
                return f"No se pudieron leer datos de `{file_path}`."
            sorted_rows = _sort_rows(rows, column, descending)
            direction = "desc" if descending else "asc"
            header = f"**Ordenado por** `{column}` ({direction}) — {len(sorted_rows)} filas\n"
            return header + _format_table(sorted_rows)

        msg = await asyncio.to_thread(do_sort)
        return SkillResult(success=True, message=msg)

    @staticmethod
    def _parse_inline(data: str) -> str:
        """Try to parse inline text as JSON, CSV, or YAML and display it."""
        # Try JSON
        try:
            parsed = json.loads(data)
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                return "**Datos (JSON):**\n" + _format_table(parsed)
            return "**Datos (JSON):**\n```json\n" + json.dumps(parsed, indent=2, ensure_ascii=False) + "\n```"
        except (json.JSONDecodeError, ValueError):
            pass

        # Try CSV
        rows = _parse_csv(data)
        if rows and any(rows[0].values()):
            return "**Datos (CSV):**\n" + _format_table(rows)

        # Try YAML
        try:
            parsed = _yaml_loads(data)
            if parsed:
                if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                    return "**Datos (YAML):**\n" + _format_table(parsed)
                return "**Datos (YAML):**\n```\n" + json.dumps(parsed, indent=2, ensure_ascii=False) + "\n```"
        except Exception:
            pass

        return f"No se pudo parsear los datos proporcionados.\nTexto recibido:\n```\n{data[:_MAX_DISPLAY]}\n```"
