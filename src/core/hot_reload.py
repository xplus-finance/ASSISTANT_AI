"""Hot-reload watcher for src/ Python modules."""

from __future__ import annotations

import ast
import importlib
import os
import shutil
import sys
import time
import threading
from pathlib import Path
from typing import Any

import structlog

from src.utils.platform import IS_WINDOWS

log = structlog.get_logger("assistant.hot_reload")

_NEVER_RELOAD = {
    "src.main",
    "src.core.hot_reload",
}

_CORE_MODULES = {
    "src.core.gateway",
    "src.core.claude_bridge",
    "src.core.security",
    "src.core.context_builder",
    "src.core.executor",
    "src.core.desktop_control",
    "src.memory.engine",
    "src.channels.telegram",
}

_SRC_ROOT = Path(__file__).resolve().parent.parent  # src/
_BACKUP_DIR = _SRC_ROOT.parent / ".backups"


def _validate_syntax(filepath: str) -> bool:

    try:
        source = Path(filepath).read_text(encoding="utf-8")
        ast.parse(source)
        return True
    except (SyntaxError, UnicodeDecodeError) as e:
        log.error("hot_reload.syntax_error", file=filepath, error=str(e))
        return False


def _backup_file(filepath: str) -> str | None:

    try:
        _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        src = Path(filepath)
        # Use relative path for backup name
        try:
            rel = src.relative_to(_SRC_ROOT.parent)
        except ValueError:
            rel = src
        backup = _BACKUP_DIR / f"{rel.as_posix().replace('/', '_')}.bak"
        shutil.copy2(filepath, backup)
        return str(backup)
    except Exception:
        log.warning("hot_reload.backup_failed", file=filepath)
        return None


def restart_process() -> None:

    log.info("hot_reload.restarting_process")

    # Give a moment for logs to flush
    time.sleep(0.5)

    python = sys.executable
    args = [python, "-m", "src.main"]

    if IS_WINDOWS:
        # Windows: os.execv is emulated, works but differently
        # Spawn detached process and exit
        import subprocess
        subprocess.Popen(
            args,
            cwd=str(_SRC_ROOT.parent),
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
        )
        os._exit(0)
    else:
        # Linux/Mac: replace current process
        os.chdir(str(_SRC_ROOT.parent))
        os.execv(python, args)


class HotReloader:


    def __init__(self) -> None:
        self._observer: Any = None
        self._running = False
        self._reload_count = 0
        self._restart_count = 0
        self._last_reload: dict[str, float] = {}  # debounce

    def start(self) -> None:
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

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
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=5)
            except Exception:
                pass
            self._observer = None
        self._running = False
        log.info("hot_reload.stopped", total_reloads=self._reload_count,
                 total_restarts=self._restart_count)

    def _on_file_changed(self, filepath: str) -> None:
        path = Path(filepath).resolve()

        # Must be under src/
        try:
            rel = path.relative_to(_SRC_ROOT)
        except ValueError:
            return

        # Skip __pycache__ files
        if "__pycache__" in filepath:
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

        # Validate syntax BEFORE doing anything
        if not _validate_syntax(filepath):
            log.warning("hot_reload.invalid_syntax_skipping",
                        module=module_name, file=filepath)
            return

        # Backup the file
        _backup_file(filepath)

        # Core modules: trigger restart instead of reload
        if module_name in _CORE_MODULES:
            log.info("hot_reload.core_module_changed_restarting",
                     module=module_name)
            self._restart_count += 1
            # Run restart in a separate thread to not block the watcher
            threading.Thread(target=restart_process, daemon=True).start()
            return

        # Non-core modules: reload in-place
        self._reload_module(module_name)

    def _reload_module(self, module_name: str) -> bool:
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
        return self._reload_count

    @property
    def is_running(self) -> bool:
        return self._running
