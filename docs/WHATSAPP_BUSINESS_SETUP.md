# Configuracion de WhatsApp Business API

Guia completa para integrar el asistente con WhatsApp usando la API oficial de Meta (Cloud API).

## Requisitos

- Cuenta de [Meta for Developers](https://developers.facebook.com/)
- Cuenta de Meta Business (la verificacion puede tomar dias)
- Numero virtual dedicado (Twilio ~$2/mes, o usar el numero de prueba que Meta te da gratis)
- Cloudflare Tunnel (gratuito) para exponer el webhook local

## Paso a paso

### 1. Crear la App en Meta

1. Ir a [developers.facebook.com](https://developers.facebook.com/)
2. Click en **"My Apps"** > **"Create App"**
3. Seleccionar tipo **"Business"**
4. Darle un nombre (ej: "Mi Asistente IA")
5. Seleccionar tu cuenta de Meta Business

### 2. Agregar el producto WhatsApp

1. En el dashboard de tu app, ir a **"Add Products"**
2. Buscar **"WhatsApp"** y hacer click en **"Set Up"**
3. Seguir el wizard de configuracion

### 3. Obtener credenciales

En la seccion **WhatsApp > API Setup** encontraras:

- **Phone Number ID**: identificador del numero de telefono (ej: `123456789012345`)
- **Access Token**: token temporal de prueba (para produccion necesitas un System User token permanente)
- **Verify Token**: lo eliges tu, es una cadena arbitraria para verificar el webhook

### 4. Configurar numero de telefono

Meta te da un numero de prueba gratuito para desarrollo. Para produccion:

1. Agregar tu propio numero en **WhatsApp > API Setup > Add Phone Number**
2. Verificar el numero via SMS o llamada
3. O usar un numero virtual de Twilio (~$2/mes) o similar

**IMPORTANTE**: Tu numero personal NUNCA se usa. Siempre es un numero dedicado para el bot.

### 5. Configurar Cloudflare Tunnel

El asistente corre un servidor webhook en `localhost:8443`. Necesitas exponer ese puerto a internet para que Meta pueda enviar los mensajes entrantes.

```bash
# Instalar cloudflared
# Opcion 1: descarga directa
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
chmod +x cloudflared

# Opcion 2: via apt (Debian/Ubuntu)
# sudo apt install cloudflared

# Crear tunnel temporal (para pruebas)
./cloudflared tunnel --url http://localhost:8443
```

Cloudflared te dara una URL tipo `https://algo-random.trycloudflare.com`. Copia esa URL.

Para produccion, configura un tunnel permanente con un dominio propio:

```bash
# Login
cloudflared tunnel login

# Crear tunnel con nombre
cloudflared tunnel create mi-asistente

# Configurar (en ~/.cloudflared/config.yml)
# tunnel: <TUNNEL_ID>
# credentials-file: /home/user/.cloudflared/<TUNNEL_ID>.json
# ingress:
#   - hostname: wa.midominio.com
#     service: http://localhost:8443
#   - service: http_status:404

# Ejecutar
cloudflared tunnel run mi-asistente
```

### 6. Configurar webhook en Meta

1. Ir a **WhatsApp > Configuration** en el dashboard de tu app
2. Click en **"Edit"** en la seccion Webhook
3. **Callback URL**: `https://tu-url-cloudflare.com/webhook`
4. **Verify Token**: el mismo que elegiste (ej: `mi_token_secreto_123`)
5. Click en **"Verify and Save"**
6. Suscribirse al campo **"messages"**

### 7. Configurar variables de entorno

Agregar a tu archivo `.env`:

```bash
# WhatsApp Business API
WHATSAPP_PHONE_NUMBER_ID=123456789012345
WHATSAPP_ACCESS_TOKEN=EAAxxxxxxxxxxxxxxxxxxxxxxx
WHATSAPP_VERIFY_TOKEN=mi_token_secreto_123
WHATSAPP_WEBHOOK_SECRET=tu_app_secret_aqui

# Puerto del webhook (opcional, default 8443)
WHATSAPP_WEBHOOK_PORT=8443
```

El `WHATSAPP_WEBHOOK_SECRET` es el **App Secret** de tu aplicacion (lo encuentras en **Settings > Basic** en el dashboard). Se usa para verificar que los webhooks realmente vienen de Meta. Es opcional pero MUY recomendado en produccion.

### 8. Probar

1. Asegurate de que el tunnel de Cloudflare esta corriendo
2. Inicia el asistente
3. Desde WhatsApp, envia un mensaje al numero del bot
4. Si usas el numero de prueba de Meta, primero debes agregar tu numero personal como "tester" en el dashboard

## Costos

| Concepto | Precio |
|---|---|
| Mensajes de servicio (respuestas dentro de 24h) | **GRATIS** (primeras 1,000/mes) |
| Mensajes iniciados por el negocio (templates) | $0.01 - $0.14 segun pais |
| Numero virtual (Twilio/similar) | ~$2 - $5/mes |
| Cloudflare Tunnel | **GRATIS** |
| Meta Business verification | **GRATIS** (pero toma tiempo) |

Referencia de precios: [Meta WhatsApp Pricing](https://developers.facebook.com/docs/whatsapp/pricing/)

## Seguridad

- **Tu numero personal NUNCA se expone** -- siempre se usa un numero dedicado
- **API oficial de Meta** -- 0% riesgo de ban (a diferencia de librerias no oficiales)
- **Webhook solo en localhost** -- el servidor web corre en `127.0.0.1`, solo accesible via el tunnel
- **Verificacion de firma** -- cada webhook se verifica con HMAC-SHA256 usando el App Secret
- **Sin puertos abiertos** -- Cloudflare Tunnel crea una conexion saliente, no necesitas abrir puertos en tu firewall

## Tipos de mensaje soportados

| Tipo | Recibir | Enviar |
|---|---|---|
| Texto | Si | Si |
| Audio/Voz | Si (se descarga automaticamente) | Si |
| Imagen | Si (se descarga automaticamente) | No (pendiente) |
| Documento | Si (se descarga automaticamente) | Si |
| Sticker | Si (se trata como imagen) | No |
| Ubicacion | Si (se convierte a texto) | No |
| Contactos | Si (se convierte a texto) | No |

## Troubleshooting

### El webhook no verifica
- Asegurate de que el tunnel esta corriendo y la URL es correcta
- Verifica que el `WHATSAPP_VERIFY_TOKEN` coincide exactamente
- Revisa los logs del asistente: `tail -f logs/assistant.log`

### No llegan mensajes
- Verifica que estas suscrito al campo "messages" en el webhook
- Si usas el numero de prueba, confirma que tu numero esta en la lista de testers
- Revisa la consola de Meta: **WhatsApp > API Setup > Logs**

### Error 401 al enviar
- El token temporal expira cada 24h. Genera uno nuevo o crea un System User token permanente
- Para token permanente: **Business Settings > System Users > Generate Token**

### Error "Message failed to send"
- Verifica que el numero destino tiene WhatsApp
- Los mensajes fuera de la ventana de 24h requieren templates aprobados
- Revisa el formato del numero: debe incluir codigo de pais, sin + ni espacios (ej: `5491123456789`)
