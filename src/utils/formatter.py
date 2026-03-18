"""Message formatting utilities for Telegram output."""

from __future__ import annotations

import re
from datetime import timedelta

# https://core.telegram.org/bots/api#markdownv2-style
_MARKDOWNV2_SPECIAL = r"_*[]()~`>#+-=|{}.!\\"


def truncate_for_telegram(text: str, max_length: int = 4096) -> list[str]:
    """Split text into chunks that fit Telegram's 4096-char limit.

    Tries newlines first, then spaces, then hard-splits.
    """
    if not text:
        return [""]

    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break

        chunk = remaining[:max_length]
        split_at = max_length

        newline_pos = chunk.rfind("\n")
        if newline_pos > max_length // 4:
            split_at = newline_pos + 1
        elif (space_pos := chunk.rfind(" ")) > max_length // 4:
            split_at = space_pos + 1

        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:]

    return chunks


def format_code_block(code: str, language: str = "") -> str:
    safe_code = code.replace("```", "\\`\\`\\`")
    return f"```{language}\n{safe_code}\n```"


def format_error(error: str) -> str:
    return f"Error: {error}"


def escape_markdown(text: str) -> str:
    pattern = "([" + re.escape(_MARKDOWNV2_SPECIAL) + "])"
    return re.sub(pattern, r"\\\1", text)


def format_status(
    uptime: float,
    memory_mb: float,
    skills: int,
    tasks: int,
) -> str:
    uptime_str = _format_duration(uptime)

    lines = [
        "== Estado del Sistema ==",
        "",
        f"  Uptime:   {uptime_str}",
        f"  Memoria:  {memory_mb:.1f} MB",
        f"  Skills:   {skills} cargados",
        f"  Tareas:   {tasks} activas",
        "",
        "========================",
    ]
    return "\n".join(lines)


def _format_duration(seconds: float) -> str:
    """Convert seconds to a human-readable duration string."""
    td = timedelta(seconds=int(seconds))
    days = td.days
    hours, remainder = divmod(td.seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")

    return " ".join(parts)
