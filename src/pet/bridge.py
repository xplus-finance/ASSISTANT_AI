"""Bridge between the AI agent (gateway) and the desktop pet (overlay).

The pet runs as a child process. The bridge manages the process lifecycle
and sends state updates via a simple pipe/queue mechanism.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import signal
import time
from multiprocessing import Process, Queue
from typing import Any

import structlog

log = structlog.get_logger("assistant.pet.bridge")


def _pet_process_main(
    pet_type: str,
    size: int,
    monitor: int,
    state_queue: Queue,
    assets_dir: str | None,
) -> None:
    """Entry point for the pet child process."""
    try:
        from src.pet.overlay import PetOverlay
        from PyQt6.QtCore import QTimer

        pet = PetOverlay(
            pet_type=pet_type,
            size=size,
            monitor=monitor,
            assets_dir=assets_dir,
        )

        # Poll the state queue periodically from within Qt event loop
        def _check_queue() -> None:
            try:
                while not state_queue.empty():
                    msg = state_queue.get_nowait()
                    if msg == "__QUIT__":
                        pet.stop()
                        return
                    pet.update_state(msg)
            except Exception:
                pass

        # We need to start the Qt app first, then set up the queue polling
        # Use a delayed timer approach
        import sys
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)

        # Create and show pet window directly
        from src.pet.sprite_engine import SpriteEngine, DEFAULT_FRAME_SIZE
        from src.pet.behavior import BehaviorController
        from src.pet.overlay import DISPLAY_SCALE
        sprite = SpriteEngine(pet_type=pet_type, assets_dir=assets_dir, frame_size=DEFAULT_FRAME_SIZE)
        if not sprite.load():
            log.error("pet.process.sprites_failed")
            return

        display_size = int(DEFAULT_FRAME_SIZE * DISPLAY_SCALE)

        from src.pet.overlay import _PetWindow
        behavior = BehaviorController()
        window = _PetWindow(sprite_engine=sprite, behavior=behavior, display_size=display_size, monitor_index=monitor)
        window.show()

        # Make sticky on all workspaces (Linux)
        import sys as _sys
        if _sys.platform.startswith("linux"):
            from src.pet.overlay import _make_sticky_all_workspaces
            from PyQt6.QtCore import QTimer as _QTimer
            _QTimer.singleShot(500, lambda: _make_sticky_all_workspaces(int(window.winId())))

        # Queue polling timer
        queue_timer = QTimer()

        def poll_queue():
            try:
                while not state_queue.empty():
                    msg = state_queue.get_nowait()
                    if msg == "__QUIT__":
                        app.quit()
                        return
                    from src.pet.behavior import AgentState
                    agent_state = AgentState.from_string(msg)
                    anim = behavior.set_state(agent_state)
                    sprite.set_animation(anim)
            except Exception:
                pass

        queue_timer.timeout.connect(poll_queue)
        queue_timer.start(200)  # Check every 200ms

        signal.signal(signal.SIGINT, signal.SIG_DFL)
        signal.signal(signal.SIGTERM, lambda *_: app.quit())

        app.exec()
    except Exception:
        log.exception("pet.process.crashed")


class PetBridge:
    """Manages the pet process from the main agent process."""

    def __init__(
        self,
        pet_type: str = "dog",
        size: int = 96,
        monitor: int = 0,
        assets_dir: str | None = None,
    ) -> None:
        self._pet_type = pet_type
        self._size = size
        self._monitor = monitor
        self._assets_dir = assets_dir
        self._process: Process | None = None
        self._state_queue: Queue | None = None
        self._last_state: str = "idle"

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.is_alive()

    def start(self) -> bool:
        """Launch the pet as a child process. Returns True if started."""
        if self.is_running:
            log.info("pet.bridge.already_running")
            return True

        try:
            self._state_queue = Queue(maxsize=100)
            self._process = Process(
                target=_pet_process_main,
                args=(self._pet_type, self._size, self._monitor,
                      self._state_queue, self._assets_dir),
                daemon=True,
                name="desktop-pet",
            )
            self._process.start()
            log.info("pet.bridge.started", pid=self._process.pid,
                     pet_type=self._pet_type)
            return True
        except Exception:
            log.exception("pet.bridge.start_failed")
            return False

    def stop(self) -> None:
        """Stop the pet process gracefully."""
        if self._state_queue:
            try:
                self._state_queue.put_nowait("__QUIT__")
            except Exception:
                pass

        if self._process and self._process.is_alive():
            self._process.join(timeout=3)
            if self._process.is_alive():
                self._process.terminate()
                self._process.join(timeout=2)
            log.info("pet.bridge.stopped")

        self._process = None
        self._state_queue = None

    def send_state(self, state: str) -> None:
        """Send a state update to the pet process."""
        if not self.is_running:
            # Auto-relaunch if crashed
            if self._process is not None:
                log.warning("pet.bridge.process_died_relaunching")
                self.start()
            return

        if state == self._last_state:
            return  # Don't spam the same state

        try:
            if self._state_queue:
                self._state_queue.put_nowait(state)
                self._last_state = state
        except Exception:
            log.debug("pet.bridge.queue_full")

    def on_message_received(self) -> None:
        self.send_state("PROCESSING")

    def on_execution_start(self) -> None:
        self.send_state("EXECUTING")

    def on_response_sent(self, success: bool = True) -> None:
        self.send_state("COMPLETE" if success else "ERROR")

    def on_idle(self) -> None:
        self.send_state("IDLE")

    def change_pet_type(self, pet_type: str) -> None:
        """Change pet type by restarting the process."""
        self._pet_type = pet_type
        if self.is_running:
            self.stop()
            time.sleep(0.5)
            self.start()
