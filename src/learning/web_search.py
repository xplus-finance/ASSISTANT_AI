"""
Web search via DuckDuckGo HTML (no API key required).

Provides ``WebSearcher`` for querying DuckDuckGo and extracting
readable text from result pages.  Used by the Learner to gather
information about arbitrary topics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote_plus

import httpx
import structlog
from bs4 import BeautifulSoup, Tag

log = structlog.get_logger("assistant.learning.web_search")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DDG_URL = "https://html.duckduckgo.com/html/"
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
}

_FETCH_TIMEOUT = 15.0  # seconds
_SEARCH_TIMEOUT = 10.0

# Tags whose text we strip when extracting page content
_NOISE_TAGS = {"script", "style", "nav", "header", "footer", "aside", "form", "noscript", "svg"}

# Maximum chars to return from a single page fetch
_MAX_PAGE_CHARS = 15_000


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SearchResult:
    """A single search result from DuckDuckGo."""
    title: str
    url: str
    snippet: str


# ---------------------------------------------------------------------------
# WebSearcher
# ---------------------------------------------------------------------------

class WebSearcher:
    """
    Search the web via DuckDuckGo HTML and fetch page content.

    No API key needed — uses the public ``html.duckduckgo.com`` endpoint.
    """

    def __init__(self, timeout: float = _SEARCH_TIMEOUT) -> None:
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        max_results: int = 5,
    ) -> list[SearchResult]:
        """
        Search DuckDuckGo for *query* and return up to *max_results* results.

        Args:
            query: The search query string.
            max_results: Maximum number of results to return (capped at 25).

        Returns:
            A list of ``SearchResult`` objects (may be empty on failure).
        """
        max_results = min(max_results, 25)
        log.info("web_search.searching", query=query, max_results=max_results)

        try:
            async with httpx.AsyncClient(
                headers=_DEFAULT_HEADERS,
                follow_redirects=True,
                timeout=self._timeout,
            ) as client:
                resp = await client.post(
                    _DDG_URL,
                    data={"q": query, "b": ""},
                )
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            log.error("web_search.request_failed", error=str(exc))
            return []

        return self._parse_results(resp.text, max_results)

    async def fetch_page(self, url: str) -> str:
        """
        Fetch a URL and return its main text content (HTML stripped).

        Strips scripts, styles, navigation, and other noise elements.
        Truncates output to ``_MAX_PAGE_CHARS`` characters.

        Args:
            url: The URL to fetch.

        Returns:
            Extracted text, or an empty string on failure.
        """
        log.debug("web_search.fetching_page", url=url)

        try:
            async with httpx.AsyncClient(
                headers=_DEFAULT_HEADERS,
                follow_redirects=True,
                timeout=_FETCH_TIMEOUT,
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("web_search.fetch_failed", url=url, error=str(exc))
            return ""

        content_type = resp.headers.get("content-type", "")
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            log.debug("web_search.non_html_content", url=url, content_type=content_type)
            return ""

        return self._extract_text(resp.text)

    # ------------------------------------------------------------------
    # Internal parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_results(html: str, max_results: int) -> list[SearchResult]:
        """Parse DuckDuckGo HTML response into SearchResult objects."""
        soup = BeautifulSoup(html, "html.parser")
        results: list[SearchResult] = []

        for result_div in soup.select(".result"):
            if len(results) >= max_results:
                break

            # Title + URL
            title_tag = result_div.select_one(".result__a")
            if not isinstance(title_tag, Tag):
                continue

            title = title_tag.get_text(strip=True)
            href = title_tag.get("href", "")
            if isinstance(href, list):
                href = href[0] if href else ""

            # DuckDuckGo wraps URLs in a redirect; extract the real one
            url = _extract_real_url(str(href))
            if not url:
                continue

            # Snippet
            snippet_tag = result_div.select_one(".result__snippet")
            snippet = snippet_tag.get_text(strip=True) if isinstance(snippet_tag, Tag) else ""

            results.append(SearchResult(title=title, url=url, snippet=snippet))

        log.info("web_search.results_parsed", count=len(results))
        return results

    @staticmethod
    def _extract_text(html: str) -> str:
        """Strip HTML to plain text, removing noise elements."""
        soup = BeautifulSoup(html, "html.parser")

        # Remove noise tags entirely
        for tag_name in _NOISE_TAGS:
            for tag in soup.find_all(tag_name):
                tag.decompose()

        # Try to find the main content area
        main = (
            soup.find("main")
            or soup.find("article")
            or soup.find("div", {"id": "content"})
            or soup.find("div", {"class": "content"})
            or soup.body
            or soup
        )

        text = main.get_text(separator="\n", strip=True)  # type: ignore[union-attr]

        # Collapse multiple blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Collapse runs of whitespace on the same line
        text = re.sub(r"[ \t]{2,}", " ", text)

        return text[:_MAX_PAGE_CHARS]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_real_url(ddg_href: str) -> str:
    """
    Extract the actual destination URL from a DuckDuckGo redirect link.

    DuckDuckGo HTML results wrap links like:
        //duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com&rut=...
    """
    if not ddg_href:
        return ""

    # Direct URL (no redirect wrapper)
    if ddg_href.startswith("http://") or ddg_href.startswith("https://"):
        return ddg_href

    # DuckDuckGo redirect pattern
    match = re.search(r"uddg=([^&]+)", ddg_href)
    if match:
        from urllib.parse import unquote

        return unquote(match.group(1))

    return ""
