"""
Knowledge base management.

Persists learned knowledge both in SQLite (with FTS5 for full-text search)
and as human-readable Markdown files under ``data/knowledge/``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import structlog

from src.memory.engine import MemoryEngine

log = structlog.get_logger("assistant.learning.knowledge_base")


class KnowledgeBase:
    """
    Store, search, and retrieve knowledge entries.

    Knowledge lives in two places:
    - The ``knowledge`` SQLite table (fast FTS search).
    - Markdown files at ``{data_dir}/knowledge/{topic}.md`` (human-readable,
      easy to version-control or share).
    """

    def __init__(self, engine: MemoryEngine, data_dir: str) -> None:
        self._engine = engine
        self._knowledge_dir = Path(data_dir) / "knowledge"
        self._knowledge_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def save_knowledge(
        self,
        topic: str,
        content: str,
        source: str | None = None,
    ) -> int:
        """
        Persist a knowledge entry to the database and to a Markdown file.

        Args:
            topic: Short topic name (e.g. ``"python-asyncio"``).
            content: The knowledge content (can be multi-paragraph).
            source: Optional source URL or description.

        Returns:
            The row id of the inserted database record.
        """
        # -- Database -------------------------------------------------------
        sql = """
            INSERT INTO knowledge (topic, content, source_url)
            VALUES (?, ?, ?)
        """
        row_id = self._engine.insert_returning_id(sql, (topic, content, source))

        # -- Markdown file --------------------------------------------------
        safe_name = _sanitise_filename(topic)
        md_path = self._knowledge_dir / f"{safe_name}.md"

        header = f"# {topic}\n\n"
        source_line = f"_Source: {source}_\n\n" if source else ""
        separator = "---\n\n"

        # Append if the file already exists (accumulate knowledge per topic)
        with md_path.open("a", encoding="utf-8") as fh:
            if md_path.stat().st_size == 0:
                fh.write(header)
            fh.write(f"{source_line}{content}\n\n{separator}")

        log.info(
            "knowledge_base.saved",
            topic=topic,
            row_id=row_id,
            md_path=str(md_path),
        )
        return row_id

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """
        Search knowledge by full-text query.

        Searches both the SQLite FTS index and scans Markdown filenames.
        Results from both sources are merged and deduplicated by topic.

        Args:
            query: Free-text search query.
            limit: Maximum number of results.

        Returns:
            List of dicts with keys: ``id``, ``topic``, ``content``,
            ``source_url``, ``learned_at``, ``origin`` (``"db"`` or ``"file"``).
        """
        results: list[dict[str, Any]] = []
        seen_topics: set[str] = set()

        # -- FTS search -----------------------------------------------------
        try:
            sql = """
                SELECT k.id, k.topic, k.content, k.source_url, k.learned_at
                FROM knowledge_fts f
                JOIN knowledge k ON k.id = f.rowid
                WHERE knowledge_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """
            rows = self._engine.fetchall_dicts(sql, (query, limit))
            for row in rows:
                row["origin"] = "db"
                results.append(row)
                seen_topics.add(row["topic"].lower())
        except Exception:
            log.warning("knowledge_base.fts_search_failed", query=query)

        # -- File search (simple substring match on filename + content) ------
        query_lower = query.lower()
        try:
            for md_file in sorted(self._knowledge_dir.glob("*.md")):
                if len(results) >= limit:
                    break

                topic = md_file.stem.replace("-", " ").replace("_", " ")
                if topic.lower() in seen_topics:
                    continue

                # Check filename match
                name_match = query_lower in md_file.stem.lower()

                # Check content match (only read first 5 KB)
                content_match = False
                if not name_match:
                    try:
                        head = md_file.read_text(encoding="utf-8")[:5120]
                        content_match = query_lower in head.lower()
                    except OSError:
                        continue

                if name_match or content_match:
                    try:
                        full_content = md_file.read_text(encoding="utf-8")
                    except OSError:
                        continue

                    results.append({
                        "id": None,
                        "topic": topic,
                        "content": full_content[:3000],
                        "source_url": None,
                        "learned_at": None,
                        "origin": "file",
                    })
                    seen_topics.add(topic.lower())
        except Exception:
            log.warning("knowledge_base.file_search_failed", query=query)

        log.debug("knowledge_base.search_complete", query=query, results=len(results))
        return results

    # ------------------------------------------------------------------
    # Topic listing
    # ------------------------------------------------------------------

    async def get_topics(self) -> list[str]:
        """
        Return a sorted list of all known topics (from DB and files combined).
        """
        topics: set[str] = set()

        # From database
        try:
            rows = self._engine.fetchall("SELECT DISTINCT topic FROM knowledge")
            topics.update(row[0] for row in rows)
        except Exception:
            log.warning("knowledge_base.db_topics_failed")

        # From filesystem
        try:
            for md_file in self._knowledge_dir.glob("*.md"):
                topic = md_file.stem.replace("-", " ").replace("_", " ")
                topics.add(topic)
        except Exception:
            log.warning("knowledge_base.file_topics_failed")

        return sorted(topics, key=str.lower)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UNSAFE_CHARS = re.compile(r"[^\w\s-]", re.UNICODE)
_WHITESPACE = re.compile(r"[\s]+")


def _sanitise_filename(name: str) -> str:
    """
    Convert a topic name to a safe, lowercase, hyphenated filename stem.

    Example: ``"Python Asyncio!"`` -> ``"python-asyncio"``
    """
    name = _UNSAFE_CHARS.sub("", name)
    name = _WHITESPACE.sub("-", name.strip())
    return name.lower()[:120] or "untitled"
