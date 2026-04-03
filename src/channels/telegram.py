"""Telegram Bot channel via python-telegram-bot v20+ long-polling."""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler as TGMessageHandler,
    filters,
)

from src.channels.base import Channel, IncomingMessage, MessageHandler

logger = logging.getLogger(__name__)

_MAX_TEXT_LENGTH = 4096


class TelegramChannel(Channel):
    def __init__(self, token: str) -> None:
        if not token or not token.strip():
            raise ValueError("Telegram bot token must not be empty.")

        self._token = token
        self._app: Application | None = None
        self._handler: MessageHandler | None = None
        self._temp_dir = tempfile.mkdtemp(prefix="tg_downloads_")

    def set_message_handler(self, handler: MessageHandler) -> None:
        self._handler = handler

    async def start(self) -> None:
        logger.info("Starting Telegram bot (polling)…")

        self._app = (
            Application.builder()
            .token(self._token)
            .build()
        )

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
        self._app.add_handler(CallbackQueryHandler(self._handle_callback_query))

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram bot is now polling for updates.")

    async def stop(self) -> None:
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
        if self._app is None:
            raise RuntimeError("Telegram bot is not running.")

        chunks = self._split_text(text)
        for chunk in chunks:
            try:
                await self._app.bot.send_message(
                    chat_id=int(chat_id), text=chunk, parse_mode="Markdown"
                )
            except Exception:
                await self._app.bot.send_message(
                    chat_id=int(chat_id), text=chunk
                )

    async def send_audio(self, chat_id: str, audio_path: str) -> None:
        if self._app is None:
            raise RuntimeError("Telegram bot is not running.")

        audio_bytes = await asyncio.to_thread(Path(audio_path).read_bytes)
        await self._app.bot.send_voice(
            chat_id=int(chat_id),
            voice=audio_bytes,
        )

    async def send_photo(self, chat_id: str, photo_path: str, caption: str = "") -> None:
        await self.send_document(chat_id, photo_path, caption=caption)

    async def send_document(
        self, chat_id: str, path: str, caption: str = ""
    ) -> None:
        if self._app is None:
            raise RuntimeError("Telegram bot is not running.")

        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"Document file not found: {path}")

        doc_bytes = await asyncio.to_thread(p.read_bytes)
        filename = p.name
        logger.info("telegram.sending_document", path=path, size=len(doc_bytes),
                 filename=filename)
        await self._app.bot.send_document(
            chat_id=int(chat_id),
            document=doc_bytes,
            caption=caption or None,
            filename=filename,
        )
        logger.info("telegram.document_sent", chat_id=chat_id, filename=filename)

    async def send_typing(self, chat_id: str) -> None:
        if self._app is None:
            return
        await self._app.bot.send_chat_action(
            chat_id=int(chat_id),
            action=ChatAction.TYPING,
        )

    async def _handle_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
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

        elif msg.photo:
            message_type = "image"
            photo = msg.photo[-1]
            tg_file = await photo.get_file()
            image_path = os.path.join(
                self._temp_dir, f"{tg_file.file_unique_id}.jpg"
            )
            await tg_file.download_to_drive(image_path)
            text = msg.caption
            logger.debug("Downloaded photo to %s", image_path)

        elif msg.document:
            message_type = "document"
            tg_file = await msg.document.get_file()
            filename = msg.document.file_name or tg_file.file_unique_id
            filename = os.path.basename(filename)
            document_path = os.path.join(self._temp_dir, filename)
            await tg_file.download_to_drive(document_path)
            text = msg.caption
            logger.debug("Downloaded document to %s", document_path)

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

    async def edit_text(
        self, chat_id: str | int, message_id: int, text: str, parse_mode: str = "Markdown",
    ) -> bool:
        if self._app is None:
            return False
        try:
            await self._app.bot.edit_message_text(
                chat_id=int(chat_id), message_id=message_id,
                text=text, parse_mode=parse_mode,
            )
            return True
        except Exception as exc:
            if "message is not modified" in str(exc).lower():
                return True  # content already matches
            logger.warning("telegram.edit_text_failed: %s", exc)
            return False

    async def send_text_with_buttons(
        self,
        chat_id: str | int,
        text: str,
        buttons: list[list[tuple[str, str]]],
        parse_mode: str = "Markdown",
    ) -> int | None:
        if self._app is None:
            return None
        keyboard = [
            [InlineKeyboardButton(label, callback_data=data) for label, data in row]
            for row in buttons
        ]
        try:
            msg = await self._app.bot.send_message(
                chat_id=int(chat_id), text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=parse_mode,
            )
            return msg.message_id
        except Exception:
            msg = await self._app.bot.send_message(
                chat_id=int(chat_id), text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            return msg.message_id

    async def _handle_callback_query(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        query = update.callback_query
        if query is None:
            return
        await query.answer()
        chat_id = str(query.message.chat_id) if query.message else "0"
        sender_id = str(query.from_user.id) if query.from_user else chat_id
        incoming = IncomingMessage(
            chat_id=chat_id, sender_id=sender_id,
            text=query.data, audio_path=None, image_path=None,
            document_path=None, message_type="callback",
            channel="telegram", raw=update,
        )
        if self._handler is not None:
            await self._handler(incoming)

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

            # Try splitting at double newline, then single newline, then space
            split_at = -1
            for sep in ("\n\n", "\n", " "):
                candidate = remaining.rfind(sep, 0, _MAX_TEXT_LENGTH)
                if candidate == -1:
                    continue
                # Don't split inside a code block (count ``` fences)
                fence_count = remaining[:candidate].count("```")
                if fence_count % 2 == 0:  # even = outside code block
                    split_at = candidate
                    break

            if split_at == -1:
                split_at = _MAX_TEXT_LENGTH

            chunks.append(remaining[:split_at])
            remaining = remaining[split_at:].lstrip("\n")

        return chunks
