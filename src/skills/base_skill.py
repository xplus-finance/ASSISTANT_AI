"""Abstract base class for assistant skills."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillResult:
    """Standard result envelope returned by every skill execution."""
    success: bool
    message: str
    data: Any = None


class BaseSkill(ABC):
    """Abstract base for all assistant skills.

    Subclasses must define ``name``, ``description``, ``triggers``,
    and ``execute(args, context)``.
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def triggers(self) -> list[str]:
        """Prefixes (case-insensitive) that activate this skill."""
        ...

    @abstractmethod
    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult: ...

    def matches(self, text: str) -> bool:
        text_lower = text.lower().strip()
        return any(text_lower.startswith(t) for t in self.triggers)

    def extract_args(self, text: str) -> str:
        text_lower = text.lower().strip()
        for trigger in self.triggers:
            if text_lower.startswith(trigger):
                return text[len(trigger):].strip()
        return text.strip()

    def __repr__(self) -> str:
        return f"<Skill:{self.name} triggers={self.triggers}>"
