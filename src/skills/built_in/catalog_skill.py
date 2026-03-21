"""Skill catalog management — browse, search, and install skills from templates."""

from __future__ import annotations

from typing import Any

from src.skills.base_skill import BaseSkill, SkillResult


class CatalogSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "catalog"

    @property
    def description(self) -> str:
        return "Explorar e instalar skills del catálogo de plantillas"

    @property
    def triggers(self) -> list[str]:
        return ["!catalogo", "!catálogo", "!catalog", "!plantillas"]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        from src.skills.catalog import SkillCatalog

        skills_dir = context.get("skills_dir", "skills")
        catalog = SkillCatalog(skills_dir=skills_dir)

        parts = args.strip().split(maxsplit=1)
        action = parts[0].lower() if parts else "list"
        param = parts[1].strip() if len(parts) > 1 else ""

        if action in ("list", "listar", "ver", ""):
            return SkillResult(success=True, message=catalog.format_catalog())

        if action in ("buscar", "search"):
            if not param:
                return SkillResult(success=False, message="Uso: !catalogo buscar <término>")
            results = catalog.search_templates(param)
            if not results:
                return SkillResult(success=True, message=f"No encontré plantillas para '{param}'")
            lines = [f"🔍 Resultados para '{param}':\n"]
            for tpl in results:
                lines.append(f"  • {tpl.name} ({tpl.category}) — {tpl.description}")
                lines.append(f"    Triggers: {', '.join(tpl.triggers)}")
            return SkillResult(success=True, message="\n".join(lines))

        if action in ("instalar", "install"):
            if not param:
                return SkillResult(success=False, message="Uso: !catalogo instalar <nombre>")
            path = catalog.install_template(param)
            if path:
                return SkillResult(
                    success=True,
                    message=f"✅ Skill '{param}' instalado en {path}\nSe cargará automáticamente por hot-reload.",
                )
            tpl = catalog.get_template(param)
            if not tpl:
                available = [t.name for t in catalog.get_templates()]
                return SkillResult(
                    success=False,
                    message=f"Plantilla '{param}' no encontrada.\nDisponibles: {', '.join(available)}",
                )
            return SkillResult(success=False, message=f"No se pudo instalar '{param}'")

        if action in ("categorias", "categories"):
            cats = catalog.get_categories()
            return SkillResult(
                success=True,
                message="🏷️ Categorías: " + ", ".join(cats),
            )

        return SkillResult(
            success=False,
            message="Uso: !catalogo [list|buscar|instalar|categorias] [argumento]",
        )
