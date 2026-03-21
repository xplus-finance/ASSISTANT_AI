"""HeartbeatPro — Proactive intelligence engine with AI reasoning, priority system, and auto-learning."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from enum import IntEnum
from pathlib import Path
from typing import Any, Callable, Awaitable

import structlog

log = structlog.get_logger("assistant.core.heartbeat")

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "heartbeat.json"


class Priority(IntEnum):
    """Notification priority levels."""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


class HeartbeatCheck:
    """A single proactive check that the heartbeat runs."""

    def __init__(
        self,
        name: str,
        check_fn: Callable[[], Awaitable[list[dict[str, Any]] | None]],
        interval_minutes: int = 15,
        default_priority: Priority = Priority.NORMAL,
        enabled: bool = True,
        category: str = "general",
    ) -> None:
        self.name = name
        self.check_fn = check_fn
        self.interval_minutes = interval_minutes
        self.default_priority = default_priority
        self.enabled = enabled
        self.category = category
        self.last_run: float = 0.0
        self.last_result: list[dict[str, Any]] | None = None
        self.run_count: int = 0
        self.fail_count: int = 0


class HeartbeatPro:
    """Proactive intelligence engine with AI reasoning and notification management."""

    def __init__(
        self,
        send_fn: Callable[[str], Awaitable[None]],
        notification_manager: Any = None,
        ai_reason_fn: Callable[[str], Awaitable[str]] | None = None,
        memory_engine: Any = None,
    ) -> None:
        self._send = send_fn
        self._notification_manager = notification_manager
        self._ai_reason = ai_reason_fn
        self._memory = memory_engine
        self._checks: list[HeartbeatCheck] = []
        self._running = False
        self._task: asyncio.Task | None = None
        self._config = self._load_config()
        self._tick_interval = self._config.get("heartbeat", {}).get("interval_seconds", 60)
        self._ai_interval_min = self._config.get("heartbeat", {}).get("ai_reasoning_interval_minutes", 30)
        self._last_ai_reasoning: float = 0.0
        self._pending_alerts: list[dict[str, Any]] = []
        self._stats = {"ticks": 0, "notifications_sent": 0, "ai_reasonings": 0, "checks_run": 0}

    @staticmethod
    def _load_config() -> dict[str, Any]:
        """Load heartbeat configuration from JSON file."""
        try:
            if CONFIG_PATH.exists():
                return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            log.warning("heartbeat.config_load_failed", path=str(CONFIG_PATH), exc_info=True)
        return {}

    def reload_config(self) -> None:
        """Hot-reload configuration from disk."""
        self._config = self._load_config()
        self._tick_interval = self._config.get("heartbeat", {}).get("interval_seconds", 60)
        self._ai_interval_min = self._config.get("heartbeat", {}).get("ai_reasoning_interval_minutes", 30)

        # Update check states from config
        checks_cfg = self._config.get("checks", {})
        for check in self._checks:
            cat_cfg = checks_cfg.get(check.category, {})
            if cat_cfg:
                check.enabled = cat_cfg.get("enabled", check.enabled)
                check.interval_minutes = cat_cfg.get("interval_minutes", check.interval_minutes)
                prio_str = cat_cfg.get("default_priority", "")
                if prio_str and hasattr(Priority, prio_str):
                    check.default_priority = Priority[prio_str]

        log.info("heartbeat.config_reloaded")

    def register_check(self, check: HeartbeatCheck) -> None:
        """Register a new proactive check."""
        self._checks.append(check)
        log.debug("heartbeat.check_registered", name=check.name,
                  interval=check.interval_minutes, category=check.category)

    def unregister_check(self, name: str) -> bool:
        """Remove a check by name."""
        before = len(self._checks)
        self._checks = [c for c in self._checks if c.name != name]
        removed = len(self._checks) < before
        if removed:
            log.info("heartbeat.check_unregistered", name=name)
        return removed

    def get_checks(self) -> list[dict[str, Any]]:
        """Return status of all registered checks."""
        return [
            {
                "name": c.name,
                "category": c.category,
                "enabled": c.enabled,
                "interval_minutes": c.interval_minutes,
                "priority": c.default_priority.name,
                "last_run": c.last_run,
                "run_count": c.run_count,
                "fail_count": c.fail_count,
            }
            for c in self._checks
        ]

    def get_stats(self) -> dict[str, Any]:
        """Return heartbeat statistics."""
        return {
            **self._stats,
            "running": self._running,
            "registered_checks": len(self._checks),
            "enabled_checks": sum(1 for c in self._checks if c.enabled),
            "pending_alerts": len(self._pending_alerts),
        }

    def start(self) -> None:
        """Start the heartbeat loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        log.info("heartbeat.started", checks=len(self._checks),
                 interval=self._tick_interval, ai_interval=self._ai_interval_min)

    def stop(self) -> None:
        """Stop the heartbeat loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        log.info("heartbeat.stopped", stats=self._stats)

    async def _loop(self) -> None:
        """Main heartbeat loop."""
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("heartbeat.tick_error")
            await asyncio.sleep(self._tick_interval)

    async def _tick(self) -> None:
        """Run all due checks, then optionally apply AI reasoning."""
        now = time.time()
        self._stats["ticks"] += 1
        collected_alerts: list[dict[str, Any]] = []

        for check in self._checks:
            if not check.enabled:
                continue
            elapsed_min = (now - check.last_run) / 60
            if elapsed_min < check.interval_minutes:
                continue

            check.last_run = now
            check.run_count += 1
            self._stats["checks_run"] += 1

            try:
                results = await check.check_fn()
                check.last_result = results
                if results:
                    for alert in results:
                        alert.setdefault("source", check.name)
                        alert.setdefault("category", check.category)
                        alert.setdefault("priority", check.default_priority)
                        alert.setdefault("timestamp", now)
                        collected_alerts.append(alert)
            except Exception:
                check.fail_count += 1
                log.warning("heartbeat.check_failed", check=check.name, exc_info=True)

        if collected_alerts:
            self._pending_alerts.extend(collected_alerts)

        # AI reasoning phase: periodically let AI decide what matters
        ai_elapsed = (now - self._last_ai_reasoning) / 60
        if self._ai_reason and ai_elapsed >= self._ai_interval_min and self._pending_alerts:
            await self._run_ai_reasoning()

        # Process pending alerts through notification manager
        await self._process_alerts()

    async def _run_ai_reasoning(self) -> None:
        """Let AI reason about pending alerts and decide what to notify."""
        if not self._ai_reason or not self._pending_alerts:
            return

        self._last_ai_reasoning = time.time()
        self._stats["ai_reasonings"] += 1

        # Build context for AI
        alert_summary = []
        for a in self._pending_alerts[:20]:  # Cap at 20 to keep prompt reasonable
            prio = a.get("priority", Priority.NORMAL)
            prio_name = prio.name if isinstance(prio, Priority) else str(prio)
            alert_summary.append(
                f"- [{prio_name}] {a.get('source', '?')}: {a.get('message', '?')}"
            )

        prompt = (
            "Eres el sistema de notificaciones proactivo de Mi Jefe. "
            "Analiza estas alertas pendientes y decide:\n"
            "1. ¿Cuáles son realmente importantes para notificar AHORA?\n"
            "2. ¿Cuáles pueden esperar al digest?\n"
            "3. ¿Cuáles son irrelevantes y se pueden descartar?\n\n"
            f"Alertas pendientes ({len(self._pending_alerts)}):\n"
            + "\n".join(alert_summary) + "\n\n"
            "Responde en JSON con formato:\n"
            '{"notify_now": ["índice0", ...], "digest": ["índice0", ...], "discard": ["índice0", ...]}\n'
            "Donde los índices son posiciones en la lista (empezando en 0)."
        )

        try:
            response = await asyncio.wait_for(self._ai_reason(prompt), timeout=30)
            # Try to parse AI decision
            decision = self._parse_ai_decision(response)
            if decision:
                await self._apply_ai_decision(decision)
        except asyncio.TimeoutError:
            log.warning("heartbeat.ai_reasoning_timeout")
        except Exception:
            log.warning("heartbeat.ai_reasoning_failed", exc_info=True)

    def _parse_ai_decision(self, response: str) -> dict[str, list[int]] | None:
        """Parse AI's JSON decision about alerts."""
        try:
            # Find JSON in response
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                raw = json.loads(response[start:end])
                return {
                    "notify_now": [int(i) for i in raw.get("notify_now", [])],
                    "digest": [int(i) for i in raw.get("digest", [])],
                    "discard": [int(i) for i in raw.get("discard", [])],
                }
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
        return None

    async def _apply_ai_decision(self, decision: dict[str, list[int]]) -> None:
        """Apply AI's decision to pending alerts."""
        alerts = self._pending_alerts[:]
        new_pending = []

        for i, alert in enumerate(alerts):
            if i in decision.get("notify_now", []):
                alert["priority"] = max(alert.get("priority", Priority.NORMAL), Priority.HIGH)
            elif i in decision.get("discard", []):
                continue  # Drop it
            elif i in decision.get("digest", []):
                alert["priority"] = Priority.NORMAL
                new_pending.append(alert)
                continue
            else:
                new_pending.append(alert)
                continue

            # Notify now items get processed immediately
            await self._deliver_alert(alert)

        self._pending_alerts = new_pending

    async def _process_alerts(self) -> None:
        """Process pending alerts through the notification manager or send directly."""
        if not self._pending_alerts:
            return

        nm = self._notification_manager
        remaining = []

        for alert in self._pending_alerts:
            priority = alert.get("priority", Priority.NORMAL)

            if nm:
                # Let notification manager handle DND, digest, etc.
                should_send = nm.should_send_now(alert)
                if should_send:
                    await self._deliver_alert(alert)
                    nm.log_notification(alert, "sent")
                elif priority == Priority.CRITICAL:
                    # Critical always goes through
                    await self._deliver_alert(alert)
                    nm.log_notification(alert, "sent_critical")
                else:
                    # Queue for digest
                    nm.queue_for_digest(alert)
            else:
                # No notification manager — send HIGH+ directly, skip LOW
                if isinstance(priority, Priority) and priority >= Priority.HIGH:
                    await self._deliver_alert(alert)
                elif isinstance(priority, int) and priority >= Priority.HIGH:
                    await self._deliver_alert(alert)
                else:
                    remaining.append(alert)
                    continue

        self._pending_alerts = remaining

    async def _deliver_alert(self, alert: dict[str, Any]) -> None:
        """Format and send a single alert to the user."""
        priority = alert.get("priority", Priority.NORMAL)
        source = alert.get("source", "Sistema")
        message = alert.get("message", "")
        details = alert.get("details", "")

        # Priority emoji
        prio_map = {
            Priority.CRITICAL: "🔴",
            Priority.HIGH: "🟠",
            Priority.NORMAL: "🔵",
            Priority.LOW: "⚪",
        }
        emoji = prio_map.get(priority, "🔔") if isinstance(priority, Priority) else "🔔"

        # Format notification
        text = f"{emoji} **{source}**\n{message}"
        if details:
            text += f"\n\n{details}"

        try:
            await self._send(text)
            self._stats["notifications_sent"] += 1

            # Log to memory
            if self._memory:
                try:
                    self._memory.execute(
                        "INSERT INTO notification_log "
                        "(category, source, message, priority, status) "
                        "VALUES (?, ?, ?, ?, 'sent')",
                        (
                            alert.get("category", "general"),
                            source,
                            message[:500],
                            priority.name if isinstance(priority, Priority) else str(priority),
                        ),
                    )
                except Exception:
                    pass  # Table might not exist yet
        except Exception:
            log.warning("heartbeat.deliver_failed", source=source, exc_info=True)

    async def force_check(self, check_name: str | None = None) -> list[dict[str, Any]]:
        """Force-run a specific check or all checks immediately."""
        results = []
        for check in self._checks:
            if check_name and check.name != check_name:
                continue
            if not check.enabled:
                continue
            try:
                check.last_run = time.time()
                check.run_count += 1
                alerts = await check.check_fn()
                if alerts:
                    results.extend(alerts)
            except Exception:
                check.fail_count += 1
                log.warning("heartbeat.force_check_failed", check=check.name, exc_info=True)
        return results

    async def send_digest_now(self) -> None:
        """Force send the current digest immediately."""
        if self._notification_manager:
            digest = self._notification_manager.build_digest()
            if digest:
                await self._send(digest)
                self._notification_manager.clear_digest()

    def set_focus_mode(self, minutes: int) -> datetime:
        """Enable focus/DND mode for N minutes. Returns when it expires."""
        if self._notification_manager:
            return self._notification_manager.set_focus_mode(minutes)
        from datetime import timedelta
        return datetime.now() + timedelta(minutes=minutes)

    def clear_focus_mode(self) -> None:
        """Disable focus mode immediately."""
        if self._notification_manager:
            self._notification_manager.clear_focus_mode()
