# Configuracion de Telegram

Telegram es el canal recomendado. Gratis, sin riesgo de ban, listo en minutos. Funciona en Windows, Linux y macOS.

> Si usaste el instalador interactivo (`install.sh` / `install.ps1`), Telegram ya quedo configurado. Esta guia es para configuracion manual o referencia.

---

## Paso 1: Crear el bot con BotFather

1. Abrir Telegram y buscar **@BotFather** (marca de verificacion azul)
2. Enviar `/newbot`
3. BotFather pide un **nombre** para el bot (nombre visible, puede tener espacios):
   - Ejemplo: `Mi Asistente IA`
4. Pide un **username** unico (debe terminar en `bot` o `_bot`, sin espacios):
   - Ejemplo: `mi_asistente_ia_bot`
5. BotFather responde con el **token**:
   ```
   Use this token to access the HTTP API:
   7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
6. Copiar el token completo (incluyendo los numeros antes de `:`)

### Configuraciones opcionales

Enviar a @BotFather:

| Comando | Funcion |
|---------|---------|
| `/setdescription` | Descripcion visible para otros usuarios |
| `/setabouttext` | Texto "Acerca de" (ej: "Bot privado. No acepta usuarios externos.") |
| `/setuserpic` | Foto de perfil |
| `/setcommands` | Menu de comandos (ver abajo) |

Menu de comandos sugerido:
```
status - Estado del sistema
yo - Mi perfil
memoria - Ver memorias
tareas - Ver tareas pendientes
help - Lista de comandos
```

---

## Paso 2: Obtener tu Chat ID

El Chat ID identifica tu cuenta. Solo tu Chat ID tendra acceso al bot.

### Opcion A: @userinfobot

1. Buscar **@userinfobot** en Telegram
2. Enviar cualquier mensaje
3. Responde con tu Chat ID:
   ```
   Id: 123456789
   ```

### Opcion B: @RawDataBot

1. Buscar **@RawDataBot**
2. Enviar cualquier mensaje
3. En la respuesta JSON, buscar `"id"` dentro de `"from"`

### Opcion C: API directa

1. Enviar un mensaje a tu bot
2. Abrir en navegador (reemplazar `TU_TOKEN`):
   ```
   https://api.telegram.org/botTU_TOKEN/getUpdates
   ```
3. Buscar `"chat": {"id": 123456789}`

---

## Paso 3: Configurar .env

```bash
# Linux / macOS
nano .env

# Windows
notepad .env
```

```
TELEGRAM_BOT_TOKEN=7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AUTHORIZED_CHAT_ID=123456789
```

- Token **sin comillas**
- Chat ID es un **numero entero**
- No compartir estos valores
- `.env` ya esta en `.gitignore`
- En Linux/macOS, el instalador establece permisos 600 automaticamente

---

## Paso 4: Arrancar el asistente

### Linux / macOS

```bash
cd /ruta/al/ASSISTANT_AI
source .venv/bin/activate
python -m src.main
```

### Windows

Doble clic en `start.bat`, o:

```powershell
.venv\Scripts\python.exe -m src.main
```

### Con systemd (Linux)

```bash
sudo systemctl start ai-assistant
journalctl -u ai-assistant -f
```

### Con launchd (macOS)

```bash
launchctl load ~/Library/LaunchAgents/com.assistant.ai.plist
```

Salida esperada:
```
[INFO] main.settings_loaded  log_level=INFO timezone=America/New_York
[INFO] telegram.bot_started  username=mi_asistente_ia_bot
```

---

## Paso 5: Enviar el primer mensaje

1. Abrir Telegram
2. Buscar el bot por username (ej: `@mi_asistente_ia_bot`)
3. Pulsar **"Iniciar"** o enviar `/start`
4. Enviar **"hola"**
5. El bot inicia el flujo de onboarding

---

## Solucion de problemas

### El bot no responde

1. Verificar que el asistente esta corriendo (revisar terminal)
2. Verificar token: abrir `https://api.telegram.org/botTU_TOKEN/getMe` en navegador
3. Verificar que hablas al bot correcto (username exacto)
4. Revisar logs:
   - Linux/macOS: `tail -20 logs/app.log`
   - Windows: abrir `logs\app.log`

### "Unauthorized" o ignora mensajes

Chat ID no coincide con `AUTHORIZED_CHAT_ID`:

```bash
grep AUTHORIZED_CHAT_ID .env
```

Verificar Chat ID real con @userinfobot. Corregir y reiniciar.

### "TELEGRAM_BOT_TOKEN not set"

1. Verificar que `.env` existe (no `.env.example`)
2. Verificar que `TELEGRAM_BOT_TOKEN=` tiene valor
3. Verificar que no hay espacios alrededor del `=`

### Respuestas lentas

- Primera respuesta tarda unos segundos mientras Claude Code inicia. Normal.
- Primera transcripcion de voz descarga el modelo Whisper si no se descargo en la instalacion.
- GPU NVIDIA con CUDA acelera transcripcion. Sin GPU funciona con CPU (mas lento).

### "Conflict: terminated by other getUpdates request"

Otra instancia del bot corriendo. Solo puede haber una:

```bash
# Linux / macOS
ps aux | grep "src.main"

# Windows
Get-Process python | Where-Object { $_.CommandLine -like "*src.main*" }
```

Con systemd: `sudo systemctl stop ai-assistant`

### Cambiar token o recrear bot

1. En @BotFather, enviar `/revoke` y seleccionar el bot
2. Actualizar token en `.env`
3. Reiniciar

---

## Funcionalidades via Telegram

- **Texto**: respuestas via Claude Code
- **Notas de voz**: transcripcion local con faster-whisper
- **Documentos**: procesamiento automatico
- **Imagenes**: analisis visual
- **Respuestas con audio**: `!voz on` o pedir "responde con voz"
- **Control de voz**: pedir tono grave/agudo, velocidad, genero
- **Skills runtime**: `!skill crear`
- **Servidores MCP**: `!mcp crear`
- **Notificaciones proactivas**: recordatorios y alertas programadas

---

## Privacidad

- Bot privado — solo tu Chat ID tiene acceso
- Mensajes cifrados en transito (Telegram TLS)
- Memoria local cifrada con SQLCipher (AES-256)
- Voz transcrita localmente (faster-whisper, nada a servicios externos)
- Respuestas via Claude Code CLI (tu suscripcion, no API key)
- Comandos en sandbox (bubblewrap en Linux, subprocess en Windows/macOS)
- Permisos de `.env`, `data/`, `logs/` endurecidos automaticamente
- Ningun dato compartido con terceros
