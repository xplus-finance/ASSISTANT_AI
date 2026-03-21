"""Skill catalog — templates and directory for creating new skills quickly."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger("assistant.skills.catalog")


@dataclass
class SkillTemplate:
    """A template for creating a new skill."""
    name: str
    category: str
    description: str
    triggers: list[str]
    code_template: str
    dependencies: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------
# Built-in templates organized by category
# ---------------------------------------------------------------

_TEMPLATES: dict[str, list[SkillTemplate]] = {
    "finance": [
        SkillTemplate(
            name="currency_converter",
            category="finance",
            description="Convertir entre monedas usando tasas en tiempo real",
            triggers=["!cambio", "!moneda", "!divisa", "!currency"],
            dependencies=["aiohttp"],
            tags=["finanzas", "divisas", "conversión"],
            code_template='''"""Currency converter skill using free exchange rate API."""

from __future__ import annotations
import asyncio, json, urllib.request
from typing import Any
from src.skills.base_skill import BaseSkill, SkillResult

class CurrencyConverterSkill(BaseSkill):
    @property
    def name(self) -> str: return "currency_converter"
    @property
    def description(self) -> str: return "Convertir entre monedas (ej: !cambio 100 USD a MXN)"
    @property
    def triggers(self) -> list[str]: return ["!cambio", "!moneda", "!divisa", "!currency"]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        import re
        match = re.match(r"(\\d+\\.?\\d*)\\s*(\\w{{3}})\\s*(?:a|to)\\s*(\\w{{3}})", args.strip(), re.IGNORECASE)
        if not match:
            return SkillResult(success=False, message="Uso: !cambio 100 USD a MXN")
        amount, src, dst = float(match.group(1)), match.group(2).upper(), match.group(3).upper()
        try:
            url = f"https://open.er-api.com/v6/latest/{{src}}"
            data = await asyncio.to_thread(lambda: json.loads(urllib.request.urlopen(url, timeout=10).read()))
            rate = data["rates"].get(dst)
            if rate is None:
                return SkillResult(success=False, message=f"Moneda {{dst}} no encontrada")
            result = amount * rate
            return SkillResult(success=True, message=f"{{amount}} {{src}} = {{result:,.2f}} {{dst}} (tasa: {{rate:.4f}})")
        except Exception as e:
            return SkillResult(success=False, message=f"Error consultando tasas: {{e}}")
''',
        ),
        SkillTemplate(
            name="crypto_price",
            category="finance",
            description="Consultar precio de criptomonedas",
            triggers=["!crypto", "!bitcoin", "!btc", "!precio crypto"],
            dependencies=[],
            tags=["finanzas", "crypto", "bitcoin"],
            code_template='''"""Cryptocurrency price checker via CoinGecko free API."""

from __future__ import annotations
import asyncio, json, urllib.request
from typing import Any
from src.skills.base_skill import BaseSkill, SkillResult

class CryptoPriceSkill(BaseSkill):
    @property
    def name(self) -> str: return "crypto_price"
    @property
    def description(self) -> str: return "Consultar precio de criptomonedas (ej: !crypto bitcoin)"
    @property
    def triggers(self) -> list[str]: return ["!crypto", "!bitcoin", "!btc"]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        coin = args.strip().lower() or "bitcoin"
        coin_map = {{"btc": "bitcoin", "eth": "ethereum", "sol": "solana", "ada": "cardano",
                     "doge": "dogecoin", "xrp": "ripple", "bnb": "binancecoin"}}
        coin = coin_map.get(coin, coin)
        try:
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={{coin}}&vs_currencies=usd,mxn&include_24hr_change=true"
            data = await asyncio.to_thread(lambda: json.loads(urllib.request.urlopen(url, timeout=10).read()))
            if coin not in data:
                return SkillResult(success=False, message=f"Crypto '{{coin}}' no encontrada")
            info = data[coin]
            usd = info.get("usd", 0)
            mxn = info.get("mxn", 0)
            change = info.get("usd_24h_change", 0)
            arrow = "📈" if change > 0 else "📉"
            return SkillResult(success=True, message=f"{{arrow}} {{coin.title()}}\\nUSD: ${{usd:,.2f}}\\nMXN: ${{mxn:,.2f}}\\n24h: {{change:+.2f}}%")
        except Exception as e:
            return SkillResult(success=False, message=f"Error: {{e}}")
''',
        ),
    ],
    "marketing": [
        SkillTemplate(
            name="seo_analyzer",
            category="marketing",
            description="Analizar SEO básico de una URL",
            triggers=["!seo", "!analizar seo"],
            dependencies=["beautifulsoup4"],
            tags=["marketing", "seo", "web"],
            code_template='''"""Basic SEO analyzer skill."""

from __future__ import annotations
import asyncio, urllib.request, re
from typing import Any
from src.skills.base_skill import BaseSkill, SkillResult

class SEOAnalyzerSkill(BaseSkill):
    @property
    def name(self) -> str: return "seo_analyzer"
    @property
    def description(self) -> str: return "Analizar SEO básico de una URL (ej: !seo https://example.com)"
    @property
    def triggers(self) -> list[str]: return ["!seo", "!analizar seo"]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        url = args.strip()
        if not url.startswith("http"):
            return SkillResult(success=False, message="Uso: !seo https://ejemplo.com")
        try:
            def _fetch():
                req = urllib.request.Request(url, headers={{"User-Agent": "Mozilla/5.0"}})
                return urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="replace")
            html = await asyncio.to_thread(_fetch)
            title = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
            desc = re.search(r\'meta\\s+name=["\\']description["\\']\\s+content=["\\\'](.*?)["\\\']\', html, re.I)
            h1s = re.findall(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
            imgs = re.findall(r"<img[^>]*>", html, re.I)
            imgs_no_alt = [i for i in imgs if \'alt="\' not in i.lower() and "alt=\'" not in i.lower()]
            lines = [f"🔍 SEO de {{url}}"]
            lines.append(f"Title: {{title.group(1).strip()[:60] if title else \'❌ SIN TITLE\'}}")
            lines.append(f"Meta desc: {{desc.group(1).strip()[:100] if desc else \'❌ SIN META DESC\'}}")
            lines.append(f"H1s: {{len(h1s)}} {{\'✅\' if len(h1s) == 1 else \'⚠️ debería haber exactamente 1\'}}")
            lines.append(f"Imágenes: {{len(imgs)}} total, {{len(imgs_no_alt)}} sin alt")
            return SkillResult(success=True, message="\\n".join(lines))
        except Exception as e:
            return SkillResult(success=False, message=f"Error: {{e}}")
''',
        ),
    ],
    "automation": [
        SkillTemplate(
            name="cron_manager",
            category="automation",
            description="Gestionar cron jobs del sistema",
            triggers=["!cron", "!crontab"],
            dependencies=[],
            tags=["automatización", "cron", "sistema"],
            code_template='''"""Cron job manager skill."""

from __future__ import annotations
import asyncio, subprocess
from typing import Any
from src.skills.base_skill import BaseSkill, SkillResult

class CronManagerSkill(BaseSkill):
    @property
    def name(self) -> str: return "cron_manager"
    @property
    def description(self) -> str: return "Gestionar cron jobs (ej: !cron list)"
    @property
    def triggers(self) -> list[str]: return ["!cron", "!crontab"]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        action = args.strip().lower().split()[0] if args.strip() else "list"
        if action == "list":
            proc = await asyncio.to_thread(lambda: subprocess.run(["crontab", "-l"], capture_output=True, text=True))
            jobs = proc.stdout.strip() if proc.returncode == 0 else "No hay cron jobs configurados"
            return SkillResult(success=True, message=f"📋 Cron jobs:\\n{{jobs}}")
        return SkillResult(success=False, message="Uso: !cron list")
''',
        ),
        SkillTemplate(
            name="clipboard_manager",
            category="automation",
            description="Gestionar portapapeles del sistema",
            triggers=["!clipboard", "!portapapeles", "!copiar"],
            dependencies=[],
            tags=["automatización", "portapapeles", "escritorio"],
            code_template='''"""Clipboard manager skill."""

from __future__ import annotations
import asyncio, subprocess, shutil
from typing import Any
from src.skills.base_skill import BaseSkill, SkillResult

class ClipboardManagerSkill(BaseSkill):
    @property
    def name(self) -> str: return "clipboard_manager"
    @property
    def description(self) -> str: return "Gestionar portapapeles (ej: !clipboard)"
    @property
    def triggers(self) -> list[str]: return ["!clipboard", "!portapapeles"]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        action = args.strip().split()[0].lower() if args.strip() else "get"
        if action == "get":
            if shutil.which("xclip"):
                proc = await asyncio.to_thread(lambda: subprocess.run(["xclip", "-selection", "clipboard", "-o"], capture_output=True, text=True, timeout=5))
                content = proc.stdout[:500] if proc.returncode == 0 else "Error leyendo portapapeles"
            elif shutil.which("xsel"):
                proc = await asyncio.to_thread(lambda: subprocess.run(["xsel", "--clipboard", "--output"], capture_output=True, text=True, timeout=5))
                content = proc.stdout[:500] if proc.returncode == 0 else "Error leyendo portapapeles"
            else:
                content = "No hay herramienta de portapapeles (xclip/xsel)"
            return SkillResult(success=True, message=f"📋 Portapapeles:\\n{{content}}")
        return SkillResult(success=False, message="Uso: !clipboard (muestra contenido actual)")
''',
        ),
    ],
    "cybersecurity": [
        SkillTemplate(
            name="hash_tool",
            category="cybersecurity",
            description="Generar y verificar hashes de archivos/texto",
            triggers=["!hash", "!checksum", "!md5", "!sha256"],
            dependencies=[],
            tags=["seguridad", "hash", "verificación"],
            code_template='''"""Hash generation and verification skill."""

from __future__ import annotations
import asyncio, hashlib
from pathlib import Path
from typing import Any
from src.skills.base_skill import BaseSkill, SkillResult

class HashToolSkill(BaseSkill):
    @property
    def name(self) -> str: return "hash_tool"
    @property
    def description(self) -> str: return "Generar hashes (ej: !hash sha256 texto o !hash md5 /ruta/archivo)"
    @property
    def triggers(self) -> list[str]: return ["!hash", "!checksum", "!md5", "!sha256"]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        parts = args.strip().split(maxsplit=1)
        if len(parts) < 1:
            return SkillResult(success=False, message="Uso: !hash [md5|sha256|sha512] texto_o_archivo")
        algo = parts[0].lower() if parts[0].lower() in ("md5", "sha1", "sha256", "sha512") else "sha256"
        target = parts[1] if len(parts) > 1 else parts[0]
        if algo == target:
            return SkillResult(success=False, message="Falta el texto o archivo")
        try:
            h = hashlib.new(algo)
            p = Path(target)
            if p.is_file():
                def _hash_file():
                    with open(p, "rb") as f:
                        for chunk in iter(lambda: f.read(8192), b""):
                            h.update(chunk)
                    return h.hexdigest()
                result = await asyncio.to_thread(_hash_file)
                return SkillResult(success=True, message=f"🔐 {{algo.upper()}} de {{p.name}}:\\n{{result}}")
            else:
                h.update(target.encode())
                return SkillResult(success=True, message=f"🔐 {{algo.upper()}}:\\n{{h.hexdigest()}}")
        except Exception as e:
            return SkillResult(success=False, message=f"Error: {{e}}")
''',
        ),
    ],
    "web": [
        SkillTemplate(
            name="http_status",
            category="web",
            description="Verificar estado HTTP de URLs",
            triggers=["!status", "!http", "!ping web"],
            dependencies=[],
            tags=["web", "http", "monitoreo"],
            code_template='''"""HTTP status checker skill."""

from __future__ import annotations
import asyncio, urllib.request, time
from typing import Any
from src.skills.base_skill import BaseSkill, SkillResult

class HTTPStatusSkill(BaseSkill):
    @property
    def name(self) -> str: return "http_status"
    @property
    def description(self) -> str: return "Verificar estado HTTP (ej: !status https://example.com)"
    @property
    def triggers(self) -> list[str]: return ["!status", "!http"]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        url = args.strip()
        if not url.startswith("http"):
            url = "https://" + url
        try:
            def _check():
                start = time.time()
                req = urllib.request.Request(url, method="HEAD", headers={{"User-Agent": "Mozilla/5.0"}})
                resp = urllib.request.urlopen(req, timeout=10)
                elapsed = (time.time() - start) * 1000
                return resp.status, elapsed
            status, ms = await asyncio.to_thread(_check)
            emoji = "✅" if status < 400 else "⚠️" if status < 500 else "❌"
            return SkillResult(success=True, message=f"{{emoji}} {{url}}\\nEstado: {{status}}\\nTiempo: {{ms:.0f}}ms")
        except Exception as e:
            return SkillResult(success=False, message=f"❌ {{url}}\\nError: {{e}}")
''',
        ),
    ],
}


class SkillCatalog:
    """Manages skill templates and facilitates skill creation."""

    def __init__(self, skills_dir: str | Path = "skills") -> None:
        self._skills_dir = Path(skills_dir)
        self._templates = dict(_TEMPLATES)  # Copy built-in templates

    def get_categories(self) -> list[str]:
        """Get all available template categories."""
        return sorted(self._templates.keys())

    def get_templates(self, category: str | None = None) -> list[SkillTemplate]:
        """Get templates, optionally filtered by category."""
        if category:
            return self._templates.get(category, [])
        all_templates: list[SkillTemplate] = []
        for cat_templates in self._templates.values():
            all_templates.extend(cat_templates)
        return all_templates

    def get_template(self, name: str) -> SkillTemplate | None:
        """Get a specific template by name."""
        for cat_templates in self._templates.values():
            for tpl in cat_templates:
                if tpl.name == name:
                    return tpl
        return None

    def search_templates(self, query: str) -> list[SkillTemplate]:
        """Search templates by name, description, or tags."""
        query_lower = query.lower()
        results: list[SkillTemplate] = []
        for tpl in self.get_templates():
            if (query_lower in tpl.name.lower()
                    or query_lower in tpl.description.lower()
                    or any(query_lower in tag for tag in tpl.tags)):
                results.append(tpl)
        return results

    def install_template(self, name: str) -> Path | None:
        """Install a skill from template into the skills directory.

        Returns the path of the created file, or None on failure.
        """
        tpl = self.get_template(name)
        if not tpl:
            log.warning("catalog.template_not_found", name=name)
            return None

        self._skills_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{tpl.name}.py"
        filepath = self._skills_dir / filename

        if filepath.exists():
            log.info("catalog.skill_already_exists", name=name, path=str(filepath))
            return filepath

        # Validate syntax before writing
        import ast
        try:
            ast.parse(tpl.code_template)
        except SyntaxError as exc:
            log.error("catalog.template_syntax_error", name=name, error=str(exc))
            return None

        filepath.write_text(tpl.code_template, encoding="utf-8")
        log.info("catalog.skill_installed", name=name, path=str(filepath))
        return filepath

    def list_installed(self) -> list[str]:
        """List skill files already installed in the skills directory."""
        if not self._skills_dir.exists():
            return []
        return [f.stem for f in sorted(self._skills_dir.glob("*.py")) if f.stem != "__init__"]

    def format_catalog(self) -> str:
        """Format the full catalog as a readable string."""
        lines: list[str] = ["📚 Catálogo de Skills disponibles:\n"]
        installed = set(self.list_installed())

        for category in self.get_categories():
            lines.append(f"\n🏷️ {category.upper()}")
            for tpl in self.get_templates(category):
                status = "✅ instalado" if tpl.name in installed else "📦 disponible"
                lines.append(f"  • {tpl.name} — {tpl.description} [{status}]")
                lines.append(f"    Triggers: {', '.join(tpl.triggers)}")

        lines.append(f"\nTotal: {len(self.get_templates())} plantillas en {len(self.get_categories())} categorías")
        lines.append("Para instalar: !catalogo instalar <nombre>")
        return "\n".join(lines)
