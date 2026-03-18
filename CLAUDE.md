# Personal AI Assistant — Development Guide

## Architecture

Python 3.12+ asyncio application. Single-user Telegram/WhatsApp bot powered by Claude Code CLI.

### Core Pipeline
```
Incoming message → SecurityGuardian (auth + rate limit + injection detect)
    → Gateway (session mgmt, onboarding, routing)
    → ClaudeBridge (persistent session or one-shot CLI)
    → Response (output validation → send via channel)
```

### Module Map
```
src/
  main.py              — Entry point, Settings (pydantic-settings), signal handling,
                         auto-permission hardening on startup
  core/
    gateway.py          — Central orchestrator, message pipeline, system prompt,
                         voice detection, skill routing, screenshot/file sending
    security.py         — SecurityGuardian: auth, command validation, path validation,
                         prompt injection detection (28 patterns), output scanning
    claude_bridge.py    — Persistent CLI session (stream-json) with one-shot fallback,
                         Windows .cmd detection, configurable max-turns
    hot_reload.py       — Watchdog-based file watcher. Utility modules: importlib.reload().
                         Core modules: trigger full process restart. Syntax validation
                         with ast.parse() before any change. Auto-backup to .backups/
    executor.py         — Sandboxed command execution (bubblewrap on Linux, subprocess on Win)
    desktop_control.py  — Screenshot, window management, browser tab scanning (CDP + xdotool)
    context_builder.py  — Builds conversation context from memory for Claude
  memory/
    engine.py           — APSW-based SQLite with optional SQLCipher. FTS5 indexes.
                         sanitize_fts_query() for safe full-text search
    conversation.py     — ConversationStore with FTS search
    relationships.py    — RelationshipTracker
    tasks.py            — TaskManager with scheduling support
    learning.py         — LearningStore (facts + knowledge)
  learning/
    web_search.py       — DuckDuckGo HTML scraping (no API key), SSRF protection
    knowledge_base.py   — Knowledge persistence (DB + Markdown), FTS search
    learner.py          — Orchestrates search → fetch → summarize → save
  audio/
    transcriber.py      — faster-whisper STT (guarded import for Python 3.13+)
    processor.py        — OGG/WAV conversion via pydub (guarded import)
    synthesizer.py      — TTS: chatterbox, espeak, gTTS, pyttsx3
  channels/
    telegram.py         — Telegram Bot (polling), send_text/photo/audio/document
    whatsapp_baileys.py — WhatsApp via Baileys bridge
    whatsapp_business.py— WhatsApp Business API with webhook verification
  skills/
    registry.py         — Skill loading + watchdog watcher for runtime skill creation
    built_in/           — Terminal, files, memory, tasks, learning, desktop, MCP creator,
                         skill creator, Claude Code integration
  onboarding/
    wizard.py           — First-run setup: name extraction, preferences, BOM/CRLF handling
  utils/
    platform.py         — IS_WINDOWS, SHELL_CMD, platform detection
    crypto.py           — AES-256-GCM encrypt/decrypt, bcrypt PIN hashing
    approval.py         — ApprovalGate for dangerous operations
    logger.py           — structlog setup (app, security, audit loggers)
    formatter.py        — Message formatting utilities
```

## Security Rules

1. All SQL queries use parameterized statements — never f-strings (exception: PRAGMA key with input validation)
2. User input to FTS5 MATCH always goes through `sanitize_fts_query()`
3. File paths validated against sensitive patterns before access
4. Output scanned for leaked secrets before sending to user
5. Prompt injection patterns detected and logged
6. PIN stored as bcrypt hash, never plaintext
7. SSRF protection blocks private/loopback IPs on web fetch
8. Telegram document filenames sanitized with `os.path.basename()`
9. File permissions hardened automatically on every startup (Linux/Mac)

## Cross-Platform

- `src/utils/platform.py`: `IS_WINDOWS` flag controls all platform branches
- Shell: `cmd /c` (Windows) vs `/bin/sh -c` (Linux/Mac)
- Claude CLI: auto-detects `.cmd` wrapper on Windows
- Signals: `signal.signal()` on Windows, `add_signal_handler()` on Linux/Mac
- Paths: `pathlib.Path` and `os.path.join` throughout — no hardcoded separators
- Desktop: `pyautogui` (Windows) vs `xdotool`/`scrot` (Linux)
- Permissions: `os.chmod` on Linux/Mac, skipped on Windows (NTFS ACLs)
- Hot-reload restart: `os.execv` (Linux/Mac) vs `subprocess.Popen` detached (Windows)

## Code Style

- Type hints: `str | None`, `list[str]` (Python 3.12+ syntax)
- `from __future__ import annotations` in every module
- `structlog` for all logging — never bare `print()`
- Async-first with `asyncio.to_thread()` for blocking calls
- Imports guarded with try/except where platform dependencies may be missing
