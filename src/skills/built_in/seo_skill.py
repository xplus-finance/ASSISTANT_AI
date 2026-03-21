"""SEO Analyzer Pro — Full website SEO analysis skill."""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any

import structlog

from src.skills.base_skill import BaseSkill, SkillResult

log = structlog.get_logger("assistant.skills.seo")

_USER_AGENT = "XPlus SEO Analyzer/1.0"
_TIMEOUT = 10
_MAX_PAGE_BYTES = 5 * 1024 * 1024  # 5 MB limit


# ---------------------------------------------------------------------------
# SSRF protection
# ---------------------------------------------------------------------------

_PRIVATE_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _is_private_host(hostname: str) -> bool:
    """Return True if hostname resolves to a private/loopback IP."""
    try:
        results = socket.getaddrinfo(hostname, None)
        for _, _, _, _, sockaddr in results:
            addr = ipaddress.ip_address(sockaddr[0])
            for net in _PRIVATE_RANGES:
                if addr in net:
                    return True
    except (socket.gaierror, ValueError):
        return True  # can't resolve → block
    return False


def _validate_url(raw: str) -> str | None:
    """Normalize URL and return it, or None if invalid/private."""
    url = raw.strip()
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    parsed = urllib.parse.urlparse(url)
    if not parsed.hostname:
        return None
    if _is_private_host(parsed.hostname):
        return None
    return url


# ---------------------------------------------------------------------------
# HTML parser
# ---------------------------------------------------------------------------

class _SEOHTMLParser(HTMLParser):
    """Lightweight HTML parser that collects SEO-relevant data."""

    def __init__(self) -> None:
        super().__init__()
        self.title: str = ""
        self.meta_description: str = ""
        self.meta_viewport: str = ""
        self.canonical: str = ""
        self.og: dict[str, str] = {}
        self.twitter: dict[str, str] = {}
        self.h1: list[str] = []
        self.h2: list[str] = []
        self.h3: list[str] = []
        self.images: list[dict[str, str]] = []
        self.links: list[dict[str, str]] = []
        self.meta_robots: str = ""

        # internal tracking
        self._in_tag: str | None = None
        self._tag_text: str = ""
        self._all_meta: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k.lower(): (v or "") for k, v in attrs}
        tag = tag.lower()

        if tag == "title":
            self._in_tag = "title"
            self._tag_text = ""
        elif tag in ("h1", "h2", "h3"):
            self._in_tag = tag
            self._tag_text = ""
        elif tag == "meta":
            name = attr.get("name", attr.get("property", "")).lower()
            content = attr.get("content", "")
            self._all_meta.append({"name": name, "content": content})
            if name == "description":
                self.meta_description = content
            elif name == "viewport":
                self.meta_viewport = content
            elif name == "robots":
                self.meta_robots = content
            elif name.startswith("og:"):
                self.og[name] = content
            elif name.startswith("twitter:"):
                self.twitter[name] = content
        elif tag == "link":
            rel = attr.get("rel", "").lower()
            href = attr.get("href", "")
            if rel == "canonical":
                self.canonical = href
        elif tag == "img":
            self.images.append({
                "src": attr.get("src", ""),
                "alt": attr.get("alt", ""),
            })
        elif tag == "a":
            href = attr.get("href", "")
            if href and not href.startswith(("#", "javascript:", "mailto:", "tel:")):
                self.links.append({
                    "href": href,
                    "rel": attr.get("rel", ""),
                })

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._in_tag == "title" and tag == "title":
            self.title = self._tag_text.strip()
            self._in_tag = None
        elif self._in_tag in ("h1", "h2", "h3") and tag == self._in_tag:
            text = self._tag_text.strip()
            if text:
                getattr(self, self._in_tag).append(text)
            self._in_tag = None

    def handle_data(self, data: str) -> None:
        if self._in_tag:
            self._tag_text += data


# ---------------------------------------------------------------------------
# HTTP fetching
# ---------------------------------------------------------------------------

def _fetch_url(url: str) -> dict[str, Any]:
    """Synchronous HTTP GET — run via asyncio.to_thread."""
    result: dict[str, Any] = {
        "url": url,
        "status": 0,
        "headers": {},
        "body": "",
        "elapsed_ms": 0,
        "size_bytes": 0,
        "is_https": url.startswith("https://"),
        "error": None,
    }

    req = urllib.request.Request(url, headers={
        "User-Agent": _USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,*/*",
        "Accept-Language": "es,en;q=0.9",
    })

    ctx = ssl.create_default_context()

    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT, context=ctx) as resp:
            result["status"] = resp.status
            result["headers"] = dict(resp.headers)
            body = resp.read(_MAX_PAGE_BYTES)
            result["size_bytes"] = len(body)
            charset = resp.headers.get_content_charset() or "utf-8"
            result["body"] = body.decode(charset, errors="replace")
    except urllib.error.HTTPError as exc:
        result["status"] = exc.code
        result["headers"] = dict(exc.headers) if exc.headers else {}
        result["error"] = f"HTTP {exc.code}: {exc.reason}"
        try:
            body = exc.read(_MAX_PAGE_BYTES)
            result["size_bytes"] = len(body)
            result["body"] = body.decode("utf-8", errors="replace")
        except Exception:
            pass
    except urllib.error.URLError as exc:
        result["error"] = str(exc.reason)
    except Exception as exc:
        result["error"] = str(exc)
    finally:
        result["elapsed_ms"] = round((time.monotonic() - start) * 1000)

    return result


def _fetch_robots(url: str) -> str | None:
    """Fetch robots.txt for the domain."""
    parsed = urllib.parse.urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    req = urllib.request.Request(robots_url, headers={"User-Agent": _USER_AGENT})
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT, context=ctx) as resp:
            if resp.status == 200:
                return resp.read(50_000).decode("utf-8", errors="replace")
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def _classify_links(links: list[dict[str, str]], base_url: str) -> tuple[int, int]:
    """Return (internal_count, external_count)."""
    parsed_base = urllib.parse.urlparse(base_url)
    base_domain = parsed_base.netloc.lower()
    internal = 0
    external = 0
    for link in links:
        href = link["href"]
        if href.startswith("/") or href.startswith("./") or href.startswith("../"):
            internal += 1
        else:
            parsed = urllib.parse.urlparse(href)
            if parsed.netloc and parsed.netloc.lower() != base_domain:
                external += 1
            else:
                internal += 1
    return internal, external


def _score_seo(data: dict[str, Any], parser: _SEOHTMLParser) -> tuple[int, list[str]]:
    """Calculate SEO score 0-100 and list of findings."""
    score = 0
    findings: list[str] = []
    max_score = 0

    def check(points: int, condition: bool, good: str, bad: str) -> None:
        nonlocal score, max_score
        max_score += points
        if condition:
            score += points
            findings.append(f"  [OK]  {good}")
        else:
            findings.append(f"  [!!]  {bad}")

    # Title
    title_len = len(parser.title)
    check(10, 0 < title_len, f"Title presente ({title_len} chars)", "Title ausente")
    if title_len > 0:
        check(5, 30 <= title_len <= 65,
              f"Title longitud OK ({title_len} chars)",
              f"Title longitud {'corto' if title_len < 30 else 'largo'} ({title_len} chars, ideal 50-60)")

    # Meta description
    desc_len = len(parser.meta_description)
    check(10, desc_len > 0, f"Meta description presente ({desc_len} chars)", "Meta description ausente")
    if desc_len > 0:
        check(5, 120 <= desc_len <= 165,
              f"Meta description longitud OK ({desc_len} chars)",
              f"Meta description longitud {'corta' if desc_len < 120 else 'larga'} ({desc_len} chars, ideal 150-160)")

    # H1
    check(10, len(parser.h1) == 1,
          f"Un solo H1 ({parser.h1[0][:50]})" if parser.h1 else "Un solo H1",
          f"{'Sin H1' if not parser.h1 else f'{len(parser.h1)} H1s (deberia ser 1)'}")

    # HTTPS
    check(10, data["is_https"], "HTTPS activo", "Sin HTTPS — inseguro")

    # Response time
    elapsed = data["elapsed_ms"]
    check(10, elapsed < 3000,
          f"Respuesta rapida ({elapsed}ms)",
          f"Respuesta lenta ({elapsed}ms, ideal <3000ms)")

    # Page size
    size_kb = data["size_bytes"] / 1024
    check(5, size_kb < 3000,
          f"Pagina liviana ({size_kb:.0f} KB)",
          f"Pagina pesada ({size_kb:.0f} KB, ideal <3MB)")

    # Images alt
    total_imgs = len(parser.images)
    imgs_with_alt = sum(1 for img in parser.images if img["alt"].strip())
    if total_imgs > 0:
        check(10, imgs_with_alt == total_imgs,
              f"Todas las imagenes tienen alt ({imgs_with_alt}/{total_imgs})",
              f"Imagenes sin alt: {total_imgs - imgs_with_alt}/{total_imgs}")
    else:
        max_score += 10
        score += 5
        findings.append("  [--]  Sin imagenes en la pagina")

    # Viewport
    check(5, bool(parser.meta_viewport),
          "Viewport meta tag presente",
          "Sin viewport meta tag — problemas mobile")

    # Canonical
    check(5, bool(parser.canonical),
          f"Canonical definido",
          "Sin canonical URL")

    # Open Graph
    check(5, bool(parser.og),
          f"Open Graph tags ({len(parser.og)} tags)",
          "Sin Open Graph tags")

    # Status code
    check(10, data["status"] == 200,
          f"HTTP {data['status']}",
          f"HTTP {data['status']} — no es 200")

    # Robots meta
    check(5, "noindex" not in parser.meta_robots.lower(),
          "No bloqueado por robots meta",
          "Pagina con noindex — no sera indexada")

    final = round((score / max_score) * 100) if max_score > 0 else 0
    return final, findings


def _grade(score: int) -> str:
    """Letter grade from score."""
    if score >= 90:
        return "A+"
    elif score >= 80:
        return "A"
    elif score >= 70:
        return "B"
    elif score >= 60:
        return "C"
    elif score >= 50:
        return "D"
    return "F"


# ---------------------------------------------------------------------------
# Full analysis builder
# ---------------------------------------------------------------------------

def _build_full_analysis(data: dict[str, Any], parser: _SEOHTMLParser, robots: str | None) -> str:
    """Build the complete analysis text."""
    lines: list[str] = []

    url = data["url"]
    lines.append(f"{'=' * 50}")
    lines.append(f"  SEO ANALYSIS: {url}")
    lines.append(f"{'=' * 50}")

    # Basic info
    lines.append(f"\n--- Informacion General ---")
    lines.append(f"  Status HTTP:      {data['status']}")
    lines.append(f"  Tiempo respuesta: {data['elapsed_ms']}ms")
    lines.append(f"  Tamano pagina:    {data['size_bytes'] / 1024:.1f} KB")
    lines.append(f"  HTTPS:            {'Si' if data['is_https'] else 'No'}")

    # Title
    title_len = len(parser.title)
    lines.append(f"\n--- Title ---")
    lines.append(f"  Contenido: {parser.title or '(vacio)'}")
    lines.append(f"  Longitud:  {title_len} chars {'[OK]' if 50 <= title_len <= 60 else '[Revisar]'}")

    # Meta description
    desc_len = len(parser.meta_description)
    lines.append(f"\n--- Meta Description ---")
    lines.append(f"  Contenido: {parser.meta_description[:200] or '(vacio)'}")
    lines.append(f"  Longitud:  {desc_len} chars {'[OK]' if 150 <= desc_len <= 160 else '[Revisar]'}")

    # Headings
    lines.append(f"\n--- Encabezados ---")
    lines.append(f"  H1: {len(parser.h1)}")
    for h in parser.h1[:5]:
        lines.append(f"      -> {h[:80]}")
    lines.append(f"  H2: {len(parser.h2)}")
    for h in parser.h2[:8]:
        lines.append(f"      -> {h[:80]}")
    lines.append(f"  H3: {len(parser.h3)}")
    if parser.h3:
        lines.append(f"      (primeros 5: {', '.join(h[:40] for h in parser.h3[:5])})")

    # Images
    total_imgs = len(parser.images)
    imgs_with_alt = sum(1 for img in parser.images if img["alt"].strip())
    lines.append(f"\n--- Imagenes ---")
    lines.append(f"  Total:    {total_imgs}")
    lines.append(f"  Con alt:  {imgs_with_alt}")
    lines.append(f"  Sin alt:  {total_imgs - imgs_with_alt}")

    # Links
    internal, external = _classify_links(parser.links, url)
    lines.append(f"\n--- Links ---")
    lines.append(f"  Total:     {len(parser.links)}")
    lines.append(f"  Internos:  {internal}")
    lines.append(f"  Externos:  {external}")

    # Canonical
    lines.append(f"\n--- Canonical ---")
    lines.append(f"  {parser.canonical or '(no definido)'}")

    # Viewport
    lines.append(f"\n--- Mobile ---")
    lines.append(f"  Viewport: {parser.meta_viewport or '(no definido)'}")

    # Open Graph
    lines.append(f"\n--- Open Graph ---")
    if parser.og:
        for k, v in parser.og.items():
            lines.append(f"  {k}: {v[:100]}")
    else:
        lines.append("  (sin tags OG)")

    # Twitter Card
    lines.append(f"\n--- Twitter Card ---")
    if parser.twitter:
        for k, v in parser.twitter.items():
            lines.append(f"  {k}: {v[:100]}")
    else:
        lines.append("  (sin tags Twitter)")

    # Robots.txt
    lines.append(f"\n--- robots.txt ---")
    if robots:
        robot_lines = robots.strip().split("\n")[:15]
        for rl in robot_lines:
            lines.append(f"  {rl}")
        if len(robots.strip().split("\n")) > 15:
            lines.append("  ... (truncado)")
    else:
        lines.append("  (no encontrado o no accesible)")

    # Robots meta
    if parser.meta_robots:
        lines.append(f"\n--- Robots Meta ---")
        lines.append(f"  {parser.meta_robots}")

    # Score
    score, findings = _score_seo(data, parser)
    grade = _grade(score)
    lines.append(f"\n{'=' * 50}")
    lines.append(f"  PUNTUACION SEO: {score}/100 ({grade})")
    lines.append(f"{'=' * 50}")
    for f in findings:
        lines.append(f)
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Skill class
# ---------------------------------------------------------------------------

class SEOSkill(BaseSkill):

    @property
    def name(self) -> str:
        return "seo"

    @property
    def description(self) -> str:
        return "SEO Analyzer Pro — analisis completo de SEO para cualquier URL"

    @property
    def natural_patterns(self) -> dict[str, list[str]]:
        return {
            "analizar": [
                r"(?:analiza|revisa|checa|eval[uú]a)\s+(?:el\s+)?seo\s+(?:de\s+)?(?P<args>https?://\S+)",
                r"(?:c[oó]mo\s+est[aá]|qu[eé]\s+tal)\s+(?:el\s+)?seo\s+(?:de\s+)?(?P<args>https?://\S+)",
                r"(?:analiza|revisa|checa)\s+(?:la\s+)?(?:p[aá]gina|web|sitio)\s+(?P<args>https?://\S+)",
                r"(?:an[aá]lisis|audit(?:or[ií]a)?)\s+seo\s+(?:de\s+|para\s+)?(?P<args>https?://\S+)",
            ],
            "comparar": [
                r"(?:compara|comparar)\s+(?:el\s+)?seo\s+(?:de\s+)?(?P<args>https?://\S+\s+(?:con|vs?\.?)\s+https?://\S+)",
            ],
            "meta": [
                r"(?:mu[eé]strame|ver|dame|revisa)\s+(?:los?\s+)?meta\s*tags?\s+(?:de\s+)?(?P<args>https?://\S+)",
            ],
            "velocidad": [
                r"(?:velocidad|speed|rendimiento|performance)\s+(?:de\s+)?(?P<args>https?://\S+)",
                r"(?:qu[eé]\s+tan\s+r[aá]pid[ao]|c[oó]mo\s+carga)\s+(?P<args>https?://\S+)",
            ],
        }

    @property
    def triggers(self) -> list[str]:
        return ["!seo", "!analizar", "!analyze", "!lighthouse", "!meta", "!keywords"]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        parts = args.strip().split(maxsplit=1)
        if not parts:
            return self._help()

        sub = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""

        # Route subcommands
        if sub == "analizar":
            return await self._full_analysis(rest)
        elif sub == "meta":
            return await self._meta_check(rest)
        elif sub == "headers":
            return await self._headers_check(rest)
        elif sub == "links":
            return await self._links_check(rest)
        elif sub in ("imagenes", "images"):
            return await self._images_check(rest)
        elif sub in ("velocidad", "speed"):
            return await self._speed_check(rest)
        elif sub in ("comparar", "compare"):
            return await self._compare(rest)
        elif sub in ("reporte", "report"):
            return await self._report(rest)
        elif sub in ("ayuda", "help"):
            return self._help()
        else:
            # Treat the entire args as a URL for full analysis
            url_candidate = args.strip()
            if "." in url_candidate.split("/")[0].split("?")[0]:
                return await self._full_analysis(url_candidate)
            return self._help()

    def _help(self) -> SkillResult:
        msg = (
            "**SEO Analyzer Pro**\n\n"
            "Uso:\n"
            "  `!seo <url>`                   — Analisis SEO completo\n"
            "  `!seo analizar <url>`          — Analisis SEO completo\n"
            "  `!seo meta <url>`              — Solo meta tags\n"
            "  `!seo headers <url>`           — Headers HTTP\n"
            "  `!seo links <url>`             — Analisis de links\n"
            "  `!seo imagenes <url>`          — Analisis de imagenes\n"
            "  `!seo velocidad <url>`         — Velocidad y tamano\n"
            "  `!seo comparar <url1> | <url2>` — Comparar dos URLs\n"
            "  `!seo reporte <url>`           — Reporte completo\n"
        )
        return SkillResult(success=True, message=msg)

    # ------------------------------------------------------------------
    # Subcommand implementations
    # ------------------------------------------------------------------

    async def _full_analysis(self, raw_url: str) -> SkillResult:
        url = _validate_url(raw_url)
        if not url:
            return SkillResult(success=False, message="URL invalida o apunta a una red privada.")

        log.info("seo.full_analysis", url=url)

        data, robots = await asyncio.gather(
            asyncio.to_thread(_fetch_url, url),
            asyncio.to_thread(_fetch_robots, url),
        )

        if data["error"] and data["status"] == 0:
            return SkillResult(success=False, message=f"No se pudo acceder a {url}: {data['error']}")

        parser = _SEOHTMLParser()
        try:
            parser.feed(data["body"])
        except Exception as exc:
            log.warning("seo.parse_error", url=url, error=str(exc))

        report = _build_full_analysis(data, parser, robots)
        return SkillResult(success=True, message=f"```\n{report}\n```")

    async def _meta_check(self, raw_url: str) -> SkillResult:
        url = _validate_url(raw_url)
        if not url:
            return SkillResult(success=False, message="URL invalida o apunta a una red privada.")

        log.info("seo.meta_check", url=url)
        data = await asyncio.to_thread(_fetch_url, url)

        if data["error"] and data["status"] == 0:
            return SkillResult(success=False, message=f"No se pudo acceder: {data['error']}")

        parser = _SEOHTMLParser()
        try:
            parser.feed(data["body"])
        except Exception:
            pass

        title_len = len(parser.title)
        desc_len = len(parser.meta_description)

        lines = [
            f"**Meta Tags: {url}**\n",
            f"**Title** ({title_len} chars):",
            f"  {parser.title or '(vacio)'}",
            f"  Ideal: 50-60 chars {'[OK]' if 50 <= title_len <= 60 else '[Revisar]'}\n",
            f"**Meta Description** ({desc_len} chars):",
            f"  {parser.meta_description[:200] or '(vacio)'}",
            f"  Ideal: 150-160 chars {'[OK]' if 150 <= desc_len <= 160 else '[Revisar]'}\n",
            f"**Canonical:** {parser.canonical or '(no definido)'}",
            f"**Viewport:** {parser.meta_viewport or '(no definido)'}",
            f"**Robots:** {parser.meta_robots or '(no definido)'}",
        ]

        if parser.og:
            lines.append("\n**Open Graph:**")
            for k, v in parser.og.items():
                lines.append(f"  {k}: {v[:120]}")

        if parser.twitter:
            lines.append("\n**Twitter Card:**")
            for k, v in parser.twitter.items():
                lines.append(f"  {k}: {v[:120]}")

        return SkillResult(success=True, message="\n".join(lines))

    async def _headers_check(self, raw_url: str) -> SkillResult:
        url = _validate_url(raw_url)
        if not url:
            return SkillResult(success=False, message="URL invalida o apunta a una red privada.")

        log.info("seo.headers_check", url=url)
        data = await asyncio.to_thread(_fetch_url, url)

        if data["error"] and data["status"] == 0:
            return SkillResult(success=False, message=f"No se pudo acceder: {data['error']}")

        lines = [
            f"**HTTP Headers: {url}**",
            f"Status: {data['status']}",
            f"Tiempo: {data['elapsed_ms']}ms\n",
        ]

        # Security headers check
        headers = {k.lower(): v for k, v in data["headers"].items()}
        security_headers = {
            "strict-transport-security": "HSTS",
            "content-security-policy": "CSP",
            "x-content-type-options": "X-Content-Type-Options",
            "x-frame-options": "X-Frame-Options",
            "x-xss-protection": "X-XSS-Protection",
            "referrer-policy": "Referrer-Policy",
            "permissions-policy": "Permissions-Policy",
        }

        lines.append("**Headers de Seguridad:**")
        for header_key, label in security_headers.items():
            value = headers.get(header_key)
            if value:
                lines.append(f"  [OK] {label}: {value[:80]}")
            else:
                lines.append(f"  [!!] {label}: AUSENTE")

        # SEO-relevant headers
        lines.append("\n**Headers SEO-relevantes:**")
        seo_keys = ["content-type", "cache-control", "server", "x-robots-tag",
                     "link", "vary", "content-encoding", "content-length"]
        for key in seo_keys:
            val = headers.get(key)
            if val:
                lines.append(f"  {key}: {val[:100]}")

        # All headers
        lines.append("\n**Todos los headers:**")
        for k, v in data["headers"].items():
            lines.append(f"  {k}: {v[:120]}")

        return SkillResult(success=True, message="\n".join(lines))

    async def _links_check(self, raw_url: str) -> SkillResult:
        url = _validate_url(raw_url)
        if not url:
            return SkillResult(success=False, message="URL invalida o apunta a una red privada.")

        log.info("seo.links_check", url=url)
        data = await asyncio.to_thread(_fetch_url, url)

        if data["error"] and data["status"] == 0:
            return SkillResult(success=False, message=f"No se pudo acceder: {data['error']}")

        parser = _SEOHTMLParser()
        try:
            parser.feed(data["body"])
        except Exception:
            pass

        internal, external = _classify_links(parser.links, url)

        lines = [
            f"**Analisis de Links: {url}**\n",
            f"Total links:  {len(parser.links)}",
            f"Internos:     {internal}",
            f"Externos:     {external}",
        ]

        # List nofollow links
        nofollow = [l for l in parser.links if "nofollow" in l["rel"].lower()]
        if nofollow:
            lines.append(f"\n**Links nofollow ({len(nofollow)}):**")
            for l in nofollow[:10]:
                lines.append(f"  {l['href'][:100]}")

        # External links
        parsed_base = urllib.parse.urlparse(url)
        base_domain = parsed_base.netloc.lower()
        ext_links = [
            l for l in parser.links
            if urllib.parse.urlparse(l["href"]).netloc
            and urllib.parse.urlparse(l["href"]).netloc.lower() != base_domain
        ]
        if ext_links:
            lines.append(f"\n**Links externos (primeros 20):**")
            for l in ext_links[:20]:
                lines.append(f"  {l['href'][:120]}")

        # Internal links sample
        int_links = [l for l in parser.links if l not in ext_links]
        if int_links:
            lines.append(f"\n**Links internos (primeros 20):**")
            for l in int_links[:20]:
                lines.append(f"  {l['href'][:120]}")

        return SkillResult(success=True, message="\n".join(lines))

    async def _images_check(self, raw_url: str) -> SkillResult:
        url = _validate_url(raw_url)
        if not url:
            return SkillResult(success=False, message="URL invalida o apunta a una red privada.")

        log.info("seo.images_check", url=url)
        data = await asyncio.to_thread(_fetch_url, url)

        if data["error"] and data["status"] == 0:
            return SkillResult(success=False, message=f"No se pudo acceder: {data['error']}")

        parser = _SEOHTMLParser()
        try:
            parser.feed(data["body"])
        except Exception:
            pass

        total = len(parser.images)
        with_alt = sum(1 for img in parser.images if img["alt"].strip())
        without_alt = total - with_alt

        lines = [
            f"**Analisis de Imagenes: {url}**\n",
            f"Total imagenes:  {total}",
            f"Con alt text:    {with_alt}",
            f"Sin alt text:    {without_alt}",
        ]

        if without_alt > 0:
            lines.append(f"\n**Imagenes SIN alt (afecta SEO y accesibilidad):**")
            count = 0
            for img in parser.images:
                if not img["alt"].strip():
                    src = img["src"][:120] if img["src"] else "(sin src)"
                    lines.append(f"  {src}")
                    count += 1
                    if count >= 25:
                        remaining = without_alt - count
                        if remaining > 0:
                            lines.append(f"  ... y {remaining} mas")
                        break

        if with_alt > 0:
            lines.append(f"\n**Imagenes CON alt (primeras 15):**")
            count = 0
            for img in parser.images:
                if img["alt"].strip():
                    src = img["src"][:80] if img["src"] else "(sin src)"
                    alt = img["alt"][:60]
                    lines.append(f"  {src}")
                    lines.append(f"    alt: \"{alt}\"")
                    count += 1
                    if count >= 15:
                        break

        return SkillResult(success=True, message="\n".join(lines))

    async def _speed_check(self, raw_url: str) -> SkillResult:
        url = _validate_url(raw_url)
        if not url:
            return SkillResult(success=False, message="URL invalida o apunta a una red privada.")

        log.info("seo.speed_check", url=url)
        data = await asyncio.to_thread(_fetch_url, url)

        if data["error"] and data["status"] == 0:
            return SkillResult(success=False, message=f"No se pudo acceder: {data['error']}")

        elapsed = data["elapsed_ms"]
        size_kb = data["size_bytes"] / 1024
        size_mb = size_kb / 1024

        if elapsed < 500:
            speed_rating = "Excelente"
        elif elapsed < 1000:
            speed_rating = "Buena"
        elif elapsed < 2000:
            speed_rating = "Aceptable"
        elif elapsed < 3000:
            speed_rating = "Lenta"
        else:
            speed_rating = "Muy lenta"

        if size_kb < 500:
            size_rating = "Liviana"
        elif size_kb < 1500:
            size_rating = "Normal"
        elif size_kb < 3000:
            size_rating = "Pesada"
        else:
            size_rating = "Muy pesada"

        headers = {k.lower(): v for k, v in data["headers"].items()}

        lines = [
            f"**Velocidad y Tamano: {url}**\n",
            f"**Tiempo de respuesta:** {elapsed}ms ({speed_rating})",
            f"**Tamano de pagina:**    {size_kb:.1f} KB ({size_mb:.2f} MB) ({size_rating})",
            f"**Status HTTP:**         {data['status']}",
        ]

        # Compression
        encoding = headers.get("content-encoding", "")
        if encoding:
            lines.append(f"\n**Compresion:** {encoding} [OK]")
        else:
            lines.append(f"\n**Compresion:** No detectada [!!] — activar gzip/brotli mejoraria la carga")

        # Cache
        cache = headers.get("cache-control", "")
        if cache:
            lines.append(f"**Cache-Control:** {cache}")
        else:
            lines.append(f"**Cache-Control:** No definido [!!] — configurar cache mejoraria rendimiento")

        # Server
        server = headers.get("server", "")
        if server:
            lines.append(f"**Servidor:** {server}")

        # Recommendations
        lines.append(f"\n**Recomendaciones:**")
        if elapsed >= 2000:
            lines.append("  - Optimizar tiempo de respuesta del servidor (TTFB)")
        if size_kb >= 1500:
            lines.append("  - Reducir tamano de pagina (minificar HTML/CSS/JS)")
        if not encoding:
            lines.append("  - Habilitar compresion gzip o brotli")
        if not cache:
            lines.append("  - Configurar Cache-Control headers")
        if elapsed < 2000 and size_kb < 1500 and encoding and cache:
            lines.append("  Todo se ve bien. Buen trabajo!")

        return SkillResult(success=True, message="\n".join(lines))

    async def _compare(self, raw: str) -> SkillResult:
        """Compare SEO of two URLs separated by |."""
        separator = "|"
        if separator not in raw:
            return SkillResult(
                success=False,
                message="Uso: `!seo comparar <url1> | <url2>`\nSepara las URLs con |",
            )

        parts = raw.split(separator, 1)
        raw_url1 = parts[0].strip()
        raw_url2 = parts[1].strip()

        url1 = _validate_url(raw_url1)
        url2 = _validate_url(raw_url2)

        if not url1:
            return SkillResult(success=False, message=f"URL1 invalida o privada: {raw_url1}")
        if not url2:
            return SkillResult(success=False, message=f"URL2 invalida o privada: {raw_url2}")

        log.info("seo.compare", url1=url1, url2=url2)

        # Fetch both in parallel
        data1, data2, robots1, robots2 = await asyncio.gather(
            asyncio.to_thread(_fetch_url, url1),
            asyncio.to_thread(_fetch_url, url2),
            asyncio.to_thread(_fetch_robots, url1),
            asyncio.to_thread(_fetch_robots, url2),
        )

        results = []
        for label, data, robots in [("URL1", data1, robots1), ("URL2", data2, robots2)]:
            if data["error"] and data["status"] == 0:
                results.append((label, data, None, 0))
                continue
            parser = _SEOHTMLParser()
            try:
                parser.feed(data["body"])
            except Exception:
                pass
            score, _ = _score_seo(data, parser)
            results.append((label, data, parser, score))

        lines = [
            f"{'=' * 55}",
            f"  SEO COMPARACION",
            f"{'=' * 55}",
            "",
        ]

        # Build comparison table
        label1 = urllib.parse.urlparse(url1).netloc[:25]
        label2 = urllib.parse.urlparse(url2).netloc[:25]
        col_w = 28

        def row(metric: str, val1: str, val2: str) -> str:
            return f"  {metric:<22} {val1:<{col_w}} {val2:<{col_w}}"

        lines.append(row("Metrica", label1, label2))
        lines.append("  " + "-" * (22 + col_w * 2))

        _, d1, p1, s1 = results[0]
        _, d2, p2, s2 = results[1]

        lines.append(row("Score SEO", f"{s1}/100 ({_grade(s1)})", f"{s2}/100 ({_grade(s2)})"))
        lines.append(row("Status HTTP", str(d1["status"]), str(d2["status"])))
        lines.append(row("Tiempo (ms)", str(d1["elapsed_ms"]), str(d2["elapsed_ms"])))
        lines.append(row("Tamano (KB)", f"{d1['size_bytes']/1024:.1f}", f"{d2['size_bytes']/1024:.1f}"))
        lines.append(row("HTTPS", "Si" if d1["is_https"] else "No", "Si" if d2["is_https"] else "No"))

        if p1 and p2:
            lines.append(row("Title (chars)", str(len(p1.title)), str(len(p2.title))))
            lines.append(row("Meta Desc (chars)", str(len(p1.meta_description)), str(len(p2.meta_description))))
            lines.append(row("H1 count", str(len(p1.h1)), str(len(p2.h1))))
            lines.append(row("H2 count", str(len(p1.h2)), str(len(p2.h2))))
            lines.append(row("Imagenes", str(len(p1.images)), str(len(p2.images))))

            alt1 = sum(1 for i in p1.images if i["alt"].strip())
            alt2 = sum(1 for i in p2.images if i["alt"].strip())
            t1 = len(p1.images)
            t2 = len(p2.images)
            lines.append(row("Imgs con alt", f"{alt1}/{t1}" if t1 else "N/A", f"{alt2}/{t2}" if t2 else "N/A"))

            int1, ext1 = _classify_links(p1.links, url1)
            int2, ext2 = _classify_links(p2.links, url2)
            lines.append(row("Links internos", str(int1), str(int2)))
            lines.append(row("Links externos", str(ext1), str(ext2)))
            lines.append(row("Viewport", "Si" if p1.meta_viewport else "No", "Si" if p2.meta_viewport else "No"))
            lines.append(row("Canonical", "Si" if p1.canonical else "No", "Si" if p2.canonical else "No"))
            lines.append(row("Open Graph", f"{len(p1.og)} tags", f"{len(p2.og)} tags"))
            lines.append(row("Twitter Card", f"{len(p1.twitter)} tags", f"{len(p2.twitter)} tags"))
            lines.append(row("robots.txt", "Si" if robots1 else "No", "Si" if robots2 else "No"))

        # Winner
        lines.append("")
        if s1 > s2:
            diff = s1 - s2
            lines.append(f"  Ganador: {label1} (+{diff} puntos)")
        elif s2 > s1:
            diff = s2 - s1
            lines.append(f"  Ganador: {label2} (+{diff} puntos)")
        else:
            lines.append(f"  Empate: ambos con {s1}/100")

        lines.append("")

        return SkillResult(success=True, message=f"```\n" + "\n".join(lines) + "\n```")

    async def _report(self, raw_url: str) -> SkillResult:
        """Comprehensive report combining all checks."""
        url = _validate_url(raw_url)
        if not url:
            return SkillResult(success=False, message="URL invalida o apunta a una red privada.")

        log.info("seo.report", url=url)

        data, robots = await asyncio.gather(
            asyncio.to_thread(_fetch_url, url),
            asyncio.to_thread(_fetch_robots, url),
        )

        if data["error"] and data["status"] == 0:
            return SkillResult(success=False, message=f"No se pudo acceder a {url}: {data['error']}")

        parser = _SEOHTMLParser()
        try:
            parser.feed(data["body"])
        except Exception:
            pass

        headers = {k.lower(): v for k, v in data["headers"].items()}
        score, findings = _score_seo(data, parser)
        grade = _grade(score)
        internal, external = _classify_links(parser.links, url)
        total_imgs = len(parser.images)
        imgs_with_alt = sum(1 for img in parser.images if img["alt"].strip())
        elapsed = data["elapsed_ms"]
        size_kb = data["size_bytes"] / 1024

        lines = [
            f"{'#' * 55}",
            f"  REPORTE SEO COMPLETO",
            f"  {url}",
            f"  Fecha: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"{'#' * 55}",
            "",
            f"  PUNTUACION FINAL: {score}/100 ({grade})",
            "",
        ]

        # 1. General
        lines.append(f"{'=' * 50}")
        lines.append("  1. INFORMACION GENERAL")
        lines.append(f"{'=' * 50}")
        lines.append(f"  Status HTTP:      {data['status']}")
        lines.append(f"  HTTPS:            {'Si' if data['is_https'] else 'No [CRITICO]'}")
        lines.append(f"  Tiempo respuesta: {elapsed}ms")
        lines.append(f"  Tamano pagina:    {size_kb:.1f} KB")
        server = headers.get("server", "No revelado")
        lines.append(f"  Servidor:         {server}")
        encoding = headers.get("content-encoding", "No")
        lines.append(f"  Compresion:       {encoding}")

        # 2. Meta Tags
        lines.append(f"\n{'=' * 50}")
        lines.append("  2. META TAGS")
        lines.append(f"{'=' * 50}")
        title_len = len(parser.title)
        desc_len = len(parser.meta_description)
        lines.append(f"  Title ({title_len} chars): {parser.title or '(vacio)'}")
        lines.append(f"  Description ({desc_len} chars): {parser.meta_description[:150] or '(vacio)'}")
        lines.append(f"  Canonical: {parser.canonical or '(no definido)'}")
        lines.append(f"  Viewport: {parser.meta_viewport or '(no definido)'}")
        lines.append(f"  Robots meta: {parser.meta_robots or '(no definido)'}")

        # 3. Headings
        lines.append(f"\n{'=' * 50}")
        lines.append("  3. ESTRUCTURA DE ENCABEZADOS")
        lines.append(f"{'=' * 50}")
        lines.append(f"  H1: {len(parser.h1)}")
        for h in parser.h1[:3]:
            lines.append(f"    -> {h[:70]}")
        lines.append(f"  H2: {len(parser.h2)}")
        for h in parser.h2[:5]:
            lines.append(f"    -> {h[:70]}")
        lines.append(f"  H3: {len(parser.h3)}")

        # 4. Links
        lines.append(f"\n{'=' * 50}")
        lines.append("  4. LINKS")
        lines.append(f"{'=' * 50}")
        lines.append(f"  Total:    {len(parser.links)}")
        lines.append(f"  Internos: {internal}")
        lines.append(f"  Externos: {external}")

        # 5. Images
        lines.append(f"\n{'=' * 50}")
        lines.append("  5. IMAGENES")
        lines.append(f"{'=' * 50}")
        lines.append(f"  Total:   {total_imgs}")
        lines.append(f"  Con alt: {imgs_with_alt}")
        lines.append(f"  Sin alt: {total_imgs - imgs_with_alt}")

        # 6. Social
        lines.append(f"\n{'=' * 50}")
        lines.append("  6. SOCIAL / OPEN GRAPH")
        lines.append(f"{'=' * 50}")
        if parser.og:
            for k, v in parser.og.items():
                lines.append(f"  {k}: {v[:100]}")
        else:
            lines.append("  Sin tags Open Graph")
        if parser.twitter:
            for k, v in parser.twitter.items():
                lines.append(f"  {k}: {v[:100]}")
        else:
            lines.append("  Sin tags Twitter Card")

        # 7. Security headers
        lines.append(f"\n{'=' * 50}")
        lines.append("  7. HEADERS DE SEGURIDAD")
        lines.append(f"{'=' * 50}")
        sec_headers = {
            "strict-transport-security": "HSTS",
            "content-security-policy": "CSP",
            "x-content-type-options": "X-Content-Type-Options",
            "x-frame-options": "X-Frame-Options",
            "x-xss-protection": "X-XSS-Protection",
            "referrer-policy": "Referrer-Policy",
        }
        for hk, label in sec_headers.items():
            val = headers.get(hk)
            status = f"[OK] {val[:60]}" if val else "[!!] AUSENTE"
            lines.append(f"  {label}: {status}")

        # 8. robots.txt
        lines.append(f"\n{'=' * 50}")
        lines.append("  8. ROBOTS.TXT")
        lines.append(f"{'=' * 50}")
        if robots:
            for rl in robots.strip().split("\n")[:10]:
                lines.append(f"  {rl}")
        else:
            lines.append("  No encontrado")

        # 9. Findings & Score
        lines.append(f"\n{'=' * 50}")
        lines.append("  9. EVALUACION DETALLADA")
        lines.append(f"{'=' * 50}")
        for f in findings:
            lines.append(f)

        lines.append(f"\n{'#' * 55}")
        lines.append(f"  PUNTUACION FINAL: {score}/100 ({grade})")
        lines.append(f"{'#' * 55}")

        # Recommendations
        lines.append(f"\n  RECOMENDACIONES PRIORITARIAS:")
        recs: list[str] = []
        if not data["is_https"]:
            recs.append("  1. CRITICO: Migrar a HTTPS")
        if not parser.title:
            recs.append("  2. Agregar title tag")
        elif title_len < 30 or title_len > 65:
            recs.append(f"  2. Ajustar longitud del title ({title_len} chars -> 50-60)")
        if not parser.meta_description:
            recs.append("  3. Agregar meta description")
        elif desc_len < 120 or desc_len > 165:
            recs.append(f"  3. Ajustar longitud de meta description ({desc_len} chars -> 150-160)")
        if len(parser.h1) != 1:
            recs.append(f"  4. {'Agregar un H1' if not parser.h1 else 'Reducir a un solo H1'}")
        if total_imgs > 0 and imgs_with_alt < total_imgs:
            recs.append(f"  5. Agregar alt text a {total_imgs - imgs_with_alt} imagenes")
        if not parser.meta_viewport:
            recs.append("  6. Agregar viewport meta tag para mobile")
        if not parser.og:
            recs.append("  7. Agregar Open Graph tags para redes sociales")
        if not parser.canonical:
            recs.append("  8. Definir canonical URL")
        if elapsed >= 2000:
            recs.append(f"  9. Optimizar velocidad ({elapsed}ms es lento)")
        if not headers.get("content-encoding"):
            recs.append("  10. Habilitar compresion gzip/brotli")

        if recs:
            for r in recs:
                lines.append(r)
        else:
            lines.append("  Todo se ve excelente. Buen trabajo!")

        lines.append("")

        return SkillResult(success=True, message=f"```\n" + "\n".join(lines) + "\n```")
