"""
Structured logging configuration for the AI assistant.

Uses structlog for structured logging with separate log files for
security events, audit trail, and general application logs.
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path

import structlog


# Base log directory — resolved relative to project root
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = _PROJECT_ROOT / "logs"


def _ensure_log_dir() -> None:
    """Create logs directory if it doesn't exist."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _get_file_handler(filename: str, level: int = logging.DEBUG) -> logging.FileHandler:
    """
    Create a file handler for the given log file.

    No rotation is configured — systemd journal handles log rotation
    at the OS level.
    """
    _ensure_log_dir()
    handler = logging.FileHandler(LOG_DIR / filename, encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(message)s"))
    return handler


def _get_stream_handler(level: int = logging.INFO) -> logging.StreamHandler:
    """Create a stream handler for stdout."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(message)s"))
    return handler


def setup_logging(log_level: str = "INFO", json_output: bool = False) -> None:
    """
    Configure structlog and stdlib logging for the entire application.

    Args:
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_output: If True, output JSON (production). If False, pretty console output (dev).
    """
    _ensure_log_dir()
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # --- Shared structlog processors ---
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

    # ── Root logger ──────────────────────────────────────────────
    root = logging.getLogger()
    root.setLevel(numeric_level)
    # Remove any existing handlers to avoid duplicates on re-init
    root.handlers.clear()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    console.setLevel(numeric_level)
    root.addHandler(console)

    # ── App logger → logs/app.log ────────────────────────────────
    app_logger = logging.getLogger("assistant.app")
    app_handler = _get_file_handler("app.log", numeric_level)
    app_handler.setFormatter(formatter)
    app_logger.addHandler(app_handler)
    app_logger.propagate = True

    # ── Security logger → logs/security.log ──────────────────────
    sec_logger = logging.getLogger("assistant.security")
    sec_handler = _get_file_handler("security.log", logging.WARNING)
    sec_handler.setFormatter(formatter)
    sec_logger.addHandler(sec_handler)
    sec_logger.propagate = True

    # ── Audit logger → logs/audit.log ────────────────────────────
    audit_logger = logging.getLogger("assistant.audit")
    audit_handler = _get_file_handler("audit.log", logging.INFO)
    audit_handler.setFormatter(formatter)
    audit_logger.addHandler(audit_handler)
    audit_logger.propagate = True


# ── Convenience accessors ────────────────────────────────────────

def get_app_logger() -> structlog.stdlib.BoundLogger:
    """Return the structured app logger."""
    return structlog.get_logger("assistant.app")


def get_security_logger() -> structlog.stdlib.BoundLogger:
    """Return the structured security logger (logs/security.log)."""
    return structlog.get_logger("assistant.security")


def get_audit_logger() -> structlog.stdlib.BoundLogger:
    """Return the structured audit logger (logs/audit.log)."""
    return structlog.get_logger("assistant.audit")
