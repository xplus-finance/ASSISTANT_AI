"""PyQt6 transparent overlay window for the desktop pet."""

from __future__ import annotations

import math
import random
import signal
import subprocess
import sys
from typing import Any

import structlog

log = structlog.get_logger("assistant.pet.overlay")

try:
    from PyQt6.QtCore import Qt, QTimer, QPoint, QSize
    from PyQt6.QtGui import QPixmap, QPainter, QAction, QCursor, QScreen, QTransform
    from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QMenu, QSystemTrayIcon
    _HAS_PYQT6 = True
except ImportError:
    _HAS_PYQT6 = False
    log.info("pet.pyqt6_not_available")

from src.pet.sprite_engine import SpriteEngine, DEFAULT_FPS, DEFAULT_FRAME_SIZE, angle_to_direction
from src.pet.behavior import BehaviorController, AgentState

DISPLAY_SCALE = 1.2


def _make_sticky_all_workspaces(window_id: int) -> None:
    try:
        subprocess.run(
            ["xprop", "-id", str(window_id),
             "-f", "_NET_WM_DESKTOP", "32c",
             "-set", "_NET_WM_DESKTOP", "0xFFFFFFFF"],
            capture_output=True, timeout=3,
        )
        subprocess.run(
            ["xprop", "-id", str(window_id),
             "-f", "_NET_WM_STATE", "32a",
             "-set", "_NET_WM_STATE", "_NET_WM_STATE_STICKY,_NET_WM_STATE_ABOVE"],
            capture_output=True, timeout=3,
        )
    except Exception:
        try:
            subprocess.run(
                ["wmctrl", "-i", "-r", str(window_id), "-b", "add,sticky,above"],
                capture_output=True, timeout=3,
            )
        except Exception:
            pass


class PetOverlay:
    def __init__(self, pet_type="dog", size=DEFAULT_FRAME_SIZE, monitor=0, assets_dir=None):
        if not _HAS_PYQT6:
            raise RuntimeError("PyQt6 required")
        self._pet_type = pet_type
        self._size = size
        self._target_monitor = monitor
        self._assets_dir = assets_dir
        self._behavior = BehaviorController()
        self._running = False

    @property
    def behavior(self):
        return self._behavior

    def start(self):
        if not _HAS_PYQT6:
            return
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._sprite = SpriteEngine(self._pet_type, self._assets_dir, DEFAULT_FRAME_SIZE)
        if not self._sprite.load():
            return
        display_size = int(DEFAULT_FRAME_SIZE * DISPLAY_SCALE)
        self._window = _PetWindow(self._sprite, self._behavior, display_size, self._target_monitor)
        self._window.show()
        if sys.platform.startswith("linux"):
            QTimer.singleShot(500, lambda: _make_sticky_all_workspaces(int(self._window.winId())))
        self._running = True
        self._app.exec()
        self._running = False

    def stop(self):
        if hasattr(self, '_window') and self._window:
            self._window.close()
        if hasattr(self, '_app') and self._app:
            self._app.quit()
        self._running = False

    def update_state(self, state: str):
        agent_state = AgentState.from_string(state)
        self._behavior.set_state(agent_state)

    @property
    def is_running(self):
        return self._running


if _HAS_PYQT6:
    class _PetWindow(QMainWindow):
        def __init__(self, sprite_engine, behavior, display_size=115, monitor_index=0):
            super().__init__()
            self._sprite = sprite_engine
            self._behavior = behavior
            self._display_size = display_size
            self._drag_position = None

            # Movement
            self._dir_x = 1
            self._wandering = False
            self._pause_ticks = 0
            self._target_x = None
            self._target_y = None
            self._locked_direction = None
            self._move_speed = 2.0
            self._current_mode = "idle"  # tracks what the pet is currently doing

            # Window
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool
                | Qt.WindowType.X11BypassWindowManagerHint
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setAttribute(Qt.WidgetAttribute.WA_X11DoNotAcceptFocus)
            self.setFixedSize(display_size, display_size)

            self._label = QLabel(self)
            self._label.setFixedSize(display_size, display_size)
            self._label.setStyleSheet("background: transparent;")

            self._position_on_monitor(monitor_index)

            # Timers
            self._anim_timer = QTimer(self)
            self._anim_timer.timeout.connect(self._on_animation_tick)
            self._anim_timer.start(1000 // DEFAULT_FPS)

            self._state_timer = QTimer(self)
            self._state_timer.timeout.connect(self._on_state_tick)
            self._state_timer.start(200)  # check behavior state 5x/sec

            self._move_timer = QTimer(self)
            self._move_timer.timeout.connect(self._on_move_tick)
            self._move_timer.start(50)

            if sys.platform.startswith("linux"):
                self._sticky_timer = QTimer(self)
                self._sticky_timer.timeout.connect(self._reapply_sticky)
                self._sticky_timer.start(10_000)

            self._update_frame()
            self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.customContextMenuRequested.connect(self._show_context_menu)

        def _reapply_sticky(self):
            try:
                _make_sticky_all_workspaces(int(self.winId()))
            except Exception:
                pass

        def _position_on_monitor(self, monitor_index):
            app = QApplication.instance()
            if not app: return
            screens = app.screens()
            if monitor_index >= len(screens): monitor_index = 0
            geo = screens[monitor_index].availableGeometry()
            self.move(geo.x() + geo.width() // 2, geo.y() + geo.height() // 2)

        def _get_total_screen_bounds(self):
            app = QApplication.instance()
            if not app: return (0, 0, 1920, 1080)
            screens = app.screens()
            if not screens: return (0, 0, 1920, 1080)
            return (
                min(s.availableGeometry().x() for s in screens),
                min(s.availableGeometry().y() for s in screens),
                max(s.availableGeometry().x() + s.availableGeometry().width() for s in screens),
                max(s.availableGeometry().y() + s.availableGeometry().height() for s in screens),
            )

        def _pick_random_target(self):
            min_x, min_y, max_x, max_y = self._get_total_screen_bounds()
            m = self._display_size
            return random.randint(min_x+m, max_x-m), random.randint(min_y+m, max_y-m)

        def _on_animation_tick(self):
            self._sprite.advance_frame()
            self._update_frame()

        def _on_state_tick(self):
            """React to behavior state changes from the agent."""
            # Let behavior check timeouts (COMPLETE→IDLE, IDLE→INACTIVE)
            self._behavior.tick()

            state = self._behavior.state
            expected_anim = self._behavior.animation

            # STATE: PROCESSING → TYPE (sit still, type on keyboard)
            if state == AgentState.PROCESSING:
                if self._current_mode != "type":
                    self._current_mode = "type"
                    self._wandering = False
                    self._target_x = None
                    self._target_y = None
                    self._locked_direction = "side"
                    self._sprite.set_direction("side")
                    self._sprite.set_animation("type")

            # STATE: EXECUTING → RUN (run across monitors!)
            elif state == AgentState.EXECUTING:
                if self._current_mode != "run":
                    self._current_mode = "run"
                    self._move_speed = 4.0  # fast!
                    self._sprite.set_animation("run")
                    self._start_new_walk()  # pick a target and run to it

            # STATE: ERROR → SAD (sit still, look sad)
            elif state == AgentState.ERROR:
                if self._current_mode != "sad":
                    self._current_mode = "sad"
                    self._wandering = False
                    self._target_x = None
                    self._target_y = None
                    self._locked_direction = "front"
                    self._sprite.set_direction("front")
                    self._sprite.set_animation("sad")

            # STATE: INACTIVE → SLEEP (stay still, sleep)
            elif state == AgentState.INACTIVE:
                if self._current_mode != "sleep":
                    self._current_mode = "sleep"
                    self._wandering = False
                    self._target_x = None
                    self._target_y = None
                    self._locked_direction = "side"
                    self._sprite.set_direction("side")
                    self._sprite.set_animation("sleep")

            # STATE: IDLE or COMPLETE → walk around freely
            elif state in (AgentState.IDLE, AgentState.COMPLETE):
                if self._current_mode in ("type", "sad", "sleep", "run"):
                    # Just came back from a non-idle state
                    self._current_mode = "idle"
                    self._move_speed = 2.0
                    self._wandering = False
                    self._pause_ticks = random.randint(20, 60)  # brief pause before walking
                    self._sprite.set_animation("idle")

        def _on_move_tick(self):
            """Handle movement. NEVER changes animation — that's _on_state_tick's job."""
            if self._drag_position is not None:
                return

            mode = self._current_mode

            # TYPE, SAD, SLEEP: absolutely no movement
            if mode in ("type", "sad", "sleep"):
                return

            # IDLE: walk around freely between pauses
            if mode == "idle":
                # Pausing
                if self._pause_ticks > 0:
                    self._pause_ticks -= 1
                    if self._pause_ticks == 0:
                        self._move_speed = 2.0
                        self._start_new_walk()
                        self._sprite.set_animation("walk")
                    return

                # Not wandering yet — decide to start
                if not self._wandering:
                    if random.random() < 0.012:
                        self._move_speed = 2.0
                        self._start_new_walk()
                        self._sprite.set_animation("walk")
                    return

                # Walking to target
                self._move_toward_target()

                # Arrived
                if self._target_x is None:
                    self._sprite.set_animation("idle")
                    self._pause_ticks = random.randint(60, 200)
                return

            # RUN: move fast toward target, pick new target when arrived
            if mode == "run":
                if not self._wandering or self._target_x is None:
                    self._move_speed = 4.0
                    self._start_new_walk()
                    return

                self._move_toward_target()

                # Arrived at target while still executing → pick new target
                if self._target_x is None and self._behavior.state == AgentState.EXECUTING:
                    self._start_new_walk()
                return

        def _move_toward_target(self):
            """Move toward current target. Sets target to None when arrived."""
            if self._target_x is None or self._target_y is None:
                return

            pos = self.pos()
            dx = self._target_x - pos.x()
            dy = self._target_y - pos.y()
            dist = math.sqrt(dx*dx + dy*dy)

            if dist < 8:
                self._wandering = False
                self._target_x = None
                self._target_y = None
                return

            move_x = (dx / dist) * self._move_speed
            move_y = (dy / dist) * self._move_speed

            new_x = pos.x() + int(move_x)
            new_y = pos.y() + int(move_y)

            min_x, min_y, max_x, max_y = self._get_total_screen_bounds()
            new_x = max(min_x, min(new_x, max_x - self._display_size))
            new_y = max(min_y, min(new_y, max_y - self._display_size))

            self.move(new_x, new_y)

        def _start_new_walk(self):
            """Pick a random target and set direction."""
            tx, ty = self._pick_random_target()
            self._target_x = tx
            self._target_y = ty
            self._wandering = True

            pos = self.pos()
            dx = float(tx - pos.x())
            dy = float(ty - pos.y())

            self._dir_x = 1 if dx >= 0 else -1
            self._locked_direction = angle_to_direction(dx, dy)
            self._sprite.set_direction(self._locked_direction)

        def _update_frame(self):
            frame = self._sprite.get_current_frame()
            if frame is None:
                return

            # Only flip side and diagonal views when moving left
            current_dir = self._locked_direction or self._sprite.current_direction
            if self._dir_x == -1 and current_dir in ("side", "front_side", "back_side"):
                frame = frame.transformed(QTransform().scale(-1, 1))

            if frame.width() != self._display_size:
                frame = frame.scaled(
                    self._display_size, self._display_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.FastTransformation,
                )

            self._label.setPixmap(frame)

        # --- Drag ---

        def mousePressEvent(self, event):
            if event.button() == Qt.MouseButton.LeftButton:
                self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                self._wandering = False
                self._target_x = None
                self._target_y = None
                event.accept()
                self._behavior.wake_up()

        def mouseMoveEvent(self, event):
            if self._drag_position is not None and event.buttons() & Qt.MouseButton.LeftButton:
                self.move(event.globalPosition().toPoint() - self._drag_position)
                event.accept()

        def mouseReleaseEvent(self, event):
            self._drag_position = None

        def mouseDoubleClickEvent(self, event):
            self._sprite.set_animation("run")
            QTimer.singleShot(2000, lambda: self._sprite.set_animation(self._behavior.animation))

        # --- Context menu ---

        def _show_context_menu(self, pos):
            menu = QMenu(self)
            menu.setStyleSheet(
                "QMenu { background-color: #2d2d2d; color: #ffffff; border: 1px solid #555; }"
                "QMenu::item:selected { background-color: #4a9eff; }"
            )
            type_menu = menu.addMenu("Cambiar mascota")
            for pt in ("dog", "cat", "robot", "fox", "owl"):
                label = {"dog":"Perro","cat":"Gato","robot":"Robot","fox":"Zorro","owl":"Búho"}[pt]
                action = type_menu.addAction(f"{'→ ' if pt == self._sprite.pet_type else ''}{label}")
                action.triggered.connect(lambda checked, p=pt: self._change_pet_type(p))
            anim_menu = menu.addMenu("Animaciones")
            for anim in self._sprite.get_available_animations():
                action = anim_menu.addAction(anim.capitalize())
                action.triggered.connect(lambda checked, a=anim: self._play_animation(a))
            menu.addSeparator()
            quit_action = menu.addAction("Cerrar mascota")
            quit_action.triggered.connect(self._quit_pet)
            menu.exec(self.mapToGlobal(pos))

        def _change_pet_type(self, pet_type):
            new_sprite = SpriteEngine(pet_type=pet_type, frame_size=DEFAULT_FRAME_SIZE)
            if new_sprite.load():
                self._sprite = new_sprite
                self._sprite.set_animation(self._behavior.animation)

        def _play_animation(self, name):
            self._sprite.set_animation(name)
            QTimer.singleShot(3000, lambda: self._sprite.set_animation(self._behavior.animation))

        def _quit_pet(self):
            app = QApplication.instance()
            if app: app.quit()
