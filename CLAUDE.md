# Personal AI Assistant — Development Guide

## Architecture

Python 3.12+ asyncio application. Single-user Telegram/WhatsApp bot powered by Claude Code CLI. 55 source files, 14 built-in skills.

### Core Pipeline
```
Incoming message → SecurityGuardian (auth + rate limit + injection detect)
    → Gateway (session mgmt, onboarding, context building, routing)
    → ClaudeBridge (persistent session or one-shot CLI)
    → Response (output validation → send via channel)
```

### Module Map (55 files)
```
src/
  __init__.py              — Package init
  main.py                  — Entry point, Settings (pydantic-settings), signal handling,
                             auto-permission hardening on startup

  core/
    __init__.py
    gateway.py              — Central orchestrator, message pipeline, system prompt,
                             voice detection, skill routing, screenshot/file sending
    security.py             — SecurityGuardian: auth, command validation, path validation,
                             prompt injection detection (28 patterns), output scanning
    claude_bridge.py        — Persistent CLI session (stream-json) with one-shot fallback,
                             Windows .cmd detection, configurable max-turns
    hot_reload.py           — Watchdog-based file watcher. Utility modules: importlib.reload().
                             Core modules: trigger full process restart. Syntax validation
                             with ast.parse() before any change. Auto-backup to .backups/
    executor.py             — Sandboxed command execution (bubblewrap on Linux, subprocess on Win/Mac)
    desktop_control.py      — Screenshot, window management, browser tab scanning (CDP + xdotool)

  memory/
    __init__.py
    engine.py               — APSW-based SQLite with optional SQLCipher. FTS5 indexes.
                             sanitize_fts_query() for safe full-text search
    conversation.py         — ConversationStore with FTS search
    context.py              — Context builder: assembles conversation history + memory for Claude
    relationships.py        — RelationshipTracker
    tasks.py                — TaskManager with scheduling support
    learning.py             — LearningStore (facts + knowledge)

  learning/
    __init__.py
    web_search.py           — DuckDuckGo HTML scraping (no API key), SSRF protection
    knowledge_base.py       — Knowledge persistence (DB + Markdown), FTS search
    learner.py              — Orchestrates search → fetch → summarize → save

  audio/
    __init__.py
    transcriber.py          — faster-whisper STT (guarded import for Python 3.13+)
    processor.py            — OGG/WAV conversion via pydub (guarded import)
    synthesizer.py          — TTS: chatterbox, espeak, gTTS, pyttsx3

  channels/
    __init__.py
    base.py                 — Abstract base class for all channels
    telegram.py             — Telegram Bot (polling), send_text/photo/audio/document
    whatsapp_baileys.py     — WhatsApp via Baileys bridge (Node.js)
    whatsapp_business.py    — WhatsApp Business API with webhook verification (HMAC-SHA256)

  skills/
    __init__.py
    base_skill.py           — Abstract base class for skills
    registry.py             — Skill loading + watchdog watcher for runtime skill creation
    built_in/
      __init__.py
      terminal.py           — Execute shell commands in sandbox
      files.py              — Read, write, search, manage files
      memory_skill.py       — Query and store permanent memory
      tasks_skill.py        — Task creation, reminders, scheduled execution
      learn_skill.py        — Web search, URL fetching, knowledge base
      desktop_control.py    — Screenshots, window management, keyboard input
      mcp_creator.py        — Generate, install, register MCP servers (FastMCP + venv)
      skill_creator.py      — Create new skills at runtime, validate, hot-load
      claude_code.py        — Claude Code CLI integration for code projects
      system_monitor.py     — System status: CPU, RAM, disk, processes, uptime
      file_search.py        — Advanced file search by name, extension, content
      git_skill.py          — Git operations: status, commit, diff, log, branch, push, pull
      network_skill.py      — Network diagnostics: ping, DNS lookup, port scan, interfaces
      package_skill.py      — Package management: apt, dnf, pacman, brew, winget

  onboarding/
    __init__.py
    wizard.py               — First-run setup: name extraction, preferences, BOM/CRLF handling

  utils/
    __init__.py
    platform.py             — IS_WINDOWS, IS_MACOS, SHELL_CMD, platform detection
    crypto.py               — AES-256-GCM encrypt/decrypt, bcrypt PIN hashing
    approval.py             — ApprovalGate for dangerous operations
    logger.py               — structlog setup (app, security, audit loggers)
    formatter.py            — Message formatting utilities
```

## Security Rules

1. All SQL queries use parameterized statements — never f-strings (exception: PRAGMA key with strict input validation)
2. User input to FTS5 MATCH always goes through `sanitize_fts_query()`
3. File paths validated against sensitive patterns before access
4. Output scanned for leaked secrets (tokens, API keys, passwords) before sending to user
5. Prompt injection patterns (28 regex) detected, logged to audit log, and blocked
6. PIN stored as bcrypt hash, never plaintext
7. SSRF protection blocks private/loopback IPs on web fetch
8. Telegram document filenames sanitized with `os.path.basename()`
9. File permissions hardened automatically on every startup: `.env` (600), `data/` (700), `logs/` (700) — Linux/macOS only
10. Sandboxed execution: bubblewrap (Linux), subprocess with timeout and restricted env (Windows/macOS)

## Cross-Platform

- `src/utils/platform.py`: `IS_WINDOWS`, `IS_MACOS` flags control all platform branches
- Shell: `cmd /c` (Windows) vs `/bin/sh -c` (Linux/Mac)
- Claude CLI: auto-detects `.cmd` wrapper on Windows
- Signals: `signal.signal()` on Windows, `add_signal_handler()` on Linux/Mac
- Paths: `pathlib.Path` and `os.path.join` throughout — no hardcoded separators
- Desktop: `pyautogui` (Windows) vs `xdotool`/`scrot` (Linux) vs `screencapture`/`osascript` (macOS)
- Permissions: `os.chmod` on Linux/Mac, skipped on Windows (NTFS ACLs)
- Hot-reload restart: `os.execv` (Linux/Mac) vs `subprocess.Popen` detached (Windows)
- Service: systemd (Linux), launchd (macOS), Task Scheduler (Windows)
- Package manager skill: auto-detects apt, dnf, pacman, brew, winget

## Code Style

- Type hints: `str | None`, `list[str]` (Python 3.12+ syntax)
- `from __future__ import annotations` in every module
- `structlog` for all logging — never bare `print()`
- Async-first with `asyncio.to_thread()` for blocking calls
- Imports guarded with try/except where platform dependencies may be missing
- Docstrings in Spanish or English, consistent within each module
- Constants in UPPER_SNAKE_CASE at module level
- No global mutable state outside of class instances

## Skills Development

New skills must:
1. Inherit from `BaseSkill` in `src/skills/base_skill.py`
2. Implement `name`, `description`, `triggers` properties and `execute()` async method
3. Be placed in `src/skills/built_in/` (built-in) or `skills/` (runtime-created)
4. The registry auto-discovers files in both directories via watchdog

Runtime-created skills (via `!skill crear`) go through:
1. Generation by Claude Code
2. Syntax validation with `ast.parse()`
3. Backup of any existing file
4. Write to `skills/` directory
5. Auto-load by watchdog without restart
