"""
Learning skill — web search, content extraction, and knowledge storage.

Uses ``httpx`` for HTTP requests and ``beautifulsoup4`` for HTML parsing.
Learned content is persisted in the ``knowledge`` table with full-text search.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlparse

import structlog

from src.memory.engine import MemoryEngine
from src.skills.base_skill import BaseSkill, SkillResult

log = structlog.get_logger("assistant.skills.learn")

# Maximum content length to store per knowledge entry
_MAX_CONTENT_LENGTH = 10_000

# User-Agent for HTTP requests
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class LearnSkill(BaseSkill):
    """Search the web, extract content, and store knowledge."""

    def __init__(self, memory_engine: MemoryEngine | None = None) -> None:
        self._memory = memory_engine

    @property
    def name(self) -> str:
        return "learn"

    @property
    def description(self) -> str:
        return "Busca en la web, extrae contenido y almacena conocimiento"

    @property
    def triggers(self) -> list[str]:
        return ["!busca", "!aprende", "!aprendido"]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        """
        Handle learning operations.

        Sub-commands:
            ``!busca <query>``     — search the web and summarize results
            ``!aprende <url>``     — extract and store content from a URL
            ``!aprendido``         — list stored knowledge
            ``!aprendido buscar <q>`` — search stored knowledge
        """
        memory = self._memory or context.get("memory")
        if memory is None:
            return SkillResult(success=False, message="Motor de memoria no disponible.")

        original = context.get("original_text", "").lower().strip()

        if original.startswith("!aprendido"):
            return self._handle_learned(memory, args)
        elif original.startswith("!aprende"):
            return await self._learn_from_url(memory, args)
        elif original.startswith("!busca"):
            return await self._web_search(memory, args, context)
        else:
            return SkillResult(
                success=False,
                message=(
                    "Uso:\n"
                    "  !busca <termino>  — buscar en la web\n"
                    "  !aprende <url>    — aprender de una pagina\n"
                    "  !aprendido        — ver conocimiento almacenado"
                ),
            )

    # ------------------------------------------------------------------
    # Web search
    # ------------------------------------------------------------------

    async def _web_search(
        self,
        memory: MemoryEngine,
        query: str,
        context: dict[str, Any],
    ) -> SkillResult:
        """Search the web using DuckDuckGo HTML (no API key needed)."""
        if not query.strip():
            return SkillResult(success=False, message="Uso: !busca <termino de busqueda>")

        try:
            import httpx
            from bs4 import BeautifulSoup
        except ImportError as exc:
            return SkillResult(
                success=False,
                message=f"Dependencia faltante: {exc}. Instala httpx y beautifulsoup4.",
            )

        search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query.strip())}"

        try:
            async with httpx.AsyncClient(
                timeout=15,
                headers={"User-Agent": _USER_AGENT},
                follow_redirects=True,
            ) as client:
                resp = await client.get(search_url)
                resp.raise_for_status()
        except Exception as exc:
            # Check for httpx-specific exceptions
            exc_name = type(exc).__name__
            if "Timeout" in exc_name:
                return SkillResult(success=False, message="Timeout buscando en la web.")
            return SkillResult(success=False, message=f"Error HTTP: {exc}")

        soup = BeautifulSoup(resp.text, "html.parser")
        results = self._parse_ddg_results(soup)

        if not results:
            return SkillResult(
                success=True,
                message=f"No encontre resultados para: {query.strip()}",
            )

        lines = [f"Resultados para '{query.strip()}':", ""]
        for i, r in enumerate(results[:5], 1):
            lines.append(f"{i}. {r['title']}")
            lines.append(f"   {r['url']}")
            if r["snippet"]:
                lines.append(f"   {r['snippet'][:150]}")
            lines.append("")

        lines.append("Usa !aprende <url> para aprender de alguno de estos.")

        return SkillResult(
            success=True,
            message="\n".join(lines),
            data={"results": results[:5]},
        )

    @staticmethod
    def _parse_ddg_results(soup: Any) -> list[dict[str, str]]:
        """Parse DuckDuckGo HTML search results."""
        results: list[dict[str, str]] = []
        for result in soup.select(".result"):
            title_tag = result.select_one(".result__title a, .result__a")
            snippet_tag = result.select_one(".result__snippet")

            if not title_tag:
                continue

            title = title_tag.get_text(strip=True)
            url = title_tag.get("href", "")
            snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""

            # DDG wraps URLs in a redirect; extract the actual URL
            if "uddg=" in url:
                parsed = urlparse(url)
                qs = parse_qs(parsed.query)
                url = qs.get("uddg", [url])[0]

            if title and url:
                results.append({"title": title, "url": url, "snippet": snippet})

        return results

    # ------------------------------------------------------------------
    # Learn from URL
    # ------------------------------------------------------------------

    async def _learn_from_url(
        self, memory: MemoryEngine, url: str
    ) -> SkillResult:
        """Fetch a URL, extract text content, and store it as knowledge."""
        url = url.strip()
        if not url:
            return SkillResult(success=False, message="Uso: !aprende <url>")

        # Basic URL validation
        parsed = urlparse(url)
        if not parsed.scheme:
            url = "https://" + url
            parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            return SkillResult(success=False, message=f"Esquema no soportado: {parsed.scheme}")

        try:
            import httpx
            from bs4 import BeautifulSoup
        except ImportError as exc:
            return SkillResult(
                success=False,
                message=f"Dependencia faltante: {exc}.",
            )

        try:
            async with httpx.AsyncClient(
                timeout=20,
                headers={"User-Agent": _USER_AGENT},
                follow_redirects=True,
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except Exception as exc:
            exc_name = type(exc).__name__
            if "Timeout" in exc_name:
                return SkillResult(success=False, message=f"Timeout accediendo a {url}")
            return SkillResult(success=False, message=f"Error HTTP: {exc}")

        content_type = resp.headers.get("content-type", "")
        if "text/html" not in content_type and "text/plain" not in content_type:
            return SkillResult(
                success=False,
                message=f"Tipo de contenido no soportado: {content_type}",
            )

        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract title
        title_tag = soup.find("title")
        topic = title_tag.get_text(strip=True) if title_tag else parsed.netloc

        # Remove scripts, styles, nav, footer
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        # Extract text
        text = soup.get_text(separator="\n", strip=True)

        # Clean up whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text[:_MAX_CONTENT_LENGTH]

        if len(text) < 50:
            return SkillResult(
                success=False,
                message="La pagina no contiene suficiente texto extraible.",
            )

        # Store in knowledge table
        knowledge_id = memory.insert_returning_id(
            """
            INSERT INTO knowledge (topic, content, source_url)
            VALUES (?, ?, ?)
            """,
            (topic[:200], text, url),
        )

        log.info("learn.stored", id=knowledge_id, topic=topic[:60], url=url)
        return SkillResult(
            success=True,
            message=(
                f"Contenido aprendido de: {url}\n"
                f"Tema: {topic[:100]}\n"
                f"Almacenado como conocimiento #{knowledge_id} ({len(text)} chars)"
            ),
            data={"id": knowledge_id, "topic": topic, "url": url},
        )

    # ------------------------------------------------------------------
    # Show stored knowledge
    # ------------------------------------------------------------------

    def _handle_learned(self, memory: MemoryEngine, args: str) -> SkillResult:
        """Handle ``!aprendido`` subcommands."""
        if not args.strip():
            return self._list_knowledge(memory)

        parts = args.split(maxsplit=1)
        sub = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""

        if sub in ("buscar", "search"):
            return self._search_knowledge(memory, rest)
        else:
            return self._search_knowledge(memory, args)

    def _list_knowledge(self, memory: MemoryEngine) -> SkillResult:
        """List all stored knowledge entries."""
        rows = memory.fetchall_dicts(
            """
            SELECT id, topic, source_url, learned_at,
                   LENGTH(content) as content_length
            FROM knowledge
            ORDER BY learned_at DESC
            LIMIT 20
            """,
        )

        if not rows:
            return SkillResult(
                success=True,
                message="No hay conocimiento almacenado. Usa !busca o !aprende.",
            )

        lines = ["Conocimiento almacenado:", ""]
        for row in rows:
            lines.append(
                f"  #{row['id']}: {row['topic'][:60]} "
                f"({row['content_length']:,} chars)"
            )
            if row.get("source_url"):
                lines.append(f"       {row['source_url'][:80]}")

        return SkillResult(success=True, message="\n".join(lines), data={"entries": rows})

    def _search_knowledge(self, memory: MemoryEngine, query: str) -> SkillResult:
        """Full-text search in stored knowledge."""
        if not query.strip():
            return SkillResult(success=False, message="Uso: !aprendido buscar <termino>")

        rows = memory.fetchall_dicts(
            """
            SELECT k.id, k.topic, k.content, k.source_url
            FROM knowledge k
            JOIN knowledge_fts ON knowledge_fts.rowid = k.id
            WHERE knowledge_fts MATCH ?
            ORDER BY rank
            LIMIT 5
            """,
            (query.strip(),),
        )

        if not rows:
            return SkillResult(
                success=True,
                message=f"No encontre conocimiento sobre '{query.strip()}'.",
            )

        lines = [f"Conocimiento sobre '{query.strip()}':", ""]
        for row in rows:
            lines.append(f"#{row['id']}: {row['topic']}")
            # Show first 300 chars of content
            preview = row["content"][:300].replace("\n", " ")
            lines.append(f"  {preview}...")
            lines.append("")

        return SkillResult(success=True, message="\n".join(lines), data={"results": rows})
