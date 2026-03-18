#!/bin/bash
set -e

# ============================================================================
# Personal AI Assistant — Instalador Interactivo v2.0
# ============================================================================
# Instalador guiado para Linux/macOS.
# Configura dependencias, canal de mensajería, audio y seguridad.
# Idempotente: seguro de ejecutar múltiples veces.
# ============================================================================

# --- Colores y estilos ------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# --- Helpers ----------------------------------------------------------------
info()    { echo -e "  ${GREEN}✅${NC} $1"; }
warn()    { echo -e "  ${YELLOW}⚠️${NC}  $1"; }
error()   { echo -e "  ${RED}❌${NC} $1"; }
working() { echo -e "  ${CYAN}⏳${NC} $1"; }
ask()     { echo -en "  ${MAGENTA}👉${NC} $1"; }

divider() { echo -e "  ${DIM}─────────────────────────────────────────────────────────${NC}"; }

confirm() {
    ask "$1 [S/n]: "
    read -r resp
    [[ -z "$resp" || "$resp" =~ ^[sSyY]$ ]]
}

step_header() {
    local step_num="$1"
    local step_title="$2"
    echo ""
    echo -e "  ${CYAN}${BOLD}═══════════════════════════════════════════════════════════${NC}"
    echo -e "  ${CYAN}${BOLD}  PASO ${step_num} de 10 — ${step_title}${NC}"
    echo -e "  ${CYAN}${BOLD}═══════════════════════════════════════════════════════════${NC}"
    echo ""
}

step_done() {
    echo ""
    echo -e "  ${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  ${GREEN}✅ Paso $1 completado — $2${NC}"
    echo ""
}

clear_line() { printf "\r\033[K"; }

# Portable sed -i (macOS requires '' argument, Linux doesn't)
_sed_i() {
    if [[ "$(uname)" == "Darwin" ]]; then
        sed -i '' "$@"
    else
        sed -i "$@"
    fi
}

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"
ENV_FILE="$PROJECT_DIR/.env"

# ============================================================================
# PANTALLA DE BIENVENIDA
# ============================================================================
clear 2>/dev/null || true
echo ""
echo -e "${CYAN}"
echo "  ╔══════════════════════════════════════════════════════════════╗"
echo "  ║                                                              ║"
echo "  ║        🤖 Personal AI Assistant — Instalador v2.0            ║"
echo "  ║                                                              ║"
echo "  ║   Tu propio asistente de IA personal, accesible desde        ║"
echo "  ║   Telegram o WhatsApp, 24/7, desde cualquier parte.          ║"
echo "  ║                                                              ║"
echo "  ╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""
echo -e "  ${BOLD}¿Qué hace este instalador?${NC}"
echo -e "  Configura todo lo necesario para que tengas un asistente de IA"
echo -e "  privado que responde por Telegram o WhatsApp."
echo ""
echo -e "  ${DIM}• No necesitas experiencia técnica — te guiamos en todo${NC}"
echo -e "  ${DIM}• Si algo falla, te explicamos cómo resolverlo${NC}"
echo -e "  ${DIM}• Tiempo estimado: 5-10 minutos${NC}"
echo -e "  ${DIM}• Directorio: ${PROJECT_DIR}${NC}"
echo ""
divider
ask "Presiona ${BOLD}Enter${NC} para comenzar... "
read -r

# ============================================================================
# PASO 1/10 — Verificación del sistema
# ============================================================================
step_header "1" "Verificando tu sistema"

echo -e "  ${DIM}Vamos a revisar que tu computadora tenga todo lo necesario.${NC}"
echo -e "  ${DIM}Si falta algo, te ayudamos a instalarlo.${NC}"
echo ""

# --- Python 3.12+ ---
working "Buscando Python 3.12 o superior..."
sleep 0.5

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
    echo ""
    echo -e "  ${BOLD}¿Qué es Python?${NC}"
    echo -e "  Es el lenguaje de programación que usa tu asistente."
    echo -e "  Necesitas la versión 3.12 o superior."
    echo ""
    echo -e "  ${BOLD}¿Cómo instalarlo?${NC}"
    echo ""
    if command -v brew &>/dev/null; then
        echo -e "  ${CYAN}macOS (Homebrew):${NC}"
        echo -e "    ${CYAN}brew install python@3.12${NC}"
    elif command -v apt &>/dev/null; then
        echo -e "  ${CYAN}Ubuntu/Debian:${NC}"
        echo -e "    ${CYAN}sudo apt update && sudo apt install -y python3.12 python3.12-venv${NC}"
    elif command -v dnf &>/dev/null; then
        echo -e "  ${CYAN}Fedora/RHEL:${NC}"
        echo -e "    ${CYAN}sudo dnf install -y python3.12${NC}"
    elif command -v pacman &>/dev/null; then
        echo -e "  ${CYAN}Arch Linux:${NC}"
        echo -e "    ${CYAN}sudo pacman -S python${NC}"
    else
        echo -e "  Instala Python 3.12+ desde: ${CYAN}https://www.python.org/downloads/${NC}"
    fi
    echo ""
    echo -e "  Después de instalarlo, vuelve a ejecutar este instalador."
    exit 1
fi
info "Python encontrado: ${BOLD}$PYTHON_CMD ($($PYTHON_CMD --version))${NC}"

# --- ffmpeg ---
working "Buscando ffmpeg (procesamiento de audio)..."
sleep 0.3

if command -v ffmpeg &>/dev/null; then
    info "ffmpeg instalado: ${DIM}$(ffmpeg -version 2>&1 | head -1 | cut -d' ' -f1-3)${NC}"
else
    echo ""
    warn "ffmpeg no encontrado."
    echo ""
    echo -e "  ${BOLD}¿Qué es ffmpeg?${NC}"
    echo -e "  Es una herramienta para procesar audio y video."
    echo -e "  Tu asistente la necesita para entender mensajes de voz."
    echo ""
    if confirm "¿Quieres que lo instale automáticamente?"; then
        working "Instalando ffmpeg (puede pedir tu contraseña)..."
        if command -v brew &>/dev/null; then
            brew install ffmpeg > /dev/null 2>&1
        elif command -v apt &>/dev/null; then
            sudo apt update -qq > /dev/null 2>&1 && sudo apt install -y -qq ffmpeg > /dev/null 2>&1
        elif command -v dnf &>/dev/null; then
            sudo dnf install -y ffmpeg-free > /dev/null 2>&1
        elif command -v pacman &>/dev/null; then
            sudo pacman -S --noconfirm ffmpeg > /dev/null 2>&1
        else
            error "No se detectó un gestor de paquetes compatible."
            echo -e "  Instala ffmpeg manualmente desde: ${CYAN}https://ffmpeg.org/download.html${NC}"
        fi
        if command -v ffmpeg &>/dev/null; then
            info "ffmpeg instalado correctamente."
        else
            warn "No se pudo instalar ffmpeg. Los mensajes de voz no funcionarán."
        fi
    else
        warn "ffmpeg no instalado. Los mensajes de voz no funcionarán."
        echo -e "  Instálalo después con tu gestor de paquetes (apt, brew, dnf, pacman)."
    fi
fi

# --- bubblewrap ---
working "Buscando bubblewrap (seguridad/sandbox)..."
sleep 0.3

if command -v bwrap &>/dev/null; then
    info "bubblewrap instalado (sandbox de seguridad activo)"
else
    echo ""
    warn "bubblewrap no encontrado."
    echo ""
    echo -e "  ${BOLD}¿Qué es bubblewrap?${NC}"
    echo -e "  Es una herramienta de seguridad que ejecuta comandos en un"
    echo -e "  entorno aislado (sandbox). Protege tu sistema si el asistente"
    echo -e "  ejecuta algo potencialmente peligroso."
    echo ""
    if confirm "¿Quieres que lo instale? (recomendado)"; then
        working "Instalando bubblewrap..."
        sudo apt update -qq > /dev/null 2>&1 && sudo apt install -y -qq bubblewrap > /dev/null 2>&1
        info "bubblewrap instalado correctamente."
    else
        warn "Sin bubblewrap los comandos se ejecutarán SIN aislamiento."
        echo -e "  ${DIM}Puedes instalarlo después: sudo apt install bubblewrap${NC}"
    fi
fi

step_done "1" "Sistema verificado"

# ============================================================================
# PASO 2/10 — Claude Code CLI
# ============================================================================
step_header "2" "Claude Code (el cerebro de tu asistente)"

echo -e "  ${DIM}Claude Code es la inteligencia artificial que le da vida${NC}"
echo -e "  ${DIM}a tu asistente. Sin él, no puede pensar ni responder.${NC}"
echo -e "  ${DIM}Necesitas una suscripción de Claude Pro o Max.${NC}"
echo ""

working "Buscando Claude Code CLI..."
sleep 0.5

if command -v claude &>/dev/null; then
    CLAUDE_VER=$(claude --version 2>/dev/null | head -1 || echo "desconocida")
    info "Claude Code CLI encontrado: ${BOLD}${CLAUDE_VER}${NC}"
    echo ""
    echo -e "  ${DIM}Para verificar que está autenticado, después de la${NC}"
    echo -e "  ${DIM}instalación puedes ejecutar: ${CYAN}claude${NC}"
    echo -e "  ${DIM}Si no está autenticado, se abrirá tu navegador.${NC}"
    echo ""
    info "Claude Code listo."
else
    echo ""
    error "Claude Code CLI no está instalado."
    echo ""
    echo -e "  ┌─────────────────────────────────────────────────────────┐"
    echo -e "  │                                                         │"
    echo -e "  │  ${BOLD}¿Cómo instalar Claude Code?${NC}                           │"
    echo -e "  │                                                         │"
    echo -e "  │  Si tienes npm/Node.js instalado, ejecuta:              │"
    echo -e "  │                                                         │"
    echo -e "  │    ${CYAN}npm install -g @anthropic-ai/claude-code${NC}              │"
    echo -e "  │                                                         │"
    echo -e "  │  Después ábrelo para autenticarte:                      │"
    echo -e "  │                                                         │"
    echo -e "  │    ${CYAN}claude${NC}                                                │"
    echo -e "  │    (Se abrirá tu navegador para iniciar sesión)          │"
    echo -e "  │                                                         │"
    echo -e "  │  ${DIM}Más info: https://docs.anthropic.com/en/docs/claude-code${NC} │"
    echo -e "  │                                                         │"
    echo -e "  └─────────────────────────────────────────────────────────┘"
    echo ""

    if confirm "¿Ya lo instalaste y quieres reintentar la verificación?"; then
        # Intentar buscar en rutas comunes
        for path in "$HOME/.npm-global/bin/claude" "$HOME/.local/bin/claude" "/usr/local/bin/claude"; do
            if [[ -x "$path" ]]; then
                export PATH="$(dirname "$path"):$PATH"
                break
            fi
        done
        if command -v claude &>/dev/null; then
            info "Claude Code CLI encontrado."
        else
            warn "Todavía no se detecta Claude Code."
            echo -e "  ${DIM}Puedes continuar e instalarlo después, pero el asistente${NC}"
            echo -e "  ${DIM}no funcionará hasta que esté instalado y autenticado.${NC}"
            echo ""
            if ! confirm "¿Continuar sin Claude Code?"; then
                exit 1
            fi
        fi
    else
        if ! confirm "¿Continuar sin Claude Code? (podrás instalarlo después)"; then
            exit 1
        fi
        warn "Continuando sin Claude Code. Recuerda instalarlo antes de usar el asistente."
    fi
fi

step_done "2" "Claude Code verificado"

# ============================================================================
# PASO 3/10 — Elegir canal de mensajería
# ============================================================================
step_header "3" "Elige tu canal de mensajería"

echo -e "  ${DIM}¿Cómo quieres hablar con tu asistente?${NC}"
echo ""
echo -e "  ┌─────────────────────────────────────────────────────────┐"
echo -e "  │                                                         │"
echo -e "  │  ${GREEN}1)${NC} 📱 ${BOLD}Telegram${NC} ${GREEN}(RECOMENDADO)${NC}                          │"
echo -e "  │     ${DIM}• Gratis, sin riesgo, setup en 2 minutos${NC}           │"
echo -e "  │     ${DIM}• Texto, audio, archivos — todo funciona${NC}           │"
echo -e "  │     ${DIM}• La opción más fácil y segura${NC}                     │"
echo -e "  │                                                         │"
echo -e "  │  ${YELLOW}2)${NC} 💬 ${BOLD}WhatsApp (Baileys — no oficial)${NC}                   │"
echo -e "  │     ${DIM}• Necesitas un número virtual (~\$2/mes)${NC}            │"
echo -e "  │     ${DIM}• Riesgo medio de ban del número${NC}                   │"
echo -e "  │     ${DIM}• NUNCA uses tu número personal${NC}                    │"
echo -e "  │                                                         │"
echo -e "  │  ${BLUE}3)${NC} 💼 ${BOLD}WhatsApp Business API (oficial)${NC}                   │"
echo -e "  │     ${DIM}• Sin riesgo de ban, API oficial de Meta${NC}           │"
echo -e "  │     ${DIM}• Requiere cuenta de negocio (~\$5-20/mes)${NC}         │"
echo -e "  │     ${DIM}• Proceso de verificación de Meta${NC}                  │"
echo -e "  │                                                         │"
echo -e "  │  ${MAGENTA}4)${NC} 🔧 ${BOLD}Todos los anteriores${NC}                              │"
echo -e "  │                                                         │"
echo -e "  └─────────────────────────────────────────────────────────┘"
echo ""
ask "Tu elección [${BOLD}1${NC}]: "
read -r CHANNEL_CHOICE
CHANNEL_CHOICE="${CHANNEL_CHOICE:-1}"

while [[ ! "$CHANNEL_CHOICE" =~ ^[1234]$ ]]; do
    error "Opción no válida. Escribe 1, 2, 3 o 4."
    ask "Tu elección [${BOLD}1${NC}]: "
    read -r CHANNEL_CHOICE
    CHANNEL_CHOICE="${CHANNEL_CHOICE:-1}"
done

step_done "3" "Canal seleccionado"

# ============================================================================
# PASO 4/10 — Configuración del canal
# ============================================================================
step_header "4" "Configuración del canal de mensajería"

# --- Preparar .env ---
if [[ -f "$ENV_FILE" ]]; then
    warn "Ya existe un archivo de configuración (.env)."
    echo ""
    if confirm "¿Quieres reconfigurarlo? (se guarda backup automático)"; then
        BACKUP_NAME="$ENV_FILE.backup.$(date +%Y%m%d_%H%M%S)"
        cp "$ENV_FILE" "$BACKUP_NAME"
        info "Backup guardado: ${DIM}$(basename "$BACKUP_NAME")${NC}"
        cp "$PROJECT_DIR/.env.example" "$ENV_FILE"
    else
        info "Manteniendo configuración existente."
        SKIP_ENV=true
    fi
else
    cp "$PROJECT_DIR/.env.example" "$ENV_FILE"
fi

BOT_USERNAME=""

if [[ "${SKIP_ENV:-}" != "true" ]]; then

    # ========================================================================
    # TELEGRAM
    # ========================================================================
    if [[ "$CHANNEL_CHOICE" == "1" || "$CHANNEL_CHOICE" == "4" ]]; then
        echo ""
        echo -e "  ${CYAN}${BOLD}═══ Configuración de Telegram ═══${NC}"
        echo ""
        echo -e "  Vamos a crear tu bot en Telegram. ${GREEN}Es gratis${NC} y toma 2 minutos."
        echo ""

        # --- PASO A: Crear el bot y obtener token ---
        echo -e "  ${BOLD}📋 PASO 1 de 3: Crear el bot${NC}"
        divider
        echo ""
        echo -e "  Sigue estos pasos ${BOLD}exactamente${NC}:"
        echo ""
        echo -e "  ${CYAN}1.${NC} Abre Telegram en tu teléfono o computadora"
        echo -e "  ${CYAN}2.${NC} En el buscador de arriba, escribe: ${BOLD}@BotFather${NC}"
        echo -e "  ${CYAN}3.${NC} Abre el chat con ${BOLD}BotFather${NC} (tiene una ✓ azul de verificado)"
        echo -e "  ${CYAN}4.${NC} Envíale este mensaje exacto: ${BOLD}/newbot${NC}"
        echo -e "  ${CYAN}5.${NC} Te preguntará el ${BOLD}nombre${NC} de tu bot"
        echo -e "     → Escribe lo que quieras (ejemplo: ${DIM}\"Mi Asistente IA\"${NC})"
        echo -e "  ${CYAN}6.${NC} Te pedirá un ${BOLD}username${NC} para el bot"
        echo -e "     → Debe terminar en ${BOLD}_bot${NC} (ejemplo: ${DIM}\"mi_asistente_ia_bot\"${NC})"
        echo -e "  ${CYAN}7.${NC} BotFather te dará un ${BOLD}TOKEN${NC} — se ve así:"
        echo -e "     ${DIM}7123456789:AAHx_ejemplo_de_token_aqui_xxxxx${NC}"
        echo ""

        TG_TOKEN=""
        while true; do
            ask "Pega el token aquí: "
            read -r TG_TOKEN

            if [[ -z "$TG_TOKEN" ]]; then
                error "No escribiste nada. Necesitas pegar el token que te dio BotFather."
                continue
            fi

            # Validar formato básico
            if [[ ! "$TG_TOKEN" =~ ^[0-9]+:[A-Za-z0-9_-]+$ ]]; then
                error "Ese token no tiene el formato correcto."
                echo -e "  ${DIM}Debería verse como: 7123456789:AAHxxxxxxxxxxxxxxxxxxx${NC}"
                echo -e "  ${DIM}Asegúrate de copiar el token COMPLETO que te dio BotFather.${NC}"
                echo ""
                continue
            fi

            # Validar con la API de Telegram
            working "Verificando token con Telegram..."
            RESULT=$(curl -s --connect-timeout 10 "https://api.telegram.org/bot${TG_TOKEN}/getMe" 2>/dev/null || echo "")

            if [[ -z "$RESULT" ]]; then
                error "No se pudo conectar con Telegram. ¿Tienes conexión a internet?"
                echo ""
                if confirm "¿Quieres reintentar?"; then
                    continue
                else
                    warn "Continuando sin verificar. Puedes corregir el token en .env después."
                    break
                fi
            fi

            if echo "$RESULT" | grep -q '"ok":true'; then
                BOT_NAME=$(echo "$RESULT" | grep -o '"first_name":"[^"]*"' | cut -d'"' -f4)
                BOT_USERNAME=$(echo "$RESULT" | grep -o '"username":"[^"]*"' | cut -d'"' -f4)
                echo ""
                info "Token válido ✨"
                echo -e "     ${DIM}Nombre del bot: ${BOT_NAME}${NC}"
                echo -e "     ${DIM}Username: @${BOT_USERNAME}${NC}"
                _sed_i "s|^TELEGRAM_BOT_TOKEN=.*|TELEGRAM_BOT_TOKEN=$TG_TOKEN|" "$ENV_FILE"
                break
            else
                ERROR_DESC=$(echo "$RESULT" | grep -o '"description":"[^"]*"' | cut -d'"' -f4)
                error "Token inválido."
                if [[ -n "$ERROR_DESC" ]]; then
                    echo -e "  ${DIM}Telegram dice: ${ERROR_DESC}${NC}"
                fi
                echo -e "  ${DIM}Verifica que copiaste el token completo y correctamente.${NC}"
                echo -e "  ${DIM}Puedes pedirle otro a @BotFather con el comando /token${NC}"
                echo ""
                continue
            fi
        done

        # --- PASO B: Obtener Chat ID ---
        echo ""
        echo -e "  ${BOLD}📋 PASO 2 de 3: Obtener tu ID de Telegram${NC}"
        divider
        echo ""
        echo -e "  Tu ID es un número único que identifica tu cuenta."
        echo -e "  Solo tú podrás hablar con el bot (seguridad)."
        echo ""
        echo -e "  ${CYAN}1.${NC} Busca en Telegram: ${BOLD}@userinfobot${NC}"
        echo -e "  ${CYAN}2.${NC} Ábrelo y envíale cualquier mensaje (por ejemplo: ${DIM}hola${NC})"
        echo -e "  ${CYAN}3.${NC} Te responderá con tu ${BOLD}ID${NC} — es un número como: ${DIM}123456789${NC}"
        echo ""

        TG_CHAT_ID=""
        while true; do
            ask "Pega tu ID aquí: "
            read -r TG_CHAT_ID

            if [[ -z "$TG_CHAT_ID" ]]; then
                error "No escribiste nada."
                continue
            fi

            if [[ ! "$TG_CHAT_ID" =~ ^-?[0-9]+$ ]]; then
                error "El ID debe ser un número (ejemplo: 123456789)"
                echo -e "  ${DIM}Lo que escribiste no parece un ID válido.${NC}"
                echo -e "  ${DIM}Ve a @userinfobot en Telegram y copia solo el número.${NC}"
                echo ""
                continue
            fi

            _sed_i "s|^AUTHORIZED_CHAT_ID=.*|AUTHORIZED_CHAT_ID=$TG_CHAT_ID|" "$ENV_FILE"
            info "ID configurado: ${BOLD}$TG_CHAT_ID${NC}"
            break
        done

        # --- PASO C: Verificación final ---
        echo ""
        echo -e "  ${BOLD}📋 PASO 3 de 3: Verificación final${NC}"
        divider
        echo ""

        if [[ -n "${TG_TOKEN:-}" ]] && [[ -n "${TG_CHAT_ID:-}" ]]; then
            info "Token válido — Bot: ${BOLD}@${BOT_USERNAME:-tu_bot}${NC}"
            info "Chat ID configurado: ${BOLD}$TG_CHAT_ID${NC}"

            # Enviar mensaje de prueba
            working "Enviando mensaje de prueba a tu Telegram..."
            TEST_MSG="🤖 ¡Hola! Soy tu asistente de IA. La instalación va por buen camino. Si ves este mensaje, ¡todo funciona perfectamente!"
            SEND_RESULT=$(curl -s --connect-timeout 10 \
                -X POST "https://api.telegram.org/bot${TG_TOKEN}/sendMessage" \
                -d "chat_id=${TG_CHAT_ID}" \
                -d "text=${TEST_MSG}" 2>/dev/null || echo "")

            if echo "$SEND_RESULT" | grep -q '"ok":true'; then
                info "Mensaje de prueba enviado. ${BOLD}¡Revisa tu Telegram!${NC} 🎉"
            else
                warn "No se pudo enviar el mensaje de prueba."
                echo -e "  ${DIM}Esto puede pasar si nunca le has enviado un mensaje al bot.${NC}"
                echo -e "  ${DIM}Ve a Telegram, busca @${BOT_USERNAME:-tu_bot} y envíale /start${NC}"
                echo -e "  ${DIM}No te preocupes, funcionará cuando arranques el asistente.${NC}"
            fi

            info "Conexión con Telegram configurada ✨"
        fi
    fi

    # ========================================================================
    # WHATSAPP BAILEYS
    # ========================================================================
    if [[ "$CHANNEL_CHOICE" == "2" || "$CHANNEL_CHOICE" == "4" ]]; then
        echo ""
        echo -e "  ${CYAN}${BOLD}═══ Configuración de WhatsApp (Baileys) ═══${NC}"
        echo ""
        echo -e "  ${RED}${BOLD}⚠️  ADVERTENCIA IMPORTANTE ⚠️${NC}"
        echo -e "  ${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo ""
        echo -e "  ${RED}Baileys usa el protocolo NO oficial de WhatsApp Web.${NC}"
        echo -e "  ${RED}Meta (dueños de WhatsApp) PUEDEN BANEAR permanentemente${NC}"
        echo -e "  ${RED}el número que uses.${NC}"
        echo ""
        echo -e "  ${BOLD}${RED}🚫 NUNCA uses tu número personal de WhatsApp.${NC}"
        echo ""
        echo -e "  ${BOLD}Opciones de números virtuales baratos:${NC}"
        echo -e "  • ${CYAN}TextNow${NC} — Gratis (solo números USA)"
        echo -e "  • ${CYAN}Google Voice${NC} — Gratis (solo USA, necesitas invitación)"
        echo -e "  • ${CYAN}Twilio${NC} — ~\$1-2/mes (funciona en todo el mundo)"
        echo -e "  • Tarjeta SIM prepago barata dedicada"
        echo ""

        if confirm "¿Entiendes el riesgo y quieres continuar?"; then
            # Verificar Node.js
            if command -v node &>/dev/null; then
                NODE_VER=$(node -v)
                info "Node.js encontrado: $NODE_VER"
            else
                warn "Node.js no encontrado. Es necesario para el bridge de WhatsApp."
                echo -e "  ${DIM}Instala Node.js 20+: https://nodejs.org/${NC}"
            fi

            # Instalar dependencias del bridge
            if [[ -d "$PROJECT_DIR/whatsapp-bridge" ]]; then
                working "Instalando dependencias del bridge de WhatsApp..."
                (cd "$PROJECT_DIR/whatsapp-bridge" && npm install --silent 2>&1 | tail -3)
                info "Dependencias del bridge instaladas."
            else
                warn "Directorio whatsapp-bridge/ no encontrado."
                echo -e "  ${DIM}Se creará cuando configures el bridge.${NC}"
            fi

            echo ""
            ask "Número virtual para WhatsApp (con código de país, ej: +1234567890): "
            read -r WA_NUMBER
            if [[ -n "$WA_NUMBER" ]]; then
                if ! grep -q "^WHATSAPP_NUMBER=" "$ENV_FILE"; then
                    {
                        echo ""
                        echo "# --- WhatsApp Baileys ---"
                        echo "WHATSAPP_NUMBER=$WA_NUMBER"
                        echo "WHATSAPP_BRIDGE_URL=http://localhost:3001"
                    } >> "$ENV_FILE"
                fi
                info "Número WhatsApp configurado."
            fi

            echo ""
            echo -e "  ${DIM}Después de la instalación, ejecuta:${NC}"
            echo -e "    ${CYAN}cd whatsapp-bridge && npm start${NC}"
            echo -e "  ${DIM}Escanea el QR con el WhatsApp del número virtual.${NC}"
        else
            info "WhatsApp Baileys omitido."
        fi
    fi

    # ========================================================================
    # WHATSAPP BUSINESS API
    # ========================================================================
    if [[ "$CHANNEL_CHOICE" == "3" || "$CHANNEL_CHOICE" == "4" ]]; then
        echo ""
        echo -e "  ${CYAN}${BOLD}═══ Configuración de WhatsApp Business API ═══${NC}"
        echo ""
        echo -e "  ${DIM}Esta es la opción oficial de Meta. Sin riesgo de ban,${NC}"
        echo -e "  ${DIM}pero requiere una cuenta de negocio verificada.${NC}"
        echo ""
        echo -e "  ${BOLD}Necesitas:${NC}"
        echo -e "  • Cuenta en ${CYAN}Meta Business Suite${NC} (business.facebook.com)"
        echo -e "  • App registrada en ${CYAN}developers.facebook.com${NC}"
        echo -e "  • Acceso a la ${CYAN}Cloud API de WhatsApp${NC}"
        echo ""
        echo -e "  ${DIM}Más info: https://developers.facebook.com/docs/whatsapp/cloud-api${NC}"
        echo ""

        ask "WhatsApp Business Phone Number ID: "
        read -r WA_PHONE_ID
        ask "WhatsApp Business API Token: "
        read -r WA_BIZ_TOKEN
        echo ""
        echo -e "  ${DIM}El Verify Token es una contraseña que tú inventas.${NC}"
        echo -e "  ${DIM}La usarás al configurar el webhook en Meta.${NC}"
        ask "Webhook Verify Token (inventa uno): "
        read -r WA_VERIFY

        if [[ -n "$WA_PHONE_ID" ]]; then
            if ! grep -q "^WHATSAPP_PHONE_NUMBER_ID=" "$ENV_FILE"; then
                {
                    echo ""
                    echo "# --- WhatsApp Business API ---"
                    echo "WHATSAPP_PHONE_NUMBER_ID=$WA_PHONE_ID"
                    echo "WHATSAPP_BUSINESS_TOKEN=$WA_BIZ_TOKEN"
                    echo "WHATSAPP_VERIFY_TOKEN=$WA_VERIFY"
                } >> "$ENV_FILE"
            fi
            info "WhatsApp Business API configurado."
        fi
    fi

fi # end SKIP_ENV for channel config

step_done "4" "Canal configurado"

# ============================================================================
# PASO 5/10 — Entorno virtual de Python
# ============================================================================
step_header "5" "Preparando entorno de Python"

echo -e "  ${DIM}Creando un espacio aislado para tu asistente.${NC}"
echo -e "  ${DIM}Esto evita conflictos con otros programas de tu sistema.${NC}"
echo ""

if [[ -d "$PROJECT_DIR/.venv" ]]; then
    info "Entorno virtual ya existe — reutilizando."
    source "$PROJECT_DIR/.venv/bin/activate"
else
    working "Creando entorno virtual con $PYTHON_CMD..."
    $PYTHON_CMD -m venv "$PROJECT_DIR/.venv"
    source "$PROJECT_DIR/.venv/bin/activate"
    info "Entorno virtual creado en .venv/"
fi

working "Actualizando gestor de paquetes (pip)..."
pip install --upgrade pip --quiet 2>/dev/null
info "pip actualizado."

step_done "5" "Entorno preparado"

# ============================================================================
# PASO 6/10 — Dependencias de Python
# ============================================================================
step_header "6" "Instalando dependencias"

echo -e "  ${DIM}Instalando los paquetes que necesita tu asistente.${NC}"
echo -e "  ${DIM}Esto puede tardar 1-2 minutos ☕${NC}"
echo ""

working "Instalando paquetes..."

# Instalar con output en vivo pero filtrado
pip install -e ".[dev]" 2>&1 | while IFS= read -r line; do
    if echo "$line" | grep -qE "^(Collecting|Downloading|Installing|Building)"; then
        pkg_name=$(echo "$line" | sed 's/^[^ ]* //' | cut -d' ' -f1 | cut -d'>' -f1 | cut -d'=' -f1 | cut -d'<' -f1 | head -c 40)
        clear_line
        printf "  ${CYAN}📦${NC} %s..." "$pkg_name"
    fi
done
clear_line

info "Todas las dependencias instaladas correctamente."

step_done "6" "Dependencias instaladas"

# ============================================================================
# PASO 7/10 — Modelo de audio (Whisper)
# ============================================================================
step_header "7" "Configuración de audio"

echo -e "  ${DIM}Tu asistente puede escuchar mensajes de voz y responder hablando.${NC}"
echo -e "  ${DIM}Para eso necesita un modelo de reconocimiento de voz (Whisper).${NC}"
echo ""
echo -e "  ┌─────────────────────────────────────────────────────────┐"
echo -e "  │  ${BOLD}Modelos disponibles:${NC}                                    │"
echo -e "  │                                                         │"
echo -e "  │  ${GREEN}1)${NC} 🚀 ${BOLD}Rápido${NC} (tiny) — 75 MB                            │"
echo -e "  │     ${DIM}Menos preciso pero responde al instante${NC}              │"
echo -e "  │     ${DIM}Ideal si tu PC tiene poca RAM${NC}                        │"
echo -e "  │                                                         │"
echo -e "  │  ${GREEN}2)${NC} ⚡ ${BOLD}Equilibrado${NC} (small) — 500 MB ${GREEN}[RECOMENDADO]${NC}     │"
echo -e "  │     ${DIM}Buena precisión y velocidad${NC}                          │"
echo -e "  │     ${DIM}Funciona bien en la mayoría de computadoras${NC}          │"
echo -e "  │                                                         │"
echo -e "  │  ${GREEN}3)${NC} 🎯 ${BOLD}Preciso${NC} (medium) — 1.5 GB                        │"
echo -e "  │     ${DIM}Muy buena precisión, un poco más lento${NC}               │"
echo -e "  │     ${DIM}Necesita al menos 4 GB de RAM libres${NC}                 │"
echo -e "  │                                                         │"
echo -e "  │  ${GREEN}4)${NC} 🏆 ${BOLD}Máximo${NC} (large-v3) — 3 GB                         │"
echo -e "  │     ${DIM}La mejor precisión posible${NC}                           │"
echo -e "  │     ${DIM}Necesita GPU o mucha RAM (8+ GB libres)${NC}              │"
echo -e "  │                                                         │"
echo -e "  └─────────────────────────────────────────────────────────┘"
echo ""
ask "Tu elección [${BOLD}2${NC}]: "
read -r WHISPER_CHOICE
WHISPER_CHOICE="${WHISPER_CHOICE:-2}"

case "$WHISPER_CHOICE" in
    1|tiny)     WHISPER_MODEL="tiny" ;;
    2|small)    WHISPER_MODEL="small" ;;
    3|medium)   WHISPER_MODEL="medium" ;;
    4|large*)   WHISPER_MODEL="large-v3" ;;
    *)          WHISPER_MODEL="small"; warn "Opción no reconocida, usando 'small' (recomendado)." ;;
esac

if [[ -f "$ENV_FILE" ]]; then
    _sed_i "s|^WHISPER_MODEL=.*|WHISPER_MODEL=$WHISPER_MODEL|" "$ENV_FILE"
fi
info "Modelo configurado: ${BOLD}$WHISPER_MODEL${NC}"

echo ""
echo -e "  ${DIM}El modelo se descarga automáticamente la primera vez${NC}"
echo -e "  ${DIM}que recibas un mensaje de voz.${NC}"
echo ""

if confirm "¿Descargar el modelo ahora? (puede tardar según tu internet)"; then
    echo ""
    working "Descargando modelo '$WHISPER_MODEL'..."
    echo -e "  ${DIM}Esto puede tardar varios minutos dependiendo de tu conexión...${NC}"
    echo ""
    source "$PROJECT_DIR/.venv/bin/activate"
    if $PYTHON_CMD -c "from faster_whisper import WhisperModel; WhisperModel('$WHISPER_MODEL')" 2>&1 | tail -5; then
        info "Modelo descargado y listo. 🎉"
    else
        warn "No se pudo descargar ahora. Se descargará automáticamente al primer uso."
        echo -e "  ${DIM}No te preocupes, funcionará igualmente.${NC}"
    fi
fi

step_done "7" "Audio configurado"

# ============================================================================
# PASO 8/10 — Zona horaria
# ============================================================================
if [[ "${SKIP_ENV:-}" != "true" ]]; then

step_header "8" "Zona horaria"

echo -e "  ${DIM}Tu asistente necesita saber tu zona horaria para${NC}"
echo -e "  ${DIM}recordatorios y tareas programadas.${NC}"
echo ""
echo -e "  ┌─────────────────────────────────────────────────────────┐"
echo -e "  │  ${BOLD}¿Dónde estás ubicado?${NC}                                  │"
echo -e "  │                                                         │"
echo -e "  │  ${GREEN}1)${NC}  🇺🇸 Estados Unidos (Este) — New York, Miami        │"
echo -e "  │  ${GREEN}2)${NC}  🇺🇸 Estados Unidos (Centro) — Chicago, Houston    │"
echo -e "  │  ${GREEN}3)${NC}  🇺🇸 Estados Unidos (Oeste) — Los Angeles, SF      │"
echo -e "  │  ${GREEN}4)${NC}  🇲🇽 México — Ciudad de México, Guadalajara        │"
echo -e "  │  ${GREEN}5)${NC}  🇨🇴 Colombia — Bogotá, Medellín                   │"
echo -e "  │  ${GREEN}6)${NC}  🇪🇸 España — Madrid, Barcelona                    │"
echo -e "  │  ${GREEN}7)${NC}  🇦🇷 Argentina — Buenos Aires                      │"
echo -e "  │  ${GREEN}8)${NC}  🇨🇱 Chile — Santiago                              │"
echo -e "  │  ${GREEN}9)${NC}  🇵🇪 Perú — Lima                                   │"
echo -e "  │  ${GREEN}10)${NC} ✏️  Otra (escribir manualmente)                    │"
echo -e "  │                                                         │"
echo -e "  └─────────────────────────────────────────────────────────┘"
echo ""
ask "Tu elección [${BOLD}1${NC}]: "
read -r TZ_CHOICE
TZ_CHOICE="${TZ_CHOICE:-1}"

case "$TZ_CHOICE" in
    1)  TZ_INPUT="America/New_York" ;;
    2)  TZ_INPUT="America/Chicago" ;;
    3)  TZ_INPUT="America/Los_Angeles" ;;
    4)  TZ_INPUT="America/Mexico_City" ;;
    5)  TZ_INPUT="America/Bogota" ;;
    6)  TZ_INPUT="Europe/Madrid" ;;
    7)  TZ_INPUT="America/Argentina/Buenos_Aires" ;;
    8)  TZ_INPUT="America/Santiago" ;;
    9)  TZ_INPUT="America/Lima" ;;
    10)
        echo ""
        echo -e "  ${DIM}Formato: Continente/Ciudad${NC}"
        echo -e "  ${DIM}Ejemplos: America/Caracas, Europe/London, Asia/Tokyo${NC}"
        echo -e "  ${DIM}Lista completa: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones${NC}"
        echo ""
        ask "Tu zona horaria: "
        read -r TZ_INPUT
        TZ_INPUT="${TZ_INPUT:-America/New_York}"
        ;;
    *)  TZ_INPUT="America/New_York"
        warn "Opción no reconocida, usando America/New_York."
        ;;
esac

_sed_i "s|^TIMEZONE=.*|TIMEZONE=$TZ_INPUT|" "$ENV_FILE"
info "Zona horaria: ${BOLD}$TZ_INPUT${NC}"

step_done "8" "Zona horaria configurada"

# ============================================================================
# PASO 9/10 — Seguridad
# ============================================================================
step_header "9" "Seguridad"

echo -e "  ${DIM}Puedes proteger tu asistente con un PIN de seguridad.${NC}"
echo -e "  ${DIM}Si lo activas, te pedirá el PIN antes de ejecutar${NC}"
echo -e "  ${DIM}operaciones sensibles (borrar archivos, cambiar config, etc.)${NC}"
echo ""
echo -e "  ${DIM}Es opcional pero recomendado si compartes la computadora.${NC}"
echo ""
ask "Escribe un PIN (4-8 dígitos) o presiona ${BOLD}Enter${NC} para omitir: "
read -r SEC_PIN

if [[ -n "$SEC_PIN" ]]; then
    if [[ "$SEC_PIN" =~ ^[0-9]{4,8}$ ]]; then
        _sed_i "s|^SECURITY_PIN=.*|SECURITY_PIN=$SEC_PIN|" "$ENV_FILE"
        info "PIN de seguridad configurado. 🔒"
    else
        warn "El PIN debe ser de 4 a 8 dígitos numéricos."
        ask "Inténtalo de nuevo (o Enter para omitir): "
        read -r SEC_PIN
        if [[ "$SEC_PIN" =~ ^[0-9]{4,8}$ ]]; then
            _sed_i "s|^SECURITY_PIN=.*|SECURITY_PIN=$SEC_PIN|" "$ENV_FILE"
            info "PIN de seguridad configurado. 🔒"
        else
            info "PIN omitido. Puedes configurarlo después en el archivo .env"
        fi
    fi
else
    info "PIN omitido. Puedes agregarlo después en el archivo .env"
fi

echo ""

# Generar clave de cifrado automáticamente
working "Generando clave de cifrado para la base de datos..."
DB_KEY=$($PYTHON_CMD -c "import secrets; print(secrets.token_hex(32))")
_sed_i "s|^DB_ENCRYPTION_KEY=.*|DB_ENCRYPTION_KEY=$DB_KEY|" "$ENV_FILE"
info "Clave de cifrado generada automáticamente. 🔐"
echo -e "  ${DIM}Esta clave protege tus conversaciones y datos almacenados.${NC}"
echo -e "  ${DIM}Se guardó en el archivo .env (no la compartas con nadie).${NC}"

info "Archivo .env configurado correctamente."

step_done "9" "Seguridad configurada"

else
    # Si saltamos la config de .env, marcamos pasos 8-9 como omitidos
    echo ""
    info "Pasos 8-9 omitidos (usando configuración existente)."
    echo ""
fi # end SKIP_ENV for timezone/security

# ============================================================================
# PASO 10/10 — Configuración final
# ============================================================================
step_header "10" "Configuración final"

# --- Crear directorios ---
working "Creando estructura de directorios..."
for dir in data logs skills models data/knowledge data/projects data/daily mcps; do
    mkdir -p "$PROJECT_DIR/$dir"
done

# Security: restrict sensitive directories/files to owner only
chmod 700 "$PROJECT_DIR/data" "$PROJECT_DIR/logs" 2>/dev/null
chmod 600 "$PROJECT_DIR/.env" 2>/dev/null
info "Permisos de seguridad aplicados (data/ y logs/ solo accesibles por ti)"
info "Directorios creados:"
echo -e "    ${DIM}📁 data/           — Tus datos y conversaciones${NC}"
echo -e "    ${DIM}📁 data/knowledge/ — Base de conocimiento${NC}"
echo -e "    ${DIM}📁 logs/           — Registros de actividad${NC}"
echo -e "    ${DIM}📁 skills/         — Habilidades del asistente${NC}"
echo -e "    ${DIM}📁 models/         — Modelos de IA${NC}"

# --- Systemd (opcional) ---
echo ""
echo -e "  ${BOLD}🖥️  Inicio automático (opcional)${NC}"
echo ""
echo -e "  ${DIM}¿Quieres que tu asistente arranque automáticamente${NC}"
echo -e "  ${DIM}cuando enciendes la computadora?${NC}"
echo ""
echo -e "  ${BOLD}¿Qué hace esto?${NC}"
echo -e "  • El asistente se inicia solo al prender tu PC"
echo -e "  • Si se cae por algún error, se reinicia automáticamente"
echo -e "  • Funciona en segundo plano sin que tengas que hacer nada"
echo ""

if confirm "¿Activar inicio automático?"; then

    if [[ "$(uname)" == "Darwin" ]]; then
        # ---- macOS: launchd LaunchAgent ----
        PLIST_SRC="$PROJECT_DIR/launchd/com.personal-ai-assistant.plist"

        if [[ ! -f "$PLIST_SRC" ]]; then
            warn "Archivo plist no encontrado: $PLIST_SRC"
            echo -e "  ${DIM}Puedes configurarlo manualmente después.${NC}"
        else
            working "Configurando LaunchAgent para macOS..."

            PLIST_DEST="$HOME/Library/LaunchAgents/com.personal-ai-assistant.plist"
            mkdir -p "$HOME/Library/LaunchAgents"

            # Generar plist con rutas correctas
            sed "s|/opt/ai-assistant|$PROJECT_DIR|g" "$PLIST_SRC" > "$PLIST_DEST"

            # Cargar el agente (lo activa ahora y al próximo login)
            launchctl unload "$PLIST_DEST" 2>/dev/null || true
            launchctl load -w "$PLIST_DEST"

            info "LaunchAgent instalado y activado."
            echo ""
            echo -e "  ${BOLD}Comandos útiles:${NC}"
            echo -e "    ${CYAN}launchctl start com.personal-ai-assistant${NC}   ← Iniciar"
            echo -e "    ${CYAN}launchctl stop com.personal-ai-assistant${NC}    ← Detener"
            echo -e "    ${CYAN}launchctl unload ~/Library/LaunchAgents/com.personal-ai-assistant.plist${NC} ← Desactivar"
            echo -e "    ${CYAN}tail -f $PROJECT_DIR/logs/launchd-stdout.log${NC} ← Ver logs"
        fi
    else
        # ---- Linux: systemd service ----
        SERVICE_FILE="$PROJECT_DIR/systemd/ai-assistant.service"

        if [[ ! -f "$SERVICE_FILE" ]]; then
            warn "Archivo de servicio no encontrado: $SERVICE_FILE"
            echo -e "  ${DIM}Puedes configurarlo manualmente después.${NC}"
        else
            working "Configurando servicio systemd..."

            TEMP_SERVICE="/tmp/ai-assistant.service"
            sed "s|/opt/ai-assistant|$PROJECT_DIR|g" "$SERVICE_FILE" > "$TEMP_SERVICE"

            CURRENT_USER=$(whoami)
            CURRENT_GROUP=$(id -gn)
            _sed_i "s|^User=.*|User=$CURRENT_USER|" "$TEMP_SERVICE"
            _sed_i "s|^Group=.*|Group=$CURRENT_GROUP|" "$TEMP_SERVICE"
            _sed_i "s|^ExecStart=.*|ExecStart=$PROJECT_DIR/.venv/bin/python -m src.main|" "$TEMP_SERVICE"

            sudo cp "$TEMP_SERVICE" /etc/systemd/system/ai-assistant.service
            sudo systemctl daemon-reload
            sudo systemctl enable ai-assistant
            info "Servicio instalado y habilitado."
            echo ""
            echo -e "  ${BOLD}Comandos útiles:${NC}"
            echo -e "    ${CYAN}sudo systemctl start ai-assistant${NC}    ← Iniciar"
            echo -e "    ${CYAN}sudo systemctl stop ai-assistant${NC}     ← Detener"
            echo -e "    ${CYAN}sudo systemctl restart ai-assistant${NC}  ← Reiniciar"
            echo -e "    ${CYAN}sudo systemctl status ai-assistant${NC}   ← Ver estado"
            echo -e "    ${CYAN}journalctl -u ai-assistant -f${NC}        ← Ver logs en vivo"
        fi
    fi
else
    info "Inicio automático omitido. Puedes configurarlo después."
fi

step_done "10" "Configuración final lista"

# ============================================================================
# PANTALLA FINAL DE ÉXITO
# ============================================================================
sleep 0.5
echo ""
echo -e "${GREEN}"
echo "  ╔══════════════════════════════════════════════════════════════╗"
echo "  ║                                                              ║"
echo "  ║           🎉 ¡Instalación completada con éxito! 🎉          ║"
echo "  ║                                                              ║"
echo "  ╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""
echo -e "  ${BOLD}Tu asistente está listo. Para arrancarlo:${NC}"
echo ""
echo -e "  ┌─────────────────────────────────────────────────────────┐"
echo -e "  │                                                         │"
echo -e "  │   ${CYAN}cd ${PROJECT_DIR}${NC}"
echo -e "  │   ${CYAN}source .venv/bin/activate${NC}"
echo -e "  │   ${CYAN}python -m src.main${NC}"
echo -e "  │                                                         │"
echo -e "  └─────────────────────────────────────────────────────────┘"
echo ""

if [[ "$CHANNEL_CHOICE" == "1" || "$CHANNEL_CHOICE" == "4" ]]; then
    echo -e "  ${BOLD}Después:${NC}"
    if [[ -n "${BOT_USERNAME:-}" ]]; then
        echo -e "  📱 Abre Telegram y busca tu bot: ${BOLD}@${BOT_USERNAME}${NC}"
    else
        echo -e "  📱 Abre Telegram y busca tu bot"
    fi
    echo -e "  💬 Envíale: ${BOLD}hola${NC}"
    echo -e "  🤖 El asistente te responderá y te guiará desde ahí."
    echo ""
fi

if [[ "$CHANNEL_CHOICE" == "2" || "$CHANNEL_CHOICE" == "4" ]]; then
    echo -e "  ${BOLD}Para WhatsApp Baileys:${NC}"
    echo -e "  Primero inicia el bridge:"
    echo -e "    ${CYAN}cd whatsapp-bridge && npm start${NC}"
    echo -e "  Escanea el QR y después arranca el asistente."
    echo ""
fi

divider
echo ""
echo -e "  ${BOLD}Resumen de lo instalado:${NC}"
echo -e "    ✅ Python: $($PYTHON_CMD --version 2>&1)"
echo -e "    ✅ Entorno virtual: .venv/"
echo -e "    ✅ Dependencias: instaladas"
if command -v ffmpeg &>/dev/null; then
    echo -e "    ✅ ffmpeg: instalado"
fi
if command -v bwrap &>/dev/null; then
    echo -e "    ✅ bubblewrap: sandbox activo"
fi
if command -v claude &>/dev/null; then
    echo -e "    ✅ Claude Code: instalado"
fi
echo -e "    ✅ Modelo de voz: ${WHISPER_MODEL:-small}"
if [[ -n "${TZ_INPUT:-}" ]]; then
    echo -e "    ✅ Zona horaria: $TZ_INPUT"
fi
echo ""
echo -e "  ${DIM}¿Necesitas ayuda? Revisa:${NC}"
echo -e "    ${DIM}cat README.md${NC}"
echo -e "    ${DIM}ls docs/${NC}"
echo ""
echo -e "  ${GREEN}${BOLD}¡Listo! Tu asistente te espera. 🚀${NC}"
echo ""
