#!/usr/bin/env python3
"""Alarm visual app — PyQt6 fullscreen window with image, sound, snooze, and dismiss."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QSize, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPixmap, QFont, QColor, QPalette, QIcon, QPainter, QLinearGradient
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
)

APP_DIR = Path(__file__).parent
SOUNDS_DIR = APP_DIR / "sounds"
IMAGES_DIR = APP_DIR / "images"
THEMES_FILE = APP_DIR / "themes.json"


def load_themes() -> dict:
    if THEMES_FILE.exists():
        with open(THEMES_FILE) as f:
            return json.load(f).get("themes", {})
    return {}


def get_theme(theme_name: str) -> dict:
    themes = load_themes()
    theme = themes.get(theme_name, themes.get("default", {}))
    # Fallback defaults
    defaults = {
        "bg_color": "#1a1a2e",
        "text_color": "#ffffff",
        "accent_color": "#e94560",
        "button_color": "#0f3460",
        "button_hover": "#16213e",
        "sound": "default.wav",
        "image": None,
        "icon": "⏰",
        "name": theme_name.title(),
    }
    for k, v in defaults.items():
        if k not in theme or theme[k] is None and k in ("bg_color", "text_color"):
            theme.setdefault(k, v)
    return theme


class AlarmWindow(QMainWindow):
    def __init__(
        self,
        message: str = "¡Hora de despertar!",
        theme_name: str = "default",
        alarm_id: int | None = None,
        snooze_minutes: int = 5,
    ):
        super().__init__()
        self.message = message
        self.theme = get_theme(theme_name)
        self.theme_name = theme_name
        self.alarm_id = alarm_id
        self.snooze_minutes = snooze_minutes
        self.sound_process: subprocess.Popen | None = None
        self.playing = False
        self.flash_state = False

        self.setWindowTitle("Alarma - Firulais")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.showFullScreen()

        self._build_ui()
        self._start_sound()
        self._start_flash()

    def _build_ui(self):
        bg = self.theme.get("bg_color", "#1a1a2e")
        text_color = self.theme.get("text_color", "#ffffff")
        accent = self.theme.get("accent_color", "#e94560")
        btn_color = self.theme.get("button_color", "#0f3460")
        btn_hover = self.theme.get("button_hover", "#16213e")
        icon_text = self.theme.get("icon", "⏰")

        central = QWidget()
        self.setCentralWidget(central)
        central.setStyleSheet(f"background-color: {bg};")

        main_layout = QVBoxLayout(central)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.setSpacing(30)
        main_layout.setContentsMargins(60, 60, 60, 60)

        # Image (if available)
        image_file = self.theme.get("image")
        if image_file:
            image_path = IMAGES_DIR / image_file
            if image_path.exists():
                img_label = QLabel()
                pixmap = QPixmap(str(image_path))
                if not pixmap.isNull():
                    scaled = pixmap.scaled(
                        QSize(400, 400),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    img_label.setPixmap(scaled)
                    img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    # Drop shadow
                    shadow = QGraphicsDropShadowEffect()
                    shadow.setBlurRadius(40)
                    shadow.setColor(QColor(accent))
                    shadow.setOffset(0, 0)
                    img_label.setGraphicsEffect(shadow)
                    main_layout.addWidget(img_label)

        # Icon (always show if no image)
        if not image_file or not (IMAGES_DIR / (image_file or "")).exists():
            icon_label = QLabel(icon_text)
            icon_label.setFont(QFont("Segoe UI Emoji", 120))
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_label.setStyleSheet(f"color: {accent}; background: transparent;")
            main_layout.addWidget(icon_label)

        # Time
        self.time_label = QLabel(datetime.now().strftime("%H:%M"))
        self.time_label.setFont(QFont("Arial", 96, QFont.Weight.Bold))
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.time_label.setStyleSheet(f"color: {text_color}; background: transparent;")
        shadow2 = QGraphicsDropShadowEffect()
        shadow2.setBlurRadius(30)
        shadow2.setColor(QColor(accent))
        shadow2.setOffset(0, 0)
        self.time_label.setGraphicsEffect(shadow2)
        main_layout.addWidget(self.time_label)

        # Message
        self.msg_label = QLabel(self.message)
        self.msg_label.setFont(QFont("Arial", 32))
        self.msg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.msg_label.setWordWrap(True)
        self.msg_label.setStyleSheet(f"color: {text_color}; background: transparent; padding: 20px;")
        main_layout.addWidget(self.msg_label)

        # Theme name
        theme_display = self.theme.get("name", self.theme_name.title())
        theme_label = QLabel(f"Tema: {theme_display}")
        theme_label.setFont(QFont("Arial", 16))
        theme_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        theme_label.setStyleSheet(f"color: {accent}; background: transparent;")
        main_layout.addWidget(theme_label)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(40)

        btn_style = f"""
            QPushButton {{
                background-color: {btn_color};
                color: {text_color};
                border: 2px solid {accent};
                border-radius: 20px;
                padding: 20px 50px;
                font-size: 24px;
                font-weight: bold;
                min-width: 200px;
            }}
            QPushButton:hover {{
                background-color: {btn_hover};
                border-color: {text_color};
            }}
            QPushButton:pressed {{
                background-color: {accent};
            }}
        """

        # Snooze button
        snooze_btn = QPushButton(f"💤 Snooze ({self.snooze_minutes} min)")
        snooze_btn.setStyleSheet(btn_style)
        snooze_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        snooze_btn.clicked.connect(self._on_snooze)
        btn_layout.addWidget(snooze_btn)

        # Dismiss button
        dismiss_btn = QPushButton("✅ Apagar")
        dismiss_style = btn_style.replace(btn_color, accent).replace(btn_hover, "#ff6b6b")
        dismiss_btn.setStyleSheet(dismiss_style)
        dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        dismiss_btn.clicked.connect(self._on_dismiss)
        btn_layout.addWidget(dismiss_btn)

        main_layout.addLayout(btn_layout)

        # Update time every second
        self.clock_timer = QTimer()
        self.clock_timer.timeout.connect(self._update_time)
        self.clock_timer.start(1000)

    def _update_time(self):
        self.time_label.setText(datetime.now().strftime("%H:%M:%S"))

    def _start_flash(self):
        """Flashes the message label to grab attention."""
        self.flash_timer = QTimer()
        self.flash_timer.timeout.connect(self._toggle_flash)
        self.flash_timer.start(800)

    def _toggle_flash(self):
        self.flash_state = not self.flash_state
        accent = self.theme.get("accent_color", "#e94560")
        text_color = self.theme.get("text_color", "#ffffff")
        if self.flash_state:
            self.msg_label.setStyleSheet(
                f"color: {accent}; background: transparent; padding: 20px; font-size: 36px;"
            )
        else:
            self.msg_label.setStyleSheet(
                f"color: {text_color}; background: transparent; padding: 20px; font-size: 32px;"
            )

    def _start_sound(self):
        """Play alarm sound in loop using paplay/ffplay/aplay."""
        sound_file = self.theme.get("sound", "default.wav")
        sound_path = SOUNDS_DIR / sound_file

        # Fallback to default if theme sound doesn't exist
        if not sound_path.exists():
            sound_path = SOUNDS_DIR / "default.wav"
        if not sound_path.exists():
            return

        self.playing = True
        self._sound_thread = threading.Thread(target=self._sound_loop, args=(str(sound_path),), daemon=True)
        self._sound_thread.start()

    def _sound_loop(self, path: str):
        """Loop sound until stopped."""
        while self.playing:
            try:
                # Try paplay first (PulseAudio), then ffplay, then aplay
                for cmd in [
                    ["paplay", path],
                    ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path],
                    ["aplay", path],
                ]:
                    try:
                        self.sound_process = subprocess.Popen(
                            cmd,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                        self.sound_process.wait()
                        break
                    except FileNotFoundError:
                        continue
            except Exception:
                break
            # Small pause between loops
            if self.playing:
                time.sleep(0.3)

    def _stop_sound(self):
        self.playing = False
        if self.sound_process and self.sound_process.poll() is None:
            try:
                self.sound_process.terminate()
                self.sound_process.wait(timeout=2)
            except Exception:
                try:
                    self.sound_process.kill()
                except Exception:
                    pass

    def _on_snooze(self):
        """Snooze: stop alarm now, schedule re-trigger in N minutes."""
        self._stop_sound()
        # Write snooze file so the trigger script knows to re-fire
        snooze_file = APP_DIR / ".snooze"
        snooze_data = {
            "alarm_id": self.alarm_id,
            "snooze_minutes": self.snooze_minutes,
            "message": self.message,
            "theme": self.theme_name,
            "snoozed_at": datetime.now().isoformat(),
        }
        with open(snooze_file, "w") as f:
            json.dump(snooze_data, f)
        self.close()

    def _on_dismiss(self):
        """Dismiss: stop everything and close."""
        self._stop_sound()
        # Remove snooze file if exists
        snooze_file = APP_DIR / ".snooze"
        if snooze_file.exists():
            snooze_file.unlink()
        self.close()

    def keyPressEvent(self, event):
        """Allow Escape or Space to dismiss, Enter to snooze."""
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Space):
            self._on_dismiss()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._on_snooze()

    def closeEvent(self, event):
        self._stop_sound()
        if hasattr(self, "clock_timer"):
            self.clock_timer.stop()
        if hasattr(self, "flash_timer"):
            self.flash_timer.stop()
        event.accept()
        QApplication.instance().quit()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Firulais Alarm")
    parser.add_argument("--message", "-m", default="¡Hora de despertar!", help="Alarm message")
    parser.add_argument("--theme", "-t", default="default", help="Theme name")
    parser.add_argument("--alarm-id", "-i", type=int, default=None, help="Alarm ID")
    parser.add_argument("--snooze", "-s", type=int, default=5, help="Snooze minutes")
    args = parser.parse_args()

    # Ensure DISPLAY is set for X11
    if "DISPLAY" not in os.environ:
        os.environ["DISPLAY"] = ":0"

    app = QApplication(sys.argv)
    app.setApplicationName("Firulais Alarm")

    window = AlarmWindow(
        message=args.message,
        theme_name=args.theme,
        alarm_id=args.alarm_id,
        snooze_minutes=args.snooze,
    )
    window.show()

    # Allow Ctrl+C
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
