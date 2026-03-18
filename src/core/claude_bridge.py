"""
Persistent Claude Code CLI session.

Runs Claude Code as a SEPARATE persistent instance using stream-json
bidirectional protocol. Does NOT interfere with the user's own
Claude Code CLI session (multiple instances can run simultaneously).

Architecture:
- Spawns `claude` with --input-format stream-json --output-format stream-json
- Process stays alive — maintains context across messages
- Communicates via stdin/stdout JSON
- Falls back to `claude -p` one-shot if persistent mode fails
"""

import asyncio
import json
import pathlib
import shutil
import sys
import time
from typing import Any
import structlog

log = structlog.get_logger("assistant.claude_bridge")

_IS_WINDOWS = sys.platform == "win32"


def _resolve_claude_path(cli_path: str) -> str:
    """Resolve the claude CLI executable path, handling Windows quirks.

    On Windows, Claude Code installs as 'claude.cmd' (a batch wrapper).
    shutil.which() finds it correctly; we just need to make sure we use
    the full path so asyncio.create_subprocess_exec works without a shell.
    """
    if cli_path != "claude":
        return cli_path  # Explicit path — trust caller

    resolved = shutil.which(cli_path)
    if resolved:
        return resolved

    # Windows fallback: try common install locations
    if _IS_WINDOWS:
        import os
        candidates = [
            pathlib.Path(os.environ.get("APPDATA", "")) / "npm" / "claude.cmd",
            pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "claude" / "claude.cmd",
        ]
        for c in candidates:
            if c.exists():
                return str(c)

    return cli_path  # Return as-is and let the OS resolve it


class ClaudeBridgeError(Exception):
    pass


class ClaudeBridge:
    def __init__(self, cli_path="claude", default_timeout=60):
        self._cli = _resolve_claude_path(cli_path)
        self._default_timeout = default_timeout
        self._install_dir = str(pathlib.Path(__file__).resolve().parent.parent.parent)

        # Persistent session
        self._process = None
        self._session_active = False
        self._lock = asyncio.Lock()  # Serialize requests to the session

    @staticmethod
    async def _create_subprocess(cmd: list[str], **kwargs):
        """Create a subprocess, handling Windows .cmd wrapper quirks.

        On Windows, batch files (.cmd) cannot be launched directly with
        create_subprocess_exec — they require cmd.exe to interpret them.
        We detect this and prepend 'cmd /c' automatically.
        """
        if _IS_WINDOWS and cmd and str(cmd[0]).lower().endswith(".cmd"):
            cmd = ["cmd", "/c"] + cmd
        return await asyncio.create_subprocess_exec(*cmd, **kwargs)

    async def start_session(self):
        """Start the persistent Claude Code session."""
        if self._process and self._process.returncode is None:
            return  # Already running

        cmd = [
            self._cli,
            '-p', '',  # Print mode with empty initial prompt
            '--input-format', 'stream-json',
            '--output-format', 'stream-json',
            '--permission-mode', 'bypassPermissions',
            '--add-dir', self._install_dir,
            '--verbose',
        ]

        self._process = await self._create_subprocess(
            cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._session_active = True
        log.info("claude_bridge.session_started", pid=self._process.pid)

    async def stop_session(self):
        """Stop the persistent session."""
        if self._process and self._process.returncode is None:
            self._process.stdin.close()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=10)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
        self._session_active = False
        self._process = None
        log.info("claude_bridge.session_stopped")

    async def ask(self, prompt, system_prompt="", timeout=None, complex_task=False):
        """Send a message to the persistent session and get response."""
        timeout = timeout or self._default_timeout
        if complex_task:
            timeout = max(timeout, 300)

        async with self._lock:  # One request at a time
            try:
                # Try persistent session first
                if self._session_active and self._process and self._process.returncode is None:
                    return await self._send_to_session(prompt, system_prompt, timeout)
            except asyncio.CancelledError:
                raise  # No swallowear — tarea cancelada externamente
            except Exception:
                log.warning("claude_bridge.session_failed_using_oneshot", exc_info=True)

            # Fallback to one-shot
            return await self._oneshot(prompt, system_prompt, timeout, complex_task=complex_task)

    async def _send_to_session(self, prompt, system_prompt, timeout):
        """Send message to persistent session via stdin JSON."""
        # Build the message according to stream-json input format
        message = {
            "type": "user_message",
            "content": prompt,
        }
        if system_prompt:
            message["system"] = system_prompt

        # Write to stdin
        line = json.dumps(message) + "\n"
        self._process.stdin.write(line.encode())
        await self._process.stdin.drain()

        # Read response chunks until we get a result
        response_text = ""
        deadline = time.time() + timeout

        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(
                    self._process.stdout.readline(),
                    timeout=min(30, deadline - time.time())
                )
            except asyncio.TimeoutError:
                break

            if not raw:
                break

            line = raw.decode().strip()
            if not line:
                continue

            try:
                chunk = json.loads(line)
                msg_type = chunk.get("type", "")

                # Collect text from assistant messages
                if msg_type == "assistant" and "content" in chunk:
                    for block in chunk["content"]:
                        if isinstance(block, dict) and block.get("type") == "text":
                            response_text += block["text"]

                # Result message = final response
                if msg_type == "result":
                    result_text = chunk.get("result", "")
                    if result_text:
                        response_text = result_text
                    break

            except json.JSONDecodeError:
                continue

        if not response_text:
            raise ClaudeBridgeError("No response from session")

        return response_text

    async def _oneshot(self, prompt, system_prompt, timeout, complex_task=False):
        """Fallback: one-shot claude -p call."""
        max_turns = '50' if complex_task else '25'
        cmd = [
            self._cli, '-p', prompt,
            '--output-format', 'text',
            '--max-turns', max_turns,
            '--add-dir', self._install_dir,
            '--permission-mode', 'bypassPermissions',
        ]
        if system_prompt:
            cmd.extend(['--append-system-prompt', system_prompt])

        proc = await self._create_subprocess(
            cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise ClaudeBridgeError(f"Timed out after {timeout}s")

        if proc.returncode != 0:
            raise ClaudeBridgeError(f"CLI error: {stderr.decode()[:300]}")

        return stdout.decode().strip()

    async def execute_in_project(self, task, project_path, system_prompt="", timeout=300):
        """Execute task in specific project directory (uses one-shot with --add-dir)."""
        cmd = [
            self._cli, '-p', task,
            '--output-format', 'text',
            '--max-turns', '50',
            '--add-dir', project_path,
            '--permission-mode', 'bypassPermissions',
        ]
        if system_prompt:
            cmd.extend(['--append-system-prompt', system_prompt])

        proc = await self._create_subprocess(
            cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise ClaudeBridgeError(f"Timed out after {timeout}s")

        if proc.returncode != 0:
            raise ClaudeBridgeError(f"CLI error: {stderr.decode()[:300]}")

        return stdout.decode().strip()

    async def check_available(self):
        """Check if claude CLI is installed."""
        try:
            proc = await self._create_subprocess(
                [self._cli, '--version'],
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            version = stdout.decode().strip()
            log.info("claude_bridge.available", version=version)
            return proc.returncode == 0
        except Exception as e:
            log.warning("claude_bridge.not_available", error=str(e))
            return False

    @property
    def install_dir(self):
        return self._install_dir
