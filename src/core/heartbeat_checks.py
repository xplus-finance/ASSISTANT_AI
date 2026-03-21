"""Modular proactive checks for HeartbeatPro."""

from __future__ import annotations

import asyncio
import ssl
import time
from datetime import datetime
from typing import Any

import structlog

from src.core.heartbeat import HeartbeatCheck, Priority

log = structlog.get_logger("assistant.core.heartbeat_checks")


# ---------------------------------------------------------------
# 1. Overdue Tasks Check
# ---------------------------------------------------------------

def create_overdue_tasks_check(tasks_manager: Any) -> HeartbeatCheck:
    """Check for overdue/due tasks and notify with priority."""

    async def _check() -> list[dict[str, Any]] | None:
        try:
            due = tasks_manager.get_due_tasks()
            if not due:
                return None

            alerts = []
            for task in due[:10]:
                title = task.get("title", "?")
                next_run = task.get("next_run", "")
                alerts.append({
                    "message": f"Tarea pendiente: {title}",
                    "details": f"Programada: {next_run}" if next_run else "",
                    "priority": Priority.HIGH,
                    "task_id": task.get("id"),
                })

            return alerts if alerts else None
        except Exception:
            return None

    return HeartbeatCheck(
        name="Tareas pendientes",
        check_fn=_check,
        interval_minutes=30,
        default_priority=Priority.HIGH,
        category="tasks",
    )


# ---------------------------------------------------------------
# 2. System Health Check
# ---------------------------------------------------------------

def create_system_health_check(config: dict[str, Any] | None = None) -> HeartbeatCheck:
    """Check system health: disk, RAM, CPU with configurable thresholds."""

    thresholds = (config or {}).get("checks", {}).get("system_health", {}).get("thresholds", {})
    disk_warn = thresholds.get("disk_percent_warning", 85)
    disk_crit = thresholds.get("disk_percent_critical", 95)
    ram_warn = thresholds.get("ram_percent_warning", 85)
    ram_crit = thresholds.get("ram_percent_critical", 95)
    cpu_warn = thresholds.get("cpu_percent_warning", 90)
    interval = (config or {}).get("checks", {}).get("system_health", {}).get("interval_minutes", 60)

    async def _check() -> list[dict[str, Any]] | None:
        import shutil

        alerts: list[dict[str, Any]] = []

        # Disk space
        try:
            usage = shutil.disk_usage("/")
            pct_used = ((usage.total - usage.free) / usage.total) * 100
            free_gb = usage.free / (1024 ** 3)

            if pct_used >= disk_crit:
                alerts.append({
                    "message": f"Disco CRÍTICO al {pct_used:.0f}% — solo {free_gb:.1f} GB libres",
                    "priority": Priority.CRITICAL,
                })
            elif pct_used >= disk_warn:
                alerts.append({
                    "message": f"Disco al {pct_used:.0f}% — {free_gb:.1f} GB libres",
                    "priority": Priority.HIGH,
                })
        except Exception:
            pass

        # Memory
        try:
            import psutil
            mem = psutil.virtual_memory()
            if mem.percent >= ram_crit:
                alerts.append({
                    "message": f"RAM CRÍTICA al {mem.percent:.0f}% — {mem.available / (1024**3):.1f} GB disponibles",
                    "priority": Priority.CRITICAL,
                })
            elif mem.percent >= ram_warn:
                alerts.append({
                    "message": f"RAM al {mem.percent:.0f}% — {mem.available / (1024**3):.1f} GB disponibles",
                    "priority": Priority.HIGH,
                })
        except ImportError:
            pass

        # CPU
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=1)
            if cpu >= cpu_warn:
                alerts.append({
                    "message": f"CPU al {cpu:.0f}%",
                    "priority": Priority.HIGH,
                })
        except ImportError:
            pass

        return alerts if alerts else None

    return HeartbeatCheck(
        name="Estado del sistema",
        check_fn=_check,
        interval_minutes=interval,
        default_priority=Priority.NORMAL,
        category="system_health",
    )


# ---------------------------------------------------------------
# 3. Morning Summary
# ---------------------------------------------------------------

def create_morning_summary_check(
    tasks_manager: Any,
    learning_store: Any,
    timezone_str: str = "America/New_York",
    config: dict[str, Any] | None = None,
) -> HeartbeatCheck:
    """Generate a morning summary once per day."""

    cfg = (config or {}).get("checks", {}).get("morning_summary", {})
    hour_range = cfg.get("hour_range", [7, 9])
    _last_date: list[str] = [""]

    async def _check() -> list[dict[str, Any]] | None:
        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            return None

        try:
            tz = ZoneInfo(timezone_str)
            now = datetime.now(tz)

            if not (hour_range[0] <= now.hour <= hour_range[1]):
                return None

            today = now.strftime("%Y-%m-%d")
            if _last_date[0] == today:
                return None
            _last_date[0] = today

            parts = [f"☀️ Buenos días Mi Jefe — {now.strftime('%A %d de %B')}"]

            # Pending tasks
            try:
                pending = tasks_manager.get_pending()
                if pending:
                    titles = [t.get("title", "?") for t in pending[:5]]
                    parts.append(f"📋 Tareas pendientes ({len(pending)}): {', '.join(titles)}")
                else:
                    parts.append("✅ No hay tareas pendientes")
            except Exception:
                pass

            # Yesterday's stats
            try:
                stats = learning_store.get_execution_stats("general")
                if stats.get("total", 0) > 0:
                    parts.append(
                        f"📊 Ejecuciones recientes: {stats['total']} total, "
                        f"{stats['success_rate']:.0f}% éxito, "
                        f"promedio {stats['avg_duration']:.0f}s"
                    )
            except Exception:
                pass

            return [{
                "message": "\n".join(parts),
                "priority": Priority.HIGH,
            }]
        except Exception:
            return None

    return HeartbeatCheck(
        name="Resumen matutino",
        check_fn=_check,
        interval_minutes=cfg.get("interval_minutes", 15),
        default_priority=Priority.HIGH,
        category="morning_summary",
    )


# ---------------------------------------------------------------
# 4. Git Monitor
# ---------------------------------------------------------------

def create_git_monitor_check(config: dict[str, Any] | None = None) -> HeartbeatCheck:
    """Monitor git repos for new remote commits, failed CI, etc."""

    cfg = (config or {}).get("checks", {}).get("git_monitor", {})
    repos: list[str] = cfg.get("repos", [])
    interval = cfg.get("interval_minutes", 15)
    _known_heads: dict[str, str] = {}

    async def _check() -> list[dict[str, Any]] | None:
        if not repos:
            return None

        alerts: list[dict[str, Any]] = []

        for repo_path in repos:
            try:
                from pathlib import Path
                repo = Path(repo_path).expanduser()
                if not (repo / ".git").exists():
                    continue

                # Check for remote changes
                proc = await asyncio.create_subprocess_exec(
                    "git", "-C", str(repo), "fetch", "--dry-run",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)

                if stderr and b"From" in stderr:
                    # There are updates
                    repo_name = repo.name
                    alerts.append({
                        "message": f"Nuevos cambios en remoto: {repo_name}",
                        "details": stderr.decode(errors="replace")[:200],
                        "priority": Priority.NORMAL,
                    })

                # Check current branch status
                proc = await asyncio.create_subprocess_exec(
                    "git", "-C", str(repo), "status", "--porcelain",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)

                if stdout:
                    lines = stdout.decode(errors="replace").strip().splitlines()
                    if len(lines) > 10:
                        alerts.append({
                            "message": f"{repo.name}: {len(lines)} archivos sin commitear",
                            "priority": Priority.NORMAL,
                        })

            except asyncio.TimeoutError:
                continue
            except Exception:
                log.debug("heartbeat.git_check_failed", repo=repo_path, exc_info=True)

        return alerts if alerts else None

    return HeartbeatCheck(
        name="Monitor Git",
        check_fn=_check,
        interval_minutes=interval,
        default_priority=Priority.NORMAL,
        category="git_monitor",
    )


# ---------------------------------------------------------------
# 5. Web/Service Monitor
# ---------------------------------------------------------------

def create_web_monitor_check(config: dict[str, Any] | None = None) -> HeartbeatCheck:
    """Monitor URLs for uptime, response time, and SSL expiry."""

    cfg = (config or {}).get("checks", {}).get("web_monitor", {})
    urls: list[str] = cfg.get("urls", [])
    timeout_secs = cfg.get("timeout_seconds", 10)
    ssl_warning_days = cfg.get("ssl_warning_days", 14)
    interval = cfg.get("interval_minutes", 5)
    _last_status: dict[str, bool] = {}  # url -> was_up

    async def _check() -> list[dict[str, Any]] | None:
        if not urls:
            return None

        try:
            import aiohttp
        except ImportError:
            log.debug("heartbeat.web_monitor_needs_aiohttp")
            return None

        alerts: list[dict[str, Any]] = []

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=timeout_secs)
        ) as session:
            for url in urls:
                try:
                    start = time.time()
                    async with session.get(url, ssl=True) as resp:
                        elapsed = time.time() - start
                        status = resp.status

                        was_down = _last_status.get(url) is False

                        if status >= 500:
                            _last_status[url] = False
                            alerts.append({
                                "message": f"🔴 {url} — Error {status}",
                                "details": f"Tiempo: {elapsed:.1f}s",
                                "priority": Priority.CRITICAL,
                            })
                        elif status >= 400:
                            _last_status[url] = False
                            alerts.append({
                                "message": f"🟡 {url} — HTTP {status}",
                                "details": f"Tiempo: {elapsed:.1f}s",
                                "priority": Priority.HIGH,
                            })
                        elif elapsed > 5.0:
                            _last_status[url] = True
                            alerts.append({
                                "message": f"🐢 {url} — Lento ({elapsed:.1f}s)",
                                "priority": Priority.NORMAL,
                            })
                        else:
                            if was_down:
                                alerts.append({
                                    "message": f"✅ {url} — Recuperado ({elapsed:.1f}s)",
                                    "priority": Priority.HIGH,
                                })
                            _last_status[url] = True

                except aiohttp.ClientError as e:
                    was_up = _last_status.get(url, True)
                    _last_status[url] = False
                    if was_up:  # Only alert on transition
                        alerts.append({
                            "message": f"🔴 {url} — CAÍDO",
                            "details": str(e)[:200],
                            "priority": Priority.CRITICAL,
                        })
                except asyncio.TimeoutError:
                    was_up = _last_status.get(url, True)
                    _last_status[url] = False
                    if was_up:
                        alerts.append({
                            "message": f"🔴 {url} — Timeout ({timeout_secs}s)",
                            "priority": Priority.CRITICAL,
                        })

            # SSL check for HTTPS URLs
            for url in urls:
                if not url.startswith("https://"):
                    continue
                try:
                    from urllib.parse import urlparse
                    hostname = urlparse(url).hostname
                    if not hostname:
                        continue

                    cert_info = await asyncio.to_thread(
                        _get_ssl_expiry, hostname
                    )
                    if cert_info:
                        days_left = cert_info
                        if days_left <= ssl_warning_days:
                            prio = Priority.CRITICAL if days_left <= 3 else Priority.HIGH
                            alerts.append({
                                "message": f"🔒 SSL de {hostname} expira en {days_left} días",
                                "priority": prio,
                            })
                except Exception:
                    pass

        return alerts if alerts else None

    return HeartbeatCheck(
        name="Monitor Web",
        check_fn=_check,
        interval_minutes=interval,
        default_priority=Priority.HIGH,
        category="web_monitor",
    )


def _get_ssl_expiry(hostname: str) -> int | None:
    """Get days until SSL certificate expires."""
    import socket
    try:
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(socket.socket(), server_hostname=hostname) as s:
            s.settimeout(5)
            s.connect((hostname, 443))
            cert = s.getpeercert()
            if cert:
                expires_str = cert.get("notAfter", "")
                if expires_str:
                    expires = datetime.strptime(expires_str, "%b %d %H:%M:%S %Y %Z")
                    return (expires - datetime.utcnow()).days
    except Exception:
        pass
    return None


# ---------------------------------------------------------------
# 6. Error Pattern Monitor
# ---------------------------------------------------------------

def create_error_pattern_check(
    learning_store: Any,
    config: dict[str, Any] | None = None,
) -> HeartbeatCheck:
    """Detect repeated errors and suggest known solutions."""

    cfg = (config or {}).get("checks", {}).get("error_pattern_monitor", {})
    threshold_count = cfg.get("threshold_count", 3)
    window_minutes = cfg.get("threshold_window_minutes", 60)
    interval = cfg.get("interval_minutes", 10)

    async def _check() -> list[dict[str, Any]] | None:
        try:
            # Find errors that occurred multiple times recently
            rows = learning_store._engine.fetchall_dicts(
                "SELECT error_pattern, solution, occurrences, effectiveness "
                "FROM error_solutions "
                "WHERE occurrences >= ? "
                "AND last_seen >= datetime('now', ?)"
                "ORDER BY occurrences DESC LIMIT 5",
                (threshold_count, f"-{window_minutes} minutes"),
            )

            if not rows:
                return None

            alerts: list[dict[str, Any]] = []
            for row in rows:
                pattern = row["error_pattern"][:100]
                solution = row["solution"][:200]
                count = row["occurrences"]
                eff = row.get("effectiveness", 0)

                msg = f"Error recurrente ({count}x): {pattern}"
                details = f"Solución sugerida"
                if eff > 0.5:
                    details += f" (efectividad: {eff*100:.0f}%)"
                details += f": {solution}"

                alerts.append({
                    "message": msg,
                    "details": details,
                    "priority": Priority.HIGH,
                })

            return alerts
        except Exception:
            return None

    return HeartbeatCheck(
        name="Patrones de error",
        check_fn=_check,
        interval_minutes=interval,
        default_priority=Priority.HIGH,
        category="error_pattern",
    )


# ---------------------------------------------------------------
# 7. Contextual Reminders
# ---------------------------------------------------------------

def create_contextual_reminders_check(
    tasks_manager: Any,
    memory_engine: Any,
    timezone_str: str = "America/New_York",
    config: dict[str, Any] | None = None,
) -> HeartbeatCheck:
    """Context-aware reminders: afternoon task check, inactivity detection."""

    cfg = (config or {}).get("checks", {}).get("contextual_reminders", {})
    afternoon_hour = cfg.get("afternoon_reminder_hour", 16)
    inactivity_hours = cfg.get("inactivity_hours", 3)
    interval = cfg.get("interval_minutes", 60)
    _last_reminder_date: list[str] = [""]
    _last_inactivity_alert: list[float] = [0.0]

    async def _check() -> list[dict[str, Any]] | None:
        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            return None

        alerts: list[dict[str, Any]] = []

        try:
            tz = ZoneInfo(timezone_str)
            now = datetime.now(tz)
            today = now.strftime("%Y-%m-%d")

            # Afternoon task reminder
            if now.hour == afternoon_hour and _last_reminder_date[0] != today:
                pending = tasks_manager.get_pending()
                if pending:
                    _last_reminder_date[0] = today
                    undone = [t.get("title", "?") for t in pending[:3]]
                    alerts.append({
                        "message": f"Son las {afternoon_hour}:00 y tiene {len(pending)} tarea(s) pendiente(s)",
                        "details": "Pendientes: " + ", ".join(undone),
                        "priority": Priority.NORMAL,
                    })

            # Inactivity detection
            try:
                last_msg = memory_engine.fetchone(
                    "SELECT timestamp FROM conversations "
                    "WHERE role = 'user' ORDER BY id DESC LIMIT 1"
                )
                if last_msg and last_msg[0]:
                    last_time = datetime.fromisoformat(last_msg[0])
                    hours_inactive = (now.replace(tzinfo=None) - last_time).total_seconds() / 3600

                    if hours_inactive >= inactivity_hours:
                        # Only alert once per inactivity period (every 3h)
                        if time.time() - _last_inactivity_alert[0] > inactivity_hours * 3600:
                            _last_inactivity_alert[0] = time.time()
                            pending = tasks_manager.get_pending()
                            if pending:
                                alerts.append({
                                    "message": f"Lleva {hours_inactive:.0f}h sin interactuar y tiene tareas pendientes",
                                    "priority": Priority.LOW,
                                })
            except Exception:
                pass

        except Exception:
            pass

        return alerts if alerts else None

    return HeartbeatCheck(
        name="Recordatorios contextuales",
        check_fn=_check,
        interval_minutes=interval,
        default_priority=Priority.NORMAL,
        category="contextual_reminders",
    )
