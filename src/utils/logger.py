"""Structured logging with separate security and audit channels."""

import logging
import logging.handlers
import os
import sys
from pathlib import Path

import structlog


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = _PROJECT_ROOT / "logs"


def _ensure_log_dir() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _get_file_handler(filename: str, level: int = logging.DEBUG) -> logging.FileHandler:
    _ensure_log_dir()
    handler = logging.FileHandler(LOG_DIR / filename, encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(message)s"))
    return handler


def _get_stream_handler(level: int = logging.INFO) -> logging.StreamHandler:
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(message)s"))
    return handler


def setup_logging(log_level: str = "INFO", json_output: bool = False) -> None:
    _ensure_log_dir()
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if json_output:
        # Production: JSON lines
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        # Development: colored, human-readable
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Formatter that structlog's stdlib integration uses
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    root = logging.getLogger()
    root.setLevel(numeric_level)
    root.handlers.clear()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    console.setLevel(numeric_level)
    root.addHandler(console)

    app_logger = logging.getLogger("assistant.app")
    app_handler = _get_file_handler("app.log", numeric_level)
    app_handler.setFormatter(formatter)
    app_logger.addHandler(app_handler)
    app_logger.propagate = True

    sec_logger = logging.getLogger("assistant.security")
    sec_handler = _get_file_handler("security.log", logging.WARNING)
    sec_handler.setFormatter(formatter)
    sec_logger.addHandler(sec_handler)
    sec_logger.propagate = True

    audit_logger = logging.getLogger("assistant.audit")
    audit_handler = _get_file_handler("audit.log", logging.INFO)
    audit_handler.setFormatter(formatter)
    audit_logger.addHandler(audit_handler)
    audit_logger.propagate = True



def get_app_logger() -> structlog.stdlib.BoundLogger:
    return structlog.get_logger("assistant.app")


def get_security_logger() -> structlog.stdlib.BoundLogger:
    return structlog.get_logger("assistant.security")


def get_audit_logger() -> structlog.stdlib.BoundLogger:
    return structlog.get_logger("assistant.audit")
