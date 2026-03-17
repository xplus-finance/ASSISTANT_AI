"""
Context builder for conversations.

Aggregates data from all memory sub-systems into a single
``ConversationContext`` object that the LLM orchestrator can
inject into its system prompt.
"""

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
    """Immutable snapshot of everything the assistant needs to answer."""

    # User identity
    user_profile: dict[str, str]

    # Recent conversation history (oldest first)
    recent_messages: list[dict[str, Any]]

    # Facts relevant to the current message
    relevant_facts: list[dict[str, Any]]

    # Relevant knowledge articles
    relevant_knowledge: list[dict[str, Any]]

    # Open tasks
    pending_tasks: list[dict[str, Any]]

    # Active projects
    active_projects: list[dict[str, Any]]

    # Summary of the last completed session
    last_session_summary: dict[str, Any] | None

    # Current session id
    session_id: str

    # Raw current message (for reference)
    current_message: str

    # Extra metadata the caller may attach
    metadata: dict[str, Any] = field(default_factory=dict)


class ContextBuilder:
    """
    Build a ``ConversationContext`` by querying every memory sub-system.

    Designed to be called once per incoming message before the LLM generates
    a response.
    """

    def __init__(
        self,
        engine: MemoryEngine,
        conversation: ConversationStore,
        learning: LearningStore,
        tasks: TaskManager,
    ) -> None:
        self._engine = engine
        self._conversation = conversation
        self._learning = learning
        self._tasks = tasks

    def build(self, current_message: str, session_id: str) -> ConversationContext:
        """
        Assemble the full context for a single turn.

        Steps:
            1. Load user profile key/value pairs.
            2. Fetch the last 20 messages in this session.
            3. Search for facts relevant to the current message.
            4. Search for knowledge relevant to the current message.
            5. List pending tasks.
            6. List active projects.
            7. Retrieve the most recent session summary.

        Args:
            current_message: The user's latest message text.
            session_id: Current session identifier.

        Returns:
            A fully-populated ``ConversationContext``.
        """
        # 1. User profile
        profile = self._load_user_profile()

        # 2. Recent messages
        recent = self._conversation.get_recent(session_id, limit=20)

        # 3. Relevant facts (FTS search on current message)
        relevant_facts = self._search_relevant_facts(current_message)

        # 4. Relevant knowledge
        relevant_knowledge = self._search_relevant_knowledge(current_message)

        # 5. Pending tasks
        pending = self._tasks.get_pending()

        # 6. Active projects
        projects = self._load_active_projects()

        # 7. Last session summary
        last_summary = self._load_last_session_summary(session_id)

        ctx = ConversationContext(
            user_profile=profile,
            recent_messages=recent,
            relevant_facts=relevant_facts,
            relevant_knowledge=relevant_knowledge,
            pending_tasks=pending,
            active_projects=projects,
            last_session_summary=last_summary,
            session_id=session_id,
            current_message=current_message,
        )

        log.debug(
            "context.built",
            session_id=session_id,
            recent_count=len(recent),
            facts_count=len(relevant_facts),
            knowledge_count=len(relevant_knowledge),
            pending_tasks=len(pending),
            projects_count=len(projects),
        )
        return ctx

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_user_profile(self) -> dict[str, str]:
        """Load all user profile entries as a flat dict."""
        rows = self._engine.fetchall(
            "SELECT key, value FROM user_profile ORDER BY key"
        )
        return {row[0]: row[1] for row in rows}

    def _search_relevant_facts(self, message: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search facts related to the current message via FTS5.

        If the message is too short or FTS raises an error (e.g. no
        indexed content yet), returns an empty list gracefully.
        """
        if len(message.strip()) < 3:
            return []
        try:
            return self._learning.search_facts(message, limit=limit)
        except Exception:
            # FTS can fail on empty tables or unusual query strings
            log.debug("context.facts_search_failed", message=message[:80], exc_info=True)
            return []

    def _search_relevant_knowledge(self, message: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search knowledge related to the current message via FTS5."""
        if len(message.strip()) < 3:
            return []
        try:
            return self._learning.search_knowledge(message, limit=limit)
        except Exception:
            log.debug("context.knowledge_search_failed", message=message[:80], exc_info=True)
            return []

    def _load_active_projects(self) -> list[dict[str, Any]]:
        """Return all projects with status 'active'."""
        sql = """
            SELECT id, name, path, description, last_activity, status, notes
            FROM projects
            WHERE status = 'active'
            ORDER BY last_activity DESC
        """
        return self._engine.fetchall_dicts(sql)

    def _load_last_session_summary(self, current_session_id: str) -> dict[str, Any] | None:
        """
        Fetch the most recent session summary that is NOT the current session.

        This gives the assistant continuity between sessions.
        """
        sql = """
            SELECT id, session_id, started_at, ended_at, summary,
                   topics, decisions, new_tasks, things_learned
            FROM session_summaries
            WHERE session_id != ?
            ORDER BY id DESC
            LIMIT 1
        """
        rows = self._engine.fetchall_dicts(sql, (current_session_id,))
        return rows[0] if rows else None
