"""Cron / Automation skill: schedule recurring commands, reminders, and tasks."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any

import structlog

from src.memory.engine import MemoryEngine
from src.skills.base_skill import BaseSkill, SkillResult

log = structlog.get_logger("assistant.skills.automation")

_AUTOMATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS automations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    action_type TEXT NOT NULL CHECK(action_type IN ('command','message','skill','reminder','backup','check')),
    action_data TEXT NOT NULL,
    schedule TEXT NOT NULL,
    next_run TEXT,
    last_run TEXT,
    last_result TEXT,
    status TEXT DEFAULT 'active' CHECK(status IN ('active','paused','completed','failed')),
    run_count INTEGER DEFAULT 0,
    max_runs INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);
"""

_AUTOMATIONS_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_automations_status ON automations(status);
CREATE INDEX IF NOT EXISTS idx_automations_next_run ON automations(next_run);
"""

_AUTOMATION_HISTORY_TABLE = """
CREATE TABLE IF NOT EXISTS automation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    automation_id INTEGER NOT NULL,
    ran_at TEXT DEFAULT (datetime('now')),
    result TEXT,
    success INTEGER DEFAULT 1,
    duration_secs REAL,
    FOREIGN KEY (automation_id) REFERENCES automations(id) ON DELETE CASCADE
);
"""

_AUTOMATION_HISTORY_INDEX = """
CREATE INDEX IF NOT EXISTS idx_automation_history_aid ON automation_history(automation_id, ran_at);
"""

# ── Spanish day-of-week mapping ──────────────────────────────────────────────

_DAYS_ES: dict[str, int] = {
    "lunes": 0,
    "martes": 1,
    "miercoles": 2,
    "miércoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sabado": 5,
    "sábado": 5,
    "domingo": 6,
}

# ── Schedule regex patterns ──────────────────────────────────────────────────

# "cada 5m", "cada 30s", "cada 2h"
_RE_INTERVAL = re.compile(
    r"^cada\s+(\d+)\s*(s|seg|segundos?|m|min|minutos?|h|horas?|d|dias?|días?)$",
    re.IGNORECASE,
)

# "cada dia 9:00", "cada día 09:30"
_RE_DAILY = re.compile(
    r"^cada\s+d[ií]a\s+(\d{1,2}):(\d{2})$",
    re.IGNORECASE,
)

# "cada lunes 10:00", "cada viernes 15:30"
_RE_WEEKLY = re.compile(
    r"^cada\s+(\w+)\s+(\d{1,2}):(\d{2})$",
    re.IGNORECASE,
)

# "una vez 2026-03-25 14:00"
_RE_ONCE_DATETIME = re.compile(
    r"^una\s+vez\s+(\d{4}-\d{2}-\d{2})\s+(\d{1,2}):(\d{2})$",
    re.IGNORECASE,
)

# "una vez 2026-03-25"
_RE_ONCE_DATE = re.compile(
    r"^una\s+vez\s+(\d{4}-\d{2}-\d{2})$",
    re.IGNORECASE,
)

# ── Reminder-specific "when" patterns ────────────────────────────────────────

# "en 30m", "en 2h", "en 5min", "en 10 minutos"
_RE_IN_DELTA = re.compile(
    r"^en\s+(\d+)\s*(s|seg|segundos?|m|min|minutos?|h|horas?|d|dias?|días?)$",
    re.IGNORECASE,
)

# "mañana 9:00"
_RE_TOMORROW = re.compile(
    r"^ma[ñn]ana\s+(\d{1,2}):(\d{2})$",
    re.IGNORECASE,
)

# "2026-03-25 14:00"
_RE_ABSOLUTE_DT = re.compile(
    r"^(\d{4}-\d{2}-\d{2})\s+(\d{1,2}):(\d{2})$",
)

# "2026-03-25"
_RE_ABSOLUTE_DATE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})$",
)


def _normalize_unit(unit: str) -> str:
    """Normalize Spanish time-unit strings to a single letter."""
    u = unit.lower().rstrip("s")
    if u in ("s", "seg", "segundo"):
        return "s"
    if u in ("m", "min", "minuto"):
        return "m"
    if u in ("h", "hora"):
        return "h"
    if u in ("d", "dia", "día"):
        return "d"
    return u


def _now() -> datetime:
    return datetime.utcnow()


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _parse_schedule(text: str) -> dict[str, Any] | None:
    """Parse a Spanish schedule expression into a JSON-serialisable dict.

    Returns *None* when the expression cannot be understood.

    Possible dict shapes:
        {"type": "interval", "seconds": 300}
        {"type": "daily", "hour": 9, "minute": 0}
        {"type": "weekly", "weekday": 0, "hour": 10, "minute": 0}
        {"type": "once", "at": "2026-03-25 14:00:00"}
    """
    text = text.strip()

    # ── interval ─────────────────────────────────────────────────────────
    m = _RE_INTERVAL.match(text)
    if m:
        amount = int(m.group(1))
        unit = _normalize_unit(m.group(2))
        multiplier = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        secs = amount * multiplier.get(unit, 60)
        return {"type": "interval", "seconds": secs}

    # ── daily ────────────────────────────────────────────────────────────
    m = _RE_DAILY.match(text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return {"type": "daily", "hour": hour, "minute": minute}
        return None

    # ── weekly ───────────────────────────────────────────────────────────
    m = _RE_WEEKLY.match(text)
    if m:
        day_name = m.group(1).lower()
        weekday = _DAYS_ES.get(day_name)
        if weekday is None:
            return None
        hour, minute = int(m.group(2)), int(m.group(3))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return {"type": "weekly", "weekday": weekday, "hour": hour, "minute": minute}
        return None

    # ── once (datetime) ──────────────────────────────────────────────────
    m = _RE_ONCE_DATETIME.match(text)
    if m:
        try:
            dt = datetime.strptime(
                f"{m.group(1)} {int(m.group(2)):02d}:{int(m.group(3)):02d}:00",
                "%Y-%m-%d %H:%M:%S",
            )
            return {"type": "once", "at": _fmt(dt)}
        except ValueError:
            return None

    # ── once (date only, defaults to 09:00) ──────────────────────────────
    m = _RE_ONCE_DATE.match(text)
    if m:
        try:
            dt = datetime.strptime(f"{m.group(1)} 09:00:00", "%Y-%m-%d %H:%M:%S")
            return {"type": "once", "at": _fmt(dt)}
        except ValueError:
            return None

    return None


def _parse_reminder_when(text: str) -> str | None:
    """Parse a Spanish *when* expression for reminders and return an ISO datetime string."""
    text = text.strip()

    # "en 30m"
    m = _RE_IN_DELTA.match(text)
    if m:
        amount = int(m.group(1))
        unit = _normalize_unit(m.group(2))
        multiplier = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        delta = timedelta(seconds=amount * multiplier.get(unit, 60))
        return _fmt(_now() + delta)

    # "mañana 9:00"
    m = _RE_TOMORROW.match(text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            tomorrow = _now().date() + timedelta(days=1)
            return _fmt(datetime(tomorrow.year, tomorrow.month, tomorrow.day, hour, minute))
        return None

    # "2026-03-25 14:00"
    m = _RE_ABSOLUTE_DT.match(text)
    if m:
        try:
            dt = datetime.strptime(
                f"{m.group(1)} {int(m.group(2)):02d}:{int(m.group(3)):02d}:00",
                "%Y-%m-%d %H:%M:%S",
            )
            return _fmt(dt)
        except ValueError:
            return None

    # "2026-03-25"
    m = _RE_ABSOLUTE_DATE.match(text)
    if m:
        try:
            dt = datetime.strptime(f"{m.group(1)} 09:00:00", "%Y-%m-%d %H:%M:%S")
            return _fmt(dt)
        except ValueError:
            return None

    return None


def _compute_next_run(schedule: dict[str, Any], after: datetime | None = None) -> str:
    """Compute the next run time from a parsed schedule dict."""
    now = after or _now()

    stype = schedule["type"]

    if stype == "interval":
        return _fmt(now + timedelta(seconds=schedule["seconds"]))

    if stype == "daily":
        candidate = now.replace(
            hour=schedule["hour"],
            minute=schedule["minute"],
            second=0,
            microsecond=0,
        )
        if candidate <= now:
            candidate += timedelta(days=1)
        return _fmt(candidate)

    if stype == "weekly":
        target_wd = schedule["weekday"]
        days_ahead = (target_wd - now.weekday()) % 7
        candidate = (now + timedelta(days=days_ahead)).replace(
            hour=schedule["hour"],
            minute=schedule["minute"],
            second=0,
            microsecond=0,
        )
        if candidate <= now:
            candidate += timedelta(weeks=1)
        return _fmt(candidate)

    if stype == "once":
        return schedule["at"]

    # Fallback
    return _fmt(now + timedelta(hours=1))


def _human_schedule(schedule: dict[str, Any]) -> str:
    """Return a human-readable description of a schedule."""
    stype = schedule["type"]

    if stype == "interval":
        secs = schedule["seconds"]
        if secs < 60:
            return f"cada {secs}s"
        if secs < 3600:
            return f"cada {secs // 60}min"
        if secs < 86400:
            return f"cada {secs // 3600}h"
        return f"cada {secs // 86400}d"

    if stype == "daily":
        return f"cada dia {schedule['hour']:02d}:{schedule['minute']:02d}"

    if stype == "weekly":
        day_names = {v: k for k, v in _DAYS_ES.items() if k.isascii()}
        day = day_names.get(schedule["weekday"], f"dia {schedule['weekday']}")
        return f"cada {day} {schedule['hour']:02d}:{schedule['minute']:02d}"

    if stype == "once":
        return f"una vez: {schedule['at']}"

    return json.dumps(schedule)


class AutomationSkill(BaseSkill):
    """Manage scheduled automations, cron jobs, and reminders."""

    def __init__(self, memory_engine: MemoryEngine | None = None) -> None:
        self._memory = memory_engine
        self._table_ready = False

    # ── BaseSkill interface ──────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "automation"

    @property
    def description(self) -> str:
        return "Automatizaciones y recordatorios programados (cron, reminders)"

    @property
    def natural_patterns(self) -> dict[str, list[str]]:
        return {
            "recordar": [
                r"recu[eé]rdame\s+(?P<args>.+)",
                r"(?:ponme|pon)\s+(?:un\s+)?recordatorio\s+(?:de\s+|para\s+)?(?P<args>.+)",
                r"(?:que\s+)?no\s+se\s+me\s+olvide\s+(?P<args>.+)",
                r"av[ií]same\s+(?:cuando|que|para)\s+(?P<args>.+)",
            ],
            "nuevo": [
                r"(?:automatiza|agenda)\s+(?:que\s+)?(?P<args>.+)",
                r"(?:programa|crea|hazme)\s+(?:una?\s+)?(?:automatizaci[oó]n|cron)(?:\s+(?:de|para|que)\s+(?P<args>.+))?",
                r"cada\s+(?:d[ií]a|lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo|hora|\d+\s*(?:min|hora|h|m))\s+(?P<args>.+)",
            ],
            "ver": [
                r"(?:mu[eé]strame|ver|dame|cu[aá]les?)\s+(?:las?\s+|mis?\s+)?automatizaciones?",
                r"(?:qu[eé]|cu[aá]les?)\s+(?:tengo|hay)\s+programado",
                r"(?:mis?\s+)?(?:crons?|automatizaciones?)",
            ],
            "pendientes": [
                r"(?:qu[eé]|cu[aá]les?)\s+(?:recordatorios?|automaciones?)\s+(?:tengo\s+)?pendientes?",
            ],
        }

    @property
    def triggers(self) -> list[str]:
        return [
            "!auto",
            "!automation",
            "!cron",
            "!programar",
            "!automatizar",
            "!recordar",
            "!reminder",
        ]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        memory = self._memory or context.get("memory")
        if memory is None:
            return SkillResult(success=False, message="Motor de memoria no disponible.")

        self._ensure_table(memory)

        if not args:
            return self._list_active(memory)

        parts = args.split(maxsplit=1)
        sub = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""

        dispatch: dict[str, str] = {
            "nuevo": "create",
            "nueva": "create",
            "new": "create",
            "crear": "create",
            "create": "create",
            "recordar": "reminder",
            "reminder": "reminder",
            "ver": "list",
            "list": "list",
            "listar": "list",
            "pausar": "pause",
            "pause": "pause",
            "reanudar": "resume",
            "resume": "resume",
            "eliminar": "delete",
            "delete": "delete",
            "borrar": "delete",
            "historial": "history",
            "history": "history",
            "ejecutar": "run",
            "run": "run",
            "pendientes": "pending",
            "pending": "pending",
        }

        action = dispatch.get(sub)

        if action == "create":
            return self._create(memory, rest)
        if action == "reminder":
            return self._create_reminder(memory, rest)
        if action == "list":
            return self._list_active(memory)
        if action == "pause":
            return self._pause(memory, rest)
        if action == "resume":
            return self._resume(memory, rest)
        if action == "delete":
            return self._delete(memory, rest)
        if action == "history":
            return self._history(memory, rest)
        if action == "run":
            return self._manual_run(memory, rest)
        if action == "pending":
            return self._pending(memory)

        # If the trigger was !recordar, treat the whole args as a reminder
        text_lower = context.get("raw_text", "").lower().strip()
        if text_lower.startswith("!recordar") or text_lower.startswith("!reminder"):
            return self._create_reminder(memory, args)

        # Unknown subcommand → show help
        return self._help()

    # ── Table initialisation ─────────────────────────────────────────────

    def _ensure_table(self, memory: MemoryEngine) -> None:
        if self._table_ready:
            return
        try:
            memory.execute(_AUTOMATIONS_TABLE)
            for stmt in _AUTOMATIONS_INDEXES.strip().splitlines():
                stmt = stmt.strip()
                if stmt:
                    memory.execute(stmt)
            memory.execute(_AUTOMATION_HISTORY_TABLE)
            for stmt in _AUTOMATION_HISTORY_INDEX.strip().splitlines():
                stmt = stmt.strip()
                if stmt:
                    memory.execute(stmt)
            self._table_ready = True
            log.debug("automation.table_ready")
        except Exception as exc:
            log.error("automation.table_create_failed", error=str(exc))

    # ── Subcommands ──────────────────────────────────────────────────────

    def _create(self, memory: MemoryEngine, rest: str) -> SkillResult:
        """Create a new automation.  Format: <name> | <action> | <schedule>"""
        parts = [p.strip() for p in rest.split("|")]
        if len(parts) < 3:
            return SkillResult(
                success=False,
                message=(
                    "Formato: !auto nuevo <nombre> | <accion> | <schedule>\n"
                    "Ejemplo: !auto nuevo backup-db | command: pg_dump mydb > /tmp/db.sql | cada dia 3:00"
                ),
            )

        name = parts[0]
        raw_action = parts[1]
        raw_schedule = parts[2]

        # Parse action_type:action_data from raw_action
        action_type, action_data = self._parse_action(raw_action)

        # Parse schedule
        schedule = _parse_schedule(raw_schedule)
        if schedule is None:
            return SkillResult(
                success=False,
                message=(
                    f"No entiendo el schedule: '{raw_schedule}'\n"
                    "Formatos validos:\n"
                    "  cada 5m / cada 1h / cada 2d\n"
                    "  cada dia 9:00\n"
                    "  cada lunes 10:00\n"
                    "  una vez 2026-03-25 14:00"
                ),
            )

        next_run = _compute_next_run(schedule)
        schedule_json = json.dumps(schedule, ensure_ascii=False)

        max_runs: int | None = None
        if schedule["type"] == "once":
            max_runs = 1

        auto_id = memory.insert_returning_id(
            """
            INSERT INTO automations (name, action_type, action_data, schedule, next_run, max_runs)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, action_type, action_data, schedule_json, next_run, max_runs),
        )

        log.info(
            "automation.created",
            id=auto_id,
            name=name,
            action_type=action_type,
            schedule=schedule,
        )

        return SkillResult(
            success=True,
            message=(
                f"Automatizacion #{auto_id} creada: {name}\n"
                f"  Tipo: {action_type}\n"
                f"  Accion: {action_data}\n"
                f"  Horario: {_human_schedule(schedule)}\n"
                f"  Proxima ejecucion: {next_run}"
            ),
            data={"id": auto_id, "schedule": schedule},
        )

    def _create_reminder(self, memory: MemoryEngine, rest: str) -> SkillResult:
        """Create a reminder.  Format: <message> | <when>"""
        parts = [p.strip() for p in rest.split("|")]
        if len(parts) < 2:
            return SkillResult(
                success=False,
                message=(
                    "Formato: !recordar <mensaje> | <cuando>\n"
                    "Ejemplos:\n"
                    "  !recordar Revisar PR | en 30m\n"
                    "  !recordar Llamar al doctor | mañana 9:00\n"
                    "  !recordar Reunion | 2026-03-25 14:00"
                ),
            )

        message = parts[0]
        when_text = parts[1]

        next_run = _parse_reminder_when(when_text)
        if next_run is None:
            return SkillResult(
                success=False,
                message=(
                    f"No entiendo cuando: '{when_text}'\n"
                    "Formatos validos:\n"
                    "  en 30m / en 2h / en 1d\n"
                    "  mañana 9:00\n"
                    "  2026-03-25 14:00"
                ),
            )

        schedule = {"type": "once", "at": next_run}
        schedule_json = json.dumps(schedule, ensure_ascii=False)

        auto_id = memory.insert_returning_id(
            """
            INSERT INTO automations (name, action_type, action_data, schedule, next_run, max_runs)
            VALUES (?, 'reminder', ?, ?, ?, 1)
            """,
            (f"Recordatorio: {message[:60]}", message, schedule_json, next_run),
        )

        log.info("automation.reminder_created", id=auto_id, message=message[:60], at=next_run)

        return SkillResult(
            success=True,
            message=(
                f"Recordatorio #{auto_id} programado\n"
                f"  Mensaje: {message}\n"
                f"  Cuando: {next_run}"
            ),
            data={"id": auto_id, "next_run": next_run},
        )

    def _list_active(self, memory: MemoryEngine) -> SkillResult:
        rows = memory.fetchall_dicts(
            """
            SELECT id, name, action_type, schedule, next_run, run_count, status
            FROM automations
            WHERE status IN ('active', 'paused')
            ORDER BY
                CASE status WHEN 'active' THEN 0 ELSE 1 END,
                next_run ASC
            LIMIT 30
            """,
        )

        if not rows:
            return SkillResult(success=True, message="No hay automatizaciones registradas.")

        lines = ["Automatizaciones:", ""]
        for row in rows:
            status_icon = "[ON]" if row["status"] == "active" else "[||]"
            schedule = self._safe_parse_schedule(row["schedule"])
            sched_str = _human_schedule(schedule) if schedule else row["schedule"]
            next_run = row["next_run"] or "—"
            lines.append(
                f"  {status_icon} #{row['id']}: {row['name'][:50]}\n"
                f"        {row['action_type']} | {sched_str} | prox: {next_run} | runs: {row['run_count']}"
            )

        return SkillResult(success=True, message="\n".join(lines), data={"automations": rows})

    def _pause(self, memory: MemoryEngine, args: str) -> SkillResult:
        auto_id = self._parse_id(args)
        if auto_id is None:
            return SkillResult(success=False, message="Uso: !auto pausar <id>")

        row = memory.fetchone(
            "SELECT name, status FROM automations WHERE id = ?", (auto_id,)
        )
        if row is None:
            return SkillResult(success=False, message=f"Automatizacion #{auto_id} no encontrada.")
        if row[1] == "paused":
            return SkillResult(success=True, message=f"#{auto_id} ya estaba pausada.")

        memory.execute(
            "UPDATE automations SET status = 'paused' WHERE id = ?", (auto_id,)
        )
        log.info("automation.paused", id=auto_id)
        return SkillResult(success=True, message=f"Automatizacion #{auto_id} pausada: {row[0]}")

    def _resume(self, memory: MemoryEngine, args: str) -> SkillResult:
        auto_id = self._parse_id(args)
        if auto_id is None:
            return SkillResult(success=False, message="Uso: !auto reanudar <id>")

        row = memory.fetchone(
            "SELECT name, status, schedule FROM automations WHERE id = ?", (auto_id,)
        )
        if row is None:
            return SkillResult(success=False, message=f"Automatizacion #{auto_id} no encontrada.")
        if row[1] == "active":
            return SkillResult(success=True, message=f"#{auto_id} ya estaba activa.")

        # Recalculate next_run
        schedule = self._safe_parse_schedule(row[2])
        next_run = _compute_next_run(schedule) if schedule else _fmt(_now() + timedelta(hours=1))

        memory.execute(
            "UPDATE automations SET status = 'active', next_run = ? WHERE id = ?",
            (next_run, auto_id),
        )
        log.info("automation.resumed", id=auto_id, next_run=next_run)
        return SkillResult(
            success=True,
            message=f"Automatizacion #{auto_id} reanudada: {row[0]}\n  Proxima ejecucion: {next_run}",
        )

    def _delete(self, memory: MemoryEngine, args: str) -> SkillResult:
        auto_id = self._parse_id(args)
        if auto_id is None:
            return SkillResult(success=False, message="Uso: !auto eliminar <id>")

        row = memory.fetchone("SELECT name FROM automations WHERE id = ?", (auto_id,))
        if row is None:
            return SkillResult(success=False, message=f"Automatizacion #{auto_id} no encontrada.")

        memory.execute("DELETE FROM automation_history WHERE automation_id = ?", (auto_id,))
        memory.execute("DELETE FROM automations WHERE id = ?", (auto_id,))
        log.info("automation.deleted", id=auto_id)
        return SkillResult(success=True, message=f"Automatizacion #{auto_id} eliminada: {row[0]}")

    def _history(self, memory: MemoryEngine, args: str) -> SkillResult:
        auto_id = self._parse_id(args)
        if auto_id is None:
            return SkillResult(success=False, message="Uso: !auto historial <id>")

        row = memory.fetchone("SELECT name FROM automations WHERE id = ?", (auto_id,))
        if row is None:
            return SkillResult(success=False, message=f"Automatizacion #{auto_id} no encontrada.")

        history = memory.fetchall_dicts(
            """
            SELECT ran_at, result, success, duration_secs
            FROM automation_history
            WHERE automation_id = ?
            ORDER BY ran_at DESC
            LIMIT 20
            """,
            (auto_id,),
        )

        if not history:
            return SkillResult(
                success=True,
                message=f"Automatizacion #{auto_id} ({row[0]}): sin historial de ejecuciones.",
            )

        lines = [f"Historial de #{auto_id} ({row[0]}):", ""]
        for h in history:
            ok = "OK" if h["success"] else "FAIL"
            dur = f"{h['duration_secs']:.1f}s" if h["duration_secs"] is not None else "—"
            result_preview = (h["result"] or "")[:80]
            lines.append(f"  [{ok}] {h['ran_at']} ({dur}) {result_preview}")

        return SkillResult(success=True, message="\n".join(lines), data={"history": history})

    def _manual_run(self, memory: MemoryEngine, args: str) -> SkillResult:
        auto_id = self._parse_id(args)
        if auto_id is None:
            return SkillResult(success=False, message="Uso: !auto ejecutar <id>")

        row = memory.fetchone(
            "SELECT name, action_type, action_data, schedule, status, run_count, max_runs "
            "FROM automations WHERE id = ?",
            (auto_id,),
        )
        if row is None:
            return SkillResult(success=False, message=f"Automatizacion #{auto_id} no encontrada.")

        name, action_type, action_data, schedule_raw, status, run_count, max_runs = row

        # Record the execution intent
        now = _fmt(_now())
        memory.execute(
            """
            INSERT INTO automation_history (automation_id, ran_at, result, success)
            VALUES (?, ?, 'Ejecucion manual solicitada', 1)
            """,
            (auto_id, now),
        )

        new_count = run_count + 1

        # Calculate next run
        schedule = self._safe_parse_schedule(schedule_raw)
        if schedule and schedule["type"] != "once":
            next_run = _compute_next_run(schedule)
        else:
            next_run = None

        # Check if completed (max_runs reached)
        new_status = status
        if max_runs is not None and new_count >= max_runs:
            new_status = "completed"
            next_run = None

        memory.execute(
            """
            UPDATE automations
            SET last_run = ?, last_result = 'Ejecucion manual', run_count = ?,
                next_run = ?, status = ?
            WHERE id = ?
            """,
            (now, new_count, next_run, new_status, auto_id),
        )

        log.info("automation.manual_run", id=auto_id, name=name)

        msg_lines = [
            f"Automatizacion #{auto_id} ejecutada manualmente: {name}",
            f"  Tipo: {action_type}",
            f"  Accion: {action_data}",
            f"  Ejecuciones: {new_count}",
        ]
        if new_status == "completed":
            msg_lines.append("  Estado: COMPLETADA (max ejecuciones alcanzado)")
        elif next_run:
            msg_lines.append(f"  Proxima ejecucion: {next_run}")

        return SkillResult(
            success=True,
            message="\n".join(msg_lines),
            data={
                "id": auto_id,
                "action_type": action_type,
                "action_data": action_data,
                "executed": True,
            },
        )

    def _pending(self, memory: MemoryEngine) -> SkillResult:
        """Show automations due within the next hour."""
        one_hour = _fmt(_now() + timedelta(hours=1))
        now = _fmt(_now())

        rows = memory.fetchall_dicts(
            """
            SELECT id, name, action_type, action_data, next_run, schedule
            FROM automations
            WHERE status = 'active' AND next_run IS NOT NULL AND next_run <= ?
            ORDER BY next_run ASC
            LIMIT 20
            """,
            (one_hour,),
        )

        if not rows:
            return SkillResult(
                success=True,
                message="No hay automatizaciones pendientes en la proxima hora.",
            )

        lines = [f"Pendientes (ahora: {now}):", ""]
        for row in rows:
            overdue = row["next_run"] <= now
            flag = " [VENCIDA]" if overdue else ""
            lines.append(
                f"  #{row['id']}: {row['name'][:50]}{flag}\n"
                f"        {row['action_type']}: {row['action_data'][:60]}\n"
                f"        Programada: {row['next_run']}"
            )

        return SkillResult(success=True, message="\n".join(lines), data={"pending": rows})

    def _help(self) -> SkillResult:
        return SkillResult(
            success=True,
            message=(
                "Uso de automatizaciones:\n"
                "  !auto ver                — listar automatizaciones activas\n"
                "  !auto nuevo <nombre> | <accion> | <horario>\n"
                "  !auto pendientes         — ver proximas ejecuciones (1h)\n"
                "  !auto pausar <id>        — pausar automatizacion\n"
                "  !auto reanudar <id>      — reanudar automatizacion\n"
                "  !auto eliminar <id>      — eliminar automatizacion\n"
                "  !auto historial <id>     — ver historial de ejecuciones\n"
                "  !auto ejecutar <id>      — ejecutar manualmente\n"
                "  !recordar <msg> | <cuando> — crear recordatorio\n"
                "\n"
                "Formatos de horario:\n"
                "  cada 5m / cada 1h / cada 2d\n"
                "  cada dia 9:00\n"
                "  cada lunes 10:00\n"
                "  una vez 2026-03-25 14:00\n"
                "\n"
                "Formatos de recordatorio:\n"
                "  en 30m / en 2h\n"
                "  mañana 9:00\n"
                "  2026-03-25 14:00"
            ),
        )

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _parse_id(text: str) -> int | None:
        text = text.strip().lstrip("#")
        try:
            return int(text)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_action(raw: str) -> tuple[str, str]:
        """Extract action_type and action_data from a raw action string.

        Supports formats:
            "command: pg_dump mydb" → ("command", "pg_dump mydb")
            "skill: !tareas ver"   → ("skill", "!tareas ver")
            "message: Hola"        → ("message", "Hola")
            "backup: /data"        → ("backup", "/data")
            "check: ping 8.8.8.8" → ("check", "ping 8.8.8.8")
            "pg_dump mydb"         → ("command", "pg_dump mydb")
        """
        valid_types = {"command", "message", "skill", "reminder", "backup", "check"}
        if ":" in raw:
            prefix, _, rest = raw.partition(":")
            prefix_clean = prefix.strip().lower()
            if prefix_clean in valid_types:
                return prefix_clean, rest.strip()
        # Default to command
        return "command", raw.strip()

    @staticmethod
    def _safe_parse_schedule(raw: str | None) -> dict[str, Any] | None:
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
