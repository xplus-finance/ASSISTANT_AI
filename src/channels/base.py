"""Abstract base class for messaging channels.

Every messaging integration (Telegram, WhatsApp, etc.) must subclass
``Channel`` and implement all abstract methods so the assistant core
can interact with any channel uniformly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine


@dataclass
class IncomingMessage:
    """Normalised representation of a message received from any channel."""

    chat_id: str
    sender_id: str
    text: str | None
    audio_path: str | None
    image_path: str | None
    document_path: str | None
    message_type: str  # 'text', 'audio', 'image', 'document'
    channel: str  # 'telegram', 'whatsapp', ...
    raw: Any = field(default=None, repr=False)


MessageHandler = Callable[[IncomingMessage], Coroutine[Any, Any, None]]


class Channel(ABC):
    """Abstract messaging channel."""

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def send_text(self, chat_id: str, text: str) -> None: ...

    @abstractmethod
    async def send_audio(self, chat_id: str, audio_path: str) -> None: ...

    @abstractmethod
    async def send_document(self, chat_id: str, path: str, caption: str = "") -> None: ...

    @abstractmethod
    async def send_typing(self, chat_id: str) -> None: ...

    @abstractmethod
    def set_message_handler(self, handler: MessageHandler) -> None: ...
