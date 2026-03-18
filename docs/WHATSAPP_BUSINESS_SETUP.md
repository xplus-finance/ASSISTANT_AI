# Configuracion de WhatsApp Business API

API oficial de Meta (Cloud API). Cero riesgo de ban. Funciona en Windows, Linux y macOS.

---

## Requisitos

| Requisito | Detalle |
|-----------|---------|
| [Meta for Developers](https://developers.facebook.com/) | Cuenta activa |
| Meta Business | Cuenta verificada (puede tomar dias) |
| Numero dedicado | Twilio ~$2/mes, o numero de prueba gratuito de Meta |
| Cloudflare Tunnel | Gratuito, expone webhook local sin abrir puertos |

---

## 1. Crear App en Meta

1. Ir a [developers.facebook.com](https://developers.facebook.com/)
2. **"My Apps"** > **"Create App"**
3. Tipo: **"Business"**
4. Nombre (ej: "Mi Asistente IA")
5. Seleccionar cuenta Meta Business

## 2. Agregar producto WhatsApp

1. Dashboard de tu app > **"Add Products"**
2. Buscar **"WhatsApp"** > **"Set Up"**
3. Seguir wizard

## 3. Obtener credenciales

En **WhatsApp > API Setup**:

| Credencial | Descripcion |
|------------|-------------|
| Phone Number ID | Identificador del numero (ej: `123456789012345`) |
| Access Token | Token temporal de prueba. Para produccion: System User token permanente |
| Verify Token | Lo eliges tu, cadena arbitraria para verificar webhook |

## 4. Configurar numero

Meta da un numero de prueba gratuito para desarrollo. Para produccion:

1. **WhatsApp > API Setup > Add Phone Number**
2. Verificar via SMS o llamada
3. O usar numero Twilio (~$2/mes)

Tu numero personal NUNCA se usa. Siempre un numero dedicado.

## 5. Configurar Cloudflare Tunnel

El asistente corre un webhook en `localhost:8443`. Cloudflare Tunnel lo expone a internet sin abrir puertos.

### Instalar cloudflared

**Linux (Debian/Ubuntu):**
```bash
sudo apt install cloudflared
```

**Linux (Arch):**
```bash
sudo pacman -S cloudflared
```

**Linux (descarga directa):**
```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
chmod +x cloudflared
```

**macOS:**
```bash
brew install cloudflared
```

**Windows:**
```powershell
winget install --id Cloudflare.cloudflared -e
```

O descargar binario desde [github.com/cloudflare/cloudflared/releases](https://github.com/cloudflare/cloudflared/releases).

### Tunnel temporal (pruebas)

```bash
cloudflared tunnel --url http://localhost:8443
```

Genera URL tipo `https://algo-random.trycloudflare.com`. Copiar esa URL.

### Tunnel permanente (produccion)

```bash
cloudflared tunnel login
cloudflared tunnel create mi-asistente
```

Configurar `~/.cloudflared/config.yml`:
```yaml
tunnel: <TUNNEL_ID>
credentials-file: /home/user/.cloudflared/<TUNNEL_ID>.json
ingress:
  - hostname: wa.midominio.com
    service: http://localhost:8443
  - service: http_status:404
```

```bash
cloudflared tunnel run mi-asistente
```

## 6. Configurar webhook en Meta

1. **WhatsApp > Configuration** en dashboard
2. **"Edit"** en seccion Webhook
3. **Callback URL**: `https://tu-url-cloudflare.com/webhook`
4. **Verify Token**: el que elegiste (ej: `mi_token_secreto_123`)
5. **"Verify and Save"**
6. Suscribirse al campo **"messages"**

## 7. Configurar .env

```
WHATSAPP_PHONE_NUMBER_ID=123456789012345
WHATSAPP_ACCESS_TOKEN=EAAxxxxxxxxxxxxxxxxxxxxxxx
WHATSAPP_VERIFY_TOKEN=mi_token_secreto_123
WHATSAPP_WEBHOOK_SECRET=tu_app_secret_aqui
WHATSAPP_WEBHOOK_PORT=8443
```

`WHATSAPP_WEBHOOK_SECRET` = App Secret de tu aplicacion (**Settings > Basic** en dashboard). Verifica que los webhooks vienen de Meta via HMAC-SHA256. Opcional pero recomendado en produccion.

## 8. Probar

1. Verificar que el tunnel de Cloudflare esta corriendo
2. Iniciar asistente:
   - Linux/macOS: `source .venv/bin/activate && python -m src.main`
   - Windows: `start.bat` o `.venv\Scripts\python.exe -m src.main`
3. Enviar mensaje al numero del bot desde WhatsApp
4. Con numero de prueba de Meta: agregar tu numero como "tester" en el dashboard

---

## Costos

| Concepto | Precio |
|----------|--------|
| Mensajes de servicio (respuestas < 24h) | **Gratis** (primeras 1,000/mes) |
| Mensajes del negocio (templates) | $0.01 - $0.14 segun pais |
| Numero virtual (Twilio/similar) | ~$2 - $5/mes |
| Cloudflare Tunnel | **Gratis** |
| Meta Business verification | **Gratis** (toma tiempo) |

Referencia: [Meta WhatsApp Pricing](https://developers.facebook.com/docs/whatsapp/pricing/)

---

## Seguridad

- **Tu numero personal nunca se expone** — numero dedicado
- **API oficial** — 0% riesgo de ban
- **Webhook en localhost** — solo accesible via tunnel
- **Verificacion de firma** — HMAC-SHA256 con App Secret
- **Sin puertos abiertos** — Cloudflare Tunnel usa conexion saliente
- **Sandbox** — comandos ejecutados en bubblewrap (Linux) o subprocess (Windows/macOS)
- **Permisos** — `.env`, `data/`, `logs/` endurecidos automaticamente (Linux/macOS)

---

## Tipos de mensaje

| Tipo | Recibir | Enviar |
|------|---------|--------|
| Texto | Si | Si |
| Audio/Voz | Si (transcripcion local, faster-whisper) | Si (multiples motores TTS) |
| Imagen | Si | No (pendiente) |
| Documento | Si | Si |
| Sticker | Si (como imagen) | No |
| Ubicacion | Si (convertido a texto) | No |
| Contactos | Si (convertido a texto) | No |

---

## Solucion de problemas

### Webhook no verifica
- Verificar tunnel corriendo y URL correcta
- `WHATSAPP_VERIFY_TOKEN` debe coincidir exactamente
- Revisar logs:
  - Linux/macOS: `tail -f logs/app.log`
  - Windows: abrir `logs\app.log`

### No llegan mensajes
- Verificar suscripcion al campo "messages" en webhook
- Con numero de prueba: confirmar tu numero en lista de testers
- Revisar consola Meta: **WhatsApp > API Setup > Logs**

### Error 401 al enviar
- Token temporal expira cada 24h. Generar nuevo o crear System User token permanente
- Token permanente: **Business Settings > System Users > Generate Token**

### "Message failed to send"
- Verificar que destino tiene WhatsApp
- Mensajes fuera de ventana 24h requieren templates aprobados
- Formato de numero: codigo de pais, sin `+` ni espacios (ej: `5491123456789`)
