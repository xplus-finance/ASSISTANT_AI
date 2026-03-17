# ============================================================================
# Personal AI Assistant — Instalador Interactivo v2.0 (Windows)
# ============================================================================
# Ejecutar: powershell -ExecutionPolicy Bypass -File install.ps1
# ============================================================================

$ErrorActionPreference = "Stop"
try { $Host.UI.RawUI.WindowTitle = "Personal AI Assistant - Instalador" } catch {}

# --- Helpers ----------------------------------------------------------------
function Write-Step($msg)  { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn($msg)  { Write-Host "  [!!] $msg" -ForegroundColor Yellow }
function Write-Err($msg)   { Write-Host "  [XX] $msg" -ForegroundColor Red }
function Write-Work($msg)  { Write-Host "  [..] $msg" -ForegroundColor Cyan }

function Write-Header($n, $t) {
    Write-Host ""
    Write-Host "  ==========================================================" -ForegroundColor Cyan
    Write-Host "  PASO $n de 10 -- $t" -ForegroundColor Cyan
    Write-Host "  ==========================================================" -ForegroundColor Cyan
    Write-Host ""
}

function Ask-Confirm($msg) {
    $resp = Read-Host "  [>>] $msg [S/n]"
    return ($resp -eq "" -or $resp -match "^[sSyY]")
}

function Ask-Input($msg, $default = "") {
    if ($default) {
        $resp = Read-Host "  [>>] $msg [$default]"
        if ([string]::IsNullOrWhiteSpace($resp)) { return $default }
        return $resp
    }
    return Read-Host "  [>>] $msg"
}

function Update-EnvVar($key, $value) {
    $content = Get-Content $EnvFile -Raw -ErrorAction SilentlyContinue
    if ($content -match "(?m)^$key=") {
        $content = $content -replace "(?m)^$key=.*", "$key=$value"
        $content | Set-Content $EnvFile -Encoding utf8 -NoNewline
    } else {
        Add-Content $EnvFile "`n$key=$value"
    }
}

$ProjectDir = $PSScriptRoot
$EnvFile    = Join-Path $ProjectDir ".env"
$VenvPath   = Join-Path $ProjectDir ".venv"
$PythonVenv = Join-Path $VenvPath "Scripts\python.exe"
$PythonwVenv= Join-Path $VenvPath "Scripts\pythonw.exe"
$PipVenv    = Join-Path $VenvPath "Scripts\pip.exe"

# ============================================================================
# PANTALLA DE BIENVENIDA
# ============================================================================
Clear-Host
Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Cyan
Write-Host "      Personal AI Assistant - Instalador v2.0 (Windows)       " -ForegroundColor Cyan
Write-Host "  ============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Tu propio asistente de IA personal, accesible desde"
Write-Host "  Telegram o WhatsApp, 24/7, desde cualquier parte."
Write-Host ""
Write-Host "  * No necesitas experiencia tecnica" -ForegroundColor DarkGray
Write-Host "  * Tiempo estimado: 5-10 minutos" -ForegroundColor DarkGray
Write-Host "  * Directorio: $ProjectDir" -ForegroundColor DarkGray
Write-Host ""
Read-Host "  Presiona Enter para comenzar"

# ============================================================================
# PASO 1/10 — Verificar sistema
# ============================================================================
Write-Header "1" "Verificando tu sistema"

# Python 3.12+
$pythonCmd = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ("$ver" -match "Python 3\.(\d+)") {
            if ([int]$Matches[1] -ge 12) {
                $pythonCmd = $cmd
                Write-Step "Python encontrado: $ver"
                break
            }
        }
    } catch {}
}

if (-not $pythonCmd) {
    Write-Err "Python 3.12+ no encontrado."
    Write-Host ""
    Write-Host "  Como instalar Python:" -ForegroundColor Yellow
    Write-Host "  1. Ve a https://www.python.org/downloads/" -ForegroundColor White
    Write-Host "  2. Descarga la ultima version 3.12+" -ForegroundColor White
    Write-Host "  3. IMPORTANTE: marca la casilla 'Add Python to PATH'" -ForegroundColor Yellow
    Write-Host "  4. Reinicia PowerShell y ejecuta este instalador de nuevo" -ForegroundColor White
    Write-Host ""
    Read-Host "  Presiona Enter para salir"
    exit 1
}

# ffmpeg
if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
    Write-Step "ffmpeg instalado (procesamiento de audio OK)"
} else {
    Write-Warn "ffmpeg no encontrado — instalando automaticamente..."
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Work "Instalando ffmpeg automaticamente con winget (puede tardar 1-2 min)..."
        winget install --id Gyan.FFmpeg -e --silent 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Step "ffmpeg instalado correctamente."
        } else {
            Write-Warn "No se pudo instalar ffmpeg. El audio de voz no funcionara."
            Write-Host "  Instala manualmente: winget install --id Gyan.FFmpeg -e" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  (winget no disponible, instala ffmpeg manualmente)" -ForegroundColor DarkGray
        Write-Host "  Descarga: https://ffmpeg.org/download.html" -ForegroundColor Yellow
    }
}

Write-Step "Verificacion del sistema completada."

# ============================================================================
# PASO 2/10 — Claude Code CLI
# ============================================================================
Write-Header "2" "Claude Code (el cerebro de tu asistente)"

Write-Host "  Claude Code es la IA que da vida al asistente." -ForegroundColor DarkGray
Write-Host "  Necesitas una suscripcion Claude Pro o Max (claude.ai/upgrade)." -ForegroundColor DarkGray
Write-Host ""

if (Get-Command claude -ErrorAction SilentlyContinue) {
    $claudeVer = & claude --version 2>&1
    Write-Step "Claude Code CLI encontrado: $claudeVer"
} else {
    Write-Err "Claude Code CLI no esta instalado."
    Write-Host ""
    Write-Host "  Como instalarlo:" -ForegroundColor Yellow
    Write-Host "  1. Instala Node.js desde https://nodejs.org/ (version 18+)" -ForegroundColor White
    Write-Host "  2. Ejecuta: npm install -g @anthropic-ai/claude-code" -ForegroundColor Cyan
    Write-Host "  3. Autenticate: claude" -ForegroundColor Cyan
    Write-Host "     (abrira tu navegador para iniciar sesion)" -ForegroundColor DarkGray
    Write-Host ""
    if (-not (Ask-Confirm "Continuar sin Claude Code? (puedes instalarlo despues)")) {
        exit 1
    }
    Write-Warn "El asistente no funcionara hasta que instales y autentiques Claude Code."
}

# ============================================================================
# PASO 3/10 — Canal de mensajeria
# ============================================================================
Write-Header "3" "Elige tu canal de mensajeria"

Write-Host "  1) Telegram  [RECOMENDADO] - Gratis, sin riesgo, 2 minutos de setup" -ForegroundColor Green
Write-Host "  2) WhatsApp Baileys (no oficial) - ~`$2/mes, riesgo de ban del numero" -ForegroundColor Yellow
Write-Host "  3) WhatsApp Business API (oficial) - ~`$5-20/mes, cero riesgo" -ForegroundColor Cyan
Write-Host "  4) Todos los anteriores" -ForegroundColor Magenta
Write-Host ""
$channelChoice = Ask-Input "Tu eleccion" "1"
while ($channelChoice -notmatch "^[1234]$") {
    Write-Err "Escribe 1, 2, 3 o 4."
    $channelChoice = Ask-Input "Tu eleccion" "1"
}

# ============================================================================
# PASO 4/10 — Configurar canal
# ============================================================================
Write-Header "4" "Configurando tu canal de mensajeria"

$skipEnv = $false
if (Test-Path $EnvFile) {
    Write-Warn "Ya existe un archivo de configuracion (.env)."
    if (Ask-Confirm "Reconfigurar desde cero? (se guarda backup automatico)") {
        $backupName = "$EnvFile.backup.$(Get-Date -Format 'yyyyMMdd_HHmmss')"
        Copy-Item $EnvFile $backupName
        Write-Step "Backup guardado: $(Split-Path $backupName -Leaf)"
        $envTemplate = Join-Path $ProjectDir ".env.example"
        if (Test-Path $envTemplate) { Copy-Item $envTemplate $EnvFile }
        else {
@"
TELEGRAM_BOT_TOKEN=
AUTHORIZED_CHAT_ID=
SECURITY_PIN=
CLAUDE_CLI_PATH=claude
WHISPER_MODEL=small
TTS_ENGINE=auto
DB_ENCRYPTION_KEY=
TIMEZONE=America/New_York
LOG_LEVEL=INFO
"@ | Out-File -FilePath $EnvFile -Encoding utf8
        }
    } else {
        Write-Step "Manteniendo .env existente."
        $skipEnv = $true
    }
} else {
    $envTemplate = Join-Path $ProjectDir ".env.example"
    if (Test-Path $envTemplate) { Copy-Item $envTemplate $EnvFile }
    else {
@"
TELEGRAM_BOT_TOKEN=
AUTHORIZED_CHAT_ID=
SECURITY_PIN=
CLAUDE_CLI_PATH=claude
WHISPER_MODEL=small
TTS_ENGINE=auto
DB_ENCRYPTION_KEY=
TIMEZONE=America/New_York
LOG_LEVEL=INFO
"@ | Out-File -FilePath $EnvFile -Encoding utf8
    }
}

$botUsername = ""

if (-not $skipEnv) {

    # --- TELEGRAM ---
    if ($channelChoice -eq "1" -or $channelChoice -eq "4") {
        Write-Host ""
        Write-Host "  --- Configuracion de Telegram ---" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  PASO A de 2: Crear el bot con @BotFather" -ForegroundColor White
        Write-Host "  1. Abre Telegram en tu telefono o computadora"
        Write-Host "  2. Busca @BotFather (tiene paloma azul de verificado)"
        Write-Host "  3. Enviable: /newbot"
        Write-Host "  4. Pon el nombre de tu bot (ej: Mi Asistente IA)"
        Write-Host "  5. Pon el username (debe terminar en _bot, ej: mi_asistente_ia_bot)"
        Write-Host "  6. Copia el TOKEN que te da BotFather:"
        Write-Host "     Ejemplo: 7123456789:AAHxxxxxxxxxxxxxxxxxxx" -ForegroundColor DarkGray
        Write-Host ""

        $tgToken = ""
        while ($true) {
            $tgToken = Ask-Input "Pega el token aqui"
            if ([string]::IsNullOrWhiteSpace($tgToken)) { Write-Err "Token vacio. Intenta de nuevo."; continue }
            if ($tgToken -notmatch "^\d+:[A-Za-z0-9_-]+$") {
                Write-Err "Formato invalido. Debe verse como: 1234567890:AAHxxx..."
                continue
            }
            Write-Work "Verificando token con Telegram..."
            try {
                $result = Invoke-RestMethod -Uri "https://api.telegram.org/bot$tgToken/getMe" -TimeoutSec 15 -ErrorAction Stop
                if ($result.ok) {
                    $botUsername = $result.result.username
                    $botName     = $result.result.first_name
                    Write-Step "Token valido! Bot: $botName (@$botUsername)"
                    Update-EnvVar "TELEGRAM_BOT_TOKEN" $tgToken
                    break
                }
            } catch {
                Write-Err "Token invalido o sin conexion a internet. Revisa e intenta de nuevo."
            }
        }

        Write-Host ""
        Write-Host "  PASO B de 2: Obtener tu Chat ID de Telegram" -ForegroundColor White
        Write-Host "  1. Busca @userinfobot en Telegram"
        Write-Host "  2. Enviable cualquier mensaje (ej: hola)"
        Write-Host "  3. Te respondara con tu ID (un numero como: 123456789)"
        Write-Host ""

        $tgChatId = ""
        while ($true) {
            $tgChatId = Ask-Input "Pega tu Chat ID"
            if ([string]::IsNullOrWhiteSpace($tgChatId)) { Write-Err "ID vacio."; continue }
            if ($tgChatId -notmatch "^-?\d+$") { Write-Err "El ID debe ser un numero (ej: 123456789)."; continue }
            Update-EnvVar "AUTHORIZED_CHAT_ID" $tgChatId
            Write-Step "Chat ID configurado: $tgChatId"
            break
        }

        # Mensaje de prueba
        Write-Work "Enviando mensaje de prueba a tu Telegram..."
        try {
            $testBody = @{ chat_id = $tgChatId; text = "Hola! Soy tu asistente de IA. La instalacion va bien! Si ves este mensaje todo funciona." }
            $testResult = Invoke-RestMethod -Uri "https://api.telegram.org/bot$tgToken/sendMessage" -Method Post -Body $testBody -TimeoutSec 10
            if ($testResult.ok) {
                Write-Step "Mensaje de prueba enviado. Revisa tu Telegram!"
            }
        } catch {
            Write-Warn "No se pudo enviar el mensaje de prueba (normal si no has iniciado el bot aun)."
            Write-Host "  Inicia el bot: ve a Telegram, busca @$botUsername, envia /start" -ForegroundColor DarkGray
        }
    }

    # --- WHATSAPP BAILEYS ---
    if ($channelChoice -eq "2" -or $channelChoice -eq "4") {
        Write-Host ""
        Write-Host "  --- WhatsApp Baileys ---" -ForegroundColor Yellow
        Write-Host ""
        Write-Warn "ADVERTENCIA: Baileys usa el protocolo NO OFICIAL de WhatsApp."
        Write-Warn "Meta PUEDE BANEAR permanentemente el numero que uses."
        Write-Host ""
        Write-Host "  NUNCA uses tu numero personal de WhatsApp." -ForegroundColor Red
        Write-Host ""
        Write-Host "  Numeros virtuales baratos:" -ForegroundColor White
        Write-Host "  * TextNow (gratis, solo USA)" -ForegroundColor DarkGray
        Write-Host "  * Google Voice (gratis, solo USA)" -ForegroundColor DarkGray
        Write-Host "  * Twilio (~`$1-2/mes, global)" -ForegroundColor DarkGray
        Write-Host ""
        if (Ask-Confirm "Entiendes el riesgo y quieres configurar WhatsApp Baileys?") {
            $waNumber = Ask-Input "Numero virtual (con codigo de pais, ej: +1234567890)"
            if ($waNumber) {
                Update-EnvVar "WHATSAPP_NUMBER" $waNumber
                Update-EnvVar "WHATSAPP_BRIDGE_URL" "http://localhost:3001"
                Write-Step "WhatsApp Baileys configurado."
                Write-Host "  Despues de la instalacion, inicia el bridge:" -ForegroundColor DarkGray
                Write-Host "  cd whatsapp-bridge && npm start" -ForegroundColor DarkGray
            }
        }
    }

    # --- WHATSAPP BUSINESS API ---
    if ($channelChoice -eq "3" -or $channelChoice -eq "4") {
        Write-Host ""
        Write-Host "  --- WhatsApp Business API ---" -ForegroundColor Cyan
        Write-Host "  (Requiere cuenta Meta Business verificada)" -ForegroundColor DarkGray
        Write-Host ""
        $waPhoneId  = Ask-Input "Phone Number ID"
        $waBizToken = Ask-Input "API Token"
        $waVerify   = Ask-Input "Webhook Verify Token (inventa uno)"
        if ($waPhoneId) {
            Update-EnvVar "WHATSAPP_PHONE_NUMBER_ID" $waPhoneId
            Update-EnvVar "WHATSAPP_BUSINESS_TOKEN" $waBizToken
            Update-EnvVar "WHATSAPP_VERIFY_TOKEN" $waVerify
            Write-Step "WhatsApp Business API configurado."
        }
    }

} # end -not skipEnv (channel config)

# ============================================================================
# PASO 5/10 — Entorno virtual de Python
# ============================================================================
Write-Header "5" "Preparando entorno de Python"

Write-Host "  Creando un espacio aislado para el asistente." -ForegroundColor DarkGray
Write-Host "  Esto evita conflictos con otros programas de tu sistema." -ForegroundColor DarkGray
Write-Host ""

if (Test-Path $VenvPath) {
    Write-Step "Entorno virtual ya existe — reutilizando."
} else {
    Write-Work "Creando entorno virtual con $pythonCmd..."
    & $pythonCmd -m venv $VenvPath
    if (-not (Test-Path $PythonVenv)) {
        Write-Err "Error al crear el entorno virtual. Verifica que Python tenga el modulo 'venv'."
        Write-Host "  Instalar: python -m pip install virtualenv" -ForegroundColor Yellow
        exit 1
    }
    Write-Step "Entorno virtual creado en .venv/"
}

Write-Work "Actualizando pip..."
& $PipVenv install --upgrade pip setuptools wheel --quiet 2>&1 | Out-Null
Write-Step "pip actualizado."

# ============================================================================
# PASO 6/10 — Dependencias
# ============================================================================
Write-Header "6" "Instalando dependencias (1-3 minutos)"

Write-Host "  Instalando los paquetes que necesita tu asistente." -ForegroundColor DarkGray
Write-Host "  Esto puede tardar unos minutos segun tu conexion." -ForegroundColor DarkGray
Write-Host ""

# apsw (SQLite driver) — install with binary wheel to avoid C compilation
Write-Work "Instalando driver de base de datos (apsw)..."
& $PipVenv install apsw --prefer-binary --quiet 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Warn "apsw no disponible con wheel pre-compilado."
    Write-Work "Intentando compilar desde fuente (requiere Visual C++ Build Tools)..."
    & $PipVenv install apsw --quiet 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "apsw no pudo instalarse. La base de datos usara sqlite3 estandar."
    }
}

# Core dependencies individually for better error handling
$coreDeps = @(
    @{ name = "Telegram bot";    pkg = "python-telegram-bot[ext]" },
    @{ name = "HTTP client";     pkg = "httpx aiohttp" },
    @{ name = "Audio (pydub)";   pkg = "pydub" },
    @{ name = "Pydantic";        pkg = "pydantic>=2.0 pydantic-settings" },
    @{ name = "Scheduler";       pkg = "APScheduler>=3.10" },
    @{ name = "File watcher";    pkg = "watchdog" },
    @{ name = "Web scraping";    pkg = "beautifulsoup4" },
    @{ name = "Logging";         pkg = "structlog" },
    @{ name = "Crypto";          pkg = "cryptography bcrypt" },
    @{ name = "Config";          pkg = "python-dotenv" },
    @{ name = "TTS (gTTS)";      pkg = "gTTS" }
)

foreach ($dep in $coreDeps) {
    Write-Work "  $($dep.name)..."
    $result = & $PipVenv install $dep.pkg --quiet 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "  $($dep.name) fallo. Continuando..."
    }
}

# Windows-specific (desktop control, TTS)
Write-Work "Paquetes especificos de Windows..."
& $PipVenv install pyautogui pyperclip pyttsx3 --quiet 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Warn "Paquetes de Windows no se instalaron completamente. Control de escritorio limitado."
}

# faster-whisper (STT — may need ctranslate2 binary)
Write-Work "faster-whisper (transcripcion de voz)..."
& $PipVenv install faster-whisper --prefer-binary --quiet 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Warn "faster-whisper no se instalo. Los mensajes de voz no funcionaran."
    Write-Host "  Para instalarlo manualmente: .venv\Scripts\pip install faster-whisper" -ForegroundColor DarkGray
}

# Install the package itself (editable)
Write-Work "Instalando el asistente..."
& $PipVenv install -e . --quiet --no-deps 2>&1 | Out-Null

Write-Step "Dependencias instaladas."

# ============================================================================
# PASO 7/10 — Modelo de audio (Whisper)
# ============================================================================
Write-Header "7" "Configuracion de audio (Whisper)"

Write-Host "  Selecciona el modelo de reconocimiento de voz:" -ForegroundColor White
Write-Host ""
Write-Host "  1) Rapido    (tiny,    75MB)  - Menos preciso, responde al instante" -ForegroundColor Green
Write-Host "  2) Equilibrado (small, 500MB) - Buena precision y velocidad [RECOMENDADO]" -ForegroundColor Green
Write-Host "  3) Preciso   (medium,  1.5GB) - Muy buena precision, un poco mas lento"
Write-Host "  4) Maximo    (large-v3, 3GB)  - La mejor precision, necesita GPU o 8+ GB RAM"
Write-Host ""
$whisperChoice = Ask-Input "Tu eleccion" "2"
$whisperModel = switch ($whisperChoice) {
    "1" { "tiny" }; "2" { "small" }; "3" { "medium" }; "4" { "large-v3" }; default { "small" }
}
Update-EnvVar "WHISPER_MODEL" $whisperModel
Write-Step "Modelo configurado: $whisperModel"
Write-Host "  El modelo se descarga automaticamente la primera vez que recibas un audio." -ForegroundColor DarkGray
Write-Host ""

if (Ask-Confirm "Descargar el modelo ahora? (se descargara automaticamente al primer uso si no)") {
    Write-Work "Descargando modelo '$whisperModel'... (puede tardar varios minutos)"
    & $PythonVenv -c "from faster_whisper import WhisperModel; WhisperModel('$whisperModel')" 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-Step "Modelo descargado y listo." }
    else { Write-Warn "Se descargara automaticamente al primer uso." }
}

# ============================================================================
# PASOS 8-9 — Zona horaria y Seguridad (solo si no hay .env previo)
# ============================================================================
if (-not $skipEnv) {

    Write-Header "8" "Zona horaria"

    Write-Host "  Tu asistente necesita saber tu zona horaria para" -ForegroundColor DarkGray
    Write-Host "  recordatorios y tareas programadas." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "   1)  Estados Unidos Este   (New York, Miami, Florida)"
    Write-Host "   2)  Estados Unidos Centro (Chicago, Houston, Dallas)"
    Write-Host "   3)  Estados Unidos Oeste  (Los Angeles, San Francisco)"
    Write-Host "   4)  Mexico                (Ciudad de Mexico, Guadalajara)"
    Write-Host "   5)  Colombia              (Bogota, Medellin)"
    Write-Host "   6)  Espana                (Madrid, Barcelona)"
    Write-Host "   7)  Argentina             (Buenos Aires)"
    Write-Host "   8)  Chile                 (Santiago)"
    Write-Host "   9)  Peru                  (Lima)"
    Write-Host "  10)  Otra (escribir manualmente)"
    Write-Host ""
    $tzChoice = Ask-Input "Tu eleccion" "1"
    $timezone = switch ($tzChoice) {
        "1"  { "America/New_York" }
        "2"  { "America/Chicago" }
        "3"  { "America/Los_Angeles" }
        "4"  { "America/Mexico_City" }
        "5"  { "America/Bogota" }
        "6"  { "Europe/Madrid" }
        "7"  { "America/Argentina/Buenos_Aires" }
        "8"  { "America/Santiago" }
        "9"  { "America/Lima" }
        "10" { Ask-Input "Zona horaria (ej: America/New_York)" "America/New_York" }
        default { "America/New_York" }
    }
    Update-EnvVar "TIMEZONE" $timezone
    Write-Step "Zona horaria: $timezone"

    Write-Header "9" "Seguridad"

    Write-Host "  Puedes proteger el asistente con un PIN de seguridad (4-8 digitos)." -ForegroundColor DarkGray
    Write-Host "  Se pedira para operaciones sensibles (borrar datos, cambiar config)." -ForegroundColor DarkGray
    Write-Host "  Es opcional. Puedes omitirlo presionando Enter." -ForegroundColor DarkGray
    Write-Host ""
    $secPin = Ask-Input "PIN (4-8 digitos, Enter para omitir)"
    if ($secPin -match "^\d{4,8}$") {
        Update-EnvVar "SECURITY_PIN" $secPin
        Write-Step "PIN de seguridad configurado."
    } else {
        Write-Step "PIN omitido. Puedes agregarlo despues en el archivo .env"
    }

    # Generar clave de cifrado
    Write-Work "Generando clave de cifrado para la base de datos..."
    $dbKey = & $PythonVenv -c "import secrets; print(secrets.token_hex(32))" 2>&1
    if ($dbKey -and $dbKey -match "^[0-9a-f]{64}$") {
        Update-EnvVar "DB_ENCRYPTION_KEY" $dbKey
        Write-Step "Clave de cifrado generada automaticamente."
        Write-Host "  Guardada en .env. No la compartas ni la cambies una vez creada." -ForegroundColor DarkGray
    }

} # end -not skipEnv (timezone/security)

# ============================================================================
# PASO 10/10 — Configuracion final
# ============================================================================
Write-Header "10" "Configuracion final"

# Crear directorios
foreach ($dir in @("data", "logs", "skills", "models", "mcps",
                   "data\knowledge", "data\projects", "data\daily")) {
    $dirPath = Join-Path $ProjectDir $dir
    if (-not (Test-Path $dirPath)) {
        New-Item -ItemType Directory -Path $dirPath -Force | Out-Null
    }
}
Write-Step "Directorios de datos creados."

# Crear start.bat
$startBatContent = @"
@echo off
title Personal AI Assistant
cd /d "%~dp0"
echo.
echo  Iniciando Personal AI Assistant...
echo  Presiona Ctrl+C para detenerlo.
echo.
.venv\Scripts\python.exe -m src.main
if errorlevel 1 (
    echo.
    echo  El asistente se detuvo. Revisa los logs en la carpeta logs/
    pause
)
"@
$startBatContent | Out-File -FilePath (Join-Path $ProjectDir "start.bat") -Encoding ascii
Write-Step "Creado start.bat (doble clic para iniciar el asistente)."

# Crear start_hidden.vbs (lanza sin ventana de consola)
$startVbsContent = @"
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run chr(34) & WScript.ScriptFullName & chr(34), 0, False
Set objShell = CreateObject("Shell.Application")
objShell.ShellExecute ".venv\Scripts\pythonw.exe", "-m src.main", CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName), "open", 0
"@
$startVbsContent | Out-File -FilePath (Join-Path $ProjectDir "start_hidden.vbs") -Encoding ascii
Write-Step "Creado start_hidden.vbs (inicia el asistente sin ventana de consola)."

# Inicio automatico con Task Scheduler
Write-Host ""
Write-Host "  Inicio automatico al iniciar sesion en Windows." -ForegroundColor White
Write-Host "  El asistente arrancara solo sin que tengas que hacer nada." -ForegroundColor DarkGray
Write-Host ""
if (Ask-Confirm "Activar inicio automatico?") {
    try {
        $taskName = "PersonalAIAssistant"

        # Usar pythonw.exe si existe (sin ventana de consola)
        $exeToUse = if (Test-Path $PythonwVenv) { $PythonwVenv } else { $PythonVenv }

        $action = New-ScheduledTaskAction `
            -Execute $exeToUse `
            -Argument "-m src.main" `
            -WorkingDirectory $ProjectDir

        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

        $settings = New-ScheduledTaskSettingsSet `
            -RestartCount 3 `
            -RestartInterval (New-TimeSpan -Minutes 2) `
            -ExecutionTimeLimit (New-TimeSpan -Days 365) `
            -StartWhenAvailable

        Register-ScheduledTask `
            -TaskName $taskName `
            -Action $action `
            -Trigger $trigger `
            -Settings $settings `
            -RunLevel Highest `
            -Force | Out-Null

        Write-Step "Tarea de inicio automatico creada: '$taskName'"
        Write-Host "  El asistente se iniciara automaticamente al abrir sesion." -ForegroundColor DarkGray
        Write-Host "  Para desactivar: schtasks /Delete /TN PersonalAIAssistant /F" -ForegroundColor DarkGray
    } catch {
        Write-Warn "No se pudo crear la tarea automatica: $($_.Exception.Message)"
        Write-Host "  Puedes iniciar manualmente con start.bat" -ForegroundColor DarkGray
    }
} else {
    Write-Step "Inicio automatico omitido. Usa start.bat para iniciar."
}

# ============================================================================
# PANTALLA FINAL
# ============================================================================
Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host "       Instalacion completada con exito!" -ForegroundColor Green
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Para iniciar el asistente:" -ForegroundColor White
Write-Host "    Doble clic en start.bat" -ForegroundColor Cyan
Write-Host "    O en PowerShell: .venv\Scripts\python.exe -m src.main" -ForegroundColor Cyan
Write-Host ""
if ($botUsername) {
    Write-Host "  Luego en Telegram:" -ForegroundColor White
    Write-Host "    Busca tu bot: @$botUsername" -ForegroundColor Cyan
    Write-Host "    Envialo: hola" -ForegroundColor Cyan
    Write-Host "    El asistente te respondera y te guiara desde ahi." -ForegroundColor DarkGray
    Write-Host ""
}
Write-Host "  Archivos importantes:" -ForegroundColor White
Write-Host "    .env             <- tu configuracion (no lo compartas)" -ForegroundColor DarkGray
Write-Host "    start.bat        <- iniciar el asistente (doble clic)" -ForegroundColor DarkGray
Write-Host "    data\            <- tus datos y conversaciones" -ForegroundColor DarkGray
Write-Host "    logs\            <- registros de actividad" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Resumen de lo instalado:" -ForegroundColor White
Write-Host "    Python: $(& $pythonCmd --version 2>&1)" -ForegroundColor DarkGray
Write-Host "    Entorno virtual: .venv/" -ForegroundColor DarkGray
Write-Host "    Modelo Whisper: $whisperModel" -ForegroundColor DarkGray
if (-not $skipEnv) {
    Write-Host "    Zona horaria: $timezone" -ForegroundColor DarkGray
}
Write-Host ""
Write-Host "  Listo! Tu asistente te espera." -ForegroundColor Green
Write-Host ""
Read-Host "  Presiona Enter para cerrar"
