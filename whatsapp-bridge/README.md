# WhatsApp Baileys Bridge

Servicio Node.js que conecta el Personal AI Assistant con WhatsApp usando la libreria [Baileys](https://github.com/WhiskeySockets/Baileys) (protocolo no oficial de WhatsApp Web).

---

## ADVERTENCIA - RIESGO DE BANEO

> **WhatsApp puede banear permanentemente el numero que uses con este bridge.**
>
> Baileys usa el protocolo no oficial de WhatsApp Web. Meta/WhatsApp no autoriza
> el uso de bots de terceros y puede suspender o banear numeros que detecte usando
> clientes no oficiales.
>
> **NUNCA uses tu numero personal.** Usa siempre un numero virtual o dedicado.

---

## Como obtener un numero virtual

Opciones para obtener un numero que puedas "quemar" sin perder tu numero personal:

1. **TextNow** (gratis, USA/Canada) — Numero VoIP gratuito, funciona con WhatsApp en muchos casos.
2. **Google Voice** (gratis, USA) — Requiere numero USA existente para activar.
3. **Twilio** (pago, ~$1/mes) — Numero programable, muy confiable.
4. **SIM prepago barata** — Compra una SIM de datos en cualquier operador local. La opcion mas simple y confiable.

> El numero virtual debe poder recibir SMS o llamadas para verificar WhatsApp la primera vez.

---

## Setup paso a paso

### 1. Instalar dependencias

```bash
cd whatsapp-bridge
npm install
```

### 2. Iniciar el bridge

```bash
npm start
```

Al iniciar por primera vez, se mostrara un **codigo QR** en la terminal.

### 3. Escanear el QR

1. Abre WhatsApp en el telefono con el **numero virtual**.
2. Ve a **Configuracion > Dispositivos vinculados > Vincular dispositivo**.
3. Escanea el QR que aparece en la terminal.

La sesion se guarda en `auth_info/` — no necesitas escanear de nuevo a menos que cierres sesion.

### 4. Configurar el asistente

En el `.env` del asistente, agrega:

```env
WHATSAPP_BAILEYS_BRIDGE_URL=http://127.0.0.1:3001
WHATSAPP_BAILEYS_AUTHORIZED_PHONE=5491112345678
```

Donde `WHATSAPP_BAILEYS_AUTHORIZED_PHONE` es el numero (con codigo de pais, sin +) del cual quieres recibir mensajes. Todos los demas numeros se ignoran.

---

## Verificar que esta funcionando

```bash
# Health check
curl http://127.0.0.1:3001/health
# Respuesta: {"status":"connected"}

# Ver QR (si aun no escaneaste)
curl http://127.0.0.1:3001/qr

# Ver mensajes en cola
curl http://127.0.0.1:3001/messages

# Enviar mensaje de prueba
curl -X POST http://127.0.0.1:3001/send/text \
  -H "Content-Type: application/json" \
  -d '{"phone":"5491112345678","message":"Hola desde el bridge!"}'
```

---

## Endpoints

| Metodo | Ruta              | Descripcion                                    |
|--------|-------------------|------------------------------------------------|
| GET    | `/health`         | Estado de conexion (`connected`/`disconnected`) |
| GET    | `/messages`       | Mensajes en cola (se vacian al leer)           |
| GET    | `/qr`             | QR actual en texto (para setup remoto)         |
| POST   | `/send/text`      | Enviar texto `{phone, message}`                |
| POST   | `/send/audio`     | Enviar audio `{phone, audioPath}`              |
| POST   | `/send/document`  | Enviar documento `{phone, path, caption}`      |
| POST   | `/send/typing`    | Indicador de escritura `{phone}`               |

---

## Seguridad

- El bridge escucha **solo en 127.0.0.1** (localhost). No es accesible desde la red.
- No requiere autenticacion (solo procesos locales pueden acceder).
- Los mensajes salientes tienen rate limit: maximo 10 por minuto.
- Se agrega un delay aleatorio de 1-3 segundos entre mensajes para reducir riesgo de baneo.

---

## Que hacer si te banean

1. **No entres en panico.** WhatsApp suele dar bans temporales primero (24h-72h).
2. Borra la carpeta `auth_info/` para limpiar la sesion.
3. Si el ban es permanente, necesitas un numero nuevo.
4. Para apelar: abre WhatsApp > deberia mostrarte opcion de "Solicitar revision".
5. Reduce la frecuencia de mensajes si te desbanean.

### Para reducir riesgo de baneo futuro:
- No envies mensajes masivos.
- Mantene conversaciones naturales (no spam).
- No envies el mismo mensaje a muchos contactos.
- Usa el bot solo para conversacion personal 1-a-1.
- Deja el bridge corriendo 24/7 (desconexiones frecuentes son sospechosas).

---

## Estructura de archivos

```
whatsapp-bridge/
  index.js         # Servidor Express + Baileys
  package.json     # Dependencias
  auth_info/       # Credenciales de sesion (NO commitear)
  media/           # Audios/imagenes/docs recibidos
  README.md        # Este archivo
```

> Agrega `auth_info/` y `media/` a tu `.gitignore`.
