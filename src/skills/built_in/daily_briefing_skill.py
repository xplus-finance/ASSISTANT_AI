"""Daily briefing skill: compiles weather, tasks, conversations, and system status."""

from __future__ import annotations

import asyncio
import os
import shutil
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

from src.memory.engine import MemoryEngine
from src.skills.base_skill import BaseSkill, SkillResult

log = structlog.get_logger("assistant.skills.daily_briefing")

_WEATHER_URL = "https://wttr.in/Cape+Coral,FL?format=%C+%t+%h+%w&lang=es"
_WEATHER_FULL_URL = "https://wttr.in/Cape+Coral,FL?format=3&lang=es"
_WEATHER_TIMEOUT = 8


class DailyBriefingSkill(BaseSkill):
    """Generates a comprehensive daily briefing with weather, tasks, and system info."""

    def __init__(self, memory_engine: MemoryEngine | None = None) -> None:
        self._memory = memory_engine

    @property
    def name(self) -> str:
        return "daily_briefing"

    @property
    def description(self) -> str:
        return "Resumen diario: clima, tareas pendientes, actividad reciente, estado del sistema"

    @property
    def natural_patterns(self) -> dict[str, list[str]]:
        return {
            "briefing": [
                r"(?:dame|quiero|hazme|mu[eé]strame|genera)\s+(?:el\s+)?(?:resumen|briefing)(?:\s+del\s+d[ií]a)?",
                r"(?:dame|quiero)\s+(?:mi\s+)?briefing",
                r"(?:ponte|ponme)\s+al\s+d[ií]a",
            ],
        }

    @property
    def triggers(self) -> list[str]:
        return [
            "!briefing",
            "!resumen",
            "!buenos dias",
            "!good morning",
        ]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        memory = self._memory or context.get("memory")
        sections: list[str] = []

        now = datetime.now()
        utc_now = datetime.now(timezone.utc)

        # --- Header ---
        greeting = _time_greeting(now)
        sections.append(
            f"{greeting}\n"
            f"\U0001F4C5 {now.strftime('%A, %d de %B de %Y')}\n"
            f"\U0001F552 {now.strftime('%H:%M')} (local) — "
            f"{utc_now.strftime('%H:%M')} UTC"
        )

        # --- Weather ---
        weather = await self._fetch_weather()
        sections.append(weather)

        # --- Pending tasks ---
        tasks_section = self._build_tasks_section(memory)
        sections.append(tasks_section)

        # --- Scheduled / upcoming tasks ---
        scheduled_section = self._build_scheduled_section(memory)
        if scheduled_section:
            sections.append(scheduled_section)

        # --- Recent activity ---
        activity_section = self._build_activity_section(memory)
        sections.append(activity_section)

        # --- System status ---
        system_section = await self._build_system_section()
        sections.append(system_section)

        full_message = "\n\n".join(s for s in sections if s)
        log.info("daily_briefing.generated", length=len(full_message))
        return SkillResult(success=True, message=full_message)

    # ------------------------------------------------------------------
    # Weather
    # ------------------------------------------------------------------

    async def _fetch_weather(self) -> str:
        header = "\U0001F324\uFE0F **Clima — Cape Coral, FL**"
        try:
            weather_line = await asyncio.to_thread(self._http_get, _WEATHER_URL)
            weather_full = await asyncio.to_thread(self._http_get, _WEATHER_FULL_URL)
            lines = [header]
            if weather_line:
                lines.append(f"  {weather_line.strip()}")
            if weather_full:
                lines.append(f"  {weather_full.strip()}")
            return "\n".join(lines) if len(lines) > 1 else f"{header}\n  Datos no disponibles"
        except Exception as exc:
            log.warning("daily_briefing.weather_failed", error=str(exc))
            return f"{header}\n  \u26A0\uFE0F No se pudo obtener el clima: {exc}"

    @staticmethod
    def _http_get(url: str) -> str | None:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "curl/7.88.0", "Accept": "text/plain"},
        )
        try:
            with urllib.request.urlopen(req, timeout=_WEATHER_TIMEOUT) as resp:
                return resp.read().decode("utf-8", errors="replace").strip()
        except (urllib.error.URLError, OSError, TimeoutError):
            return None

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    def _build_tasks_section(self, memory: MemoryEngine | None) -> str:
        header = "\U0001F4CB **Tareas pendientes**"
        if memory is None:
            return f"{header}\n  (memoria no disponible)"

        try:
            rows = memory.fetchall_dicts(
                """
                SELECT id, title, status, project, created_at
                FROM tasks
                WHERE status IN ('pending', 'in_progress', 'recurring')
                ORDER BY
                    CASE status
                        WHEN 'in_progress' THEN 0
                        WHEN 'recurring' THEN 1
                        WHEN 'pending' THEN 2
                    END,
                    created_at DESC
                LIMIT 15
                """,
            )
        except Exception as exc:
            log.warning("daily_briefing.tasks_query_failed", error=str(exc))
            return f"{header}\n  \u26A0\uFE0F Error consultando tareas: {exc}"

        if not rows:
            return f"{header}\n  \u2705 No hay tareas pendientes. \u00A1Dia libre!"

        icons = {
            "pending": "\U0001F7E1",
            "in_progress": "\U0001F535",
            "recurring": "\U0001F504",
        }

        lines = [header]
        for row in rows:
            icon = icons.get(row["status"], "\u2753")
            project_tag = f" [{row['project']}]" if row.get("project") else ""
            lines.append(f"  {icon} #{row['id']}: {row['title'][:70]}{project_tag}")

        total = self._count_pending_tasks(memory)
        if total is not None and total > len(rows):
            lines.append(f"  ... y {total - len(rows)} mas")

        return "\n".join(lines)

    def _count_pending_tasks(self, memory: MemoryEngine) -> int | None:
        try:
            row = memory.fetchone(
                "SELECT COUNT(*) FROM tasks WHERE status IN ('pending', 'in_progress', 'recurring')",
            )
            return row[0] if row else None
        except Exception:
            return None

    def _build_scheduled_section(self, memory: MemoryEngine | None) -> str:
        if memory is None:
            return ""

        try:
            rows = memory.fetchall_dicts(
                """
                SELECT id, title, next_run, recurrence_pattern
                FROM tasks
                WHERE next_run IS NOT NULL
                  AND status IN ('pending', 'recurring', 'in_progress')
                ORDER BY next_run ASC
                LIMIT 10
                """,
            )
        except Exception as exc:
            log.warning("daily_briefing.scheduled_query_failed", error=str(exc))
            return ""

        if not rows:
            return ""

        lines = ["\u23F0 **Tareas programadas**"]
        for row in rows:
            recurrence = f" ({row['recurrence_pattern']})" if row.get("recurrence_pattern") else ""
            lines.append(
                f"  \U0001F4C6 #{row['id']}: {row['title'][:60]} — {row['next_run']}{recurrence}"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Recent activity
    # ------------------------------------------------------------------

    def _build_activity_section(self, memory: MemoryEngine | None) -> str:
        header = "\U0001F4AC **Actividad reciente (24h)**"
        if memory is None:
            return f"{header}\n  (memoria no disponible)"

        try:
            since = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")

            conv_row = memory.fetchone(
                "SELECT COUNT(*) FROM conversations WHERE timestamp >= ?",
                (since,),
            )
            conv_count = conv_row[0] if conv_row else 0

            user_row = memory.fetchone(
                "SELECT COUNT(*) FROM conversations WHERE timestamp >= ? AND role = 'user'",
                (since,),
            )
            user_count = user_row[0] if user_row else 0

            exec_row = memory.fetchone(
                "SELECT COUNT(*) FROM execution_log WHERE timestamp >= ?",
                (since,),
            )
            exec_count = exec_row[0] if exec_row else 0

            exec_ok = memory.fetchone(
                "SELECT COUNT(*) FROM execution_log WHERE timestamp >= ? AND success = 1",
                (since,),
            )
            exec_success = exec_ok[0] if exec_ok else 0

            lines = [header]
            lines.append(f"  \U0001F4E8 Mensajes: {conv_count} total ({user_count} del usuario)")
            lines.append(
                f"  \u2699\uFE0F Ejecuciones: {exec_count} "
                f"({exec_success} exitosas, {exec_count - exec_success} fallidas)"
            )

            # Last conversation topic
            last_msg = memory.fetchone(
                """
                SELECT message FROM conversations
                WHERE role = 'user' AND timestamp >= ?
                ORDER BY timestamp DESC LIMIT 1
                """,
                (since,),
            )
            if last_msg and last_msg[0]:
                preview = last_msg[0][:80].replace("\n", " ")
                lines.append(f"  \U0001F4DD Ultimo mensaje: \"{preview}...\"" if len(last_msg[0]) > 80 else f"  \U0001F4DD Ultimo mensaje: \"{preview}\"")

            return "\n".join(lines)

        except Exception as exc:
            log.warning("daily_briefing.activity_query_failed", error=str(exc))
            return f"{header}\n  \u26A0\uFE0F Error consultando actividad: {exc}"

    # ------------------------------------------------------------------
    # System status
    # ------------------------------------------------------------------

    async def _build_system_section(self) -> str:
        header = "\U0001F5A5\uFE0F **Estado del sistema**"
        lines = [header]

        try:
            import psutil

            cpu = await asyncio.to_thread(psutil.cpu_percent, interval=1)
            mem = psutil.virtual_memory()
            disk = shutil.disk_usage("/")
            boot = psutil.boot_time()

            import time
            uptime_s = int(time.time() - boot)
            h, remainder = divmod(uptime_s, 3600)
            m, _ = divmod(remainder, 60)

            cpu_bar = _progress_bar(cpu)
            mem_bar = _progress_bar(mem.percent)
            disk_pct = disk.used * 100 / disk.total if disk.total else 0
            disk_bar = _progress_bar(disk_pct)

            lines.append(f"  CPU:   {cpu_bar} {cpu:.0f}% ({os.cpu_count()} cores)")
            lines.append(
                f"  RAM:   {mem_bar} {mem.percent}% "
                f"({mem.used / (1024**3):.1f}/{mem.total / (1024**3):.1f} GB)"
            )
            lines.append(
                f"  Disco: {disk_bar} {disk_pct:.0f}% "
                f"({disk.used / (1024**3):.1f}/{disk.total / (1024**3):.1f} GB)"
            )
            lines.append(f"  Uptime: {h}h {m}m")

            # Load average on Linux/Mac
            if hasattr(os, "getloadavg"):
                load = os.getloadavg()
                lines.append(f"  Load: {load[0]:.2f} / {load[1]:.2f} / {load[2]:.2f}")

        except ImportError:
            log.info("daily_briefing.psutil_not_available")
            lines.append(await self._fallback_system_info())
        except Exception as exc:
            log.warning("daily_briefing.system_info_failed", error=str(exc))
            lines.append(f"  \u26A0\uFE0F Error obteniendo info del sistema: {exc}")

        return "\n".join(lines)

    async def _fallback_system_info(self) -> str:
        """Gather basic system info without psutil."""
        parts: list[str] = []

        # Disk via shutil
        try:
            disk = shutil.disk_usage("/")
            disk_pct = disk.used * 100 / disk.total if disk.total else 0
            parts.append(
                f"  Disco: {disk_pct:.0f}% "
                f"({disk.used / (1024**3):.1f}/{disk.total / (1024**3):.1f} GB)"
            )
        except Exception:
            parts.append("  Disco: no disponible")

        parts.append(f"  CPU cores: {os.cpu_count()}")

        # Load average
        if hasattr(os, "getloadavg"):
            try:
                load = os.getloadavg()
                parts.append(f"  Load: {load[0]:.2f} / {load[1]:.2f} / {load[2]:.2f}")
            except OSError:
                pass

        # Uptime from /proc
        try:
            proc_uptime = await asyncio.to_thread(_read_proc_uptime)
            if proc_uptime is not None:
                h, remainder = divmod(int(proc_uptime), 3600)
                m, _ = divmod(remainder, 60)
                parts.append(f"  Uptime: {h}h {m}m")
        except Exception:
            pass

        return "\n".join(parts) if parts else "  Info basica no disponible"


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _time_greeting(now: datetime) -> str:
    hour = now.hour
    if hour < 6:
        return "\U0001F303 **Briefing nocturno**"
    elif hour < 12:
        return "\U0001F305 **Buenos dias — Briefing matutino**"
    elif hour < 18:
        return "\u2600\uFE0F **Buenas tardes — Briefing vespertino**"
    else:
        return "\U0001F306 **Buenas noches — Briefing nocturno**"


def _progress_bar(pct: float, width: int = 10) -> str:
    filled = int(round(pct / 100 * width))
    filled = max(0, min(width, filled))
    empty = width - filled
    return f"[{'█' * filled}{'░' * empty}]"


def _read_proc_uptime() -> float | None:
    try:
        with open("/proc/uptime") as f:
            return float(f.read().split()[0])
    except (FileNotFoundError, ValueError, IndexError):
        return None
