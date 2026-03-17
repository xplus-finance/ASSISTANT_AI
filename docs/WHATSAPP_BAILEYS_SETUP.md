# Configuracion de WhatsApp con Baileys

---

## ADVERTENCIA IMPORTANTE

> **Baileys usa ingenieria inversa del protocolo de WhatsApp Web. NO es una API oficial.**
>
> Riesgos reales:
> - **Ban temporal o permanente** del numero (~5-15% de probabilidad)
> - Meta puede cambiar el protocolo sin aviso, rompiendo la conexion
> - No hay soporte oficial ni garantias de funcionamiento
>
> **Reglas de oro:**
> - **NUNCA** uses tu numero personal
> - Usa un numero virtual dedicado exclusivamente para el bot
> - Si el numero es importante para ti, usa WhatsApp Business API en su lugar

---

## Requisitos previos

- El asistente instalado (haber ejecutado `install.sh`)
- Node.js 18+ instalado
- Un numero de telefono virtual dedicado
- Un telefono o emulador donde registrar WhatsApp con ese numero

---

## Paso 1: Obtener un numero virtual

Necesitas un numero de telefono que pueda recibir SMS para verificar WhatsApp. **Este numero es desechable** -- si lo banean, consigues otro.

| Servicio | Costo | Paises | Notas |
|----------|-------|--------|-------|
| TextNow | Gratis | USA/Canada | Puede expirar si no lo usas |
| Google Voice | Gratis | Solo USA | Requiere numero existente para verificar |
| Hushed | ~$2/mes | Multiples | Buena opcion economica |
| MySudo | ~$1/mes | USA/Canada | Buena privacidad |
| Twilio | ~$1-2/mes | Muchos paises | Mas tecnico pero confiable |
| SIM prepaga | ~$2-5 unica vez | Local | Comprar un chip barato |

### Proceso:

1. Obtener el numero virtual en el servicio elegido
2. Instalar WhatsApp en un telefono o emulador (BlueStacks, etc.)
3. Registrar WhatsApp con el numero virtual
4. Verificar con SMS o llamada
5. Una vez verificado, ya puedes vincular dispositivos

---

## Paso 2: Instalar Node.js

Se requiere Node.js 18 o superior:

```bash
# Ubuntu/Debian
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Verificar
node --version  # v20.x.x
npm --version   # 10.x.x
```

Alternativa con nvm:
```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.0/install.sh | bash
source ~/.bashrc
nvm install 20
nvm use 20
```

---

## Paso 3: Instalar el bridge de WhatsApp

```bash
cd /ruta/al/personal-ai-assistant/whatsapp-bridge
npm install
```

Esto instala Baileys y todas las dependencias necesarias.

Si el directorio `whatsapp-bridge/` no existe, crealo:
```bash
mkdir -p whatsapp-bridge
cd whatsapp-bridge
npm init -y
npm install @whiskeysockets/baileys express qrcode-terminal pino
```

---

## Paso 4: Iniciar el bridge y escanear QR

```bash
cd whatsapp-bridge
npm start
```

1. Aparecera un **codigo QR** en la terminal
2. Abre WhatsApp en el telefono donde registraste el numero virtual
3. Ve a **Configuracion > Dispositivos vinculados > Vincular dispositivo**
4. Escanea el QR que aparece en la terminal
5. Espera a que diga `Conectado exitosamente`

> **Importante:** La sesion se guarda en `whatsapp-bridge/auth_info/`. **No borres esta carpeta** o tendras que escanear el QR de nuevo.

---

## Paso 5: Verificar que el bridge funciona

Con el bridge corriendo, verifica la conexion:

```bash
curl http://127.0.0.1:3001/health
```

Deberia devolver:
```json
{"status":"connected","uptime":...}
```

---

## Paso 6: Configurar .env

Edita el `.env` del proyecto principal:

```bash
nano .env
```

Agrega o modifica estas lineas:

```
# --- WhatsApp Baileys ---
WHATSAPP_NUMBER=+1234567890
WHATSAPP_BRIDGE_URL=http://localhost:3001
```

El numero en `WHATSAPP_NUMBER` es el numero virtual que usaste para registrar WhatsApp (con codigo de pais).

---

## Paso 7: Iniciar todo

Necesitas **dos procesos** corriendo simultaneamente:

### Terminal 1: Bridge de WhatsApp
```bash
cd /ruta/al/personal-ai-assistant/whatsapp-bridge
npm start
```

### Terminal 2: Asistente
```bash
cd /ruta/al/personal-ai-assistant
source .venv/bin/activate
python -m src.main
```

O si instalaste los servicios systemd:
```bash
sudo systemctl start ai-assistant
# (el bridge necesita su propio servicio systemd o ejecutarse por separado)
```

---

## Medidas anti-ban (incluidas en el bridge)

El bridge incluye estas protecciones por defecto para reducir el riesgo de ban:

1. **Delays aleatorios** -- 1-3 segundos de espera antes de cada respuesta (simula escritura humana)
2. **Rate limiting** -- maximo 10 mensajes por minuto
3. **Indicador de escritura** -- envia "escribiendo..." antes de responder
4. **Sin mensajes masivos** -- solo responde, nunca inicia conversaciones no solicitadas
5. **Reconexion gradual** -- backoff exponencial en desconexiones (no reconecta inmediatamente)

### Recomendaciones adicionales:

- No envies muchos mensajes seguidos al bot (espera las respuestas)
- No uses el bot 24/7 sin pausa los primeros dias
- Empieza con poco uso e incrementa gradualmente
- No envies contenido que pueda ser marcado como spam

---

## Si te banean el numero

No es el fin del mundo:

1. Consigue otro numero virtual (son baratos o gratis)
2. Registra WhatsApp con el nuevo numero
3. Borra la sesion anterior:
   ```bash
   rm -rf whatsapp-bridge/auth_info/
   ```
4. Reinicia el bridge (`npm start`) y escanea el QR de nuevo
5. Actualiza el numero en `.env` si es diferente

La memoria y datos del asistente **no se pierden** -- estan en la base de datos local, no en WhatsApp.

---

## Solucion de problemas

### El QR no aparece
- Verifica que Node.js 18+ esta instalado: `node --version`
- Borra `auth_info/` y reinicia
- Verifica que el puerto 3001 no esta en uso: `lsof -i :3001`

### Se desconecta constantemente
- Asegurate de que el telefono con el numero virtual tiene conexion a internet estable
- No uses WhatsApp Web simultaneamente en otro navegador/dispositivo
- Revisa que no haya un conflicto de sesiones
- Revisa los logs del bridge por errores

### El asistente no recibe mensajes
- Verifica que el bridge esta corriendo: `curl http://127.0.0.1:3001/health`
- Verifica que el `WHATSAPP_BRIDGE_URL` en `.env` apunta al bridge
- Revisa los logs: `tail -20 logs/app.log`

### Error "Connection closed" o "Stream errored"
- Es normal que la conexion se reinicie ocasionalmente
- El bridge tiene reconexion automatica
- Si persiste, borra `auth_info/` y escanea el QR de nuevo

### Numero baneado
- Ver seccion "Si te banean el numero" arriba
- Considera migrar a WhatsApp Business API para evitar bans futuros

---

## Comparacion con WhatsApp Business API

| Aspecto | Baileys | Business API |
|---------|---------|-------------|
| Costo | ~$2/mes (numero virtual) | ~$5-20/mes |
| Riesgo de ban | Medio (5-15%) | 0% |
| Setup | 15 min | 1-2 horas |
| Requiere | Node.js, telefono | Cuenta Meta Business, Cloudflare Tunnel |
| Estabilidad | Puede romperse | API oficial estable |
| Ideal para | Uso personal, pruebas | Produccion |

Si el riesgo de ban te preocupa, la guia de WhatsApp Business API esta en [WHATSAPP_BUSINESS_SETUP.md](WHATSAPP_BUSINESS_SETUP.md).
