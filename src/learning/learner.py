"""
Main learning engine.

Orchestrates web search, content fetching, Claude-powered summarisation,
and fact extraction to build the assistant's knowledge over time.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from src.learning.knowledge_base import KnowledgeBase
from src.learning.web_search import WebSearcher

log = structlog.get_logger("assistant.learning.learner")

# Maximum characters of fetched page content to send to Claude for summarisation
_MAX_CONTEXT_CHARS = 12_000

# Prompt templates
_SUMMARISE_PROMPT = """\
Eres un asistente de investigacion. Analiza el siguiente contenido web sobre \
el tema "{topic}" y genera un resumen estructurado con:

1. **Definicion o concepto principal**
2. **Puntos clave** (lista con viñetas)
3. **Datos relevantes o ejemplos**
4. **Fuentes consultadas**

Responde en español. Se conciso pero completo.

CONTENIDO:
{content}
"""

_EXTRACT_FACTS_PROMPT = """\
Analiza los siguientes mensajes de una conversacion y extrae hechos sobre \
el usuario. Devuelve SOLO un JSON array donde cada elemento tiene:
- "category": una de "user", "project", "preference", "technical", "world"
- "fact": el hecho extraido (una oracion clara)
- "confidence": float entre 0.0 y 1.0

Si no hay hechos claros, devuelve un array vacio [].
No inventes informacion — solo extrae lo que se deduce claramente.

MENSAJES:
{messages}
"""


class Learner:
    """
    Active learning engine.

    Combines web search, page fetching, and Claude summarisation
    to learn about topics on demand. Also extracts facts about the
    user from conversation history.
    """

    def __init__(
        self,
        knowledge_base: KnowledgeBase,
        web_searcher: WebSearcher,
        claude_bridge: Any,
    ) -> None:
        self._kb = knowledge_base
        self._ws = web_searcher
        self._claude = claude_bridge

    # ------------------------------------------------------------------
    # Learn about a topic
    # ------------------------------------------------------------------

    async def learn_about(self, topic: str) -> str:
        """
        Research a topic end-to-end:

        1. Search the web for the topic.
        2. Fetch the top result pages.
        3. Summarise and extract key information via Claude.
        4. Save the knowledge to the knowledge base.
        5. Return the summary.

        Args:
            topic: The topic to learn about.

        Returns:
            A Spanish-language summary of what was learned, or an error
            message if research failed.
        """
        log.info("learner.learning", topic=topic)

        # 1. Web search
        results = await self._ws.search(topic, max_results=5)
        if not results:
            msg = f"No encontre resultados para: {topic}"
            log.warning("learner.no_results", topic=topic)
            return msg

        # 2. Fetch top pages concurrently
        fetch_tasks = [
            self._ws.fetch_page(r.url)
            for r in results[:3]  # limit to top 3 to save time
        ]
        pages = await asyncio.gather(*fetch_tasks, return_exceptions=True)

        # Build combined context
        snippets: list[str] = []
        sources: list[str] = []

        for result, page in zip(results[:3], pages):
            if isinstance(page, Exception) or not page:
                # Fall back to the search snippet
                snippets.append(f"[{result.title}]\n{result.snippet}")
            else:
                snippets.append(f"[{result.title}] ({result.url})\n{page[:4000]}")
            sources.append(result.url)

        combined = "\n\n---\n\n".join(snippets)
        if len(combined) > _MAX_CONTEXT_CHARS:
            combined = combined[:_MAX_CONTEXT_CHARS] + "\n\n[... contenido truncado]"

        # 3. Summarise with Claude
        if self._claude is None:
            summary = f"Informacion recopilada sobre {topic}:\n\n{combined[:3000]}"
        else:
            prompt = _SUMMARISE_PROMPT.format(topic=topic, content=combined)
            try:
                summary = await asyncio.to_thread(self._claude.send, prompt)
            except Exception:
                log.exception("learner.claude_summarise_failed", topic=topic)
                summary = f"Recopile informacion sobre {topic} pero no pude resumirla."

        # 4. Save to knowledge base
        source_str = ", ".join(sources[:3])
        try:
            await self._kb.save_knowledge(
                topic=topic,
                content=summary,
                source=source_str,
            )
        except Exception:
            log.exception("learner.save_failed", topic=topic)

        log.info("learner.learned", topic=topic, sources=len(sources))
        return summary

    # ------------------------------------------------------------------
    # Fact extraction from conversations
    # ------------------------------------------------------------------

    async def extract_facts(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Analyse a batch of conversation messages and extract facts
        about the user.

        Uses Claude to identify facts, then persists them to the
        ``learned_facts`` table.

        Args:
            messages: List of message dicts (must have ``role`` and ``message`` keys).

        Returns:
            List of extracted fact dicts (each with ``category``, ``fact``,
            ``confidence``), or an empty list on failure.
        """
        if self._claude is None:
            return []

        if not messages:
            return []

        # Format messages for the prompt
        formatted = "\n".join(
            f"{m.get('role', 'unknown').upper()}: {m.get('message', '')}"
            for m in messages
        )

        prompt = _EXTRACT_FACTS_PROMPT.format(messages=formatted)

        try:
            raw_response = await asyncio.to_thread(self._claude.send, prompt)
        except Exception:
            log.exception("learner.fact_extraction_claude_failed")
            return []

        # Parse JSON response
        facts = _parse_facts_json(raw_response)
        if not facts:
            return []

        # Persist to database
        persisted: list[dict[str, Any]] = []
        for fact in facts:
            category = fact.get("category", "user")
            fact_text = fact.get("fact", "")
            confidence = float(fact.get("confidence", 0.8))

            if not fact_text:
                continue

            # Validate category
            valid_categories = {"user", "project", "preference", "technical", "world"}
            if category not in valid_categories:
                category = "user"

            # Clamp confidence
            confidence = max(0.0, min(1.0, confidence))

            try:
                from src.memory.engine import MemoryEngine

                # Access the engine through the knowledge base
                self._kb._engine.insert_returning_id(
                    """
                    INSERT INTO learned_facts (category, fact, confidence, source)
                    VALUES (?, ?, ?, ?)
                    """,
                    (category, fact_text, confidence, "conversation"),
                )
                persisted.append(fact)
            except Exception:
                log.warning("learner.fact_persist_failed", fact=fact_text[:60])

        log.info("learner.facts_extracted", total=len(facts), persisted=len(persisted))
        return persisted


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_facts_json(text: str) -> list[dict[str, Any]]:
    """
    Extract a JSON array from Claude's response.

    Claude may wrap the JSON in markdown code fences or add commentary;
    this function tries to extract just the array.
    """
    import json
    import re

    # Try direct parse first
    text = text.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass

    # Try to find a JSON array in the text
    # Look for content between ``` fences first
    fenced = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if fenced:
        try:
            parsed = json.loads(fenced.group(1))
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

    # Last resort: find the first [ ... ] block
    bracket_match = re.search(r"\[.*\]", text, re.DOTALL)
    if bracket_match:
        try:
            parsed = json.loads(bracket_match.group(0))
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

    log.warning("learner.facts_json_parse_failed", text_head=text[:200])
    return []
