#!/bin/bash
set -e

# ============================================================================
# Personal AI Assistant — Instalador Interactivo v1.0
# ============================================================================
# Idempotente: seguro de ejecutar multiples veces.
# ============================================================================

# --- Colores ----------------------------------------------------------------
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

# --- Helpers ----------------------------------------------------------------
info()    { echo -e "${GREEN}[✓]${NC} $1"; }
warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
error()   { echo -e "${RED}[✗]${NC} $1"; }
ask()     { echo -en "${BLUE}[?]${NC} $1"; }
section() { echo -e "\n${BOLD}── $1 ──${NC}\n"; }

confirm() {
    ask "$1 [S/n]: "
    read -r resp
    [[ -z "$resp" || "$resp" =~ ^[sSyY]$ ]]
}

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# --- Banner -----------------------------------------------------------------
echo -e "${GREEN}"
echo "╔══════════════════════════════════════════════╗"
echo "║   Personal AI Assistant — Instalador v1.0    ║"
echo "╚══════════════════════════════════════════════╝"
echo -e "${NC}"
echo "Directorio del proyecto: $PROJECT_DIR"
echo ""

# ============================================================================
# 1. Python 3.12+
# ============================================================================
section "1/10 — Verificando Python"

PYTHON_CMD=""
for cmd in python3.12 python3.13 python3.14 python3; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [[ "$major" -ge 3 && "$minor" -ge 12 ]]; then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done

if [[ -z "$PYTHON_CMD" ]]; then
    error "Python 3.12+ no encontrado."
    echo "  Instala Python 3.12 o superior:"
    echo "    sudo apt install python3.12 python3.12-venv python3.12-dev"
    echo "  O usa pyenv/deadsnakes PPA si tu distro no lo tiene."
    exit 1
fi

info "Python encontrado: $PYTHON_CMD ($($PYTHON_CMD --version))"

# ============================================================================
# 2. ffmpeg
# ============================================================================
section "2/10 — Verificando ffmpeg"

if command -v ffmpeg &>/dev/null; then
    info "ffmpeg ya instalado: $(ffmpeg -version 2>&1 | head -1)"
else
    warn "ffmpeg no encontrado. Es necesario para procesar audio."
    if confirm "¿Instalar ffmpeg con apt?"; then
        sudo apt update && sudo apt install -y ffmpeg
        info "ffmpeg instalado correctamente."
    else
        error "ffmpeg es obligatorio para el procesamiento de audio."
        error "Instálalo manualmente: sudo apt install ffmpeg"
        exit 1
    fi
fi

# ============================================================================
# 3. bubblewrap (bwrap)
# ============================================================================
section "3/10 — Verificando bubblewrap (sandbox)"

if command -v bwrap &>/dev/null; then
    info "bubblewrap ya instalado."
else
    warn "bubblewrap (bwrap) no encontrado. Se usa para ejecutar comandos en sandbox."
    if confirm "¿Instalar bubblewrap con apt?"; then
        sudo apt update && sudo apt install -y bubblewrap
        info "bubblewrap instalado correctamente."
    else
        warn "Sin bubblewrap, los comandos se ejecutarán SIN sandbox."
        warn "Esto es un riesgo de seguridad. Puedes instalarlo después:"
        echo "  sudo apt install bubblewrap"
    fi
fi

# ============================================================================
# 4. Claude CLI
# ============================================================================
section "4/10 — Verificando Claude CLI"

if command -v claude &>/dev/null; then
    info "Claude CLI encontrado: $(which claude)"
    # Verificar autenticación intentando un comando simple
    if claude -p "test" --max-turns 1 &>/dev/null 2>&1; then
        info "Claude CLI autenticado correctamente."
    else
        warn "Claude CLI instalado pero podría no estar autenticado."
        echo "  Ejecuta: claude login"
        echo "  Y sigue las instrucciones para autenticarte."
    fi
else
    error "Claude CLI no encontrado."
    echo ""
    echo "  Para instalar Claude CLI:"
    echo "    npm install -g @anthropic-ai/claude-code"
    echo ""
    echo "  Después autentícate:"
    echo "    claude login"
    echo ""
    echo "  Más info: https://docs.anthropic.com/en/docs/claude-code"
    echo ""
    if confirm "¿Continuar sin Claude CLI? (podrás instalarlo después)"; then
        warn "Continuando sin Claude CLI. Recuerda instalarlo antes de usar el asistente."
    else
        exit 1
    fi
fi

# ============================================================================
# 5. Entorno virtual de Python
# ============================================================================
section "5/10 — Entorno virtual de Python"

if [[ -d "$PROJECT_DIR/.venv" ]]; then
    info "Entorno virtual ya existe en .venv/"
    source "$PROJECT_DIR/.venv/bin/activate"
else
    info "Creando entorno virtual con $PYTHON_CMD..."
    $PYTHON_CMD -m venv "$PROJECT_DIR/.venv"
    source "$PROJECT_DIR/.venv/bin/activate"
    info "Entorno virtual creado en .venv/"
fi

# Actualizar pip
pip install --upgrade pip --quiet
info "pip actualizado."

# ============================================================================
# 6. Dependencias de Python
# ============================================================================
section "6/10 — Instalando dependencias de Python"

info "Instalando paquete en modo editable (pip install -e .)..."
pip install -e ".[dev]" 2>&1 | tail -5
info "Dependencias de Python instaladas."

# ============================================================================
# 7. Configuración de .env
# ============================================================================
section "7/10 — Configuración del archivo .env"

ENV_FILE="$PROJECT_DIR/.env"

if [[ -f "$ENV_FILE" ]]; then
    warn "El archivo .env ya existe."
    if confirm "¿Quieres reconfigurarlo? (se creará un backup)"; then
        cp "$ENV_FILE" "$ENV_FILE.backup.$(date +%Y%m%d_%H%M%S)"
        info "Backup creado."
    else
        info "Manteniendo .env existente."
        SKIP_ENV=true
    fi
fi

if [[ "${SKIP_ENV:-}" != "true" ]]; then
    # Copiar template
    cp "$PROJECT_DIR/.env.example" "$ENV_FILE"

    echo ""
    echo -e "${BOLD}Selecciona los canales de mensajería:${NC}"
    echo "  1) Telegram (recomendado, gratis, sin riesgo de ban)"
    echo "  2) WhatsApp con Baileys (número virtual, riesgo medio de ban)"
    echo "  3) WhatsApp Business API (costo mensual, sin riesgo de ban)"
    echo "  4) Todos los anteriores"
    echo ""
    ask "Canales a configurar [1]: "
    read -r CHANNEL_CHOICE
    CHANNEL_CHOICE="${CHANNEL_CHOICE:-1}"

    # --- Telegram -----------------------------------------------------------
    if [[ "$CHANNEL_CHOICE" == "1" || "$CHANNEL_CHOICE" == "4" ]]; then
        echo ""
        echo -e "${BOLD}— Configuración de Telegram —${NC}"
        echo ""
        echo "  Necesitas crear un bot en Telegram:"
        echo "  1. Abre Telegram y busca @BotFather"
        echo "  2. Envía /newbot y sigue las instrucciones"
        echo "  3. Copia el token que te da (formato: 123456789:ABCdef...)"
        echo ""
        ask "Token del bot de Telegram: "
        read -r TG_TOKEN
        if [[ -n "$TG_TOKEN" ]]; then
            sed -i "s|^TELEGRAM_BOT_TOKEN=.*|TELEGRAM_BOT_TOKEN=$TG_TOKEN|" "$ENV_FILE"
        fi

        echo ""
        echo "  Para obtener tu Chat ID:"
        echo "  1. Busca @userinfobot en Telegram"
        echo "  2. Envíale cualquier mensaje"
        echo "  3. Te responde con tu ID (un número como 123456789)"
        echo ""
        ask "Tu Chat ID de Telegram: "
        read -r TG_CHAT_ID
        if [[ -n "$TG_CHAT_ID" ]]; then
            sed -i "s|^AUTHORIZED_CHAT_ID=.*|AUTHORIZED_CHAT_ID=$TG_CHAT_ID|" "$ENV_FILE"
        fi
    fi

    # --- WhatsApp Baileys ---------------------------------------------------
    if [[ "$CHANNEL_CHOICE" == "2" || "$CHANNEL_CHOICE" == "4" ]]; then
        echo ""
        echo -e "${RED}${BOLD}⚠ ADVERTENCIA: WhatsApp Baileys${NC}"
        echo -e "${RED}  Baileys usa el protocolo NO oficial de WhatsApp Web.${NC}"
        echo -e "${RED}  Meta PUEDE BANEAR el número usado.${NC}"
        echo -e "${RED}  NUNCA uses tu número personal.${NC}"
        echo ""
        echo "  Opciones de números virtuales:"
        echo "  - TextNow (gratis, USA)"
        echo "  - Google Voice (gratis, USA)"
        echo "  - Twilio (~\$1-2/mes)"
        echo "  - Número prepago barato"
        echo ""

        if confirm "¿Entiendes el riesgo y quieres continuar?"; then
            # Verificar Node.js
            if command -v node &>/dev/null; then
                NODE_VER=$(node -v)
                info "Node.js encontrado: $NODE_VER"
            else
                warn "Node.js no encontrado. Es necesario para el bridge de Baileys."
                echo "  Instala Node.js 20+: https://nodejs.org/"
            fi

            # Instalar dependencias del bridge si existe
            if [[ -d "$PROJECT_DIR/whatsapp-bridge" ]]; then
                info "Instalando dependencias del bridge de WhatsApp..."
                cd "$PROJECT_DIR/whatsapp-bridge" && npm install 2>&1 | tail -3
                cd "$PROJECT_DIR"
                info "Dependencias de Baileys instaladas."
            else
                warn "Directorio whatsapp-bridge/ no encontrado."
                echo "  Se creará cuando configures el bridge."
            fi

            ask "Número virtual para WhatsApp (con código de país, ej: +1234567890): "
            read -r WA_NUMBER
            if [[ -n "$WA_NUMBER" ]]; then
                # Agregar al .env si no existe la variable
                if ! grep -q "^WHATSAPP_NUMBER=" "$ENV_FILE"; then
                    echo "" >> "$ENV_FILE"
                    echo "# --- WhatsApp Baileys ---" >> "$ENV_FILE"
                    echo "WHATSAPP_NUMBER=$WA_NUMBER" >> "$ENV_FILE"
                    echo "WHATSAPP_BRIDGE_URL=http://localhost:3001" >> "$ENV_FILE"
                fi
            fi
        fi
    fi

    # --- WhatsApp Business API ----------------------------------------------
    if [[ "$CHANNEL_CHOICE" == "3" || "$CHANNEL_CHOICE" == "4" ]]; then
        echo ""
        echo -e "${BOLD}— Configuración de WhatsApp Business API —${NC}"
        echo ""
        echo "  Necesitas una cuenta en Meta Business / Cloud API."
        echo "  Más info: https://developers.facebook.com/docs/whatsapp/cloud-api"
        echo ""

        ask "WhatsApp Business Phone Number ID: "
        read -r WA_PHONE_ID
        ask "WhatsApp Business API Token: "
        read -r WA_BIZ_TOKEN
        ask "Webhook Verify Token (invéntalo): "
        read -r WA_VERIFY

        if [[ -n "$WA_PHONE_ID" ]]; then
            if ! grep -q "^WHATSAPP_PHONE_NUMBER_ID=" "$ENV_FILE"; then
                echo "" >> "$ENV_FILE"
                echo "# --- WhatsApp Business API ---" >> "$ENV_FILE"
                echo "WHATSAPP_PHONE_NUMBER_ID=$WA_PHONE_ID" >> "$ENV_FILE"
                echo "WHATSAPP_BUSINESS_TOKEN=$WA_BIZ_TOKEN" >> "$ENV_FILE"
                echo "WHATSAPP_VERIFY_TOKEN=$WA_VERIFY" >> "$ENV_FILE"
            fi
        fi
    fi

    # --- Zona horaria -------------------------------------------------------
    echo ""
    echo -e "${BOLD}— Zona horaria —${NC}"
    echo "  Ejemplos: America/Mexico_City, America/New_York, Europe/Madrid"
    echo "  America/Bogota, America/Lima, America/Santiago"
    echo ""
    ask "Tu zona horaria [America/New_York]: "
    read -r TZ_INPUT
    TZ_INPUT="${TZ_INPUT:-America/New_York}"
    sed -i "s|^TIMEZONE=.*|TIMEZONE=$TZ_INPUT|" "$ENV_FILE"

    # --- PIN de seguridad ---------------------------------------------------
    echo ""
    ask "PIN de seguridad para operaciones sensibles (Enter para omitir): "
    read -r SEC_PIN
    if [[ -n "$SEC_PIN" ]]; then
        sed -i "s|^SECURITY_PIN=.*|SECURITY_PIN=$SEC_PIN|" "$ENV_FILE"
    fi

    # --- Clave de cifrado de BD (generar automáticamente) -------------------
    DB_KEY=$($PYTHON_CMD -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s|^DB_ENCRYPTION_KEY=.*|DB_ENCRYPTION_KEY=$DB_KEY|" "$ENV_FILE"
    info "Clave de cifrado de base de datos generada automáticamente."

    info "Archivo .env configurado."
fi

# ============================================================================
# 8. Crear directorios
# ============================================================================
section "8/10 — Creando directorios"

for dir in data logs skills models data/knowledge; do
    mkdir -p "$PROJECT_DIR/$dir"
done
info "Directorios creados: data/, logs/, skills/, models/, data/knowledge/"

# ============================================================================
# 9. Modelo de Whisper
# ============================================================================
section "9/10 — Modelo de Whisper (speech-to-text)"

echo "  Modelos disponibles:"
echo "    tiny   — ~75 MB  — Rápido, baja precisión"
echo "    base   — ~150 MB — Equilibrio velocidad/precisión"
echo "    small  — ~500 MB — Buena precisión"
echo "    medium — ~1.5 GB — Muy buena precisión (recomendado)"
echo "    large-v3 — ~3 GB — Máxima precisión (necesita GPU)"
echo ""
ask "Modelo de Whisper a usar [medium]: "
read -r WHISPER_CHOICE
WHISPER_CHOICE="${WHISPER_CHOICE:-medium}"

# Actualizar .env
if [[ -f "$ENV_FILE" ]]; then
    sed -i "s|^WHISPER_MODEL=.*|WHISPER_MODEL=$WHISPER_CHOICE|" "$ENV_FILE"
fi

info "Modelo configurado: $WHISPER_CHOICE"
echo "  El modelo se descargará automáticamente la primera vez que recibas un audio."
echo "  Si prefieres descargarlo ahora, ejecuta:"
echo "    source .venv/bin/activate"
echo "    python -c \"from faster_whisper import WhisperModel; WhisperModel('$WHISPER_CHOICE')\""

if confirm "¿Descargar el modelo de Whisper ahora?"; then
    info "Descargando modelo $WHISPER_CHOICE (puede tardar unos minutos)..."
    source "$PROJECT_DIR/.venv/bin/activate"
    $PYTHON_CMD -c "from faster_whisper import WhisperModel; WhisperModel('$WHISPER_CHOICE')" 2>&1 | tail -5 || {
        warn "No se pudo descargar el modelo ahora. Se descargará al primer uso."
    }
    info "Modelo descargado."
fi

# ============================================================================
# 10. Servicio systemd (opcional)
# ============================================================================
section "10/10 — Servicio systemd (opcional)"

echo "  Un servicio systemd permite que el asistente se ejecute"
echo "  automáticamente al arrancar el sistema y se reinicie si falla."
echo ""

if confirm "¿Instalar servicio systemd?"; then
    SERVICE_FILE="$PROJECT_DIR/systemd/ai-assistant.service"

    if [[ ! -f "$SERVICE_FILE" ]]; then
        error "Archivo de servicio no encontrado: $SERVICE_FILE"
    else
        # Adaptar rutas al directorio actual
        TEMP_SERVICE="/tmp/ai-assistant.service"
        sed "s|/opt/ai-assistant|$PROJECT_DIR|g" "$SERVICE_FILE" > "$TEMP_SERVICE"

        # Usar el usuario actual en lugar de ai-assistant
        CURRENT_USER=$(whoami)
        CURRENT_GROUP=$(id -gn)
        sed -i "s|^User=.*|User=$CURRENT_USER|" "$TEMP_SERVICE"
        sed -i "s|^Group=.*|Group=$CURRENT_GROUP|" "$TEMP_SERVICE"

        # Usar el Python del venv
        sed -i "s|^ExecStart=.*|ExecStart=$PROJECT_DIR/.venv/bin/python -m src.main|" "$TEMP_SERVICE"

        sudo cp "$TEMP_SERVICE" /etc/systemd/system/ai-assistant.service
        sudo systemctl daemon-reload
        sudo systemctl enable ai-assistant
        info "Servicio systemd instalado y habilitado."
        echo ""
        echo "  Comandos útiles:"
        echo "    sudo systemctl start ai-assistant    # Iniciar"
        echo "    sudo systemctl stop ai-assistant     # Detener"
        echo "    sudo systemctl restart ai-assistant  # Reiniciar"
        echo "    sudo systemctl status ai-assistant   # Ver estado"
        echo "    journalctl -u ai-assistant -f        # Ver logs en vivo"
    fi
else
    info "Servicio systemd omitido. Puedes instalarlo después ejecutando install.sh de nuevo."
fi

# ============================================================================
# Resumen final
# ============================================================================
echo ""
echo -e "${GREEN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                 ¡Instalación completada!                     ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""
echo -e "${BOLD}Próximos pasos:${NC}"
echo ""
echo "  1. Verifica tu archivo .env:"
echo "     ${BLUE}cat .env${NC}"
echo ""
echo "  2. Activa el entorno virtual:"
echo "     ${BLUE}source .venv/bin/activate${NC}"
echo ""
echo "  3. Arranca el asistente:"
echo "     ${BLUE}python -m src.main${NC}"
echo ""
echo "  4. Abre tu bot en Telegram y envía: ${BOLD}hola${NC}"
echo ""
echo "  Para más información:"
echo "     ${BLUE}cat README.md${NC}"
echo "     ${BLUE}cat docs/TELEGRAM_SETUP.md${NC}"
echo ""
echo -e "${GREEN}¡Listo! Tu asistente te espera.${NC}"
