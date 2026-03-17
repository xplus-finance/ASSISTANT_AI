"""
Relationship tracking and sentiment analysis over time.

Logs observations about the user-assistant relationship and derives
a qualitative "stage" based on interaction volume and history length.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

from src.memory.engine import MemoryEngine

log = structlog.get_logger("assistant.memory.relationships")

# Stage thresholds (message count, days active)
_STAGES: list[tuple[str, int, int]] = [
    # (stage_name, min_messages, min_days)
    ("stranger", 0, 0),
    ("acquaintance", 20, 1),
    ("familiar", 100, 7),
    ("trusted", 500, 30),
    ("partner", 2000, 90),
]


class RelationshipTracker:
    """Track and query the evolving user-assistant relationship."""

    def __init__(self, engine: MemoryEngine) -> None:
        self._engine = engine

    def log_observation(self, note: str, sentiment: str = "neutral") -> int:
        """
        Record a relationship observation.

        Args:
            note: Free-text observation (e.g. "User seemed frustrated with slow response").
            sentiment: One of 'positive', 'neutral', 'negative'.

        Returns:
            The id of the inserted row.
        """
        if sentiment not in ("positive", "neutral", "negative"):
            raise ValueError(f"Invalid sentiment: {sentiment!r}. Must be positive/neutral/negative.")

        sql = """
            INSERT INTO relationship_log (note, sentiment)
            VALUES (?, ?)
        """
        row_id = self._engine.insert_returning_id(sql, (note, sentiment))
        log.debug("relationship.observation_logged", sentiment=sentiment, row_id=row_id)
        return row_id

    def get_relationship_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent relationship observations, newest first."""
        sql = """
            SELECT id, date, note, sentiment
            FROM relationship_log
            ORDER BY id DESC
            LIMIT ?
        """
        return self._engine.fetchall_dicts(sql, (limit,))

    def get_relationship_stage(self) -> str:
        """
        Derive the current relationship stage based on total message count
        and the number of days since the first recorded message.

        Stages (in order):
            stranger -> acquaintance -> familiar -> trusted -> partner
        """
        # Total messages
        row = self._engine.fetchone("SELECT COUNT(*) FROM conversations")
        total_messages = row[0] if row else 0

        # Days since first message
        row = self._engine.fetchone(
            "SELECT MIN(timestamp) FROM conversations"
        )
        if row and row[0]:
            try:
                first_ts = datetime.fromisoformat(row[0])
                if first_ts.tzinfo is None:
                    first_ts = first_ts.replace(tzinfo=timezone.utc)
                days_active = (datetime.now(timezone.utc) - first_ts).days
            except (ValueError, TypeError):
                days_active = 0
        else:
            days_active = 0

        # Walk stages from highest to lowest; first match wins
        stage = "stranger"
        for stage_name, min_msgs, min_days in reversed(_STAGES):
            if total_messages >= min_msgs and days_active >= min_days:
                stage = stage_name
                break

        log.debug(
            "relationship.stage_computed",
            stage=stage,
            total_messages=total_messages,
            days_active=days_active,
        )
        return stage

    def get_sentiment_summary(self) -> dict[str, int]:
        """Return counts of each sentiment across all observations."""
        sql = """
            SELECT sentiment, COUNT(*) as cnt
            FROM relationship_log
            GROUP BY sentiment
        """
        rows = self._engine.fetchall(sql)
        return {row[0]: row[1] for row in rows}
