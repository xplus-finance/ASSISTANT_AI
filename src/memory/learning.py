"""Learned facts, knowledge persistence, and auto-learning stores."""

from __future__ import annotations

import re
import string
from datetime import datetime, timezone
from typing import Any

import structlog

from src.memory.engine import MemoryEngine, sanitize_fts_query

log = structlog.get_logger("assistant.memory.learning")

_VALID_CATEGORIES = {"user", "project", "preference", "technical", "world", "procedure"}

# Valid source labels for learned_facts.source
_VALID_SOURCES = {"conversation", "web_search", "user_correction", "system"}

# Punctuation stripper for deduplication normalization
_PUNCT_TABLE = str.maketrans("", "", string.punctuation)


def _normalize_text(text: str) -> str:
    """Lowercase and strip punctuation for fuzzy comparison."""
    return text.lower().translate(_PUNCT_TABLE).strip()


class LearningStore:
    def __init__(self, engine: MemoryEngine) -> None:
        self._engine = engine

    # ------------------------------------------------------------------ #
    # Facts                                                                #
    # ------------------------------------------------------------------ #

    def add_fact(
        self,
        category: str,
        fact: str,
        source: str | None = None,
        confidence: float = 1.0,
    ) -> int:
        if category not in _VALID_CATEGORIES:
            raise ValueError(f"Invalid category: {category!r}")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"Confidence must be between 0 and 1, got {confidence}")
        # Normalize source; default to "conversation" when absent or unknown
        if source not in _VALID_SOURCES:
            source = "conversation"
        sql = (
            "INSERT INTO learned_facts (category, fact, source, confidence) "
            "VALUES (?, ?, ?, ?)"
        )
        fact_id = self._engine.insert_returning_id(sql, (category, fact, source, confidence))
        log.debug("learning.fact_added", fact_id=fact_id, category=category, source=source)
        return fact_id

    def add_fact_deduplicated(
        self,
        category: str,
        fact: str,
        source: str | None = None,
        confidence: float = 1.0,
    ) -> int:
        """Add a fact, but if a very similar one exists, reinforce it instead.

        Deduplication uses Jaccard similarity on normalized tokens with a
        threshold of 0.7 (raised from the previous 0.6 to reduce false
        positives).  When a duplicate is found the stored fact keeps the
        highest confidence and its use_count is incremented.
        """
        if category not in _VALID_CATEGORIES:
            category = "technical"
        confidence = max(0.0, min(1.0, confidence))
        if source not in _VALID_SOURCES:
            source = "conversation"

        normalized_new = _normalize_text(fact)
        new_words = set(normalized_new.split())

        safe_query = sanitize_fts_query(fact)
        if safe_query:
            existing = self._engine.fetchall_dicts(
                "SELECT f.id, f.fact, f.confidence, f.use_count "
                "FROM facts_fts fts JOIN learned_facts f ON f.id = fts.rowid "
                "WHERE facts_fts MATCH ? AND f.category = ? AND f.superseded_by IS NULL "
                "ORDER BY rank LIMIT 5",
                (safe_query, category),
            )
            for row in existing:
                existing_words = set(_normalize_text(row["fact"]).split())
                if not existing_words or not new_words:
                    continue
                # Jaccard similarity
                overlap = len(existing_words & new_words) / len(existing_words | new_words)
                if overlap >= 0.7:
                    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                    # Keep the higher confidence, but cap at 1.0
                    new_confidence = min(1.0, max(row["confidence"], confidence) + 0.05)
                    self._engine.execute(
                        "UPDATE learned_facts "
                        "SET use_count = use_count + 1, last_used = ?, confidence = ? "
                        "WHERE id = ?",
                        (now, new_confidence, row["id"]),
                    )
                    log.debug(
                        "learning.fact_reinforced",
                        fact_id=row["id"],
                        confidence=new_confidence,
                        jaccard=round(overlap, 2),
                    )
                    return row["id"]

        return self.add_fact(category, fact, source, confidence)

    def search_facts(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        safe_query = sanitize_fts_query(query)
        if not safe_query:
            return []
        sql = (
            "SELECT f.id, f.category, f.fact, f.confidence, f.source, "
            "f.learned_at, f.last_used, f.use_count, rank "
            "FROM facts_fts fts JOIN learned_facts f ON f.id = fts.rowid "
            "WHERE facts_fts MATCH ? AND f.superseded_by IS NULL "
            "ORDER BY rank LIMIT ?"
        )
        return self._engine.fetchall_dicts(sql, (safe_query, limit))

    def get_facts_by_category(self, category: str) -> list[dict[str, Any]]:
        sql = (
            "SELECT id, category, fact, confidence, source, learned_at, last_used, use_count "
            "FROM learned_facts WHERE category = ? AND superseded_by IS NULL "
            "ORDER BY confidence DESC, learned_at DESC"
        )
        return self._engine.fetchall_dicts(sql, (category,))

    def update_fact_usage(self, fact_id: int) -> None:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        sql = "UPDATE learned_facts SET use_count = use_count + 1, last_used = ? WHERE id = ?"
        self._engine.execute(sql, (now, fact_id))

    def get_most_used_facts(self, limit: int = 20) -> list[dict[str, Any]]:
        sql = (
            "SELECT id, category, fact, confidence, use_count, last_used "
            "FROM learned_facts "
            "WHERE use_count > 0 AND superseded_by IS NULL "
            "ORDER BY use_count DESC LIMIT ?"
        )
        return self._engine.fetchall_dicts(sql, (limit,))

    # ------------------------------------------------------------------ #
    # Confidence decay                                                     #
    # ------------------------------------------------------------------ #

    def decay_unused_facts(self, days_threshold: int = 30, decay_factor: float = 0.9) -> int:
        """Reduce confidence of facts not accessed in the last ``days_threshold`` days.

        Formula: new_confidence = confidence * decay_factor
        Applies once per decay cycle. Facts already below 0.05 are left alone
        to avoid permanently zeroing out long-term but low-traffic knowledge.

        Returns the number of rows updated.
        """
        cutoff = f"datetime('now', '-{int(days_threshold)} days')"
        # Build the SQL using the computed cutoff expression — safe because
        # days_threshold is cast to int above (no user-controlled string).
        sql = f"""
            UPDATE learned_facts
            SET confidence = ROUND(confidence * ?, 4)
            WHERE superseded_by IS NULL
              AND confidence > 0.05
              AND (
                  last_used IS NULL AND learned_at < {cutoff}
                  OR last_used < {cutoff}
              )
        """
        self._engine.execute(sql, (decay_factor,))
        # APSW does not expose rowcount via the cursor directly; fetch count separately.
        row = self._engine.fetchone(
            f"""
            SELECT COUNT(*) FROM learned_facts
            WHERE superseded_by IS NULL
              AND confidence > 0.05
              AND (
                  last_used IS NULL AND learned_at < {cutoff}
                  OR last_used < {cutoff}
              )
            """
        )
        # The count above is what would have been updated on the NEXT run;
        # use changes() pragma instead for an accurate count of what was just updated.
        changes_row = self._engine.fetchone("SELECT changes()")
        updated = changes_row[0] if changes_row else 0
        log.info(
            "learning.decay_applied",
            updated=updated,
            days_threshold=days_threshold,
            decay_factor=decay_factor,
        )
        return updated

    # ------------------------------------------------------------------ #
    # User corrections                                                     #
    # ------------------------------------------------------------------ #

    def process_correction(self, original_fact_id: int, corrected_text: str) -> int:
        """Record a user correction for a stored fact.

        Marks ``original_fact_id`` as superseded and inserts a new fact that
        carries the corrected text.  The two rows are linked via the
        ``superseded_by`` column on the old row.

        Returns the id of the newly created corrected fact.
        """
        # Load the original to inherit its category
        row = self._engine.fetchone(
            "SELECT id, category, confidence FROM learned_facts WHERE id = ?",
            (original_fact_id,),
        )
        if not row:
            raise ValueError(f"No fact found with id={original_fact_id}")

        _orig_id, category, old_confidence = row

        # Insert corrected fact — inherit confidence so it starts trusted
        new_id = self.add_fact(
            category=category,
            fact=corrected_text,
            source="user_correction",
            confidence=min(1.0, old_confidence + 0.1),
        )

        # Mark original as superseded
        self._engine.execute(
            "UPDATE learned_facts SET superseded_by = ? WHERE id = ?",
            (new_id, original_fact_id),
        )

        log.info(
            "learning.correction_processed",
            original_id=original_fact_id,
            new_id=new_id,
            category=category,
        )
        return new_id

    # ------------------------------------------------------------------ #
    # Knowledge                                                            #
    # ------------------------------------------------------------------ #

    def add_knowledge(
        self,
        topic: str,
        content: str,
        source_url: str | None = None,
    ) -> int:
        sql = "INSERT INTO knowledge (topic, content, source_url) VALUES (?, ?, ?)"
        kid = self._engine.insert_returning_id(sql, (topic, content, source_url))
        log.debug("learning.knowledge_added", knowledge_id=kid, topic=topic)
        return kid

    def search_knowledge(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        safe_query = sanitize_fts_query(query)
        if not safe_query:
            return []
        sql = (
            "SELECT k.id, k.topic, k.content, k.source_url, k.learned_at, "
            "k.relevance_score, rank "
            "FROM knowledge_fts kf JOIN knowledge k ON k.id = kf.rowid "
            "WHERE knowledge_fts MATCH ? ORDER BY rank LIMIT ?"
        )
        return self._engine.fetchall_dicts(sql, (safe_query, limit))

    def get_knowledge_by_topic(self, topic: str) -> list[dict[str, Any]]:
        sql = (
            "SELECT id, topic, content, source_url, learned_at, relevance_score "
            "FROM knowledge WHERE topic = ? ORDER BY relevance_score DESC"
        )
        return self._engine.fetchall_dicts(sql, (topic,))

    # ------------------------------------------------------------------ #
    # Execution Log                                                        #
    # ------------------------------------------------------------------ #

    def log_execution(
        self,
        task_type: str,
        task_summary: str,
        *,
        method_used: str | None = None,
        success: bool = True,
        duration_secs: float | None = None,
        error_message: str | None = None,
        resolution: str | None = None,
        session_id: str | None = None,
        message_count: int = 1,
    ) -> int:
        sql = """
            INSERT INTO execution_log
            (task_type, task_summary, method_used, success, duration_secs,
             error_message, resolution, session_id, message_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        row_id = self._engine.insert_returning_id(sql, (
            task_type, task_summary[:500], method_used, int(success),
            duration_secs, error_message, resolution, session_id, message_count,
        ))
        log.debug("learning.execution_logged", row_id=row_id, task_type=task_type, success=success)
        return row_id

    def get_similar_executions(self, task_type: str, limit: int = 5) -> list[dict[str, Any]]:
        sql = """
            SELECT id, timestamp, task_type, task_summary, method_used,
                   success, duration_secs, error_message, resolution
            FROM execution_log
            WHERE task_type = ?
            ORDER BY id DESC
            LIMIT ?
        """
        return self._engine.fetchall_dicts(sql, (task_type, limit))

    def get_execution_stats(self, task_type: str) -> dict[str, Any]:
        row = self._engine.fetchone(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes, "
            "AVG(CASE WHEN success = 1 THEN duration_secs END) as avg_duration "
            "FROM execution_log WHERE task_type = ?",
            (task_type,),
        )
        if not row or not row[0]:
            return {"total": 0, "successes": 0, "success_rate": 0.0, "avg_duration": 0.0}
        total, successes, avg_dur = row
        return {
            "total": total,
            "successes": successes,
            "success_rate": (successes / total * 100) if total else 0.0,
            "avg_duration": round(avg_dur or 0, 1),
        }

    # ------------------------------------------------------------------ #
    # Task Patterns                                                        #
    # ------------------------------------------------------------------ #

    def upsert_task_pattern(
        self,
        task_type: str,
        pattern_key: str,
        method: str,
        duration_secs: float | None = None,
        success: bool = True,
        tip: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        existing = self._engine.fetchone(
            "SELECT id, best_method, avg_duration_secs, success_count, fail_count, tips "
            "FROM task_patterns WHERE task_type = ? AND pattern_key = ?",
            (task_type, pattern_key),
        )
        if existing:
            pat_id, old_method, old_avg, s_count, f_count, old_tips = existing
            if success:
                new_s = s_count + 1
                new_f = f_count
                if duration_secs and old_avg:
                    new_avg = (old_avg * s_count + duration_secs) / new_s
                else:
                    new_avg = duration_secs or old_avg
                new_method = method if (new_s > s_count) else old_method
            else:
                new_s = s_count
                new_f = f_count + 1
                new_avg = old_avg
                new_method = old_method

            new_tips = old_tips or ""
            if tip and tip not in (new_tips or ""):
                new_tips = f"{new_tips}\n{tip}".strip() if new_tips else tip

            self._engine.execute(
                "UPDATE task_patterns SET best_method = ?, avg_duration_secs = ?, "
                "success_count = ?, fail_count = ?, last_used = ?, tips = ? WHERE id = ?",
                (new_method, new_avg, new_s, new_f, now, new_tips, pat_id),
            )
        else:
            self._engine.execute(
                "INSERT INTO task_patterns (task_type, pattern_key, best_method, "
                "avg_duration_secs, success_count, fail_count, last_used, tips) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (task_type, pattern_key, method, duration_secs,
                 1 if success else 0, 0 if success else 1, now, tip),
            )

    def get_best_patterns(self, task_type: str, limit: int = 3) -> list[dict[str, Any]]:
        sql = """
            SELECT task_type, pattern_key, best_method, avg_duration_secs,
                   success_count, fail_count, tips, last_used
            FROM task_patterns
            WHERE task_type = ?
            ORDER BY success_count DESC, last_used DESC
            LIMIT ?
        """
        return self._engine.fetchall_dicts(sql, (task_type, limit))

    # ------------------------------------------------------------------ #
    # Error Solutions                                                      #
    # ------------------------------------------------------------------ #

    def log_error_solution(
        self,
        error_pattern: str,
        solution: str,
        context: str | None = None,
    ) -> None:
        existing = self._engine.fetchone(
            "SELECT id, occurrences FROM error_solutions WHERE error_pattern = ?",
            (error_pattern,),
        )
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        if existing:
            self._engine.execute(
                "UPDATE error_solutions SET occurrences = occurrences + 1, "
                "last_seen = ?, solution = ? WHERE id = ?",
                (now, solution, existing[0]),
            )
        else:
            self._engine.execute(
                "INSERT INTO error_solutions (error_pattern, solution, context, last_seen) "
                "VALUES (?, ?, ?, ?)",
                (error_pattern, solution, context, now),
            )

    def close_error_solution(self, error_pattern: str, actual_solution: str) -> None:
        """Close the cycle: update a pending error with the real solution that worked."""
        existing = self._engine.fetchone(
            "SELECT id, times_applied, times_resolved FROM error_solutions "
            "WHERE error_pattern = ?",
            (error_pattern,),
        )
        if not existing:
            return
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        new_resolved = (existing[2] or 0) + 1
        new_applied = max((existing[1] or 0), new_resolved)
        effectiveness = new_resolved / new_applied if new_applied > 0 else 0.0
        self._engine.execute(
            "UPDATE error_solutions SET solution = ?, times_resolved = ?, "
            "times_applied = ?, effectiveness = ?, last_seen = ? WHERE id = ?",
            (actual_solution, new_resolved, new_applied, round(effectiveness, 2), now, existing[0]),
        )
        log.debug(
            "learning.error_solution_closed",
            error_pattern=error_pattern[:60],
            effectiveness=effectiveness,
        )

    def track_error_applied(self, error_pattern: str) -> None:
        """Track that a known solution was applied (regardless of outcome)."""
        self._engine.execute(
            "UPDATE error_solutions "
            "SET times_applied = COALESCE(times_applied, 0) + 1 "
            "WHERE error_pattern = ?",
            (error_pattern,),
        )

    def get_known_errors(self, limit: int = 10) -> list[dict[str, Any]]:
        sql = """
            SELECT error_pattern, solution, context, occurrences, effectiveness
            FROM error_solutions
            ORDER BY occurrences DESC, effectiveness DESC
            LIMIT ?
        """
        return self._engine.fetchall_dicts(sql, (limit,))

    def search_error_solutions(self, error_text: str, limit: int = 3) -> list[dict[str, Any]]:
        """Search error solutions using FTS5 with LIKE fallback."""
        safe_query = sanitize_fts_query(error_text[:150])
        if safe_query:
            try:
                results = self._engine.fetchall_dicts(
                    "SELECT es.error_pattern, es.solution, es.context, "
                    "es.occurrences, es.effectiveness "
                    "FROM error_solutions_fts fts "
                    "JOIN error_solutions es ON es.id = fts.rowid "
                    "WHERE error_solutions_fts MATCH ? ORDER BY rank LIMIT ?",
                    (safe_query, limit),
                )
                if results:
                    return results
            except Exception:
                pass  # FTS table may not exist on older DBs; fall through to LIKE
        # Fallback: LIKE search
        sql = """
            SELECT error_pattern, solution, context, occurrences, effectiveness
            FROM error_solutions
            WHERE error_pattern LIKE ? OR ? LIKE '%' || error_pattern || '%'
            ORDER BY occurrences DESC
            LIMIT ?
        """
        pattern = f"%{error_text[:100]}%"
        return self._engine.fetchall_dicts(sql, (pattern, error_text[:200], limit))
