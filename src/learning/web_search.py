"""Web search via DuckDuckGo HTML and page content extraction."""

from __future__ import annotations

import ipaddress
import re
import socket
import time
from collections import OrderedDict
from dataclasses import dataclass
from urllib.parse import quote_plus, urlparse

import httpx
import structlog
from bs4 import BeautifulSoup, Tag

log = structlog.get_logger("assistant.learning.web_search")

_DDG_URL = "https://html.duckduckgo.com/html/"
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
}

_FETCH_TIMEOUT = 30.0  # seconds
_SEARCH_TIMEOUT = 20.0
_CACHE_TTL_SECS = 3600.0  # 1 hour
_CACHE_MAX_ENTRIES = 100


def _is_safe_url(url: str) -> bool:

    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False
        # Resolve hostname to IP
        ip = ipaddress.ip_address(socket.gethostbyname(hostname))
        # Block private, loopback, link-local
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False
        return True
    except (socket.gaierror, ValueError):
        return False

_NOISE_TAGS = {"script", "style", "nav", "header", "footer", "aside", "form", "noscript", "svg"}

_MAX_PAGE_CHARS = 15_000


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str


class WebSearcher:

    def __init__(self, timeout: float = _SEARCH_TIMEOUT) -> None:
        self._timeout = timeout
        # In-memory LRU cache: key -> (result, inserted_at)
        # Shared for both search results (key = "search:<query>:<max>") and
        # fetched pages (key = "page:<url>").  Max 100 entries, 1-hour TTL.
        self._cache: OrderedDict[str, tuple[object, float]] = OrderedDict()

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _cache_get(self, key: str) -> object | None:
        """Return cached value if present and not expired, else None."""
        entry = self._cache.get(key)
        if entry is None:
            return None
        value, inserted_at = entry
        if time.monotonic() - inserted_at > _CACHE_TTL_SECS:
            del self._cache[key]
            return None
        # Move to end (most-recently-used)
        self._cache.move_to_end(key)
        return value

    def _cache_set(self, key: str, value: object) -> None:
        """Store value in cache, evicting the oldest entry when full."""
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (value, time.monotonic())
        if len(self._cache) > _CACHE_MAX_ENTRIES:
            self._cache.popitem(last=False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        max_results: int = 5,
    ) -> list[SearchResult]:
        max_results = min(max_results, 25)

        cache_key = f"search:{query}:{max_results}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            log.debug("web_search.cache_hit", query=query)
            return cached  # type: ignore[return-value]

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

        results = self._parse_results(resp.text, max_results)
        self._cache_set(cache_key, results)
        return results

    async def fetch_page(self, url: str) -> str:
        cache_key = f"page:{url}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            log.debug("web_search.page_cache_hit", url=url)
            return cached  # type: ignore[return-value]

        log.debug("web_search.fetching_page", url=url)

        if not _is_safe_url(url):
            log.warning("web_search.blocked_unsafe_url", url=url)
            return ""

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

        text = self._extract_text(resp.text)
        self._cache_set(cache_key, text)
        return text

    @staticmethod
    def _parse_results(html: str, max_results: int) -> list[SearchResult]:
        soup = BeautifulSoup(html, "html.parser")
        results: list[SearchResult] = []

        for result_div in soup.select(".result"):
            if len(results) >= max_results:
                break

            title_tag = result_div.select_one(".result__a")
            if not isinstance(title_tag, Tag):
                continue

            title = title_tag.get_text(strip=True)
            href = title_tag.get("href", "")
            if isinstance(href, list):
                href = href[0] if href else ""

            url = _extract_real_url(str(href))
            if not url:
                continue

            snippet_tag = result_div.select_one(".result__snippet")
            snippet = snippet_tag.get_text(strip=True) if isinstance(snippet_tag, Tag) else ""

            results.append(SearchResult(title=title, url=url, snippet=snippet))

        log.info("web_search.results_parsed", count=len(results))
        return results

    @staticmethod
    def _extract_text(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")

        for tag_name in _NOISE_TAGS:
            for tag in soup.find_all(tag_name):
                tag.decompose()

        main = (
            soup.find("main")
            or soup.find("article")
            or soup.find("div", {"id": "content"})
            or soup.find("div", {"class": "content"})
            or soup.body
            or soup
        )

        text = main.get_text(separator="\n", strip=True)  # type: ignore[union-attr]

        text = re.sub(r"\n{3,}", "\n\n", text)

        text = re.sub(r"[ \t]{2,}", " ", text)

        return text[:_MAX_PAGE_CHARS]


def _extract_real_url(ddg_href: str) -> str:
    if not ddg_href:
        return ""

    if ddg_href.startswith("http://") or ddg_href.startswith("https://"):
        return ddg_href

    match = re.search(r"uddg=([^&]+)", ddg_href)
    if match:
        from urllib.parse import unquote

        return unquote(match.group(1))

    return ""
