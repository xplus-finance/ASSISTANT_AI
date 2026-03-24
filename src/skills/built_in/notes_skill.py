"""Notes Manager skill: create, search, organize and export personal notes.

Syncs with the StickyNotes desktop app (PyQt6) via REST API on port 17532.
Notes are stored in both the assistant's MemoryEngine AND the desktop app,
so they appear as visual sticky notes on the user's screen.
"""

from __future__ import annotations

import asyncio
import json
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any

import structlog

from src.memory.engine import MemoryEngine, sanitize_fts_query
from src.skills.base_skill import BaseSkill, SkillResult

log = structlog.get_logger("assistant.skills.notes")

STICKYNOTES_API = "http://127.0.0.1:17532"

CATEGORY_COLOR_MAP = {
    "nota": "#FDFD96",
    "proyecto": "#C7CEEA",
    "idea": "#FFDAC1",
    "bug": "#FFB7B2",
    "tarea": "#B5EAD7",
    "recordatorio": "#E2B6CF",
}


def _sticky_api(method: str, path: str, data: dict | None = None) -> dict | None:
    """Call the StickyNotes desktop app API. Returns None if app is not running."""
    url = f"{STICKYNOTES_API}{path}"
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return None

_TAG_RE = re.compile(r"@(\w+)")
_PROJECT_RE = re.compile(r"#(\w+)")

_NOTES_TABLES = """
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    project TEXT,
    tags TEXT,
    is_pinned INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    title, content, tags, content='notes', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
    INSERT INTO notes_fts(rowid, title, content, tags)
        VALUES (new.id, new.title, new.content, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
    INSERT INTO notes_fts(notes_fts, rowid, title, content, tags)
        VALUES ('delete', old.id, old.title, old.content, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
    INSERT INTO notes_fts(notes_fts, rowid, title, content, tags)
        VALUES ('delete', old.id, old.title, old.content, old.tags);
    INSERT INTO notes_fts(rowid, title, content, tags)
        VALUES (new.id, new.title, new.content, new.tags);
END;

CREATE INDEX IF NOT EXISTS idx_notes_project ON notes(project);
CREATE INDEX IF NOT EXISTS idx_notes_pinned ON notes(is_pinned DESC, updated_at DESC);
"""


class NotesSkill(BaseSkill):
    """Manage personal notes with projects, tags, pinning and FTS search."""

    def __init__(self, memory_engine: MemoryEngine | None = None) -> None:
        self._memory = memory_engine
        self._tables_ready = False

    @property
    def name(self) -> str:
        return "notes"

    @property
    def description(self) -> str:
        return "Gestor de notas personales con proyectos, tags, busqueda y exportacion"

    @property
    def natural_patterns(self) -> dict[str, list[str]]:
        return {
            "nueva": [
                r"(?:anota|apunta|escribe|guarda)\s+(?:una?\s+)?(?:nota|apunte)?\s*(?:que\s+)?(?P<args>.+)",
                r"(?:nueva|crear?)\s+nota(?:\s+(?:sobre|de|que)\s+(?P<args>.+))?",
                r"toma\s+nota\s+(?:de\s+)?(?:que\s+)?(?P<args>.+)",
            ],
            "buscar": [
                r"busca(?:r|me)?\s+(?:en\s+)?(?:mis?\s+)?notas?\s+(?P<args>.+)",
                r"(?:qu[eé]\s+anoté|qu[eé]\s+apunté)\s+(?:sobre|de)\s+(?P<args>.+)",
                r"(?:encuentra|dame)\s+(?:la\s+)?nota\s+(?:de|sobre|que)\s+(?P<args>.+)",
            ],
            "ver": [
                r"(?:mu[eé]strame|ver|dame|lee)\s+(?:mis?\s+)?notas?",
                r"(?:qu[eé]|cu[aá]les?)\s+notas?\s+(?:tengo|hay)",
                r"(?:mis?\s+)?(?:notas?|apuntes?)\s+recientes?",
            ],
            "proyecto": [
                r"(?:notas?\s+del?\s+proyecto|apuntes?\s+del?\s+proyecto)\s+(?P<args>.+)",
            ],
            "tags": [
                r"(?:qu[eé]|cu[aá]les?)\s+(?:tags?|etiquetas?)\s+(?:tengo|hay)\s+(?:en\s+)?(?:notas?|apuntes?)",
            ],
        }

    @property
    def triggers(self) -> list[str]:
        return ["!nota", "!notas", "!note", "!notes", "!apunte", "!apuntes"]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        memory = self._memory or context.get("memory")
        if memory is None:
            return SkillResult(success=False, message="Motor de memoria no disponible.")

        await asyncio.to_thread(self._ensure_tables, memory)

        if not args:
            return await asyncio.to_thread(self._list_recent, memory)

        parts = args.split(maxsplit=1)
        sub = parts[0].lower()
        rest = parts[1] if len(parts) > 1 else ""

        dispatch: dict[str, Any] = {
            "nueva": lambda: self._create_note(memory, rest),
            "new": lambda: self._create_note(memory, rest),
            "ver": lambda: self._view_note(memory, rest),
            "view": lambda: self._view_note(memory, rest),
            "buscar": lambda: self._search(memory, rest),
            "search": lambda: self._search(memory, rest),
            "editar": lambda: self._edit_note(memory, rest),
            "edit": lambda: self._edit_note(memory, rest),
            "eliminar": lambda: self._delete_note(memory, rest),
            "delete": lambda: self._delete_note(memory, rest),
            "pin": lambda: self._toggle_pin(memory, rest),
            "proyecto": lambda: self._list_by_project(memory, rest),
            "project": lambda: self._list_by_project(memory, rest),
            "tags": lambda: self._list_tags(memory),
            "tag": lambda: self._list_by_tag(memory, rest),
            "exportar": lambda: self._export_notes(memory, rest),
            "export": lambda: self._export_notes(memory, rest),
        }

        handler = dispatch.get(sub)
        if handler is not None:
            return await asyncio.to_thread(handler)

        # No recognized subcommand — try to interpret as note ID for viewing
        try:
            int(sub)
            return await asyncio.to_thread(self._view_note, memory, sub)
        except ValueError:
            pass

        # Fall back to search
        return await asyncio.to_thread(self._search, memory, args)

    # ------------------------------------------------------------------
    # Table initialization
    # ------------------------------------------------------------------

    def _ensure_tables(self, memory: MemoryEngine) -> None:
        if self._tables_ready:
            return
        for statement in _split_note_statements(_NOTES_TABLES):
            try:
                memory.execute(statement)
            except Exception as exc:  # noqa: BLE001
                # Table/trigger may already exist from a previous session
                log.debug("notes.table_init_skip", statement=statement[:60], error=str(exc))
        self._tables_ready = True
        log.info("notes.tables_ready")

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def _create_note(self, memory: MemoryEngine, raw: str) -> SkillResult:
        if not raw.strip():
            return SkillResult(
                success=False,
                message=(
                    "Uso: !nota nueva <titulo> | <contenido>\n"
                    "Opcional: #proyecto @tag1 @tag2"
                ),
            )

        if "|" in raw:
            title_part, content_part = raw.split("|", 1)
            title = title_part.strip()
            content = content_part.strip()
        else:
            # No separator — first line is title, rest is content
            lines = raw.strip().splitlines()
            title = lines[0].strip()
            content = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""

        if not title:
            return SkillResult(success=False, message="El titulo no puede estar vacio.")

        # Extract project from #tag in title or content
        project: str | None = None
        project_match = _PROJECT_RE.search(title) or _PROJECT_RE.search(content)
        if project_match:
            project = project_match.group(1)
            # Remove #project from title and content
            title = _PROJECT_RE.sub("", title).strip()
            content = _PROJECT_RE.sub("", content).strip()

        # Extract @tags from title and content
        all_text = f"{title} {content}"
        tag_matches = _TAG_RE.findall(all_text)
        tags_str: str | None = None
        if tag_matches:
            tags_str = ",".join(sorted(set(t.lower() for t in tag_matches)))
            # Remove @tags from title and content
            title = _TAG_RE.sub("", title).strip()
            content = _TAG_RE.sub("", content).strip()

        note_id = memory.insert_returning_id(
            """
            INSERT INTO notes (title, content, project, tags)
            VALUES (?, ?, ?, ?)
            """,
            (title, content, project, tags_str),
        )

        log.info("notes.created", id=note_id, project=project, tags=tags_str)

        # ── Sync to StickyNotes desktop app ──
        sticky_id = None
        category = "proyecto" if project else "nota"
        if tags_str and "idea" in tags_str:
            category = "idea"
        elif tags_str and "bug" in tags_str:
            category = "bug"

        sticky_data = {
            "title": title,
            "content": content,
            "category": category,
            "color": CATEGORY_COLOR_MAP.get(category, "#FDFD96"),
        }
        if tags_str:
            sticky_data["tags"] = [t.strip() for t in tags_str.split(",") if t.strip()]

        result = _sticky_api("POST", "/notes", sticky_data)
        if result and "id" in result:
            sticky_id = result["id"]
            log.info("notes.synced_to_sticky", note_id=note_id, sticky_id=sticky_id)

        msg_parts = [f"📝 Nota #{note_id} creada: {title}"]
        if project:
            msg_parts.append(f"Proyecto: {project}")
        if tags_str:
            msg_parts.append(f"Tags: {tags_str}")
        if sticky_id:
            msg_parts.append("📌 Papelito puesto en tu escritorio.")
        else:
            msg_parts.append("(StickyNotes no está corriendo — nota guardada solo en memoria)")

        return SkillResult(
            success=True,
            message="\n".join(msg_parts),
            data={"id": note_id, "title": title, "project": project, "tags": tags_str, "sticky_id": sticky_id},
        )

    # ------------------------------------------------------------------
    # View / List
    # ------------------------------------------------------------------

    def _list_recent(self, memory: MemoryEngine) -> SkillResult:
        rows = memory.fetchall_dicts(
            """
            SELECT id, title, project, tags, is_pinned, created_at
            FROM notes
            ORDER BY is_pinned DESC, updated_at DESC
            LIMIT 15
            """,
        )

        if not rows:
            return SkillResult(success=True, message="No hay notas guardadas.")

        lines = ["Notas recientes:", ""]
        for row in rows:
            pin = "\U0001f4cc " if row["is_pinned"] else ""
            proj = f" [{row['project']}]" if row["project"] else ""
            tags = f" ({row['tags']})" if row["tags"] else ""
            date = row["created_at"][:10] if row["created_at"] else ""
            lines.append(f"  {pin}#{row['id']} {row['title']}{proj}{tags}  {date}")

        total = memory.fetchone("SELECT COUNT(*) FROM notes")
        count = total[0] if total else 0
        if count > 15:
            lines.append(f"\nMostrando 15 de {count} notas. Usa '!nota buscar <texto>' para filtrar.")

        return SkillResult(success=True, message="\n".join(lines))

    def _view_note(self, memory: MemoryEngine, args: str) -> SkillResult:
        if not args.strip():
            return self._list_recent(memory)

        try:
            note_id = int(args.strip().lstrip("#"))
        except ValueError:
            return SkillResult(success=False, message=f"ID invalido: {args}. Debe ser un numero.")

        row = memory.fetchone(
            """
            SELECT id, title, content, project, tags, is_pinned, created_at, updated_at
            FROM notes WHERE id = ?
            """,
            (note_id,),
        )

        if row is None:
            return SkillResult(success=False, message=f"Nota #{note_id} no encontrada.")

        nid, title, content, project, tags, pinned, created, updated = row
        pin_label = " [FIJADA]" if pinned else ""
        lines = [
            f"Nota #{nid}{pin_label}: {title}",
            f"Creada: {created}  |  Actualizada: {updated}",
        ]
        if project:
            lines.append(f"Proyecto: {project}")
        if tags:
            lines.append(f"Tags: {tags}")
        lines.append("")
        lines.append(content if content else "(sin contenido)")

        return SkillResult(success=True, message="\n".join(lines))

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _search(self, memory: MemoryEngine, query: str) -> SkillResult:
        if not query.strip():
            return SkillResult(success=False, message="Uso: !nota buscar <termino>")

        safe_query = sanitize_fts_query(query.strip())
        if not safe_query:
            return SkillResult(success=False, message="La busqueda no contiene terminos validos.")

        rows = memory.fetchall_dicts(
            """
            SELECT n.id, n.title, n.project, n.tags, n.is_pinned, n.created_at
            FROM notes n
            JOIN notes_fts ON notes_fts.rowid = n.id
            WHERE notes_fts MATCH ?
            ORDER BY rank
            LIMIT 20
            """,
            (safe_query,),
        )

        if not rows:
            return SkillResult(success=True, message=f"No se encontraron notas para '{query.strip()}'.")

        lines = [f"Resultados para '{query.strip()}':", ""]
        for row in rows:
            pin = "\U0001f4cc " if row["is_pinned"] else ""
            proj = f" [{row['project']}]" if row["project"] else ""
            lines.append(f"  {pin}#{row['id']} {row['title']}{proj}")

        return SkillResult(success=True, message="\n".join(lines))

    # ------------------------------------------------------------------
    # Edit
    # ------------------------------------------------------------------

    def _edit_note(self, memory: MemoryEngine, args: str) -> SkillResult:
        if not args.strip() or "|" not in args:
            return SkillResult(
                success=False,
                message="Uso: !nota editar <id> | <nuevo contenido>",
            )

        id_part, new_content = args.split("|", 1)
        try:
            note_id = int(id_part.strip().lstrip("#"))
        except ValueError:
            return SkillResult(success=False, message=f"ID invalido: {id_part.strip()}")

        existing = memory.fetchone("SELECT id FROM notes WHERE id = ?", (note_id,))
        if existing is None:
            return SkillResult(success=False, message=f"Nota #{note_id} no encontrada.")

        new_content = new_content.strip()
        memory.execute(
            """
            UPDATE notes SET content = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (new_content, note_id),
        )

        log.info("notes.edited", id=note_id)
        return SkillResult(
            success=True,
            message=f"Nota #{note_id} actualizada.",
            data={"id": note_id},
        )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def _delete_note(self, memory: MemoryEngine, args: str) -> SkillResult:
        if not args.strip():
            return SkillResult(success=False, message="Uso: !nota eliminar <id>")

        try:
            note_id = int(args.strip().lstrip("#"))
        except ValueError:
            return SkillResult(success=False, message=f"ID invalido: {args.strip()}")

        row = memory.fetchone("SELECT title FROM notes WHERE id = ?", (note_id,))
        if row is None:
            return SkillResult(success=False, message=f"Nota #{note_id} no encontrada.")

        memory.execute("DELETE FROM notes WHERE id = ?", (note_id,))

        # Also try to delete from StickyNotes app (best-effort, same ID may not match)
        _sticky_api("DELETE", f"/notes/{note_id}")

        log.info("notes.deleted", id=note_id)
        return SkillResult(
            success=True,
            message=f"🗑️ Nota #{note_id} eliminada: {row[0][:80]}",
        )

    # ------------------------------------------------------------------
    # Pin
    # ------------------------------------------------------------------

    def _toggle_pin(self, memory: MemoryEngine, args: str) -> SkillResult:
        if not args.strip():
            return SkillResult(success=False, message="Uso: !nota pin <id>")

        try:
            note_id = int(args.strip().lstrip("#"))
        except ValueError:
            return SkillResult(success=False, message=f"ID invalido: {args.strip()}")

        row = memory.fetchone(
            "SELECT title, is_pinned FROM notes WHERE id = ?", (note_id,),
        )
        if row is None:
            return SkillResult(success=False, message=f"Nota #{note_id} no encontrada.")

        new_pinned = 0 if row[1] else 1
        memory.execute(
            "UPDATE notes SET is_pinned = ?, updated_at = datetime('now') WHERE id = ?",
            (new_pinned, note_id),
        )

        state = "fijada" if new_pinned else "desfijada"
        log.info("notes.pin_toggled", id=note_id, pinned=bool(new_pinned))
        return SkillResult(
            success=True,
            message=f"Nota #{note_id} {state}: {row[0][:80]}",
        )

    # ------------------------------------------------------------------
    # Project
    # ------------------------------------------------------------------

    def _list_by_project(self, memory: MemoryEngine, args: str) -> SkillResult:
        project = args.strip().lstrip("#")
        if not project:
            # List all projects with counts
            rows = memory.fetchall_dicts(
                """
                SELECT project, COUNT(*) as cnt
                FROM notes
                WHERE project IS NOT NULL AND project != ''
                GROUP BY project
                ORDER BY cnt DESC
                """,
            )
            if not rows:
                return SkillResult(success=True, message="No hay notas asignadas a proyectos.")

            lines = ["Proyectos:", ""]
            for row in rows:
                lines.append(f"  #{row['project']}  ({row['cnt']} notas)")
            return SkillResult(success=True, message="\n".join(lines))

        rows = memory.fetchall_dicts(
            """
            SELECT id, title, tags, is_pinned, created_at
            FROM notes
            WHERE project = ?
            ORDER BY is_pinned DESC, updated_at DESC
            """,
            (project,),
        )

        if not rows:
            return SkillResult(success=True, message=f"No hay notas en el proyecto '{project}'.")

        lines = [f"Notas del proyecto '{project}' ({len(rows)}):", ""]
        for row in rows:
            pin = "\U0001f4cc " if row["is_pinned"] else ""
            tags = f" ({row['tags']})" if row["tags"] else ""
            lines.append(f"  {pin}#{row['id']} {row['title']}{tags}")

        return SkillResult(success=True, message="\n".join(lines))

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    def _list_tags(self, memory: MemoryEngine) -> SkillResult:
        rows = memory.fetchall(
            "SELECT tags FROM notes WHERE tags IS NOT NULL AND tags != ''",
        )

        if not rows:
            return SkillResult(success=True, message="No hay notas con tags.")

        tag_counts: dict[str, int] = {}
        for (tags_str,) in rows:
            for tag in tags_str.split(","):
                tag = tag.strip()
                if tag:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1

        sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)

        lines = ["Tags:", ""]
        for tag, count in sorted_tags:
            lines.append(f"  @{tag}  ({count} notas)")

        return SkillResult(success=True, message="\n".join(lines))

    def _list_by_tag(self, memory: MemoryEngine, args: str) -> SkillResult:
        tag = args.strip().lstrip("@").lower()
        if not tag:
            return self._list_tags(memory)

        # Search for notes containing this tag in the comma-separated tags field
        rows = memory.fetchall_dicts(
            """
            SELECT id, title, project, tags, is_pinned, created_at
            FROM notes
            WHERE ',' || tags || ',' LIKE ?
            ORDER BY is_pinned DESC, updated_at DESC
            """,
            (f"%,{tag},%",),
        )

        # Also check notes where the tag is the only tag (no commas)
        rows_single = memory.fetchall_dicts(
            """
            SELECT id, title, project, tags, is_pinned, created_at
            FROM notes
            WHERE tags = ?
            ORDER BY is_pinned DESC, updated_at DESC
            """,
            (tag,),
        )

        # Merge and deduplicate
        seen_ids: set[int] = set()
        merged: list[dict[str, Any]] = []
        for row in rows + rows_single:
            if row["id"] not in seen_ids:
                seen_ids.add(row["id"])
                merged.append(row)

        if not merged:
            return SkillResult(success=True, message=f"No hay notas con el tag '@{tag}'.")

        lines = [f"Notas con tag '@{tag}' ({len(merged)}):", ""]
        for row in merged:
            pin = "\U0001f4cc " if row["is_pinned"] else ""
            proj = f" [{row['project']}]" if row["project"] else ""
            lines.append(f"  {pin}#{row['id']} {row['title']}{proj}")

        return SkillResult(success=True, message="\n".join(lines))

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _export_notes(self, memory: MemoryEngine, args: str) -> SkillResult:
        project = args.strip().lstrip("#") if args.strip() else None

        if project:
            rows = memory.fetchall_dicts(
                """
                SELECT id, title, content, project, tags, is_pinned, created_at, updated_at
                FROM notes
                WHERE project = ?
                ORDER BY is_pinned DESC, created_at ASC
                """,
                (project,),
            )
            filename = f"notas_{project}.md"
            header = f"# Notas — Proyecto: {project}"
        else:
            rows = memory.fetchall_dicts(
                """
                SELECT id, title, content, project, tags, is_pinned, created_at, updated_at
                FROM notes
                ORDER BY project NULLS LAST, is_pinned DESC, created_at ASC
                """,
            )
            filename = "notas_export.md"
            header = "# Notas"

        if not rows:
            msg = f"No hay notas para exportar"
            if project:
                msg += f" en el proyecto '{project}'"
            return SkillResult(success=True, message=msg + ".")

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        md_lines = [header, f"\nExportado: {now_str}", f"Total: {len(rows)} notas\n"]

        current_project: str | None = "__NONE__"
        for row in rows:
            # Group by project
            if row["project"] != current_project and not project:
                current_project = row["project"]
                proj_label = current_project if current_project else "Sin proyecto"
                md_lines.append(f"\n## {proj_label}\n")

            pin = " (FIJADA)" if row["is_pinned"] else ""
            md_lines.append(f"### #{row['id']}: {row['title']}{pin}")
            if row["tags"]:
                md_lines.append(f"Tags: {row['tags']}")
            md_lines.append(f"Creada: {row['created_at']}  |  Actualizada: {row['updated_at']}")
            md_lines.append("")
            md_lines.append(row["content"] if row["content"] else "(sin contenido)")
            md_lines.append("")
            md_lines.append("---")
            md_lines.append("")

        content = "\n".join(md_lines)

        return SkillResult(
            success=True,
            message=f"Exportacion lista ({len(rows)} notas).\n\n{content}",
            data={"filename": filename, "content": content, "count": len(rows)},
        )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _split_note_statements(sql_block: str) -> list[str]:
    """Split SQL block into individual statements, respecting triggers."""
    statements: list[str] = []
    current: list[str] = []
    in_trigger = False

    for line in sql_block.strip().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue

        current.append(line)

        upper = stripped.upper()
        if upper.startswith("CREATE TRIGGER"):
            in_trigger = True

        if in_trigger:
            if upper == "END;":
                statements.append("\n".join(current))
                current = []
                in_trigger = False
        else:
            if stripped.endswith(";"):
                statements.append("\n".join(current))
                current = []

    if current:
        joined = "\n".join(current).strip()
        if joined:
            statements.append(joined)

    return statements
