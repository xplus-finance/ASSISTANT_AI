# Paso a Paso -- Poner en Marcha tu Asistente Personal

## Que necesitas

| Requisito | Detalle |
|-----------|---------|
| OS | Windows 10+, Linux (Ubuntu, Debian, Fedora, Arch) o macOS 13+ |
| Python | 3.12 o superior |
| Claude Code CLI | Suscripcion Pro o Max activa |
| Canal | Telegram (recomendado), WhatsApp Baileys o WhatsApp Business API |

---

## Instalacion

### Linux / macOS

```bash
cd /ruta/al/ASSISTANT_AI
bash install.sh
```

Detecta el gestor de paquetes (apt, dnf, pacman, brew) e instala dependencias faltantes (ffmpeg, bubblewrap) automaticamente.

### Windows

```powershell
cd C:\ruta\al\ASSISTANT_AI
powershell -ExecutionPolicy Bypass -File install.ps1
```

Usa `winget` para dependencias como ffmpeg y crea `start.bat` para iniciar con doble clic.

### Que hace el instalador (10 pasos)

1. Verifica Python 3.12+, ffmpeg y bubblewrap (sandbox de seguridad)
2. Verifica Claude Code CLI instalado y autenticado
3. Permite elegir canal: Telegram, WhatsApp Baileys, WhatsApp Business API o todos
4. Configura el canal con validacion en vivo (verifica tokens contra APIs, envia mensaje de prueba)
5. Crea entorno virtual de Python
6. Instala dependencias
7. Configura modelo de reconocimiento de voz (faster-whisper) con opcion de descarga inmediata
8. Configura zona horaria
9. Configura seguridad: PIN opcional y clave de cifrado para la base de datos
10. Crea directorios de datos y ofrece inicio automatico (systemd en Linux, launchd en macOS, Task Scheduler en Windows)

El instalador es idempotente. Si ya existe un `.env`, ofrece reconfigurarlo con backup automatico.

---

## Primer arranque

### Linux / macOS

```bash
cd /ruta/al/ASSISTANT_AI
source .venv/bin/activate
python -m src.main
```

### Windows

Doble clic en `start.bat` o desde PowerShell:

```powershell
.venv\Scripts\python.exe -m src.main
```

`start.bat` hace `git pull` automatico al arrancar.

---

## Primer mensaje (onboarding)

La primera vez que hables con el bot se activa la configuracion inicial:

1. Nombre del asistente
2. Tu nombre
3. Area de trabajo o intereses
4. Preferencias de comunicacion (texto/audio, formal/informal)
5. Zona horaria (si no se configuro en la instalacion)
6. PIN de seguridad (opcional)

Despues del onboarding, el asistente esta operativo.

---

## Canales de mensajeria

| Canal | Costo | Riesgo | Setup | Guia |
|-------|-------|--------|-------|------|
| Telegram | Gratis | Ninguno | 2 min | [TELEGRAM_SETUP.md](TELEGRAM_SETUP.md) |
| WhatsApp Baileys | ~$2/mes | Medio | 15 min | [WHATSAPP_BAILEYS_SETUP.md](WHATSAPP_BAILEYS_SETUP.md) |
| WhatsApp Business API | ~$5-20/mes | Ninguno | 1-2 hrs | [WHATSAPP_BUSINESS_SETUP.md](WHATSAPP_BUSINESS_SETUP.md) |

---

## Skills integradas (14)

| Skill | Funcion | Activacion |
|-------|---------|------------|
| terminal | Comandos del sistema en sandbox | `!cmd <comando>` |
| files | Leer, escribir, buscar archivos | `lee el archivo [ruta]` |
| memory | Memoria permanente | `!memoria`, `!recuerda [algo]` |
| tasks | Tareas y recordatorios | `!tareas`, `!tarea nueva [desc]` |
| learning | Busqueda web y base de conocimiento | `!busca [tema]`, `!aprende [url]` |
| desktop_control | Capturas de pantalla, ventanas, teclado | `!screenshot` |
| mcp_creator | Generar e instalar servidores MCP | `!mcp crear [desc]` |
| skill_creator | Crear skills en runtime | `!skill crear [desc]` |
| claude_code | Integracion con Claude Code CLI | Lenguaje natural sobre codigo |
| system_monitor | Estado del sistema (CPU, RAM, disco) | `!status` |
| file_search | Busqueda avanzada de archivos | `busca archivos [patron]` |
| git | Operaciones git completas | `git status`, lenguaje natural |
| network | Diagnostico de red | `haz ping a [host]` |
| package_manager | Gestionar paquetes del sistema | `instala [paquete]` |

---

## Comandos

```
INFORMACION
  !status          -- estado del asistente y recursos del sistema
  !yo              -- tu perfil como lo ve el asistente
  !help            -- lista de comandos
  !memoria         -- que recuerda de ti
  !recuerda [algo] -- guardar en memoria permanente

TAREAS
  !tareas          -- ver todas las tareas
  !tarea nueva [X] -- crear tarea
  recuerdame [algo] a las [hora] -- recordatorio en lenguaje natural

AUDIO
  !voz on          -- responder siempre con audio
  !voz off         -- responder siempre con texto
  !voz auto        -- el asistente decide segun contexto

SKILLS
  !skills          -- ver skills disponibles
  !skill crear     -- crear nueva skill en runtime

MCP
  !mcp crear       -- crear servidor MCP, instalarlo y registrarlo
  !mcp list        -- listar servidores MCP instalados

APRENDIZAJE
  !busca [tema]    -- buscar en la web
  !aprende [url]   -- obtener y almacenar contenido de URL

SISTEMA
  !cmd [comando]   -- ejecutar en terminal (sandbox)
  !screenshot      -- captura de pantalla
  !logs            -- ultimos comandos ejecutados
```

---

## Audio

- Transcripcion con faster-whisper (100% local, nada se envia a terceros)
- Modelos: tiny (75 MB), small (500 MB), medium (1.5 GB), large-v3 (3 GB)
- TTS con multiples motores: chatterbox, espeak, gTTS, pyttsx3 (Windows)
- Control por lenguaje natural: tono (grave/agudo), velocidad, genero
- GPU NVIDIA con CUDA acelera la transcripcion. Sin GPU funciona con CPU.

---

## Seguridad (8 capas)

| Capa | Mecanismo |
|------|-----------|
| Autenticacion | Chat ID de Telegram o numero autorizado de WhatsApp |
| PIN | Hash bcrypt para operaciones sensibles |
| Sanitizacion | Validacion de comandos, path traversal prevention, FTS5 sanitization |
| Prompt injection | 28 patrones regex, registro en audit log |
| Escaneo de salida | Deteccion de tokens, keys y passwords antes de enviar |
| Rate limiting | Limite configurable de mensajes por minuto |
| Permisos | `.env` (600), `data/` (700), `logs/` (700) — automatico al arrancar (Linux/macOS) |
| Sandbox | bubblewrap (Linux), subprocess con timeout (Windows/macOS) |

---

## Auto-evolucion

- Hot-reload: detecta cambios en su propio codigo y recarga modulos en caliente
- Modulos utilitarios y skills: recarga sin reiniciar
- Modulos core (gateway, bridge, seguridad): reinicio completo del proceso
- Validacion con `ast.parse()` antes de aplicar cambios
- Backup automatico en `.backups/` antes de reemplazar
- Skills runtime: `!skill crear` genera, valida, guarda y carga sin reiniciar
- MCP servers: `!mcp crear` genera con FastMCP, instala venv + deps, registra en Claude Code

---

## Memoria

| Tipo | Persistencia | Descripcion |
|------|-------------|-------------|
| Hechos permanentes | Indefinida | Guardados con `!recuerda` |
| Procedimientos | Indefinida | Lecciones de errores, no se repiten |
| Resumenes de sesion | Indefinida | Resumen automatico al cerrar sesion |
| Historial cruzado | 7 dias | Contexto de sesiones anteriores |
| Base de conocimiento | Indefinida | De busquedas web y URLs |

SQLite local con cifrado AES-256 opcional (SQLCipher via APSW). Indices FTS5.

---

## Ejecucion 24/7

### Linux (systemd)

```bash
sudo cp systemd/ai-assistant.service /etc/systemd/system/
sudo systemctl enable ai-assistant
sudo systemctl start ai-assistant
journalctl -u ai-assistant -f
```

### macOS (launchd)

```bash
cp launchd/com.assistant.ai.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.assistant.ai.plist
```

### Windows (Task Scheduler)

El instalador configura una tarea programada al iniciar sesion. Alternativas: `start.bat` o `start_hidden.vbs` (sin ventana de consola).

### Alternativa rapida (tmux/screen)

```bash
tmux new -s asistente
source .venv/bin/activate
python -m src.main
# Ctrl+B, D para desconectar
# tmux attach -t asistente para reconectar
```

---

## Solucion de problemas

### "Claude Code CLI no encontrado"

```bash
claude --version
# Si no esta:
npm install -g @anthropic-ai/claude-code
# Autenticarse:
claude
```

### "El bot no responde en Telegram"

1. Verificar que el proceso esta corriendo
2. Verificar token y chat_id en `.env`
3. Revisar logs: `tail -f logs/app.log`
4. Confirmar que enviaste `/start` al bot

### "Error de base de datos"

```bash
# Borrar DB corrupta (se pierde memoria, se regenera estructura)
rm data/assistant.db
python -m src.main
```

### "faster-whisper da error"

```bash
source .venv/bin/activate
python -c "from faster_whisper import WhisperModel; WhisperModel('small')"
```

### "El bridge de WhatsApp no conecta"

```bash
curl http://127.0.0.1:3001/health
# Si dice "disconnected":
cd whatsapp-bridge
rm -rf auth_info/
npm start
```

### Permisos en Linux/macOS

El asistente endurece permisos al arrancar. Si hay problemas:

```bash
chmod 700 data/ logs/
chmod 600 .env
```
