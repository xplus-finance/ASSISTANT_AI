"""
Abstract base class for assistant skills.

Every skill — built-in or user-created — must inherit from ``BaseSkill``
and implement its abstract members.  The ``SkillResult`` dataclass is
the standard return type for all skill executions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillResult:
    """
    Standard result envelope returned by every skill execution.

    Attributes:
        success: ``True`` if the operation completed without errors.
        message: Human-readable summary of what happened.
        data: Optional structured data (dict, list, etc.) for
              programmatic consumers.
    """

    success: bool
    message: str
    data: Any = None


class BaseSkill(ABC):
    """
    Abstract base for all assistant skills.

    Subclasses must define:

    * ``name`` — unique identifier (e.g., ``"terminal"``).
    * ``description`` — one-line human-readable description.
    * ``triggers`` — list of prefixes that activate the skill
      (e.g., ``["!cmd", "!exec"]``).
    * ``execute(args, context)`` — the async entry point that performs
      the skill's work and returns a ``SkillResult``.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique skill identifier."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """One-line description of what this skill does."""
        ...

    @property
    @abstractmethod
    def triggers(self) -> list[str]:
        """
        Prefixes that activate this skill.

        Each entry is compared (case-insensitive) against the start of
        the user's message.  The first match wins.
        """
        ...

    @abstractmethod
    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        """
        Run the skill.

        Args:
            args: Everything after the trigger prefix, stripped.
            context: Runtime context dict.  Typically includes:
                     ``memory`` (MemoryEngine), ``send_fn`` (message sender),
                     ``bridge`` (ClaudeBridge), ``approval_gate``, etc.

        Returns:
            A ``SkillResult`` describing the outcome.
        """
        ...

    # ------------------------------------------------------------------
    # Convenience helpers (non-abstract)
    # ------------------------------------------------------------------

    def matches(self, text: str) -> bool:
        """
        Return ``True`` if *text* starts with any of this skill's triggers.
        """
        text_lower = text.lower().strip()
        return any(text_lower.startswith(t) for t in self.triggers)

    def extract_args(self, text: str) -> str:
        """
        Strip the matching trigger prefix from *text* and return the
        remaining argument string.
        """
        text_lower = text.lower().strip()
        for trigger in self.triggers:
            if text_lower.startswith(trigger):
                return text[len(trigger):].strip()
        return text.strip()

    def __repr__(self) -> str:
        return f"<Skill:{self.name} triggers={self.triggers}>"
