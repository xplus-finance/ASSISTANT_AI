"""Desktop control skill: screenshots, windows, tabs, keyboard."""

from __future__ import annotations

from typing import Any

import structlog

from src.skills.base_skill import BaseSkill, SkillResult

log = structlog.get_logger("assistant.skills.desktop_control")


class DesktopControlSkill(BaseSkill):


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
            "!pestañas", "!tabs",  # listar/escanear todas las pestañas
            "!claude",
        ]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        from src.core.desktop_control import DesktopControl

        desktop = DesktopControl()
        original = context.get("_original_text", "").lower().strip()

        if original.startswith(("!screenshot", "!captura")):
            return await self._do_screenshot(desktop)
        elif original.startswith(("!ventanas", "!windows")):
            return await self._do_list_windows(desktop)
        elif original.startswith(("!pestañas", "!tabs")):
            return await self._do_scan_all_tabs(desktop)
        elif original.startswith(("!tab", "!pestaña")):
            return await self._do_tab(desktop, args)
        elif original.startswith("!teclado"):
            return await self._do_type(desktop, args)
        elif original.startswith("!claude"):
            return await self._do_claude(desktop, args)

        args_lower = args.lower().strip()
        if not args_lower:
            return await self._do_screenshot(desktop)
        elif args_lower in ("next", "prev") or args_lower.isdigit():
            return await self._do_tab(desktop, args)
        else:
            return await self._do_type(desktop, args)

    async def _do_screenshot(self, desktop: Any) -> SkillResult:
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

    async def _do_scan_all_tabs(self, desktop: Any) -> SkillResult:
        # Intento 1: Chrome DevTools Protocol (instantáneo, sin mover nada)
        cdp_tabs = await desktop.list_browser_tabs_cdp()
        if cdp_tabs:
            lines = [f"Pestañas del navegador via CDP ({len(cdp_tabs)}):"]
            for t in cdp_tabs:
                lines.append(f"  [{t['index']+1}] {t['title']}")
                if t.get("url") and not t["url"].startswith("chrome://"):
                    lines.append(f"       {t['url']}")
            return SkillResult(
                success=True,
                message="\n".join(lines),
                data={"tabs": cdp_tabs, "method": "cdp"},
            )

        # Intento 2: iteración visual con Ctrl+Tab
        try:
            tabs = await desktop.scan_all_tabs(max_tabs=80)
            if not tabs:
                return SkillResult(
                    success=False,
                    message=(
                        "No encontré pestañas. Asegúrate de que el navegador esté en foco.\n"
                        "Para mejor resultado, activa CDP en Chrome:\n"
                        "  chromium --remote-debugging-port=9222 &"
                    ),
                )
            lines = [f"Pestañas escaneadas ({len(tabs)}):"]
            for t in tabs:
                lines.append(f"  [{t['index']+1}] {t['title']}")
            lines.append("\n(Escaneado visual. Para más info activa CDP: chromium --remote-debugging-port=9222)")
            return SkillResult(
                success=True,
                message="\n".join(lines),
                data={"tabs": tabs, "method": "visual_scan"},
            )
        except Exception as exc:
            return SkillResult(success=False, message=f"Error al escanear pestañas: {exc}")

    async def _do_claude(self, desktop: Any, args: str) -> SkillResult:
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
