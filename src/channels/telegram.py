"""Telegram Bot channel implementation using python-telegram-bot v20+.

Uses long-polling (no webhooks, no open ports) to receive messages.
Supports text, voice, image, and document messages.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler as TGMessageHandler,
    filters,
)

from src.channels.base import Channel, IncomingMessage, MessageHandler

logger = logging.getLogger(__name__)

# Telegram's maximum text message length
_MAX_TEXT_LENGTH = 4096


class TelegramChannel(Channel):
    """Telegram Bot channel.

    Args:
        token: Telegram Bot API token (from @BotFather).
    """

    def __init__(self, token: str) -> None:
        if not token or not token.strip():
            raise ValueError("Telegram bot token must not be empty.")

        self._token = token
        self._app: Application | None = None
        self._handler: MessageHandler | None = None
        self._temp_dir = tempfile.mkdtemp(prefix="tg_downloads_")

    # ------------------------------------------------------------------
    # Channel interface
    # ------------------------------------------------------------------

    def set_message_handler(self, handler: MessageHandler) -> None:
        """Register the async callback for incoming messages."""
        self._handler = handler

    async def start(self) -> None:
        """Build and start the Telegram bot with long-polling."""
        logger.info("Starting Telegram bot (polling)…")

        self._app = (
            Application.builder()
            .token(self._token)
            .build()
        )

        # Register a catch-all handler for text, voice, photo, and documents
        self._app.add_handler(
            TGMessageHandler(
                filters.TEXT
                | filters.VOICE
                | filters.AUDIO
                | filters.PHOTO
                | filters.Document.ALL,
                self._handle_message,
            )
        )

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram bot is now polling for updates.")

    async def stop(self) -> None:
        """Gracefully stop the bot."""
        if self._app is None:
            return
        logger.info("Stopping Telegram bot…")
        if self._app.updater and self._app.updater.running:
            await self._app.updater.stop()
        await self._app.stop()
        await self._app.shutdown()
        self._app = None
        logger.info("Telegram bot stopped.")

    async def send_text(self, chat_id: str, text: str) -> None:
        """Send a text message, auto-splitting if it exceeds 4096 chars."""
        if self._app is None:
            raise RuntimeError("Telegram bot is not running.")

        chunks = self._split_text(text)
        for chunk in chunks:
            await self._app.bot.send_message(
                chat_id=int(chat_id),
                text=chunk,
            )

    async def send_audio(self, chat_id: str, audio_path: str) -> None:
        """Send a voice note (.ogg opus) to a chat."""
        if self._app is None:
            raise RuntimeError("Telegram bot is not running.")

        with open(audio_path, "rb") as audio_file:
            await self._app.bot.send_voice(
                chat_id=int(chat_id),
                voice=audio_file,
            )

    async def send_document(
        self, chat_id: str, path: str, caption: str = ""
    ) -> None:
        """Send a file/document to a chat."""
        if self._app is None:
            raise RuntimeError("Telegram bot is not running.")

        with open(path, "rb") as doc_file:
            await self._app.bot.send_document(
                chat_id=int(chat_id),
                document=doc_file,
                caption=caption or None,
            )

    async def send_typing(self, chat_id: str) -> None:
        """Send a typing indicator."""
        if self._app is None:
            return
        await self._app.bot.send_chat_action(
            chat_id=int(chat_id),
            action=ChatAction.TYPING,
        )

    # ------------------------------------------------------------------
    # Internal message handling
    # ------------------------------------------------------------------

    async def _handle_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Process an incoming Telegram update and forward to the handler."""
        if update.message is None:
            return

        msg = update.message
        chat_id = str(msg.chat_id)
        sender_id = str(msg.from_user.id) if msg.from_user else chat_id

        text: str | None = None
        audio_path: str | None = None
        image_path: str | None = None
        document_path: str | None = None
        message_type = "text"

        # --- Voice message ---
        if msg.voice or msg.audio:
            message_type = "audio"
            file_obj = msg.voice or msg.audio
            tg_file = await file_obj.get_file()
            ext = ".ogg" if msg.voice else ".mp3"
            audio_path = os.path.join(
                self._temp_dir, f"{tg_file.file_unique_id}{ext}"
            )
            await tg_file.download_to_drive(audio_path)
            logger.debug("Downloaded voice to %s", audio_path)

        # --- Photo ---
        elif msg.photo:
            message_type = "image"
            # Telegram sends multiple sizes; grab the largest
            photo = msg.photo[-1]
            tg_file = await photo.get_file()
            image_path = os.path.join(
                self._temp_dir, f"{tg_file.file_unique_id}.jpg"
            )
            await tg_file.download_to_drive(image_path)
            text = msg.caption
            logger.debug("Downloaded photo to %s", image_path)

        # --- Document ---
        elif msg.document:
            message_type = "document"
            tg_file = await msg.document.get_file()
            filename = msg.document.file_name or tg_file.file_unique_id
            document_path = os.path.join(self._temp_dir, filename)
            await tg_file.download_to_drive(document_path)
            text = msg.caption
            logger.debug("Downloaded document to %s", document_path)

        # --- Plain text ---
        elif msg.text:
            message_type = "text"
            text = msg.text

        incoming = IncomingMessage(
            chat_id=chat_id,
            sender_id=sender_id,
            text=text,
            audio_path=audio_path,
            image_path=image_path,
            document_path=document_path,
            message_type=message_type,
            channel="telegram",
            raw=update,
        )

        if self._handler is not None:
            await self._handler(incoming)
        else:
            logger.warning(
                "No message handler registered — dropping message from %s",
                sender_id,
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _split_text(text: str) -> list[str]:
        """Split text into chunks of at most _MAX_TEXT_LENGTH chars.

        Tries to split on newline boundaries first, then falls back
        to hard splitting.
        """
        if len(text) <= _MAX_TEXT_LENGTH:
            return [text]

        chunks: list[str] = []
        remaining = text

        while remaining:
            if len(remaining) <= _MAX_TEXT_LENGTH:
                chunks.append(remaining)
                break

            # Try to find a newline to split on
            split_at = remaining.rfind("\n", 0, _MAX_TEXT_LENGTH)
            if split_at == -1:
                # No newline — try space
                split_at = remaining.rfind(" ", 0, _MAX_TEXT_LENGTH)
            if split_at == -1:
                # Hard split
                split_at = _MAX_TEXT_LENGTH

            chunks.append(remaining[:split_at])
            remaining = remaining[split_at:].lstrip("\n")

        return chunks
