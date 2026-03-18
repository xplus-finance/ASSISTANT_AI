"""Cross-platform detection and constants."""

from __future__ import annotations

import os
import platform
import sys
import tempfile
from pathlib import Path

IS_WINDOWS: bool = platform.system() == "Windows"
IS_LINUX: bool = platform.system() == "Linux"
IS_MACOS: bool = platform.system() == "Darwin"

SHELL_CMD: list[str] = ["cmd", "/c"] if IS_WINDOWS else ["/bin/sh", "-c"]

TEMP_DIR: str = tempfile.gettempdir()

if IS_WINDOWS:
    DEFAULT_PATH_ENV: str = os.environ.get("PATH", "")
elif IS_MACOS:
    DEFAULT_PATH_ENV = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
else:
    DEFAULT_PATH_ENV = "/usr/bin:/bin"

if IS_WINDOWS:
    DEFAULT_HOME_ENV: str = os.environ.get("USERPROFILE", os.environ.get("HOME", ""))
elif IS_MACOS:
    DEFAULT_HOME_ENV = str(Path.home())
else:
    DEFAULT_HOME_ENV = "/workspace"
