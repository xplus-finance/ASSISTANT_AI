"""HeartbeatSkill — User commands for managing the proactive heartbeat system."""

from __future__ import annotations

import json
from typing import Any

from src.skills.base_skill import BaseSkill, SkillResult


class HeartbeatSkill(BaseSkill):

    @property
    def name(self) -> str:
        return "heartbeat"

    @property
    def description(self) -> str:
        return "Gestionar el sistema de heartbeat proactivo: checks, focus, digest, alertas"

    @property
    def triggers(self) -> list[str]:
        return ["!heartbeat", "!hb", "!focus", "!alertas", "!digest", "!dnd"]

    @property
    def natural_patterns(self) -> dict[str, list[str]]:
        return {
            "status": [
                r"(?:estado|status)\s+(?:del\s+)?heartbeat",
                r"(?:cómo|como)\s+(?:está|esta)\s+(?:el\s+)?heartbeat",
                r"mis\s+alertas",
            ],
            "focus": [
                r"modo\s+focus\s+(?P<args>\d+\s*(?:min|hora|h|m)?)",
                r"no\s+molestar\s+(?P<args>\d+\s*(?:min|hora|h|m)?)",
                r"silencio\s+(?P<args>\d+\s*(?:min|hora|h|m)?)",
            ],
            "focus_off": [
                r"(?:quita|desactiva|apaga)\s+(?:el\s+)?(?:modo\s+)?focus",
                r"(?:quita|desactiva|apaga)\s+(?:el\s+)?(?:modo\s+)?(?:no\s+molestar|dnd)",
            ],
            "digest": [
                r"(?:envía|envia|manda|muestra)\s+(?:el\s+)?digest",
                r"(?:envía|envia|manda|muestra)\s+(?:el\s+)?resumen",
            ],
            "checks": [
                r"(?:qué|que)\s+checks?\s+(?:hay|tienes|están)",
                r"(?:lista|listar)\s+checks?",
                r"configura(?:r)?\s+heartbeat",
            ],
            "add_url": [
                r"(?:monitorea|vigila|monitorear|vigilar)\s+(?:la\s+)?(?:url|web|sitio|página)\s+(?P<args>.+)",
            ],
            "add_repo": [
                r"(?:monitorea|vigila|monitorear|vigilar)\s+(?:el\s+)?(?:repo|repositorio)\s+(?P<args>.+)",
            ],
            "force_check": [
                r"(?:ejecuta|corre|run)\s+(?:el\s+)?check\s+(?P<args>.+)",
                r"(?:revisa|revisar)\s+(?:el\s+)?(?:sistema|salud|servicios)",
            ],
        }

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        gateway = context.get("gateway")
        if not gateway or not gateway.heartbeat:
            return SkillResult(False, "El sistema HeartbeatPro no está activo.")

        heartbeat = gateway.heartbeat
        nm = heartbeat._notification_manager

        # Parse command
        text = args.strip().lower()
        intent = context.get("intent", "")

        if not text and not intent:
            text = "status"

        # Route to handler
        if text.startswith("status") or text.startswith("estado") or intent == "status":
            return self._handle_status(heartbeat, nm)

        if text.startswith("focus") or text.startswith("silencio") or intent == "focus":
            return self._handle_focus(heartbeat, args)

        if intent == "focus_off" or "quita" in text or "desactiva" in text:
            return self._handle_focus_off(heartbeat)

        if text.startswith("digest") or text.startswith("resumen") or intent == "digest":
            return await self._handle_digest(heartbeat)

        if text.startswith("checks") or text.startswith("lista") or intent == "checks":
            return self._handle_list_checks(heartbeat)

        if intent == "add_url" or text.startswith("url"):
            url = args.strip()
            if intent == "add_url":
                url = context.get("args", args).strip()
            return self._handle_add_url(url)

        if intent == "add_repo" or text.startswith("repo"):
            repo = args.strip()
            if intent == "add_repo":
                repo = context.get("args", args).strip()
            return self._handle_add_repo(repo)

        if intent == "force_check" or text.startswith("check") or text.startswith("revisa"):
            check_name = args.strip() if intent == "force_check" else None
            return await self._handle_force_check(heartbeat, check_name)

        # Default: show status
        return self._handle_status(heartbeat, nm)

    def _handle_status(self, heartbeat: Any, nm: Any) -> SkillResult:
        """Show heartbeat status."""
        stats = heartbeat.get_stats()
        checks = heartbeat.get_checks()

        lines = ["**HeartbeatPro — Estado**\n"]
        lines.append(f"Estado: {'🟢 Activo' if stats['running'] else '🔴 Detenido'}")
        lines.append(f"Checks: {stats['enabled_checks']}/{stats['registered_checks']} activos")
        lines.append(f"Ticks: {stats['ticks']} | Notificaciones: {stats['notifications_sent']}")
        lines.append(f"Razonamientos IA: {stats['ai_reasonings']}")
        lines.append(f"Alertas pendientes: {stats['pending_alerts']}")

        if nm:
            dnd = nm.get_dnd_status()
            if dnd["active"]:
                lines.append(f"\n🔕 **No Molestar ACTIVO**")
                if dnd.get("focus_mode"):
                    lines.append(f"  Focus restante: {dnd['focus_remaining_minutes']:.0f} min")
                if dnd.get("schedule"):
                    lines.append(f"  Horario: {dnd['schedule']}")
            else:
                lines.append(f"\n🔔 Notificaciones habilitadas")
                if dnd.get("schedule"):
                    lines.append(f"  DND programado: {dnd['schedule']}")

            digest_count = nm.get_digest_queue_count()
            if digest_count:
                lines.append(f"📋 Digest pendiente: {digest_count} items")

        lines.append("\n**Checks registrados:**")
        for c in checks:
            status = "✅" if c["enabled"] else "⏸️"
            lines.append(
                f"  {status} {c['name']} — cada {c['interval_minutes']}min "
                f"[{c['priority']}] (runs: {c['run_count']}, fails: {c['fail_count']})"
            )

        return SkillResult(True, "\n".join(lines))

    def _handle_focus(self, heartbeat: Any, args: str) -> SkillResult:
        """Activate focus/DND mode."""
        # Extract minutes from args
        import re
        match = re.search(r"(\d+)\s*(h(?:ora)?s?|m(?:in)?(?:utos?)?)?", args)
        if not match:
            return SkillResult(False, "Especifique duración. Ej: `!focus 30 min` o `!focus 2 horas`")

        value = int(match.group(1))
        unit = (match.group(2) or "m").lower()
        if unit.startswith("h"):
            minutes = value * 60
        else:
            minutes = value

        expires = heartbeat.set_focus_mode(minutes)
        return SkillResult(
            True,
            f"🔕 **Modo Focus activado** por {minutes} minutos.\n"
            f"Expira: {expires.strftime('%H:%M')}\n"
            f"Solo las alertas CRÍTICAS pasarán."
        )

    def _handle_focus_off(self, heartbeat: Any) -> SkillResult:
        """Deactivate focus mode."""
        heartbeat.clear_focus_mode()
        return SkillResult(True, "🔔 Modo Focus desactivado. Notificaciones normales restauradas.")

    async def _handle_digest(self, heartbeat: Any) -> SkillResult:
        """Force send digest now."""
        await heartbeat.send_digest_now()
        return SkillResult(True, "📋 Digest enviado.")

    def _handle_list_checks(self, heartbeat: Any) -> SkillResult:
        """List all registered checks with details."""
        checks = heartbeat.get_checks()
        if not checks:
            return SkillResult(True, "No hay checks registrados.")

        lines = ["**Checks del HeartbeatPro:**\n"]
        for c in checks:
            status = "✅" if c["enabled"] else "⏸️"
            lines.append(
                f"{status} **{c['name']}** [{c['category']}]\n"
                f"  Intervalo: {c['interval_minutes']}min | "
                f"Prioridad: {c['priority']} | "
                f"Ejecuciones: {c['run_count']} | Fallos: {c['fail_count']}"
            )

        return SkillResult(True, "\n".join(lines))

    def _handle_add_url(self, url: str) -> SkillResult:
        """Add a URL to the web monitor."""
        if not url or not url.startswith(("http://", "https://")):
            return SkillResult(False, "URL inválida. Debe empezar con http:// o https://")

        from src.core.heartbeat import CONFIG_PATH
        try:
            config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            urls = config.get("checks", {}).get("web_monitor", {}).get("urls", [])
            if url in urls:
                return SkillResult(False, f"La URL {url} ya está siendo monitoreada.")
            urls.append(url)
            config.setdefault("checks", {}).setdefault("web_monitor", {})["urls"] = urls
            CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
            return SkillResult(True, f"🌐 URL agregada al monitor: {url}")
        except Exception as e:
            return SkillResult(False, f"Error al guardar: {e}")

    def _handle_add_repo(self, repo_path: str) -> SkillResult:
        """Add a git repo to the monitor."""
        from pathlib import Path
        repo = Path(repo_path).expanduser()
        if not (repo / ".git").exists():
            return SkillResult(False, f"No es un repositorio Git válido: {repo}")

        from src.core.heartbeat import CONFIG_PATH
        try:
            config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            repos = config.get("checks", {}).get("git_monitor", {}).get("repos", [])
            repo_str = str(repo)
            if repo_str in repos:
                return SkillResult(False, f"El repo {repo_str} ya está siendo monitoreado.")
            repos.append(repo_str)
            config.setdefault("checks", {}).setdefault("git_monitor", {})["repos"] = repos
            CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
            return SkillResult(True, f"🔀 Repo agregado al monitor: {repo_str}")
        except Exception as e:
            return SkillResult(False, f"Error al guardar: {e}")

    async def _handle_force_check(self, heartbeat: Any, check_name: str | None) -> SkillResult:
        """Force run a check."""
        results = await heartbeat.force_check(check_name)
        if not results:
            target = check_name or "todos los checks"
            return SkillResult(True, f"✅ {target} — sin alertas.")

        lines = ["**Resultados del check forzado:**\n"]
        for r in results:
            msg = r.get("message", "?")
            prio = r.get("priority", "NORMAL")
            prio_name = prio.name if hasattr(prio, "name") else str(prio)
            lines.append(f"• [{prio_name}] {msg}")

        return SkillResult(True, "\n".join(lines))
