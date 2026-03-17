"""
Message formatting utilities for Telegram output.

Handles message splitting (Telegram's 4096 char limit), code block
formatting, error formatting, and MarkdownV2 escaping.
"""

from __future__ import annotations

import re
from datetime import timedelta


# Characters that must be escaped in Telegram MarkdownV2
# See: https://core.telegram.org/bots/api#markdownv2-style
_MARKDOWNV2_SPECIAL = r"_*[]()~`>#+-=|{}.!\\"


def truncate_for_telegram(
    text: str, max_length: int = 4096
) -> list[str]:
    """
    Split a long message into chunks that fit Telegram's message size limit.

    Tries to split at newlines first, then at spaces, and only as a last
    resort splits mid-word.

    Args:
        text: The full text to split.
        max_length: Maximum characters per chunk (default 4096).

    Returns:
        List of string chunks, each <= max_length characters.
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

        # Try to find a good split point
        chunk = remaining[:max_length]
        split_at = max_length

        # Priority 1: split at last newline
        newline_pos = chunk.rfind("\n")
        if newline_pos > max_length // 4:
            split_at = newline_pos + 1  # include the newline in this chunk

        # Priority 2: split at last space
        elif (space_pos := chunk.rfind(" ")) > max_length // 4:
            split_at = space_pos + 1

        # Priority 3: hard split at max_length (already set)

        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:]

    return chunks


def format_code_block(code: str, language: str = "") -> str:
    """
    Wrap code in a Telegram-compatible markdown code block.

    Args:
        code: The code string.
        language: Optional language identifier for syntax highlighting.

    Returns:
        Formatted code block string.
    """
    # Escape any triple backticks inside the code to prevent breaking the block
    safe_code = code.replace("```", "\\`\\`\\`")
    return f"```{language}\n{safe_code}\n```"


def format_error(error: str) -> str:
    """
    Format an error message for display to the user.

    Args:
        error: The error description.

    Returns:
        Formatted error string with emoji indicator.
    """
    return f"Error: {error}"


def escape_markdown(text: str) -> str:
    """
    Escape special characters for Telegram MarkdownV2 format.

    All characters in _MARKDOWNV2_SPECIAL are prefixed with a backslash.

    Args:
        text: Raw text to escape.

    Returns:
        Escaped text safe for MarkdownV2 parsing.
    """
    pattern = "([" + re.escape(_MARKDOWNV2_SPECIAL) + "])"
    return re.sub(pattern, r"\\\1", text)


def format_status(
    uptime: float,
    memory_mb: float,
    skills: int,
    tasks: int,
) -> str:
    """
    Format a system status message.

    Args:
        uptime: Uptime in seconds.
        memory_mb: Memory usage in megabytes.
        skills: Number of loaded skills.
        tasks: Number of active/pending tasks.

    Returns:
        Human-readable status string.
    """
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
