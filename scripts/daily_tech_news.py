#!/usr/bin/env python3
"""Top 5 noticias diarias de programacion, IA y desarrollo de software.

Corre via cron a las 8:30 AM ET.
Envia resumen por Telegram.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from html import unescape
from pathlib import Path
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# ENV
# ---------------------------------------------------------------------------
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _load_env() -> None:
    if not _ENV_FILE.exists():
        return
    for line in _ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and value and key not in os.environ:
            os.environ[key] = value


_load_env()

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("AUTHORIZED_CHAT_ID", "")
ET = ZoneInfo("America/New_York")

# ---------------------------------------------------------------------------
# Telegram send
# ---------------------------------------------------------------------------

def _tg_send(text: str) -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        print("TELEGRAM_BOT_TOKEN o AUTHORIZED_CHAT_ID no configurados", file=sys.stderr)
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except Exception as exc:
        print(f"Error enviando a Telegram: {exc}", file=sys.stderr)
        return False

# ---------------------------------------------------------------------------
# News fetching — DuckDuckGo HTML scraping (no API key needed)
# ---------------------------------------------------------------------------

_SEARCHES = [
    "international programming technology news today global",
    "artificial intelligence AI news today worldwide",
    "software development industry news today global",
]

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    clean = re.sub(r"<[^>]+>", "", text)
    return unescape(clean).strip()


def _search_ddg(query: str, max_results: int = 5) -> list[dict]:
    """Scrape DuckDuckGo HTML for news results."""
    results = []
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"DDG search failed for '{query}': {exc}", file=sys.stderr)
        return results

    # Extract result blocks: <a class="result__a" href="...">title</a>
    # and <a class="result__snippet">...</a>
    link_pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    snippet_pattern = re.compile(
        r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL,
    )

    links = link_pattern.findall(html)
    snippets = snippet_pattern.findall(html)

    for i, (href, title_html) in enumerate(links[:max_results]):
        title = _strip_html(title_html)
        snippet = _strip_html(snippets[i]) if i < len(snippets) else ""
        # DDG wraps URLs in a redirect; extract actual URL
        actual_url = href
        if "uddg=" in href:
            match = re.search(r"uddg=([^&]+)", href)
            if match:
                actual_url = urllib.parse.unquote(match.group(1))
        if title and actual_url:
            results.append({"title": title, "url": actual_url, "snippet": snippet})

    return results


def _fetch_news() -> list[dict]:
    """Fetch and deduplicate news from multiple searches."""
    all_results = []
    seen_urls = set()

    for query in _SEARCHES:
        results = _search_ddg(query, max_results=4)
        for r in results:
            # Deduplicate by domain+path
            clean_url = r["url"].split("?")[0].rstrip("/")
            if clean_url not in seen_urls:
                seen_urls.add(clean_url)
                all_results.append(r)

    # Return top 5
    return all_results[:5]


# ---------------------------------------------------------------------------
# Format message
# ---------------------------------------------------------------------------

def _format_news(news: list[dict]) -> str:
    now = datetime.now(ET)
    date_str = now.strftime("%A %d de %B, %Y")

    lines = [
        f"📰 <b>Top 5 Noticias Tech — {date_str}</b>",
        "",
    ]

    if not news:
        lines.append("⚠️ No pude obtener noticias hoy. Revisa la conexión.")
        return "\n".join(lines)

    for i, item in enumerate(news, 1):
        title = item["title"][:120]
        url = item["url"]
        snippet = item.get("snippet", "")[:200]
        lines.append(f"<b>{i}.</b> <a href=\"{url}\">{title}</a>")
        if snippet:
            lines.append(f"   <i>{snippet}</i>")
        lines.append("")

    lines.append("🌐 <i>Temas: Programación, IA, Desarrollo de Software — Ámbito Internacional</i>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"[{datetime.now(ET)}] Fetching daily tech news...")
    news = _fetch_news()
    print(f"Found {len(news)} news items")

    message = _format_news(news)
    ok = _tg_send(message)

    if ok:
        print("Tech news sent to Telegram successfully")
    else:
        print("Failed to send tech news", file=sys.stderr)


if __name__ == "__main__":
    main()
