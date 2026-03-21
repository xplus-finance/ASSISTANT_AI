"""Abstract base class for assistant skills."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillResult:
    success: bool
    message: str
    data: Any = None


@dataclass
class NaturalMatch:
    """Result of a natural language match."""
    skill_name: str
    intent: str
    args: str
    confidence: float  # 0.0–1.0


class BaseSkill(ABC):


    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def triggers(self) -> list[str]:
        ...

    @property
    def natural_patterns(self) -> dict[str, list[str]]:
        """Map of intent → list of regex patterns for natural language matching.

        Override in subclasses to enable natural language routing.
        Patterns are case-insensitive. Use named group (?P<args>...) to extract args.
        Example:
            {"add": [r"registra(?:r)? (?:un )?gasto (?:de )?(?P<args>.+)"]}
        """
        return {}

    @abstractmethod
    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult: ...

    def matches(self, text: str) -> bool:
        text_lower = text.lower().strip()
        return any(text_lower.startswith(t) for t in self.triggers)

    def matches_natural(self, text: str) -> NaturalMatch | None:
        """Check if text matches any natural language pattern.

        Returns NaturalMatch with extracted intent and args, or None.
        """
        text_lower = text.lower().strip()
        for intent, patterns in self.natural_patterns.items():
            for pattern in patterns:
                m = re.search(pattern, text_lower)
                if m:
                    # Extract args from named group or full match remainder
                    args = ""
                    try:
                        args = m.group("args") or ""
                    except IndexError:
                        pass
                    # Confidence based on match coverage
                    coverage = len(m.group(0)) / max(len(text_lower), 1)
                    confidence = min(0.5 + coverage * 0.5, 1.0)
                    return NaturalMatch(
                        skill_name=self.name,
                        intent=intent,
                        args=args.strip(),
                        confidence=confidence,
                    )
        return None

    def extract_args(self, text: str) -> str:
        text_lower = text.lower().strip()
        for trigger in self.triggers:
            if text_lower.startswith(trigger):
                return text[len(trigger):].strip()
        return text.strip()

    def __repr__(self) -> str:
        return f"<Skill:{self.name} triggers={self.triggers}>"
