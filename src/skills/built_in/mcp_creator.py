"""
MCP Server creator skill.

When the assistant needs tools it doesn't have, it can create
MCP (Model Context Protocol) servers that provide new capabilities.
Uses Claude to generate the MCP server code.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import structlog

from src.skills.base_skill import BaseSkill, SkillResult

log = structlog.get_logger("assistant.skills.mcp_creator")

_MCP_GENERATION_PROMPT = textwrap.dedent("""\
    Generate a minimal MCP (Model Context Protocol) server in Python.

    The server should provide the following capability:
    {description}

    Requirements:
    - Use the `mcp` Python package (pip install mcp)
    - Use FastMCP for simplicity
    - Include proper tool descriptions
    - Handle errors gracefully
    - Include a requirements.txt with dependencies

    Return ONLY the Python code for the MCP server, nothing else.
    The code should be ready to run with: python server.py
""")


class MCPCreatorSkill(BaseSkill):
    """Creates MCP servers for new capabilities the assistant needs."""

    @property
    def name(self) -> str:
        return "mcp_creator"

    @property
    def description(self) -> str:
        return "Crear servidores MCP para agregar nuevas herramientas al asistente"

    @property
    def triggers(self) -> list[str]:
        return ["!mcp nueva", "!mcp crear", "!mcp list", "!mcp"]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        args = args.strip()
        claude = context.get("claude")

        if not args or args.lower() in ("list", "lista"):
            return await self._list_mcps()

        if not claude:
            return SkillResult(
                success=False,
                message="No puedo crear MCPs sin conexión a Claude.",
            )

        return await self._create_mcp(args, claude)

    async def _list_mcps(self) -> SkillResult:
        """List existing MCP servers."""
        mcp_dir = Path("mcps")
        if not mcp_dir.exists():
            return SkillResult(
                success=True,
                message="No hay servidores MCP creados todavía. "
                        "Usa !mcp crear [descripción] para crear uno.",
            )

        mcps = list(mcp_dir.glob("*/server.py"))
        if not mcps:
            return SkillResult(
                success=True,
                message="No hay servidores MCP creados todavía.",
            )

        lines = ["🔌 Servidores MCP disponibles:\n"]
        for mcp in mcps:
            name = mcp.parent.name
            lines.append(f"  • {name}")

        return SkillResult(success=True, message="\n".join(lines))

    async def _create_mcp(self, description: str, claude: Any) -> SkillResult:
        """Create a new MCP server from description."""
        # Clean name from description
        safe_name = "".join(
            c if c.isalnum() or c == "_" else "_"
            for c in description[:30].lower()
        ).strip("_")

        mcp_dir = Path("mcps") / safe_name
        mcp_dir.mkdir(parents=True, exist_ok=True)

        prompt = _MCP_GENERATION_PROMPT.format(description=description)

        try:
            code = await claude.ask(
                prompt=prompt,
                system_prompt="You are an MCP server generator. Return ONLY valid Python code.",
                timeout=60,
            )

            # Clean code — remove markdown fences if present
            code = code.strip()
            if code.startswith("```python"):
                code = code[len("```python"):].strip()
            if code.startswith("```"):
                code = code[3:].strip()
            if code.endswith("```"):
                code = code[:-3].strip()

            # Save the server
            server_path = mcp_dir / "server.py"
            server_path.write_text(code, encoding="utf-8")

            # Create requirements.txt
            req_path = mcp_dir / "requirements.txt"
            req_path.write_text("mcp\n", encoding="utf-8")

            log.info("mcp_creator.created", name=safe_name, path=str(server_path))

            return SkillResult(
                success=True,
                message=(
                    f"✅ Servidor MCP creado: {safe_name}\n\n"
                    f"📁 Ubicación: {server_path}\n\n"
                    f"Para activarlo:\n"
                    f"1. pip install -r {req_path}\n"
                    f"2. python {server_path}\n\n"
                    f"¿Quieres que lo instale y active ahora?"
                ),
                data={"path": str(server_path), "name": safe_name},
            )

        except Exception as exc:
            log.exception("mcp_creator.failed")
            return SkillResult(
                success=False,
                message=f"No pude crear el MCP server. Intenta con una descripción más detallada.",
            )
