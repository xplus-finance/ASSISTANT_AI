"""
Sandboxed command execution using bubblewrap (bwrap).

Provides a secure execution environment with namespace isolation,
read-only filesystem binds, and controlled network access.
Falls back to plain subprocess with timeout if bwrap is not installed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from src.utils.logger import get_app_logger, get_security_logger
from src.utils.platform import IS_WINDOWS, SHELL_CMD, TEMP_DIR, DEFAULT_PATH_ENV, DEFAULT_HOME_ENV


@dataclass(frozen=True)
class ExecutionResult:
    """Result of a sandboxed command execution."""
    stdout: str
    stderr: str
    returncode: int
    timed_out: bool
    sandboxed: bool

    @property
    def success(self) -> bool:
        """True if command exited with code 0 and did not time out."""
        return self.returncode == 0 and not self.timed_out

    @property
    def output(self) -> str:
        """Combined stdout + stderr for convenience."""
        parts = []
        if self.stdout:
            parts.append(self.stdout)
        if self.stderr:
            parts.append(self.stderr)
        return "\n".join(parts)


class SandboxedExecutor:
    """Execute shell commands inside a bubblewrap (bwrap) sandbox with
    namespace isolation and controlled filesystem/network access.
    Falls back to subprocess with timeout if bwrap is unavailable."""

    # Maximum output size to capture (prevent OOM on pathological commands)
    MAX_OUTPUT_BYTES = 1024 * 1024  # 1 MB

    def __init__(self) -> None:
        self._log = get_app_logger()
        self._sec_log = get_security_logger()
        self._bwrap_path = None if IS_WINDOWS else shutil.which("bwrap")

        if self._bwrap_path is None and not IS_WINDOWS:
            self._log.warning(
                "bwrap_not_found",
                message=(
                    "bubblewrap (bwrap) is not installed. "
                    "Commands will run WITHOUT sandboxing. "
                    "Install with: sudo apt install bubblewrap"
                ),
            )
        elif IS_WINDOWS:
            self._log.info(
                "sandbox_windows",
                message="Running on Windows — bubblewrap not available, using subprocess fallback.",
            )

    @property
    def sandbox_available(self) -> bool:
        """True if bubblewrap is installed and usable."""
        return self._bwrap_path is not None

    def execute(
        self,
        command: str,
        workspace: str = TEMP_DIR,
        timeout: int = 30,
        allow_network: bool = False,
    ) -> ExecutionResult:
        """
        Execute a command, sandboxed if possible.

        Args:
            command: Shell command to execute.
            workspace: Directory that will be writable inside the sandbox.
                       Mapped to /workspace inside bwrap.
            timeout: Maximum execution time in seconds.
            allow_network: If True, share the host network namespace.
                           If False (default), the command has no network access.

        Returns:
            ExecutionResult with stdout, stderr, return code, and status flags.
        """
        # Ensure workspace exists
        ws_path = Path(workspace)
        ws_path.mkdir(parents=True, exist_ok=True)

        if self._bwrap_path is not None:
            return self._execute_sandboxed(command, workspace, timeout, allow_network)
        else:
            return self._execute_fallback(command, workspace, timeout)

    def _execute_sandboxed(
        self,
        command: str,
        workspace: str,
        timeout: int,
        allow_network: bool,
    ) -> ExecutionResult:
        """Execute command inside bubblewrap sandbox."""

        bwrap_args = [
            self._bwrap_path,
            # ── Namespace isolation ──
            "--unshare-all",
            # ── Filesystems ──
            "--tmpfs", "/tmp",
            "--dev", "/dev",
            "--proc", "/proc",
            # ── Read-only system binds ──
            "--ro-bind", "/usr", "/usr",
            "--ro-bind", "/bin", "/bin",
            "--ro-bind", "/lib", "/lib",
            "--ro-bind", "/etc/resolv.conf", "/etc/resolv.conf",
            "--ro-bind", "/etc/ssl/certs", "/etc/ssl/certs",
            # ── Writable workspace ──
            "--bind", workspace, "/workspace",
            # ── Security ──
            "--die-with-parent",
            "--new-session",
        ]

        # /lib64 may not exist on all systems (e.g., some ARM builds)
        if Path("/lib64").exists():
            bwrap_args.extend(["--ro-bind", "/lib64", "/lib64"])

        # /etc/alternatives is needed for some distros to resolve symlinks
        if Path("/etc/alternatives").exists():
            bwrap_args.extend(["--ro-bind", "/etc/alternatives", "/etc/alternatives"])

        # Network access
        if allow_network:
            bwrap_args.append("--share-net")

        # The actual command to run inside the sandbox
        bwrap_args.extend([
            "/bin/sh", "-c",
            f"cd /workspace && {command}",
        ])

        self._log.info(
            "sandbox_execute",
            command=command[:200],
            workspace=workspace,
            timeout=timeout,
            network=allow_network,
        )

        return self._run_process(bwrap_args, timeout, sandboxed=True)

    def _execute_fallback(
        self,
        command: str,
        workspace: str,
        timeout: int,
    ) -> ExecutionResult:
        """Execute command with subprocess.run (no sandbox)."""
        self._sec_log.warning(
            "unsandboxed_execution",
            command=command[:200],
            message="Running without sandbox \u2014 bwrap not available",
        )

        if IS_WINDOWS:
            # On Windows use cmd /c with cd
            args = [*SHELL_CMD, f"cd /d {workspace} && {command}"]
        else:
            args = [*SHELL_CMD, f"cd {workspace} && {command}"]
        return self._run_process(args, timeout, sandboxed=False)

    def _run_process(
        self,
        args: list[str],
        timeout: int,
        sandboxed: bool,
    ) -> ExecutionResult:
        """
        Run a subprocess with timeout and output capture.

        Args:
            args: Command arguments list.
            timeout: Timeout in seconds.
            sandboxed: Whether this execution is sandboxed (for the result flag).

        Returns:
            ExecutionResult.
        """
        timed_out = False
        start = time.monotonic()

        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                timeout=timeout,
                # Don't inherit environment inside sandbox
                env={"PATH": DEFAULT_PATH_ENV, "HOME": DEFAULT_HOME_ENV, "LANG": "C.UTF-8"},
            )
            stdout = proc.stdout.decode("utf-8", errors="replace")[:self.MAX_OUTPUT_BYTES]
            stderr = proc.stderr.decode("utf-8", errors="replace")[:self.MAX_OUTPUT_BYTES]
            returncode = proc.returncode

        except subprocess.TimeoutExpired:
            timed_out = True
            stdout = ""
            stderr = f"Command timed out after {timeout} seconds"
            returncode = -1
            self._log.warning(
                "command_timeout",
                timeout=timeout,
                command=str(args[-1])[:200] if args else "unknown",
            )

        except OSError as exc:
            stdout = ""
            stderr = f"Failed to execute: {exc}"
            returncode = -1
            self._log.error(
                "execution_error",
                error=str(exc),
                command=str(args[-1])[:200] if args else "unknown",
            )

        elapsed = time.monotonic() - start
        self._log.info(
            "execution_complete",
            returncode=returncode,
            timed_out=timed_out,
            sandboxed=sandboxed,
            elapsed_seconds=round(elapsed, 3),
        )

        return ExecutionResult(
            stdout=stdout,
            stderr=stderr,
            returncode=returncode,
            timed_out=timed_out,
            sandboxed=sandboxed,
        )
