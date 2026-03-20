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

Un asistente personal que vive en tu computadora. Se comunica contigo por Telegram o WhatsApp, ejecuta comandos en tu sistema, busca informacion en la web, programa tareas, trabaja en tus proyectos de codigo y aprende tus preferencias.

Incluye una mascota de escritorio animada que reacciona en tiempo real: teclea cuando el agente piensa, corre cuando ejecuta tareas, duerme cuando no hay actividad, y camina libremente por todos tus monitores.

Un solo usuario autorizado. Nadie mas puede interactuar con el. Todos los datos almacenados localmente.

~60 archivos fuente Python. 14 skills integradas. 8 capas de seguridad. Auto-aprendizaje profundo. Mascota de escritorio.

---

## Capacidades

| Auto-aprendizaje profundo | Mascota de escritorio | Voz entrada/salida |
|---|---|---|
| Aprende de cada interaccion: registra ejecuciones, patrones de exito, errores y sus soluciones. Clasifica tareas en 7 tipos y aplica el mejor metodo aprendido. Cada tarea repetida le cuesta menos tiempo. | 5 mascotas (perro, gato, robot, zorro, buho) con 6 animaciones en 5 direcciones. Reacciona al estado del agente: teclea, corre por los monitores, duerme, se entristece. Arrastrable, multi-monitor, sticky en todos los workspaces. | Notas de voz con faster-whisper (local). Multiples motores TTS: chatterbox, espeak, gTTS, pyttsx3. |

| Memoria permanente | Seguridad en 8 capas | Multi-plataforma |
|---|---|---|
| Conversaciones, hechos, procedimientos, ejecuciones, patrones y errores en SQLite cifrado con AES-256. Historial cruzado de 365 dias. Deduplicacion automatica. | Autenticacion, PIN bcrypt, sanitizacion, deteccion de prompt injection, escaneo de salida, rate limiting, permisos automaticos, ejecucion en sandbox. | Windows 10+ (PowerShell, Task Scheduler), Linux (apt/dnf/pacman, systemd), macOS (Homebrew, launchd). Mismo codigo. |

| Auto-evolucion | Control de escritorio | Clasificacion de tareas |
|---|---|---|
| Crea skills y servidores MCP en runtime. Hot-reload con auto-restart. Validacion y backups automaticos. | Capturas de pantalla, gestion de ventanas, escaneo de pestanas del navegador, escritura en teclado. Soporte dual monitor. | Clasifica automaticamente cada mensaje en 7 tipos (email, desktop, code, search, file, command, general) para aplicar el mejor metodo aprendido. |

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

Ambos instaladores son interactivos, paso a paso, con 11 pasos incluyendo configuracion de la mascota de escritorio. Tiempo estimado: 5-10 minutos.

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
| **PyQt6** | Opcional | Mascota de escritorio (`pip install PyQt6`, instalado automaticamente si activas la mascota) |
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

| Estado del agente | Animacion de la mascota | Comportamiento |
|---|---|---|
| Esperando | Idle / Walk | Camina libremente por todos los monitores |
| Procesando tu mensaje | Type | Se sienta y teclea en un teclado |
| Ejecutando tarea | Run | Corre por todos los monitores |
| Error | Sad | Se sienta triste, no se mueve |
| 5 min sin actividad | Sleep | Se duerme, no se mueve |

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

## Memoria y auto-aprendizaje

| Tipo | Persistencia | Descripcion |
|------|-------------|-------------|
| **Hechos permanentes** | Indefinida | Datos extraidos automaticamente de cada conversacion, con deduplicacion |
| **Procedimientos** | Indefinida | Lecciones aprendidas: que funciono, que fallo, trucos descubiertos |
| **Registro de ejecuciones** | Indefinida | Cada tarea registrada: tipo, duracion, metodo, exito/fallo |
| **Patrones de tareas** | Indefinida | Mejores metodos por tipo de tarea con tasa de exito acumulada |
| **Errores y soluciones** | Indefinida | Errores encontrados y como se resolvieron, para no repetirlos |
| **Resumenes de sesion** | Indefinida | Resumen automatico al cerrar cada sesion |
| **Historial cruzado** | 365 dias | Contexto de sesiones anteriores disponible en nuevas conversaciones |
| **Base de conocimiento** | Indefinida | Informacion obtenida de busquedas web y URLs |

El system prompt se enriquece automaticamente con historial de ejecuciones similares, estadisticas de exito, mejores metodos aprendidos y errores conocidos a evitar.

SQLite local con cifrado AES-256 opcional (SQLCipher via APSW). Indices FTS5 para busqueda full-text.

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
| `PET_ENABLED` | No | `false` | Activar mascota de escritorio (requiere PyQt6) |
| `PET_TYPE` | No | `dog` | Tipo de mascota: dog, cat, robot, fox, owl |
| `PET_SIZE` | No | `96` | Tamano del sprite en pixeles |
| `PET_MONITOR` | No | `0` | Monitor donde aparece (0 = primario) |
| `TIMEZONE` | No | `America/New_York` | Zona horaria para tareas programadas |
| `LOG_LEVEL` | No | `INFO` | Nivel de logging |

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
|   Gateway            |  Orquestador central - Task classifier - Execution tracker
+---+--------+--------+  Sesiones - Context builder - Auto-learning
    |        |     |
    v        v     v
+--------+ +------+------+ +-------------+
| Memory | | Claude Code  | | Desktop Pet |
| Engine | | Bridge       | | (PyQt6)     |
+--------+ +------+------+ +-------------+
                  |
           +------+------+
           |   Skills     |  14 built-in + runtime creation
           |   Registry   |  Hot-reload - Watchdog
           +-------------+
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
| Mascota no aparece | Verificar `PET_ENABLED=true` en .env y PyQt6 instalado |
| Mascota no se ve en Linux | Instalar `libxcb-cursor0` (Ubuntu/Debian) |

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

A private, self-hosted assistant that runs on your machine and communicates via Telegram or WhatsApp. Uses Claude Code CLI with your existing subscription — no API keys, no per-token costs.

Includes an animated desktop pet that reacts in real time: types when the agent thinks, runs across monitors when executing tasks, sleeps when inactive, and walks freely across all your screens.

~60 Python source files. 14 built-in skills. 8 security layers. Deep auto-learning. Desktop pet companion. Runs on Windows 10+, Linux and macOS.

### What it does

- **Deep auto-learning**: logs every execution (type, duration, method, success/fail), learns best methods per task type, remembers error solutions, deduplicates facts. Each repeated task gets faster.
- **Desktop pet**: 5 pets (dog, cat, robot, fox, owl) with 6 animations in 5 directions. Reacts to agent state: types when processing, runs across monitors when executing, sleeps when inactive. Draggable, multi-monitor, sticky on all workspaces.
- **Permanent memory**: facts, procedures, session summaries, 365-day cross-session history. SQLite with optional AES-256 encryption.
- **14 skills**: terminal, files, memory, tasks, learning, desktop control, MCP server creation, skill creation, Claude Code integration, system monitor, file search, git, network diagnostics, package management.
- **Voice**: faster-whisper STT (local), multiple TTS engines (chatterbox, espeak, gTTS, pyttsx3).
- **Security**: 8 layers — authentication, bcrypt PIN, input sanitization, prompt injection detection (28 patterns), output scanning, rate limiting, auto-hardened file permissions, sandboxed execution.
- **Self-evolution**: creates its own skills and MCP servers at runtime. Hot-reload with syntax validation and automatic backups.
- **Task classification**: auto-classifies messages into 7 types (email, desktop, code, search, file, command, general) and applies best learned method.
- **Desktop control**: screenshots, window management, browser tab scanning, keyboard input. Dual monitor support.
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
| PyQt6 | Optional (desktop pet) |
| CUDA GPU | Optional (faster whisper) |

### License

MIT — see [LICENSE](LICENSE).

---

<div align="center">

**Built with determination.**

[Report Bug](https://github.com/xplus-finance/ASSISTANT_AI/issues) · [Request Feature](https://github.com/xplus-finance/ASSISTANT_AI/issues)

</div>
