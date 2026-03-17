"""
Claude Code CLI integration via asyncio subprocess.

Uses ``claude -p`` (print mode) with the user's Claude Pro/Max subscription.
All communication happens through the CLI invoked as a child process.

CRITICAL: Uses --permission-mode bypassPermissions so Claude can act
autonomously without blocking on terminal prompts. Security is handled
by our own 7-layer security system, not by Claude's permission prompts.
"""

from __future__ import annotations

import asyncio
import json
import shlex
from collections.abc import AsyncIterator
from typing import Any

import structlog

log = structlog.get_logger("assistant.claude_bridge")


class ClaudeBridgeError(Exception):
    """Raised when the Claude CLI returns an error or times out."""


class ClaudeBridge:
    """
    Async bridge to the ``claude`` CLI.

    All methods use ``asyncio.create_subprocess_exec`` with
    ``stdin=DEVNULL`` to prevent hanging on interactive input.
    Uses ``--permission-mode bypassPermissions`` so Claude acts
    autonomously (our security layer handles permissions instead).
    """

    def __init__(
        self,
        cli_path: str = "claude",
        default_timeout: int = 60,
        max_turns: int = 5,
    ) -> None:
        self._cli = cli_path
        self._default_timeout = default_timeout
        self._max_turns = max(max_turns, 10)  # Minimum 10 turns for basic tasks
        self._max_turns_complex = 30  # For tasks that need more autonomy

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def ask(
        self,
        prompt: str,
        system_prompt: str = "",
        timeout: int | None = None,
        complex_task: bool = False,
    ) -> str:
        """Send a one-shot prompt and return the response text.

        Args:
            complex_task: If True, allows more turns and longer timeout
                         for tasks that need autonomy (creating tools, etc.)
        """
        if complex_task:
            timeout = timeout or 300  # 5 min for complex tasks
            max_turns = self._max_turns_complex
        else:
            timeout = timeout or self._default_timeout
            max_turns = self._max_turns

        cmd = self._build_cmd(
            prompt, system_prompt, output_format="text",
            extra_args=["--max-turns", str(max_turns)] if complex_task else None,
        )
        stdout = await self._run(cmd, timeout)
        return stdout.strip()

    async def ask_json(
        self,
        prompt: str,
        system_prompt: str = "",
        timeout: int | None = None,
    ) -> str:
        """Send a prompt and return parsed JSON response."""
        timeout = timeout or self._default_timeout
        cmd = self._build_cmd(prompt, system_prompt, output_format="json")
        stdout = await self._run(cmd, timeout)
        return self._extract_result(stdout)

    async def ask_streaming(
        self,
        prompt: str,
        system_prompt: str = "",
    ) -> AsyncIterator[dict[str, Any]]:
        """Send a prompt and yield JSON chunks as they arrive."""
        cmd = self._build_cmd(prompt, system_prompt, output_format="stream-json")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        assert process.stdout is not None

        try:
            async for raw_line in process.stdout:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    pass
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()

    async def execute_in_project(
        self,
        task: str,
        project_path: str,
        system_prompt: str = "",
        timeout: int = 300,
        max_turns: int = 10,
    ) -> str:
        """Execute a task scoped to a project directory."""
        cmd = self._build_cmd(
            task,
            system_prompt,
            output_format="text",
            extra_args=[
                "--cwd", project_path,
                "--max-turns", str(max_turns),
            ],
        )
        stdout = await self._run(cmd, timeout)
        return stdout.strip()

    async def check_available(self) -> bool:
        """Return True if claude CLI is installed."""
        try:
            proc = await asyncio.create_subprocess_exec(
                self._cli, "--version",
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            version = stdout.decode("utf-8", errors="replace").strip()
            log.info("claude_bridge.available", version=version)
            return proc.returncode == 0
        except (FileNotFoundError, asyncio.TimeoutError, OSError) as exc:
            log.warning("claude_bridge.not_available", error=str(exc))
            return False

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_cmd(
        self,
        prompt: str,
        system_prompt: str,
        output_format: str,
        extra_args: list[str] | None = None,
    ) -> list[str]:
        """Build the CLI argument list."""
        cmd: list[str] = [
            self._cli,
            "-p", prompt,
            "--output-format", output_format,
            "--max-turns", str(self._max_turns),
            # CRITICAL: bypass permission prompts so Claude doesn't block
            # waiting for terminal input that nobody will see.
            # Our own security layer (SecurityGuardian) handles permissions.
            "--permission-mode", "bypassPermissions",
        ]

        if system_prompt:
            cmd.extend(["--append-system-prompt", system_prompt])

        if extra_args:
            cmd.extend(extra_args)

        return cmd

    async def _run(self, cmd: list[str], timeout: int) -> str:
        """Execute cmd as subprocess with timeout, return stdout."""
        log.debug(
            "claude_bridge.exec",
            cmd_preview=" ".join(shlex.quote(c) for c in cmd[:6]) + " ...",
            timeout=timeout,
        )

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise ClaudeBridgeError(
                f"Claude CLI timed out after {timeout}s"
            ) from None
        except FileNotFoundError:
            raise ClaudeBridgeError(
                f"Claude CLI not found at '{self._cli}'."
            ) from None

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")

        if process.returncode != 0:
            log.error(
                "claude_bridge.cli_error",
                returncode=process.returncode,
                stderr=stderr[:500],
            )
            raise ClaudeBridgeError(
                f"Claude CLI exited with code {process.returncode}: "
                f"{stderr[:300]}"
            )

        return stdout

    @staticmethod
    def _extract_result(stdout: str) -> str:
        """Parse JSON output and extract the result text."""
        stdout = stdout.strip()
        if not stdout:
            raise ClaudeBridgeError("Claude CLI returned empty output")

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            # Try last line if output has preamble
            for line in reversed(stdout.splitlines()):
                line = line.strip()
                if line.startswith("{"):
                    try:
                        data = json.loads(line)
                        break
                    except json.JSONDecodeError:
                        continue
            else:
                # Not JSON — return raw text
                return stdout.strip()

        if isinstance(data, dict):
            result = data.get("result", "")
            if result:
                return str(result)
            if "content" in data:
                parts = []
                for block in data["content"]:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block["text"])
                if parts:
                    return "\n".join(parts)

        return stdout.strip()
