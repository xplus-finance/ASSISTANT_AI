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

Detecta el gestor de paquetes (apt, dnf, pacman, brew) e instala dependencias faltantes (ffmpeg, bubblewrap, libxcb-cursor0) automaticamente.

### Windows

```powershell
cd C:\ruta\al\ASSISTANT_AI
powershell -ExecutionPolicy Bypass -File install.ps1
```

Usa `winget` para dependencias como ffmpeg y crea `start.bat` para iniciar con doble clic.

### Que hace el instalador (11 pasos)

1. Verifica Python 3.12+, ffmpeg y bubblewrap (sandbox de seguridad)
2. Verifica Claude Code CLI instalado y autenticado
3. Permite elegir canal: Telegram, WhatsApp Baileys, WhatsApp Business API o todos
4. Configura el canal con validacion en vivo (verifica tokens contra APIs, envia mensaje de prueba)
5. Crea entorno virtual de Python
6. Instala dependencias
7. Configura modelo de reconocimiento de voz (faster-whisper) con opcion de descarga inmediata
8. Configura mascota de escritorio (5 opciones: perro, gato, robot, zorro, buho) — instala PyQt6 y libxcb-cursor0 automaticamente
9. Configura zona horaria
10. Configura seguridad: PIN opcional y clave de cifrado para la base de datos
11. Crea directorios de datos y ofrece inicio automatico (systemd en Linux, launchd en macOS, Task Scheduler en Windows)

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

## Mascota de escritorio

Si activaste la mascota durante la instalacion (o agregaste `PET_ENABLED=true` al `.env`), aparece automaticamente al arrancar el asistente.

### Comportamiento

| Estado del agente | Que hace la mascota |
|---|---|
| Esperando | Camina libremente por todos los monitores y workspaces |
| Procesando tu mensaje | Se sienta y teclea en un teclado, quieta |
| Ejecutando tarea compleja | Corre por todos los monitores |
| Error | Se sienta triste, no se mueve |
| 5 min sin actividad | Se duerme, no se mueve |

### Interaccion

- **Clic derecho**: menu para cambiar mascota o ver animaciones
- **Arrastrar**: moverla con clic izquierdo mantenido
- **Doble clic**: hace una animacion feliz

### Sprites personalizados

Los sprites estan en `src/pet/assets/{animal}/`. Cada archivo es un sprite sheet horizontal (N frames de 96x96 unidos lado a lado). Formatos:

- `{animacion}_side.png` — vista de perfil
- `{animacion}_front.png` — mirando al usuario
- `{animacion}_back.png` — de espaldas
- `{animacion}_front_side.png` — 3/4 vista diagonal hacia el usuario
- `{animacion}_back_side.png` — 3/4 vista diagonal alejandose
- `{animacion}.png` — fallback si no existen las vistas direccionales

Para usar sprites propios: reemplaza los PNG y reinicia el asistente. El sistema detecta automaticamente cuantos frames tiene cada sprite sheet.

### Configuracion

```env
PET_ENABLED=true    # Activar mascota
PET_TYPE=dog        # dog, cat, robot, fox, owl
PET_SIZE=96         # Tamano del sprite base en pixeles
PET_MONITOR=0       # Monitor donde aparece (0 = primario)
```

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

## Auto-aprendizaje

El asistente mejora con cada interaccion:

1. **Clasificacion de tareas**: cada mensaje se clasifica automaticamente en 7 tipos (email, desktop, code, search, file, command, general)
2. **Registro de ejecuciones**: cada interaccion se registra con tipo, duracion, metodo usado, exito/fallo
3. **Patrones de exito**: acumula los mejores metodos por tipo de tarea y los aplica automaticamente
4. **Errores memorizados**: registra errores y sus soluciones para no repetirlos
5. **Deduplicacion**: si extrae un hecho que ya existe, refuerza el existente en vez de duplicar
6. **Contexto enriquecido**: el prompt incluye automaticamente historial de ejecuciones similares, estadisticas de exito, y errores conocidos a evitar

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
| Hechos permanentes | Indefinida | Guardados automaticamente o con `!recuerda` |
| Procedimientos | Indefinida | Lecciones de errores, no se repiten |
| Ejecuciones | Indefinida | Registro completo de cada tarea ejecutada |
| Patrones de tareas | Indefinida | Mejores metodos acumulados por tipo |
| Errores y soluciones | Indefinida | Errores con su resolucion documentada |
| Resumenes de sesion | Indefinida | Resumen automatico al cerrar sesion |
| Historial cruzado | 365 dias | Contexto de sesiones anteriores |
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

### "La mascota no aparece"

1. Verificar `PET_ENABLED=true` en `.env`
2. Verificar PyQt6: `python -c "from PyQt6.QtWidgets import QApplication"`
3. Linux: instalar `libxcb-cursor0` (`sudo apt install libxcb-cursor0`)
4. Verificar logs para errores del pet: `grep pet logs/app.log`

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

### Permisos en Linux/macOS

El asistente endurece permisos al arrancar. Si hay problemas:

```bash
chmod 700 data/ logs/
chmod 600 .env
```
