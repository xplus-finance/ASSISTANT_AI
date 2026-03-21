"""Social media scheduler skill: create, schedule, manage and preview posts."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import structlog

from src.memory.engine import MemoryEngine
from src.skills.base_skill import BaseSkill, SkillResult

log = structlog.get_logger("assistant.skills.social_media")

_TZ_DISPLAY = ZoneInfo("US/Eastern")
_TZ_UTC = timezone.utc

_VALID_PLATFORMS = {"twitter", "x", "linkedin", "facebook", "instagram", "all"}

_PLATFORM_LABELS: dict[str, str] = {
    "twitter": "Twitter/X",
    "x": "Twitter/X",
    "linkedin": "LinkedIn",
    "facebook": "Facebook",
    "instagram": "Instagram",
    "all": "Todas",
}

_PLATFORM_LIMITS: dict[str, int] = {
    "twitter": 280,
    "x": 280,
    "linkedin": 3000,
    "facebook": 63206,
    "instagram": 2200,
}

# Common hashtag keywords per topic area — used for simple suggestion heuristics.
_HASHTAG_HINTS: dict[str, list[str]] = {
    "tech": ["#Tech", "#Technology", "#Innovation", "#Digital"],
    "ai": ["#AI", "#ArtificialIntelligence", "#MachineLearning", "#DeepLearning"],
    "marketing": ["#Marketing", "#DigitalMarketing", "#ContentMarketing", "#SEO"],
    "business": ["#Business", "#Entrepreneur", "#Startup", "#Leadership"],
    "dev": ["#Developer", "#Programming", "#Coding", "#WebDev", "#SoftwareEngineering"],
    "security": ["#CyberSecurity", "#InfoSec", "#AppSec", "#Security"],
    "finance": ["#Finance", "#Fintech", "#Investing", "#Crypto"],
    "design": ["#Design", "#UX", "#UI", "#GraphicDesign"],
    "news": ["#Breaking", "#News", "#Trending"],
    "personal": ["#Motivation", "#Growth", "#Mindset"],
}

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS social_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    content TEXT NOT NULL,
    media_path TEXT,
    scheduled_at TEXT,
    posted_at TEXT,
    status TEXT DEFAULT 'draft' CHECK(status IN ('draft','scheduled','posted','failed','cancelled')),
    hashtags TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
"""

_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_social_posts_status ON social_posts(status);
CREATE INDEX IF NOT EXISTS idx_social_posts_scheduled ON social_posts(scheduled_at);
CREATE INDEX IF NOT EXISTS idx_social_posts_platform ON social_posts(platform);
"""


def _utc_now() -> datetime:
    return datetime.now(tz=_TZ_UTC)


def _utc_now_str() -> str:
    return _utc_now().strftime("%Y-%m-%d %H:%M:%S")


def _to_eastern(dt_str: str | None) -> str:
    """Convert a UTC datetime string to US/Eastern display string."""
    if not dt_str:
        return "—"
    try:
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=_TZ_UTC)
        eastern = dt.astimezone(_TZ_DISPLAY)
        return eastern.strftime("%Y-%m-%d %I:%M %p ET")
    except (ValueError, TypeError):
        return dt_str


def _parse_datetime(raw: str) -> datetime | None:
    """Parse a user-supplied datetime string into a UTC datetime.

    Accepts several formats. The user input is assumed to be in US/Eastern.
    """
    raw = raw.strip()
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %I:%M %p",
        "%Y-%m-%d %I:%M%p",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y %I:%M %p",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
    ]
    for fmt in formats:
        try:
            dt_local = datetime.strptime(raw, fmt).replace(tzinfo=_TZ_DISPLAY)
            return dt_local.astimezone(_TZ_UTC)
        except ValueError:
            continue
    return None


def _suggest_hashtags(content: str, max_tags: int = 5) -> list[str]:
    """Suggest hashtags based on keyword matching in the content."""
    lower = content.lower()
    suggestions: list[str] = []
    for keyword, tags in _HASHTAG_HINTS.items():
        if keyword in lower:
            for tag in tags:
                if tag not in suggestions:
                    suggestions.append(tag)
    # Extract existing hashtags from content so we don't duplicate them.
    existing = {m.lower() for m in re.findall(r"#\w+", content)}
    suggestions = [s for s in suggestions if s.lower() not in existing]
    return suggestions[:max_tags]


def _format_post_row(row: dict[str, Any]) -> str:
    """Format a single post dict into a readable block."""
    pid = row["id"]
    platform = _PLATFORM_LABELS.get(row["platform"], row["platform"])
    status = row["status"]
    content_preview = row["content"][:120]
    if len(row["content"]) > 120:
        content_preview += "..."
    scheduled = _to_eastern(row.get("scheduled_at"))
    created = _to_eastern(row.get("created_at"))
    hashtags = row.get("hashtags") or ""

    lines = [
        f"#{pid}  [{status.upper()}]  {platform}",
        f"  {content_preview}",
    ]
    if hashtags:
        lines.append(f"  Tags: {hashtags}")
    if status == "scheduled":
        lines.append(f"  Programado: {scheduled}")
    lines.append(f"  Creado: {created}")
    return "\n".join(lines)


class SocialMediaSkill(BaseSkill):
    """Schedule, draft, and manage social media posts."""

    def __init__(self, memory_engine: MemoryEngine | None = None) -> None:
        self._memory = memory_engine
        self._table_ready = False

    # ------------------------------------------------------------------
    # BaseSkill interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "social_media"

    @property
    def description(self) -> str:
        return (
            "Programador de redes sociales: crear, programar, editar y "
            "gestionar publicaciones para Twitter/X, LinkedIn, Facebook e Instagram"
        )

    @property
    def natural_patterns(self) -> dict[str, list[str]]:
        return {
            "nuevo": [
                r"(?:programa|agenda|publica|crea)\s+(?:un\s+)?post(?:\s+(?:en|para)\s+(?P<args>.+))?",
                r"(?:programa|agenda|publica|crea)\s+(?:una?\s+)?publicaci[oó]n(?:\s+(?:en|para)\s+(?P<args>.+))?",
                r"(?:quiero|necesito)\s+(?:publicar|postear)(?:\s+(?:en|algo\s+en)\s+(?P<args>.+))?",
            ],
            "ver": [
                r"(?:mu[eé]strame|ver|dame)\s+(?:los?\s+)?posts?\s+programados?",
                r"(?:qu[eé]|cu[aá]les?)\s+(?:posts?|publicaciones?)\s+(?:tengo|hay)\s+programad[ao]s?",
                r"(?:mis?\s+)?(?:redes|social\s+media)\s+(?:pendientes?|programad[ao]s?)",
            ],
            "borradores": [
                r"(?:mu[eé]strame|ver|dame)\s+(?:los?\s+)?borradores?(?:\s+de\s+(?:redes|social))?",
                r"(?:qu[eé]|cu[aá]les?)\s+borradores?\s+(?:tengo|hay)",
            ],
            "calendario": [
                r"(?:mu[eé]strame|ver|dame)\s+(?:el\s+)?calendario\s+(?:de\s+)?(?:redes|social|publicaciones?|posts?)",
                r"calendario\s+social",
            ],
            "hashtags": [
                r"(?:sugiere|recomienda|dame)\s+hashtags?\s+(?:para|de|sobre)\s+(?P<args>.+)",
            ],
        }

    @property
    def triggers(self) -> list[str]:
        return ["!social", "!post", "!publicar", "!programar", "!rrss", "!redes"]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        memory = self._memory or context.get("memory")
        if memory is None:
            return SkillResult(success=False, message="Motor de memoria no disponible.")

        await self._ensure_table(memory)

        if not args:
            return await self._cmd_ver(memory)

        parts = args.split(maxsplit=1)
        sub = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""

        dispatch: dict[str, str] = {
            "nuevo": "_cmd_nuevo",
            "new": "_cmd_nuevo",
            "crear": "_cmd_nuevo",
            "borrador": "_cmd_borrador",
            "draft": "_cmd_borrador",
            "ver": "_cmd_ver",
            "list": "_cmd_ver",
            "listar": "_cmd_ver",
            "borradores": "_cmd_borradores",
            "drafts": "_cmd_borradores",
            "editar": "_cmd_editar",
            "edit": "_cmd_editar",
            "cancelar": "_cmd_cancelar",
            "cancel": "_cmd_cancelar",
            "historial": "_cmd_historial",
            "history": "_cmd_historial",
            "pendientes": "_cmd_pendientes",
            "pending": "_cmd_pendientes",
            "calendario": "_cmd_calendario",
            "calendar": "_cmd_calendario",
            "hashtags": "_cmd_hashtags",
            "tags": "_cmd_hashtags",
        }

        handler_name = dispatch.get(sub)
        if handler_name is None:
            return SkillResult(
                success=False,
                message=(
                    "Subcomando no reconocido. Usa:\n"
                    "  nuevo <plataforma> | <contenido> | <fecha>\n"
                    "  borrador <plataforma> | <contenido>\n"
                    "  ver — publicaciones programadas\n"
                    "  borradores — ver borradores\n"
                    "  editar <id> | <nuevo contenido>\n"
                    "  cancelar <id>\n"
                    "  historial — publicaciones pasadas\n"
                    "  pendientes — por publicar\n"
                    "  calendario — vista semanal\n"
                    "  hashtags <texto> — sugerir hashtags"
                ),
            )

        handler = getattr(self, handler_name)
        return await handler(memory, rest)

    # ------------------------------------------------------------------
    # Table setup
    # ------------------------------------------------------------------

    async def _ensure_table(self, memory: MemoryEngine) -> None:
        if self._table_ready:
            return

        def _create() -> None:
            memory.execute(_TABLE_SQL)
            for stmt in _INDEXES_SQL.strip().split(";"):
                stmt = stmt.strip()
                if stmt:
                    memory.execute(stmt + ";")

        await asyncio.to_thread(_create)
        self._table_ready = True
        log.info("social_media.table_ready")

    # ------------------------------------------------------------------
    # Subcommands
    # ------------------------------------------------------------------

    async def _cmd_nuevo(self, memory: MemoryEngine, rest: str) -> SkillResult:
        """Create a scheduled post: <platform> | <content> | <datetime>"""
        segments = [s.strip() for s in rest.split("|")]
        if len(segments) < 3:
            return SkillResult(
                success=False,
                message=(
                    "Formato: nuevo <plataforma> | <contenido> | <fecha hora>\n"
                    "Ejemplo: nuevo twitter | Lanzamos la v2.0! | 2026-03-21 10:00\n"
                    "Plataformas: twitter/x, linkedin, facebook, instagram, all"
                ),
            )

        platform = segments[0].lower()
        content = segments[1]
        dt_raw = segments[2]
        media_path = segments[3].strip() if len(segments) > 3 else None

        if platform not in _VALID_PLATFORMS:
            return SkillResult(
                success=False,
                message=f"Plataforma '{platform}' no valida. Opciones: {', '.join(sorted(_VALID_PLATFORMS))}",
            )

        scheduled_dt = _parse_datetime(dt_raw)
        if scheduled_dt is None:
            return SkillResult(
                success=False,
                message=(
                    f"No pude interpretar la fecha '{dt_raw}'.\n"
                    "Formatos validos: 2026-03-21 10:00, 2026-03-21 2:30 PM, 21/03/2026 10:00"
                ),
            )

        if scheduled_dt < _utc_now():
            return SkillResult(
                success=False,
                message="La fecha programada ya paso. Usa una fecha futura.",
            )

        # Character limit warning
        char_limit = _PLATFORM_LIMITS.get(platform, 99999)
        warning = ""
        if len(content) > char_limit:
            warning = (
                f"\n⚠ El contenido tiene {len(content)} caracteres, "
                f"el limite de {_PLATFORM_LABELS.get(platform, platform)} es {char_limit}."
            )

        hashtags_suggested = _suggest_hashtags(content)
        hashtags_str = " ".join(hashtags_suggested) if hashtags_suggested else None

        scheduled_str = scheduled_dt.strftime("%Y-%m-%d %H:%M:%S")

        platforms_to_insert = (
            [p for p in _VALID_PLATFORMS if p not in ("all", "x")]
            if platform == "all"
            else [platform]
        )

        ids_created: list[int] = []

        def _insert() -> None:
            for plat in platforms_to_insert:
                pid = memory.insert_returning_id(
                    "INSERT INTO social_posts (platform, content, media_path, scheduled_at, status, hashtags) "
                    "VALUES (?, ?, ?, ?, 'scheduled', ?)",
                    (plat, content, media_path, scheduled_str, hashtags_str),
                )
                ids_created.append(pid)

        await asyncio.to_thread(_insert)

        display_dt = _to_eastern(scheduled_str)
        ids_display = ", ".join(f"#{i}" for i in ids_created)
        msg = f"Post programado ({ids_display}) para {display_dt} en {_PLATFORM_LABELS.get(platform, platform)}.{warning}"
        if hashtags_suggested:
            msg += f"\nHashtags sugeridos: {' '.join(hashtags_suggested)}"

        log.info("social_media.post_scheduled", ids=ids_created, platform=platform, scheduled=scheduled_str)
        return SkillResult(success=True, message=msg, data={"ids": ids_created})

    async def _cmd_borrador(self, memory: MemoryEngine, rest: str) -> SkillResult:
        """Save a draft: <platform> | <content>"""
        segments = [s.strip() for s in rest.split("|")]
        if len(segments) < 2:
            return SkillResult(
                success=False,
                message="Formato: borrador <plataforma> | <contenido>\nEjemplo: borrador linkedin | Mi nuevo articulo...",
            )

        platform = segments[0].lower()
        content = segments[1]
        media_path = segments[2].strip() if len(segments) > 2 else None

        if platform not in _VALID_PLATFORMS:
            return SkillResult(
                success=False,
                message=f"Plataforma '{platform}' no valida. Opciones: {', '.join(sorted(_VALID_PLATFORMS))}",
            )

        hashtags_suggested = _suggest_hashtags(content)
        hashtags_str = " ".join(hashtags_suggested) if hashtags_suggested else None

        def _insert() -> int:
            return memory.insert_returning_id(
                "INSERT INTO social_posts (platform, content, media_path, status, hashtags) "
                "VALUES (?, ?, ?, 'draft', ?)",
                (platform, content, media_path, hashtags_str),
            )

        pid = await asyncio.to_thread(_insert)

        msg = f"Borrador #{pid} guardado para {_PLATFORM_LABELS.get(platform, platform)}."
        if hashtags_suggested:
            msg += f"\nHashtags sugeridos: {' '.join(hashtags_suggested)}"

        log.info("social_media.draft_saved", id=pid, platform=platform)
        return SkillResult(success=True, message=msg, data={"id": pid})

    async def _cmd_ver(self, memory: MemoryEngine, rest: str = "") -> SkillResult:
        """Show upcoming scheduled posts."""

        def _fetch() -> list[dict[str, Any]]:
            return memory.fetchall_dicts(
                "SELECT * FROM social_posts WHERE status = 'scheduled' "
                "AND scheduled_at >= ? ORDER BY scheduled_at ASC LIMIT 25",
                (_utc_now_str(),),
            )

        rows = await asyncio.to_thread(_fetch)
        if not rows:
            return SkillResult(success=True, message="No hay publicaciones programadas.")

        lines = ["Publicaciones programadas:\n"]
        for row in rows:
            lines.append(_format_post_row(row))
            lines.append("")
        return SkillResult(success=True, message="\n".join(lines), data={"count": len(rows)})

    async def _cmd_borradores(self, memory: MemoryEngine, rest: str = "") -> SkillResult:
        """Show all drafts."""

        def _fetch() -> list[dict[str, Any]]:
            return memory.fetchall_dicts(
                "SELECT * FROM social_posts WHERE status = 'draft' ORDER BY created_at DESC LIMIT 25",
            )

        rows = await asyncio.to_thread(_fetch)
        if not rows:
            return SkillResult(success=True, message="No hay borradores guardados.")

        lines = ["Borradores:\n"]
        for row in rows:
            lines.append(_format_post_row(row))
            lines.append("")
        return SkillResult(success=True, message="\n".join(lines), data={"count": len(rows)})

    async def _cmd_editar(self, memory: MemoryEngine, rest: str) -> SkillResult:
        """Edit a post: <id> | <new content>"""
        segments = [s.strip() for s in rest.split("|", maxsplit=1)]
        if len(segments) < 2:
            return SkillResult(
                success=False,
                message="Formato: editar <id> | <nuevo contenido>\nEjemplo: editar 5 | Contenido actualizado",
            )

        try:
            post_id = int(segments[0])
        except ValueError:
            return SkillResult(success=False, message="El ID debe ser un numero.")

        new_content = segments[1]

        def _update() -> dict[str, Any] | None:
            row = memory.fetchone(
                "SELECT id, status, platform FROM social_posts WHERE id = ?", (post_id,)
            )
            if row is None:
                return None
            status = row[1]
            platform = row[2]
            if status in ("posted", "cancelled"):
                return {"error": f"No se puede editar un post con estado '{status}'."}
            memory.execute(
                "UPDATE social_posts SET content = ? WHERE id = ?",
                (new_content, post_id),
            )
            # Re-suggest hashtags
            tags = _suggest_hashtags(new_content)
            if tags:
                memory.execute(
                    "UPDATE social_posts SET hashtags = ? WHERE id = ?",
                    (" ".join(tags), post_id),
                )
            return {"platform": platform, "status": status}

        result = await asyncio.to_thread(_update)
        if result is None:
            return SkillResult(success=False, message=f"No existe un post con ID #{post_id}.")
        if "error" in result:
            return SkillResult(success=False, message=result["error"])

        log.info("social_media.post_edited", id=post_id)
        return SkillResult(success=True, message=f"Post #{post_id} actualizado.")

    async def _cmd_cancelar(self, memory: MemoryEngine, rest: str) -> SkillResult:
        """Cancel a scheduled post."""
        try:
            post_id = int(rest.strip())
        except ValueError:
            return SkillResult(success=False, message="Formato: cancelar <id>\nEjemplo: cancelar 3")

        def _cancel() -> str | None:
            row = memory.fetchone(
                "SELECT id, status FROM social_posts WHERE id = ?", (post_id,)
            )
            if row is None:
                return None
            status = row[1]
            if status in ("posted", "cancelled"):
                return f"El post #{post_id} ya tiene estado '{status}', no se puede cancelar."
            memory.execute(
                "UPDATE social_posts SET status = 'cancelled' WHERE id = ?", (post_id,)
            )
            return "ok"

        result = await asyncio.to_thread(_cancel)
        if result is None:
            return SkillResult(success=False, message=f"No existe un post con ID #{post_id}.")
        if result != "ok":
            return SkillResult(success=False, message=result)

        log.info("social_media.post_cancelled", id=post_id)
        return SkillResult(success=True, message=f"Post #{post_id} cancelado.")

    async def _cmd_historial(self, memory: MemoryEngine, rest: str = "") -> SkillResult:
        """Show posted history."""

        def _fetch() -> list[dict[str, Any]]:
            return memory.fetchall_dicts(
                "SELECT * FROM social_posts WHERE status = 'posted' ORDER BY posted_at DESC LIMIT 25",
            )

        rows = await asyncio.to_thread(_fetch)
        if not rows:
            return SkillResult(success=True, message="No hay publicaciones en el historial.")

        lines = ["Historial de publicaciones:\n"]
        for row in rows:
            lines.append(_format_post_row(row))
            posted = _to_eastern(row.get("posted_at"))
            lines.append(f"  Publicado: {posted}")
            lines.append("")
        return SkillResult(success=True, message="\n".join(lines), data={"count": len(rows)})

    async def _cmd_pendientes(self, memory: MemoryEngine, rest: str = "") -> SkillResult:
        """Show posts pending publication (scheduled, past due or upcoming)."""

        def _fetch() -> list[dict[str, Any]]:
            return memory.fetchall_dicts(
                "SELECT * FROM social_posts WHERE status = 'scheduled' ORDER BY scheduled_at ASC LIMIT 50",
            )

        rows = await asyncio.to_thread(_fetch)
        if not rows:
            return SkillResult(success=True, message="No hay publicaciones pendientes.")

        now = _utc_now_str()
        overdue = [r for r in rows if (r.get("scheduled_at") or "") <= now]
        upcoming = [r for r in rows if (r.get("scheduled_at") or "") > now]

        lines: list[str] = []

        if overdue:
            lines.append(f"VENCIDAS ({len(overdue)}):\n")
            for row in overdue:
                lines.append(_format_post_row(row))
                lines.append("")

        if upcoming:
            lines.append(f"PROXIMAS ({len(upcoming)}):\n")
            for row in upcoming:
                lines.append(_format_post_row(row))
                lines.append("")

        header = f"Pendientes: {len(rows)} total ({len(overdue)} vencidas, {len(upcoming)} proximas)\n"
        return SkillResult(
            success=True,
            message=header + "\n".join(lines),
            data={"total": len(rows), "overdue": len(overdue), "upcoming": len(upcoming)},
        )

    async def _cmd_calendario(self, memory: MemoryEngine, rest: str = "") -> SkillResult:
        """Show posts organized by date for the next 7 days."""
        now_utc = _utc_now()
        end_utc = now_utc + timedelta(days=7)

        def _fetch() -> list[dict[str, Any]]:
            return memory.fetchall_dicts(
                "SELECT * FROM social_posts WHERE status IN ('scheduled', 'draft') "
                "AND (scheduled_at IS NULL OR scheduled_at BETWEEN ? AND ?) "
                "ORDER BY scheduled_at ASC",
                (now_utc.strftime("%Y-%m-%d %H:%M:%S"), end_utc.strftime("%Y-%m-%d %H:%M:%S")),
            )

        rows = await asyncio.to_thread(_fetch)

        # Group by date (Eastern time)
        by_date: dict[str, list[dict[str, Any]]] = {}
        drafts: list[dict[str, Any]] = []
        for row in rows:
            if row["status"] == "draft":
                drafts.append(row)
                continue
            sched = row.get("scheduled_at")
            if sched:
                try:
                    dt = datetime.strptime(sched, "%Y-%m-%d %H:%M:%S").replace(tzinfo=_TZ_UTC)
                    date_key = dt.astimezone(_TZ_DISPLAY).strftime("%A %Y-%m-%d")
                except ValueError:
                    date_key = "Sin fecha"
            else:
                date_key = "Sin fecha"
            by_date.setdefault(date_key, []).append(row)

        if not rows:
            return SkillResult(success=True, message="Calendario vacio para los proximos 7 dias.")

        lines = ["Calendario de publicaciones (proximos 7 dias):\n"]

        for date_label, day_rows in by_date.items():
            lines.append(f"--- {date_label} ---")
            for row in day_rows:
                sched = row.get("scheduled_at", "")
                try:
                    dt = datetime.strptime(sched, "%Y-%m-%d %H:%M:%S").replace(tzinfo=_TZ_UTC)
                    time_str = dt.astimezone(_TZ_DISPLAY).strftime("%I:%M %p")
                except (ValueError, TypeError):
                    time_str = "?"
                platform = _PLATFORM_LABELS.get(row["platform"], row["platform"])
                preview = row["content"][:80]
                if len(row["content"]) > 80:
                    preview += "..."
                lines.append(f"  {time_str}  {platform}  #{row['id']}  {preview}")
            lines.append("")

        if drafts:
            lines.append("--- Borradores sin programar ---")
            for row in drafts:
                platform = _PLATFORM_LABELS.get(row["platform"], row["platform"])
                preview = row["content"][:80]
                if len(row["content"]) > 80:
                    preview += "..."
                lines.append(f"  {platform}  #{row['id']}  {preview}")
            lines.append("")

        return SkillResult(
            success=True,
            message="\n".join(lines),
            data={"scheduled": sum(len(v) for v in by_date.values()), "drafts": len(drafts)},
        )

    async def _cmd_hashtags(self, memory: MemoryEngine, rest: str) -> SkillResult:
        """Suggest hashtags for given text."""
        if not rest:
            return SkillResult(
                success=False,
                message="Formato: hashtags <texto del post>\nEjemplo: hashtags Nuevo articulo sobre inteligencia artificial",
            )

        suggestions = _suggest_hashtags(rest, max_tags=8)
        if not suggestions:
            return SkillResult(
                success=True,
                message="No encontre hashtags sugeridos automaticamente. Intenta agregar palabras clave como tech, ai, marketing, etc.",
            )

        return SkillResult(
            success=True,
            message=f"Hashtags sugeridos:\n{' '.join(suggestions)}\n\nCopia los que quieras al contenido de tu post.",
            data={"hashtags": suggestions},
        )
