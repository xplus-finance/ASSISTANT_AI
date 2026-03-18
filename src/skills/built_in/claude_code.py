"""
Claude Code integration skill — delegate project tasks to the Claude CLI.

Uses ``ClaudeBridge`` to execute tasks within a project context, with
tool restrictions and turn limits for safety.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from src.core.claude_bridge import ClaudeBridge, ClaudeBridgeError
from src.skills.base_skill import BaseSkill, SkillResult

log = structlog.get_logger("assistant.skills.claude_code")


class ClaudeCodeSkill(BaseSkill):
    """Delegate programming and project tasks to Claude Code CLI."""

    def __init__(self, bridge: ClaudeBridge | None = None) -> None:
        self._bridge = bridge

    @property
    def name(self) -> str:
        return "claude_code"

    @property
    def description(self) -> str:
        return "Integra con Claude Code CLI para tareas de programacion y proyectos"

    @property
    def triggers(self) -> list[str]:
        return ["!claude", "!code", "!proyecto"]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        """
        Execute a Claude Code task.

        Sub-commands:
            ``!claude <prompt>``      — ask Claude a question
            ``!code <path> <task>``   — execute a task in a project directory
            ``!proyecto <path>``      — analyze/work on a project
            ``!claude status``        — check if Claude CLI is available

        Context keys used:
            ``bridge`` (ClaudeBridge): Pre-configured bridge instance.
        """
        bridge = self._bridge or context.get("bridge") or context.get("claude_bridge")
        if bridge is None:
            bridge = ClaudeBridge()

        if not args.strip():
            return SkillResult(
                success=False,
                message=(
                    "Uso:\n"
                    "  !claude <pregunta>         — preguntar a Claude\n"
                    "  !claude status             — verificar disponibilidad\n"
                    "  !code <ruta> <tarea>       — tarea en proyecto\n"
                    "  !proyecto <ruta> [tarea]   — analizar proyecto"
                ),
            )

        original = context.get("original_text", "").lower().strip()

        if original.startswith("!code"):
            return await self._project_task(bridge, args)
        elif original.startswith("!proyecto"):
            return await self._analyze_project(bridge, args)
        elif args.strip().lower() == "status":
            return await self._check_status(bridge)
        else:
            return await self._ask(bridge, args)

    # ------------------------------------------------------------------
    # Sub-commands
    # ------------------------------------------------------------------

    async def _ask(self, bridge: ClaudeBridge, prompt: str) -> SkillResult:
        """Send a direct question to Claude."""
        prompt = prompt.strip()
        if not prompt:
            return SkillResult(success=False, message="Escribe una pregunta despues de !claude")

        try:
            available = await bridge.check_available()
            if not available:
                return SkillResult(
                    success=False,
                    message=(
                        "Claude CLI no esta disponible. "
                        "Asegurate de tener claude instalado y autenticado."
                    ),
                )

            response = await bridge.ask(
                prompt,
                system_prompt=(
                    "Eres un asistente tecnico. Responde de forma concisa y "
                    "directa en espanol. Si incluyes codigo, usa bloques de codigo."
                ),
            )

            return SkillResult(success=True, message=response)

        except ClaudeBridgeError as exc:
            log.error("claude_code.ask_error", error=str(exc))
            return SkillResult(success=False, message=f"Error de Claude: {exc}")

    async def _project_task(self, bridge: ClaudeBridge, args: str) -> SkillResult:
        """Execute a task scoped to a project directory."""
        parts = args.split(maxsplit=1)
        if not parts:
            return SkillResult(
                success=False,
                message="Uso: !code <ruta_proyecto> <descripcion_tarea>",
            )

        project_path = parts[0]
        task = parts[1] if len(parts) > 1 else "Analiza la estructura del proyecto y describe que hace."

        # Validate path
        resolved = Path(project_path).resolve()
        if not resolved.is_dir():
            return SkillResult(
                success=False,
                message=f"Directorio no encontrado: {resolved}",
            )

        try:
            available = await bridge.check_available()
            if not available:
                return SkillResult(
                    success=False,
                    message="Claude CLI no disponible.",
                )

            response = await bridge.execute_in_project(
                task=task,
                project_path=str(resolved),
                system_prompt=(
                    "Eres un asistente de desarrollo. Analiza el codigo y "
                    "responde en espanol. Se conciso y preciso."
                ),
                timeout=600,
            )

            return SkillResult(
                success=True,
                message=response,
                data={"project_path": str(resolved), "task": task},
            )

        except ClaudeBridgeError as exc:
            log.error("claude_code.project_error", error=str(exc), path=str(resolved))
            return SkillResult(success=False, message=f"Error ejecutando tarea: {exc}")

    async def _analyze_project(self, bridge: ClaudeBridge, args: str) -> SkillResult:
        """Analyze a project directory."""
        parts = args.split(maxsplit=1)
        if not parts:
            return SkillResult(
                success=False,
                message="Uso: !proyecto <ruta> [pregunta especifica]",
            )

        project_path = parts[0]
        question = parts[1] if len(parts) > 1 else None

        resolved = Path(project_path).resolve()
        if not resolved.is_dir():
            return SkillResult(
                success=False,
                message=f"Directorio no encontrado: {resolved}",
            )

        task = question or (
            "Analiza este proyecto:\n"
            "1. Que tecnologias usa?\n"
            "2. Cual es su estructura?\n"
            "3. Cual es su proposito principal?\n"
            "Resume en maximo 10 lineas."
        )

        try:
            response = await bridge.execute_in_project(
                task=task,
                project_path=str(resolved),
                system_prompt="Responde en espanol. Se conciso.",
                timeout=360,
            )

            return SkillResult(
                success=True,
                message=response,
                data={"project_path": str(resolved)},
            )

        except ClaudeBridgeError as exc:
            log.error("claude_code.analyze_error", error=str(exc))
            return SkillResult(success=False, message=f"Error analizando proyecto: {exc}")

    async def _check_status(self, bridge: ClaudeBridge) -> SkillResult:
        """Check if the Claude CLI is available."""
        available = await bridge.check_available()
        if available:
            return SkillResult(
                success=True,
                message="Claude CLI esta disponible y funcionando.",
            )
        return SkillResult(
            success=False,
            message=(
                "Claude CLI no esta disponible.\n"
                "Verifica que esta instalado: npm install -g @anthropic-ai/claude-code\n"
                "Y que estas autenticado: claude auth login"
            ),
        )
