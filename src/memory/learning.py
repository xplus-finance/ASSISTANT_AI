"""
Learning and knowledge persistence.

Manages two complementary stores:
- **learned_facts**: discrete facts about the user, their projects,
  preferences, and the world — with confidence scores and usage tracking.
- **knowledge**: longer-form knowledge articles with topics and sources.

Both tables have FTS5 indexes for fast semantic retrieval.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

from src.memory.engine import MemoryEngine, sanitize_fts_query

log = structlog.get_logger("assistant.memory.learning")

_VALID_CATEGORIES = {"user", "project", "preference", "technical", "world"}


class LearningStore:
    """Read/write access to facts and knowledge."""

    def __init__(self, engine: MemoryEngine) -> None:
        self._engine = engine

    # ------------------------------------------------------------------
    # Facts
    # ------------------------------------------------------------------

    def add_fact(
        self,
        category: str,
        fact: str,
        source: str | None = None,
        confidence: float = 1.0,
    ) -> int:
        """
        Store a new learned fact.

        Args:
            category: One of 'user', 'project', 'preference', 'technical', 'world'.
            fact: The fact text.
            source: Where this fact was learned from (e.g. 'conversation', 'web').
            confidence: Confidence score between 0.0 and 1.0.

        Returns:
            The id of the inserted fact.

        Raises:
            ValueError: If category or confidence is invalid.
        """
        if category not in _VALID_CATEGORIES:
            raise ValueError(f"Invalid category: {category!r}. Must be one of {_VALID_CATEGORIES}")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"Confidence must be between 0 and 1, got {confidence}")

        sql = """
            INSERT INTO learned_facts (category, fact, source, confidence)
            VALUES (?, ?, ?, ?)
        """
        fact_id = self._engine.insert_returning_id(sql, (category, fact, source, confidence))
        log.debug("learning.fact_added", fact_id=fact_id, category=category)
        return fact_id

    def search_facts(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """
        Full-text search across learned facts using FTS5.

        Returns matches ranked by relevance (BM25).
        """
        safe_query = sanitize_fts_query(query)
        if not safe_query:
            return []
        sql = """
            SELECT f.id, f.category, f.fact, f.confidence, f.source,
                   f.learned_at, f.last_used, f.use_count, rank
            FROM facts_fts fts
            JOIN learned_facts f ON f.id = fts.rowid
            WHERE facts_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """
        return self._engine.fetchall_dicts(sql, (safe_query, limit))

    def get_facts_by_category(self, category: str) -> list[dict[str, Any]]:
        """Return all facts for a given category, ordered by confidence descending."""
        sql = """
            SELECT id, category, fact, confidence, source, learned_at, last_used, use_count
            FROM learned_facts
            WHERE category = ?
            ORDER BY confidence DESC, learned_at DESC
        """
        return self._engine.fetchall_dicts(sql, (category,))

    def update_fact_usage(self, fact_id: int) -> None:
        """Increment use_count and update last_used timestamp for a fact."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        sql = """
            UPDATE learned_facts
            SET use_count = use_count + 1,
                last_used = ?
            WHERE id = ?
        """
        self._engine.execute(sql, (now, fact_id))
        log.debug("learning.fact_usage_updated", fact_id=fact_id)

    def get_most_used_facts(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return facts ordered by use_count descending."""
        sql = """
            SELECT id, category, fact, confidence, use_count, last_used
            FROM learned_facts
            WHERE use_count > 0
            ORDER BY use_count DESC
            LIMIT ?
        """
        return self._engine.fetchall_dicts(sql, (limit,))

    # ------------------------------------------------------------------
    # Knowledge
    # ------------------------------------------------------------------

    def add_knowledge(
        self,
        topic: str,
        content: str,
        source_url: str | None = None,
    ) -> int:
        """
        Store a knowledge article.

        Args:
            topic: Short topic/title.
            content: Full content text.
            source_url: Optional URL where the knowledge came from.

        Returns:
            The id of the inserted knowledge entry.
        """
        sql = """
            INSERT INTO knowledge (topic, content, source_url)
            VALUES (?, ?, ?)
        """
        kid = self._engine.insert_returning_id(sql, (topic, content, source_url))
        log.debug("learning.knowledge_added", knowledge_id=kid, topic=topic)
        return kid

    def search_knowledge(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """
        Full-text search across knowledge entries using FTS5.

        Searches both topic and content fields.
        """
        safe_query = sanitize_fts_query(query)
        if not safe_query:
            return []
        sql = """
            SELECT k.id, k.topic, k.content, k.source_url,
                   k.learned_at, k.relevance_score, rank
            FROM knowledge_fts kf
            JOIN knowledge k ON k.id = kf.rowid
            WHERE knowledge_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """
        return self._engine.fetchall_dicts(sql, (safe_query, limit))

    def get_knowledge_by_topic(self, topic: str) -> list[dict[str, Any]]:
        """Return knowledge entries with an exact topic match."""
        sql = """
            SELECT id, topic, content, source_url, learned_at, relevance_score
            FROM knowledge
            WHERE topic = ?
            ORDER BY relevance_score DESC
        """
        return self._engine.fetchall_dicts(sql, (topic,))
