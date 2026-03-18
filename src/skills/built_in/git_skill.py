"""Git repository operations."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import structlog

from src.skills.base_skill import BaseSkill, SkillResult
from src.utils.approval import ApprovalGate

log = structlog.get_logger("assistant.skills.git")

_MAX_OUTPUT = 4000


class GitSkill(BaseSkill):


    @property
    def name(self) -> str:
        return "git"

    @property
    def description(self) -> str:
        return "Operaciones Git: status, log, diff, branch, commit"

    @property
    def triggers(self) -> list[str]:
        return ["!git"]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        parts = args.strip().split(maxsplit=1)
        if not parts:
            return SkillResult(
                success=False,
                message=(
                    "Uso:\n"
                    "  !git status   — estado del repositorio\n"
                    "  !git log      — ultimos 10 commits\n"
                    "  !git diff     — cambios staged + unstaged\n"
                    "  !git branch   — listar ramas\n"
                    "  !git commit <mensaje> — commit (requiere aprobacion)"
                ),
            )

        sub = parts[0].lower()
        extra = parts[1] if len(parts) > 1 else ""
        cwd = self._find_git_root(context)

        if sub == "status":
            return await self._run_git("status --short", cwd)
        elif sub == "log":
            return await self._run_git("log --oneline -10", cwd)
        elif sub == "diff":
            return await self._git_diff(cwd)
        elif sub in ("branch", "ramas"):
            return await self._run_git("branch -a", cwd)
        elif sub == "commit":
            return await self._git_commit(extra, cwd, context)
        else:
            return SkillResult(
                success=False,
                message=f"Subcomando desconocido: {sub}. Usa: status, log, diff, branch, commit",
            )

    def _find_git_root(self, context: dict[str, Any]) -> str:
        start = Path(context.get("cwd") or os.getcwd())
        current = start
        for _ in range(20):
            if (current / ".git").exists():
                return str(current)
            parent = current.parent
            if parent == current:
                break
            current = parent
        return str(start)

    async def _run_git(self, cmd: str, cwd: str) -> SkillResult:
        full_cmd = f"git {cmd}"
        log.info("git.execute", command=full_cmd, cwd=cwd)

        try:
            proc = await asyncio.create_subprocess_shell(
                full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            out, err = await asyncio.wait_for(proc.communicate(), 30)
            stdout = out.decode("utf-8", errors="replace").strip()
            stderr = err.decode("utf-8", errors="replace").strip()

            if proc.returncode != 0:
                msg = stderr or stdout or "Comando git fallo"
                if "not a git repository" in msg.lower():
                    msg = f"No es un repositorio git: {cwd}"
                return SkillResult(success=False, message=msg)

            text = stdout or "(sin salida)"
            if len(text) > _MAX_OUTPUT:
                text = text[:_MAX_OUTPUT] + "\n... (truncado)"
            return SkillResult(success=True, message=f"```\n{text}\n```")

        except asyncio.TimeoutError:
            return SkillResult(success=False, message="Comando git excedio 30s.")
        except Exception as exc:
            return SkillResult(success=False, message=f"Error: {exc}")

    async def _git_diff(self, cwd: str) -> SkillResult:
        staged = await self._run_git("diff --cached --stat", cwd)
        unstaged = await self._run_git("diff --stat", cwd)

        parts: list[str] = []
        if staged.success and staged.message.strip() != "```\n(sin salida)\n```":
            parts.append("**Staged:**\n" + staged.message)
        if unstaged.success and unstaged.message.strip() != "```\n(sin salida)\n```":
            parts.append("**Unstaged:**\n" + unstaged.message)

        if not parts:
            return SkillResult(success=True, message="No hay cambios.")
        return SkillResult(success=True, message="\n\n".join(parts))

    async def _git_commit(
        self, message: str, cwd: str, context: dict[str, Any]
    ) -> SkillResult:
        if not message:
            return SkillResult(
                success=False,
                message="Especifica un mensaje: !git commit <mensaje>",
            )

        gate: ApprovalGate | None = context.get("approval_gate")
        send_fn = context.get("send_fn")
        receive_fn = context.get("receive_fn")

        if gate and send_fn and receive_fn:
            req = gate.request_approval(
                "command_execute",
                f"git add -A && git commit -m '{message}'",
            )
            await send_fn(
                f"Se hara commit con mensaje:\n"
                f"  \"{message}\"\n"
                f"Esto ejecuta `git add -A && git commit`. Apruebas? (si/no)"
            )
            response = await receive_fn()
            if not gate.check_response(req.request_id, response):
                return SkillResult(success=False, message="Commit cancelado.")
        else:
            return SkillResult(
                success=False,
                message="Commit requiere aprobacion pero no hay mecanismo disponible.",
            )

        add_result = await self._run_git("add -A", cwd)
        if not add_result.success:
            return add_result

        safe_msg = message.replace('"', '\\"')
        return await self._run_git(f'commit -m "{safe_msg}"', cwd)
