"""System resource monitoring."""

from __future__ import annotations

import asyncio
import os
import shutil
from typing import Any

import structlog

from src.skills.base_skill import BaseSkill, SkillResult
from src.utils.platform import IS_WINDOWS, IS_MACOS

log = structlog.get_logger("assistant.skills.system_monitor")

_MAX_OUTPUT = 4000


class SystemMonitorSkill(BaseSkill):


    @property
    def name(self) -> str:
        return "system_monitor"

    @property
    def description(self) -> str:
        return "Monitoreo de recursos del sistema: CPU, RAM, disco, red"

    @property
    def triggers(self) -> list[str]:
        return ["!sistema", "!system", "!monitor", "!recursos"]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        sub = args.strip().lower()

        if sub in ("procesos", "processes"):
            return await self._top_processes()
        elif sub in ("disco", "disk"):
            return await self._disk_usage()
        elif sub in ("red", "network"):
            return await self._network_info()
        else:
            return await self._overview()

    async def _overview(self) -> SkillResult:
        lines: list[str] = ["**Sistema**\n"]

        try:
            import psutil
            cpu = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory()
            disk = shutil.disk_usage("/")
            boot = psutil.boot_time()
            import time
            uptime_s = int(time.time() - boot)
            h, remainder = divmod(uptime_s, 3600)
            m, s = divmod(remainder, 60)

            lines.append(f"CPU: {cpu}% ({os.cpu_count()} cores)")
            lines.append(
                f"RAM: {mem.used / (1024**3):.1f} GB / "
                f"{mem.total / (1024**3):.1f} GB ({mem.percent}%)"
            )
            lines.append(
                f"Disco /: {disk.used / (1024**3):.1f} GB / "
                f"{disk.total / (1024**3):.1f} GB "
                f"({disk.used * 100 / disk.total:.0f}%)"
            )
            lines.append(f"Uptime: {h}h {m}m {s}s")
        except ImportError:
            log.info("system_monitor.psutil_not_available")
            lines.append(await self._fallback_overview())

        return SkillResult(success=True, message="\n".join(lines))

    async def _fallback_overview(self) -> str:
        parts: list[str] = []
        if not IS_WINDOWS:
            cmds = {
                "CPU": "top -bn1 | head -5",
                "Memoria": "free -h | head -3",
                "Disco": "df -h / | tail -1",
                "Uptime": "uptime -p",
            }
            for label, cmd in cmds.items():
                try:
                    proc = await asyncio.create_subprocess_shell(
                        cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    out, _ = await asyncio.wait_for(proc.communicate(), 10)
                    parts.append(f"{label}: {out.decode().strip()}")
                except Exception:
                    parts.append(f"{label}: no disponible")
        else:
            parts.append(f"CPU cores: {os.cpu_count()}")
            disk = shutil.disk_usage("C:\\")
            parts.append(
                f"Disco C: {disk.used / (1024**3):.1f} GB / "
                f"{disk.total / (1024**3):.1f} GB"
            )
        return "\n".join(parts)

    async def _top_processes(self) -> SkillResult:
        try:
            import psutil
            procs = []
            for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
                info = p.info
                procs.append(info)
            procs.sort(key=lambda x: x.get("cpu_percent") or 0, reverse=True)
            lines = ["**Top 10 procesos (CPU)**\n"]
            lines.append(f"{'PID':<8} {'CPU%':<7} {'MEM%':<7} {'Nombre'}")
            lines.append("-" * 40)
            for p in procs[:10]:
                lines.append(
                    f"{p.get('pid', '?'):<8} "
                    f"{p.get('cpu_percent', 0):<7.1f} "
                    f"{p.get('memory_percent', 0):<7.1f} "
                    f"{p.get('name', '?')}"
                )
            return SkillResult(success=True, message="\n".join(lines))
        except ImportError:
            return await self._shell_result(
                "ps aux --sort=-%cpu | head -11" if not IS_WINDOWS
                else "tasklist /FO TABLE | more"
            )

    async def _disk_usage(self) -> SkillResult:
        try:
            import psutil
            parts = psutil.disk_partitions()
            lines = ["**Uso de disco**\n"]
            for part in parts:
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    lines.append(
                        f"{part.mountpoint}: "
                        f"{usage.used / (1024**3):.1f} / "
                        f"{usage.total / (1024**3):.1f} GB "
                        f"({usage.percent}%) [{part.fstype}]"
                    )
                except PermissionError:
                    lines.append(f"{part.mountpoint}: sin acceso")
            return SkillResult(success=True, message="\n".join(lines))
        except ImportError:
            return await self._shell_result(
                "df -h" if not IS_WINDOWS else "wmic logicaldisk get size,freespace,caption"
            )

    async def _network_info(self) -> SkillResult:
        try:
            import psutil
            conns = psutil.net_connections(kind="inet")
            addrs = psutil.net_if_addrs()
            lines = ["**Red**\n"]
            lines.append(f"Conexiones activas: {len(conns)}")
            established = sum(1 for c in conns if c.status == "ESTABLISHED")
            listening = sum(1 for c in conns if c.status == "LISTEN")
            lines.append(f"  ESTABLISHED: {established}")
            lines.append(f"  LISTEN: {listening}")
            lines.append("\nInterfaces:")
            for iface, addr_list in addrs.items():
                for addr in addr_list:
                    if addr.family.name in ("AF_INET", "AF_INET6"):
                        lines.append(f"  {iface}: {addr.address}")
            return SkillResult(success=True, message="\n".join(lines))
        except ImportError:
            return await self._shell_result(
                "ss -tunap | head -20" if not IS_WINDOWS
                else "netstat -an | findstr ESTABLISHED | find /c /v \"\""
            )

    async def _shell_result(self, cmd: str) -> SkillResult:
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, err = await asyncio.wait_for(proc.communicate(), 15)
            text = out.decode("utf-8", errors="replace").strip()
            if len(text) > _MAX_OUTPUT:
                text = text[:_MAX_OUTPUT] + "\n... (truncado)"
            return SkillResult(success=proc.returncode == 0, message=f"```\n{text}\n```")
        except Exception as exc:
            return SkillResult(success=False, message=f"Error: {exc}")
