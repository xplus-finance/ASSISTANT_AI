"""Bidirectional sync between Firulais memory (SQLite) and Claude Code memory (.md files)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import structlog

from src.memory.engine import MemoryEngine
from src.memory.learning import LearningStore

log = structlog.get_logger("assistant.memory.claude_code_sync")

# Default Claude Code memory directory
_DEFAULT_MEMORY_DIR = Path.home() / ".claude" / "projects" / "-tmp-ASSISTANT-AI" / "memory"


class ClaudeCodeSync:
    """Sync facts between SQLite (Firulais) and Claude Code markdown memory files."""

    def __init__(
        self,
        engine: MemoryEngine,
        learning: LearningStore,
        memory_dir: str | Path | None = None,
    ) -> None:
        self._engine = engine
        self._learning = learning
        self._memory_dir = Path(memory_dir) if memory_dir else _DEFAULT_MEMORY_DIR

    @property
    def memory_dir(self) -> Path:
        return self._memory_dir

    def is_available(self) -> bool:
        """Check if Claude Code memory directory exists."""
        return self._memory_dir.is_dir()

    # ------------------------------------------------------------------
    # Import: Claude Code .md files → SQLite learned_facts
    # ------------------------------------------------------------------

    def import_from_claude_code(self) -> int:
        """Read all .md memory files and import new facts into SQLite.

        Returns the number of facts imported.
        """
        if not self.is_available():
            log.info("claude_code_sync.dir_not_found", path=str(self._memory_dir))
            return 0

        imported = 0
        for md_file in sorted(self._memory_dir.glob("*.md")):
            if md_file.name == "MEMORY.md":
                continue  # Index file, skip

            try:
                content = md_file.read_text(encoding="utf-8", errors="replace")
                meta = self._parse_frontmatter(content)
                body = self._extract_body(content)

                if not body.strip():
                    continue

                mem_type = meta.get("type", "technical")
                category = self._type_to_category(mem_type)
                source = f"claude_code:{md_file.name}"

                fact_id = self._learning.add_fact_deduplicated(
                    category=category,
                    fact=body.strip()[:500],
                    source=source,
                    confidence=0.9,
                )
                if fact_id:
                    imported += 1

            except Exception:
                log.warning("claude_code_sync.import_file_failed",
                            file=md_file.name, exc_info=True)

        log.info("claude_code_sync.imported", count=imported)
        return imported

    # ------------------------------------------------------------------
    # Export: SQLite learned_facts → Claude Code .md files
    # ------------------------------------------------------------------

    def export_to_claude_code(self, categories: list[str] | None = None) -> int:
        """Export key facts from SQLite to Claude Code memory files.

        Returns the number of files written/updated.
        """
        if not self._memory_dir.exists():
            try:
                self._memory_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                log.warning("claude_code_sync.cannot_create_dir", path=str(self._memory_dir))
                return 0

        cats = categories or ["procedure", "preference", "user", "project"]
        exported = 0

        for category in cats:
            try:
                facts = self._learning.get_facts_by_category(category)
                if not facts:
                    continue

                # Group facts by category into a single file
                filename = f"sync_{category}.md"
                filepath = self._memory_dir / filename

                lines = [
                    "---",
                    f"name: firulais_{category}_facts",
                    f"description: {category.capitalize()} facts synced from Firulais SQLite memory",
                    f"type: {'feedback' if category == 'preference' else category}",
                    "---",
                    "",
                ]

                for fact in facts[:30]:  # Limit to top 30 per category
                    fact_text = fact.get("fact", "")
                    if fact_text:
                        confidence = fact.get("confidence", 1.0)
                        use_count = fact.get("use_count", 0)
                        lines.append(f"- {fact_text} (confidence: {confidence}, uses: {use_count})")

                filepath.write_text("\n".join(lines), encoding="utf-8")
                exported += 1

            except Exception:
                log.warning("claude_code_sync.export_category_failed",
                            category=category, exc_info=True)

        # Update MEMORY.md index
        self._update_memory_index()

        log.info("claude_code_sync.exported", count=exported)
        return exported

    # ------------------------------------------------------------------
    # Full bidirectional sync
    # ------------------------------------------------------------------

    def sync(self) -> dict[str, int]:
        """Run full bidirectional sync. Returns {imported, exported}."""
        imported = self.import_from_claude_code()
        exported = self.export_to_claude_code()
        log.info("claude_code_sync.sync_complete", imported=imported, exported=exported)
        return {"imported": imported, "exported": exported}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_frontmatter(content: str) -> dict[str, str]:
        """Extract YAML-like frontmatter from markdown."""
        match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if not match:
            return {}
        meta: dict[str, str] = {}
        for line in match.group(1).splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                meta[key.strip()] = value.strip()
        return meta

    @staticmethod
    def _extract_body(content: str) -> str:
        """Extract body content after frontmatter."""
        match = re.match(r"^---\s*\n.*?\n---\s*\n?", content, re.DOTALL)
        if match:
            return content[match.end():]
        return content

    @staticmethod
    def _type_to_category(mem_type: str) -> str:
        """Map Claude Code memory type to Firulais fact category."""
        mapping = {
            "user": "user",
            "feedback": "preference",
            "project": "project",
            "reference": "technical",
        }
        return mapping.get(mem_type, "technical")

    def _update_memory_index(self) -> None:
        """Update MEMORY.md to include sync files."""
        index_path = self._memory_dir / "MEMORY.md"
        if not index_path.exists():
            return

        try:
            content = index_path.read_text(encoding="utf-8", errors="replace")

            # Check if sync section already exists
            if "## Synced from Firulais" in content:
                # Update existing section
                before = content.split("## Synced from Firulais")[0]
                content = before.rstrip() + "\n\n"
            else:
                content = content.rstrip() + "\n\n"

            # Add sync section
            sync_files = sorted(self._memory_dir.glob("sync_*.md"))
            if sync_files:
                lines = ["## Synced from Firulais"]
                for sf in sync_files:
                    cat = sf.stem.replace("sync_", "")
                    lines.append(f"- [{sf.name}]({sf.name}) — {cat.capitalize()} facts from Firulais memory")
                content += "\n".join(lines) + "\n"

            index_path.write_text(content, encoding="utf-8")
        except Exception:
            log.warning("claude_code_sync.index_update_failed", exc_info=True)
