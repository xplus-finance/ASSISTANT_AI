# Paso a Paso — Poner en Marcha tu Asistente Personal IA

## Estado actual
- ✅ Código completo (60 archivos, 11,000+ líneas)
- ✅ Dependencias Python instaladas
- ✅ Archivo .env creado (falta rellenarlo)
- ⏳ Falta: configurar al menos un canal de mensajería

---

## OPCIÓN 1: WhatsApp con Baileys (número virtual)

### Lo que necesitas:
- Un número de teléfono virtual/desechable (NO tu número personal)
- Node.js 20+ instalado

### Paso 1: Obtener un número virtual
Opciones gratuitas:
- **TextNow** — App gratis, te da número USA
- **Google Voice** — Gratis con cuenta Google (solo USA)

Opciones de pago:
- **Twilio** — ~$1-2/mes, número de cualquier país
- **Número prepago** — Compra un SIM barato dedicado

### Paso 2: Instalar Node.js (si no lo tienes)
```bash
# Verificar si ya lo tienes
node --version

# Si no lo tienes, instalar:
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
```

### Paso 3: Configurar el bridge de WhatsApp
```bash
cd /home/orlando/Desktop/XPlus-Finance/ASSISTANT_AI/personal-ai-assistant/whatsapp-bridge
npm install
```

### Paso 4: Iniciar el bridge y escanear QR
```bash
npm start
```
- Aparecerá un código QR en la terminal
- Abre WhatsApp en el teléfono del número virtual
- Ve a Configuración → Dispositivos vinculados → Vincular dispositivo
- Escanea el QR
- Espera a que diga "Connected!"

### Paso 5: Obtener tu chat_id de WhatsApp
- Envía un mensaje desde TU WhatsApp personal al número virtual
- En la terminal del bridge verás algo como: `Message from: 1234567890`
- Ese número (sin el @s.whatsapp.net) es tu AUTHORIZED_PHONE

### Paso 6: Configurar .env
Edita el archivo .env:
```bash
nano /home/orlando/Desktop/XPlus-Finance/ASSISTANT_AI/personal-ai-assistant/.env
```

Cambiar/agregar estas líneas:
```
# WhatsApp Baileys
WHATSAPP_BAILEYS_ENABLED=true
WHATSAPP_BAILEYS_BRIDGE_URL=http://127.0.0.1:3001
AUTHORIZED_PHONE=TU_NUMERO_PERSONAL_SIN_PLUS  # ej: 12345678901

# DB encryption (ya generada)
DB_ENCRYPTION_KEY=2eff35c6f7939cc59280d17ccd7390c8e5a91a3885cbe91b636936d1868cbfce

# Timezone (ajustar a tu zona)
TIMEZONE=America/New_York
```

### Paso 7: Arrancar el asistente
```bash
# Terminal 1: Bridge de WhatsApp (si no está corriendo)
cd /home/orlando/Desktop/XPlus-Finance/ASSISTANT_AI/personal-ai-assistant/whatsapp-bridge
npm start

# Terminal 2: Asistente Python
cd /home/orlando/Desktop/XPlus-Finance/ASSISTANT_AI/personal-ai-assistant
source .venv/bin/activate
python -m src.main
```

### Paso 8: Probar
- Envía "hola" desde tu WhatsApp personal al número virtual
- El asistente debería iniciar el onboarding

### ⚠️ Si te banean el número virtual:
1. Para el bridge (Ctrl+C)
2. Borra la sesión: `rm -rf whatsapp-bridge/auth_info/`
3. Consigue otro número virtual
4. Repite desde el paso 4

---

## OPCIÓN 2: WhatsApp Business API (oficial, sin riesgo)

### Lo que necesitas:
- Cuenta de Meta for Developers
- Cuenta de Meta Business Manager (verificación puede tomar días)
- Número virtual (Twilio ~$2/mes)
- Cloudflare Tunnel (gratis) para recibir webhooks

### Paso 1: Crear cuenta en Meta for Developers
1. Ve a https://developers.facebook.com
2. Inicia sesión con tu cuenta de Facebook
3. Acepta los términos de desarrollador

### Paso 2: Crear app de Business
1. Click "Crear app"
2. Seleccionar "Business" como tipo
3. Dar nombre a la app
4. Seleccionar o crear una cuenta de Business

### Paso 3: Agregar WhatsApp
1. En el dashboard de la app, click "Agregar producto"
2. Seleccionar "WhatsApp"
3. Click "Configurar"

### Paso 4: Obtener credenciales
Del dashboard de WhatsApp obtendrás:
- **Phone Number ID** — ID del número de teléfono
- **Access Token** — Token temporal (generar uno permanente después)
- **Verify Token** — Lo defines tú (cualquier string secreto)

### Paso 5: Configurar número de teléfono
- Puedes usar el número de prueba que Meta te da gratis
- O agregar tu número virtual de Twilio

### Paso 6: Instalar Cloudflare Tunnel
```bash
# Descargar cloudflared
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared

# Crear tunnel (te da una URL pública temporal)
cloudflared tunnel --url http://localhost:8443
```

### Paso 7: Configurar webhook en Meta
1. En el dashboard de WhatsApp → Configuración → Webhook
2. URL del callback: `https://TU-URL-DE-CLOUDFLARE/webhook`
3. Verify token: el que definiste tú
4. Suscribirse a: messages

### Paso 8: Configurar .env
```
WHATSAPP_BUSINESS_ENABLED=true
WHATSAPP_PHONE_NUMBER_ID=tu_phone_number_id
WHATSAPP_ACCESS_TOKEN=tu_access_token
WHATSAPP_VERIFY_TOKEN=tu_verify_token
WHATSAPP_WEBHOOK_SECRET=tu_app_secret
AUTHORIZED_PHONE=tu_numero_personal
```

### Paso 9: Arrancar
```bash
# Terminal 1: Cloudflare Tunnel
cloudflared tunnel --url http://localhost:8443

# Terminal 2: Asistente
cd /home/orlando/Desktop/XPlus-Finance/ASSISTANT_AI/personal-ai-assistant
source .venv/bin/activate
python -m src.main
```

### Costos:
- Mensajes de servicio (cuando TÚ le escribes): **GRATIS**
- Número virtual Twilio: ~$2/mes
- Cloudflare Tunnel: **GRATIS**

---

## OPCIÓN 3: Telegram (la más fácil y segura)

### Lo que necesitas:
- Cuenta de Telegram (gratis)
- 5 minutos

### Paso 1: Crear el bot
1. Abre Telegram en tu teléfono o desktop
2. Busca **@BotFather**
3. Envía `/newbot`
4. Elige nombre: `Mi Asistente IA` (o el que quieras)
5. Elige username: `mi_asistente_ia_bot` (debe terminar en _bot)
6. **BotFather te da un token** — cópialo, es algo como:
   `7123456789:AAH1bGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9`

### Paso 2: Obtener tu Chat ID
1. Busca **@userinfobot** en Telegram
2. Envíale cualquier mensaje (ej: "hola")
3. Te responde con tu **Chat ID** — es un número como: `987654321`

### Paso 3: Configurar .env
```bash
nano /home/orlando/Desktop/XPlus-Finance/ASSISTANT_AI/personal-ai-assistant/.env
```

Rellenar:
```
TELEGRAM_BOT_TOKEN=7123456789:AAH1bGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9
AUTHORIZED_CHAT_ID=987654321
DB_ENCRYPTION_KEY=2eff35c6f7939cc59280d17ccd7390c8e5a91a3885cbe91b636936d1868cbfce
TIMEZONE=America/New_York
```

### Paso 4: Arrancar
```bash
cd /home/orlando/Desktop/XPlus-Finance/ASSISTANT_AI/personal-ai-assistant
source .venv/bin/activate
python -m src.main
```

### Paso 5: Probar
1. Abre tu bot en Telegram (búscalo por el username que elegiste)
2. Envía "hola"
3. El asistente inicia el onboarding automáticamente

---

## DESPUÉS DE CONFIGURAR CUALQUIER CANAL

### El onboarding
La primera vez que envíes un mensaje, el asistente te preguntará:
1. ¿Cómo quieres que se llame?
2. ¿Cómo te llamo a ti?
3. ¿En qué área trabajas?
4. ¿Cómo prefieres comunicarte? (texto/audio, formal/informal)
5. ¿Zona horaria?
6. ¿PIN de seguridad? (opcional)

### Comandos disponibles después del onboarding:
```
INFORMACIÓN
!status          — estado del asistente
!yo              — tu perfil como lo ve el asistente
!memoria         — qué recuerda de ti
!recuerda [algo] — guardar en memoria

TAREAS
!tareas          — ver todas
!tarea nueva [X] — crear tarea

AUDIO
!voz on          — responder siempre con audio
!voz off         — responder siempre con texto
!voz auto        — automático

SKILLS
!skills          — ver skills disponibles
!skill nueva     — crear nueva skill

APRENDIZAJE
!busca [tema]    — buscar en web y aprender

SISTEMA
!cmd [comando]   — ejecutar comando en terminal
!logs            — ver últimos comandos
```

### Para dejar el asistente corriendo 24/7:
```bash
# Opción 1: Usar systemd (recomendado para producción)
sudo cp systemd/ai-assistant.service /etc/systemd/system/
sudo systemctl enable ai-assistant
sudo systemctl start ai-assistant

# Opción 2: Usar tmux (rápido para probar)
tmux new -s asistente
source .venv/bin/activate
python -m src.main
# Ctrl+B, luego D para desconectar
# tmux attach -t asistente para reconectar
```

---

## SOLUCIÓN DE PROBLEMAS

### "No se puede conectar a Claude CLI"
```bash
claude --version  # ¿Está instalado?
claude auth login # ¿Está autenticado?
```

### "El bot no responde en Telegram"
1. Verifica el token en .env
2. Verifica el chat_id en .env
3. Mira los logs: `tail -f logs/app.log`

### "Error de base de datos"
```bash
# Si la DB está corrupta, borrarla y empezar de nuevo
rm data/assistant.db
python -m src.main  # Crea una nueva automáticamente
```

### "El bridge de WhatsApp no conecta"
```bash
# Verificar que el bridge está corriendo
curl http://127.0.0.1:3001/health

# Si dice "disconnected", escanear QR de nuevo
cd whatsapp-bridge
rm -rf auth_info/
npm start
```

### "faster-whisper da error de modelo"
```bash
# Descargar modelo manualmente
source .venv/bin/activate
python -c "from faster_whisper import WhisperModel; WhisperModel('medium')"
```
