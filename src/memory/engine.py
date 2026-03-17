"""
Core memory engine backed by SQLite via APSW.

Provides the database connection, schema initialization, and low-level
query helpers used by every other memory module. Supports optional
SQLCipher encryption when an encryption key is provided.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Sequence

import apsw
import structlog

log = structlog.get_logger("assistant.memory")

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

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
    category TEXT NOT NULL CHECK(category IN ('user', 'project', 'preference', 'technical', 'world')),
    fact TEXT NOT NULL,
    confidence REAL DEFAULT 1.0 CHECK(confidence BETWEEN 0 AND 1),
    source TEXT,
    learned_at TEXT DEFAULT (datetime('now')),
    last_used TEXT,
    use_count INTEGER DEFAULT 0
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
"""

# Indexes for common query patterns
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
"""


class MemoryEngine:
    """
    Central database engine for all assistant memory.

    Thread-safe: each public method acquires a lock before touching the
    connection.  APSW itself allows sharing a connection across threads
    when using WAL mode, but the lock prevents interleaved multi-statement
    transactions.
    """

    def __init__(self, db_path: str, encryption_key: str | None = None) -> None:
        self._db_path = str(Path(db_path).resolve())
        self._encryption_key = encryption_key
        self._lock = threading.Lock()
        self._conn: apsw.Connection | None = None
        self._open()
        self._init_db()
        log.info("memory_engine.ready", db_path=self._db_path, encrypted=bool(encryption_key))

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _open(self) -> None:
        """Open the APSW connection (create file if needed)."""
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = apsw.Connection(self._db_path)
        if self._encryption_key:
            # SQLCipher support — requires apsw compiled against SQLCipher.
            # PRAGMA key does not support parameter binding, and standard
            # apsw is NOT compiled with SQLCipher. We attempt the pragma
            # but gracefully skip if the extension is not available.
            try:
                if "'" in self._encryption_key:
                    raise ValueError("Encryption key contains invalid characters")
                self._conn.execute(f"PRAGMA key = '{self._encryption_key}'")
                log.info("memory_engine.encryption_enabled")
            except apsw.SQLError:
                log.warning(
                    "memory_engine.encryption_not_available",
                    hint="apsw not compiled with SQLCipher — DB is unencrypted",
                )

    def _init_db(self) -> None:
        """Create all tables, FTS indexes, triggers and performance indexes."""
        assert self._conn is not None
        with self._lock:
            # Pragmas must be executed one at a time (no multi-statement)
            for line in _PRAGMAS.strip().splitlines():
                line = line.strip()
                if line and not line.startswith("--"):
                    self._conn.execute(line)

            # Tables, triggers, virtual tables
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

    # ------------------------------------------------------------------
    # Public query helpers — always use parameterised queries
    # ------------------------------------------------------------------

    def execute(self, sql: str, params: Sequence[Any] = ()) -> apsw.Cursor:
        """Execute a single SQL statement with parameters. Returns a cursor."""
        assert self._conn is not None, "MemoryEngine is closed"
        with self._lock:
            return self._conn.execute(sql, tuple(params))

    def execute_many(self, sql: str, param_seq: Sequence[Sequence[Any]]) -> None:
        """Execute a statement for each set of parameters."""
        assert self._conn is not None, "MemoryEngine is closed"
        with self._lock:
            for params in param_seq:
                self._conn.execute(sql, tuple(params))

    def fetchone(self, sql: str, params: Sequence[Any] = ()) -> tuple[Any, ...] | None:
        """Execute and return the first row, or None."""
        cursor = self.execute(sql, params)
        return next(cursor, None)  # type: ignore[arg-type]

    def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[tuple[Any, ...]]:
        """Execute and return all rows as a list of tuples."""
        return list(self.execute(sql, params))

    def fetchall_dicts(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        """Execute and return all rows as a list of dicts (column-name keys)."""
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
        """Execute an INSERT and return last_insert_rowid()."""
        assert self._conn is not None, "MemoryEngine is closed"
        with self._lock:
            self._conn.execute(sql, tuple(params))
            row = next(self._conn.execute("SELECT last_insert_rowid()"))
            return row[0]  # type: ignore[index]

    def last_insert_rowid(self) -> int:
        """Return the rowid of the last INSERT (must be called under lock)."""
        assert self._conn is not None
        row = next(self._conn.execute("SELECT last_insert_rowid()"))
        return row[0]  # type: ignore[index]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the database connection gracefully."""
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

import re as _re

# Characters that have special meaning in FTS5 query syntax
_FTS5_SPECIAL = _re.compile(r'["\*\(\)\+\-\:\^\{\}\~\?\|]')


def sanitize_fts_query(query: str) -> str:
    """
    Sanitize a user-provided string for safe use in an FTS5 MATCH clause.

    Strips FTS5 special characters and wraps each remaining token in
    double quotes to force literal matching.  Returns an empty string
    if nothing usable remains.
    """
    # Remove special chars
    cleaned = _FTS5_SPECIAL.sub(" ", query)
    tokens = cleaned.split()
    if not tokens:
        return ""
    # Quote each token and join with implicit AND
    return " ".join(f'"{t}"' for t in tokens)


def _split_statements(sql_block: str) -> list[str]:
    """
    Split a multi-statement SQL block into individual statements.

    Handles CREATE TRIGGER ... END; blocks properly by tracking BEGIN/END
    nesting.
    """
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
