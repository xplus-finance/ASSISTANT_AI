"""Application entry point."""

from __future__ import annotations

import asyncio
import os
import signal
import stat
import sys
import traceback
from pathlib import Path

from pydantic_settings import BaseSettings

from src.utils.platform import IS_WINDOWS


class Settings(BaseSettings):
    """Application configuration from environment or .env file."""

    telegram_bot_token: str
    authorized_chat_id: int
    security_pin: str = ""

    claude_cli_path: str = "claude"
    claude_max_turns: int = 20
    claude_timeout: int = 480

    projects_base_dir: str = str(Path.home()) if IS_WINDOWS else "/home"
    data_dir: str = "data"
    skills_dir: str = "skills"
    logs_dir: str = "logs"

    max_messages_per_minute: int = 20
    require_approval: bool = True

    whisper_model: str = "medium"
    tts_engine: str = "auto"
    tts_voice_pitch: int = -4
    tts_voice_speed: float = 1.55
    tts_voice_gender: str = "male"

    db_encryption_key: str = ""

    # Desktop pet
    pet_enabled: str = "false"
    pet_type: str = "dog"
    pet_size: int = 96
    pet_monitor: int = 0

    timezone: str = "America/New_York"
    log_level: str = "INFO"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


_shutdown_event: asyncio.Event | None = None


async def _shutdown(gateway: object) -> None:
    try:
        await gateway.stop()  # type: ignore[attr-defined]
    except Exception:
        traceback.print_exc()
    finally:
        if _shutdown_event is not None:
            _shutdown_event.set()


async def main() -> None:
    global _shutdown_event
    _shutdown_event = asyncio.Event()

    try:
        settings = Settings()  # type: ignore[call-arg]
    except Exception as exc:
        print(
            f"[FATAL] Failed to load settings: {exc}\n"
            "Make sure TELEGRAM_BOT_TOKEN and AUTHORIZED_CHAT_ID are set "
            "in the environment or .env file.",
            file=sys.stderr,
        )
        sys.exit(1)

    from src.utils.logger import setup_logging
    setup_logging(settings.log_level)

    import structlog
    log = structlog.get_logger("assistant.main")
    log.info(
        "main.settings_loaded",
        log_level=settings.log_level,
        timezone=settings.timezone,
        data_dir=settings.data_dir,
    )

    for directory in (settings.data_dir, settings.logs_dir, settings.skills_dir):
        Path(directory).mkdir(parents=True, exist_ok=True)

    if not IS_WINDOWS:
        _OWNER_ONLY_DIR = stat.S_IRWXU  # 700
        _OWNER_ONLY_FILE = stat.S_IRUSR | stat.S_IWUSR  # 600
        for d in (settings.data_dir, settings.logs_dir):
            try:
                os.chmod(d, _OWNER_ONLY_DIR)
            except OSError:
                pass
        env_file = Path(".env")
        if env_file.exists():
            try:
                os.chmod(env_file, _OWNER_ONLY_FILE)
            except OSError:
                pass
        db_file = Path(settings.data_dir) / "assistant.db"
        if db_file.exists():
            try:
                os.chmod(db_file, _OWNER_ONLY_FILE)
            except OSError:
                pass

    from src.core.gateway import Gateway
    gateway = Gateway(settings)

    if IS_WINDOWS:
        def _win_handler(signum, frame):
            asyncio.ensure_future(_handle_signal(signal.Signals(signum), gateway, log))

        signal.signal(signal.SIGINT, _win_handler)
        signal.signal(signal.SIGTERM, _win_handler)
    else:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(_handle_signal(s, gateway, log)),
            )

    try:
        await gateway.start()
    except asyncio.CancelledError:
        log.info("main.cancelled")
    except Exception:
        log.exception("main.fatal_error")
        sys.exit(1)
    finally:
        if gateway._running:
            await gateway.stop()
        log.info("main.exited")


async def _handle_signal(sig: signal.Signals, gateway: object, log: object) -> None:
    log.info("main.signal_received", signal=sig.name)  # type: ignore[attr-defined]
    await _shutdown(gateway)


def run() -> None:
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
