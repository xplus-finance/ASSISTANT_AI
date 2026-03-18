<div align="center">

# Personal AI Assistant

**Your own private AI assistant. Reachable via Telegram or WhatsApp, 24/7, from anywhere.**

Built on [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI — runs on your existing subscription. No API keys. No per-token costs.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-green.svg)](https://python.org)
[![Claude Code](https://img.shields.io/badge/Claude_Code-CLI-orange.svg)](https://docs.anthropic.com/en/docs/claude-code)
[![Windows](https://img.shields.io/badge/Windows-10+-blue.svg)](https://www.microsoft.com)
[![Linux](https://img.shields.io/badge/Linux-Ubuntu_22.04+-orange.svg)](https://ubuntu.com)
[![macOS](https://img.shields.io/badge/macOS-13+-lightgrey.svg)](https://apple.com)

[English](#english) | [Installation](#installation) | [Documentation](#documentation) | [Security](#security)

---

</div>

## What is this?

A **private, self-hosted AI assistant** that lives on your machine and talks to you through Telegram or WhatsApp. This is not a generic chatbot — it is *your* assistant: it remembers everything, executes commands on your system, searches the web, schedules tasks, works on your code projects, and learns your preferences over time.

Single authorized user. Nobody else can interact with it. All data stored locally — nothing leaves your machine.

---

## Core Capabilities

| Permanent Memory | Security Hardened | Voice In/Out |
|---|---|---|
| Every conversation, fact, and preference stored locally with AES-256 encryption. Persistent across restarts. | Authentication, PIN verification, sandboxed execution, input sanitization, output scanning, rate limiting. | Send and receive voice notes. Local speech recognition via faster-whisper. No cloud dependency. |

| Full Autonomy | Self-Evolving | Multi-Platform |
|---|---|---|
| If it lacks a tool, it builds one. If it doesn't know something, it researches it. Never says "I can't". | Creates its own skills, MCP servers, and scripts on the fly. Hot-reload applies changes without restart. | Windows 10+, Linux (Ubuntu/Fedora/Arch), macOS. Same codebase, same features. |

| Scheduled Tasks | Web Research | Desktop Control |
|---|---|---|
| Program reminders and recurring tasks. They execute automatically at the specified time. | Searches DuckDuckGo without API keys. Fetches, summarizes, and stores knowledge. | Navigate browser tabs, take screenshots, type text, open applications. Cross-platform. |

---

## Installation

### Linux / macOS

```bash
git clone https://github.com/xplus-finance/ASSISTANT_AI.git
cd ASSISTANT_AI
bash install.sh
```

Supports **apt** (Ubuntu/Debian), **brew** (macOS), **dnf** (Fedora), **pacman** (Arch).

### Windows

```powershell
git clone https://github.com/xplus-finance/ASSISTANT_AI.git
cd ASSISTANT_AI
powershell -ExecutionPolicy Bypass -File install.ps1
```

Both installers are interactive, step-by-step. No technical experience required.
Estimated time: **5-10 minutes**.

> The installer is idempotent — safe to run multiple times.

---

## Requirements

| Requirement | Version | Notes |
|-------------|---------|-------|
| **OS** | Windows 10+, Linux, macOS | Cross-platform |
| **Python** | 3.12+ | With venv and pip |
| **Claude Code CLI** | Latest | `npm install -g @anthropic-ai/claude-code` (requires Pro or Max subscription) |
| **ffmpeg** | Any | Audio processing (auto-installed by installer) |
| **Node.js** | 18+ | Only for WhatsApp Baileys channel |
| **CUDA GPU** | Optional | Faster Whisper transcription |

Platform-specific packages are handled automatically by the installer.

---

## Channels

| Channel | Cost | Ban Risk | Setup Time | Recommended |
|---------|------|----------|------------|-------------|
| **Telegram** | Free | None | 2 min | Start here |
| **WhatsApp Baileys** | ~$2/mo | Medium | 15 min | Casual use |
| **WhatsApp Business API** | ~$5-20/mo | None | 1-2 hrs | Production |

Start with Telegram. It's free, zero risk, and takes minutes.

---

## Commands

The assistant understands **natural language**, but also accepts direct commands:

### Information
| Command | Description |
|---------|-------------|
| `!status` | System status, uptime, memory usage |
| `!yo` | Your profile: learned preferences, stats |
| `!help` | List all available commands |

### Memory
| Command | Description |
|---------|-------------|
| `!memoria` | View stored memories |
| `!memoria buscar <text>` | Search memories |
| `!recuerda <text>` | Save to permanent memory |

### Tasks
| Command | Description |
|---------|-------------|
| `!tareas` | View pending tasks |
| `!tarea nueva <desc>` | Create task |
| `recuerdame [something] a las [time]` | Natural language reminder |

### Web & Learning
| Command | Description |
|---------|-------------|
| `!busca <query>` | Web search |
| `!aprende <url>` | Fetch and learn from URL |

### Terminal & Files
| Command | Description |
|---------|-------------|
| `!cmd <command>` | Execute in sandbox |
| `!screenshot` | Take and send screenshot |
| `lee el archivo [path]` | Read file contents |

### Skills & MCP
| Command | Description |
|---------|-------------|
| `!skills` | List available skills |
| `!skill crear <desc>` | Create a new skill |
| `!mcp crear <desc>` | Create, install and activate an MCP server |
| `!mcp list` | List MCP servers |

---

## Architecture

```
  You (Telegram / WhatsApp)
         |
         v
+---------------------+
|   Channel Layer      |  Telegram Bot / WhatsApp Baileys / Business API
+--------+------------+
         |
         v
+---------------------+
|   SecurityGuardian   |  Chat ID auth - PIN verification - Rate limiting
+--------+------------+   Prompt injection detection - Output scanning
         |
         v
+---------------------+
|   Gateway            |  Central orchestrator - Message pipeline
+---+--------+--------+  Session management - Onboarding
    |        |
    v        v
+--------+ +--------------+
| Memory | | Claude Code   |  Brain (uses your subscription, NOT API key)
| Engine | | Bridge        |  Persistent session - One-shot fallback
+--------+ +------+-------+
                  |
           +------+------+
           |   Skills     |  Terminal - Files - Web - Audio - MCP
           |   Registry   |  Hot-reload - Runtime creation
           +-------------+
```

The assistant runs Claude Code as a **separate process** — it never interferes with your own Claude Code sessions. Multiple instances can run simultaneously.

---

## Security

| Layer | Mechanism |
|-------|-----------|
| **Authentication** | Only the configured `AUTHORIZED_CHAT_ID` can interact. All others silently rejected. |
| **PIN Verification** | Sensitive operations require a bcrypt-hashed PIN. Stored securely, never in plaintext. |
| **Input Sanitization** | FTS5 query sanitization, path traversal prevention, SSRF blocking on private IPs. |
| **Prompt Injection Detection** | 28 regex patterns detect injection attempts. Logged for audit. |
| **Output Scanning** | Responses scanned for accidentally leaked secrets (tokens, keys, passwords) before delivery. |
| **Rate Limiting** | Configurable messages-per-minute limit prevents abuse. |
| **File Permissions** | Automatic hardening on startup: `.env` (600), `data/` (700), `logs/` (700). |
| **Sandboxed Execution** | Commands run inside bubblewrap (Linux) or subprocess with timeout (Windows/Mac). |

---

## Self-Evolution

The assistant can modify its own source code, create new tools, and restart itself:

- **Hot-reload**: Changes to utility modules apply instantly via `importlib.reload()`
- **Auto-restart**: Changes to core modules trigger a full process restart (`os.execv`)
- **Syntax validation**: Every modification is validated with `ast.parse()` before applying
- **Automatic backups**: Original files backed up to `.backups/` before any change
- **Skill creation**: New skills created at runtime, loaded by the watchdog-based registry
- **MCP server creation**: Generates, installs (venv + deps), and registers MCP servers automatically

With systemd, `Restart=always` ensures the assistant recovers from any failure within 10 seconds.

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | — | Bot token from @BotFather |
| `AUTHORIZED_CHAT_ID` | Yes | — | Your Telegram Chat ID |
| `SECURITY_PIN` | No | *(empty)* | PIN for sensitive operations |
| `CLAUDE_CLI_PATH` | No | `claude` | Path to Claude CLI executable |
| `PROJECTS_BASE_DIR` | No | *(auto-detected)* | Base directory for projects |
| `DB_ENCRYPTION_KEY` | No | *(empty)* | Database encryption key (generated by installer) |
| `WHISPER_MODEL` | No | `medium` | STT model: tiny, base, small, medium, large-v3 |
| `TTS_ENGINE` | No | `auto` | TTS engine: auto, chatterbox, espeak |
| `TIMEZONE` | No | `America/New_York` | Timezone for scheduled tasks |
| `LOG_LEVEL` | No | `INFO` | Logging level |

---

## Running

### Development

```bash
# Linux/macOS
source .venv/bin/activate
python -m src.main

# Windows
.venv\Scripts\activate
python -m src.main
```

### Production (Linux — systemd)

```bash
sudo systemctl start ai-assistant
sudo systemctl enable ai-assistant
journalctl -u ai-assistant -f
```

### Windows (auto-start)

The installer can configure a Windows Scheduled Task that launches the assistant at login.
Alternatively, double-click `start.bat`.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `TELEGRAM_BOT_TOKEN not set` | Check your `.env` file |
| Bot doesn't respond | Verify token with @BotFather, restart assistant |
| `Unauthorized` on message | Your Chat ID doesn't match `AUTHORIZED_CHAT_ID` |
| Audio/whisper error | Verify ffmpeg: `ffmpeg -version` |
| `claude: command not found` | Install Claude CLI: `npm install -g @anthropic-ai/claude-code` |
| Task hit max turns | Complex tasks auto-retry with higher limits; split into smaller steps if needed |

---

## Contributing

1. Fork the repository
2. Create a branch: `git checkout -b feature-name`
3. Follow the project's code style (see below)
4. Run tests: `pytest tests/`
5. Run linter: `ruff check src/`
6. Open a Pull Request

### Code Style

- Python 3.12+ with type hints (`str | None`, `list[str]`)
- `from __future__ import annotations` in every module
- `structlog` for logging (never `print()`)
- Parameterized SQL queries exclusively (never f-strings)
- Async-first; `asyncio.to_thread()` for blocking calls

---

## License

MIT — see [LICENSE](LICENSE).

---

<div align="center">

**Built with determination.**

[Report Bug](https://github.com/xplus-finance/ASSISTANT_AI/issues) · [Request Feature](https://github.com/xplus-finance/ASSISTANT_AI/issues)

</div>
