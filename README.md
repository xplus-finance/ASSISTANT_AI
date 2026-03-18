<div align="center">

# Personal AI Assistant

Asistente privado que corre en tu maquina y se comunica via Telegram o WhatsApp. Usa Claude Code CLI con tu suscripcion — sin API keys, sin costos por token.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-green.svg)](https://python.org)
[![Claude Code](https://img.shields.io/badge/Claude_Code-CLI-orange.svg)](https://docs.anthropic.com/en/docs/claude-code)
[![Windows](https://img.shields.io/badge/Windows-10+-blue.svg)](https://www.microsoft.com)
[![Linux](https://img.shields.io/badge/Linux-Ubuntu_22.04+-orange.svg)](https://ubuntu.com)
[![macOS](https://img.shields.io/badge/macOS-13+-lightgrey.svg)](https://apple.com)

[English](#english) | [Instalacion](#instalacion) | [Documentacion](#documentacion) | [Seguridad](#seguridad)

---

</div>

## Que es esto

Un asistente personal que vive en tu computadora. Se comunica contigo por Telegram o WhatsApp, ejecuta comandos en tu sistema, recuerda todo entre sesiones, busca informacion en la web, programa tareas, trabaja en tus proyectos de codigo y aprende tus preferencias.

Un solo usuario autorizado. Nadie mas puede interactuar con el. Todos los datos almacenados localmente — nada sale de tu maquina.

55 archivos fuente Python. 14 skills integradas. 8 capas de seguridad.

---

## Capacidades

| Memoria permanente | Seguridad en 8 capas | Voz entrada/salida |
|---|---|---|
| Conversaciones, hechos y preferencias en SQLite cifrado con AES-256. Persistente entre reinicios. Historial cruzado de 7 dias entre sesiones. | Autenticacion, PIN bcrypt, sanitizacion, deteccion de prompt injection, escaneo de salida, rate limiting, permisos automaticos, ejecucion en sandbox. | Notas de voz con faster-whisper (local). Multiples motores TTS: chatterbox, espeak, gTTS, pyttsx3. |

| Auto-evolucion | Multi-plataforma | Escritorio |
|---|---|---|
| Crea sus propias skills y servidores MCP en tiempo de ejecucion. Hot-reload con auto-restart. Validacion de sintaxis y backups automaticos. | Windows 10+ (PowerShell, Task Scheduler), Linux (apt/dnf/pacman, systemd), macOS (Homebrew, launchd). Mismo codigo, mismas funciones. | Control de ventanas, capturas de pantalla, escaneo de pestanas del navegador, escritura en teclado. Soporte dual monitor. |

---

## Instalacion

### Linux / macOS

```bash
git clone https://github.com/xplus-finance/ASSISTANT_AI.git
cd ASSISTANT_AI
bash install.sh
```

Detecta automaticamente `apt`, `dnf`, `pacman` o `brew` e instala dependencias.

### Windows

```powershell
git clone https://github.com/xplus-finance/ASSISTANT_AI.git
cd ASSISTANT_AI
powershell -ExecutionPolicy Bypass -File install.ps1
```

Ambos instaladores son interactivos y paso a paso. Tiempo estimado: 5-10 minutos.

> El instalador es idempotente — seguro ejecutar multiples veces.

---

## Requisitos

| Requisito | Version | Notas |
|-----------|---------|-------|
| **OS** | Windows 10+, Linux, macOS | Multiplataforma |
| **Python** | 3.12+ | Con venv y pip |
| **Claude Code CLI** | Ultimo | `npm install -g @anthropic-ai/claude-code` (requiere suscripcion Pro o Max) |
| **ffmpeg** | Cualquiera | Procesamiento de audio (instalado automaticamente) |
| **Node.js** | 18+ | Solo para canal WhatsApp Baileys |
| **GPU CUDA** | Opcional | Transcripcion mas rapida con faster-whisper |

---

## Canales

| Canal | Costo | Riesgo de ban | Setup | Recomendado |
|-------|-------|---------------|-------|-------------|
| **Telegram** | Gratis | Ninguno | 2 min | Empezar aqui |
| **WhatsApp Baileys** | ~$2/mes | Medio | 15 min | Uso casual |
| **WhatsApp Business API** | ~$5-20/mes | Ninguno | 1-2 hrs | Produccion |

---

## Skills integradas

14 skills disponibles desde la instalacion:

| Skill | Funcion | Activacion |
|-------|---------|------------|
| **terminal** | Ejecutar comandos del sistema en sandbox | `!cmd <comando>` |
| **files** | Leer, escribir, buscar y gestionar archivos | `lee el archivo [ruta]` |
| **memory** | Consultar y almacenar memoria permanente | `!memoria`, `!recuerda [algo]` |
| **tasks** | Crear tareas, recordatorios y programar ejecuciones | `!tareas`, `!tarea nueva [desc]` |
| **learning** | Buscar en la web y almacenar conocimiento | `!busca [tema]`, `!aprende [url]` |
| **desktop_control** | Capturas de pantalla, gestion de ventanas, teclado | `!screenshot`, lenguaje natural |
| **mcp_creator** | Generar, instalar y registrar servidores MCP | `!mcp crear [desc]` |
| **skill_creator** | Crear nuevas skills en tiempo de ejecucion | `!skill crear [desc]` |
| **claude_code** | Integrar sesiones de Claude Code para proyectos | Lenguaje natural sobre codigo |
| **system_monitor** | Estado del sistema, CPU, RAM, disco, procesos | `!status` |
| **file_search** | Busqueda avanzada de archivos por nombre/contenido | `busca archivos [patron]` |
| **git** | Operaciones git: status, commit, diff, log, branches | `git status`, lenguaje natural |
| **network** | Diagnostico de red: ping, DNS, puertos, interfaces | `haz ping a [host]` |
| **package_manager** | Gestionar paquetes del sistema (apt/dnf/pacman/brew/winget) | `instala [paquete]` |

---

## Comandos

| Categoria | Comando | Descripcion |
|-----------|---------|-------------|
| Info | `!status` | Estado del sistema, uptime, uso de recursos |
| Info | `!yo` | Tu perfil: preferencias aprendidas, estadisticas |
| Info | `!help` | Lista de comandos disponibles |
| Memoria | `!memoria` | Ver memorias almacenadas |
| Memoria | `!memoria buscar <texto>` | Buscar en memoria |
| Memoria | `!recuerda <texto>` | Guardar en memoria permanente |
| Tareas | `!tareas` | Ver tareas pendientes |
| Tareas | `!tarea nueva <desc>` | Crear tarea |
| Tareas | `recuerdame [algo] a las [hora]` | Recordatorio en lenguaje natural |
| Web | `!busca <query>` | Busqueda web (DuckDuckGo, sin API key) |
| Web | `!aprende <url>` | Obtener y aprender de una URL |
| Terminal | `!cmd <comando>` | Ejecutar en sandbox |
| Desktop | `!screenshot` | Captura de pantalla |
| Skills | `!skills` | Listar skills disponibles |
| Skills | `!skill crear <desc>` | Crear nueva skill |
| MCP | `!mcp crear <desc>` | Crear e instalar servidor MCP |
| MCP | `!mcp list` | Listar servidores MCP |
| Audio | `!voz on/off/auto` | Controlar respuestas de voz |

El asistente entiende lenguaje natural. Los comandos son atajos directos.

---

## Arquitectura

```
  Tu (Telegram / WhatsApp)
         |
         v
+---------------------+
|   Channel Layer      |  Telegram Bot / WhatsApp Baileys / Business API
+--------+------------+
         |
         v
+---------------------+
|   SecurityGuardian   |  Auth por Chat ID - PIN bcrypt - Rate limiting
+--------+------------+   Prompt injection (28 patrones) - Escaneo de salida
         |
         v
+---------------------+
|   Gateway            |  Orquestador central - Pipeline de mensajes
+---+--------+--------+  Sesiones - Onboarding - Context builder
    |        |
    v        v
+--------+ +--------------+
| Memory | | Claude Code   |  Cerebro (usa tu suscripcion, NO API key)
| Engine | | Bridge        |  Sesion persistente - Fallback one-shot
+--------+ +------+-------+
                  |
           +------+------+
           |   Skills     |  14 built-in + runtime creation
           |   Registry   |  Hot-reload - Watchdog
           +-------------+
```

El asistente ejecuta Claude Code como proceso separado — nunca interfiere con tus sesiones propias de Claude Code.

---

## Seguridad

| Capa | Mecanismo |
|------|-----------|
| **Autenticacion** | Solo el `AUTHORIZED_CHAT_ID` configurado puede interactuar. Resto rechazado silenciosamente. |
| **PIN** | Operaciones sensibles requieren PIN con hash bcrypt. Nunca en texto plano. |
| **Sanitizacion** | FTS5 query sanitization, prevencion de path traversal, bloqueo SSRF en IPs privadas. |
| **Prompt injection** | 28 patrones regex detectan intentos de inyeccion. Registrados en audit log. |
| **Escaneo de salida** | Respuestas escaneadas por tokens, keys y passwords filtrados antes de enviar. |
| **Rate limiting** | Limite configurable de mensajes por minuto. |
| **Permisos** | Endurecimiento automatico al arrancar: `.env` (600), `data/` (700), `logs/` (700). |
| **Sandbox** | bubblewrap (Linux), subprocess con timeout (Windows/macOS). |

---

## Auto-evolucion

- **Hot-reload**: Cambios en modulos utilitarios se aplican via `importlib.reload()` sin reiniciar
- **Auto-restart**: Cambios en modulos core disparan restart completo (`os.execv`)
- **Validacion**: Cada modificacion validada con `ast.parse()` antes de aplicar
- **Backups**: Archivos originales respaldados en `.backups/` antes de cualquier cambio
- **Skills**: Nuevas skills creadas en runtime, cargadas por el registry con watchdog
- **MCP**: Genera, instala (venv + deps) y registra servidores MCP automaticamente

Con systemd, `Restart=always` recupera de cualquier fallo en 10 segundos.

---

## Memoria

| Tipo | Persistencia | Descripcion |
|------|-------------|-------------|
| **Hechos permanentes** | Indefinida | Datos guardados explicitamente con `!recuerda` |
| **Procedimientos** | Indefinida | Lecciones aprendidas de errores, nunca se repiten |
| **Resumenes de sesion** | Indefinida | Resumen automatico al cerrar cada sesion |
| **Historial cruzado** | 7 dias | Contexto de sesiones anteriores disponible en nuevas conversaciones |
| **Base de conocimiento** | Indefinida | Informacion obtenida de busquedas web y URLs |

Todo almacenado en SQLite local con cifrado opcional AES-256 via SQLCipher (APSW). Indices FTS5 para busqueda full-text.

---

## Variables de entorno

| Variable | Requerida | Default | Descripcion |
|----------|-----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | Si | — | Token de @BotFather |
| `AUTHORIZED_CHAT_ID` | Si | — | Tu Chat ID de Telegram |
| `SECURITY_PIN` | No | *(vacio)* | PIN para operaciones sensibles |
| `CLAUDE_CLI_PATH` | No | `claude` | Ruta al ejecutable Claude CLI |
| `PROJECTS_BASE_DIR` | No | *(auto)* | Directorio base para proyectos |
| `DB_ENCRYPTION_KEY` | No | *(vacio)* | Clave de cifrado de DB (generada por el instalador) |
| `WHISPER_MODEL` | No | `medium` | Modelo STT: tiny, base, small, medium, large-v3 |
| `TTS_ENGINE` | No | `auto` | Motor TTS: auto, chatterbox, espeak |
| `TIMEZONE` | No | `America/New_York` | Zona horaria para tareas programadas |
| `LOG_LEVEL` | No | `INFO` | Nivel de logging |

---

## Ejecucion

### Desarrollo

```bash
# Linux/macOS
source .venv/bin/activate
python -m src.main

# Windows
.venv\Scripts\activate
python -m src.main
```

### Produccion — Linux (systemd)

```bash
sudo systemctl start ai-assistant
sudo systemctl enable ai-assistant
journalctl -u ai-assistant -f
```

### Produccion — macOS (launchd)

```bash
cp launchd/com.assistant.ai.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.assistant.ai.plist
```

### Windows (auto-start)

El instalador configura una tarea en Task Scheduler que arranca el asistente al iniciar sesion. Alternativa: doble clic en `start.bat`.

---

## Solucion de problemas

| Problema | Solucion |
|----------|----------|
| `TELEGRAM_BOT_TOKEN not set` | Verificar archivo `.env` |
| Bot no responde | Verificar token con @BotFather, reiniciar |
| `Unauthorized` en mensaje | Chat ID no coincide con `AUTHORIZED_CHAT_ID` |
| Error de audio/whisper | Verificar ffmpeg: `ffmpeg -version` |
| `claude: command not found` | `npm install -g @anthropic-ai/claude-code` |
| Tarea alcanza max turns | Dividir en pasos mas pequenos |

---

## Documentacion

| Documento | Contenido |
|-----------|-----------|
| [PASO_A_PASO.md](docs/PASO_A_PASO.md) | Guia completa de instalacion y configuracion |
| [TELEGRAM_SETUP.md](docs/TELEGRAM_SETUP.md) | Configuracion del canal Telegram |
| [WHATSAPP_BAILEYS_SETUP.md](docs/WHATSAPP_BAILEYS_SETUP.md) | WhatsApp con Baileys (no oficial) |
| [WHATSAPP_BUSINESS_SETUP.md](docs/WHATSAPP_BUSINESS_SETUP.md) | WhatsApp Business API (oficial) |
| [CLAUDE.md](CLAUDE.md) | Guia de desarrollo y mapa de modulos |

---

## Contribuir

1. Fork del repositorio
2. Crear branch: `git checkout -b feature-name`
3. Seguir el estilo del proyecto (ver abajo)
4. Tests: `pytest tests/`
5. Linter: `ruff check src/`
6. Abrir Pull Request

### Estilo de codigo

- Python 3.12+ con type hints (`str | None`, `list[str]`)
- `from __future__ import annotations` en cada modulo
- `structlog` para logging (nunca `print()`)
- SQL parametrizado exclusivamente (nunca f-strings)
- Async-first; `asyncio.to_thread()` para llamadas bloqueantes

---

## Licencia

MIT — ver [LICENSE](LICENSE).

---

---

<a id="english"></a>

## English

### What is this

A private, self-hosted assistant that runs on your machine and communicates via Telegram or WhatsApp. It uses Claude Code CLI with your existing subscription — no API keys, no per-token costs.

55 Python source files. 14 built-in skills. 8 security layers. Runs on Windows 10+, Linux and macOS.

### What it does

- **Permanent memory**: facts, procedures learned from mistakes, session summaries, 7-day cross-session history. SQLite with optional AES-256 encryption.
- **14 skills**: terminal, files, memory, tasks, learning, desktop control, MCP server creation, skill creation, Claude Code integration, system monitor, file search, git, network diagnostics, package management.
- **Voice**: faster-whisper STT (local), multiple TTS engines (chatterbox, espeak, gTTS, pyttsx3).
- **Security**: authentication, bcrypt PIN, input sanitization, prompt injection detection (28 patterns), output scanning, rate limiting, auto-hardened file permissions, sandboxed execution.
- **Self-evolution**: creates its own skills and MCP servers at runtime. Hot-reload with syntax validation and automatic backups.
- **Desktop**: screenshots, window management, browser tab scanning, keyboard input. Dual monitor support.
- **Cross-platform**: Windows (PowerShell installer, Task Scheduler), Linux (apt/dnf/pacman, systemd), macOS (Homebrew, launchd).

### Quick start

```bash
# Linux/macOS
git clone https://github.com/xplus-finance/ASSISTANT_AI.git
cd ASSISTANT_AI && bash install.sh

# Windows
git clone https://github.com/xplus-finance/ASSISTANT_AI.git
cd ASSISTANT_AI
powershell -ExecutionPolicy Bypass -File install.ps1
```

### Requirements

| Requirement | Version |
|-------------|---------|
| OS | Windows 10+, Linux, macOS |
| Python | 3.12+ |
| Claude Code CLI | Latest (`npm install -g @anthropic-ai/claude-code`) |
| ffmpeg | Any (auto-installed) |
| Node.js 18+ | Only for WhatsApp Baileys |
| CUDA GPU | Optional (faster whisper) |

### Built-in skills

| Skill | Purpose |
|-------|---------|
| terminal | Execute system commands in sandbox |
| files | Read, write, search and manage files |
| memory | Query and store permanent memory |
| tasks | Create tasks, reminders, scheduled execution |
| learning | Web search and knowledge storage |
| desktop_control | Screenshots, window management, keyboard |
| mcp_creator | Generate, install and register MCP servers |
| skill_creator | Create new skills at runtime |
| claude_code | Claude Code integration for code projects |
| system_monitor | System status: CPU, RAM, disk, processes |
| file_search | Advanced file search by name/content |
| git | Git operations: status, commit, diff, log, branches |
| network | Network diagnostics: ping, DNS, ports, interfaces |
| package_manager | System packages (apt/dnf/pacman/brew/winget) |

### Security

8 layers: chat ID authentication, bcrypt PIN, input sanitization, prompt injection detection, output scanning, rate limiting, automatic file permission hardening, sandboxed execution (bubblewrap on Linux, subprocess with timeout on Windows/macOS).

### License

MIT — see [LICENSE](LICENSE).

---

<div align="center">

**Built with determination.**

[Report Bug](https://github.com/xplus-finance/ASSISTANT_AI/issues) · [Request Feature](https://github.com/xplus-finance/ASSISTANT_AI/issues)

</div>
