# Personal AI Assistant — Claude Code Instructions

## Project Overview
This is a personal AI assistant accessible via Telegram, using Claude Code CLI as its brain.

## Key Architecture
- Python 3.12+ with asyncio
- SQLite with SQLCipher encryption for memory (via APSW)
- Claude CLI (`claude -p`) for AI processing (uses subscription, NOT API key)
- Telegram Bot API for messaging
- faster-whisper for STT, chatterbox/espeak for TTS
- bubblewrap (bwrap) for command sandboxing
- APScheduler for recurring tasks
- structlog for structured logging

## Directory Layout
```
src/
  main.py              — entry point, Settings, signal handling
  core/
    gateway.py          — central orchestrator, message pipeline
    security.py         — SecurityGuardian (auth, path validation, output scanning)
    claude_bridge.py    — wrapper around `claude` CLI
    context_builder.py  — builds conversation context for Claude
  memory/
    engine.py           — MemoryEngine (APSW/SQLCipher)
    conversation.py     — ConversationStore
    relationships.py    — RelationshipTracker
    tasks.py            — TaskManager
  learning/
    web_search.py       — DuckDuckGo HTML search (no API key)
    knowledge_base.py   — knowledge persistence (DB + Markdown files)
    learner.py          — orchestrates search → fetch → summarise → save
  audio/
    transcriber.py      — faster-whisper STT
    processor.py        — OGG/WAV conversion
    synthesizer.py      — TTS output
  channels/
    telegram.py         — Telegram Bot channel
  skills/
    registry.py         — skill loading and dispatch
    built_in/           — bundled skills
  onboarding/
    wizard.py           — first-run onboarding flow
  utils/
    approval.py         — ApprovalGate for dangerous operations
    crypto.py           — encryption helpers
    formatter.py        — message formatting
    logger.py           — structlog configuration
data/                   — SQLite DB, knowledge Markdown files
logs/                   — app.log, security.log, audit.log
skills/                 — user-created skill files
systemd/                — systemd service unit
```

## Security Rules (NEVER VIOLATE)
1. Never execute commands without validation through SecurityGuardian
2. Never access files in .ssh, .gnupg, .env, /etc/shadow
3. Always use prepared statements for SQL (never string concatenation)
4. Always validate file paths before access
5. Always scan output for leaked secrets before sending
6. Rate limit all incoming messages
7. Only the AUTHORIZED_CHAT_ID can interact

## Running
```bash
# Development
python -m src.main

# Production (via systemd)
sudo systemctl start ai-assistant
```

## Testing
```bash
pytest tests/
```

## Environment Variables
Required:
- `TELEGRAM_BOT_TOKEN` — Telegram bot token from @BotFather
- `AUTHORIZED_CHAT_ID` — your Telegram chat ID (integer)

Optional:
- `SECURITY_PIN` — PIN for sensitive operations
- `CLAUDE_CLI_PATH` — path to claude binary (default: `claude`)
- `DB_ENCRYPTION_KEY` — SQLCipher encryption key
- `LOG_LEVEL` — DEBUG, INFO, WARNING, ERROR (default: INFO)
- `TIMEZONE` — e.g. America/New_York
- `WHISPER_MODEL` — tiny, base, small, medium, large-v3
- `TTS_ENGINE` — auto, chatterbox, espeak

## Code Style
- Type hints everywhere (Python 3.12+ syntax: `str | None`, `list[str]`)
- `from __future__ import annotations` in every module
- structlog for logging (never bare `print()`)
- All DB queries use parameterised statements — NEVER f-strings or .format()
- Async where possible; use `asyncio.to_thread()` for blocking calls
