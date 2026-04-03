"""Conversation context assembly from memory stores."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import structlog

from src.memory.conversation import ConversationStore
from src.memory.engine import MemoryEngine, sanitize_fts_query
from src.memory.learning import LearningStore
from src.memory.relationships import RelationshipTracker
from src.memory.tasks import TaskManager

log = structlog.get_logger("assistant.memory.context")

# Default token budget for the assembled context (1 token ≈ 4 chars)
_DEFAULT_MAX_CONTEXT_TOKENS = 4000
_CHARS_PER_TOKEN = 4


def _approx_tokens(text: str) -> int:
    """Rough token count approximation: 1 token per 4 characters."""
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _dict_to_str(d: dict[str, Any]) -> str:
    """Convert a dict to a flat string for token-budget estimation."""
    return " ".join(str(v) for v in d.values() if v is not None)


def _recency_factor(last_used_str: str | None, learned_at_str: str | None) -> float:
    """Compute a recency weight in range (0, 1].

    Formula: 1.0 / (1.0 + days_since_last_use * 0.1)

    Falls back to learned_at when last_used is absent.  If neither date
    parses, returns 0.5 as a neutral default.
    """
    date_str = last_used_str or learned_at_str
    if not date_str:
        return 0.5
    try:
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        days = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400)
        return 1.0 / (1.0 + days * 0.1)
    except (ValueError, TypeError):
        return 0.5


def _score_fact(row: dict[str, Any]) -> float:
    """Combined relevance score = confidence * recency_factor."""
    confidence = float(row.get("confidence", 1.0))
    rf = _recency_factor(row.get("last_used"), row.get("learned_at"))
    return confidence * rf


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
    execution_history: list[dict[str, Any]] = field(default_factory=list)
    error_patterns: list[dict[str, Any]] = field(default_factory=list)
    task_patterns: list[dict[str, Any]] = field(default_factory=list)
    execution_stats: dict[str, Any] = field(default_factory=dict)
    relationship_stage: str = "stranger"
    recent_mood: str = "neutral"
    metadata: dict[str, Any] = field(default_factory=dict)


class ContextBuilder:
    def __init__(
        self,
        engine: MemoryEngine,
        conversation: ConversationStore,
        learning: LearningStore,
        tasks: TaskManager,
        relationships: RelationshipTracker | None = None,
        max_context_tokens: int = _DEFAULT_MAX_CONTEXT_TOKENS,
    ) -> None:
        self._engine = engine
        self._conversation = conversation
        self._learning = learning
        self._tasks = tasks
        self._relationships = relationships
        self._profile_cache: dict[str, str] | None = None
        self._max_context_tokens = max_context_tokens

    def invalidate_profile_cache(self) -> None:
        self._profile_cache = None

    def build(
        self,
        current_message: str,
        session_id: str,
        task_type: str | None = None,
    ) -> ConversationContext:
        """Synchronous build — runs the async implementation in a new event loop."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Already inside an async context (e.g. called from a coroutine via
                # run_until_complete is invalid here) — fall back to sequential build.
                return self._build_sync(current_message, session_id, task_type)
        except RuntimeError:
            pass
        return asyncio.run(self._build_async(current_message, session_id, task_type))

    def _build_sync(
        self,
        current_message: str,
        session_id: str,
        task_type: str | None = None,
    ) -> ConversationContext:
        """Sequential fallback used when already inside a running event loop."""
        profile = self._load_user_profile()
        recent = self._conversation.get_recent(session_id, limit=20)
        if len(recent) < 5:
            cross = self._load_cross_session_history(session_id, limit=20 - len(recent))
            recent = cross + recent

        relevant_facts = self._search_relevant_facts(current_message)
        relevant_knowledge = self._search_relevant_knowledge(current_message)
        procedures = self._search_procedures(current_message)
        pending = self._tasks.get_pending()
        projects = self._load_active_projects()
        last_summary = self._load_last_session_summary(session_id)

        execution_history: list[dict[str, Any]] = []
        error_patterns: list[dict[str, Any]] = []
        best_patterns: list[dict[str, Any]] = []
        exec_stats: dict[str, Any] = {}

        if task_type:
            try:
                execution_history = self._learning.get_similar_executions(task_type, limit=5)
            except Exception:
                pass
            try:
                best_patterns = self._learning.get_best_patterns(task_type, limit=3)
            except Exception:
                pass
            try:
                exec_stats = self._learning.get_execution_stats(task_type)
            except Exception:
                pass

        try:
            error_patterns = self._learning.get_known_errors(limit=5)
        except Exception:
            pass

        rel_stage, rel_mood = self._load_relationship_context()
        return self._assemble(
            profile=profile, recent=recent, relevant_facts=relevant_facts,
            relevant_knowledge=relevant_knowledge, procedures=procedures,
            pending=pending, projects=projects, last_summary=last_summary,
            execution_history=execution_history, error_patterns=error_patterns,
            best_patterns=best_patterns, exec_stats=exec_stats,
            rel_stage=rel_stage, rel_mood=rel_mood,
            session_id=session_id, current_message=current_message,
        )

    async def _build_async(
        self,
        current_message: str,
        session_id: str,
        task_type: str | None = None,
    ) -> ConversationContext:
        """Parallelized build using asyncio.gather + asyncio.to_thread.

        Independent DB queries run concurrently.  Queries that depend on
        task_type are still gated but launched in a second gather batch so
        they do not serialize against the first batch.
        """
        # --- Batch 1: all queries independent of task_type ---
        (
            profile,
            relevant_facts,
            relevant_knowledge,
            procedures,
            pending,
            projects,
            last_summary,
            error_patterns_result,
        ) = await asyncio.gather(
            asyncio.to_thread(self._load_user_profile),
            asyncio.to_thread(self._search_relevant_facts, current_message),
            asyncio.to_thread(self._search_relevant_knowledge, current_message),
            asyncio.to_thread(self._search_procedures, current_message),
            asyncio.to_thread(self._tasks.get_pending),
            asyncio.to_thread(self._load_active_projects),
            asyncio.to_thread(self._load_last_session_summary, session_id),
            asyncio.to_thread(self._safe_get_known_errors),
            return_exceptions=False,
        )

        # Conversation history (separate because it may need a second DB call)
        recent: list[dict[str, Any]] = await asyncio.to_thread(
            self._conversation.get_recent, session_id, 20
        )
        if len(recent) < 5:
            cross = await asyncio.to_thread(
                self._load_cross_session_history, session_id, 20 - len(recent)
            )
            recent = cross + recent

        # --- Batch 2: task_type-gated queries (run in parallel when present) ---
        execution_history: list[dict[str, Any]] = []
        best_patterns: list[dict[str, Any]] = []
        exec_stats: dict[str, Any] = {}

        if task_type:
            exec_hist_result, best_pat_result, exec_stats_result = await asyncio.gather(
                asyncio.to_thread(self._safe_get_similar_executions, task_type),
                asyncio.to_thread(self._safe_get_best_patterns, task_type),
                asyncio.to_thread(self._safe_get_execution_stats, task_type),
                return_exceptions=False,
            )
            execution_history = exec_hist_result  # type: ignore[assignment]
            best_patterns = best_pat_result  # type: ignore[assignment]
            exec_stats = exec_stats_result  # type: ignore[assignment]

        # Relationship context
        rel_stage, rel_mood = await asyncio.to_thread(self._load_relationship_context)

        return self._assemble(
            profile=profile,  # type: ignore[arg-type]
            recent=recent,
            relevant_facts=relevant_facts,  # type: ignore[arg-type]
            relevant_knowledge=relevant_knowledge,  # type: ignore[arg-type]
            procedures=procedures,  # type: ignore[arg-type]
            pending=pending,  # type: ignore[arg-type]
            projects=projects,  # type: ignore[arg-type]
            last_summary=last_summary,  # type: ignore[arg-type]
            execution_history=execution_history,
            error_patterns=error_patterns_result,  # type: ignore[arg-type]
            best_patterns=best_patterns,
            exec_stats=exec_stats,
            rel_stage=rel_stage,
            rel_mood=rel_mood,
            session_id=session_id,
            current_message=current_message,
        )

    # ------------------------------------------------------------------ #
    # Assembly with token budgeting                                        #
    # ------------------------------------------------------------------ #

    def _assemble(
        self,
        *,
        profile: dict[str, str],
        recent: list[dict[str, Any]],
        relevant_facts: list[dict[str, Any]],
        relevant_knowledge: list[dict[str, Any]],
        procedures: list[dict[str, Any]],
        pending: list[dict[str, Any]],
        projects: list[dict[str, Any]],
        last_summary: dict[str, Any] | None,
        execution_history: list[dict[str, Any]],
        error_patterns: list[dict[str, Any]],
        best_patterns: list[dict[str, Any]],
        exec_stats: dict[str, Any],
        rel_stage: str,
        rel_mood: str,
        session_id: str,
        current_message: str,
    ) -> ConversationContext:
        """Apply recency-weighted sorting and token-budget trimming before building the context.

        Priority order when the budget runs out:
          1. Recent conversation (always kept in full — it is the most critical signal)
          2. High-confidence facts (sorted by confidence * recency_factor)
          3. Relevant knowledge (sorted by relevance_score * recency_factor)
          4. Everything else (procedures, tasks, projects, summaries, patterns)
        """
        budget_chars = self._max_context_tokens * _CHARS_PER_TOKEN
        used_chars = 0

        # Always include the current message in the budget estimate
        used_chars += len(current_message)

        # --- Recent conversation: include all, count toward budget ---
        for msg in recent:
            used_chars += _approx_tokens(_dict_to_str(msg)) * _CHARS_PER_TOKEN

        # --- Facts: sort by recency-weighted score, then trim to budget ---
        sorted_facts = sorted(relevant_facts, key=_score_fact, reverse=True)
        trimmed_facts: list[dict[str, Any]] = []
        for fact in sorted_facts:
            cost = _approx_tokens(_dict_to_str(fact)) * _CHARS_PER_TOKEN
            if used_chars + cost > budget_chars:
                break
            trimmed_facts.append(fact)
            used_chars += cost

        # --- Knowledge: sort by relevance_score * recency_factor, then trim ---
        def _score_knowledge(row: dict[str, Any]) -> float:
            base = float(row.get("relevance_score", 1.0))
            rf = _recency_factor(row.get("last_used"), row.get("learned_at"))
            return base * rf

        sorted_knowledge = sorted(relevant_knowledge, key=_score_knowledge, reverse=True)
        trimmed_knowledge: list[dict[str, Any]] = []
        for kn in sorted_knowledge:
            cost = _approx_tokens(_dict_to_str(kn)) * _CHARS_PER_TOKEN
            if used_chars + cost > budget_chars:
                break
            trimmed_knowledge.append(kn)
            used_chars += cost

        # --- Remaining items: include until budget runs out ---
        trimmed_procedures = _trim_to_budget(procedures, budget_chars, used_chars)
        used_chars += sum(
            _approx_tokens(_dict_to_str(p)) * _CHARS_PER_TOKEN for p in trimmed_procedures
        )

        ctx = ConversationContext(
            user_profile=profile,
            recent_messages=recent,
            relevant_facts=trimmed_facts,
            relevant_knowledge=trimmed_knowledge,
            pending_tasks=pending,
            active_projects=projects,
            last_session_summary=last_summary,
            session_id=session_id,
            current_message=current_message,
            procedures=trimmed_procedures,
            execution_history=execution_history,
            error_patterns=error_patterns,
            task_patterns=best_patterns,
            execution_stats=exec_stats,
            relationship_stage=rel_stage,
            recent_mood=rel_mood,
        )
        log.debug(
            "context.built",
            session_id=session_id,
            recent_count=len(recent),
            facts_count=len(trimmed_facts),
            knowledge_count=len(trimmed_knowledge),
            procedures_count=len(trimmed_procedures),
            exec_history=len(execution_history),
            approx_chars_used=used_chars,
            budget_chars=budget_chars,
        )
        return ctx

    # ------------------------------------------------------------------ #
    # Safe wrappers for gather (return empty lists/dicts on failure)       #
    # ------------------------------------------------------------------ #

    def _safe_get_known_errors(self) -> list[dict[str, Any]]:
        try:
            return self._learning.get_known_errors(limit=5)
        except Exception:
            return []

    def _safe_get_similar_executions(self, task_type: str) -> list[dict[str, Any]]:
        try:
            return self._learning.get_similar_executions(task_type, limit=5)
        except Exception:
            return []

    def _safe_get_best_patterns(self, task_type: str) -> list[dict[str, Any]]:
        try:
            return self._learning.get_best_patterns(task_type, limit=3)
        except Exception:
            return []

    def _safe_get_execution_stats(self, task_type: str) -> dict[str, Any]:
        try:
            return self._learning.get_execution_stats(task_type)
        except Exception:
            return {}

    # ------------------------------------------------------------------ #
    # Private DB helpers                                                   #
    # ------------------------------------------------------------------ #

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
        """Search procedures by relevance to message, falling back to most recent."""
        try:
            stripped = message.strip()
            if len(stripped) >= 3:
                safe_query = sanitize_fts_query(stripped)
                if safe_query:
                    results = self._engine.fetchall_dicts(
                        "SELECT f.id, f.fact, f.confidence, f.use_count "
                        "FROM facts_fts fts JOIN learned_facts f ON f.id = fts.rowid "
                        "WHERE facts_fts MATCH ? AND f.category = 'procedure' "
                        "AND f.superseded_by IS NULL "
                        "ORDER BY rank LIMIT ?",
                        (safe_query, limit),
                    )
                    if results:
                        return results

            # Fallback: most recent/used procedures
            sql = (
                "SELECT id, fact, confidence, use_count FROM learned_facts "
                "WHERE category = 'procedure' AND superseded_by IS NULL "
                "ORDER BY use_count DESC, id DESC LIMIT ?"
            )
            return self._engine.fetchall_dicts(sql, (limit,))
        except Exception:
            return []

    def _load_active_projects(self) -> list[dict[str, Any]]:
        sql = (
            "SELECT id, name, path, description, last_activity, status, notes "
            "FROM projects WHERE status = 'active' ORDER BY last_activity DESC"
        )
        return self._engine.fetchall_dicts(sql)

    def _load_cross_session_history(
        self, exclude_session: str, limit: int = 15
    ) -> list[dict[str, Any]]:
        sql = """
            SELECT id, timestamp, role, message, message_type, audio_duration_secs, channel
            FROM conversations
            WHERE session_id != ?
              AND timestamp >= datetime('now', '-365 days')
            ORDER BY id DESC
            LIMIT ?
        """
        rows = self._engine.fetchall_dicts(sql, (exclude_session, limit))
        rows.reverse()
        return rows

    def _load_last_session_summary(self, current_session_id: str) -> dict[str, Any] | None:
        sql = (
            "SELECT id, session_id, started_at, ended_at, summary, topics, decisions, "
            "new_tasks, things_learned FROM session_summaries "
            "WHERE session_id != ? ORDER BY id DESC LIMIT 1"
        )
        rows = self._engine.fetchall_dicts(sql, (current_session_id,))
        return rows[0] if rows else None

    def _load_relationship_context(self) -> tuple[str, str]:
        """Return (relationship_stage, recent_mood) — safe to call in a thread."""
        rel_stage = "stranger"
        rel_mood = "neutral"
        if self._relationships:
            try:
                rel_stage = self._relationships.get_relationship_stage()
            except Exception:
                pass
            try:
                rel_mood = self._relationships.get_recent_mood(last_n=5)
            except Exception:
                pass
        return rel_stage, rel_mood


# ------------------------------------------------------------------ #
# Utilities                                                            #
# ------------------------------------------------------------------ #

def _trim_to_budget(
    items: list[dict[str, Any]],
    budget_chars: int,
    used_chars: int,
) -> list[dict[str, Any]]:
    """Include items from the list until the char budget is exhausted."""
    result: list[dict[str, Any]] = []
    for item in items:
        cost = _approx_tokens(_dict_to_str(item)) * _CHARS_PER_TOKEN
        if used_chars + cost > budget_chars:
            break
        result.append(item)
        used_chars += cost
    return result
