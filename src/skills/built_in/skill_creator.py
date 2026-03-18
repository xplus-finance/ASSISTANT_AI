"""Meta-skill: generate new skills at runtime via Claude."""

from __future__ import annotations

import re
import textwrap
from pathlib import Path
from typing import Any

import structlog

from src.core.claude_bridge import ClaudeBridge, ClaudeBridgeError
from src.skills.base_skill import BaseSkill, SkillResult

log = structlog.get_logger("assistant.skills.skill_creator")

_GENERATION_PROMPT = textwrap.dedent("""\
    Genera un skill para un asistente de IA en Python.

    Requisitos:
    - Debe heredar de BaseSkill (importar de src.skills.base_skill)
    - Debe implementar: name, description, triggers, execute(args, context)
    - execute() es async y retorna SkillResult(success, message, data)
    - Los triggers deben empezar con "!" seguido de un nombre descriptivo
    - Incluir docstrings y type hints
    - Manejar errores apropiadamente
    - Responder en espanol en los mensajes al usuario

    Descripcion del skill a crear:
    {description}

    IMPORTANTE: Responde SOLO con el codigo Python, sin explicacion adicional.
    No uses bloques de codigo markdown. Solo el codigo puro.
""")


class SkillCreatorSkill(BaseSkill):


    def __init__(self, bridge: ClaudeBridge | None = None) -> None:
        self._bridge = bridge

    @property
    def name(self) -> str:
        return "skill_creator"

    @property
    def description(self) -> str:
        return "Crea nuevos skills a partir de una descripcion en lenguaje natural"

    @property
    def triggers(self) -> list[str]:
        return ["!skill"]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        if not args.strip():
            return SkillResult(
                success=False,
                message=(
                    "Uso:\n"
                    "  !skill crear <descripcion del skill>\n"
                    "  !skill listar — ver skills creados por el usuario"
                ),
            )

        parts = args.split(maxsplit=1)
        sub = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""

        if sub in ("crear", "create", "nuevo", "new"):
            return await self._create_skill(rest, context)
        elif sub in ("listar", "list"):
            return self._list_user_skills(context)
        else:
            # Treat as "crear" with the full args as description
            return await self._create_skill(args, context)

    async def _create_skill(
        self, description: str, context: dict[str, Any]
    ) -> SkillResult:
        if not description.strip():
            return SkillResult(
                success=False,
                message="Describe que quieres que haga el nuevo skill.",
            )

        bridge: ClaudeBridge | None = (
            self._bridge
            or context.get("bridge")
            or context.get("claude_bridge")
        )
        if bridge is None:
            bridge = ClaudeBridge()

        send_fn = context.get("send_fn")
        receive_fn = context.get("receive_fn")
        skills_dir = context.get("skills_dir") or context.get("user_skills_dir")

        if not skills_dir:
            return SkillResult(
                success=False,
                message="No se configuro el directorio de skills del usuario.",
            )

        try:
            available = await bridge.check_available()
            if not available:
                return SkillResult(
                    success=False,
                    message="Claude CLI no disponible para generar el skill.",
                )

            prompt = _GENERATION_PROMPT.format(description=description)
            generated_code = await bridge.ask(
                prompt,
                system_prompt=(
                    "Eres un generador de codigo Python. Genera SOLO codigo "
                    "Python valido, sin bloques markdown ni explicaciones."
                ),
                timeout=120,
            )
        except ClaudeBridgeError as exc:
            log.error("skill_creator.generation_error", error=str(exc))
            return SkillResult(
                success=False,
                message=f"Error generando el skill: {exc}",
            )

        code = self._clean_code(generated_code)

        if not code or len(code) < 50:
            return SkillResult(
                success=False,
                message="El codigo generado esta vacio o es demasiado corto.",
            )

        if send_fn and receive_fn:
            preview = code[:3000]
            if len(code) > 3000:
                preview += "\n... (truncado para preview)"

            await send_fn(
                f"Skill generado:\n```python\n{preview}\n```\n\n"
                f"Quieres activar este skill? (si/no)"
            )

            response = await receive_fn()
            normalized = response.strip().lower()
            if normalized not in ("si", "sí", "yes", "ok", "dale", "va"):
                return SkillResult(
                    success=False,
                    message="Creacion de skill cancelada.",
                )
        else:
            return SkillResult(
                success=False,
                message=(
                    "El skill fue generado pero no se puede guardar sin "
                    "aprobacion del usuario.\n\n"
                    f"```python\n{code[:2000]}\n```"
                ),
            )

        filename = self._derive_filename(code, description)
        filepath = Path(skills_dir) / filename

        try:
            Path(skills_dir).mkdir(parents=True, exist_ok=True)
            filepath.write_text(code, encoding="utf-8")
            log.info("skill_creator.saved", path=str(filepath))
        except Exception as exc:
            return SkillResult(
                success=False,
                message=f"Error guardando el skill: {exc}",
            )

        registry = context.get("registry") or context.get("skill_registry")
        if registry is not None:
            try:
                skill_instance = registry._load_skill_file(str(filepath))
                if skill_instance is not None:
                    registry.register(skill_instance)
                    return SkillResult(
                        success=True,
                        message=(
                            f"Skill creado y activado: {skill_instance.name}\n"
                            f"Triggers: {', '.join(skill_instance.triggers)}\n"
                            f"Archivo: {filepath}"
                        ),
                        data={
                            "name": skill_instance.name,
                            "path": str(filepath),
                            "triggers": skill_instance.triggers,
                        },
                    )
            except Exception:
                log.warning("skill_creator.register_error", exc_info=True)

        return SkillResult(
            success=True,
            message=(
                f"Skill guardado en: {filepath}\n"
                f"Se activara automaticamente si el watcher esta activo."
            ),
            data={"path": str(filepath)},
        )

    def _list_user_skills(self, context: dict[str, Any]) -> SkillResult:
        skills_dir = context.get("skills_dir") or context.get("user_skills_dir")
        if not skills_dir:
            return SkillResult(success=False, message="Directorio de skills no configurado.")

        skills_path = Path(skills_dir)
        if not skills_path.is_dir():
            return SkillResult(success=True, message="No hay skills de usuario creados.")

        files = sorted(skills_path.glob("*.py"))
        files = [f for f in files if not f.name.startswith("_")]

        if not files:
            return SkillResult(success=True, message="No hay skills de usuario creados.")

        lines = ["Skills de usuario:", ""]
        for f in files:
            size = f.stat().st_size
            lines.append(f"  {f.name} ({size:,} bytes)")

        return SkillResult(success=True, message="\n".join(lines))

    @staticmethod
    def _clean_code(raw: str) -> str:
        code = raw.strip()

        if code.startswith("```"):
            lines = code.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            code = "\n".join(lines)

        return code.strip()

    @staticmethod
    def _derive_filename(code: str, description: str) -> str:
        match = re.search(r"class\s+(\w+)\s*\(", code)
        if match:
            class_name = match.group(1)
            name = re.sub(r"(?<!^)(?=[A-Z])", "_", class_name).lower()
            name = re.sub(r"_?skill$", "", name)
            if name:
                return f"{name}_skill.py"

        words = re.sub(r"[^a-z0-9\s]", "", description.lower()).split()[:3]
        name = "_".join(words) if words else "custom"
        return f"{name}_skill.py"
