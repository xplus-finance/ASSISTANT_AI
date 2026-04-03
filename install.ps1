# ============================================================================
# Personal AI Assistant - Instalador Interactivo v3.0 (Windows)
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
    Write-Host "  PASO $n de 11 -- $t" -ForegroundColor Cyan
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
# BIENVENIDA
# ============================================================================
Clear-Host
Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Cyan
Write-Host "      Personal AI Assistant - Instalador v3.0 (Windows)       " -ForegroundColor Cyan
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
# PASO 1/11 - Verificar sistema
# ============================================================================
Write-Header "1" "Verificando tu sistema"

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

if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
    Write-Step "ffmpeg instalado (procesamiento de audio OK)"
} else {
    Write-Warn "ffmpeg no encontrado"
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Work "Instalando ffmpeg con winget..."
        winget install --id Gyan.FFmpeg -e --silent 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Step "ffmpeg instalado correctamente."
        } else {
            Write-Warn "No se pudo instalar ffmpeg. Los mensajes de voz no funcionaran."
        }
    } else {
        Write-Host "  Instala ffmpeg manualmente: https://ffmpeg.org/download.html" -ForegroundColor Yellow
    }
}

Write-Step "Verificacion del sistema completada."

# ============================================================================
# PASO 2/11 - Claude Code CLI
# ============================================================================
Write-Header "2" "Claude Code (el cerebro de tu asistente)"

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
    Write-Host ""
    if (-not (Ask-Confirm "Continuar sin Claude Code?")) { exit 1 }
    Write-Warn "El asistente no funcionara hasta que instales Claude Code."
}

# ============================================================================
# PASO 3/11 - Canal de mensajeria
# ============================================================================
Write-Header "3" "Elige tu canal de mensajeria"

Write-Host "  1) Telegram  [RECOMENDADO] - Gratis, sin riesgo" -ForegroundColor Green
Write-Host "  2) WhatsApp Baileys (no oficial) - Riesgo de ban" -ForegroundColor Yellow
Write-Host "  3) WhatsApp Business API (oficial) - Cero riesgo" -ForegroundColor Cyan
Write-Host "  4) Todos los anteriores" -ForegroundColor Magenta
Write-Host ""
$channelChoice = Ask-Input "Tu eleccion" "1"
while ($channelChoice -notmatch "^[1234]$") {
    Write-Err "Escribe 1, 2, 3 o 4."
    $channelChoice = Ask-Input "Tu eleccion" "1"
}

# ============================================================================
# PASO 4/11 - Configurar canal
# ============================================================================
Write-Header "4" "Configurando tu canal de mensajeria"

$skipEnv = $false
if (Test-Path $EnvFile) {
    Write-Warn "Ya existe un archivo de configuracion (.env)."
    if (Ask-Confirm "Reconfigurar desde cero? (se guarda backup)") {
        $backupName = "$EnvFile.backup.$(Get-Date -Format 'yyyyMMdd_HHmmss')"
        Copy-Item $EnvFile $backupName
        Write-Step "Backup guardado: $(Split-Path $backupName -Leaf)"
        $envTemplate = Join-Path $ProjectDir ".env.example"
        if (Test-Path $envTemplate) { Copy-Item $envTemplate $EnvFile }
    } else {
        Write-Step "Manteniendo .env existente."
        $skipEnv = $true
    }
} else {
    $envTemplate = Join-Path $ProjectDir ".env.example"
    if (Test-Path $envTemplate) { Copy-Item $envTemplate $EnvFile }
}

$botUsername = ""

if (-not $skipEnv) {
    # --- TELEGRAM ---
    if ($channelChoice -eq "1" -or $channelChoice -eq "4") {
        Write-Host ""
        Write-Host "  --- Configuracion de Telegram ---" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  1. Abre Telegram, busca @BotFather"
        Write-Host "  2. Envia: /newbot"
        Write-Host "  3. Sigue las instrucciones y copia el TOKEN"
        Write-Host ""

        $tgToken = ""
        while ($true) {
            $tgToken = Ask-Input "Pega el token aqui"
            if ([string]::IsNullOrWhiteSpace($tgToken)) { Write-Err "Token vacio."; continue }
            if ($tgToken -notmatch "^\d+:[A-Za-z0-9_-]+$") { Write-Err "Formato invalido."; continue }
            Write-Work "Verificando token..."
            try {
                $result = Invoke-RestMethod -Uri "https://api.telegram.org/bot$tgToken/getMe" -TimeoutSec 15 -ErrorAction Stop
                if ($result.ok) {
                    $botUsername = $result.result.username
                    Write-Step "Token valido! Bot: @$botUsername"
                    Update-EnvVar "TELEGRAM_BOT_TOKEN" $tgToken
                    break
                }
            } catch {
                Write-Err "Token invalido o sin conexion."
            }
        }

        Write-Host ""
        Write-Host "  Ahora necesitas tu Chat ID:" -ForegroundColor White
        Write-Host "  1. Busca @userinfobot en Telegram"
        Write-Host "  2. Envia cualquier mensaje"
        Write-Host "  3. Copia tu ID (un numero)"
        Write-Host ""

        while ($true) {
            $tgChatId = Ask-Input "Pega tu Chat ID"
            if ($tgChatId -match "^-?\d+$") {
                Update-EnvVar "AUTHORIZED_CHAT_ID" $tgChatId
                Write-Step "Chat ID configurado: $tgChatId"
                break
            }
            Write-Err "El ID debe ser un numero."
        }

        Write-Work "Enviando mensaje de prueba..."
        try {
            $testBody = @{ chat_id = $tgChatId; text = "Hola! Soy tu asistente. La instalacion va bien!" }
            Invoke-RestMethod -Uri "https://api.telegram.org/bot$tgToken/sendMessage" -Method Post -Body $testBody -TimeoutSec 10 | Out-Null
            Write-Step "Mensaje de prueba enviado. Revisa tu Telegram!"
        } catch {
            Write-Warn "No se pudo enviar (normal si no has iniciado el bot)."
        }
    }

    # --- WHATSAPP BAILEYS ---
    if ($channelChoice -eq "2" -or $channelChoice -eq "4") {
        Write-Host ""
        Write-Host "  --- WhatsApp Baileys ---" -ForegroundColor Yellow
        Write-Warn "NUNCA uses tu numero personal. Riesgo de ban."
        Write-Host ""
        if (Ask-Confirm "Configurar WhatsApp Baileys?") {
            $waNumber = Ask-Input "Numero virtual (ej: +1234567890)"
            if ($waNumber) {
                Update-EnvVar "WHATSAPP_NUMBER" $waNumber
                Update-EnvVar "WHATSAPP_BRIDGE_URL" "http://localhost:3001"
                Write-Step "WhatsApp Baileys configurado."
            }
        }
    }

    # --- WHATSAPP BUSINESS API ---
    if ($channelChoice -eq "3" -or $channelChoice -eq "4") {
        Write-Host ""
        Write-Host "  --- WhatsApp Business API ---" -ForegroundColor Cyan
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
}

# ============================================================================
# PASO 5/11 - Entorno virtual
# ============================================================================
Write-Header "5" "Preparando entorno de Python"

if ((Test-Path $VenvPath) -and (Test-Path $PythonVenv)) {
    Write-Step "Entorno virtual ya existe."
} else {
    if (Test-Path $VenvPath) {
        Write-Warn "Entorno virtual corrupto (falta python.exe). Recreando..."
        Remove-Item $VenvPath -Recurse -Force
    }
    Write-Work "Creando entorno virtual..."
    & $pythonCmd -m venv $VenvPath
    if (-not (Test-Path $PythonVenv)) {
        Write-Err "Error al crear el entorno virtual."
        exit 1
    }
    Write-Step "Entorno virtual creado en .venv/"
}

Write-Work "Actualizando pip..."
& $PipVenv install --upgrade pip setuptools wheel --quiet 2>&1 | Out-Null
Write-Step "pip actualizado."

# ============================================================================
# PASO 6/11 - Dependencias
# ============================================================================
Write-Header "6" "Instalando dependencias (1-3 minutos)"

# Install everything from pyproject.toml (single source of truth for dependencies)
# Using -e ".[windows]" installs core deps + Windows-specific packages
Write-Work "Instalando dependencias desde pyproject.toml..."
$pipLog = Join-Path $env:TEMP "pip_install.log"
try {
    & $PipVenv install -e ".[windows]" --prefer-binary 2>&1 | Out-File $pipLog -Encoding utf8
    $pipExit = $LASTEXITCODE
} catch {
    $pipExit = 1
}

if ($pipExit -ne 0) {
    Write-Err "Error al instalar dependencias."
    Write-Host ""
    Write-Host "  Ultimas lineas del log:" -ForegroundColor DarkGray
    Get-Content $pipLog -Tail 15 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
    Write-Host ""
    Write-Host "  Log completo: $pipLog" -ForegroundColor White
    Write-Host "  Intenta manualmente: .venv\Scripts\pip.exe install -e `".[windows]`"" -ForegroundColor Cyan
    Write-Host ""
    Read-Host "  Presiona Enter para salir"
    exit 1
}
Remove-Item $pipLog -ErrorAction SilentlyContinue

# Verify critical imports actually work
Write-Work "Verificando dependencias..."
$verifyCode = @"
ok, fail = [], []
for mod in ['telegram','httpx','aiohttp','pydub','pydantic','pydantic_settings','structlog','cryptography','bcrypt','dotenv','PIL','openai','apsw','faster_whisper']:
    try:
        __import__(mod)
        ok.append(mod)
    except ImportError:
        fail.append(mod)
print(f'OK: {len(ok)}/{len(ok)+len(fail)}')
if fail: print(f'FALTAN: {", ".join(fail)}')
else: print('Todas las dependencias verificadas')
"@
try {
    $verifyOut = & $PythonVenv -c $verifyCode 2>&1 | Out-String
    $verifyTrimmed = $verifyOut.Trim()
    Write-Host "  $verifyTrimmed" -ForegroundColor DarkGray
    if ($verifyTrimmed -match "FALTAN") {
        Write-Warn "Algunas dependencias no se instalaron. Revisa el output."
    }
} catch {}

Write-Step "Dependencias instaladas."

# ============================================================================
# PASO 7/11 - Audio (Whisper)
# ============================================================================
Write-Header "7" "Configuracion de audio"

Write-Host "  1) Rapido    (tiny,    75MB)" -ForegroundColor Green
Write-Host "  2) Equilibrado (small, 500MB) [RECOMENDADO]" -ForegroundColor Green
Write-Host "  3) Preciso   (medium,  1.5GB)"
Write-Host "  4) Maximo    (large-v3, 3GB)"
Write-Host ""
$whisperChoice = Ask-Input "Tu eleccion" "2"
$whisperModel = switch ($whisperChoice) {
    "1" { "tiny" }; "2" { "small" }; "3" { "medium" }; "4" { "large-v3" }; default { "small" }
}
Update-EnvVar "WHISPER_MODEL" $whisperModel
Write-Step "Modelo: $whisperModel"

if (Ask-Confirm "Descargar el modelo ahora?") {
    Write-Work "Descargando '$whisperModel'..."
    & $PythonVenv -c "from faster_whisper import WhisperModel; WhisperModel('$whisperModel')" 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-Step "Modelo descargado." }
    else { Write-Warn "Se descargara al primer uso." }
}

# ============================================================================
# PASO 8/11 - Mascota de escritorio
# ============================================================================
Write-Header "8" "Mascota de escritorio"

Write-Host "  1) Perro   - Fiel, mueve la cola" -ForegroundColor Green
Write-Host "  2) Gato    - Elegante, se acurruca" -ForegroundColor Green
Write-Host "  3) Robot   - Luces, antena, jets" -ForegroundColor Green
Write-Host "  4) Zorro   - Astuto, cola frondosa" -ForegroundColor Green
Write-Host "  5) Buho    - Sabio, gira la cabeza" -ForegroundColor Green
Write-Host "  6) No quiero mascota" -ForegroundColor DarkGray
Write-Host ""
$petChoice = Ask-Input "Tu eleccion" "6"

$petType = ""
if ($petChoice -ne "6") {
    $petType = switch ($petChoice) {
        "1" { "dog" }; "2" { "cat" }; "3" { "robot" }; "4" { "fox" }; "5" { "owl" }; default { "dog" }
    }
    Write-Work "Instalando PyQt6..."
    & $PipVenv install PyQt6 --quiet 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Step "PyQt6 instalado."
        Update-EnvVar "PET_ENABLED" "true"
        Update-EnvVar "PET_TYPE" $petType
        Update-EnvVar "PET_SIZE" "96"
        Update-EnvVar "PET_MONITOR" "0"
        $petNames = @{ dog = "Perro"; cat = "Gato"; robot = "Robot"; fox = "Zorro"; owl = "Buho" }
        Write-Step "Mascota activada: $($petNames[$petType])"
    } else {
        Write-Warn "PyQt6 no se pudo instalar."
        Write-Host "  Instala Visual C++ Redistributable: https://aka.ms/vs/17/release/vc_redist.x64.exe" -ForegroundColor Cyan
    }
} else {
    Write-Step "Mascota omitida. Puedes activarla en .env (PET_ENABLED=true)"
}

# ============================================================================
# PASOS 9-10 - Zona horaria y Seguridad
# ============================================================================
if (-not $skipEnv) {

    Write-Header "9" "Zona horaria"

    Write-Host "   1)  Estados Unidos Este   (New York, Miami)"
    Write-Host "   2)  Estados Unidos Centro (Chicago, Houston)"
    Write-Host "   3)  Estados Unidos Oeste  (Los Angeles, SF)"
    Write-Host "   4)  Mexico                (CDMX, Guadalajara)"
    Write-Host "   5)  Colombia              (Bogota, Medellin)"
    Write-Host "   6)  Espana                (Madrid, Barcelona)"
    Write-Host "   7)  Argentina             (Buenos Aires)"
    Write-Host "   8)  Chile                 (Santiago)"
    Write-Host "   9)  Peru                  (Lima)"
    Write-Host "  10)  Otra (escribir)"
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

    Write-Header "10" "Seguridad"

    Write-Host "  El PIN de seguridad es OBLIGATORIO." -ForegroundColor Yellow
    Write-Host "  Se pide antes de cualquier accion invasiva." -ForegroundColor DarkGray
    Write-Host "  3 intentos fallidos = bloqueo de 24 horas." -ForegroundColor DarkGray
    Write-Host ""
    $secPin = ""
    while (-not $secPin -or $secPin.Length -lt 4) {
        $secPin = Ask-Input "PIN (minimo 4 digitos, OBLIGATORIO)"
        if (-not $secPin -or $secPin.Length -lt 4) {
            Write-Host "  El PIN es obligatorio y debe tener minimo 4 caracteres." -ForegroundColor Red
        }
    }
    Update-EnvVar "SECURITY_PIN" $secPin
    Write-Step "PIN configurado."

    Write-Work "Generando clave de cifrado..."
    $dbKey = & $PythonVenv -c "import secrets; print(secrets.token_hex(32))" 2>&1
    if ($dbKey -and $dbKey -match "^[0-9a-f]{64}$") {
        Update-EnvVar "DB_ENCRYPTION_KEY" $dbKey
        Write-Step "Clave de cifrado generada."
    }
}

# ============================================================================
# PASO 11/11 - Configuracion final
# ============================================================================
Write-Header "11" "Configuracion final"

# Crear directorios
foreach ($dir in @("data", "logs", "skills", "models", "mcps", "output", "config", "scripts",
                   "data\knowledge", "data\projects", "data\daily")) {
    $dirPath = Join-Path $ProjectDir $dir
    if (-not (Test-Path $dirPath)) {
        New-Item -ItemType Directory -Path $dirPath -Force | Out-Null
    }
}
Write-Step "Directorios creados."

# Crear start.bat
@"
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
    echo  El asistente se detuvo. Revisa los logs en logs/
    pause
)
"@ | Out-File -FilePath (Join-Path $ProjectDir "start.bat") -Encoding ascii
Write-Step "Creado start.bat"

# Inicio automatico
Write-Host ""
if (Ask-Confirm "Activar inicio automatico al iniciar sesion?") {
    try {
        $taskName = "PersonalAIAssistant"
        $exeToUse = if (Test-Path $PythonwVenv) { $PythonwVenv } else { $PythonVenv }
        $action = New-ScheduledTaskAction -Execute $exeToUse -Argument "-m src.main" -WorkingDirectory $ProjectDir
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
        $settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 2) -ExecutionTimeLimit (New-TimeSpan -Days 365) -StartWhenAvailable
        Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -RunLevel Limited -Force | Out-Null
        Write-Step "Inicio automatico activado."
    } catch {
        Write-Warn "No se pudo crear la tarea: $($_.Exception.Message)"
    }
} else {
    Write-Step "Inicio automatico omitido. Usa start.bat."
}

# ============================================================================
# PANTALLA FINAL
# ============================================================================
Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host "       Instalacion completada!" -ForegroundColor Green
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Para iniciar:" -ForegroundColor White
Write-Host "    Doble clic en start.bat" -ForegroundColor Cyan
Write-Host "    O: .venv\Scripts\python.exe -m src.main" -ForegroundColor Cyan
Write-Host ""
if ($botUsername) {
    Write-Host "  En Telegram busca: @$botUsername" -ForegroundColor White
    Write-Host "  Envia: hola" -ForegroundColor Cyan
    Write-Host ""
}
Write-Host "  Resumen:" -ForegroundColor White
Write-Host "    Python: $(& $pythonCmd --version 2>&1)" -ForegroundColor DarkGray
Write-Host "    Whisper: $whisperModel" -ForegroundColor DarkGray
if ($petType) {
    $petDisplay = @{ dog = "Perro"; cat = "Gato"; robot = "Robot"; fox = "Zorro"; owl = "Buho" }
    Write-Host "    Mascota: $($petDisplay[$petType])" -ForegroundColor DarkGray
}
if (-not $skipEnv) {
    Write-Host "    Zona horaria: $timezone" -ForegroundColor DarkGray
}
Write-Host ""
Write-Host "  Listo! Tu asistente te espera." -ForegroundColor Green
Write-Host ""
Read-Host "  Presiona Enter para cerrar"
