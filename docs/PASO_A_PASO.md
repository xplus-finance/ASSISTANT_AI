# Paso a Paso -- Poner en Marcha tu Asistente Personal IA

## Que necesitas

- Una computadora con Windows 10+, Linux (Ubuntu, Debian, Fedora, Arch) o macOS
- Python 3.12 o superior
- Una suscripcion activa de Claude Pro o Max (para Claude Code CLI)
- Una cuenta de Telegram (recomendado) o WhatsApp (ver opciones abajo)

---

## Instalacion

El proyecto incluye un instalador interactivo que configura todo automaticamente: dependencias del sistema, entorno de Python, canal de mensajeria, audio y seguridad.

### Linux / macOS

```bash
cd /ruta/al/personal-ai-assistant
bash install.sh
```

El instalador detecta tu gestor de paquetes (apt, dnf, pacman, brew) e instala las dependencias faltantes (ffmpeg, bubblewrap) de forma automatica.

### Windows

```powershell
cd C:\ruta\al\personal-ai-assistant
powershell -ExecutionPolicy Bypass -File install.ps1
```

En Windows, el instalador usa `winget` para dependencias como ffmpeg y crea un archivo `start.bat` para iniciar con doble clic.

### Que hace el instalador (10 pasos)

1. Verifica Python 3.12+, ffmpeg y bubblewrap (sandbox de seguridad)
2. Verifica que Claude Code CLI este instalado y autenticado
3. Te permite elegir canal de mensajeria: Telegram, WhatsApp Baileys, WhatsApp Business API o todos
4. Configura el canal elegido paso a paso, con validacion en vivo (verifica tokens contra la API de Telegram, envia mensaje de prueba, etc.)
5. Crea el entorno virtual de Python
6. Instala todas las dependencias
7. Configura el modelo de reconocimiento de voz (Whisper) con opcion de descarga inmediata
8. Configura zona horaria
9. Configura seguridad: PIN opcional y clave de cifrado para la base de datos
10. Crea directorios de datos y ofrece inicio automatico (systemd en Linux, Task Scheduler en Windows)

El instalador es idempotente: puedes ejecutarlo varias veces sin problema. Si ya existe un `.env`, ofrece reconfigurarlo con backup automatico.

---

## Primer arranque

### Linux / macOS

```bash
cd /ruta/al/personal-ai-assistant
source .venv/bin/activate
python -m src.main
```

### Windows

Doble clic en `start.bat` o desde PowerShell:

```powershell
.venv\Scripts\python.exe -m src.main
```

El `start.bat` en Windows hace `git pull` automatico al arrancar para mantener el codigo actualizado.

---

## Primer mensaje (onboarding)

La primera vez que hables con el bot por Telegram (o WhatsApp), se activa el asistente de configuracion inicial:

1. Te pregunta como quieres que se llame el asistente
2. Te pregunta tu nombre
3. Te pregunta tu area de trabajo o intereses
4. Te pregunta tus preferencias de comunicacion (texto/audio, formal/informal)
5. Te pregunta la zona horaria (si no la configuraste en la instalacion)
6. Opcion de configurar un PIN de seguridad

Despues del onboarding, el asistente esta listo para usar.

---

## Canales de mensajeria disponibles

### Telegram (recomendado)

La opcion mas rapida y segura. Gratis, sin riesgo de ban. Se configura en 2 minutos durante la instalacion. Guia completa: [TELEGRAM_SETUP.md](TELEGRAM_SETUP.md)

### WhatsApp con Baileys (no oficial)

Usa ingenieria inversa del protocolo de WhatsApp Web. Requiere un numero virtual desechable. Riesgo medio de ban del numero. Guia completa: [WHATSAPP_BAILEYS_SETUP.md](WHATSAPP_BAILEYS_SETUP.md)

### WhatsApp Business API (oficial)

API oficial de Meta, cero riesgo de ban. Requiere cuenta de negocio verificada y Cloudflare Tunnel. Guia completa: [WHATSAPP_BUSINESS_SETUP.md](WHATSAPP_BUSINESS_SETUP.md)

---

## Capacidades del asistente

### Comandos principales

```
INFORMACION
!status          -- estado del asistente y sus modulos
!yo              -- tu perfil como lo ve el asistente
!memoria         -- que recuerda de ti
!recuerda [algo] -- guardar algo en memoria permanente

TAREAS
!tareas          -- ver todas las tareas
!tarea nueva [X] -- crear tarea

AUDIO
!voz on          -- responder siempre con audio
!voz off         -- responder siempre con texto
!voz auto        -- el asistente decide segun el contexto

SKILLS
!skills          -- ver skills disponibles
!skill crear     -- crear una nueva skill en tiempo de ejecucion

MCP
!mcp crear       -- crear un servidor MCP, instalarlo y registrarlo automaticamente

APRENDIZAJE
!busca [tema]    -- buscar en la web y almacenar en base de conocimiento

SISTEMA
!cmd [comando]   -- ejecutar comando en terminal (con sandbox de seguridad)
!logs            -- ver ultimos comandos ejecutados
```

### Audio

- Transcripcion de voz con faster-whisper (procesamiento 100% local, nada se envia a terceros)
- Modelos disponibles: tiny (75 MB), small (500 MB), medium (1.5 GB), large-v3 (3 GB)
- Sintesis de voz (TTS) con multiples motores: chatterbox, piper, gTTS, espeak, pyttsx3 (Windows)
- Control de voz por lenguaje natural: cambiar tono (grave/agudo), velocidad y genero

### Seguridad (8 capas)

1. Autenticacion por Chat ID de Telegram o numero autorizado de WhatsApp
2. PIN de seguridad con hash bcrypt para operaciones sensibles
3. Sanitizacion de entrada (validacion de comandos contra lista negra)
4. Deteccion de inyeccion de prompts
5. Escaneo de salida (previene filtracion de datos sensibles)
6. Rate limiting (limite de mensajes por minuto)
7. Permisos de archivos endurecidos automaticamente en cada arranque (Linux/macOS)
8. Ejecucion en sandbox con bubblewrap (Linux) o subprocess con timeout (Windows/macOS)

### Auto-evolucion

- Hot-reload: el asistente detecta cambios en su propio codigo y recarga modulos en caliente
- Los modulos utilitarios y de skills se recargan sin reiniciar
- Los modulos core (gateway, bridge, seguridad) activan un reinicio completo del proceso
- Validacion de sintaxis con `ast.parse()` antes de aplicar cualquier cambio
- Backup automatico de modulos antes de reemplazarlos

### Skills en tiempo de ejecucion

Con `!skill crear`, el asistente genera nuevas habilidades usando Claude, las valida, las guarda en el directorio `skills/` y las carga sin reiniciar. Las skills personalizadas persisten entre reinicios.

### Servidores MCP

Con `!mcp crear`, el asistente puede generar servidores MCP (Model Context Protocol) completos con FastMCP, instalarlos en `mcps/` y registrarlos automaticamente en la configuracion de Claude Code.

### Control de escritorio

- Capturas de pantalla (scrot en Linux, screencapture en macOS, pyautogui en Windows)
- Gestion de ventanas (xdotool/wmctrl en Linux, osascript en macOS, pyautogui en Windows)
- Escaneo de pestanas del navegador
- Escritura en teclado

### Base de datos

- APSW (driver SQLite avanzado) con cifrado opcional via SQLCipher (AES-256)
- La clave de cifrado se genera automaticamente durante la instalacion
- Todos los datos (conversaciones, memoria, tareas) se almacenan localmente

---

## Ejecucion 24/7

### Linux (systemd)

```bash
sudo cp systemd/ai-assistant.service /etc/systemd/system/
sudo systemctl enable ai-assistant
sudo systemctl start ai-assistant

# Ver logs en vivo
journalctl -u ai-assistant -f
```

### Windows (Task Scheduler)

El instalador puede configurar una tarea programada que inicia el asistente al abrir sesion. Tambien puedes usar `start.bat` o `start_hidden.vbs` (sin ventana de consola).

### Alternativa rapida (tmux/screen)

```bash
tmux new -s asistente
source .venv/bin/activate
python -m src.main
# Ctrl+B, luego D para desconectar
# tmux attach -t asistente para reconectar
```

---

## Solucion de problemas

### "Claude Code CLI no encontrado"

```bash
# Verificar instalacion
claude --version

# Si no esta instalado
npm install -g @anthropic-ai/claude-code

# Autenticarse (abre el navegador)
claude
```

### "El bot no responde en Telegram"

1. Verifica que el token y el chat_id en `.env` son correctos
2. Verifica que el proceso esta corriendo
3. Revisa los logs: `tail -f logs/app.log`
4. Asegurate de haber enviado `/start` al bot al menos una vez

### "Error de base de datos"

```bash
# Si la DB esta corrupta, borrarla y empezar de nuevo
# (se pierde la memoria del asistente pero se regenera)
rm data/assistant.db
python -m src.main
```

### "faster-whisper da error"

```bash
source .venv/bin/activate
python -c "from faster_whisper import WhisperModel; WhisperModel('small')"
```

Si usas GPU NVIDIA con CUDA, faster-whisper la detecta y la usa automaticamente. Sin GPU funciona con CPU (mas lento pero operativo).

### "El bridge de WhatsApp no conecta"

```bash
curl http://127.0.0.1:3001/health

# Si dice "disconnected", borrar sesion y re-escanear QR
cd whatsapp-bridge
rm -rf auth_info/
npm start
```

### Permisos en Linux/macOS

El asistente endurece permisos automaticamente al arrancar:
- `data/` y `logs/`: modo 700 (solo el propietario)
- `.env`: modo 600 (solo lectura/escritura del propietario)

Si tienes problemas de permisos, ejecuta:

```bash
chmod 700 data/ logs/
chmod 600 .env
```
