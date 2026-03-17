"""
Terminal skill — execute shell commands with sandboxing and approval.

Commands are routed through ``SandboxedExecutor`` (when available) or
a restricted ``asyncio.create_subprocess_shell``.  Dangerous commands
require explicit user approval via ``ApprovalGate``.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from src.skills.base_skill import BaseSkill, SkillResult
from src.utils.approval import ApprovalGate
from src.utils.platform import IS_WINDOWS

log = structlog.get_logger("assistant.skills.terminal")

# Maximum output length before truncation (characters)
_MAX_OUTPUT = 4000

# Commands that are outright blocked regardless of approval
_BLOCKED_PATTERNS_LINUX: frozenset[str] = frozenset({
    "rm -rf /",
    "rm -rf /*",
    "mkfs",
    ":(){:|:&};:",
    "dd if=/dev/zero of=/dev/sd",
    "> /dev/sda",
    "chmod -R 777 /",
})

_BLOCKED_PATTERNS_WINDOWS: frozenset[str] = frozenset({
    "del /f /s /q c:\\",
    "rd /s /q c:\\",
    "format c:",
    "diskpart",
    "bcdedit",
    "remove-item -recurse -force c:\\",
})

_BLOCKED_PATTERNS: frozenset[str] = _BLOCKED_PATTERNS_WINDOWS if IS_WINDOWS else _BLOCKED_PATTERNS_LINUX

# Commands that require approval before execution
_DANGEROUS_PREFIXES_LINUX: tuple[str, ...] = (
    "rm ",
    "sudo ",
    "apt ",
    "pip install",
    "npm install",
    "docker ",
    "systemctl ",
    "kill ",
    "pkill ",
    "chmod ",
    "chown ",
    "mv /",
    "cp /",
    "dd ",
    "curl ",
    "wget ",
)

_DANGEROUS_PREFIXES_WINDOWS: tuple[str, ...] = (
    "del ",
    "rd ",
    "rmdir ",
    "pip install",
    "npm install",
    "docker ",
    "net stop",
    "net user",
    "sc delete",
    "sc stop",
    "taskkill ",
    "move c:\\",
    "copy c:\\",
    "reg delete",
    "reg add",
    "powershell ",
    "curl ",
    "wget ",
)

_DANGEROUS_PREFIXES: tuple[str, ...] = _DANGEROUS_PREFIXES_WINDOWS if IS_WINDOWS else _DANGEROUS_PREFIXES_LINUX


class TerminalSkill(BaseSkill):
    """Execute shell commands with safety checks."""

    @property
    def name(self) -> str:
        return "terminal"

    @property
    def description(self) -> str:
        return "Ejecuta comandos de terminal con sandboxing y aprobacion de seguridad"

    @property
    def triggers(self) -> list[str]:
        return ["!cmd", "!terminal", "!exec", "!run"]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        """
        Execute a shell command.

        Context keys used:
            ``approval_gate`` (ApprovalGate): For dangerous-command approval.
            ``send_fn`` (callable): To send approval prompts to the user.
            ``receive_fn`` (callable): To receive approval responses.
            ``security_guardian``: Optional SecurityGuardian for validation.
            ``sandbox`` / ``executor``: Optional SandboxedExecutor.
        """
        command = args.strip()
        if not command:
            return SkillResult(
                success=False,
                message="Uso: !cmd <comando>\nEjemplo: !cmd ls -la",
            )

        # Check for absolutely blocked commands
        cmd_lower = command.lower().strip()
        for blocked in _BLOCKED_PATTERNS:
            if blocked in cmd_lower:
                log.warning("terminal.blocked", command=command)
                return SkillResult(
                    success=False,
                    message=f"Comando bloqueado por seguridad: {command}",
                )

        # Validate through SecurityGuardian if available
        guardian = context.get("security_guardian") or context.get("guardian")
        if guardian is not None:
            try:
                result = guardian.validate_command(command)
                if isinstance(result, tuple):
                    allowed, reason = result
                else:
                    allowed = result
                if not allowed:
                    return SkillResult(
                        success=False,
                        message=f"Comando bloqueado por SecurityGuardian: {command}",
                    )
            except Exception as exc:
                log.warning("terminal.guardian_error", error=str(exc))

        # Check if command needs approval
        needs_approval = any(
            cmd_lower.startswith(prefix) for prefix in _DANGEROUS_PREFIXES
        )

        if needs_approval:
            gate: ApprovalGate | None = context.get("approval_gate")
            send_fn = context.get("send_fn")
            receive_fn = context.get("receive_fn")

            if gate and send_fn and receive_fn:
                req = gate.request_approval(
                    "command_execute",
                    f"Ejecutar: {command}",
                )
                await send_fn(
                    f"Comando potencialmente peligroso:\n"
                    f"```\n{command}\n```\n"
                    f"Apruebas la ejecucion? (si/no)"
                )
                response = await receive_fn()
                if not gate.check_response(req.request_id, response):
                    return SkillResult(
                        success=False,
                        message="Ejecucion cancelada por el usuario.",
                    )
            else:
                # No approval mechanism available — reject dangerous commands
                return SkillResult(
                    success=False,
                    message=(
                        "Este comando requiere aprobacion pero no hay "
                        "mecanismo de aprobacion disponible."
                    ),
                )

        # Execute via SandboxedExecutor or fallback to asyncio subprocess
        executor = context.get("sandbox") or context.get("executor")
        if executor is not None:
            return await self._run_sandboxed(command, executor)
        return await self._run_subprocess(command)

    async def _run_sandboxed(self, command: str, executor: Any) -> SkillResult:
        """Run via a SandboxedExecutor instance."""
        log.info("terminal.execute_sandboxed", command=command)
        try:
            result = await executor.run(command)
            stdout = result.get("stdout", "") if isinstance(result, dict) else str(result)
            stderr = result.get("stderr", "") if isinstance(result, dict) else ""
            exit_code = result.get("returncode", 0) if isinstance(result, dict) else 0

            return self._format_output(command, stdout, stderr, exit_code)

        except Exception as exc:
            log.error("terminal.sandbox_error", command=command, error=str(exc))
            return SkillResult(success=False, message=f"Error ejecutando comando: {exc}")

    async def _run_subprocess(self, command: str) -> SkillResult:
        """Run *command* as a subprocess and return captured output."""
        log.info("terminal.execute", command=command)

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=60,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return SkillResult(
                    success=False,
                    message="Comando cancelado: excedio el tiempo limite de 60s.",
                )

            stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
            stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
            exit_code = process.returncode or 0

            return self._format_output(command, stdout, stderr, exit_code)

        except Exception as exc:
            log.error("terminal.error", command=command, error=str(exc))
            return SkillResult(
                success=False,
                message=f"Error ejecutando comando: {exc}",
            )

    def _format_output(
        self, command: str, stdout: str, stderr: str, exit_code: int
    ) -> SkillResult:
        """Format command output into a SkillResult."""
        output_parts: list[str] = []
        if stdout:
            output_parts.append(stdout)
        if stderr:
            output_parts.append(f"[stderr]\n{stderr}")

        output = "\n".join(output_parts) if output_parts else "(sin salida)"

        # Truncate if too long
        if len(output) > _MAX_OUTPUT:
            output = (
                output[:_MAX_OUTPUT]
                + f"\n... (truncado, {len(output)} chars total)"
            )

        success = exit_code == 0
        header = f"Exit code: {exit_code}\n" if exit_code != 0 else ""

        return SkillResult(
            success=success,
            message=f"{header}```\n$ {command}\n{output}\n```",
            data={
                "exit_code": exit_code,
                "stdout": stdout[:2000],
                "stderr": stderr[:2000],
            },
        )
