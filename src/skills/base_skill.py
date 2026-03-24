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
        Only triggers when the message clearly expresses intent to use
        the skill — casual mentions of keywords are NOT enough.
        """
        text_lower = text.lower().strip()

        # Skip very long conversational messages — they are unlikely to be
        # direct skill invocations (e.g. user chatting naturally).
        # Skills should only trigger on short, purposeful messages.
        if len(text_lower) > 200:
            return None

        best: NaturalMatch | None = None
        best_confidence = 0.0

        for intent, patterns in self.natural_patterns.items():
            for pattern in patterns:
                m = re.search(pattern, text_lower)
                if not m:
                    continue
                # Extract args from named group or full match remainder
                args = ""
                try:
                    args = m.group("args") or ""
                except IndexError:
                    pass
                # Confidence based on match coverage — how much of the
                # message is consumed by the pattern match.
                matched_len = len(m.group(0))
                coverage = matched_len / max(len(text_lower), 1)

                # Require the pattern to cover at least 40% of the message.
                # This prevents short pattern hits inside long casual messages.
                if coverage < 0.40:
                    continue

                # The match must start near the beginning of the message
                # (within the first 20 chars) to avoid matching fragments
                # buried inside conversational sentences.
                if m.start() > 20:
                    continue

                confidence = min(0.5 + coverage * 0.5, 1.0)

                if confidence > best_confidence:
                    best_confidence = confidence
                    best = NaturalMatch(
                        skill_name=self.name,
                        intent=intent,
                        args=args.strip(),
                        confidence=confidence,
                    )
        return best

    def extract_args(self, text: str) -> str:
        text_lower = text.lower().strip()
        for trigger in self.triggers:
            if text_lower.startswith(trigger):
                return text[len(trigger):].strip()
        return text.strip()

    def __repr__(self) -> str:
        return f"<Skill:{self.name} triggers={self.triggers}>"
