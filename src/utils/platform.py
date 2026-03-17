"""
Cross-platform detection and constants.

Import IS_WINDOWS / IS_LINUX and platform-aware defaults from here
instead of hard-coding OS-specific values throughout the codebase.
"""

from __future__ import annotations

import os
import platform
import tempfile

IS_WINDOWS: bool = platform.system() == "Windows"
IS_LINUX: bool = platform.system() == "Linux"
IS_MACOS: bool = platform.system() == "Darwin"

# Shell command prefix for subprocess invocation
SHELL_CMD: list[str] = ["cmd", "/c"] if IS_WINDOWS else ["/bin/sh", "-c"]

# Cross-platform temp directory
TEMP_DIR: str = tempfile.gettempdir()

# Default PATH for sandboxed/restricted execution
DEFAULT_PATH_ENV: str = (
    os.environ.get("PATH", "")
    if IS_WINDOWS
    else "/usr/bin:/bin"
)

# Default HOME for sandboxed execution
DEFAULT_HOME_ENV: str = (
    os.environ.get("USERPROFILE", os.environ.get("HOME", ""))
    if IS_WINDOWS
    else "/workspace"
)
