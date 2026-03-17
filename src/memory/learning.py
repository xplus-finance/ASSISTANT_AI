"""
Learning and knowledge persistence.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

from src.memory.engine import MemoryEngine, sanitize_fts_query

log = structlog.get_logger("assistant.memory.learning")

_VALID_CATEGORIES = {"user", "project", "preference", "technical", "world"}


class LearningStore:
    def __init__(self, engine: MemoryEngine) -> None:
        self._engine = engine

    def add_fact(self, category: str, fact: str, source: str | None = None, confidence: float = 1.0) -> int:
        if category not in _VALID_CATEGORIES:
            raise ValueError(f"Invalid category: {category!r}")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"Confidence must be between 0 and 1, got {confidence}")
        sql = "INSERT INTO learned_facts (category, fact, source, confidence) VALUES (?, ?, ?, ?)"
        fact_id = self._engine.insert_returning_id(sql, (category, fact, source, confidence))
        log.debug("learning.fact_added", fact_id=fact_id, category=category)
        return fact_id

    def search_facts(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        safe_query = sanitize_fts_query(query)
        if not safe_query:
            return []
        sql = "SELECT f.id, f.category, f.fact, f.confidence, f.source, f.learned_at, f.last_used, f.use_count, rank FROM facts_fts fts JOIN learned_facts f ON f.id = fts.rowid WHERE facts_fts MATCH ? ORDER BY rank LIMIT ?"
        return self._engine.fetchall_dicts(sql, (safe_query, limit))

    def get_facts_by_category(self, category: str) -> list[dict[str, Any]]:
        sql = "SELECT id, category, fact, confidence, source, learned_at, last_used, use_count FROM learned_facts WHERE category = ? ORDER BY confidence DESC, learned_at DESC"
        return self._engine.fetchall_dicts(sql, (category,))

    def update_fact_usage(self, fact_id: int) -> None:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        sql = "UPDATE learned_facts SET use_count = use_count + 1, last_used = ? WHERE id = ?"
        self._engine.execute(sql, (now, fact_id))

    def get_most_used_facts(self, limit: int = 20) -> list[dict[str, Any]]:
        sql = "SELECT id, category, fact, confidence, use_count, last_used FROM learned_facts WHERE use_count > 0 ORDER BY use_count DESC LIMIT ?"
        return self._engine.fetchall_dicts(sql, (limit,))

    def add_knowledge(self, topic: str, content: str, source_url: str | None = None) -> int:
        sql = "INSERT INTO knowledge (topic, content, source_url) VALUES (?, ?, ?)"
        kid = self._engine.insert_returning_id(sql, (topic, content, source_url))
        log.debug("learning.knowledge_added", knowledge_id=kid, topic=topic)
        return kid

    def search_knowledge(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        safe_query = sanitize_fts_query(query)
        if not safe_query:
            return []
        sql = "SELECT k.id, k.topic, k.content, k.source_url, k.learned_at, k.relevance_score, rank FROM knowledge_fts kf JOIN knowledge k ON k.id = kf.rowid WHERE knowledge_fts MATCH ? ORDER BY rank LIMIT ?"
        return self._engine.fetchall_dicts(sql, (safe_query, limit))

    def get_knowledge_by_topic(self, topic: str) -> list[dict[str, Any]]:
        sql = "SELECT id, topic, content, source_url, learned_at, relevance_score FROM knowledge WHERE topic = ? ORDER BY relevance_score DESC"
        return self._engine.fetchall_dicts(sql, (topic,))
