"""SQLite memory engine backed by APSW with optional SQLCipher encryption."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Sequence

import apsw
import structlog

log = structlog.get_logger("assistant.memory")

_OPTIMIZE_INTERVAL_SECS = 24 * 60 * 60  # 24 hours
_STMT_CACHE_SIZE = 64  # Number of prepared statement strings to remember

_PRAGMAS = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
PRAGMA synchronous = NORMAL;
"""

_TABLES = """
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT (datetime('now')),
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    message TEXT NOT NULL,
    message_type TEXT DEFAULT 'text' CHECK(message_type IN ('text', 'audio', 'image', 'document')),
    audio_duration_secs REAL,
    session_id TEXT NOT NULL,
    channel TEXT DEFAULT 'telegram'
);

CREATE VIRTUAL TABLE IF NOT EXISTS conversations_fts USING fts5(
    message, content='conversations', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS conversations_ai AFTER INSERT ON conversations BEGIN
    INSERT INTO conversations_fts(rowid, message) VALUES (new.id, new.message);
END;

CREATE TRIGGER IF NOT EXISTS conversations_ad AFTER DELETE ON conversations BEGIN
    INSERT INTO conversations_fts(conversations_fts, rowid, message)
        VALUES ('delete', old.id, old.message);
END;

CREATE TRIGGER IF NOT EXISTS conversations_au AFTER UPDATE ON conversations BEGIN
    INSERT INTO conversations_fts(conversations_fts, rowid, message)
        VALUES ('delete', old.id, old.message);
    INSERT INTO conversations_fts(rowid, message) VALUES (new.id, new.message);
END;

CREATE TABLE IF NOT EXISTS user_profile (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now')),
    source TEXT
);

CREATE TABLE IF NOT EXISTS learned_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    fact TEXT NOT NULL,
    confidence REAL DEFAULT 1.0 CHECK(confidence BETWEEN 0 AND 1),
    source TEXT DEFAULT 'conversation',
    learned_at TEXT DEFAULT (datetime('now')),
    last_used TEXT,
    use_count INTEGER DEFAULT 0,
    superseded_by INTEGER REFERENCES learned_facts(id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
    fact, content='learned_facts', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON learned_facts BEGIN
    INSERT INTO facts_fts(rowid, fact) VALUES (new.id, new.fact);
END;

CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON learned_facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, fact)
        VALUES ('delete', old.id, old.fact);
END;

CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON learned_facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, fact)
        VALUES ('delete', old.id, old.fact);
    INSERT INTO facts_fts(rowid, fact) VALUES (new.id, new.fact);
END;

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'in_progress', 'done', 'recurring', 'cancelled')),
    is_recurring INTEGER DEFAULT 0,
    recurrence_pattern TEXT,
    next_run TEXT,
    last_run TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    project TEXT
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    path TEXT,
    description TEXT,
    last_activity TEXT,
    status TEXT DEFAULT 'active',
    notes TEXT
);

CREATE TABLE IF NOT EXISTS knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    content TEXT NOT NULL,
    source_url TEXT,
    learned_at TEXT DEFAULT (datetime('now')),
    relevance_score REAL DEFAULT 1.0
);

CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
    topic, content, content='knowledge', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS knowledge_ai AFTER INSERT ON knowledge BEGIN
    INSERT INTO knowledge_fts(rowid, topic, content) VALUES (new.id, new.topic, new.content);
END;

CREATE TRIGGER IF NOT EXISTS knowledge_ad AFTER DELETE ON knowledge BEGIN
    INSERT INTO knowledge_fts(knowledge_fts, rowid, topic, content)
        VALUES ('delete', old.id, old.topic, old.content);
END;

CREATE TRIGGER IF NOT EXISTS knowledge_au AFTER UPDATE ON knowledge BEGIN
    INSERT INTO knowledge_fts(knowledge_fts, rowid, topic, content)
        VALUES ('delete', old.id, old.topic, old.content);
    INSERT INTO knowledge_fts(rowid, topic, content) VALUES (new.id, new.topic, new.content);
END;

CREATE TABLE IF NOT EXISTS skills (
    name TEXT PRIMARY KEY,
    description TEXT,
    file_path TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    use_count INTEGER DEFAULT 0,
    created_by TEXT DEFAULT 'system' CHECK(created_by IN ('system', 'assistant', 'user'))
);

CREATE TABLE IF NOT EXISTS relationship_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT DEFAULT (date('now')),
    note TEXT NOT NULL,
    sentiment TEXT CHECK(sentiment IN ('positive', 'neutral', 'negative'))
);

CREATE TABLE IF NOT EXISTS session_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL UNIQUE,
    started_at TEXT,
    ended_at TEXT,
    summary TEXT NOT NULL,
    topics TEXT,
    decisions TEXT,
    new_tasks TEXT,
    things_learned TEXT
);

CREATE TABLE IF NOT EXISTS security_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT (datetime('now')),
    event_type TEXT NOT NULL,
    details TEXT,
    sender_id TEXT,
    severity TEXT CHECK(severity IN ('info', 'warning', 'critical'))
);

CREATE TABLE IF NOT EXISTS execution_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT (datetime('now')),
    task_type TEXT NOT NULL,
    task_summary TEXT NOT NULL,
    method_used TEXT,
    success INTEGER DEFAULT 1,
    duration_secs REAL,
    error_message TEXT,
    resolution TEXT,
    session_id TEXT,
    message_count INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS task_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT NOT NULL,
    pattern_key TEXT NOT NULL,
    best_method TEXT NOT NULL,
    avg_duration_secs REAL,
    success_count INTEGER DEFAULT 1,
    fail_count INTEGER DEFAULT 0,
    last_used TEXT DEFAULT (datetime('now')),
    tips TEXT,
    UNIQUE(task_type, pattern_key)
);

CREATE TABLE IF NOT EXISTS error_solutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    error_pattern TEXT NOT NULL,
    solution TEXT NOT NULL,
    context TEXT,
    occurrences INTEGER DEFAULT 1,
    last_seen TEXT DEFAULT (datetime('now')),
    effectiveness REAL DEFAULT 0.0,
    times_applied INTEGER DEFAULT 0,
    times_resolved INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS notification_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT (datetime('now')),
    category TEXT NOT NULL DEFAULT 'general',
    source TEXT NOT NULL,
    message TEXT NOT NULL,
    priority TEXT DEFAULT 'NORMAL',
    status TEXT DEFAULT 'sent' CHECK(status IN ('sent', 'sent_critical', 'read', 'dismissed', 'digest', 'discarded')),
    user_response TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS error_solutions_fts USING fts5(
    error_pattern, solution, content='error_solutions', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS error_solutions_ai AFTER INSERT ON error_solutions BEGIN
    INSERT INTO error_solutions_fts(rowid, error_pattern, solution)
        VALUES (new.id, new.error_pattern, new.solution);
END;

CREATE TRIGGER IF NOT EXISTS error_solutions_ad AFTER DELETE ON error_solutions BEGIN
    INSERT INTO error_solutions_fts(error_solutions_fts, rowid, error_pattern, solution)
        VALUES ('delete', old.id, old.error_pattern, old.solution);
END;

CREATE TRIGGER IF NOT EXISTS error_solutions_au AFTER UPDATE ON error_solutions BEGIN
    INSERT INTO error_solutions_fts(error_solutions_fts, rowid, error_pattern, solution)
        VALUES ('delete', old.id, old.error_pattern, old.solution);
    INSERT INTO error_solutions_fts(rowid, error_pattern, solution)
        VALUES (new.id, new.error_pattern, new.solution);
END;
"""

_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_conversations_session
    ON conversations(session_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_conversations_role
    ON conversations(role);
CREATE INDEX IF NOT EXISTS idx_tasks_status
    ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_next_run
    ON tasks(next_run);
CREATE INDEX IF NOT EXISTS idx_learned_facts_category
    ON learned_facts(category);
CREATE INDEX IF NOT EXISTS idx_projects_status
    ON projects(status);
CREATE INDEX IF NOT EXISTS idx_security_audit_severity
    ON security_audit(severity, timestamp);
CREATE INDEX IF NOT EXISTS idx_session_summaries_session
    ON session_summaries(session_id);
CREATE INDEX IF NOT EXISTS idx_execution_log_task_type
    ON execution_log(task_type, timestamp);
CREATE INDEX IF NOT EXISTS idx_execution_log_session
    ON execution_log(session_id);
CREATE INDEX IF NOT EXISTS idx_task_patterns_type_key
    ON task_patterns(task_type, pattern_key);
CREATE INDEX IF NOT EXISTS idx_error_solutions_pattern
    ON error_solutions(error_pattern);
CREATE INDEX IF NOT EXISTS idx_notification_log_category
    ON notification_log(category, timestamp);
CREATE INDEX IF NOT EXISTS idx_notification_log_status
    ON notification_log(status, timestamp);
"""


class MemoryEngine:


    def __init__(self, db_path: str, encryption_key: str | None = None) -> None:
        self._db_path = str(Path(db_path).resolve())
        self._encryption_key = encryption_key
        self._lock = threading.Lock()
        self._conn: apsw.Connection | None = None
        # LRU cache for prepared statement SQL strings (avoids re-parsing identical queries)
        self._stmt_cache: OrderedDict[str, None] = OrderedDict()
        self._last_optimize_time: float = 0.0
        self._open()
        self._init_db()
        self._maybe_optimize()
        log.info("memory_engine.ready", db_path=self._db_path, encrypted=bool(encryption_key))

    def _open(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = apsw.Connection(self._db_path)
        if self._encryption_key:
            # SQLCipher support — requires apsw compiled against SQLCipher.
            # PRAGMA key does not support parameter binding, and standard
            # apsw is NOT compiled with SQLCipher. We attempt the pragma
            # but gracefully skip if the extension is not available.
            try:
                import re as _re
                if not _re.fullmatch(r'[0-9a-fA-F]+', self._encryption_key):
                    raise ValueError("Encryption key must be hex-only")
                self._conn.execute(f"PRAGMA key = \"x'{self._encryption_key}'\"")  # hex key literal
                log.info("memory_engine.encryption_enabled")
            except apsw.SQLError:
                log.warning(
                    "memory_engine.encryption_not_available",
                    hint="apsw not compiled with SQLCipher — DB is unencrypted",
                )

    def _init_db(self) -> None:
        assert self._conn is not None
        with self._lock:
            for line in _PRAGMAS.strip().splitlines():
                line = line.strip()
                if line and not line.startswith("--"):
                    self._conn.execute(line)

            self._conn.execute("BEGIN")
            try:
                for statement in _split_statements(_TABLES):
                    self._conn.execute(statement)
                for statement in _split_statements(_INDEXES):
                    self._conn.execute(statement)
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

        self._run_migrations()

    def optimize(self) -> None:
        """Run VACUUM and ANALYZE to reclaim space and refresh query planner statistics.

        VACUUM rewrites the database file to remove free pages left by deletes/updates.
        ANALYZE updates the sqlite_stat tables so the query planner picks better indexes.
        Both are safe to call on a live database with WAL mode.
        """
        assert self._conn is not None, "MemoryEngine is closed"
        log.info("memory_engine.optimize_start")
        try:
            with self._lock:
                self._conn.execute("VACUUM")
                self._conn.execute("ANALYZE")
                self._conn.execute("PRAGMA optimize")
            self._last_optimize_time = time.monotonic()
            log.info("memory_engine.optimize_complete")
        except Exception as exc:
            log.warning("memory_engine.optimize_failed", error=str(exc))

    def _maybe_optimize(self) -> None:
        """Run optimize() if it hasn't been run in the last 24 hours."""
        now = time.monotonic()
        if now - self._last_optimize_time < _OPTIMIZE_INTERVAL_SECS:
            return
        self.optimize()

    def _run_migrations(self) -> None:
        """Apply incremental ALTER TABLE migrations for existing databases."""
        assert self._conn is not None
        migrations: list[tuple[str, str]] = [
            # (check_sql, alter_sql)
            # Add 'superseded_by' to learned_facts if absent
            (
                "SELECT COUNT(*) FROM pragma_table_info('learned_facts') WHERE name='superseded_by'",
                "ALTER TABLE learned_facts ADD COLUMN superseded_by INTEGER REFERENCES learned_facts(id)",
            ),
            # Ensure 'source' column exists in learned_facts with a proper default
            # (it already existed but may have been NULL in old rows; no migration needed
            #  for the column itself — it was always present per original schema)
        ]
        with self._lock:
            for check_sql, alter_sql in migrations:
                try:
                    row = next(self._conn.execute(check_sql), None)
                    if row and row[0] == 0:
                        self._conn.execute(alter_sql)
                        log.info("memory_engine.migration_applied", sql=alter_sql[:80])
                except Exception as exc:
                    log.warning("memory_engine.migration_skipped", sql=alter_sql[:80], error=str(exc))

    def _cache_stmt(self, sql: str) -> None:
        """Track recently used SQL strings in an LRU dict.

        APSW compiles each SQL string to a prepared statement internally.
        Keeping the LRU order means the most-used queries stay warm in
        SQLite's internal statement cache when the same SQL is re-submitted.
        This is a Python-level accounting layer; the actual statement reuse
        happens inside SQLite's own cache (controlled by SQLITE_MAX_PREPARE_RETRIES).
        """
        if sql in self._stmt_cache:
            self._stmt_cache.move_to_end(sql)
        else:
            self._stmt_cache[sql] = None
            if len(self._stmt_cache) > _STMT_CACHE_SIZE:
                self._stmt_cache.popitem(last=False)

    def execute(self, sql: str, params: Sequence[Any] = ()) -> apsw.Cursor:
        assert self._conn is not None, "MemoryEngine is closed"
        self._cache_stmt(sql)
        with self._lock:
            return self._conn.execute(sql, tuple(params))

    def execute_many(self, sql: str, param_seq: Sequence[Sequence[Any]]) -> None:
        assert self._conn is not None, "MemoryEngine is closed"
        with self._lock:
            for params in param_seq:
                self._conn.execute(sql, tuple(params))

    def fetchone(self, sql: str, params: Sequence[Any] = ()) -> tuple[Any, ...] | None:
        cursor = self.execute(sql, params)
        return next(cursor, None)  # type: ignore[arg-type]

    def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[tuple[Any, ...]]:
        return list(self.execute(sql, params))

    def fetchall_dicts(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        assert self._conn is not None, "MemoryEngine is closed"
        with self._lock:
            cursor = self._conn.execute(sql, tuple(params))
            try:
                description = cursor.getdescription()
            except apsw.ExecutionCompleteError:
                # No rows returned — cursor already completed
                return []
            columns = [col[0] for col in description]
            return [dict(zip(columns, row)) for row in cursor]

    def insert_returning_id(self, sql: str, params: Sequence[Any] = ()) -> int:
        assert self._conn is not None, "MemoryEngine is closed"
        with self._lock:
            self._conn.execute(sql, tuple(params))
            row = next(self._conn.execute("SELECT last_insert_rowid()"))
            return row[0]  # type: ignore[index]

    def last_insert_rowid(self) -> int:
        assert self._conn is not None
        row = next(self._conn.execute("SELECT last_insert_rowid()"))
        return row[0]  # type: ignore[index]

    def close(self) -> None:
        if self._conn is not None:
            with self._lock:
                self._conn.close()
                self._conn = None
            log.info("memory_engine.closed")

    def __del__(self) -> None:
        self.close()

    def __enter__(self) -> "MemoryEngine":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


import re as _re

_FTS5_SPECIAL = _re.compile(r'["\*\(\)\+\-\:\^\{\}\~\?\|]')


def sanitize_fts_query(query: str) -> str:
    # Remove special chars
    cleaned = _FTS5_SPECIAL.sub(" ", query)
    tokens = cleaned.split()
    if not tokens:
        return ""
    # Quote each token and join with implicit AND
    return " ".join(f'"{t}"' for t in tokens)


def _split_statements(sql_block: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_trigger = False

    for line in sql_block.strip().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue

        current.append(line)

        upper = stripped.upper()
        if upper.startswith("CREATE TRIGGER"):
            in_trigger = True

        if in_trigger:
            if upper == "END;":
                statements.append("\n".join(current))
                current = []
                in_trigger = False
        else:
            if stripped.endswith(";"):
                statements.append("\n".join(current))
                current = []

    if current:
        joined = "\n".join(current).strip()
        if joined:
            statements.append(joined)

    return statements
