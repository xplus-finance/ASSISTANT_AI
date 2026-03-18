# Configuracion de Telegram

Telegram es el canal recomendado para empezar. Es gratis, sin riesgo de ban, y se configura en minutos.

---

## Requisitos previos

- Una cuenta de Telegram (la app instalada en tu telefono o escritorio)
- El asistente instalado (haber ejecutado `install.sh` en Linux/macOS o `install.ps1` en Windows)

Si aun no instalaste el asistente, el propio instalador te guia paso a paso por la configuracion de Telegram. No necesitas seguir esta guia por separado si usas el instalador interactivo.

---

## Paso 1: Crear el bot con BotFather

1. Abre Telegram y busca **@BotFather** (tiene una marca de verificacion azul)
2. Envia el comando `/newbot`
3. BotFather te pide un **nombre** para el bot:
   - Este es el nombre visible. Puede tener espacios.
   - Ejemplo: `Mi Asistente IA`
4. Luego te pide un **username** unico para el bot:
   - Debe terminar en `bot` o `_bot`
   - No puede tener espacios ni caracteres especiales
   - Ejemplo: `mi_asistente_ia_bot`
5. BotFather te responde con un mensaje que incluye el **token**:
   ```
   Use this token to access the HTTP API:
   7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
6. **Copia el token completo** (incluyendo los numeros antes de los dos puntos)

### Configuraciones opcionales del bot

Envia estos comandos a @BotFather para personalizar tu bot:

- `/setdescription` -- Descripcion que ven otros usuarios
- `/setabouttext` -- Texto "Acerca de" del bot (ej: "Bot privado. No acepta usuarios externos.")
- `/setuserpic` -- Foto de perfil del bot
- `/setcommands` -- Menu de comandos:
  ```
  status - Estado del sistema
  yo - Mi perfil
  memoria - Ver memorias
  tareas - Ver tareas pendientes
  help - Lista de comandos
  ```

---

## Paso 2: Obtener tu Chat ID

El Chat ID es un numero unico que identifica tu cuenta de Telegram. Se usa para que **solo tu** puedas usar el bot.

### Opcion A: Usar @userinfobot (mas facil)

1. Busca **@userinfobot** en Telegram
2. Envia cualquier mensaje (por ejemplo "hola")
3. Te responde con tu informacion, incluyendo:
   ```
   Id: 123456789
   ```
4. Ese numero es tu Chat ID

### Opcion B: Usar @RawDataBot

1. Busca **@RawDataBot** en Telegram
2. Envia cualquier mensaje
3. En la respuesta JSON, busca `"id"` dentro de `"from"`
4. Ese es tu Chat ID

### Opcion C: Usar la API directamente

Si ya tienes el token del bot:

1. Envia un mensaje a tu bot en Telegram (cualquier cosa)
2. Abre esta URL en tu navegador (reemplazando `TU_TOKEN`):
   ```
   https://api.telegram.org/botTU_TOKEN/getUpdates
   ```
3. En la respuesta JSON, busca `"chat": {"id": 123456789}`
4. Ese es tu Chat ID

---

## Paso 3: Configurar .env

Abre el archivo `.env` en el directorio del proyecto:

```bash
# Linux / macOS
nano .env

# Windows (PowerShell)
notepad .env
```

Busca y rellena estas lineas:

```
TELEGRAM_BOT_TOKEN=7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AUTHORIZED_CHAT_ID=123456789
```

**Importante:**
- El token va **sin comillas**
- El Chat ID es un **numero entero** (sin comillas, sin espacios)
- No compartas estos valores con nadie
- No subas el archivo `.env` a git (ya esta en `.gitignore`)
- En Linux/macOS, el instalador establece permisos 600 en `.env` automaticamente

---

## Paso 4: Arrancar el asistente

### Linux / macOS

```bash
cd /ruta/al/personal-ai-assistant
source .venv/bin/activate
python -m src.main
```

### Windows

Doble clic en `start.bat`, o desde PowerShell:

```powershell
.venv\Scripts\python.exe -m src.main
```

Deberias ver algo como:

```
[INFO] main.settings_loaded  log_level=INFO timezone=America/New_York
[INFO] telegram.bot_started  username=mi_asistente_ia_bot
```

Si usas systemd (Linux):

```bash
sudo systemctl start ai-assistant
journalctl -u ai-assistant -f   # Ver logs en vivo
```

---

## Paso 5: Enviar el primer mensaje

1. Abre Telegram
2. Busca tu bot por su username (ej: `@mi_asistente_ia_bot`)
3. Pulsa **"Iniciar"** o envia `/start`
4. Envia **"hola"**
5. El bot responde con el flujo de onboarding (te pregunta tu nombre, preferencias, etc.)

Si todo funciona, el bot esta listo para usar.

---

## Solucion de problemas

### El bot no responde

1. **Verifica que el asistente esta corriendo** -- revisa la terminal donde lo arrancaste
2. **Verifica el token** -- abre `https://api.telegram.org/botTU_TOKEN/getMe` en el navegador. Si el token es valido, veras info del bot en JSON
3. **Verifica que hablaste al bot correcto** -- busca el username exacto
4. **Revisa los logs** -- `tail -20 logs/app.log` (Linux/macOS) o abre `logs\app.log` con un editor (Windows)

### "Unauthorized" o el bot ignora tus mensajes

Tu Chat ID no coincide con el configurado en `.env`:

1. Verifica tu Chat ID real (usa @userinfobot)
2. Compara con el valor en `.env`:
   ```bash
   grep AUTHORIZED_CHAT_ID .env
   ```
3. Corrige si es diferente y reinicia el asistente

### "TELEGRAM_BOT_TOKEN not set" al arrancar

El archivo `.env` no tiene el token configurado o no se esta leyendo:

1. Verifica que el archivo `.env` existe en el directorio raiz del proyecto (no `.env.example`)
2. Verifica que la linea `TELEGRAM_BOT_TOKEN=...` tiene un valor
3. Verifica que no hay espacios alrededor del `=`

### El bot responde muy lento

1. **Claude CLI** -- la primera respuesta puede tardar unos segundos mientras se inicia. Es normal.
2. **Audio** -- la primera transcripcion descarga el modelo de Whisper si no lo descargaste durante la instalacion. Las siguientes son rapidas.
3. **GPU** -- si tienes GPU NVIDIA con CUDA, faster-whisper la usara automaticamente. Sin GPU, la transcripcion es mas lenta (pero funciona).

### Error "Conflict: terminated by other getUpdates request"

Hay otra instancia del bot corriendo. Solo puede haber una:

1. Busca y mata otros procesos:
   ```bash
   # Linux / macOS
   ps aux | grep "src.main"

   # Windows (PowerShell)
   Get-Process python | Where-Object { $_.CommandLine -like "*src.main*" }
   ```
2. Si usas systemd:
   ```bash
   sudo systemctl stop ai-assistant
   ```
3. Reinicia

### Quiero cambiar el token o recrear el bot

1. Si necesitas un token nuevo: ve a @BotFather, envia `/revoke` y selecciona tu bot
2. Actualiza el token en `.env`
3. Reinicia el asistente

---

## Funcionalidades en Telegram

Una vez configurado, puedes:

- **Enviar mensajes de texto** -- el bot responde usando Claude
- **Enviar notas de voz** -- se transcriben localmente con faster-whisper y el bot responde al contenido
- **Enviar documentos** -- el bot los procesa
- **Enviar imagenes** -- el bot puede analizarlas
- **Recibir respuestas con audio** -- pidele "responde con voz" o usa `!voz on`
- **Controlar la voz** -- pidele que hable mas grave, mas rapido o mas agudo con lenguaje natural
- **Crear skills** -- `!skill crear` genera habilidades nuevas en tiempo de ejecucion
- **Crear servidores MCP** -- `!mcp crear` genera e instala servidores MCP automaticamente

El bot tambien puede enviarte **notificaciones proactivas** (recordatorios, alertas de tareas programadas).

---

## Privacidad y seguridad

- Tu bot de Telegram es **privado** -- solo tu puedes hablar con el (gracias al filtro por `AUTHORIZED_CHAT_ID`)
- Los mensajes viajan cifrados entre Telegram y tu servidor
- La memoria del bot se almacena **localmente** en tu maquina, cifrada con SQLCipher (AES-256) via APSW
- Las notas de voz se transcriben **localmente** con faster-whisper (nada se envia a servicios de transcripcion externos)
- Las respuestas se generan via Claude Code CLI usando tu suscripcion (no API key)
- Los comandos del sistema se ejecutan en sandbox (bubblewrap en Linux, subprocess con timeout en Windows/macOS)
- Los permisos de archivos sensibles (.env, data/, logs/) se endurecen automaticamente al arrancar
- Ningun dato se comparte con terceros
