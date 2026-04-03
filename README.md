<div align="center">

# Personal AI Assistant

Your own private AI assistant that lives on your machine and talks to you via Telegram or WhatsApp. Powered by Claude Code CLI with your existing subscription — no API keys, no per-token costs, full privacy.

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

Un asistente personal que vive en tu computadora. Se comunica contigo por Telegram o WhatsApp, ejecuta comandos en tu sistema, busca informacion en la web, programa tareas, trabaja en tus proyectos de codigo y aprende de cada interaccion.

Incluye una mascota de escritorio animada que reacciona en tiempo real: teclea cuando el agente piensa, corre cuando ejecuta tareas, duerme cuando no hay actividad, y camina libremente por todos tus monitores.

Un solo usuario autorizado. Nadie mas puede interactuar con el. Todos los datos almacenados localmente, cifrados.

~60 archivos fuente Python. 14+ skills integradas. 8 capas de seguridad. Auto-aprendizaje con decaimiento temporal. Mascota de escritorio interactiva.

---

## Capacidades

| Auto-aprendizaje profundo | Mascota de escritorio | Voz entrada/salida |
|---|---|---|
| Aprende de cada interaccion: registra ejecuciones, patrones de exito, errores y sus soluciones. Clasifica tareas en 7 tipos y aplica el mejor metodo aprendido. Hechos con ponderacion temporal (lo reciente pesa mas). Deduplicacion por similitud semantica. Decaimiento automatico de conocimiento obsoleto. | 5 mascotas (perro, gato, robot, zorro, buho) con 6 animaciones en 5 direcciones. Reacciona al estado del agente: teclea, corre por los monitores, duerme, se entristece. Arrastrable, multi-monitor, sticky en todos los workspaces. | Notas de voz con faster-whisper (local, sin nube). Multiples motores TTS: chatterbox, espeak, gTTS, pyttsx3. |

| Memoria permanente | Seguridad en 8 capas | Multi-plataforma |
|---|---|---|
| Conversaciones, hechos con fuente de origen, procedimientos, ejecuciones, patrones y errores en SQLite cifrado con AES-256. Historial cruzado de 365 dias. Deduplicacion avanzada. Correcciones del usuario reemplazan hechos obsoletos. | Autenticacion, PIN bcrypt, sanitizacion, deteccion de prompt injection (30+ patrones), escaneo de salida, rate limiting por severidad, permisos automaticos, ejecucion en sandbox (bubblewrap). | Windows 10+ (PowerShell, Task Scheduler), Linux (apt/dnf/pacman, systemd), macOS (Homebrew, launchd). Mismo codigo, instalador interactivo de 11 pasos. |

| Auto-evolucion | Control de escritorio | Clasificacion de tareas |
|---|---|---|
| Crea skills y servidores MCP en runtime. Hot-reload con validacion de sintaxis, auto-backup y reinicio graceful. | Capturas de pantalla, gestion de ventanas, escaneo de pestanas del navegador (CDP + xdotool), escritura en teclado. Soporte multi-monitor. | Clasifica automaticamente cada mensaje en 7 tipos (email, desktop, code, search, file, command, general) para aplicar el mejor metodo aprendido. |

---

## Instalacion

### Linux / macOS

```bash
git clone https://github.com/mundowise/ASSISTANT_AI.git
cd ASSISTANT_AI
bash install.sh
```

Detecta automaticamente `apt`, `dnf`, `pacman` o `brew` e instala dependencias del sistema. En macOS, bubblewrap se omite automaticamente (usa aislamiento por subprocess).

### Windows

```powershell
git clone https://github.com/mundowise/ASSISTANT_AI.git
cd ASSISTANT_AI
powershell -ExecutionPolicy Bypass -File install.ps1
```

Ambos instaladores son interactivos, paso a paso, con 11 pasos incluyendo configuracion de canal, modelo de voz, mascota de escritorio y seguridad. Tiempo estimado: 5-10 minutos.

> El instalador es idempotente — seguro ejecutar multiples veces. Si falla, te dice exactamente que salio mal y como resolverlo.

### Despues de instalar

```bash
# Linux/macOS
source .venv/bin/activate
python -m src.main

# Windows
.venv\Scripts\activate
python -m src.main
# O doble clic en start.bat
```

---

## Requisitos

| Requisito | Version | Notas |
|-----------|---------|-------|
| **OS** | Windows 10+, Linux, macOS | Multiplataforma |
| **Python** | 3.12+ | Con venv y pip. Python 3.13 soportado |
| **Claude Code CLI** | Ultimo | `npm install -g @anthropic-ai/claude-code` (requiere suscripcion Pro o Max) |
| **ffmpeg** | Cualquiera | Procesamiento de audio (instalado automaticamente) |
| **Node.js** | 18+ | Solo para canal WhatsApp Baileys |
| **PyQt6** | Opcional | Mascota de escritorio (instalado automaticamente si activas la mascota) |
| **GPU CUDA** | Opcional | Transcripcion mas rapida con faster-whisper |

---

## Mascota de escritorio

5 mascotas animadas que viven en tu escritorio y reaccionan al estado del agente:

| Mascota | Estilo |
|---------|--------|
| Perro (Golden Retriever) | Fiel, mueve la cola, se duerme acurrucado |
| Gato (Naranja atigrado) | Elegante, camina con gracia felina |
| Robot | Luces LED, antena, jets al correr |
| Zorro (Rojo) | Cola frondosa, trot elegante |
| Buho (Gran Buho Real) | Ojazos, gira la cabeza, vuela |

| Estado del agente | Animacion | Comportamiento |
|---|---|---|
| Esperando | Idle / Walk | Camina libremente por todos los monitores |
| Procesando tu mensaje | Type | Se sienta y teclea en un teclado |
| Ejecutando tarea | Run | Corre por todos los monitores |
| Error | Sad | Se sienta triste |
| 5 min sin actividad | Sleep | Se duerme |

Sprites en 5 direcciones (side, front, back, front_side, back_side). Movimiento 2D libre. Sticky en todos los workspaces (Linux/macOS). Clic derecho para cambiar mascota o ver animaciones.

Para activar, agrega a `.env`:
```
PET_ENABLED=true
PET_TYPE=dog
```

Para usar sprites propios, reemplaza los PNG en `src/pet/assets/{animal}/`.

---

## Canales

| Canal | Costo | Riesgo de ban | Setup | Recomendado |
|-------|-------|---------------|-------|-------------|
| **Telegram** | Gratis | Ninguno | 2 min | Empezar aqui |
| **WhatsApp Baileys** | ~$2/mes | Medio | 15 min | Uso casual |
| **WhatsApp Business API** | ~$5-20/mes | Ninguno | 1-2 hrs | Produccion |

---

## Skills integradas

14+ skills disponibles desde la instalacion:

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

Puedes crear skills adicionales en runtime con `!skill crear [descripcion]`. Se validan con `ast.parse()`, se respaldan automaticamente y se cargan via hot-reload sin reinicio.

---

## Memoria y auto-aprendizaje

| Tipo | Persistencia | Descripcion |
|------|-------------|-------------|
| **Hechos permanentes** | Indefinida | Datos extraidos automaticamente de cada conversacion, con deduplicacion semantica y fuente de origen |
| **Correcciones** | Indefinida | Si dices "eso esta mal", el hecho original se marca como obsoleto y se reemplaza |
| **Procedimientos** | Indefinida | Lecciones aprendidas: que funciono, que fallo, trucos descubiertos |
| **Registro de ejecuciones** | Indefinida | Cada tarea registrada: tipo, duracion, metodo, exito/fallo |
| **Patrones de tareas** | Indefinida | Mejores metodos por tipo de tarea con tasa de exito acumulada |
| **Errores y soluciones** | Indefinida | Errores encontrados y como se resolvieron, con score de efectividad |
| **Resumenes de sesion** | Indefinida | Resumen automatico al cerrar cada sesion |
| **Historial cruzado** | 365 dias | Contexto de sesiones anteriores disponible en nuevas conversaciones |
| **Base de conocimiento** | Indefinida | Informacion obtenida de busquedas web y URLs, con cache |

### Ponderacion temporal

Los hechos recientes pesan mas que los antiguos. Hechos no accedidos en 30+ dias pierden relevancia gradualmente (decaimiento del 10% por ciclo). Esto evita que el contexto se contamine con informacion obsoleta.

### Presupuesto de contexto

El system prompt se enriquece automaticamente con historial de ejecuciones similares, estadisticas de exito, mejores metodos aprendidos y errores conocidos a evitar — todo dentro de un presupuesto de tokens configurable para no exceder el contexto de Claude.

SQLite local con cifrado AES-256 opcional (SQLCipher via APSW). Indices FTS5 para busqueda full-text. Optimizacion automatica periodica (VACUUM/ANALYZE).

---

## Variables de entorno

Copia `.env.example` a `.env` o usa el instalador interactivo.

| Variable | Requerida | Default | Descripcion |
|----------|-----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | Si | — | Token de @BotFather |
| `AUTHORIZED_CHAT_ID` | Si | — | Tu Chat ID de Telegram |
| `SECURITY_PIN` | Si | — | PIN para operaciones sensibles (minimo 4 caracteres) |
| `CLAUDE_CLI_PATH` | No | `claude` | Ruta al ejecutable Claude CLI |
| `PROJECTS_BASE_DIR` | No | *(auto)* | Directorio base para proyectos |
| `DB_ENCRYPTION_KEY` | No | *(auto)* | Clave de cifrado de DB (generada por el instalador) |
| `WHISPER_MODEL` | No | `medium` | Modelo STT: tiny, base, small, medium, large-v3 |
| `TTS_MODEL` | No | `chatterbox` | Motor TTS: chatterbox, espeak, gTTS, pyttsx3 |
| `PET_ENABLED` | No | `false` | Activar mascota de escritorio (requiere PyQt6) |
| `PET_TYPE` | No | `dog` | Tipo de mascota: dog, cat, robot, fox, owl |
| `PET_SIZE` | No | `96` | Tamano del sprite en pixeles |
| `PET_MONITOR` | No | `0` | Monitor donde aparece (0 = primario) |
| `TIMEZONE` | No | `America/New_York` | Zona horaria para tareas programadas |
| `MAX_MESSAGES_PER_MINUTE` | No | `20` | Limite de mensajes por minuto (anti-flood) |
| `REQUIRE_APPROVAL` | No | `true` | Requiere aprobacion antes de acciones destructivas |
| `LOG_LEVEL` | No | `INFO` | Nivel de logging: DEBUG, INFO, WARNING, ERROR |

---

<a id="seguridad"></a>

## Seguridad

8 capas de proteccion:

1. **Autenticacion** — Solo responde al `AUTHORIZED_CHAT_ID` configurado
2. **PIN bcrypt** — Operaciones destructivas requieren PIN. 3 fallos = bloqueo 24h
3. **Sanitizacion de entrada** — Validacion de paths, comandos y nombres de archivo
4. **Deteccion de prompt injection** — 30+ patrones regex detectan intentos de manipulacion
5. **Escaneo de salida** — Detecta tokens, API keys y credenciales antes de enviar
6. **Rate limiting** — Por severidad de accion, no solo por volumen de mensajes
7. **Permisos de archivo** — `.env` (600), `data/` (700), `logs/` (700) — automatico al iniciar
8. **Ejecucion en sandbox** — bubblewrap (Linux), subprocess aislado (Windows/macOS)

Acciones destructivas detectadas por analisis de intencion natural requieren aprobacion explicita antes de ejecutarse.

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
+--------+------------+   Prompt injection (30+ patrones) - Escaneo de salida
         |
         v
+---------------------+
|   Gateway            |  Orquestador central - Task classifier - Execution tracker
+---+--------+--------+  Sesiones - Context builder (token budget) - Auto-learning
    |        |     |
    v        v     v
+--------+ +------+------+ +-------------+
| Memory | | Claude Code  | | Desktop Pet |
| Engine | | Bridge       | | (PyQt6)     |
+--------+ +------+------+ +-------------+
    |             |
    v             v
+--------+ +-------------+
| FTS5   | |   Skills     |  14+ built-in + runtime creation
| Search | |   Registry   |  Hot-reload - Watchdog - Conflict detection
+--------+ +-------------+
```

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
launchctl load ~/Library/LaunchAgents/com.personal-ai-assistant.plist
launchctl start com.personal-ai-assistant
tail -f logs/launchd-stdout.log
```

### Windows (auto-start)

El instalador configura una tarea en Task Scheduler que arranca el asistente al iniciar sesion. Alternativa: doble clic en `start.bat`.

---

## Solucion de problemas

| Problema | Solucion |
|----------|----------|
| `ModuleNotFoundError` al iniciar | Ejecuta: `source .venv/bin/activate && pip install -e ".[dev]"` |
| `TELEGRAM_BOT_TOKEN not set` | Verificar archivo `.env` tiene el token |
| Bot no responde | Verificar token con @BotFather, reiniciar con `python -m src.main` |
| `Unauthorized` en mensaje | Chat ID no coincide con `AUTHORIZED_CHAT_ID` en `.env` |
| Error de audio/whisper | Verificar ffmpeg: `ffmpeg -version`. Si falta: `sudo apt install ffmpeg` |
| `claude: command not found` | `npm install -g @anthropic-ai/claude-code` y luego `claude` para autenticar |
| Tarea alcanza max turns | Dividir en pasos mas pequenos |
| Mascota no aparece | Verificar `PET_ENABLED=true` en `.env` y `pip install PyQt6` |
| Mascota no se ve en Linux | `sudo apt install libxcb-cursor0` (Ubuntu/Debian) |
| Instalador falla en paso 6 | Revisa el log que muestra. Error comun: sin internet o pip desactualizado |
| `audioop` error en Python 3.13 | Se instala automaticamente (`audioop-lts`). Si falla: `pip install audioop-lts` |
| Venv corrupto | Borra `.venv/` y ejecuta el instalador de nuevo |

---

<a id="documentacion"></a>

## Documentacion

| Documento | Contenido |
|-----------|-----------|
| [PASO_A_PASO.md](docs/PASO_A_PASO.md) | Guia completa de instalacion y configuracion |
| [TELEGRAM_SETUP.md](docs/TELEGRAM_SETUP.md) | Configuracion manual del canal Telegram |
| [WHATSAPP_BAILEYS_SETUP.md](docs/WHATSAPP_BAILEYS_SETUP.md) | WhatsApp con Baileys (no oficial) |
| [WHATSAPP_BUSINESS_SETUP.md](docs/WHATSAPP_BUSINESS_SETUP.md) | WhatsApp Business API (oficial) |
| [CLAUDE.md](CLAUDE.md) | Guia de desarrollo y mapa de modulos |

---

## Contribuir

1. Fork del repositorio
2. Crear branch: `git checkout -b feature/tu-feature`
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
- Imports con guard `try/except` para dependencias opcionales

---

## Licencia

MIT — ver [LICENSE](LICENSE).

---

---

<a id="english"></a>

## English

### What is this

A private, self-hosted AI assistant that runs on your machine and communicates via Telegram or WhatsApp. Powered by Claude Code CLI with your existing subscription — no API keys, no per-token costs, full local privacy.

Includes an animated desktop pet that reacts in real time: types when the agent thinks, runs across monitors when executing tasks, sleeps when inactive, and walks freely across all your screens.

~60 Python source files. 14+ built-in skills. 8 security layers. Deep auto-learning with temporal weighting. Desktop pet companion. Runs on Windows 10+, Linux and macOS.

### Key features

- **Deep auto-learning**: logs every execution (type, duration, method, success/fail), learns best methods per task type, remembers error solutions, deduplicates facts semantically. Recent knowledge is weighted higher. Unused facts decay over time. User corrections replace outdated facts.
- **Desktop pet**: 5 pets (dog, cat, robot, fox, owl) with 6 animations in 5 directions. Reacts to agent state in real time. Draggable, multi-monitor, sticky on all workspaces.
- **Permanent memory**: facts with source attribution, procedures, session summaries, 365-day cross-session history. SQLite with optional AES-256 encryption. FTS5 full-text search. Periodic auto-optimization.
- **14+ skills**: terminal, files, memory, tasks, learning, desktop control, MCP server creation, skill creation, Claude Code integration, system monitor, file search, git, network diagnostics, package management. Create new skills at runtime.
- **Voice**: faster-whisper STT (fully local), multiple TTS engines (chatterbox, espeak, gTTS, pyttsx3).
- **8-layer security**: authentication, bcrypt PIN, input sanitization, prompt injection detection (30+ patterns), output scanning, severity-based rate limiting, auto-hardened file permissions, sandboxed execution.
- **Self-evolution**: creates its own skills and MCP servers at runtime. Hot-reload with syntax validation, automatic backups and graceful restart.
- **Context budgeting**: system prompt enriched with execution history, success stats, best methods and known errors — all within a configurable token budget.
- **Cross-platform**: Windows (PowerShell installer, Task Scheduler), Linux (apt/dnf/pacman, systemd), macOS (Homebrew, launchd). Single codebase.

### Quick start

```bash
# Linux/macOS
git clone https://github.com/mundowise/ASSISTANT_AI.git
cd ASSISTANT_AI && bash install.sh

# Windows
git clone https://github.com/mundowise/ASSISTANT_AI.git
cd ASSISTANT_AI
powershell -ExecutionPolicy Bypass -File install.ps1
```

### Requirements

| Requirement | Version |
|-------------|---------|
| OS | Windows 10+, Linux, macOS |
| Python | 3.12+ (3.13 supported) |
| Claude Code CLI | Latest (`npm install -g @anthropic-ai/claude-code`) |
| ffmpeg | Any (auto-installed) |
| Node.js 18+ | Only for WhatsApp Baileys channel |
| PyQt6 | Optional (desktop pet) |
| CUDA GPU | Optional (faster whisper transcription) |

### License

MIT — see [LICENSE](LICENSE).

---

<div align="center">

**Built with determination.**

[Report Bug](https://github.com/mundowise/ASSISTANT_AI/issues) · [Request Feature](https://github.com/mundowise/ASSISTANT_AI/issues)

</div>
