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
    """Normalised representation of a message received from any channel.

    Attributes:
        chat_id: Unique identifier for the conversation/chat.
        sender_id: Unique identifier for the message sender.
        text: Text content (None for non-text messages).
        audio_path: Local path to a downloaded audio file, if present.
        image_path: Local path to a downloaded image file, if present.
        document_path: Local path to a downloaded document, if present.
        message_type: One of ``'text'``, ``'audio'``, ``'image'``,
            ``'document'``.
        channel: Channel identifier, e.g. ``'telegram'``, ``'whatsapp'``.
        raw: The original, unmodified message object from the channel
            library — useful for accessing channel-specific features.
    """

    chat_id: str
    sender_id: str
    text: str | None
    audio_path: str | None
    image_path: str | None
    document_path: str | None
    message_type: str  # 'text', 'audio', 'image', 'document'
    channel: str  # 'telegram', 'whatsapp', ...
    raw: Any = field(default=None, repr=False)


# Type alias for the async callback that the assistant core provides.
MessageHandler = Callable[[IncomingMessage], Coroutine[Any, Any, None]]


class Channel(ABC):
    """Abstract messaging channel.

    Subclasses must implement every abstract method.  The assistant core
    calls ``set_message_handler`` once to register its callback, then
    ``start`` to begin receiving messages.
    """

    @abstractmethod
    async def start(self) -> None:
        """Start listening for incoming messages."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully shut down the channel."""
        ...

    @abstractmethod
    async def send_text(self, chat_id: str, text: str) -> None:
        """Send a text message to a chat."""
        ...

    @abstractmethod
    async def send_audio(self, chat_id: str, audio_path: str) -> None:
        """Send a voice/audio note to a chat."""
        ...

    @abstractmethod
    async def send_document(
        self, chat_id: str, path: str, caption: str = ""
    ) -> None:
        """Send a file/document to a chat."""
        ...

    @abstractmethod
    async def send_typing(self, chat_id: str) -> None:
        """Send a "typing…" indicator to a chat."""
        ...

    @abstractmethod
    def set_message_handler(self, handler: MessageHandler) -> None:
        """Register the callback invoked for every incoming message.

        The handler receives an ``IncomingMessage`` and should return
        once processing is complete.
        """
        ...
