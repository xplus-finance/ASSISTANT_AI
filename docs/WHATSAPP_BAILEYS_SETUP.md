# Configuracion de WhatsApp con Baileys

---

## ADVERTENCIA

> **Baileys usa ingenieria inversa del protocolo de WhatsApp Web. NO es API oficial.**
>
> - **Ban temporal o permanente** del numero (~5-15% probabilidad)
> - Meta puede cambiar el protocolo sin aviso
> - Sin soporte oficial
>
> **NUNCA** uses tu numero personal. Usa un numero virtual dedicado.
> Si el numero importa, usa WhatsApp Business API.

---

## Requisitos

| Requisito | Detalle |
|-----------|---------|
| Asistente instalado | `install.sh` (Linux/macOS) o `install.ps1` (Windows) ejecutado |
| Node.js | 18+ |
| Numero virtual | Dedicado exclusivamente para el bot |
| Telefono/emulador | Para registrar WhatsApp con el numero virtual |

---

## Paso 1: Obtener un numero virtual

| Servicio | Costo | Paises | Notas |
|----------|-------|--------|-------|
| TextNow | Gratis | USA/Canada | Puede expirar sin uso |
| Google Voice | Gratis | Solo USA | Requiere numero existente |
| Hushed | ~$2/mes | Multiples | Buena opcion economica |
| MySudo | ~$1/mes | USA/Canada | Buena privacidad |
| Twilio | ~$1-2/mes | Muchos | Mas tecnico, confiable |
| SIM prepaga | ~$2-5 una vez | Local | Chip barato |

Proceso:
1. Obtener numero en el servicio elegido
2. Instalar WhatsApp en telefono o emulador (BlueStacks, etc.)
3. Registrar con el numero virtual
4. Verificar via SMS o llamada

---

## Paso 2: Instalar Node.js

### Linux (Ubuntu/Debian)

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

### Linux (Fedora)

```bash
sudo dnf install -y nodejs
```

### Linux (Arch)

```bash
sudo pacman -S nodejs npm
```

### macOS

```bash
brew install node
```

### Windows

```powershell
winget install --id OpenJS.NodeJS.LTS -e
```

O descargar desde [nodejs.org](https://nodejs.org/) (LTS 20+).

### nvm (multiplataforma)

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.0/install.sh | bash
source ~/.bashrc
nvm install 20
nvm use 20
```

### Verificar

```bash
node --version  # v20.x.x
npm --version   # 10.x.x
```

---

## Paso 3: Instalar el bridge

```bash
cd /ruta/al/ASSISTANT_AI/whatsapp-bridge
npm install
```

Si el directorio no existe:

```bash
mkdir -p whatsapp-bridge
cd whatsapp-bridge
npm init -y
npm install @whiskeysockets/baileys express qrcode-terminal pino
```

---

## Paso 4: Iniciar bridge y escanear QR

```bash
cd whatsapp-bridge
npm start
```

1. Aparece un **codigo QR** en terminal
2. En WhatsApp (telefono del numero virtual): **Configuracion > Dispositivos vinculados > Vincular dispositivo**
3. Escanear el QR
4. Esperar mensaje `Conectado exitosamente`

> La sesion se guarda en `whatsapp-bridge/auth_info/`. No borrar esa carpeta.

---

## Paso 5: Verificar conexion

```bash
curl http://127.0.0.1:3001/health
```

Respuesta esperada:
```json
{"status":"connected","uptime":...}
```

---

## Paso 6: Configurar .env

```bash
# Linux / macOS
nano .env

# Windows
notepad .env
```

```
WHATSAPP_NUMBER=+1234567890
WHATSAPP_BRIDGE_URL=http://localhost:3001
```

`WHATSAPP_NUMBER` = numero virtual con codigo de pais.

---

## Paso 7: Iniciar todo

Dos procesos simultaneos:

### Terminal 1: Bridge

```bash
cd /ruta/al/ASSISTANT_AI/whatsapp-bridge
npm start
```

### Terminal 2: Asistente

```bash
# Linux / macOS
cd /ruta/al/ASSISTANT_AI
source .venv/bin/activate
python -m src.main

# Windows
cd C:\ruta\al\ASSISTANT_AI
.venv\Scripts\python.exe -m src.main
```

Con systemd (Linux):
```bash
sudo systemctl start ai-assistant
```

En Windows: `start.bat` para el asistente, bridge en terminal aparte.

---

## Medidas anti-ban (incluidas en el bridge)

1. **Delays aleatorios**: 1-3 segundos antes de cada respuesta
2. **Rate limiting**: maximo 10 mensajes por minuto
3. **Indicador de escritura**: envia "escribiendo..." antes de responder
4. **Sin mensajes masivos**: solo responde, nunca inicia conversaciones
5. **Reconexion gradual**: backoff exponencial en desconexiones

Recomendaciones:
- No enviar muchos mensajes seguidos (esperar respuestas)
- No usar 24/7 sin pausa los primeros dias
- Empezar con poco uso e incrementar
- Evitar contenido que pueda marcarse como spam

---

## Si banean el numero

1. Obtener otro numero virtual
2. Registrar WhatsApp con el nuevo numero
3. Borrar sesion anterior:
   ```bash
   rm -rf whatsapp-bridge/auth_info/
   ```
4. Reiniciar bridge (`npm start`), escanear QR
5. Actualizar numero en `.env`

La memoria del asistente no se pierde — esta en la DB local cifrada.

---

## Solucion de problemas

### QR no aparece
- Verificar Node.js 18+: `node --version`
- Borrar `auth_info/` y reiniciar
- Verificar puerto 3001 libre:
  - Linux/macOS: `lsof -i :3001`
  - Windows: `netstat -ano | findstr :3001`

### Desconexiones constantes
- Verificar conexion a internet del telefono con el numero virtual
- No usar WhatsApp Web simultaneamente en otro dispositivo
- Revisar logs del bridge

### Asistente no recibe mensajes
- Verificar bridge corriendo: `curl http://127.0.0.1:3001/health`
- Verificar `WHATSAPP_BRIDGE_URL` en `.env`
- Revisar logs:
  - Linux/macOS: `tail -20 logs/app.log`
  - Windows: abrir `logs\app.log`

### "Connection closed" o "Stream errored"
- Normal que la conexion se reinicie ocasionalmente
- Bridge tiene reconexion automatica
- Si persiste: borrar `auth_info/` y re-escanear QR

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
| Plataformas | Windows, Linux, macOS | Windows, Linux, macOS |

Guia Business API: [WHATSAPP_BUSINESS_SETUP.md](WHATSAPP_BUSINESS_SETUP.md).
