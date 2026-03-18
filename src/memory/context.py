"""Conversation context assembly from memory stores."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from src.memory.conversation import ConversationStore
from src.memory.engine import MemoryEngine
from src.memory.learning import LearningStore
from src.memory.tasks import TaskManager

log = structlog.get_logger("assistant.memory.context")


@dataclass(frozen=True, slots=True)
class ConversationContext:
    user_profile: dict[str, str]
    recent_messages: list[dict[str, Any]]
    relevant_facts: list[dict[str, Any]]
    relevant_knowledge: list[dict[str, Any]]
    pending_tasks: list[dict[str, Any]]
    active_projects: list[dict[str, Any]]
    last_session_summary: dict[str, Any] | None
    session_id: str
    current_message: str
    procedures: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class ContextBuilder:
    def __init__(self, engine: MemoryEngine, conversation: ConversationStore, learning: LearningStore, tasks: TaskManager) -> None:
        self._engine = engine
        self._conversation = conversation
        self._learning = learning
        self._tasks = tasks
        self._profile_cache: dict[str, str] | None = None

    def invalidate_profile_cache(self) -> None:
        self._profile_cache = None

    def build(self, current_message: str, session_id: str) -> ConversationContext:
        profile = self._load_user_profile()

        # Get recent from current session
        recent = self._conversation.get_recent(session_id, limit=20)

        # If current session has few messages, supplement with cross-session history
        if len(recent) < 5:
            cross_session = self._load_cross_session_history(session_id, limit=20 - len(recent))
            recent = cross_session + recent

        relevant_facts = self._search_relevant_facts(current_message)
        relevant_knowledge = self._search_relevant_knowledge(current_message)
        procedures = self._search_procedures(current_message)
        pending = self._tasks.get_pending()
        projects = self._load_active_projects()
        last_summary = self._load_last_session_summary(session_id)
        ctx = ConversationContext(
            user_profile=profile, recent_messages=recent,
            relevant_facts=relevant_facts, relevant_knowledge=relevant_knowledge,
            pending_tasks=pending, active_projects=projects,
            last_session_summary=last_summary, session_id=session_id,
            current_message=current_message,
            procedures=procedures,
        )
        log.debug("context.built", session_id=session_id, recent_count=len(recent), facts_count=len(relevant_facts))
        return ctx

    def _load_user_profile(self) -> dict[str, str]:
        if self._profile_cache is not None:
            return self._profile_cache
        rows = self._engine.fetchall("SELECT key, value FROM user_profile ORDER BY key")
        self._profile_cache = {row[0]: row[1] for row in rows}
        return self._profile_cache

    def _search_relevant_facts(self, message: str, limit: int = 10) -> list[dict[str, Any]]:
        stripped = message.strip()
        if len(stripped) < 3:
            # For very short messages, return most-used facts as general context
            try:
                return self._learning.get_most_used_facts(limit=5)
            except Exception:
                return []
        try:
            return self._learning.search_facts(stripped, limit=limit)
        except Exception:
            return []

    def _search_relevant_knowledge(self, message: str, limit: int = 5) -> list[dict[str, Any]]:
        stripped = message.strip()
        if len(stripped) < 3:
            return []
        try:
            return self._learning.search_knowledge(stripped, limit=limit)
        except Exception:
            return []

    def _search_procedures(self, message: str, limit: int = 5) -> list[dict[str, Any]]:
        try:
            sql = "SELECT fact FROM learned_facts WHERE category = 'procedure' ORDER BY last_used DESC, id DESC LIMIT ?"
            return self._engine.fetchall_dicts(sql, (limit,))
        except Exception:
            return []

    def _load_active_projects(self) -> list[dict[str, Any]]:
        sql = "SELECT id, name, path, description, last_activity, status, notes FROM projects WHERE status = 'active' ORDER BY last_activity DESC"
        return self._engine.fetchall_dicts(sql)

    def _load_cross_session_history(self, exclude_session: str, limit: int = 15) -> list[dict[str, Any]]:
        sql = """
            SELECT id, timestamp, role, message, message_type, audio_duration_secs, channel
            FROM conversations
            WHERE session_id != ?
              AND timestamp >= datetime('now', '-7 days')
            ORDER BY id DESC
            LIMIT ?
        """
        rows = self._engine.fetchall_dicts(sql, (exclude_session, limit))
        rows.reverse()
        return rows

    def _load_last_session_summary(self, current_session_id: str) -> dict[str, Any] | None:
        sql = "SELECT id, session_id, started_at, ended_at, summary, topics, decisions, new_tasks, things_learned FROM session_summaries WHERE session_id != ? ORDER BY id DESC LIMIT 1"
        rows = self._engine.fetchall_dicts(sql, (current_session_id,))
        return rows[0] if rows else None
