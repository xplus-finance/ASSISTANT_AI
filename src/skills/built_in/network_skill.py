"""Network diagnostics and tools."""

from __future__ import annotations

import asyncio
import socket
from typing import Any

import structlog

from src.skills.base_skill import BaseSkill, SkillResult
from src.utils.platform import IS_WINDOWS

log = structlog.get_logger("assistant.skills.network")

_MAX_OUTPUT = 4000


class NetworkSkill(BaseSkill):


    @property
    def name(self) -> str:
        return "network"

    @property
    def description(self) -> str:
        return "Herramientas de red: ping, curl, puertos, IP, DNS"

    @property
    def triggers(self) -> list[str]:
        return ["!red", "!network", "!ping", "!curl"]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        parts = args.strip().split(maxsplit=1)
        if not parts:
            return SkillResult(
                success=False,
                message=(
                    "Uso:\n"
                    "  !red ping <host>     — ping con 3 paquetes\n"
                    "  !red curl <url>      — HTTP GET, status + headers\n"
                    "  !red puertos         — puertos escuchando\n"
                    "  !red ip              — IP publica + local\n"
                    "  !red dns <dominio>   — DNS lookup"
                ),
            )

        sub = parts[0].lower()
        target = parts[1].strip() if len(parts) > 1 else ""

        if sub == "ping":
            return await self._ping(target)
        elif sub == "curl":
            return await self._curl(target)
        elif sub in ("puertos", "ports"):
            return await self._listening_ports()
        elif sub == "ip":
            return await self._ip_addresses()
        elif sub == "dns":
            return await self._dns_lookup(target)
        else:
            # If trigger was !ping or !curl, treat sub as the target
            trigger_used = ""
            text_lower = context.get("raw_text", "").lower().strip()
            if text_lower.startswith("!ping"):
                return await self._ping(args.strip())
            elif text_lower.startswith("!curl"):
                return await self._curl(args.strip())
            return SkillResult(
                success=False,
                message=f"Subcomando desconocido: {sub}. Usa: ping, curl, puertos, ip, dns",
            )

    async def _ping(self, host: str) -> SkillResult:
        if not host:
            return SkillResult(success=False, message="Especifica un host: !red ping google.com")

        count_flag = "-n" if IS_WINDOWS else "-c"
        cmd = f"ping {count_flag} 3 {host}"
        log.info("network.ping", host=host)
        return await self._shell(cmd, timeout=15)

    async def _curl(self, url: str) -> SkillResult:
        if not url:
            return SkillResult(success=False, message="Especifica una URL: !red curl https://example.com")

        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        log.info("network.curl", url=url)

        try:
            import httpx
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.get(url)
            hdrs = "\n".join(f"  {k}: {v}" for k, v in list(resp.headers.items())[:12])
            body = resp.text[:500] if resp.text else "(sin cuerpo)"
            msg = (f"**HTTP GET {url}**\nStatus: {resp.status_code} {resp.reason_phrase}"
                   f"\nHeaders:\n{hdrs}\nBody:\n```\n{body}\n```")
            return SkillResult(success=True, message=msg)
        except ImportError:
            return await self._shell(f'curl -sS -D - -o /dev/null --max-time 10 "{url}"', 15)
        except Exception as exc:
            return SkillResult(success=False, message=f"Error HTTP: {exc}")

    async def _listening_ports(self) -> SkillResult:
        log.info("network.ports")
        if IS_WINDOWS:
            cmd = "netstat -an | findstr LISTEN"
        else:
            cmd = "ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null"
        return await self._shell(cmd, timeout=10)

    async def _ip_addresses(self) -> SkillResult:
        log.info("network.ip")
        lines: list[str] = ["**Direcciones IP**\n"]

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            lines.append(f"Local: {local_ip}")
        except Exception:
            lines.append("Local: no disponible")

        try:
            import httpx
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get("https://api.ipify.org?format=text")
                lines.append(f"Publica: {resp.text.strip()}")
        except Exception:
            r = await self._shell("curl -s --max-time 5 https://api.ipify.org", 8)
            pub = r.message.strip("`\n ") if r.success else ""
            lines.append(f"Publica: {pub}" if pub else "Publica: no disponible")

        lines.append(f"Hostname: {socket.gethostname()}")
        return SkillResult(success=True, message="\n".join(lines))

    async def _dns_lookup(self, domain: str) -> SkillResult:
        if not domain:
            return SkillResult(success=False, message="Especifica un dominio: !red dns example.com")

        log.info("network.dns", domain=domain)
        lines: list[str] = [f"**DNS: {domain}**\n"]

        try:
            results = socket.getaddrinfo(domain, None)
            seen: set[str] = set()
            for family, _, _, _, sockaddr in results:
                ip = sockaddr[0]
                if ip not in seen:
                    seen.add(ip)
                    fam = "IPv4" if family == socket.AF_INET else "IPv6"
                    lines.append(f"  {fam}: {ip}")
            if not seen:
                lines.append("  Sin resultados")
        except socket.gaierror as exc:
            lines.append(f"  Error: {exc}")
        except Exception as exc:
            lines.append(f"  Error: {exc}")

        return SkillResult(success=True, message="\n".join(lines))

    async def _shell(self, cmd: str, timeout: int = 15) -> SkillResult:
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, err = await asyncio.wait_for(proc.communicate(), timeout)
            text = out.decode("utf-8", errors="replace").strip()
            if err_text := err.decode("utf-8", errors="replace").strip():
                text += f"\n[stderr] {err_text}"
            if len(text) > _MAX_OUTPUT:
                text = text[:_MAX_OUTPUT] + "\n... (truncado)"
            return SkillResult(
                success=proc.returncode == 0,
                message=f"```\n{text}\n```" if text else "(sin salida)",
            )
        except asyncio.TimeoutError:
            return SkillResult(success=False, message=f"Comando excedio {timeout}s.")
        except Exception as exc:
            return SkillResult(success=False, message=f"Error: {exc}")
