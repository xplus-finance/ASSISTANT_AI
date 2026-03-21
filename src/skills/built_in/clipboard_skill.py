"""Clipboard manager skill: copy, paste, history, search, pin."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from typing import Any

import structlog

from src.memory.engine import MemoryEngine, sanitize_fts_query
from src.skills.base_skill import BaseSkill, SkillResult
from src.utils.platform import IS_LINUX, IS_MACOS, IS_WINDOWS

log = structlog.get_logger("assistant.skills.clipboard")

_TABLE_DDL = """\
CREATE TABLE IF NOT EXISTS clipboard_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    content_type TEXT DEFAULT 'text',
    source TEXT,
    copied_at TEXT DEFAULT (datetime('now')),
    pinned INTEGER DEFAULT 0
);
"""

_INDEX_DDL = """\
CREATE INDEX IF NOT EXISTS idx_clipboard_copied_at
    ON clipboard_history(copied_at);
CREATE INDEX IF NOT EXISTS idx_clipboard_pinned
    ON clipboard_history(pinned);
"""


def _detect_clipboard_tool() -> tuple[str, str] | None:
    """Return (copy_cmd, paste_cmd) names or None if nothing available."""
    if IS_MACOS:
        return ("pbcopy", "pbpaste")
    if IS_WINDOWS:
        return ("clip", "powershell -command Get-Clipboard")
    # Linux — prefer xclip, fall back to xsel
    if shutil.which("xclip"):
        return ("xclip -selection clipboard", "xclip -selection clipboard -o")
    if shutil.which("xsel"):
        return ("xsel --clipboard --input", "xsel --clipboard --output")
    return None


class ClipboardSkill(BaseSkill):
    """Gestiona el portapapeles del sistema con historial persistente."""

    def __init__(self, memory_engine: MemoryEngine | None = None) -> None:
        self._memory = memory_engine
        self._table_ready = False

    # -- BaseSkill interface ---------------------------------------------------

    @property
    def name(self) -> str:
        return "clipboard"

    @property
    def description(self) -> str:
        return "Gestiona el portapapeles: copiar, pegar, historial, buscar, pin"

    @property
    def natural_patterns(self) -> dict[str, list[str]]:
        return {
            "historial": [
                r"(?:qu[eé]|mu[eé]strame|dame|ver)\s+(?:lo\s+que\s+)?(?:he\s+)?copi(?:ado|é)",
                r"(?:historial|lista)\s+(?:del?\s+)?clipboard",
                r"(?:historial|lista)\s+(?:del?\s+)?portapapeles",
                r"(?:mis?\s+)?copiados?\s+recientes?",
                r"(?:qu[eé]|ver)\s+(?:tengo|hay)\s+(?:en\s+(?:el\s+)?)?(?:clipboard|portapapeles)",
            ],
            "copiar": [
                r"copia(?:r|me)?\s+(?:esto|al\s+portapapeles)\s*(?P<args>.+)?",
                r"pon(?:er|me)?\s+(?:en\s+(?:el\s+)?)?(?:clipboard|portapapeles)\s+(?P<args>.+)",
            ],
            "pegar": [
                r"(?:pega|paste)\s*(?:me)?(?:\s+(?:lo\s+)?(?:del?\s+)?(?:clipboard|portapapeles))?",
                r"(?:qu[eé]\s+hay|qu[eé]\s+tengo)\s+(?:en\s+(?:el\s+)?)?(?:clipboard|portapapeles)",
            ],
            "buscar": [
                r"busca(?:r|me)?\s+(?:en\s+(?:el\s+)?)?(?:clipboard|portapapeles|copiados?)\s+(?P<args>.+)",
            ],
            "limpiar": [
                r"limpia(?:r)?\s+(?:el\s+)?(?:clipboard|portapapeles|historial\s+de\s+copiado)",
                r"borra(?:r)?\s+(?:el\s+)?(?:clipboard|portapapeles|historial\s+de\s+copiado)",
            ],
        }

    @property
    def triggers(self) -> list[str]:
        return ["!clipboard", "!clip", "!copiar", "!portapapeles", "!cb"]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        memory = self._memory or context.get("memory")
        if memory is None:
            return SkillResult(success=False, message="Motor de memoria no disponible.")

        await self._ensure_table(memory)

        parts = args.strip().split(None, 1)
        sub = parts[0].lower() if parts else ""
        rest = parts[1] if len(parts) > 1 else ""

        if sub in ("", "ver"):
            return await self._show_recent(memory, limit=10)
        if sub == "copiar":
            if not rest:
                return SkillResult(success=False, message="Uso: !cb copiar <texto>")
            return await self._copy(memory, rest)
        if sub == "pegar":
            return await self._paste(memory)
        if sub == "buscar":
            if not rest:
                return SkillResult(success=False, message="Uso: !cb buscar <query>")
            return await self._search(memory, rest)
        if sub == "pin":
            return await self._pin(memory, rest)
        if sub in ("limpiar", "clean"):
            return await self._cleanup(memory)
        if sub in ("historial", "todo", "all"):
            return await self._show_recent(memory, limit=50)

        # Unknown subcommand — treat the whole args as text to copy
        return await self._copy(memory, args.strip())

    # -- Subcommands -----------------------------------------------------------

    async def _copy(self, memory: MemoryEngine, text: str) -> SkillResult:
        """Copy text to system clipboard and save to history."""
        tool = _detect_clipboard_tool()
        if tool is None:
            return SkillResult(
                success=False,
                message=(
                    "No se encontró herramienta de portapapeles.\n"
                    "Instala xclip (`sudo apt install xclip`) o xsel (`sudo apt install xsel`)."
                ),
            )

        copy_cmd = tool[0]
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                copy_cmd.split(),
                input=text.encode(),
                capture_output=True,
                timeout=5,
            )
            if result.returncode != 0:
                stderr = result.stderr.decode(errors="replace").strip()
                return SkillResult(success=False, message=f"Error al copiar: {stderr}")
        except FileNotFoundError:
            return SkillResult(
                success=False,
                message=f"Comando no encontrado: {copy_cmd.split()[0]}. Instala xclip o xsel.",
            )
        except subprocess.TimeoutExpired:
            return SkillResult(success=False, message="Timeout copiando al portapapeles.")

        entry_id = await asyncio.to_thread(
            memory.insert_returning_id,
            "INSERT INTO clipboard_history (content, content_type, source) VALUES (?, ?, ?)",
            (text, "text", "manual"),
        )

        preview = text[:80] + ("..." if len(text) > 80 else "")
        log.info("clipboard.copied", entry_id=entry_id, length=len(text))
        return SkillResult(
            success=True,
            message=f"Copiado al portapapeles (#{entry_id}):\n`{preview}`",
        )

    async def _paste(self, memory: MemoryEngine) -> SkillResult:
        """Get current clipboard content and save to history."""
        tool = _detect_clipboard_tool()
        if tool is None:
            return SkillResult(
                success=False,
                message=(
                    "No se encontró herramienta de portapapeles.\n"
                    "Instala xclip (`sudo apt install xclip`) o xsel (`sudo apt install xsel`)."
                ),
            )

        paste_cmd = tool[1]
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                paste_cmd.split(),
                capture_output=True,
                timeout=5,
            )
            if result.returncode != 0:
                stderr = result.stderr.decode(errors="replace").strip()
                return SkillResult(success=False, message=f"Error al pegar: {stderr}")
        except FileNotFoundError:
            return SkillResult(
                success=False,
                message=f"Comando no encontrado: {paste_cmd.split()[0]}. Instala xclip o xsel.",
            )
        except subprocess.TimeoutExpired:
            return SkillResult(success=False, message="Timeout leyendo el portapapeles.")

        content = result.stdout.decode(errors="replace")
        if not content.strip():
            return SkillResult(success=True, message="El portapapeles está vacío.")

        entry_id = await asyncio.to_thread(
            memory.insert_returning_id,
            "INSERT INTO clipboard_history (content, content_type, source) VALUES (?, ?, ?)",
            (content, "text", "paste"),
        )

        preview = content[:200] + ("..." if len(content) > 200 else "")
        log.info("clipboard.pasted", entry_id=entry_id, length=len(content))
        return SkillResult(
            success=True,
            message=f"Contenido del portapapeles (#{entry_id}):\n```\n{preview}\n```",
        )

    async def _search(self, memory: MemoryEngine, query: str) -> SkillResult:
        """Search clipboard history by content."""
        safe_query = sanitize_fts_query(query)
        if not safe_query:
            return SkillResult(success=False, message="Query de búsqueda inválida.")

        # Use LIKE as fallback since clipboard_history has no FTS table
        like_pattern = f"%{query}%"
        rows = await asyncio.to_thread(
            memory.fetchall,
            "SELECT id, content, copied_at, pinned FROM clipboard_history "
            "WHERE content LIKE ? ORDER BY copied_at DESC LIMIT 20",
            (like_pattern,),
        )

        if not rows:
            return SkillResult(success=True, message=f"No se encontraron entradas para: {query}")

        lines: list[str] = [f"Resultados para \"{query}\" ({len(rows)}):"]
        for row in rows:
            entry_id, content, copied_at, pinned = row
            pin_mark = " 📌" if pinned else ""
            preview = content[:60].replace("\n", " ") + ("..." if len(content) > 60 else "")
            lines.append(f"  #{entry_id}{pin_mark} [{copied_at}] {preview}")

        return SkillResult(success=True, message="\n".join(lines))

    async def _pin(self, memory: MemoryEngine, id_str: str) -> SkillResult:
        """Toggle pin on a clipboard entry."""
        if not id_str.strip():
            return SkillResult(success=False, message="Uso: !cb pin <id>")

        try:
            entry_id = int(id_str.strip().lstrip("#"))
        except ValueError:
            return SkillResult(success=False, message=f"ID inválido: {id_str}")

        row = await asyncio.to_thread(
            memory.fetchone,
            "SELECT pinned FROM clipboard_history WHERE id = ?",
            (entry_id,),
        )
        if row is None:
            return SkillResult(success=False, message=f"No existe la entrada #{entry_id}.")

        new_pinned = 0 if row[0] else 1
        await asyncio.to_thread(
            memory.execute,
            "UPDATE clipboard_history SET pinned = ? WHERE id = ?",
            (new_pinned, entry_id),
        )

        action = "fijada" if new_pinned else "desfijada"
        log.info("clipboard.pin_toggled", entry_id=entry_id, pinned=bool(new_pinned))
        return SkillResult(success=True, message=f"Entrada #{entry_id} {action}.")

    async def _cleanup(self, memory: MemoryEngine) -> SkillResult:
        """Remove non-pinned entries older than 7 days."""
        deleted = await asyncio.to_thread(
            memory.fetchone,
            "SELECT COUNT(*) FROM clipboard_history "
            "WHERE pinned = 0 AND copied_at < datetime('now', '-7 days')",
        )
        count = deleted[0] if deleted else 0

        if count == 0:
            return SkillResult(success=True, message="No hay entradas antiguas para limpiar.")

        await asyncio.to_thread(
            memory.execute,
            "DELETE FROM clipboard_history "
            "WHERE pinned = 0 AND copied_at < datetime('now', '-7 days')",
        )

        log.info("clipboard.cleanup", deleted=count)
        return SkillResult(success=True, message=f"Eliminadas {count} entradas antiguas (>7 días).")

    async def _show_recent(self, memory: MemoryEngine, limit: int = 10) -> SkillResult:
        """Show recent clipboard entries."""
        rows = await asyncio.to_thread(
            memory.fetchall,
            "SELECT id, content, copied_at, pinned FROM clipboard_history "
            "ORDER BY copied_at DESC LIMIT ?",
            (limit,),
        )

        if not rows:
            return SkillResult(success=True, message="El historial del portapapeles está vacío.")

        label = "completo" if limit > 10 else "reciente"
        lines: list[str] = [f"Portapapeles — historial {label} ({len(rows)} entradas):"]
        for row in rows:
            entry_id, content, copied_at, pinned = row
            pin_mark = " 📌" if pinned else ""
            preview = content[:60].replace("\n", " ") + ("..." if len(content) > 60 else "")
            lines.append(f"  #{entry_id}{pin_mark} [{copied_at}] {preview}")

        return SkillResult(success=True, message="\n".join(lines))

    # -- Internal helpers ------------------------------------------------------

    async def _ensure_table(self, memory: MemoryEngine) -> None:
        """Create the clipboard_history table if it doesn't exist yet."""
        if self._table_ready:
            return
        await asyncio.to_thread(memory.execute, _TABLE_DDL)
        for stmt in _INDEX_DDL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                await asyncio.to_thread(memory.execute, stmt + ";")
        self._table_ready = True
        log.debug("clipboard.table_ready")
