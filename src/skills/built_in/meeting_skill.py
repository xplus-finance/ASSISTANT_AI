"""Meeting notes skill: create, annotate, and manage meeting minutes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import structlog

from src.memory.engine import MemoryEngine
from src.skills.base_skill import BaseSkill, SkillResult

log = structlog.get_logger("assistant.skills.meetings")

_MEETINGS_TABLE = """
CREATE TABLE IF NOT EXISTS meetings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    date TEXT DEFAULT (date('now')),
    attendees TEXT,
    notes TEXT,
    action_items TEXT,
    decisions TEXT,
    project TEXT,
    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'archived')),
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
"""

_MEETINGS_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_meetings_status ON meetings(status, date DESC);
CREATE INDEX IF NOT EXISTS idx_meetings_date ON meetings(date DESC);
CREATE INDEX IF NOT EXISTS idx_meetings_project ON meetings(project);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class MeetingSkill(BaseSkill):

    def __init__(self, memory_engine: MemoryEngine | None = None) -> None:
        self._memory = memory_engine
        self._table_ready = False

    # ── BaseSkill interface ──────────────────────────────────────────

    @property
    def name(self) -> str:
        return "meetings"

    @property
    def description(self) -> str:
        return "Gestionar notas de reuniones, minutas, acciones y decisiones"

    @property
    def natural_patterns(self) -> dict[str, list[str]]:
        return {
            "nueva": [
                r"(?:nueva|iniciar?|empezar?|crear?)\s+(?:una?\s+)?reuni[oó]n(?:\s+(?:con|de|sobre)\s+(?P<args>.+))?",
                r"(?:empez[oó]|inici[oó]|comenz[oó])\s+(?:la\s+)?reuni[oó]n(?:\s+(?:con|de)\s+(?P<args>.+))?",
                r"(?:nueva|crear?)\s+(?:una?\s+)?minuta(?:\s+(?:de|para)\s+(?P<args>.+))?",
            ],
            "nota": [
                r"(?:anota|apunta|agrega)\s+(?:a\s+la\s+reuni[oó]n|en\s+la\s+minuta)\s*(?::?\s*)?(?P<args>.+)",
                r"(?:nota\s+de\s+reuni[oó]n|nota\s+en\s+la\s+minuta)\s*(?::?\s*)?(?P<args>.+)",
            ],
            "accion": [
                r"(?:acci[oó]n|tarea|action)\s+(?:de\s+la\s+reuni[oó]n|para)\s+(?P<args>.+)",
                r"(?:asigna|asignar)\s+(?:a\s+)?(?P<args>.+)",
            ],
            "cerrar": [
                r"(?:cierra|termina|finaliza)\s+(?:la\s+)?reuni[oó]n",
            ],
            "lista": [
                r"(?:mu[eé]strame|ver|dame|cu[aá]les?)\s+(?:las?\s+|mis?\s+)?reuniones?",
                r"(?:historial|lista)\s+(?:de\s+)?reuniones?",
            ],
            "acciones": [
                r"(?:qu[eé]|cu[aá]les?)\s+acciones?\s+(?:hay\s+)?pendientes?\s+(?:de\s+)?reuniones?",
                r"(?:acciones?|tareas?)\s+pendientes?\s+(?:de\s+)?reuniones?",
            ],
        }

    @property
    def triggers(self) -> list[str]:
        return ["!reunion", "!reunión", "!meeting", "!meet", "!minuta", "!acta"]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        memory = self._memory or context.get("memory")
        if memory is None:
            return SkillResult(success=False, message="Motor de memoria no disponible.")

        self._ensure_table(memory)

        if not args:
            return self._show_current(memory)

        parts = args.split(maxsplit=1)
        sub = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""

        dispatch: dict[str, str] = {
            "nueva": "new",
            "new": "new",
            "crear": "new",
            "nota": "note",
            "note": "note",
            "accion": "action",
            "acción": "action",
            "action": "action",
            "decision": "decision",
            "decisión": "decision",
            "cerrar": "close",
            "close": "close",
            "archivar": "close",
            "ver": "view",
            "view": "view",
            "show": "view",
            "lista": "list",
            "list": "list",
            "buscar": "search",
            "search": "search",
            "acciones": "actions",
            "actions": "actions",
            "resumen": "summary",
            "summary": "summary",
            "exportar": "export",
            "export": "export",
        }

        action = dispatch.get(sub)

        if action == "new":
            return self._new_meeting(memory, rest)
        if action == "note":
            return self._add_note(memory, rest)
        if action == "action":
            return self._add_action(memory, rest)
        if action == "decision":
            return self._add_decision(memory, rest)
        if action == "close":
            return self._close_meeting(memory, rest)
        if action == "view":
            return self._view_meeting(memory, rest)
        if action == "list":
            return self._list_meetings(memory)
        if action == "search":
            return self._search_meetings(memory, rest)
        if action == "actions":
            return self._list_actions(memory, rest)
        if action == "summary":
            return self._summary(memory, rest)
        if action == "export":
            return self._export(memory, rest)

        # Unknown subcommand — treat as new meeting title
        return self._new_meeting(memory, args)

    # ── Table setup ──────────────────────────────────────────────────

    def _ensure_table(self, memory: MemoryEngine) -> None:
        if self._table_ready:
            return
        try:
            memory.execute(_MEETINGS_TABLE)
            for stmt in _MEETINGS_INDEXES.strip().splitlines():
                stmt = stmt.strip()
                if stmt:
                    memory.execute(stmt)
            self._table_ready = True
            log.info("meetings.table_ready")
        except Exception as exc:  # noqa: BLE001
            log.warning("meetings.table_create_failed", error=str(exc))
            # Table may already exist — mark ready and move on
            self._table_ready = True

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _parse_id(text: str) -> int | None:
        text = text.strip().lstrip("#")
        try:
            return int(text)
        except (ValueError, TypeError):
            return None

    def _get_active(self, memory: MemoryEngine) -> dict[str, Any] | None:
        rows = memory.fetchall_dicts(
            "SELECT * FROM meetings WHERE status = 'active' ORDER BY created_at DESC LIMIT 1",
        )
        return rows[0] if rows else None

    @staticmethod
    def _load_json_list(raw: str | None) -> list[Any]:
        if not raw:
            return []
        try:
            data = json.loads(raw)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    def _update_field(
        self, memory: MemoryEngine, meeting_id: int, field: str, value: Any
    ) -> None:
        serialized = json.dumps(value, ensure_ascii=False)
        memory.execute(
            f"UPDATE meetings SET {field} = ?, updated_at = ? WHERE id = ?",
            (serialized, _now_iso(), meeting_id),
        )

    def _get_meeting_by_id(self, memory: MemoryEngine, meeting_id: int) -> dict[str, Any] | None:
        rows = memory.fetchall_dicts(
            "SELECT * FROM meetings WHERE id = ?", (meeting_id,),
        )
        return rows[0] if rows else None

    # ── Subcommands ──────────────────────────────────────────────────

    def _new_meeting(self, memory: MemoryEngine, rest: str) -> SkillResult:
        if not rest.strip():
            return SkillResult(
                success=False,
                message=(
                    "Uso: !reunion nueva <titulo>\n"
                    "      !reunion nueva <titulo> | <asistente1, asistente2>"
                ),
            )

        # Parse title and optional attendees
        attendees: list[str] = []
        if "|" in rest:
            title_part, att_part = rest.split("|", 1)
            title = title_part.strip()
            attendees = [a.strip() for a in att_part.split(",") if a.strip()]
        else:
            title = rest.strip()

        # Extract project tag if present
        project: str | None = None
        if "#" in title:
            parts = title.rsplit("#", 1)
            title = parts[0].strip()
            project = parts[1].strip() or None

        attendees_json = json.dumps(attendees, ensure_ascii=False) if attendees else None
        notes_json = json.dumps([], ensure_ascii=False)
        actions_json = json.dumps([], ensure_ascii=False)
        decisions_json = json.dumps([], ensure_ascii=False)

        meeting_id = memory.insert_returning_id(
            """
            INSERT INTO meetings (title, date, attendees, notes, action_items, decisions, project)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (title, _today(), attendees_json, notes_json, actions_json, decisions_json, project),
        )

        log.info("meetings.created", id=meeting_id, title=title[:60])

        msg_lines = [f"Reunion #{meeting_id} creada: {title}"]
        if attendees:
            msg_lines.append(f"  Asistentes: {', '.join(attendees)}")
        if project:
            msg_lines.append(f"  Proyecto: {project}")
        msg_lines.append("")
        msg_lines.append("Usa !reunion nota <texto> para agregar notas.")

        return SkillResult(success=True, message="\n".join(msg_lines), data={"id": meeting_id})

    def _add_note(self, memory: MemoryEngine, text: str) -> SkillResult:
        if not text.strip():
            return SkillResult(success=False, message="Uso: !reunion nota <texto>")

        meeting = self._get_active(memory)
        if meeting is None:
            return SkillResult(
                success=False,
                message="No hay reunion activa. Crea una con: !reunion nueva <titulo>",
            )

        notes = self._load_json_list(meeting["notes"])
        notes.append({
            "text": text.strip(),
            "timestamp": _now_iso(),
        })
        self._update_field(memory, meeting["id"], "notes", notes)

        log.info("meetings.note_added", meeting_id=meeting["id"], note_len=len(text))
        return SkillResult(
            success=True,
            message=f"Nota agregada a reunion #{meeting['id']} ({len(notes)} notas total).",
        )

    def _add_action(self, memory: MemoryEngine, text: str) -> SkillResult:
        if not text.strip():
            return SkillResult(
                success=False,
                message="Uso: !reunion accion <descripcion> @responsable",
            )

        meeting = self._get_active(memory)
        if meeting is None:
            return SkillResult(
                success=False,
                message="No hay reunion activa. Crea una con: !reunion nueva <titulo>",
            )

        # Extract @assignee
        assignee: str | None = None
        words = text.split()
        for word in words:
            if word.startswith("@") and len(word) > 1:
                assignee = word[1:]
                break

        action_text = text.strip()
        if assignee:
            action_text = action_text.replace(f"@{assignee}", "").strip()

        actions = self._load_json_list(meeting["action_items"])
        actions.append({
            "text": action_text,
            "assignee": assignee,
            "done": False,
            "created_at": _now_iso(),
        })
        self._update_field(memory, meeting["id"], "action_items", actions)

        log.info("meetings.action_added", meeting_id=meeting["id"], assignee=assignee)
        resp = f"Accion agregada a reunion #{meeting['id']}"
        if assignee:
            resp += f" (asignada a {assignee})"
        return SkillResult(success=True, message=resp)

    def _add_decision(self, memory: MemoryEngine, text: str) -> SkillResult:
        if not text.strip():
            return SkillResult(success=False, message="Uso: !reunion decision <texto>")

        meeting = self._get_active(memory)
        if meeting is None:
            return SkillResult(
                success=False,
                message="No hay reunion activa. Crea una con: !reunion nueva <titulo>",
            )

        decisions = self._load_json_list(meeting["decisions"])
        decisions.append(text.strip())
        self._update_field(memory, meeting["id"], "decisions", decisions)

        log.info("meetings.decision_added", meeting_id=meeting["id"])
        return SkillResult(
            success=True,
            message=f"Decision registrada en reunion #{meeting['id']} ({len(decisions)} decisiones total).",
        )

    def _close_meeting(self, memory: MemoryEngine, rest: str) -> SkillResult:
        if rest.strip():
            meeting_id = self._parse_id(rest)
            if meeting_id is None:
                return SkillResult(success=False, message="Uso: !reunion cerrar [id]")
            meeting = self._get_meeting_by_id(memory, meeting_id)
        else:
            meeting = self._get_active(memory)

        if meeting is None:
            return SkillResult(success=False, message="No hay reunion activa para cerrar.")

        if meeting["status"] == "archived":
            return SkillResult(
                success=True,
                message=f"Reunion #{meeting['id']} ya estaba archivada.",
            )

        memory.execute(
            "UPDATE meetings SET status = 'archived', updated_at = ? WHERE id = ?",
            (_now_iso(), meeting["id"]),
        )

        log.info("meetings.closed", id=meeting["id"])

        # Generate closing summary
        summary = self._build_summary(meeting)
        return SkillResult(
            success=True,
            message=f"Reunion #{meeting['id']} cerrada.\n\n{summary}",
            data={"id": meeting["id"]},
        )

    def _show_current(self, memory: MemoryEngine) -> SkillResult:
        meeting = self._get_active(memory)
        if meeting is None:
            return SkillResult(
                success=True,
                message=(
                    "No hay reunion activa.\n"
                    "Crea una con: !reunion nueva <titulo>\n"
                    "Lista reuniones: !reunion lista"
                ),
            )
        return SkillResult(
            success=True,
            message=self._format_meeting(meeting),
            data=meeting,
        )

    def _view_meeting(self, memory: MemoryEngine, rest: str) -> SkillResult:
        if not rest.strip():
            return self._show_current(memory)

        meeting_id = self._parse_id(rest)
        if meeting_id is None:
            return SkillResult(success=False, message="Uso: !reunion ver [id]")

        meeting = self._get_meeting_by_id(memory, meeting_id)
        if meeting is None:
            return SkillResult(success=False, message=f"Reunion #{meeting_id} no encontrada.")

        return SkillResult(
            success=True,
            message=self._format_meeting(meeting),
            data=meeting,
        )

    def _list_meetings(self, memory: MemoryEngine) -> SkillResult:
        rows = memory.fetchall_dicts(
            """
            SELECT id, title, date, status, project,
                   attendees, action_items
            FROM meetings
            ORDER BY date DESC, created_at DESC
            LIMIT 30
            """,
        )

        if not rows:
            return SkillResult(success=True, message="No hay reuniones registradas.")

        lines = ["Reuniones:", ""]
        for row in rows:
            status_icon = "[*]" if row["status"] == "active" else "[v]"
            project = f" #{row['project']}" if row["project"] else ""

            # Count pending actions
            actions = self._load_json_list(row["action_items"])
            pending = sum(1 for a in actions if not a.get("done"))
            action_tag = f" ({pending} pendientes)" if pending else ""

            lines.append(
                f"  {status_icon} #{row['id']}: {row['title'][:55]} "
                f"({row['date']}){project}{action_tag}"
            )

        return SkillResult(success=True, message="\n".join(lines), data={"meetings": rows})

    def _search_meetings(self, memory: MemoryEngine, query: str) -> SkillResult:
        if not query.strip():
            return SkillResult(success=False, message="Uso: !reunion buscar <texto>")

        pattern = f"%{query.strip()}%"
        rows = memory.fetchall_dicts(
            """
            SELECT id, title, date, status, project, notes, decisions
            FROM meetings
            WHERE title LIKE ?
               OR notes LIKE ?
               OR decisions LIKE ?
               OR action_items LIKE ?
               OR attendees LIKE ?
            ORDER BY date DESC
            LIMIT 20
            """,
            (pattern, pattern, pattern, pattern, pattern),
        )

        if not rows:
            return SkillResult(success=True, message=f"Sin resultados para: {query}")

        lines = [f"Resultados para '{query}':", ""]
        for row in rows:
            status_icon = "[*]" if row["status"] == "active" else "[v]"
            lines.append(f"  {status_icon} #{row['id']}: {row['title'][:55]} ({row['date']})")

        return SkillResult(success=True, message="\n".join(lines), data={"results": rows})

    def _list_actions(self, memory: MemoryEngine, rest: str) -> SkillResult:
        if rest.strip():
            # Actions for specific meeting
            meeting_id = self._parse_id(rest)
            if meeting_id is None:
                return SkillResult(success=False, message="Uso: !reunion acciones [id]")
            meeting = self._get_meeting_by_id(memory, meeting_id)
            if meeting is None:
                return SkillResult(success=False, message=f"Reunion #{meeting_id} no encontrada.")
            return self._format_actions_for_meeting(meeting)

        # All pending actions across all meetings
        rows = memory.fetchall_dicts(
            """
            SELECT id, title, date, action_items, status
            FROM meetings
            WHERE action_items IS NOT NULL AND action_items != '[]'
            ORDER BY date DESC
            LIMIT 50
            """,
        )

        if not rows:
            return SkillResult(success=True, message="No hay acciones registradas.")

        lines = ["Acciones pendientes:", ""]
        total_pending = 0

        for row in rows:
            actions = self._load_json_list(row["action_items"])
            pending = [a for a in actions if not a.get("done")]
            if not pending:
                continue

            total_pending += len(pending)
            meeting_tag = f"#{row['id']} {row['title'][:40]}"
            status_tag = " (archivada)" if row["status"] == "archived" else ""
            lines.append(f"  [{meeting_tag}]{status_tag}:")

            for action in pending:
                assignee = f" @{action['assignee']}" if action.get("assignee") else ""
                lines.append(f"    [ ] {action['text']}{assignee}")

            lines.append("")

        if total_pending == 0:
            return SkillResult(success=True, message="No hay acciones pendientes.")

        lines.insert(1, f"  Total pendientes: {total_pending}")
        return SkillResult(success=True, message="\n".join(lines))

    def _format_actions_for_meeting(self, meeting: dict[str, Any]) -> SkillResult:
        actions = self._load_json_list(meeting["action_items"])
        if not actions:
            return SkillResult(
                success=True,
                message=f"Reunion #{meeting['id']} no tiene acciones.",
            )

        lines = [f"Acciones de reunion #{meeting['id']}: {meeting['title']}", ""]
        for i, action in enumerate(actions, 1):
            check = "[x]" if action.get("done") else "[ ]"
            assignee = f" @{action['assignee']}" if action.get("assignee") else ""
            lines.append(f"  {check} {i}. {action['text']}{assignee}")

        done_count = sum(1 for a in actions if a.get("done"))
        lines.append("")
        lines.append(f"  Completadas: {done_count}/{len(actions)}")

        return SkillResult(success=True, message="\n".join(lines))

    def _summary(self, memory: MemoryEngine, rest: str) -> SkillResult:
        if rest.strip():
            meeting_id = self._parse_id(rest)
            if meeting_id is None:
                return SkillResult(success=False, message="Uso: !reunion resumen <id>")
            meeting = self._get_meeting_by_id(memory, meeting_id)
        else:
            meeting = self._get_active(memory)

        if meeting is None:
            return SkillResult(success=False, message="Reunion no encontrada.")

        return SkillResult(
            success=True,
            message=self._build_summary(meeting),
            data=meeting,
        )

    def _export(self, memory: MemoryEngine, rest: str) -> SkillResult:
        if rest.strip():
            meeting_id = self._parse_id(rest)
            if meeting_id is None:
                return SkillResult(success=False, message="Uso: !reunion exportar <id>")
            meeting = self._get_meeting_by_id(memory, meeting_id)
        else:
            meeting = self._get_active(memory)

        if meeting is None:
            return SkillResult(success=False, message="Reunion no encontrada.")

        return SkillResult(
            success=True,
            message=self._build_markdown(meeting),
            data={"id": meeting["id"], "format": "markdown"},
        )

    # ── Formatting ───────────────────────────────────────────────────

    def _format_meeting(self, meeting: dict[str, Any]) -> str:
        status_label = "ACTIVA" if meeting["status"] == "active" else "ARCHIVADA"
        lines = [
            f"=== Reunion #{meeting['id']}: {meeting['title']} ===",
            f"  Fecha: {meeting['date']}  |  Estado: {status_label}",
        ]

        if meeting.get("project"):
            lines.append(f"  Proyecto: {meeting['project']}")

        # Attendees
        attendees = self._load_json_list(meeting.get("attendees"))
        if attendees:
            lines.append(f"  Asistentes: {', '.join(attendees)}")

        lines.append("")

        # Notes
        notes = self._load_json_list(meeting.get("notes"))
        if notes:
            lines.append("--- Notas ---")
            for note in notes:
                ts = note.get("timestamp", "")
                ts_short = ts[11:16] if len(ts) >= 16 else ts  # HH:MM
                lines.append(f"  [{ts_short}] {note.get('text', '')}")
            lines.append("")

        # Decisions
        decisions = self._load_json_list(meeting.get("decisions"))
        if decisions:
            lines.append("--- Decisiones ---")
            for i, dec in enumerate(decisions, 1):
                lines.append(f"  {i}. {dec}")
            lines.append("")

        # Action items
        actions = self._load_json_list(meeting.get("action_items"))
        if actions:
            lines.append("--- Acciones ---")
            for i, action in enumerate(actions, 1):
                check = "[x]" if action.get("done") else "[ ]"
                assignee = f" @{action['assignee']}" if action.get("assignee") else ""
                lines.append(f"  {check} {i}. {action.get('text', '')}{assignee}")
            lines.append("")

        # Stats
        if notes or actions or decisions:
            done_actions = sum(1 for a in actions if a.get("done"))
            lines.append(
                f"  {len(notes)} notas | {len(decisions)} decisiones | "
                f"{done_actions}/{len(actions)} acciones completadas"
            )

        return "\n".join(lines)

    def _build_summary(self, meeting: dict[str, Any]) -> str:
        notes = self._load_json_list(meeting.get("notes"))
        decisions = self._load_json_list(meeting.get("decisions"))
        actions = self._load_json_list(meeting.get("action_items"))
        attendees = self._load_json_list(meeting.get("attendees"))

        lines = [
            f"RESUMEN: {meeting['title']}",
            f"Fecha: {meeting['date']}",
        ]

        if attendees:
            lines.append(f"Asistentes: {', '.join(attendees)}")
        if meeting.get("project"):
            lines.append(f"Proyecto: {meeting['project']}")

        lines.append("")

        # Key points from notes
        if notes:
            lines.append("PUNTOS TRATADOS:")
            for note in notes:
                lines.append(f"  - {note.get('text', '')}")
            lines.append("")

        # Decisions
        if decisions:
            lines.append("DECISIONES TOMADAS:")
            for i, dec in enumerate(decisions, 1):
                lines.append(f"  {i}. {dec}")
            lines.append("")

        # Actions
        if actions:
            pending = [a for a in actions if not a.get("done")]
            done = [a for a in actions if a.get("done")]

            if pending:
                lines.append("ACCIONES PENDIENTES:")
                for action in pending:
                    assignee = f" → {action['assignee']}" if action.get("assignee") else ""
                    lines.append(f"  [ ] {action.get('text', '')}{assignee}")
                lines.append("")

            if done:
                lines.append("ACCIONES COMPLETADAS:")
                for action in done:
                    lines.append(f"  [x] {action.get('text', '')}")
                lines.append("")

        # Stats
        done_count = sum(1 for a in actions if a.get("done"))
        lines.append("---")
        lines.append(
            f"Totales: {len(notes)} notas, {len(decisions)} decisiones, "
            f"{done_count}/{len(actions)} acciones completadas"
        )

        return "\n".join(lines)

    def _build_markdown(self, meeting: dict[str, Any]) -> str:
        notes = self._load_json_list(meeting.get("notes"))
        decisions = self._load_json_list(meeting.get("decisions"))
        actions = self._load_json_list(meeting.get("action_items"))
        attendees = self._load_json_list(meeting.get("attendees"))

        lines = [
            f"# {meeting['title']}",
            "",
            f"**Fecha:** {meeting['date']}  ",
        ]

        status_label = "Activa" if meeting["status"] == "active" else "Archivada"
        lines.append(f"**Estado:** {status_label}  ")

        if meeting.get("project"):
            lines.append(f"**Proyecto:** {meeting['project']}  ")

        if attendees:
            lines.append(f"**Asistentes:** {', '.join(attendees)}  ")

        lines.append("")

        # Notes
        if notes:
            lines.append("## Notas")
            lines.append("")
            for note in notes:
                ts = note.get("timestamp", "")
                ts_short = ts[11:16] if len(ts) >= 16 else ""
                prefix = f"*{ts_short}* — " if ts_short else ""
                lines.append(f"- {prefix}{note.get('text', '')}")
            lines.append("")

        # Decisions
        if decisions:
            lines.append("## Decisiones")
            lines.append("")
            for i, dec in enumerate(decisions, 1):
                lines.append(f"{i}. {dec}")
            lines.append("")

        # Action items
        if actions:
            lines.append("## Acciones")
            lines.append("")
            for action in actions:
                check = "x" if action.get("done") else " "
                assignee = f" — *@{action['assignee']}*" if action.get("assignee") else ""
                lines.append(f"- [{check}] {action.get('text', '')}{assignee}")
            lines.append("")

        # Footer
        lines.append("---")
        done_count = sum(1 for a in actions if a.get("done"))
        lines.append(
            f"*{len(notes)} notas | {len(decisions)} decisiones | "
            f"{done_count}/{len(actions)} acciones completadas*"
        )
        lines.append(f"*Exportado: {_now_iso()}*")

        return "\n".join(lines)
