"""Search files by name or content."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import structlog

from src.skills.base_skill import BaseSkill, SkillResult
from src.utils.platform import IS_WINDOWS

log = structlog.get_logger("assistant.skills.file_search")

_MAX_RESULTS = 20
_MAX_OUTPUT = 4000

_SKIP_DIRS: frozenset[str] = frozenset({
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".cache", ".local", ".npm", ".nvm", "dist", "build",
})

_FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "/proc", "/sys", "/dev", "/run", "/boot",
    "/etc/shadow", "/etc/gshadow",
)


class FileSearchSkill(BaseSkill):


    @property
    def name(self) -> str:
        return "file_search"

    @property
    def description(self) -> str:
        return "Buscar archivos por nombre o contenido"

    @property
    def triggers(self) -> list[str]:
        return ["!buscar archivo", "!find", "!grep", "!buscar"]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        parts = args.strip().split(maxsplit=1)
        if not parts:
            return SkillResult(
                success=False,
                message=(
                    "Uso:\n"
                    "  !buscar nombre <patron>  — buscar por nombre\n"
                    "  !buscar contenido <texto> — buscar dentro de archivos\n"
                    "  !buscar reciente          — archivos modificados recientemente"
                ),
            )

        sub = parts[0].lower()
        query = parts[1] if len(parts) > 1 else ""

        if sub in ("nombre", "name"):
            return await self._search_by_name(query, context)
        elif sub in ("contenido", "content"):
            return await self._search_by_content(query, context)
        elif sub in ("reciente", "recent"):
            return await self._recent_files(context)
        else:
            # Treat entire args as a name search
            return await self._search_by_name(args.strip(), context)

    def _get_base_dir(self, context: dict[str, Any]) -> Path:
        cwd = context.get("cwd") or os.environ.get("HOME", "/tmp")
        return Path(cwd)

    def _is_forbidden(self, path: Path) -> bool:
        path_str = str(path)
        return any(path_str.startswith(p) for p in _FORBIDDEN_PREFIXES)

    async def _search_by_name(self, pattern: str, context: dict[str, Any]) -> SkillResult:
        if not pattern:
            return SkillResult(success=False, message="Especifica un patron. Ejemplo: !find nombre *.py")

        base = self._get_base_dir(context)
        if not pattern.startswith("*"):
            pattern = f"*{pattern}*"

        log.info("file_search.name", pattern=pattern, base=str(base))
        results: list[str] = []

        try:
            for p in base.rglob(pattern):
                if any(skip in p.parts for skip in _SKIP_DIRS):
                    continue
                if self._is_forbidden(p):
                    continue
                results.append(str(p))
                if len(results) >= _MAX_RESULTS:
                    break
        except PermissionError:
            pass
        except Exception as exc:
            return SkillResult(success=False, message=f"Error en busqueda: {exc}")

        if not results:
            return SkillResult(success=True, message=f"No se encontraron archivos con patron '{pattern}'")

        header = f"**Archivos encontrados ({len(results)}):**\n"
        body = "\n".join(f"  {r}" for r in results)
        return SkillResult(success=True, message=header + body)

    async def _search_by_content(self, text: str, context: dict[str, Any]) -> SkillResult:
        if not text:
            return SkillResult(success=False, message="Especifica texto a buscar. Ejemplo: !grep contenido TODO")

        base = self._get_base_dir(context)
        log.info("file_search.content", text=text, base=str(base))

        exclude_args = " ".join(f"--exclude-dir={d}" for d in _SKIP_DIRS)
        cmd = (
            f"grep -rl --include='*' {exclude_args} "
            f"-m 1 -- {_shell_quote(text)} {_shell_quote(str(base))} "
            f"2>/dev/null | head -{_MAX_RESULTS}"
        )

        if IS_WINDOWS:
            cmd = f'findstr /S /M /C:"{text}" "{base}\\*"'

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), 30)
            raw = out.decode("utf-8", errors="replace").strip()
        except asyncio.TimeoutError:
            return SkillResult(success=False, message="Busqueda cancelada: excedio 30s.")
        except Exception as exc:
            return SkillResult(success=False, message=f"Error: {exc}")

        if not raw:
            return SkillResult(success=True, message=f"No se encontro '{text}' en archivos bajo {base}")

        files = raw.splitlines()[:_MAX_RESULTS]
        safe = [f for f in files if not any(f.startswith(p) for p in _FORBIDDEN_PREFIXES)]
        header = f"**Archivos que contienen '{text}' ({len(safe)}):**\n"
        body = "\n".join(f"  {f}" for f in safe)
        return SkillResult(success=True, message=header + body)

    async def _recent_files(self, context: dict[str, Any]) -> SkillResult:
        base = self._get_base_dir(context)
        log.info("file_search.recent", base=str(base))

        if IS_WINDOWS:
            cmd = f'forfiles /P "{base}" /S /D +0 /C "cmd /c echo @path @fdate @ftime" 2>nul'
        else:
            excludes = " ".join(f'-path "*/{d}" -prune -o' for d in _SKIP_DIRS)
            cmd = (
                f"find {_shell_quote(str(base))} -maxdepth 4 "
                f"{excludes} -type f -printf '%T@ %p\\n' 2>/dev/null "
                f"| sort -rn | head -{_MAX_RESULTS}"
            )

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), 15)
            raw = out.decode("utf-8", errors="replace").strip()
        except Exception as exc:
            return SkillResult(success=False, message=f"Error: {exc}")

        if not raw:
            return SkillResult(success=True, message="No se encontraron archivos recientes.")

        lines: list[str] = ["**Archivos recientes:**\n"]
        for line in raw.splitlines()[:_MAX_RESULTS]:
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                lines.append(f"  {parts[1]}")
            else:
                lines.append(f"  {line}")
        return SkillResult(success=True, message="\n".join(lines))


def _shell_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"
