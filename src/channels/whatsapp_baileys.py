"""WhatsApp channel via Baileys Node.js bridge.

WARNING: Uses unofficial WhatsApp Web protocol.
RISK: WhatsApp may ban the phone number used.
NEVER use your personal number \u2014 use a virtual/dedicated number only.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from src.channels.base import Channel, IncomingMessage, MessageHandler

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 1.0


class WhatsAppBaileysChannel(Channel):
    def __init__(self, bridge_url: str = "http://127.0.0.1:3001", authorized_phone: str = "") -> None:
        if not authorized_phone:
            raise ValueError("authorized_phone is required.")
        self._bridge_url = bridge_url.rstrip("/")
        self._authorized_phone = authorized_phone
        self._handler: MessageHandler | None = None
        self._session: aiohttp.ClientSession | None = None
        self._poll_task: asyncio.Task[None] | None = None
        self._running = False

    def set_message_handler(self, handler: MessageHandler) -> None:
        self._handler = handler

    async def start(self) -> None:
        logger.info("Connecting to Baileys bridge at %s", self._bridge_url)
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        if not await self._check_bridge():
            await self._session.close()
            self._session = None
            raise ConnectionError(f"Baileys bridge not reachable at {self._bridge_url}.")
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_messages(), name="whatsapp-baileys-poll")
        logger.info("WhatsApp Baileys channel started. Authorized phone: %s", self._authorized_phone)

    async def stop(self) -> None:
        logger.info("Stopping WhatsApp Baileys channel")
        self._running = False
        if self._poll_task is not None:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def send_text(self, chat_id: str, text: str) -> None:
        await self._post("/send/text", {"phone": chat_id, "message": text})

    async def send_audio(self, chat_id: str, audio_path: str) -> None:
        await self._post("/send/audio", {"phone": chat_id, "audioPath": audio_path})

    async def send_document(self, chat_id: str, path: str, caption: str = "") -> None:
        await self._post("/send/document", {"phone": chat_id, "path": path, "caption": caption})

    async def send_typing(self, chat_id: str) -> None:
        await self._post("/send/typing", {"phone": chat_id})

    async def _check_bridge(self) -> bool:
        try:
            async with self._session.get(f"{self._bridge_url}/health") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logger.info("Bridge health: %s", data.get("status", "unknown"))
                    return True
                return False
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return False

    async def _post(self, path: str, payload: dict[str, Any]) -> dict:
        if self._session is None:
            raise RuntimeError("WhatsApp Baileys channel is not running.")
        url = f"{self._bridge_url}{path}"
        try:
            async with self._session.post(url, json=payload) as resp:
                body = await resp.json()
                if resp.status != 200:
                    logger.error("Bridge error %d on %s: %s", resp.status, path, body)
                return body
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.error("Failed to reach bridge at %s: %s", url, exc)
            raise ConnectionError(f"Bridge unreachable at {url}") from exc

    async def _poll_messages(self) -> None:
        while self._running:
            try:
                await self._fetch_and_dispatch()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Error polling messages from bridge")
            await asyncio.sleep(_POLL_INTERVAL)

    async def _fetch_and_dispatch(self) -> None:
        if self._session is None:
            return
        try:
            async with self._session.get(f"{self._bridge_url}/messages") as resp:
                if resp.status != 200:
                    return
                messages = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return
        if not messages:
            return
        for msg in messages:
            sender = msg.get("from", "")
            sender_clean = sender.split("@")[0]
            if sender_clean != self._authorized_phone:
                continue
            await self._dispatch_message(msg, sender_clean)

    async def _dispatch_message(self, msg: dict[str, Any], sender: str) -> None:
        text = msg.get("text")
        audio_path = msg.get("audioPath")
        image_path = msg.get("imagePath")
        document_path = msg.get("documentPath")
        if audio_path:
            message_type = "audio"
        elif image_path:
            message_type = "image"
        elif document_path:
            message_type = "document"
        else:
            message_type = "text"
        incoming = IncomingMessage(
            chat_id=sender, sender_id=sender, text=text,
            audio_path=audio_path, image_path=image_path,
            document_path=document_path, message_type=message_type,
            channel="whatsapp_baileys", raw=msg,
        )
        if self._handler is not None:
            try:
                await self._handler(incoming)
            except Exception:
                logger.exception("Error in message handler for message from %s", sender)
        else:
            logger.warning("No message handler registered")
