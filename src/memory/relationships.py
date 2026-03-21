"""Relationship tracking and sentiment analysis."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import structlog

from src.memory.engine import MemoryEngine

log = structlog.get_logger("assistant.memory.relationships")

_STAGES: list[tuple[str, int, int]] = [
    ("stranger", 0, 0),
    ("acquaintance", 20, 1),
    ("familiar", 100, 7),
    ("trusted", 500, 30),
    ("partner", 2000, 90),
]

# Heuristic sentiment keywords (Spanish + English)
_POSITIVE_PATTERNS = re.compile(
    r"\b(?:gracias|genial|perfecto|excelente|increíble|bien hecho|me encanta|"
    r"buen trabajo|thanks|great|perfect|excellent|awesome|love it|good job|"
    r"exacto|exactamente|eso es|así es|bravo|dale|chévere|súper|buenísimo|"
    r"te pasaste|crack|máquina|eres el mejor|nice|cool|amazing|fantastic)\b",
    re.IGNORECASE,
)

_NEGATIVE_PATTERNS = re.compile(
    r"\b(?:no sirve|está mal|error|no funciona|malo|pésimo|horrible|"
    r"no me gusta|qué asco|inútil|basura|porquería|idiota|tonto|"
    r"doesn't work|broken|terrible|awful|useless|wrong|bad|stupid|"
    r"no así|eso no|mal hecho|arregla|fix this|no no no)\b",
    re.IGNORECASE,
)

_FRUSTRATION_PATTERNS = re.compile(
    r"\b(?:ya te dije|otra vez|de nuevo|cuántas veces|no entiendes|"
    r"hazlo bien|ya basta|me desesperas|told you|again|how many times|"
    r"seriously|come on|ugh|damn|dammit)\b",
    re.IGNORECASE,
)


class RelationshipTracker:

    def __init__(self, engine: MemoryEngine) -> None:
        self._engine = engine

    def log_observation(self, note: str, sentiment: str = "neutral") -> int:
        if sentiment not in ("positive", "neutral", "negative"):
            raise ValueError(f"Invalid sentiment: {sentiment!r}. Must be positive/neutral/negative.")
        sql = "INSERT INTO relationship_log (note, sentiment) VALUES (?, ?)"
        row_id = self._engine.insert_returning_id(sql, (note, sentiment))
        log.debug("relationship.observation_logged", sentiment=sentiment, row_id=row_id)
        return row_id

    def analyze_sentiment(self, text: str) -> str:
        """Auto-detect sentiment from user message text (heuristic)."""
        if not text or len(text.strip()) < 2:
            return "neutral"

        pos_matches = len(_POSITIVE_PATTERNS.findall(text))
        neg_matches = len(_NEGATIVE_PATTERNS.findall(text))
        frust_matches = len(_FRUSTRATION_PATTERNS.findall(text))

        neg_total = neg_matches + frust_matches

        if pos_matches > 0 and neg_total == 0:
            return "positive"
        if neg_total > 0 and pos_matches == 0:
            return "negative"
        if neg_total > pos_matches:
            return "negative"
        if pos_matches > neg_total:
            return "positive"
        return "neutral"

    def auto_track(self, user_message: str) -> None:
        """Automatically analyze and log sentiment from a user message."""
        sentiment = self.analyze_sentiment(user_message)
        if sentiment != "neutral":
            # Only log non-neutral to avoid noise
            snippet = user_message[:100]
            self.log_observation(f"Auto: {snippet}", sentiment=sentiment)

    def get_recent_mood(self, last_n: int = 5) -> str:
        """Get the dominant mood from the last N observations."""
        rows = self._engine.fetchall(
            "SELECT sentiment FROM relationship_log ORDER BY id DESC LIMIT ?",
            (last_n,),
        )
        if not rows:
            return "neutral"
        sentiments = [r[0] for r in rows]
        neg_count = sentiments.count("negative")
        pos_count = sentiments.count("positive")
        if neg_count >= 3:
            return "frustrated"
        if neg_count > pos_count:
            return "negative"
        if pos_count > neg_count:
            return "positive"
        return "neutral"

    def get_relationship_history(self, limit: int = 50) -> list[dict[str, Any]]:
        sql = "SELECT id, date, note, sentiment FROM relationship_log ORDER BY id DESC LIMIT ?"
        return self._engine.fetchall_dicts(sql, (limit,))

    def get_relationship_stage(self) -> str:
        row = self._engine.fetchone("SELECT COUNT(*) FROM conversations")
        total_messages = row[0] if row else 0
        row = self._engine.fetchone("SELECT MIN(timestamp) FROM conversations")
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
        stage = "stranger"
        for stage_name, min_msgs, min_days in reversed(_STAGES):
            if total_messages >= min_msgs and days_active >= min_days:
                stage = stage_name
                break
        log.debug("relationship.stage_computed", stage=stage, total_messages=total_messages, days_active=days_active)
        return stage

    def get_sentiment_summary(self) -> dict[str, int]:
        sql = "SELECT sentiment, COUNT(*) as cnt FROM relationship_log GROUP BY sentiment"
        rows = self._engine.fetchall(sql)
        return {row[0]: row[1] for row in rows}
