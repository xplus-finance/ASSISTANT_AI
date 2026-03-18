"""File operations skill with path security validation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import structlog

from src.skills.base_skill import BaseSkill, SkillResult
from src.utils.platform import IS_WINDOWS

log = structlog.get_logger("assistant.skills.files")

_FORBIDDEN_PATHS_UNIX: frozenset[str] = frozenset({
    "/etc/shadow",
    "/etc/passwd",
    "/etc/sudoers",
    "/root",
    "/proc",
    "/sys",
    "/dev",
    "/boot",
})

_FORBIDDEN_PATHS_WIN: frozenset[str] = frozenset({
    "\\Windows\\System32\\config",
    "\\Windows\\repair",
    "\\Windows\\System32\\drivers\\etc\\hosts",
})

_FORBIDDEN_PATHS: frozenset[str] = _FORBIDDEN_PATHS_WIN if IS_WINDOWS else _FORBIDDEN_PATHS_UNIX

_MAX_READ_SIZE = 512_000  # 500 KB

_MAX_DISPLAY_OUTPUT = 4000


def _validate_file_access(
    path: str,
    allowed_dirs: list[str] | None = None,
    guardian: Any = None,
) -> str | None:
    resolved = str(Path(path).resolve())

    # Check via SecurityGuardian if available
    if guardian is not None:
        try:
            if not guardian.validate_file_access(resolved):
                return f"Acceso denegado por SecurityGuardian: {resolved}"
        except Exception as exc:
            log.warning("files.guardian_error", error=str(exc))

    # Check forbidden paths
    for forbidden in _FORBIDDEN_PATHS:
        if resolved.startswith(forbidden):
            return f"Acceso denegado: {resolved} esta en una ruta protegida."

    # If allowed_dirs is specified, enforce whitelist
    if allowed_dirs:
        if not any(resolved.startswith(d) for d in allowed_dirs):
            return (
                f"Acceso denegado: {resolved} no esta dentro de los "
                f"directorios permitidos."
            )

    return None


class FilesSkill(BaseSkill):


    @property
    def name(self) -> str:
        return "files"

    @property
    def description(self) -> str:
        return "Operaciones de archivos (leer, escribir, listar) con validacion de seguridad"

    @property
    def triggers(self) -> list[str]:
        return ["!file", "!files", "!read", "!write"]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        if not args:
            return SkillResult(
                success=False,
                message=(
                    "Uso:\n"
                    "  !file read <ruta>\n"
                    "  !file write <ruta> <contenido>\n"
                    "  !file list <ruta>"
                ),
            )

        parts = args.split(maxsplit=1)
        sub_cmd = parts[0].lower()
        rest = parts[1] if len(parts) > 1 else ""

        guardian = context.get("security_guardian") or context.get("guardian")
        allowed_dirs: list[str] | None = context.get("allowed_dirs")

        if sub_cmd == "read":
            return await self._read(rest.strip(), allowed_dirs, guardian)
        elif sub_cmd == "write":
            return await self._write(rest, allowed_dirs, guardian, context)
        elif sub_cmd in ("list", "ls"):
            return await self._list(rest.strip() or ".", allowed_dirs, guardian)
        else:
            # Treat the whole arg as a path to read
            return await self._read(args.strip(), allowed_dirs, guardian)

    async def _read(
        self,
        path: str,
        allowed_dirs: list[str] | None,
        guardian: Any,
    ) -> SkillResult:
        if not path:
            return SkillResult(success=False, message="Especifica la ruta del archivo.")

        path = os.path.expanduser(path)
        error = _validate_file_access(path, allowed_dirs, guardian)
        if error:
            return SkillResult(success=False, message=error)

        resolved = Path(path).resolve()

        if not resolved.exists():
            return SkillResult(success=False, message=f"Archivo no encontrado: {resolved}")

        if not resolved.is_file():
            return SkillResult(success=False, message=f"No es un archivo: {resolved}")

        size = resolved.stat().st_size
        if size > _MAX_READ_SIZE:
            return SkillResult(
                success=False,
                message=f"Archivo demasiado grande ({size:,} bytes, maximo {_MAX_READ_SIZE:,}).",
            )

        try:
            content = resolved.read_text(encoding="utf-8", errors="replace")
        except PermissionError:
            return SkillResult(success=False, message=f"Sin permisos para leer: {resolved}")
        except Exception as exc:
            return SkillResult(success=False, message=f"Error leyendo archivo: {exc}")

        display = content
        if len(display) > _MAX_DISPLAY_OUTPUT:
            display = display[:_MAX_DISPLAY_OUTPUT] + "\n... (contenido truncado)"

        return SkillResult(
            success=True,
            message=f"```\n{display}\n```",
            data={"path": str(resolved), "size": size, "content": content},
        )

    async def _write(
        self,
        args: str,
        allowed_dirs: list[str] | None,
        guardian: Any,
        context: dict[str, Any],
    ) -> SkillResult:
        parts = args.split(maxsplit=1)
        if len(parts) < 2:
            return SkillResult(
                success=False,
                message="Uso: !file write <ruta> <contenido>",
            )

        path, content = os.path.expanduser(parts[0]), parts[1]

        error = _validate_file_access(path, allowed_dirs, guardian)
        if error:
            return SkillResult(success=False, message=error)

        gate = context.get("approval_gate")
        send_fn = context.get("send_fn")
        receive_fn = context.get("receive_fn")

        if gate and send_fn and receive_fn:
            preview = content[:200] + ("..." if len(content) > 200 else "")
            req = gate.request_approval(
                "file_write",
                f"Escribir en {path}: {preview}",
            )
            await send_fn(
                f"Escribir en {path}?\n"
                f"Contenido: {preview}\n"
                f"Apruebas? (si/no)"
            )
            response = await receive_fn()
            if not gate.check_response(req.request_id, response):
                return SkillResult(success=False, message="Escritura cancelada.")

        resolved = Path(path).resolve()

        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
        except PermissionError:
            return SkillResult(success=False, message=f"Sin permisos para escribir: {resolved}")
        except Exception as exc:
            return SkillResult(success=False, message=f"Error escribiendo: {exc}")

        log.info("files.write", path=str(resolved), size=len(content))
        return SkillResult(
            success=True,
            message=f"Archivo escrito: {resolved} ({len(content)} chars)",
            data={"path": str(resolved), "size": len(content)},
        )

    async def _list(
        self,
        path: str,
        allowed_dirs: list[str] | None,
        guardian: Any,
    ) -> SkillResult:
        path = os.path.expanduser(path)
        error = _validate_file_access(path, allowed_dirs, guardian)
        if error:
            return SkillResult(success=False, message=error)

        resolved = Path(path).resolve()

        if not resolved.exists():
            return SkillResult(success=False, message=f"Directorio no encontrado: {resolved}")

        if not resolved.is_dir():
            return SkillResult(success=False, message=f"No es un directorio: {resolved}")

        try:
            entries = sorted(resolved.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return SkillResult(success=False, message=f"Sin permisos para listar: {resolved}")

        lines: list[str] = [f"Contenido de {resolved}:", ""]
        for entry in entries[:100]:
            indicator = "/" if entry.is_dir() else ""
            try:
                size = entry.stat().st_size if entry.is_file() else 0
                size_str = f"  ({size:,} bytes)" if size else ""
            except OSError:
                size_str = ""
            lines.append(f"  {entry.name}{indicator}{size_str}")

        total = len(entries)
        if total > 100:
            lines.append(f"  ... y {total - 100} mas")

        output = "\n".join(lines)
        return SkillResult(
            success=True,
            message=output,
            data={"path": str(resolved), "count": total},
        )
