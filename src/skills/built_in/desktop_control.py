"""
Desktop control skill — expose desktop commands via Telegram.

Allows the user to take screenshots, list windows, switch browser tabs,
type text, and send messages to another Claude Code instance.
"""

from __future__ import annotations

from typing import Any

import structlog

from src.skills.base_skill import BaseSkill, SkillResult

log = structlog.get_logger("assistant.skills.desktop_control")


class DesktopControlSkill(BaseSkill):
    """Expose desktop control actions as Telegram commands."""

    @property
    def name(self) -> str:
        return "desktop_control"

    @property
    def description(self) -> str:
        return "Control del escritorio: capturas, ventanas, pestañas, teclado y Claude Code"

    @property
    def triggers(self) -> list[str]:
        return [
            "!screenshot", "!captura",
            "!teclado",
            "!ventanas", "!windows",
            "!tab", "!pestaña",
            "!claude",
        ]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        """Route to the correct desktop action based on the original trigger."""
        from src.core.desktop_control import DesktopControl

        desktop = DesktopControl()
        original = context.get("_original_text", "").lower().strip()

        # Determine subcommand from the original trigger
        if original.startswith(("!screenshot", "!captura")):
            return await self._do_screenshot(desktop)
        elif original.startswith(("!ventanas", "!windows")):
            return await self._do_list_windows(desktop)
        elif original.startswith(("!tab", "!pestaña")):
            return await self._do_tab(desktop, args)
        elif original.startswith("!teclado"):
            return await self._do_type(desktop, args)
        elif original.startswith("!claude"):
            return await self._do_claude(desktop, args)

        # Fallback heuristics when _original_text is not available
        args_lower = args.lower().strip()
        if not args_lower:
            return await self._do_screenshot(desktop)
        elif args_lower in ("next", "prev") or args_lower.isdigit():
            return await self._do_tab(desktop, args)
        else:
            return await self._do_type(desktop, args)

    # ------------------------------------------------------------------
    # Subcommands
    # ------------------------------------------------------------------

    async def _do_screenshot(self, desktop: Any) -> SkillResult:
        """Take a screenshot and return the image path."""
        try:
            path = await desktop.take_screenshot()
            return SkillResult(
                success=True,
                message=path,
                data={"type": "screenshot", "path": path},
            )
        except Exception as exc:
            return SkillResult(success=False, message=f"Error al tomar captura: {exc}")

    async def _do_list_windows(self, desktop: Any) -> SkillResult:
        """List all open windows."""
        try:
            windows = await desktop.list_windows()
            if not windows:
                return SkillResult(success=True, message="No se encontraron ventanas abiertas.")

            lines = [f"Ventanas abiertas ({len(windows)}):"]
            for w in windows:
                lines.append(f"  - [{w['id']}] {w['title']}")
            return SkillResult(success=True, message="\n".join(lines))
        except Exception as exc:
            return SkillResult(success=False, message=f"Error al listar ventanas: {exc}")

    async def _do_tab(self, desktop: Any, args: str) -> SkillResult:
        """Switch browser tab: next, prev, or specific number."""
        args = args.strip().lower()
        try:
            if args.isdigit():
                tab_num = int(args)
                await desktop.go_to_browser_tab(tab_num)
                return SkillResult(success=True, message=f"Cambiado a pestaña {tab_num}.")
            elif args == "prev":
                await desktop.switch_browser_tab("prev")
                return SkillResult(success=True, message="Pestaña anterior.")
            else:
                await desktop.switch_browser_tab("next")
                return SkillResult(success=True, message="Siguiente pestaña.")
        except Exception as exc:
            return SkillResult(success=False, message=f"Error al cambiar pestaña: {exc}")

    async def _do_type(self, desktop: Any, args: str) -> SkillResult:
        """Type text using the keyboard."""
        text = args.strip()
        if not text:
            return SkillResult(
                success=False,
                message="Uso: !teclado <texto a escribir>",
            )
        try:
            await desktop.type_text(text)
            return SkillResult(success=True, message=f"Texto escrito: {text[:100]}")
        except Exception as exc:
            return SkillResult(success=False, message=f"Error al escribir texto: {exc}")

    async def _do_claude(self, desktop: Any, args: str) -> SkillResult:
        """Send a message to the user's Claude Code instance in VS Code."""
        message = args.strip()
        if not message:
            return SkillResult(
                success=False,
                message="Uso: !claude <mensaje para Claude Code>",
            )
        try:
            sent = await desktop.send_to_claude_code(message)
            if sent:
                return SkillResult(
                    success=True,
                    message=f"Mensaje enviado a Claude Code: {message[:100]}",
                )
            else:
                return SkillResult(
                    success=False,
                    message="No encontre una ventana de Claude Code abierta.",
                )
        except Exception as exc:
            return SkillResult(success=False, message=f"Error al enviar a Claude: {exc}")
