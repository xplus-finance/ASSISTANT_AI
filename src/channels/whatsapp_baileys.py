"""WhatsApp channel via Baileys Node.js bridge.

WARNING: Uses unofficial WhatsApp Web protocol.
RISK: WhatsApp may ban the phone number used.
NEVER use your personal number — use a virtual/dedicated number only.

Architecture:
    Python (this module) <--HTTP--> Node.js bridge (whatsapp-bridge/)
    The bridge runs Baileys and exposes a REST API on localhost:3001.
    This channel polls the bridge for incoming messages and forwards
    outgoing messages via POST requests.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from src.channels.base import Channel, IncomingMessage, MessageHandler

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 1.0  # seconds between message polls


class WhatsAppBaileysChannel(Channel):
    """WhatsApp channel using a local Baileys Node.js bridge.

    The bridge must be running before calling ``start()``.
    See ``whatsapp-bridge/README.md`` for setup instructions.

    Args:
        bridge_url: Base URL of the Baileys bridge (default localhost:3001).
        authorized_phone: Phone number (with country code, no +) that is
            allowed to interact with the assistant. Messages from any
            other number are silently ignored.
    """

    def __init__(
        self,
        bridge_url: str = "http://127.0.0.1:3001",
        authorized_phone: str = "",
    ) -> None:
        if not authorized_phone:
            raise ValueError(
                "authorized_phone is required. "
                "Provide the phone number (with country code) that will "
                "interact with the assistant, e.g. '5491112345678'."
            )

        self._bridge_url = bridge_url.rstrip("/")
        self._authorized_phone = authorized_phone
        self._handler: MessageHandler | None = None
        self._session: aiohttp.ClientSession | None = None
        self._poll_task: asyncio.Task[None] | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Channel interface
    # ------------------------------------------------------------------

    def set_message_handler(self, handler: MessageHandler) -> None:
        """Register the async callback for incoming messages."""
        self._handler = handler

    async def start(self) -> None:
        """Connect to the Baileys bridge and start polling for messages."""
        logger.info("Connecting to Baileys bridge at %s …", self._bridge_url)

        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10)
        )

        # Verify the bridge is reachable
        if not await self._check_bridge():
            await self._session.close()
            self._session = None
            raise ConnectionError(
                f"Baileys bridge not reachable at {self._bridge_url}. "
                "Make sure the bridge is running: "
                "cd whatsapp-bridge && npm start"
            )

        self._running = True
        self._poll_task = asyncio.create_task(
            self._poll_messages(), name="whatsapp-baileys-poll"
        )
        logger.info(
            "WhatsApp Baileys channel started. "
            "Authorized phone: %s", self._authorized_phone
        )

    async def stop(self) -> None:
        """Stop polling and close the HTTP session."""
        logger.info("Stopping WhatsApp Baileys channel…")
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

        logger.info("WhatsApp Baileys channel stopped.")

    async def send_text(self, chat_id: str, text: str) -> None:
        """Send a text message through the bridge."""
        await self._post("/send/text", {"phone": chat_id, "message": text})

    async def send_audio(self, chat_id: str, audio_path: str) -> None:
        """Send an audio file through the bridge."""
        await self._post(
            "/send/audio", {"phone": chat_id, "audioPath": audio_path}
        )

    async def send_document(
        self, chat_id: str, path: str, caption: str = ""
    ) -> None:
        """Send a document through the bridge."""
        await self._post(
            "/send/document",
            {"phone": chat_id, "path": path, "caption": caption},
        )

    async def send_typing(self, chat_id: str) -> None:
        """Send a typing/composing indicator through the bridge."""
        await self._post("/send/typing", {"phone": chat_id})

    # ------------------------------------------------------------------
    # Internal: bridge communication
    # ------------------------------------------------------------------

    async def _check_bridge(self) -> bool:
        """Return True if the bridge is running and reachable."""
        try:
            async with self._session.get(  # type: ignore[union-attr]
                f"{self._bridge_url}/health"
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    status = data.get("status", "unknown")
                    logger.info("Bridge health: %s", status)
                    return True
                return False
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return False

    async def _post(self, path: str, payload: dict[str, Any]) -> dict:
        """POST JSON to the bridge and return the response body."""
        if self._session is None:
            raise RuntimeError(
                "WhatsApp Baileys channel is not running. Call start() first."
            )

        url = f"{self._bridge_url}{path}"
        try:
            async with self._session.post(url, json=payload) as resp:
                body = await resp.json()
                if resp.status != 200:
                    logger.error(
                        "Bridge error %d on %s: %s", resp.status, path, body
                    )
                return body
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.error("Failed to reach bridge at %s: %s", url, exc)
            raise ConnectionError(
                f"Bridge unreachable at {url}"
            ) from exc

    async def _poll_messages(self) -> None:
        """Continuously poll the bridge for new incoming messages."""
        logger.debug("Message polling started (interval=%.1fs)", _POLL_INTERVAL)

        while self._running:
            try:
                await self._fetch_and_dispatch()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Error polling messages from bridge")

            await asyncio.sleep(_POLL_INTERVAL)

    async def _fetch_and_dispatch(self) -> None:
        """Fetch queued messages from the bridge and dispatch them."""
        if self._session is None:
            return

        try:
            async with self._session.get(
                f"{self._bridge_url}/messages"
            ) as resp:
                if resp.status != 200:
                    return
                messages = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return

        if not messages:
            return

        for msg in messages:
            sender = msg.get("from", "")
            # Normalize: remove @s.whatsapp.net suffix if present
            sender_clean = sender.split("@")[0]

            # Only process messages from the authorized phone
            if sender_clean != self._authorized_phone:
                logger.debug(
                    "Ignoring message from unauthorized number: %s",
                    sender_clean,
                )
                continue

            await self._dispatch_message(msg, sender_clean)

    async def _dispatch_message(
        self, msg: dict[str, Any], sender: str
    ) -> None:
        """Convert a bridge message dict to IncomingMessage and dispatch."""
        text = msg.get("text")
        audio_path = msg.get("audioPath")
        image_path = msg.get("imagePath")
        document_path = msg.get("documentPath")

        # Determine message type
        if audio_path:
            message_type = "audio"
        elif image_path:
            message_type = "image"
        elif document_path:
            message_type = "document"
        else:
            message_type = "text"

        incoming = IncomingMessage(
            chat_id=sender,
            sender_id=sender,
            text=text,
            audio_path=audio_path,
            image_path=image_path,
            document_path=document_path,
            message_type=message_type,
            channel="whatsapp_baileys",
            raw=msg,
        )

        if self._handler is not None:
            try:
                await self._handler(incoming)
            except Exception:
                logger.exception(
                    "Error in message handler for message from %s", sender
                )
        else:
            logger.warning(
                "No message handler registered — dropping message from %s",
                sender,
            )
