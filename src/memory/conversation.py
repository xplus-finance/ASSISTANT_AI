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
        self,
        role: str,
        message: str,
        session_id: str,
        message_type: str = "text",
        audio_duration: float | None = None,
        channel: str = "telegram",
    ) -> int:
        """
        Persist a new message and return its row id.

        Args:
            role: One of 'user', 'assistant', 'system'.
            message: The message text.
            session_id: Identifier for the current session.
            message_type: One of 'text', 'audio', 'image', 'document'.
            audio_duration: Duration in seconds (only for audio messages).
            channel: Origin channel (default 'telegram').

        Returns:
            The id of the inserted row.
        """
        sql = """
            INSERT INTO conversations (role, message, session_id, message_type, audio_duration_secs, channel)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        row_id = self._engine.insert_returning_id(
            sql, (role, message, session_id, message_type, audio_duration, channel)
        )
        log.debug(
            "conversation.message_added",
            role=role,
            session_id=session_id,
            message_type=message_type,
            msg_id=row_id,
        )
        return row_id

    def get_recent(self, session_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """
        Return the most recent messages for a session, ordered oldest-first.

        The query fetches the last *limit* rows and reverses so the caller
        gets chronological order (useful for building conversation context).
        """
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
        """
        Full-text search across all conversation messages using FTS5.

        Returns matches ranked by relevance (BM25).
        """
        safe_query = sanitize_fts_query(query)
        if not safe_query:
            return []
        sql = """
            SELECT c.id, c.timestamp, c.role, c.message, c.session_id, c.channel,
                   rank
            FROM conversations_fts f
            JOIN conversations c ON c.id = f.rowid
            WHERE conversations_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """
        return self._engine.fetchall_dicts(sql, (safe_query, limit))

    def get_session_messages(self, session_id: str) -> list[dict[str, Any]]:
        """Return *all* messages for a given session in chronological order."""
        sql = """
            SELECT id, timestamp, role, message, message_type, audio_duration_secs, channel
            FROM conversations
            WHERE session_id = ?
            ORDER BY id ASC
        """
        return self._engine.fetchall_dicts(sql, (session_id,))

    def get_message_count(self) -> int:
        """Return total number of messages across all sessions."""
        row = self._engine.fetchone("SELECT COUNT(*) FROM conversations")
        return row[0] if row else 0

    def get_all_sessions(self) -> list[str]:
        """Return a list of all distinct session IDs, most recent first."""
        sql = """
            SELECT DISTINCT session_id
            FROM conversations
            ORDER BY MAX(id) DESC
        """
        # DISTINCT + ORDER BY MAX(id) requires GROUP BY
        sql = """
            SELECT session_id
            FROM conversations
            GROUP BY session_id
            ORDER BY MAX(id) DESC
        """
        rows = self._engine.fetchall(sql)
        return [r[0] for r in rows]
