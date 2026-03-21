"""Notification manager — priority routing, DND, digest, and relevance learning."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from typing import Any

import structlog

from src.core.heartbeat import Priority, CONFIG_PATH

log = structlog.get_logger("assistant.core.notification_manager")


class NotificationManager:
    """Manages notification delivery: priorities, DND, digest queuing, and relevance learning."""

    def __init__(self, memory_engine: Any = None, timezone_str: str = "America/New_York") -> None:
        self._memory = memory_engine
        self._timezone_str = timezone_str
        self._config = self._load_config()

        # DND state
        self._dnd_active = False
        self._focus_until: float | None = None

        # Digest queue
        self._digest_queue: list[dict[str, Any]] = []
        self._last_digest_time: float = 0.0

        # Relevance learning counters: {category: {sent: N, read: N, dismissed: N}}
        self._relevance_stats: dict[str, dict[str, int]] = {}

    @staticmethod
    def _load_config() -> dict[str, Any]:
        try:
            if CONFIG_PATH.exists():
                return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def reload_config(self) -> None:
        self._config = self._load_config()

    def _get_local_now(self) -> datetime:
        """Get current time in configured timezone."""
        try:
            from zoneinfo import ZoneInfo
            return datetime.now(ZoneInfo(self._timezone_str))
        except Exception:
            return datetime.now()

    # ---------------------------------------------------------------
    # DND / Focus Mode
    # ---------------------------------------------------------------

    def is_dnd_active(self) -> bool:
        """Check if Do Not Disturb is active (scheduled or manual focus)."""
        # Manual focus mode
        if self._focus_until is not None:
            if time.time() < self._focus_until:
                return True
            else:
                self._focus_until = None  # Expired

        # Scheduled DND
        dnd_cfg = self._config.get("do_not_disturb", {})
        if not dnd_cfg.get("enabled", False):
            return False

        schedule = dnd_cfg.get("schedule", {})
        start_h = schedule.get("start_hour", 23)
        end_h = schedule.get("end_hour", 6)

        now = self._get_local_now()
        hour = now.hour

        if start_h > end_h:
            # Overnight: e.g., 23-6
            return hour >= start_h or hour < end_h
        else:
            return start_h <= hour < end_h

    def set_focus_mode(self, minutes: int) -> datetime:
        """Activate focus mode for N minutes."""
        self._focus_until = time.time() + (minutes * 60)
        expires = datetime.now() + timedelta(minutes=minutes)
        log.info("notification.focus_mode_set", minutes=minutes, expires=expires.isoformat())
        return expires

    def clear_focus_mode(self) -> None:
        """Deactivate focus mode."""
        self._focus_until = None
        log.info("notification.focus_mode_cleared")

    def get_dnd_status(self) -> dict[str, Any]:
        """Return current DND/focus status."""
        active = self.is_dnd_active()
        result: dict[str, Any] = {"active": active}
        if self._focus_until is not None and time.time() < self._focus_until:
            remaining = (self._focus_until - time.time()) / 60
            result["focus_mode"] = True
            result["focus_remaining_minutes"] = round(remaining, 1)
        else:
            result["focus_mode"] = False

        dnd_cfg = self._config.get("do_not_disturb", {})
        if dnd_cfg.get("enabled"):
            schedule = dnd_cfg.get("schedule", {})
            result["schedule"] = f"{schedule.get('start_hour', 23)}:00 - {schedule.get('end_hour', 6)}:00"

        return result

    # ---------------------------------------------------------------
    # Should Send Decision
    # ---------------------------------------------------------------

    def should_send_now(self, alert: dict[str, Any]) -> bool:
        """Decide if an alert should be sent immediately."""
        priority = alert.get("priority", Priority.NORMAL)
        category = alert.get("category", "general")

        # Critical always goes through
        if isinstance(priority, Priority) and priority == Priority.CRITICAL:
            return True
        if isinstance(priority, int) and priority >= Priority.CRITICAL:
            return True

        # DND blocks non-critical
        if self.is_dnd_active():
            dnd_cfg = self._config.get("do_not_disturb", {})
            if dnd_cfg.get("allow_critical", True):
                return False  # Only critical passes

        # Check relevance learning — auto-downgrade if user ignores this category
        learned_prio = self._get_learned_priority(category)
        if learned_prio is not None and learned_prio < Priority.HIGH:
            return False  # Learned to queue this

        # HIGH+ gets sent immediately
        if isinstance(priority, Priority):
            return priority >= Priority.HIGH
        return priority >= Priority.HIGH

    # ---------------------------------------------------------------
    # Digest
    # ---------------------------------------------------------------

    def queue_for_digest(self, alert: dict[str, Any]) -> None:
        """Add an alert to the digest queue."""
        self._digest_queue.append(alert)
        log.debug("notification.queued_for_digest", source=alert.get("source"))

    def build_digest(self) -> str | None:
        """Build a formatted digest message from queued alerts."""
        if not self._digest_queue:
            return None

        digest_cfg = self._config.get("digest", {})
        max_items = digest_cfg.get("max_items_per_digest", 20)

        items = self._digest_queue[:max_items]
        now = self._get_local_now()

        lines = [f"📋 **Resumen — {now.strftime('%H:%M')}**\n"]

        # Group by category
        by_category: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            cat = item.get("category", "general")
            by_category.setdefault(cat, []).append(item)

        category_icons = {
            "tasks": "📝",
            "system_health": "💻",
            "git_monitor": "🔀",
            "web_monitor": "🌐",
            "error_pattern": "⚠️",
            "contextual_reminders": "⏰",
            "morning_summary": "☀️",
            "general": "📌",
        }

        for cat, alerts in by_category.items():
            icon = category_icons.get(cat, "📌")
            lines.append(f"\n{icon} **{cat.replace('_', ' ').title()}**")
            for a in alerts:
                msg = a.get("message", "?")
                lines.append(f"  • {msg}")

        total = len(self._digest_queue)
        if total > max_items:
            lines.append(f"\n_...y {total - max_items} más_")

        return "\n".join(lines)

    def clear_digest(self) -> None:
        """Clear the digest queue after sending."""
        count = len(self._digest_queue)
        self._digest_queue.clear()
        self._last_digest_time = time.time()
        log.info("notification.digest_cleared", items=count)

    def is_digest_due(self) -> bool:
        """Check if it's time to send a digest based on configured times."""
        digest_cfg = self._config.get("digest", {})
        if not digest_cfg.get("enabled", True):
            return False

        min_items = digest_cfg.get("min_items_to_send", 1)
        if len(self._digest_queue) < min_items:
            return False

        now = self._get_local_now()
        current_time = now.strftime("%H:%M")
        digest_times = digest_cfg.get("times", ["08:00", "13:00", "18:00"])

        # Check if current time matches any digest time (with 2-min window)
        for dt in digest_times:
            try:
                target = datetime.strptime(dt, "%H:%M").replace(
                    year=now.year, month=now.month, day=now.day
                )
                diff = abs((now.replace(tzinfo=None) - target).total_seconds())
                if diff < 120:  # Within 2-minute window
                    # Don't send twice in same window
                    if time.time() - self._last_digest_time > 300:
                        return True
            except ValueError:
                continue

        return False

    def get_digest_queue_count(self) -> int:
        return len(self._digest_queue)

    # ---------------------------------------------------------------
    # Relevance Learning
    # ---------------------------------------------------------------

    def log_notification(self, alert: dict[str, Any], action: str) -> None:
        """Log a notification event for relevance learning."""
        category = alert.get("category", "general")
        stats = self._relevance_stats.setdefault(category, {"sent": 0, "read": 0, "dismissed": 0})
        if action in ("sent", "sent_critical"):
            stats["sent"] += 1
        elif action == "read":
            stats["read"] += 1
        elif action == "dismissed":
            stats["dismissed"] += 1

        # Persist to DB
        if self._memory:
            try:
                source = alert.get("source", "")
                message = alert.get("message", "")[:300]
                priority = alert.get("priority", Priority.NORMAL)
                prio_name = priority.name if isinstance(priority, Priority) else str(priority)
                self._memory.execute(
                    "INSERT INTO notification_log "
                    "(category, source, message, priority, status) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (category, source, message, prio_name, action),
                )
            except Exception:
                pass

    def mark_notification_read(self, category: str) -> None:
        """Mark notifications of a category as read (user engaged with them)."""
        stats = self._relevance_stats.setdefault(category, {"sent": 0, "read": 0, "dismissed": 0})
        stats["read"] += 1

    def mark_notification_dismissed(self, category: str) -> None:
        """Mark notifications of a category as dismissed (user ignored them)."""
        stats = self._relevance_stats.setdefault(category, {"sent": 0, "read": 0, "dismissed": 0})
        stats["dismissed"] += 1

    def _get_learned_priority(self, category: str) -> Priority | None:
        """Check if relevance learning has adjusted the priority for a category."""
        learn_cfg = self._config.get("relevance_learning", {})
        if not learn_cfg.get("enabled", True):
            return None

        stats = self._relevance_stats.get(category)
        if not stats:
            # Try to load from DB
            if self._memory:
                try:
                    rows = self._memory.fetchall_dicts(
                        "SELECT status, COUNT(*) as cnt FROM notification_log "
                        "WHERE category = ? GROUP BY status",
                        (category,),
                    )
                    if rows:
                        stats = {"sent": 0, "read": 0, "dismissed": 0}
                        for row in rows:
                            if row["status"] in ("sent", "sent_critical"):
                                stats["sent"] += row["cnt"]
                            elif row["status"] == "read":
                                stats["read"] += row["cnt"]
                            elif row["status"] == "dismissed":
                                stats["dismissed"] += row["cnt"]
                        self._relevance_stats[category] = stats
                except Exception:
                    return None

        if not stats:
            return None

        downgrade_threshold = learn_cfg.get("downgrade_after_ignores", 5)
        upgrade_threshold = learn_cfg.get("upgrade_after_responses", 3)

        # If user consistently ignores, downgrade
        if stats["dismissed"] >= downgrade_threshold and stats["read"] < upgrade_threshold:
            return Priority.LOW

        # If user consistently reads/responds, upgrade
        if stats["read"] >= upgrade_threshold:
            return Priority.HIGH

        return None

    def get_relevance_stats(self) -> dict[str, dict[str, int]]:
        """Return relevance learning statistics."""
        return dict(self._relevance_stats)
