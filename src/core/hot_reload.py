"""
Hot-reload system for the AI assistant.

Watches the entire src/ directory for changes to .py files.
When a file is modified (by Claude or manually), the corresponding
module is reloaded in-place without restarting the process.

This allows the assistant to fix its own code and have the
changes take effect immediately.

Safety:
- Only reloads modules under src/
- Never reloads main.py or this module (would break the reload loop)
- Logs all reloads to audit log
- If a reload fails, keeps the old version (no crash)
"""

from __future__ import annotations

import importlib
import sys
import time
import threading
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger("assistant.hot_reload")

# Modules that should NEVER be reloaded (would break the system)
_NEVER_RELOAD = {
    "src.main",
    "src.core.hot_reload",
}

# Root of the source code
_SRC_ROOT = Path(__file__).resolve().parent.parent  # src/


class HotReloader:
    """
    Watches src/ for .py file changes and reloads modules in-place.

    Usage::

        reloader = HotReloader()
        reloader.start()
        # ... later ...
        reloader.stop()
    """

    def __init__(self) -> None:
        self._observer: Any = None
        self._running = False
        self._reload_count = 0
        self._last_reload: dict[str, float] = {}  # debounce

    def start(self) -> None:
        """Start watching src/ for changes."""
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent

            class _Handler(FileSystemEventHandler):
                def __init__(self, reloader: HotReloader):
                    self._reloader = reloader

                def on_modified(self, event):
                    if not event.is_directory and event.src_path.endswith(".py"):
                        self._reloader._on_file_changed(event.src_path)

                def on_created(self, event):
                    if not event.is_directory and event.src_path.endswith(".py"):
                        self._reloader._on_file_changed(event.src_path)

            self._observer = Observer()
            self._observer.schedule(
                _Handler(self),
                str(_SRC_ROOT),
                recursive=True,
            )
            self._observer.daemon = True
            self._observer.start()
            self._running = True
            log.info("hot_reload.started", watching=str(_SRC_ROOT))

        except ImportError:
            log.warning("hot_reload.watchdog_not_available")
        except Exception:
            log.exception("hot_reload.start_failed")

    def stop(self) -> None:
        """Stop watching."""
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=5)
            except Exception:
                pass
            self._observer = None
        self._running = False
        log.info("hot_reload.stopped", total_reloads=self._reload_count)

    def _on_file_changed(self, filepath: str) -> None:
        """Called when a .py file under src/ is modified."""
        path = Path(filepath).resolve()

        # Must be under src/
        try:
            rel = path.relative_to(_SRC_ROOT)
        except ValueError:
            return

        # Convert file path to module name: src/core/gateway.py -> src.core.gateway
        parts = list(rel.parts)
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        else:
            parts[-1] = parts[-1].replace(".py", "")

        module_name = "src." + ".".join(parts)

        # Safety checks
        if module_name in _NEVER_RELOAD:
            log.debug("hot_reload.skip_protected", module=module_name)
            return

        # Debounce — don't reload the same module within 2 seconds
        now = time.time()
        last = self._last_reload.get(module_name, 0)
        if now - last < 2.0:
            return
        self._last_reload[module_name] = now

        # Skip __pycache__ files
        if "__pycache__" in filepath:
            return

        # Reload the module
        self._reload_module(module_name)

    def _reload_module(self, module_name: str) -> bool:
        """
        Reload a module in-place.

        Returns True if successful, False if the module wasn't loaded
        or if the reload failed.
        """
        if module_name not in sys.modules:
            log.debug("hot_reload.module_not_loaded", module=module_name)
            return False

        try:
            module = sys.modules[module_name]
            importlib.reload(module)
            self._reload_count += 1
            log.info(
                "hot_reload.reloaded",
                module=module_name,
                total_reloads=self._reload_count,
            )
            return True

        except Exception:
            # If reload fails, the old version stays in memory (safe)
            log.exception(
                "hot_reload.reload_failed",
                module=module_name,
            )
            return False

    @property
    def reload_count(self) -> int:
        """Total number of successful reloads since start."""
        return self._reload_count

    @property
    def is_running(self) -> bool:
        return self._running
