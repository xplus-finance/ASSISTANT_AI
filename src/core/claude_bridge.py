"""Persistent Claude Code CLI session via stream-json protocol."""

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
    # Exponential backoff constants for persistent session recovery
    _BACKOFF_BASE_SECS = 5.0
    _BACKOFF_MAX_SECS = 300.0  # 5 minutes

    def __init__(self, cli_path="claude", default_timeout=1200):
        self._cli = _resolve_claude_path(cli_path)
        self._default_timeout = default_timeout
        self._install_dir = str(pathlib.Path(__file__).resolve().parent.parent.parent)

        # Persistent session
        self._process = None
        self._session_active = False
        self._lock = asyncio.Lock()  # Serialize requests to the session

        # Exponential backoff state for persistent session retries
        # Tracks when it is safe to attempt restarting the persistent session
        # after a failure.  No background thread — the delay is only applied
        # inside ask() when choosing between session and one-shot mode.
        self._session_fail_count: int = 0
        self._session_retry_after: float = 0.0  # monotonic timestamp

    @staticmethod
    async def _create_subprocess(cmd: list[str], **kwargs):
        if _IS_WINDOWS and cmd and str(cmd[0]).lower().endswith(".cmd"):
            cmd = ["cmd", "/c"] + cmd
        return await asyncio.create_subprocess_exec(*cmd, **kwargs)

    async def start_session(self):
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
        # Successful start — reset backoff counters
        self._session_fail_count = 0
        self._session_retry_after = 0.0
        log.info("claude_bridge.session_started", pid=self._process.pid)

    async def stop_session(self):
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

    def _record_session_failure(self) -> None:
        """Update backoff state after a persistent session failure."""
        self._session_fail_count += 1
        delay = min(
            self._BACKOFF_BASE_SECS * (2 ** (self._session_fail_count - 1)),
            self._BACKOFF_MAX_SECS,
        )
        self._session_retry_after = time.monotonic() + delay
        log.warning(
            "claude_bridge.session_backoff",
            fail_count=self._session_fail_count,
            retry_in_secs=delay,
        )

    def _session_allowed(self) -> bool:
        """Return True if the backoff window has elapsed and a session attempt is permitted."""
        return time.monotonic() >= self._session_retry_after

    async def ask(self, prompt, system_prompt="", timeout=None, complex_task=False):
        timeout = timeout or self._default_timeout
        if complex_task:
            timeout = max(timeout, 1200)

        async with self._lock:
            try:
                session_ready = (
                    self._session_active
                    and self._process
                    and self._process.returncode is None
                    and self._session_allowed()
                )
                if session_ready:
                    result = await self._send_to_session(prompt, system_prompt, timeout)
                    # Successful exchange — reset backoff
                    self._session_fail_count = 0
                    self._session_retry_after = 0.0
                    return result
            except asyncio.CancelledError:
                raise  # No swallowear — tarea cancelada externamente
            except Exception:
                self._record_session_failure()
                log.warning("claude_bridge.session_failed_using_oneshot", exc_info=True)

            return await self._oneshot(prompt, system_prompt, timeout, complex_task=complex_task)

    async def _send_to_session(self, prompt, system_prompt, timeout):
        message = {
            "type": "user_message",
            "content": prompt,
        }
        if system_prompt:
            message["system"] = system_prompt

        line = json.dumps(message) + "\n"
        self._process.stdin.write(line.encode())
        await self._process.stdin.drain()

        response_text = ""
        deadline = time.time() + timeout

        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(
                    self._process.stdout.readline(),
                    timeout=min(60, deadline - time.time())
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

                if msg_type == "assistant" and "content" in chunk:
                    for block in chunk["content"]:
                        if isinstance(block, dict) and block.get("type") == "text":
                            response_text += block["text"]

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
        max_turns = '200' if complex_task else '100'

        # Calculate total command length to detect Windows limit
        total_len = len(prompt) + len(system_prompt or '')

        # On Windows, command line is limited to ~8KB. If the prompt + system_prompt
        # is too long, use stdin pipe instead of command line arguments.
        if _IS_WINDOWS and total_len > 6000:
            return await self._oneshot_via_stdin(prompt, system_prompt, timeout, max_turns)

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

    async def _oneshot_via_stdin(self, prompt, system_prompt, timeout, max_turns):
        """Fallback for Windows: send prompt via stdin to avoid command line length limit."""
        # Combine prompt and system prompt into stdin
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n---\n\nUser request:\n{prompt}"

        cmd = [
            self._cli, '-p', '-',
            '--output-format', 'text',
            '--max-turns', max_turns,
            '--add-dir', self._install_dir,
            '--permission-mode', 'bypassPermissions',
        ]

        proc = await self._create_subprocess(
            cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=full_prompt.encode('utf-8')),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise ClaudeBridgeError(f"Timed out after {timeout}s")

        if proc.returncode != 0:
            raise ClaudeBridgeError(f"CLI error: {stderr.decode()[:300]}")

        return stdout.decode().strip()

    async def execute_in_project(self, task, project_path, system_prompt="", timeout=1200):
        cmd = [
            self._cli, '-p', task,
            '--output-format', 'text',
            '--max-turns', '100',
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
