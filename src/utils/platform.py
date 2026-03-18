"""
Cross-platform detection and constants.

Import IS_WINDOWS / IS_LINUX and platform-aware defaults from here
instead of hard-coding OS-specific values throughout the codebase.
"""

from __future__ import annotations

import os
import platform
import sys
import tempfile
from pathlib import Path

IS_WINDOWS: bool = platform.system() == "Windows"
IS_LINUX: bool = platform.system() == "Linux"
IS_MACOS: bool = platform.system() == "Darwin"

# Shell command prefix for subprocess invocation
SHELL_CMD: list[str] = ["cmd", "/c"] if IS_WINDOWS else ["/bin/sh", "-c"]

# Cross-platform temp directory
TEMP_DIR: str = tempfile.gettempdir()

# Default PATH for sandboxed/restricted execution
if IS_WINDOWS:
    DEFAULT_PATH_ENV: str = os.environ.get("PATH", "")
elif IS_MACOS:
    # Include Homebrew paths for both Apple Silicon and Intel Macs
    DEFAULT_PATH_ENV = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
else:
    # Linux: minimal PATH used inside bwrap sandbox
    DEFAULT_PATH_ENV = "/usr/bin:/bin"

# Default HOME for sandboxed execution
if IS_WINDOWS:
    DEFAULT_HOME_ENV: str = os.environ.get("USERPROFILE", os.environ.get("HOME", ""))
elif IS_MACOS:
    # macOS doesn't use bwrap, so use the real home directory
    DEFAULT_HOME_ENV = str(Path.home())
else:
    # Linux: mapped workspace inside bwrap sandbox
    DEFAULT_HOME_ENV = "/workspace"
