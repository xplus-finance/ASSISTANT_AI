"""Active learning engine: web search, summarisation, fact extraction."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from src.learning.knowledge_base import KnowledgeBase
from src.learning.web_search import WebSearcher

log = structlog.get_logger("assistant.learning.learner")

_MAX_CONTEXT_CHARS = 12_000

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
Analiza estos mensajes y extrae DOS tipos de información:

1. HECHOS sobre el usuario (datos personales, preferencias, proyectos, contactos)
2. PROCEDIMIENTOS APRENDIDOS (qué funcionó, qué falló, trucos descubiertos)

Devuelve SOLO un JSON array. Cada elemento:
- "category": "user" | "project" | "preference" | "technical" | "world" | "procedure"
- "fact": el hecho o procedimiento (una oración clara y útil)
- "confidence": float 0.0-1.0

Para procedimientos (category="procedure"), incluye QUÉ SE HIZO y POR QUÉ FUNCIONÓ.
Ejemplo: "Para componer email en Gmail usar atajo 'c' + Tab entre campos, NO mouse"
Ejemplo: "Monitor derecho del usuario tiene offset +1920 en xrandr"
Ejemplo: "El usuario tiene ~30 pestañas en Firefox, CDP no está activo"

Si no hay hechos claros, devuelve [].
No inventes — solo extrae lo que se deduce de la conversación.

MENSAJES:
{messages}
"""


class Learner:


    def __init__(
        self,
        knowledge_base: KnowledgeBase,
        web_searcher: WebSearcher,
        claude_bridge: Any,
    ) -> None:
        self._kb = knowledge_base
        self._ws = web_searcher
        self._claude = claude_bridge

    async def learn_about(self, topic: str) -> str:
        log.info("learner.learning", topic=topic)

        results = await self._ws.search(topic, max_results=5)
        if not results:
            msg = f"No encontre resultados para: {topic}"
            log.warning("learner.no_results", topic=topic)
            return msg

        fetch_tasks = [
            self._ws.fetch_page(r.url)
            for r in results[:3]  # limit to top 3 to save time
        ]
        pages = await asyncio.gather(*fetch_tasks, return_exceptions=True)

        snippets: list[str] = []
        sources: list[str] = []

        for result, page in zip(results[:3], pages):
            if isinstance(page, Exception) or not page:
                    snippets.append(f"[{result.title}]\n{result.snippet}")
            else:
                snippets.append(f"[{result.title}] ({result.url})\n{page[:4000]}")
            sources.append(result.url)

        combined = "\n\n---\n\n".join(snippets)
        if len(combined) > _MAX_CONTEXT_CHARS:
            combined = combined[:_MAX_CONTEXT_CHARS] + "\n\n[... contenido truncado]"

        if self._claude is None:
            summary = f"Informacion recopilada sobre {topic}:\n\n{combined[:3000]}"
        else:
            prompt = _SUMMARISE_PROMPT.format(topic=topic, content=combined)
            try:
                summary = await self._claude.ask(prompt, timeout=60)
            except Exception:
                log.exception("learner.claude_summarise_failed", topic=topic)
                summary = f"Recopile informacion sobre {topic} pero no pude resumirla."

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

    async def extract_facts(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self._claude is None:
            return []

        if not messages:
            return []

        formatted = "\n".join(
            f"{m.get('role', 'unknown').upper()}: {m.get('message', '')}"
            for m in messages
        )

        prompt = _EXTRACT_FACTS_PROMPT.format(messages=formatted)

        try:
            raw_response = await self._claude.ask(prompt, timeout=60)
        except Exception:
            log.exception("learner.fact_extraction_claude_failed")
            return []

        facts = _parse_facts_json(raw_response)
        if not facts:
            return []

        persisted: list[dict[str, Any]] = []
        for fact in facts:
            category = fact.get("category", "user")
            fact_text = fact.get("fact", "")
            confidence = float(fact.get("confidence", 0.8))

            if not fact_text:
                continue

            valid_categories = {"user", "project", "preference", "technical", "world"}
            if category not in valid_categories:
                category = "user"

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


def _parse_facts_json(text: str) -> list[dict[str, Any]]:

    import json
    import re

    text = text.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if fenced:
        try:
            parsed = json.loads(fenced.group(1))
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

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
