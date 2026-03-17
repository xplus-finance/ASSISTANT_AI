"""
Conversation storage and retrieval.

Manages the conversations table with full-text search support via FTS5.
"""

from __future__ import annotations

from typing import Any

import structlog

from src.memory.engine import MemoryEngine, sanitize_fts_query

log = structlog.get_logger("assistant.memory.conversation")


class ConversationStore:
    """Read/write access to the conversation history."""

    def __init__(self, engine: MemoryEngine) -> None:
        self._engine = engine

    def add_message(
        self, role: str, message: str, session_id: str,
        message_type: str = "text", audio_duration: float | None = None,
        channel: str = "telegram",
    ) -> int:
        sql = """
            INSERT INTO conversations (role, message, session_id, message_type, audio_duration_secs, channel)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        row_id = self._engine.insert_returning_id(
            sql, (role, message, session_id, message_type, audio_duration, channel)
        )
        log.debug("conversation.message_added", role=role, session_id=session_id, message_type=message_type, msg_id=row_id)
        return row_id

    def get_recent(self, session_id: str, limit: int = 50) -> list[dict[str, Any]]:
        sql = """
            SELECT id, timestamp, role, message, message_type, audio_duration_secs, channel
            FROM conversations
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT ?
        """
        rows = self._engine.fetchall_dicts(sql, (session_id, limit))
        rows.reverse()
        return rows

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        safe_query = sanitize_fts_query(query)
        if not safe_query:
            return []
        sql = """
            SELECT c.id, c.timestamp, c.role, c.message, c.session_id, c.channel, rank
            FROM conversations_fts f
            JOIN conversations c ON c.id = f.rowid
            WHERE conversations_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """
        return self._engine.fetchall_dicts(sql, (safe_query, limit))

    def get_session_messages(self, session_id: str) -> list[dict[str, Any]]:
        sql = """
            SELECT id, timestamp, role, message, message_type, audio_duration_secs, channel
            FROM conversations
            WHERE session_id = ?
            ORDER BY id ASC
        """
        return self._engine.fetchall_dicts(sql, (session_id,))

    def get_message_count(self) -> int:
        row = self._engine.fetchone("SELECT COUNT(*) FROM conversations")
        return row[0] if row else 0

    def get_all_sessions(self) -> list[str]:
        sql = """
            SELECT session_id
            FROM conversations
            GROUP BY session_id
            ORDER BY MAX(id) DESC
        """
        rows = self._engine.fetchall(sql)
        return [r[0] for r in rows]
