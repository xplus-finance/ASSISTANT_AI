# Personal AI Assistant

> Your own personal AI assistant. Accessible from Telegram and WhatsApp,
> 24/7, from anywhere in the world. Secure. Private. Yours.
>
> Built on [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI
> with persistent memory, voice support, web search, and 7 layers of security.

---

## Que es?

Tu propio asistente de IA personal que:

- **Responde por texto y audio** -- transcribe tus notas de voz y puede responderte con voz
- **Ejecuta comandos en tu terminal** -- dentro de un sandbox seguro (bubblewrap)
- **Trabaja en tus proyectos** -- integrado con Claude Code para escribir, refactorizar y depurar codigo
- **Busca informacion en la web** -- DuckDuckGo sin API key, resume y guarda lo que aprende
- **Recuerda TODO** -- memoria persistente cifrada (SQLCipher), nunca olvida nada
- **Automatiza tareas** -- recordatorios, tareas programadas, scripts recurrentes
- **Tiene 7 capas de seguridad** -- solo tu puedes usarlo, cada accion es validada

Disenado para uso **personal** (un solo usuario autorizado). No es un bot publico.

## Canales disponibles

| Canal | Costo | Riesgo de ban | Tiempo de setup |
|-------|-------|---------------|-----------------|
| Telegram Bot | Gratis | 0% | 5 min |
| WhatsApp (Baileys + numero virtual) | ~$2/mes | Medio (~5-15%) | 15 min |
| WhatsApp Business API | ~$5-20/mes | 0% | 1-2 horas |

**Recomendacion:** empieza con Telegram. Es gratis, sin riesgo, y se configura en 5 minutos.

## Instalacion rapida

```bash
git clone https://github.com/tu-usuario/personal-ai-assistant
cd personal-ai-assistant
chmod +x install.sh
bash install.sh
```

El instalador interactivo te guia paso a paso. Es idempotente (puedes ejecutarlo varias veces sin problema).

## Requisitos

| Requisito | Version | Notas |
|-----------|---------|-------|
| Linux | Ubuntu 22.04+ recomendado | macOS tambien soportado |
| Python | 3.12+ | Con venv y pip |
| Claude Code CLI | Ultima version | `npm install -g @anthropic-ai/claude-code` |
| ffmpeg | Cualquiera | Para procesamiento de audio |
| bubblewrap | Cualquiera | Sandbox para comandos (recomendado) |
| Node.js | 18+ | Solo si usas WhatsApp Baileys |
| GPU con CUDA | Opcional | Para transcripcion rapida con Whisper |

## Estructura del proyecto

```
personal-ai-assistant/
├── src/
│   ├── main.py              # Entry point, Settings, signal handling
│   ├── core/
│   │   ├── gateway.py        # Orquestador central, pipeline de mensajes
│   │   ├── security.py       # SecurityGuardian (auth, validacion, escaneo)
│   │   ├── claude_bridge.py  # Wrapper del CLI de Claude
│   │   └── executor.py       # Ejecucion sandboxed de comandos
│   ├── memory/
│   │   ├── engine.py         # MemoryEngine (APSW/SQLCipher)
│   │   ├── conversation.py   # ConversationStore
│   │   ├── relationships.py  # RelationshipTracker
│   │   ├── tasks.py          # TaskManager
│   │   ├── context.py        # ContextBuilder
│   │   └── learning.py       # LearningMemory
│   ├── learning/
│   │   ├── web_search.py     # Busqueda en DuckDuckGo (sin API key)
│   │   ├── knowledge_base.py # Persistencia de conocimiento
│   │   └── learner.py        # Orquesta buscar -> resumir -> guardar
│   ├── audio/
│   │   ├── transcriber.py    # faster-whisper STT
│   │   ├── processor.py      # Conversion OGG/WAV
│   │   └── synthesizer.py    # TTS (chatterbox/espeak)
│   ├── channels/
│   │   ├── base.py           # Clase base para canales
│   │   ├── telegram.py       # Canal de Telegram
│   │   ├── whatsapp_baileys.py   # Canal WhatsApp via Baileys
│   │   └── whatsapp_business.py  # Canal WhatsApp Business API
│   ├── skills/
│   │   ├── registry.py       # Carga y despacho de skills
│   │   ├── base_skill.py     # Clase base para skills
│   │   └── built_in/         # Skills incluidos
│   │       ├── claude_code.py    # Integracion con Claude Code
│   │       ├── terminal.py       # Ejecucion de comandos
│   │       ├── files.py          # Gestion de archivos
│   │       ├── learn_skill.py    # Busqueda web y aprendizaje
│   │       ├── memory_skill.py   # Consulta de memoria
│   │       ├── tasks_skill.py    # Recordatorios y tareas
│   │       └── skill_creator.py  # Creacion de skills custom
│   ├── onboarding/
│   │   └── wizard.py         # Flujo de primer uso
│   └── utils/
│       ├── approval.py       # ApprovalGate para operaciones peligrosas
│       ├── crypto.py         # Helpers de cifrado
│       ├── formatter.py      # Formateo de mensajes
│       └── logger.py         # Configuracion de structlog
├── data/                     # Base de datos SQLite cifrada, archivos de conocimiento
├── logs/                     # app.log, security.log, audit.log
├── skills/                   # Skills creados por el usuario
├── models/                   # Modelos de Whisper descargados
├── systemd/                  # Archivo de servicio systemd
├── docs/                     # Documentacion detallada
├── install.sh                # Instalador interactivo
├── pyproject.toml            # Configuracion del proyecto Python
├── .env.example              # Template de variables de entorno
└── .gitignore
```

## Canales -- Guias detalladas

### Telegram (recomendado)

La opcion mas sencilla. Creas un bot con @BotFather, copias el token, y listo.

Guia completa: **[docs/TELEGRAM_SETUP.md](docs/TELEGRAM_SETUP.md)**

### WhatsApp con Baileys

Usa el protocolo no oficial de WhatsApp Web. Requiere un numero virtual dedicado (nunca uses tu numero personal). Riesgo medio de que Meta banee el numero.

Guia completa: **[docs/WHATSAPP_BAILEYS_SETUP.md](docs/WHATSAPP_BAILEYS_SETUP.md)**

### WhatsApp Business API

La opcion oficial de Meta. Sin riesgo de ban, pero requiere cuenta de Meta Business y tiene costo mensual.

Guia completa: **[docs/WHATSAPP_BUSINESS_SETUP.md](docs/WHATSAPP_BUSINESS_SETUP.md)**

## Comandos disponibles

El asistente entiende lenguaje natural, pero tambien reconoce comandos directos:

### Informacion y estado

| Comando | Descripcion |
|---------|-------------|
| `!status` | Estado del sistema, uptime, uso de memoria |
| `!yo` | Tu perfil: preferencias aprendidas, estadisticas |
| `!help` | Lista de todos los comandos disponibles |

### Memoria y conocimiento

| Comando | Descripcion |
|---------|-------------|
| `!memoria` | Ver memorias almacenadas (ultimas 10) |
| `!memoria buscar <texto>` | Buscar en memorias |
| `!recuerda <texto>` | Guardar algo en memoria permanente |
| `!olvida <id>` | Eliminar una memoria especifica |
| `recuerda que [dato]` | Guardar con lenguaje natural |
| `que sabes sobre [tema]` | Consultar la memoria |

### Tareas y recordatorios

| Comando | Descripcion |
|---------|-------------|
| `!tareas` | Ver tareas pendientes |
| `!tarea nueva <descripcion>` | Crear nueva tarea |
| `!tarea hecha <id>` | Marcar tarea como completada |
| `!tarea eliminar <id>` | Eliminar una tarea |
| `recuerdame [algo] a las [hora]` | Recordatorio con lenguaje natural |
| `recuerdame [algo] cada [frecuencia]` | Recordatorio recurrente |

### Busqueda y web

| Comando | Descripcion |
|---------|-------------|
| `!busca <query>` | Buscar en la web |
| `!resumen <url>` | Resumir contenido de una URL |
| `busca [tema]` | Busqueda con lenguaje natural |
| `aprende sobre [tema]` | Busqueda profunda con multiples fuentes |

### Terminal y proyectos

| Comando | Descripcion |
|---------|-------------|
| `!cmd <comando>` | Ejecutar comando en sandbox seguro |
| `!script <nombre>` | Ejecutar script predefinido |
| `ejecuta: [comando]` | Ejecutar con lenguaje natural |
| `trabaja en [proyecto]` | Activa Claude Code en un proyecto |
| `claude: [instruccion]` | Instruccion directa a Claude Code |
| `estado del sistema` | Muestra uso de CPU, RAM, disco |

### Archivos

| Comando | Descripcion |
|---------|-------------|
| `lee el archivo [ruta]` | Muestra contenido de un archivo |
| `crea archivo [ruta]` | Crea un archivo nuevo |
| (enviar documento) | El asistente lo procesa automaticamente |

### Audio

| Comando | Descripcion |
|---------|-------------|
| (enviar nota de voz) | Transcripcion automatica con faster-whisper |
| `!voz <texto>` | Generar audio con TTS local |
| `responde con voz` | El asistente responde con audio |

### Configuracion

| Comando | Descripcion |
|---------|-------------|
| `!config` | Ver configuracion actual |
| `!config <clave> <valor>` | Cambiar configuracion |
| `!skills` | Ver skills disponibles |

## Seguridad -- 7 capas

El asistente implementa seguridad en profundidad:

1. **Autenticacion por Chat ID** -- solo el `AUTHORIZED_CHAT_ID` configurado puede interactuar con el bot. Cualquier otro usuario es rechazado silenciosamente.

2. **PIN de seguridad** -- operaciones sensibles (borrar datos, acceder a archivos del sistema) requieren un PIN opcional configurable.

3. **Sandbox con bubblewrap** -- los comandos de terminal se ejecutan dentro de un contenedor ligero (`bwrap`) con acceso limitado al filesystem.

4. **Validacion de rutas** -- toda ruta de archivo se valida para prevenir path traversal. Directorios sensibles (`.ssh`, `.gnupg`, `/etc/shadow`) estan bloqueados.

5. **Rate limiting** -- maximo configurable de mensajes por minuto para prevenir abuso o flood accidental.

6. **Escaneo de output** -- antes de enviar cualquier respuesta, se escanea para detectar secretos filtrados (tokens, passwords, claves privadas).

7. **Cifrado de base de datos** -- toda la memoria persistente usa SQLCipher (AES-256) con clave generada automaticamente.

## Arquitectura

```
Usuario (Telegram/WhatsApp)
    |
    v
+---------------------+
|   Canal (Telegram/   |
|   WhatsApp)          |
+--------+------------+
         |
         v
+---------------------+
|   SecurityGuardian   |  <- Autenticacion, rate limit, validacion
+--------+------------+
         |
         v
+---------------------+
|   Gateway            |  <- Orquestador central
|   (pipeline)         |
+----+-------+--------+
     |       |
     v       v
+--------+ +------------+
| Memory | | Claude CLI  |  <- Cerebro (usa tu suscripcion, NO API key)
| Engine | | Bridge      |
+--------+ +------+-----+
                  |
            +-----+------+
            |   Skills    |
            | (terminal,  |
            |  archivos,  |
            |  web, etc)  |
            +------------+
```

El asistente usa tu **suscripcion de Claude** a traves del CLI, no una API key. Esto significa que no pagas por tokens extra -- usas lo que ya tienes incluido.

## Audio

### Speech-to-Text (STT)
- Motor: **faster-whisper** (CTranslate2)
- Modelo: `medium` por defecto (configurable: `tiny`, `base`, `small`, `medium`, `large-v3`)
- Idioma: Deteccion automatica
- Sin conexion a internet requerida para transcripcion

### Text-to-Speech (TTS)
- Motor: **chatterbox-tts** (local, offline) con fallback a **espeak**
- Genera archivos `.ogg` compatibles con Telegram/WhatsApp

## Variables de entorno

| Variable | Requerida | Default | Descripcion |
|----------|-----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | Si | -- | Token del bot de @BotFather |
| `AUTHORIZED_CHAT_ID` | Si | -- | Tu Chat ID de Telegram |
| `SECURITY_PIN` | No | (vacio) | PIN para operaciones sensibles |
| `CLAUDE_CLI_PATH` | No | `claude` | Ruta al ejecutable de Claude CLI |
| `PROJECTS_BASE_DIR` | No | `/home` | Directorio base de proyectos |
| `MAX_MESSAGES_PER_MINUTE` | No | `20` | Limite de mensajes por minuto |
| `REQUIRE_APPROVAL` | No | `true` | Aprobacion para acciones destructivas |
| `TIMEZONE` | No | `America/New_York` | Zona horaria |
| `DB_ENCRYPTION_KEY` | No | (vacio) | Clave SQLCipher (generada por install.sh) |
| `WHISPER_MODEL` | No | `medium` | Modelo de Whisper |
| `TTS_ENGINE` | No | `auto` | Motor TTS: auto/chatterbox/espeak |
| `LOG_LEVEL` | No | `INFO` | Nivel de logging |

## Ejecucion

### Desarrollo

```bash
source .venv/bin/activate
python -m src.main
```

### Produccion (systemd)

```bash
# Instalar servicio (incluido en install.sh)
sudo systemctl start ai-assistant
sudo systemctl enable ai-assistant

# Ver logs
journalctl -u ai-assistant -f
```

### Verificar que funciona

1. Arranca el asistente con `python -m src.main`
2. Abre Telegram y busca tu bot
3. Envia "hola"
4. El bot deberia responder con el flujo de onboarding

## Solucion de problemas

| Problema | Solucion |
|----------|----------|
| `TELEGRAM_BOT_TOKEN not set` | Verifica tu archivo `.env` |
| Bot no responde | Verifica el token con @BotFather, reinicia el asistente |
| `Unauthorized` al enviar mensaje | Tu Chat ID no coincide con `AUTHORIZED_CHAT_ID` |
| Error de audio/whisper | Verifica que ffmpeg esta instalado: `ffmpeg -version` |
| `claude: command not found` | Instala Claude CLI: `npm install -g @anthropic-ai/claude-code` |
| Memoria/BD corrupta | Verifica `DB_ENCRYPTION_KEY` en `.env`, no la cambies despues de crearla |
| Comando rechazado por sandbox | Verifica que bubblewrap esta instalado: `which bwrap` |

## Licencia

MIT -- ver [LICENSE](LICENSE).

## Contribuir

1. Fork del repositorio
2. Crea una rama: `git checkout -b mi-feature`
3. Haz tus cambios siguiendo el estilo del proyecto (ver `pyproject.toml` para config de ruff)
4. Ejecuta tests: `pytest tests/`
5. Ejecuta linter: `ruff check src/`
6. Crea un Pull Request

### Estilo de codigo

- Python 3.12+ con type hints (`str | None`, `list[str]`)
- `from __future__ import annotations` en cada modulo
- `structlog` para logging (nunca `print()`)
- Queries SQL siempre parametrizadas (nunca f-strings)
- Async donde sea posible; `asyncio.to_thread()` para llamadas bloqueantes
