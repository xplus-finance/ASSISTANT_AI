<div align="center">

# 🤖 Personal AI Assistant

**Tu propio asistente de IA personal. Accesible desde Telegram o WhatsApp, 24/7, desde cualquier parte del mundo.**

Construido sobre [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI — usa tu suscripción existente, sin API keys, sin costos extra por token.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-green.svg)](https://python.org)
[![Claude Code](https://img.shields.io/badge/Claude_Code-CLI-orange.svg)](https://docs.anthropic.com/en/docs/claude-code)
[![Windows](https://img.shields.io/badge/Windows-10+-blue.svg)](https://www.microsoft.com)
[![Linux](https://img.shields.io/badge/Linux-Ubuntu_22.04+-orange.svg)](https://ubuntu.com)

[English](#english) · [Instalación](#instalación-rápida) · [Documentación](#documentación) · [Seguridad](#seguridad--7-capas)

---

</div>

## ¿Qué es esto?

Un asistente de IA **personal y privado** que vive en tu servidor y se comunica contigo por Telegram o WhatsApp. No es un chatbot genérico — es **tu** asistente: recuerda todo lo que le dices, ejecuta comandos en tu máquina, busca información en la web, programa tareas, trabaja en tus proyectos de código, y aprende tus preferencias con el tiempo.

Diseñado para un solo usuario autorizado. Nadie más puede interactuar con él. Toda la información se almacena cifrada localmente — nunca sale de tu servidor.

---

## Características

| Memoria Permanente | 7 Capas de Seguridad | Audio Bidireccional |
|---|---|---|
| Nunca olvida nada. Cada conversación, dato y preferencia se guarda cifrada con SQLCipher (AES-256) para siempre. | Sandbox, cifrado, anti-injection, rate limiting, validación de output, autenticación, monitoreo. | Envía y recibe notas de voz. Reconocimiento de voz local con faster-whisper. Sin conexión a internet requerida. |

| Autonomía Total | Multi-Canal | Tareas Programadas |
|---|---|---|
| Si no tiene una herramienta, la crea. Si no sabe algo, lo busca. Resuelve problemas solo con Claude Code. | Telegram (gratis), WhatsApp Baileys, WhatsApp Business API. Tú eliges. | Programa recordatorios y tareas para cualquier fecha/hora. Se ejecutan automáticamente. |

| Búsqueda Web | Terminal Segura | Gestión de Archivos |
|---|---|---|
| Busca en DuckDuckGo sin API key. Resume, analiza y guarda conocimiento automáticamente. | Ejecuta comandos dentro de un sandbox con bubblewrap. Acceso controlado al filesystem. | Lee, crea y procesa archivos y documentos. Trabaja en tus proyectos de código directamente. |

---

## Instalación Rápida

### Linux / macOS

```bash
git clone https://github.com/xplus-finance/ASSISTANT_AI.git
cd ASSISTANT_AI
bash install.sh
```

### Windows

```powershell
git clone https://github.com/xplus-finance/ASSISTANT_AI.git
cd ASSISTANT_AI
powershell -ExecutionPolicy Bypass -File install.ps1
```

El instalador te guía paso a paso. No necesitas experiencia técnica.
Tiempo estimado: **5-10 minutos**.

> **Nota:** El instalador es idempotente — puedes ejecutarlo varias veces sin problema.

---

## Requisitos

| Requisito | Versión | Notas |
|-----------|---------|-------|
| **OS** | Windows 10+, Ubuntu 22.04+, macOS | Multiplataforma |
| **Python** | 3.12+ | Con venv y pip |
| **Claude Code CLI** | Última versión | `npm install -g @anthropic-ai/claude-code` (requiere suscripción Pro o Max) |
| **ffmpeg** | Cualquiera | Para procesamiento de audio |
| **bubblewrap** | Cualquiera | Sandbox para comandos (solo Linux, recomendado) |
| **Node.js** | 18+ | Solo si usas WhatsApp Baileys |
| **GPU con CUDA** | Opcional | Para transcripción rápida con Whisper |

### Requisitos adicionales por plataforma

**Windows:** `pip install pyautogui pyperclip pyttsx3` (incluido automáticamente con `install.ps1`)

**Linux:** `sudo apt install xdotool wmctrl scrot xclip bubblewrap ffmpeg`

---

## Canales Disponibles

| Canal | Costo | Riesgo de ban | Tiempo de setup | Audio | Recomendado |
|---|---|---|---|---|---|
| **Telegram** | Gratis | 0% | 2 min | ✅ | ⭐ Empezar aquí |
| **WhatsApp Baileys** | ~$2/mes | Medio | 15 min | ✅ | Para uso casual |
| **WhatsApp Business API** | ~$5-20/mes | 0% | 1-2 hrs | ✅ | Para uso profesional |

**Recomendación:** Empieza con Telegram. Es gratis, sin riesgo, y se configura en minutos.

Guías detalladas:
- [Telegram Setup](docs/TELEGRAM_SETUP.md)
- [WhatsApp Baileys Setup](docs/WHATSAPP_BAILEYS_SETUP.md)
- [WhatsApp Business API Setup](docs/WHATSAPP_BUSINESS_SETUP.md)
- [Guía paso a paso completa](docs/PASO_A_PASO.md)

---

## Comandos

El asistente entiende **lenguaje natural**, pero también reconoce comandos directos:

### Información y Estado

| Comando | Descripción |
|---------|-------------|
| `!status` | Estado del sistema, uptime, uso de memoria |
| `!yo` | Tu perfil: preferencias aprendidas, estadísticas |
| `!help` | Lista de todos los comandos disponibles |

### Memoria y Conocimiento

| Comando | Descripción |
|---------|-------------|
| `!memoria` | Ver memorias almacenadas (últimas 10) |
| `!memoria buscar <texto>` | Buscar en memorias |
| `!recuerda <texto>` | Guardar algo en memoria permanente |
| `!olvida <id>` | Eliminar una memoria específica |
| `recuerda que [dato]` | Guardar con lenguaje natural |
| `qué sabes sobre [tema]` | Consultar la memoria |

### Tareas y Recordatorios

| Comando | Descripción |
|---------|-------------|
| `!tareas` | Ver tareas pendientes |
| `!tarea nueva <descripción>` | Crear nueva tarea |
| `!tarea hecha <id>` | Marcar tarea como completada |
| `!tarea eliminar <id>` | Eliminar una tarea |
| `recuérdame [algo] a las [hora]` | Recordatorio con lenguaje natural |
| `recuérdame [algo] cada [frecuencia]` | Recordatorio recurrente |

### Búsqueda Web

| Comando | Descripción |
|---------|-------------|
| `!busca <query>` | Buscar en la web |
| `!resumen <url>` | Resumir contenido de una URL |
| `busca [tema]` | Búsqueda con lenguaje natural |
| `aprende sobre [tema]` | Búsqueda profunda con múltiples fuentes |

### Terminal y Proyectos

| Comando | Descripción |
|---------|-------------|
| `!cmd <comando>` | Ejecutar comando en sandbox seguro |
| `!script <nombre>` | Ejecutar script predefinido |
| `ejecuta: [comando]` | Ejecutar con lenguaje natural |
| `trabaja en [proyecto]` | Activar Claude Code en un proyecto |
| `claude: [instrucción]` | Instrucción directa a Claude Code |
| `estado del sistema` | Uso de CPU, RAM, disco |

### Audio

| Comando | Descripción |
|---------|-------------|
| *(enviar nota de voz)* | Transcripción automática con faster-whisper |
| `!voz <texto>` | Generar audio con TTS local |
| `responde con voz` | El asistente responde con audio |

### Archivos y Configuración

| Comando | Descripción |
|---------|-------------|
| `lee el archivo [ruta]` | Muestra contenido de un archivo |
| `crea archivo [ruta]` | Crea un archivo nuevo |
| *(enviar documento)* | El asistente lo procesa automáticamente |
| `!config` | Ver configuración actual |
| `!config <clave> <valor>` | Cambiar configuración |
| `!skills` | Ver skills disponibles |

---

## Arquitectura

```
  Tú (Telegram / WhatsApp)
         │
         ▼
┌─────────────────────┐
│   Canal              │  Telegram Bot / WhatsApp Baileys / Business API
│   (channels/)        │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│   SecurityGuardian   │  Auth por Chat ID · Rate limiting · Validación
│   (security.py)      │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│   Gateway            │  Orquestador central · Pipeline de mensajes
│   (gateway.py)       │
└───┬────────┬────────┘
    │        │
    ▼        ▼
┌────────┐ ┌──────────────┐
│ Memory │ │ Claude Code   │  Cerebro (usa tu suscripción, NO API key)
│ Engine │ │ Bridge        │
└────────┘ └──────┬───────┘
                  │
           ┌──────┴──────┐
           │   Skills     │  Terminal · Archivos · Web · Audio · Custom
           │   Registry   │
           └─────────────┘
```

El asistente usa tu **suscripción de Claude** a través del CLI, no una API key. No pagas por tokens extra — usas lo que ya tienes incluido en tu plan Pro o Max.

---

## Seguridad — 7 Capas

La seguridad no es un feature opcional — es la base del diseño:

| Capa | Mecanismo | Descripción |
|------|-----------|-------------|
| **1** | Autenticación por Chat ID | Solo el `AUTHORIZED_CHAT_ID` configurado puede interactuar. Cualquier otro usuario es rechazado silenciosamente. |
| **2** | PIN de seguridad | Operaciones sensibles (borrar datos, acceder a archivos del sistema) requieren un PIN configurable. |
| **3** | Sandbox con bubblewrap | Los comandos se ejecutan dentro de un contenedor ligero (`bwrap`) con acceso limitado al filesystem. En Windows, se usa subprocess con timeout (bubblewrap no disponible). |
| **4** | Validación de rutas | Toda ruta se valida para prevenir path traversal. Directorios sensibles (`.ssh`, `.gnupg`, `/etc/shadow`) están bloqueados. |
| **5** | Rate limiting | Máximo configurable de mensajes por minuto para prevenir abuso o flood accidental. |
| **6** | Escaneo de output | Antes de enviar cualquier respuesta, se escanea para detectar secretos filtrados (tokens, passwords, claves privadas). |
| **7** | Cifrado de BD | Toda la memoria persistente usa SQLCipher (AES-256) con clave generada automáticamente. |

---

## Variables de Entorno

| Variable | Requerida | Default | Descripción |
|----------|-----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | Sí | — | Token del bot de @BotFather |
| `AUTHORIZED_CHAT_ID` | Sí | — | Tu Chat ID de Telegram |
| `SECURITY_PIN` | No | *(vacío)* | PIN para operaciones sensibles |
| `CLAUDE_CLI_PATH` | No | `claude` | Ruta al ejecutable de Claude CLI |
| `PROJECTS_BASE_DIR` | No | `/home` | Directorio base de proyectos |
| `MAX_MESSAGES_PER_MINUTE` | No | `20` | Límite de mensajes por minuto |
| `REQUIRE_APPROVAL` | No | `true` | Aprobación para acciones destructivas |
| `TIMEZONE` | No | `America/New_York` | Zona horaria |
| `DB_ENCRYPTION_KEY` | No | *(vacío)* | Clave SQLCipher (generada por install.sh) |
| `WHISPER_MODEL` | No | `medium` | Modelo de Whisper: tiny, base, small, medium, large-v3 |
| `TTS_ENGINE` | No | `auto` | Motor TTS: auto / chatterbox / espeak |
| `LOG_LEVEL` | No | `INFO` | Nivel de logging |

---

## Ejecución

### Linux / macOS

```bash
source .venv/bin/activate
python -m src.main
```

### Windows

```powershell
.venv\Scripts\activate
python -m src.main
```

### Producción (Linux — systemd)

```bash
sudo systemctl start ai-assistant
sudo systemctl enable ai-assistant

# Ver logs en tiempo real
journalctl -u ai-assistant -f
```

### Verificar que funciona

1. Arranca el asistente con `python -m src.main`
2. Abre Telegram y busca tu bot
3. Envía "hola"
4. El bot responde con el flujo de onboarding

---

## Documentación

| Documento | Descripción |
|-----------|-------------|
| [Guía Paso a Paso](docs/PASO_A_PASO.md) | Tutorial completo desde cero |
| [Telegram Setup](docs/TELEGRAM_SETUP.md) | Configurar canal de Telegram |
| [WhatsApp Baileys](docs/WHATSAPP_BAILEYS_SETUP.md) | Configurar WhatsApp con Baileys |
| [WhatsApp Business](docs/WHATSAPP_BUSINESS_SETUP.md) | Configurar WhatsApp Business API |

---

## Solución de Problemas

| Problema | Solución |
|----------|----------|
| `TELEGRAM_BOT_TOKEN not set` | Verifica tu archivo `.env` |
| Bot no responde | Verifica el token con @BotFather, reinicia el asistente |
| `Unauthorized` al enviar mensaje | Tu Chat ID no coincide con `AUTHORIZED_CHAT_ID` |
| Error de audio/whisper | Verifica que ffmpeg está instalado: `ffmpeg -version` |
| `claude: command not found` | Instala Claude CLI: `npm install -g @anthropic-ai/claude-code` |
| Memoria/BD corrupta | Verifica `DB_ENCRYPTION_KEY` en `.env` — no la cambies después de crearla |
| Comando rechazado por sandbox | Verifica que bubblewrap está instalado: `which bwrap` |
| Error en Windows: `pyautogui` no instalado | Ejecuta: `pip install pyautogui pyperclip pyttsx3` |
| Error en Windows: `ffmpeg` no encontrado | Ejecuta: `winget install ffmpeg` |

---

## Estructura del Proyecto

```
personal-ai-assistant/
├── src/
│   ├── main.py                  # Entry point, Settings, signal handling
│   ├── core/
│   │   ├── gateway.py           # Orquestador central
│   │   ├── security.py          # SecurityGuardian
│   │   ├── claude_bridge.py     # Wrapper del CLI de Claude
│   │   └── executor.py          # Ejecución sandboxed
│   ├── memory/                  # Motor de memoria persistente
│   ├── learning/                # Búsqueda web y base de conocimiento
│   ├── audio/                   # STT (whisper) y TTS (chatterbox/espeak)
│   ├── channels/                # Telegram, WhatsApp Baileys, Business API
│   ├── skills/                  # Sistema de skills extensible
│   ├── onboarding/              # Flujo de primer uso
│   └── utils/                   # Cifrado, formateo, logging, platform detection
├── data/                        # BD SQLite cifrada
├── logs/                        # app.log, security.log, audit.log
├── skills/                      # Skills creados por el usuario
├── models/                      # Modelos de Whisper
├── docs/                        # Documentación detallada
├── systemd/                     # Servicio systemd (Linux)
├── install.sh                   # Instalador interactivo (Linux/macOS)
├── install.ps1                  # Instalador PowerShell (Windows)
├── pyproject.toml               # Configuración del proyecto
└── .env.example                 # Template de variables de entorno
```

---

<a name="english"></a>

## English

### What is this?

A **private, self-hosted AI assistant** that communicates with you through Telegram or WhatsApp. Built on top of Claude Code CLI, it uses your existing Claude subscription (Pro or Max) — no API keys, no extra token costs.

### Key Features

- **Permanent encrypted memory** — remembers everything you tell it, stored locally with SQLCipher (AES-256)
- **Voice support** — send and receive voice notes with local speech recognition (faster-whisper) and TTS
- **Terminal access** — execute commands in a sandboxed environment (bubblewrap)
- **Web search** — searches DuckDuckGo, summarizes and stores knowledge automatically
- **Scheduled tasks** — set reminders and recurring tasks that execute automatically
- **7 layers of security** — authentication, PIN, sandbox, path validation, rate limiting, output scanning, encryption
- **Multi-channel** — Telegram (free), WhatsApp Baileys, WhatsApp Business API
- **Autonomous** — if it doesn't have a tool, it creates one. If it doesn't know something, it searches for it.
- **Cross-platform** — runs on Windows 10+, Linux (Ubuntu 22.04+), and macOS

### Quick Start

```bash
git clone https://github.com/xplus-finance/ASSISTANT_AI.git
cd ASSISTANT_AI

# Linux/macOS
bash install.sh

# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File install.ps1
```

Requires Windows 10+, Linux (Ubuntu 22.04+), or macOS, Python 3.12+, and Claude Code CLI with a Pro or Max subscription.

---

## Contribuir

1. Fork del repositorio
2. Crea una rama: `git checkout -b mi-feature`
3. Haz tus cambios siguiendo el estilo del proyecto
4. Ejecuta tests: `pytest tests/`
5. Ejecuta linter: `ruff check src/`
6. Crea un Pull Request

### Estilo de código

- Python 3.12+ con type hints (`str | None`, `list[str]`)
- `from __future__ import annotations` en cada módulo
- `structlog` para logging (nunca `print()`)
- Queries SQL siempre parametrizadas (nunca f-strings)
- Async donde sea posible; `asyncio.to_thread()` para llamadas bloqueantes

---

## Licencia

MIT — ver [LICENSE](LICENSE).

---

<div align="center">

**Hecho con determinación.**

[Reportar Bug](https://github.com/xplus-finance/ASSISTANT_AI/issues) · [Solicitar Feature](https://github.com/xplus-finance/ASSISTANT_AI/issues)

</div>
