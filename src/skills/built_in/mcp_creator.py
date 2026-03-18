"""
MCP Server creator skill.

When the assistant needs tools it doesn't have, it can create
MCP (Model Context Protocol) servers that provide new capabilities.
Uses Claude to generate the MCP server code, then installs and
activates it automatically.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import structlog

from src.skills.base_skill import BaseSkill, SkillResult
from src.utils.platform import IS_WINDOWS

log = structlog.get_logger("assistant.skills.mcp_creator")

_MCP_GENERATION_PROMPT = textwrap.dedent("""\
    Generate a complete MCP (Model Context Protocol) server in Python using FastMCP.

    The server should provide this capability:
    {description}

    Requirements:
    - Use `from mcp.server.fastmcp import FastMCP` (pip install "mcp[cli]")
    - Use FastMCP for simplicity: `mcp = FastMCP("server-name")`
    - Define tools with `@mcp.tool()` decorator
    - Include clear tool descriptions and parameter types
    - Handle errors gracefully with try/except
    - Include proper docstrings
    - The server should be self-contained in a single file
    - At the bottom: `if __name__ == "__main__": mcp.run()`

    Also generate a requirements.txt with ALL needed dependencies, one per line.

    Format your response EXACTLY like this:
    ```python
    <server code here>
    ```

    ```requirements
    <requirements here>
    ```
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
        return ["!mcp nueva", "!mcp crear", "!mcp instalar", "!mcp list", "!mcp"]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        args = args.strip()
        claude = context.get("claude")

        if not args or args.lower() in ("list", "lista"):
            return await self._list_mcps()

        if args.lower().startswith(("instalar ", "install ")):
            name = args.split(None, 1)[1] if " " in args else ""
            return await self._install_mcp(name)

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

        lines = ["Servidores MCP disponibles:\n"]
        for mcp in mcps:
            name = mcp.parent.name
            has_venv = (mcp.parent / ".venv").exists()
            status = "instalado" if has_venv else "sin instalar"
            lines.append(f"  - {name} ({status})")

        lines.append("\nUsa !mcp instalar <nombre> para instalar uno.")
        return SkillResult(success=True, message="\n".join(lines))

    async def _create_mcp(self, description: str, claude: Any) -> SkillResult:
        """Create a new MCP server from description."""
        # Clean name from description
        safe_name = "".join(
            c if c.isalnum() or c == "_" else "_"
            for c in description[:30].lower()
        ).strip("_")
        if not safe_name:
            safe_name = "custom_mcp"

        mcp_dir = Path("mcps") / safe_name
        mcp_dir.mkdir(parents=True, exist_ok=True)

        prompt = _MCP_GENERATION_PROMPT.format(description=description)

        try:
            response = await claude.ask(
                prompt=prompt,
                system_prompt=(
                    "You are an expert MCP server developer. "
                    "Return ONLY the code blocks as requested, no extra text."
                ),
                timeout=180,
            )

            # Parse response — extract python and requirements blocks
            code, requirements = self._parse_response(response)

            if not code:
                return SkillResult(
                    success=False,
                    message="No pude generar el código del MCP. Intenta con más detalle.",
                )

            # Save files
            server_path = mcp_dir / "server.py"
            server_path.write_text(code, encoding="utf-8")

            req_path = mcp_dir / "requirements.txt"
            if not requirements:
                requirements = 'mcp[cli]\n'
            if "mcp" not in requirements.lower():
                requirements = "mcp[cli]\n" + requirements
            req_path.write_text(requirements, encoding="utf-8")

            log.info("mcp_creator.created", name=safe_name, path=str(server_path))

            # Auto-install
            install_result = await self._install_mcp(safe_name)

            return SkillResult(
                success=True,
                message=(
                    f"MCP server '{safe_name}' creado e instalado.\n\n"
                    f"Ubicación: {server_path}\n"
                    f"{install_result.message}"
                ),
                data={"path": str(server_path), "name": safe_name},
            )

        except Exception:
            log.exception("mcp_creator.failed")
            return SkillResult(
                success=False,
                message="No pude crear el MCP server. Intenta con una descripción más detallada.",
            )

    async def _install_mcp(self, name: str) -> SkillResult:
        """Install dependencies and register an MCP server."""
        mcp_dir = Path("mcps") / name
        server_path = mcp_dir / "server.py"
        req_path = mcp_dir / "requirements.txt"

        if not server_path.exists():
            return SkillResult(
                success=False,
                message=f"MCP '{name}' no encontrado en mcps/{name}/server.py",
            )

        python = sys.executable
        venv_dir = mcp_dir / ".venv"
        pip = str(venv_dir / ("Scripts" if IS_WINDOWS else "bin") / "pip")
        venv_python = str(venv_dir / ("Scripts" if IS_WINDOWS else "bin") / "python")

        steps = []

        # Step 1: Create venv
        if not venv_dir.exists():
            try:
                result = await asyncio.to_thread(
                    subprocess.run,
                    [python, "-m", "venv", str(venv_dir)],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode == 0:
                    steps.append("Entorno virtual creado")
                else:
                    steps.append(f"Error creando venv: {result.stderr[:100]}")
            except Exception as e:
                steps.append(f"Error creando venv: {e}")

        # Step 2: Install requirements
        if req_path.exists():
            try:
                result = await asyncio.to_thread(
                    subprocess.run,
                    [pip, "install", "-r", str(req_path), "--quiet"],
                    capture_output=True, text=True, timeout=240,
                )
                if result.returncode == 0:
                    steps.append("Dependencias instaladas")
                else:
                    steps.append(f"Error instalando deps: {result.stderr[:100]}")
            except Exception as e:
                steps.append(f"Error instalando deps: {e}")

        # Step 3: Register with Claude CLI
        try:
            # claude mcp add -s user <name> -- <python> <server.py>
            register_cmd = [
                "claude", "mcp", "add",
                "-s", "user",
                name,
                "--",
                venv_python, str(server_path.resolve()),
            ]
            result = await asyncio.to_thread(
                subprocess.run,
                register_cmd,
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                steps.append(f"Registrado como MCP server '{name}' en Claude")
            else:
                # If claude mcp add fails, give manual instructions
                steps.append(
                    f"Para registrar manualmente:\n"
                    f"  claude mcp add -s user {name} -- {venv_python} {server_path.resolve()}"
                )
        except FileNotFoundError:
            steps.append(
                f"Claude CLI no encontrado. Registra manualmente:\n"
                f"  claude mcp add -s user {name} -- {venv_python} {server_path.resolve()}"
            )
        except Exception as e:
            steps.append(f"Error registrando: {e}")

        return SkillResult(
            success=True,
            message="\n".join(f"  - {s}" for s in steps),
        )

    @staticmethod
    def _parse_response(response: str) -> tuple[str, str]:
        """Parse Claude's response to extract code and requirements blocks."""
        code = ""
        requirements = ""

        # Extract ```python block
        if "```python" in response:
            start = response.index("```python") + len("```python")
            end = response.index("```", start)
            code = response[start:end].strip()
        elif "```" in response:
            # Try first code block
            start = response.index("```") + 3
            # Skip language identifier if present
            newline = response.index("\n", start)
            start = newline + 1
            end = response.index("```", start)
            code = response[start:end].strip()

        # Extract ```requirements block
        if "```requirements" in response:
            start = response.index("```requirements") + len("```requirements")
            end = response.index("```", start)
            requirements = response[start:end].strip()

        return code, requirements
