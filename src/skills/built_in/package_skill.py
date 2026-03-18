"""System package management."""

from __future__ import annotations

import asyncio
import shutil
from typing import Any

import structlog

from src.skills.base_skill import BaseSkill, SkillResult
from src.utils.approval import ApprovalGate
from src.utils.platform import IS_WINDOWS, IS_MACOS

log = structlog.get_logger("assistant.skills.package")
_MAX_OUTPUT = 4000

_INSTALL_CMDS = {
    "apt": "sudo apt install -y {pkg}", "dnf": "sudo dnf install -y {pkg}",
    "brew": "brew install {pkg}", "pacman": "sudo pacman -S --noconfirm {pkg}",
    "pip": "pip install {pkg}", "pip3": "pip3 install {pkg}",
    "npm": "npm install -g {pkg}", "cargo": "cargo install {pkg}",
}

_MANAGER_PRIORITY = ("pip3", "pip", "apt", "brew", "dnf", "pacman", "npm", "cargo")


def _detect_managers() -> dict[str, str]:
    return {n: p for n in _MANAGER_PRIORITY if (p := shutil.which(n))}


class PackageSkill(BaseSkill):


    @property
    def name(self) -> str:
        return "package"

    @property
    def description(self) -> str:
        return "Gestion de paquetes: instalar, buscar, listar, actualizar"

    @property
    def triggers(self) -> list[str]:
        return ["!paquete", "!package", "!install", "!pip", "!npm"]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        parts = args.strip().split(maxsplit=1)
        if not parts:
            return SkillResult(success=False, message=(
                "Uso:\n  !package instalar <nombre>\n  !package buscar <nombre>\n"
                "  !package lista\n  !package actualizar"))

        sub, query = parts[0].lower(), (parts[1].strip() if len(parts) > 1 else "")

        # Handle !pip install X / !npm install X
        raw = context.get("raw_text", "").lower().strip()
        forced = "pip" if raw.startswith("!pip") else ("npm" if raw.startswith("!npm") else None)
        if forced and sub in ("install", "instalar"):
            return await self._install(query, context, forced)

        if sub in ("instalar", "install"):
            return await self._install(query, context)
        elif sub in ("buscar", "search"):
            return await self._search(query)
        elif sub in ("lista", "list"):
            return await self._list_packages(forced)
        elif sub in ("actualizar", "update"):
            return await self._update(context)
        return SkillResult(success=False, message=f"Subcomando desconocido: {sub}")

    async def _approve(self, context: dict[str, Any], action: str, detail: str) -> bool:
        gate: ApprovalGate | None = context.get("approval_gate")
        send_fn, recv_fn = context.get("send_fn"), context.get("receive_fn")
        if not (gate and send_fn and recv_fn):
            return False
        req = gate.request_approval(action, detail)
        await send_fn(f"Se ejecutara:\n```\n{detail}\n```\nApruebas? (si/no)")
        return gate.check_response(req.request_id, await recv_fn())

    async def _install(self, pkg: str, ctx: dict[str, Any], forced: str | None = None) -> SkillResult:
        if not pkg:
            return SkillResult(success=False, message="Especifica un paquete: !package instalar <nombre>")
        managers = _detect_managers()
        mgr = forced if forced and forced in managers else next(iter(managers), None)
        if not mgr:
            return SkillResult(success=False, message="No se detecto un gestor de paquetes.")
        cmd = _INSTALL_CMDS.get(mgr, f"{mgr} install {{pkg}}").format(pkg=pkg)
        log.info("package.install", manager=mgr, package=pkg)
        if not await self._approve(ctx, "install_package", cmd):
            return SkillResult(success=False, message="Instalacion cancelada o sin mecanismo de aprobacion.")
        return await self._shell(cmd, 120)

    async def _search(self, query: str) -> SkillResult:
        if not query:
            return SkillResult(success=False, message="Especifica que buscar: !package buscar <nombre>")
        managers = _detect_managers()
        results: list[str] = []
        searches = []
        if "pip3" in managers or "pip" in managers:
            pip = "pip3" if "pip3" in managers else "pip"
            searches.append(("pip", f"{pip} index versions {query} 2>/dev/null || echo 'No encontrado'"))
        if "apt" in managers:
            searches.append(("apt", f"apt-cache search {query} | head -10"))
        if "npm" in managers:
            searches.append(("npm", f"npm search {query} --parseable 2>/dev/null | head -10"))
        for label, cmd in searches:
            r = await self._shell(cmd, 15)
            if r.success:
                results.append(f"**{label}:**\n{r.message}")
        return SkillResult(success=True, message="\n\n".join(results) or f"Sin resultados para '{query}'")

    async def _list_packages(self, forced: str | None = None) -> SkillResult:
        managers = _detect_managers()
        targets = [forced] if forced and forced in managers else list(managers.keys())
        lines: list[str] = []
        cmds = {
            "pip": "pip list --format=columns 2>/dev/null | head -25",
            "pip3": "pip3 list --format=columns 2>/dev/null | head -25",
            "apt": "dpkg --get-selections | wc -l",
            "npm": "npm list -g --depth=0 2>/dev/null",
        }
        for mgr in targets:
            if mgr in cmds:
                r = await self._shell(cmds[mgr], 10)
                if r.success:
                    lines.append(f"**{mgr}:**\n{r.message}")
        return SkillResult(success=True, message="\n\n".join(lines) or "No se detectaron gestores.")

    async def _update(self, ctx: dict[str, Any]) -> SkillResult:
        managers = _detect_managers()
        cmds: list[str] = []
        if "apt" in managers:
            cmds.append("sudo apt update")
        if "brew" in managers:
            cmds.append("brew update")
        pip = "pip3" if "pip3" in managers else ("pip" if "pip" in managers else None)
        if pip:
            cmds.append(f"{pip} list --outdated --format=columns 2>/dev/null | head -15")
        if not cmds:
            return SkillResult(success=False, message="No se detectaron gestores de paquetes.")
        if any("sudo" in c for c in cmds):
            if not await self._approve(ctx, "install_package", "Actualizar listas de paquetes"):
                return SkillResult(success=False, message="Actualizacion cancelada.")
        results = [r.message for c in cmds if (r := await self._shell(c, 60))]
        return SkillResult(success=True, message="\n\n".join(results))

    async def _shell(self, cmd: str, timeout: int = 30) -> SkillResult:
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            out, err = await asyncio.wait_for(proc.communicate(), timeout)
            text = out.decode("utf-8", errors="replace").strip()
            if err_text := err.decode("utf-8", errors="replace").strip():
                text += f"\n[stderr] {err_text}" if text else err_text
            if len(text) > _MAX_OUTPUT:
                text = text[:_MAX_OUTPUT] + "\n... (truncado)"
            return SkillResult(success=proc.returncode == 0,
                               message=f"```\n{text}\n```" if text else "(sin salida)")
        except asyncio.TimeoutError:
            return SkillResult(success=False, message=f"Comando excedio {timeout}s.")
        except Exception as exc:
            return SkillResult(success=False, message=f"Error: {exc}")
