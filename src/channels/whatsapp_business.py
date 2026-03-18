"""WhatsApp Business Cloud API channel with local webhook server."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import mimetypes
import os
import tempfile
from pathlib import Path

import httpx
from aiohttp import web

from src.channels.base import Channel, IncomingMessage, MessageHandler

logger = logging.getLogger(__name__)

_API_VERSION = "v21.0"
_BASE_URL = f"https://graph.facebook.com/{_API_VERSION}"

_MAX_TEXT_LENGTH = 4096

_WEBHOOK_HOST = "127.0.0.1"
_WEBHOOK_PORT = 8443


class WhatsAppBusinessChannel(Channel):


    def __init__(
        self,
        phone_number_id: str,
        access_token: str,
        verify_token: str,
        webhook_secret: str = "",
        webhook_port: int = _WEBHOOK_PORT,
    ) -> None:
        if not phone_number_id or not access_token or not verify_token:
            raise ValueError(
                "phone_number_id, access_token y verify_token son obligatorios."
            )

        self._phone_number_id = phone_number_id
        self._access_token = access_token
        self._verify_token = verify_token
        self._webhook_secret = webhook_secret
        self._webhook_port = webhook_port

        self._handler: MessageHandler | None = None
        self._http_client: httpx.AsyncClient | None = None
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._temp_dir = tempfile.mkdtemp(prefix="wa_downloads_")

        self._processed_messages: set[str] = set()
        self._processed_messages_max = 10_000

        self._headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    def set_message_handler(self, handler: MessageHandler) -> None:
        self._handler = handler

    async def start(self) -> None:
        logger.info(
            "Starting WhatsApp Business channel (webhook on %s:%d)...",
            _WEBHOOK_HOST,
            self._webhook_port,
        )

        self._http_client = httpx.AsyncClient(timeout=30.0)

        self._app = web.Application()
        self._app.router.add_get("/webhook", self._verify_webhook)
        self._app.router.add_post("/webhook", self._handle_webhook)
        self._app.router.add_get("/health", self._health_check)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(
            self._runner, _WEBHOOK_HOST, self._webhook_port
        )
        await self._site.start()

        logger.info(
            "WhatsApp webhook server running on http://%s:%d/webhook",
            _WEBHOOK_HOST,
            self._webhook_port,
        )
        logger.info(
            "Expose this port with: cloudflared tunnel --url http://localhost:%d",
            self._webhook_port,
        )

    async def stop(self) -> None:
        logger.info("Stopping WhatsApp Business channel...")

        if self._site is not None:
            await self._site.stop()
            self._site = None

        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

        self._app = None
        logger.info("WhatsApp Business channel stopped.")

    async def send_text(self, chat_id: str, text: str) -> None:
        self._ensure_client()

        chunks = self._split_text(text)
        for chunk in chunks:
            payload = {
                "messaging_product": "whatsapp",
                "to": chat_id,
                "type": "text",
                "text": {"body": chunk},
            }
            resp = await self._http_client.post(
                f"{_BASE_URL}/{self._phone_number_id}/messages",
                headers=self._headers,
                json=payload,
            )
            if resp.status_code != 200:
                logger.error(
                    "Failed to send text to %s: %d %s",
                    chat_id,
                    resp.status_code,
                    resp.text,
                )
                resp.raise_for_status()

    async def send_audio(self, chat_id: str, audio_path: str) -> None:
        self._ensure_client()

        mime_type = mimetypes.guess_type(audio_path)[0] or "audio/ogg"
        media_id = await self._upload_media(audio_path, mime_type)

        payload = {
            "messaging_product": "whatsapp",
            "to": chat_id,
            "type": "audio",
            "audio": {"id": media_id},
        }
        resp = await self._http_client.post(
            f"{_BASE_URL}/{self._phone_number_id}/messages",
            headers=self._headers,
            json=payload,
        )
        if resp.status_code != 200:
            logger.error(
                "Failed to send audio to %s: %d %s",
                chat_id,
                resp.status_code,
                resp.text,
            )
            resp.raise_for_status()

    async def send_document(
        self, chat_id: str, path: str, caption: str = ""
    ) -> None:
        self._ensure_client()

        mime_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
        media_id = await self._upload_media(path, mime_type)

        doc_payload: dict = {"id": media_id}
        if caption:
            doc_payload["caption"] = caption
        doc_payload["filename"] = Path(path).name

        payload = {
            "messaging_product": "whatsapp",
            "to": chat_id,
            "type": "document",
            "document": doc_payload,
        }
        resp = await self._http_client.post(
            f"{_BASE_URL}/{self._phone_number_id}/messages",
            headers=self._headers,
            json=payload,
        )
        if resp.status_code != 200:
            logger.error(
                "Failed to send document to %s: %d %s",
                chat_id,
                resp.status_code,
                resp.text,
            )
            resp.raise_for_status()

    async def send_typing(self, chat_id: str) -> None:
        logger.debug(
            "send_typing called for %s — WhatsApp does not support this, ignoring.",
            chat_id,
        )

    async def _verify_webhook(self, request: web.Request) -> web.Response:
        mode = request.query.get("hub.mode")
        token = request.query.get("hub.verify_token")
        challenge = request.query.get("hub.challenge")

        if mode == "subscribe" and token == self._verify_token:
            logger.info("Webhook verification successful.")
            return web.Response(text=challenge, content_type="text/plain")

        logger.warning(
            "Webhook verification failed: mode=%s, token=%s",
            mode,
            token,
        )
        return web.Response(status=403, text="Verification failed")

    async def _handle_webhook(self, request: web.Request) -> web.Response:
        if self._webhook_secret:
            signature = request.headers.get("X-Hub-Signature-256", "")
            body_bytes = await request.read()
            if not self._verify_signature(body_bytes, signature):
                logger.warning("Invalid webhook signature — rejecting request.")
                return web.Response(status=403, text="Invalid signature")
            try:
                body = json.loads(body_bytes)
            except json.JSONDecodeError:
                logger.error("Invalid JSON in webhook body.")
                return web.Response(status=400, text="Invalid JSON")
        else:
            try:
                body = await request.json()
            except json.JSONDecodeError:
                logger.error("Invalid JSON in webhook body.")
                return web.Response(status=400, text="Invalid JSON")

        asyncio.create_task(self._process_webhook_payload(body))

        return web.Response(status=200, text="OK")

    async def _health_check(self, request: web.Request) -> web.Response:
        return web.Response(
            text=json.dumps({"status": "ok", "channel": "whatsapp_business"}),
            content_type="application/json",
        )

    async def _process_webhook_payload(self, body: dict) -> None:
        if body.get("object") != "whatsapp_business_account":
            logger.debug("Ignoring non-WhatsApp webhook event.")
            return

        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                if change.get("field") != "messages":
                    continue

                value = change.get("value", {})
                messages = value.get("messages", [])

                for msg in messages:
                    await self._process_message(msg, value)

    async def _process_message(self, msg: dict, value: dict) -> None:
        msg_id = msg.get("id", "")

        if msg_id in self._processed_messages:
            logger.debug("Skipping duplicate message %s", msg_id)
            return
        self._processed_messages.add(msg_id)
        if len(self._processed_messages) > self._processed_messages_max:
            to_remove = list(self._processed_messages)[
                : self._processed_messages_max // 2
            ]
            self._processed_messages -= set(to_remove)

        sender = msg.get("from", "")
        msg_type = msg.get("type", "")
        timestamp = msg.get("timestamp", "")

        text: str | None = None
        audio_path: str | None = None
        image_path: str | None = None
        document_path: str | None = None
        message_type = "text"

        try:
            if msg_type == "text":
                message_type = "text"
                text = msg.get("text", {}).get("body", "")

            elif msg_type in ("audio", "voice"):
                message_type = "audio"
                media_id = msg.get("audio", {}).get("id") or msg.get("voice", {}).get("id")
                if media_id:
                    audio_path = await self._download_media(media_id, ext=".ogg")

            elif msg_type == "image":
                message_type = "image"
                media_id = msg.get("image", {}).get("id")
                text = msg.get("image", {}).get("caption")
                if media_id:
                    image_path = await self._download_media(media_id, ext=".jpg")

            elif msg_type == "document":
                message_type = "document"
                doc_data = msg.get("document", {})
                media_id = doc_data.get("id")
                text = doc_data.get("caption")
                filename = doc_data.get("filename", "document")
                ext = Path(filename).suffix or ".bin"
                if media_id:
                    document_path = await self._download_media(media_id, ext=ext)

            elif msg_type == "sticker":
                message_type = "image"
                media_id = msg.get("sticker", {}).get("id")
                if media_id:
                    image_path = await self._download_media(media_id, ext=".webp")

            elif msg_type == "location":
                message_type = "text"
                loc = msg.get("location", {})
                lat = loc.get("latitude", "")
                lng = loc.get("longitude", "")
                name = loc.get("name", "")
                text = f"Ubicacion: {name} ({lat}, {lng})" if name else f"Ubicacion: ({lat}, {lng})"

            elif msg_type == "contacts":
                message_type = "text"
                contacts = msg.get("contacts", [])
                parts = []
                for c in contacts:
                    name = c.get("name", {}).get("formatted_name", "?")
                    phones = [
                        p.get("phone", "") for p in c.get("phones", [])
                    ]
                    parts.append(f"{name}: {', '.join(phones)}")
                text = "Contactos compartidos:\n" + "\n".join(parts)

            else:
                message_type = "text"
                text = f"[Mensaje de tipo '{msg_type}' no soportado]"
                logger.info("Unsupported message type: %s", msg_type)

        except Exception:
            logger.exception("Error processing WhatsApp message %s", msg_id)
            return

        incoming = IncomingMessage(
            chat_id=sender,
            sender_id=sender,
            text=text,
            audio_path=audio_path,
            image_path=image_path,
            document_path=document_path,
            message_type=message_type,
            channel="whatsapp",
            raw=msg,
        )

        if self._handler is not None:
            try:
                await self._handler(incoming)
            except Exception:
                logger.exception(
                    "Error in message handler for WhatsApp message %s",
                    msg_id,
                )
        else:
            logger.warning(
                "No message handler registered — dropping WhatsApp message from %s",
                sender,
            )

    async def _upload_media(self, file_path: str, mime_type: str) -> str:
        self._ensure_client()

        url = f"{_BASE_URL}/{self._phone_number_id}/media"

        with open(file_path, "rb") as f:
            resp = await self._http_client.post(
                url,
                headers={"Authorization": f"Bearer {self._access_token}"},
                data={"messaging_product": "whatsapp"},
                files={"file": (Path(file_path).name, f, mime_type)},
            )

        if resp.status_code != 200:
            logger.error(
                "Media upload failed: %d %s", resp.status_code, resp.text
            )
            resp.raise_for_status()

        data = resp.json()
        media_id = data.get("id")
        if not media_id:
            raise RuntimeError(f"No media ID in upload response: {data}")

        logger.debug("Uploaded media %s -> %s", file_path, media_id)
        return media_id

    async def _download_media(self, media_id: str, ext: str = "") -> str:
        self._ensure_client()

        url_resp = await self._http_client.get(
            f"{_BASE_URL}/{media_id}",
            headers={"Authorization": f"Bearer {self._access_token}"},
        )
        if url_resp.status_code != 200:
            logger.error(
                "Failed to get media URL for %s: %d %s",
                media_id,
                url_resp.status_code,
                url_resp.text,
            )
            url_resp.raise_for_status()

        media_url = url_resp.json().get("url")
        if not media_url:
            raise RuntimeError(f"No URL in media response for {media_id}")

        dl_resp = await self._http_client.get(
            media_url,
            headers={"Authorization": f"Bearer {self._access_token}"},
        )
        if dl_resp.status_code != 200:
            logger.error(
                "Failed to download media from %s: %d",
                media_url,
                dl_resp.status_code,
            )
            dl_resp.raise_for_status()

        if not ext:
            content_type = dl_resp.headers.get("content-type", "")
            ext = mimetypes.guess_extension(content_type) or ".bin"

        local_path = os.path.join(self._temp_dir, f"{media_id}{ext}")
        with open(local_path, "wb") as f:
            f.write(dl_resp.content)

        logger.debug("Downloaded media %s -> %s", media_id, local_path)
        return local_path

    def _verify_signature(self, body: bytes, signature_header: str) -> bool:
        if not self._webhook_secret:
            return True

        if not signature_header.startswith("sha256="):
            return False

        expected_sig = signature_header[7:]  # strip "sha256="
        computed_sig = hmac.new(
            self._webhook_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected_sig, computed_sig)

    def _ensure_client(self) -> None:
        if self._http_client is None:
            raise RuntimeError(
                "WhatsApp channel is not running. Call start() first."
            )

    @staticmethod
    def _split_text(text: str) -> list[str]:
        if len(text) <= _MAX_TEXT_LENGTH:
            return [text]

        chunks: list[str] = []
        remaining = text

        while remaining:
            if len(remaining) <= _MAX_TEXT_LENGTH:
                chunks.append(remaining)
                break

            split_at = remaining.rfind("\n", 0, _MAX_TEXT_LENGTH)
            if split_at == -1:
                split_at = remaining.rfind(" ", 0, _MAX_TEXT_LENGTH)
            if split_at == -1:
                split_at = _MAX_TEXT_LENGTH

            chunks.append(remaining[:split_at])
            remaining = remaining[split_at:].lstrip("\n")

        return chunks
