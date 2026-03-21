"""Alarm skill — create, manage, and control alarms via natural language."""

from __future__ import annotations

import json
import os
import re
import subprocess
import signal
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.skills.base_skill import BaseSkill, SkillResult

PROJECT_DIR = Path(__file__).parent.parent.parent.parent
ALARM_DIR = PROJECT_DIR / "src" / "apps" / "alarm"
SCRIPTS_DIR = PROJECT_DIR / "scripts"

# Add scripts to path for imports
sys.path.insert(0, str(SCRIPTS_DIR))


def _get_manager():
    """Lazy import of alarm_manager to avoid circular issues."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("alarm_manager", SCRIPTS_DIR / "alarm_manager.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _get_trigger():
    """Lazy import of alarm_trigger."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("alarm_trigger", SCRIPTS_DIR / "alarm_trigger.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class AlarmSkill(BaseSkill):

    @property
    def name(self) -> str:
        return "alarm"

    @property
    def description(self) -> str:
        return "Crear, editar, eliminar y gestionar alarmas/despertadores con temas personalizados"

    @property
    def triggers(self) -> list[str]:
        return ["!alarma", "!alarm", "!despertador"]

    @property
    def natural_patterns(self) -> dict[str, list[str]]:
        return {
            "add": [
                r"(?:pon(?:me|er)?|crea(?:r)?|configura(?:r)?|programa(?:r)?|agrega(?:r)?|añade|set) (?:una? )?(?:alarma|despertador|recordatorio)(?:.*?)(?:a las?|para las?|a|para) (?P<args>\d{1,2}[:\s]?\d{2}.*)",
                r"despi[eé]rtame (?:a las?|a|para las?) (?P<args>\d{1,2}[:\s]?\d{2}.*)",
                r"(?:alarma|despertador) (?:a las?|para las?) (?P<args>\d{1,2}[:\s]?\d{2}.*)",
                r"(?:recuérdame|avísame) (?:a las?|para las?) (?P<args>\d{1,2}[:\s]?\d{2}.*)",
            ],
            "list": [
                r"(?:lista|muestra|ver|enseña|cuáles|que|qué) (?:las? )?(?:alarma|despertador|alarm)s?",
                r"(?:alarma|despertador)s? (?:que tengo|activ[ao]s|configurad[ao]s)",
                r"mis alarmas",
            ],
            "delete": [
                r"(?:borra|elimina|quita|cancela|remueve) (?:la )?alarma (?:#?)?(?P<args>\d+)",
                r"(?:borra|elimina|quita|cancela) (?:el )?despertador (?:#?)?(?P<args>\d+)",
            ],
            "toggle": [
                r"(?:activa|desactiva|enciende|apaga|pausa) (?:la )?alarma (?:#?)?(?P<args>\d+)",
            ],
            "stop": [
                r"(?:apaga|para|detén|calla|silencia) (?:la )?(?:alarma|despertador|el sonido|el ruido)",
                r"(?:alarma|despertador) (?:apagar|parar|detener|callar)",
                r"ya (?:me desperté|estoy despierto|la oí|escuché)",
            ],
            "themes": [
                r"(?:temas|estilos|tipos) (?:de )?(?:alarma|despertador)s?",
                r"(?:qué|cuáles|que) temas (?:hay|tiene|existen)",
            ],
            "test": [
                r"(?:prueba|test|probar) (?:la )?(?:alarma|despertador)",
            ],
        }

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        text = args.lower().strip()
        intent = context.get("intent", "")

        # Determine action
        if intent:
            action = intent
        elif any(t in text for t in ["lista", "ver", "muestra", "cuáles", "mis alarmas"]):
            action = "list"
        elif any(t in text for t in ["borra", "elimina", "quita", "cancela"]):
            action = "delete"
        elif any(t in text for t in ["apaga", "para", "detén", "calla", "silencia", "desperté"]):
            action = "stop"
        elif any(t in text for t in ["temas", "estilos", "tipos"]):
            action = "themes"
        elif any(t in text for t in ["prueba", "test"]):
            action = "test"
        elif any(t in text for t in ["activa", "desactiva", "pausa"]):
            action = "toggle"
        else:
            action = "add"

        try:
            if action == "add":
                return await self._add_alarm(args)
            elif action == "list":
                return self._list_alarms()
            elif action == "delete":
                return self._delete_alarm(args)
            elif action == "toggle":
                return self._toggle_alarm(args)
            elif action == "stop":
                return self._stop_alarm()
            elif action == "themes":
                return self._list_themes()
            elif action == "test":
                return await self._test_alarm(args)
            else:
                return self._list_alarms()
        except Exception as e:
            return SkillResult(success=False, message=f"Error en alarma: {e}")

    async def _add_alarm(self, args: str) -> SkillResult:
        """Parse and add alarm from natural language."""
        mgr = _get_manager()

        # Extract time
        time_match = re.search(r'(\d{1,2})[:\s](\d{2})', args)
        if not time_match:
            return SkillResult(success=False, message="No pude detectar la hora. Usa formato como '7:00' o '7 30'.")

        hour = int(time_match.group(1))
        minute = int(time_match.group(2))

        # Detect AM/PM
        text_lower = args.lower()
        if "pm" in text_lower and hour < 12:
            hour += 12
        elif "am" in text_lower and hour == 12:
            hour = 0

        if hour > 23 or minute > 59:
            return SkillResult(success=False, message=f"Hora inválida: {hour}:{minute:02d}")

        # Extract theme
        theme = "default"
        theme_keywords = {
            "trabajo": "trabajo",
            "laboral": "trabajo",
            "oficina": "trabajo",
            "ejercicio": "ejercicio",
            "gym": "ejercicio",
            "gimnasio": "ejercicio",
            "deporte": "ejercicio",
            "medicina": "medicina",
            "medicamento": "medicina",
            "pastilla": "medicina",
            "píldora": "medicina",
            "relajante": "relajante",
            "suave": "relajante",
            "tranquilo": "relajante",
            "urgente": "urgente",
            "importante": "urgente",
            "emergencia": "urgente",
            "reunión": "reunion",
            "reunion": "reunion",
            "meeting": "reunion",
            "llamada": "reunion",
            "descanso": "descanso",
            "break": "descanso",
            "café": "descanso",
            "pausa": "descanso",
        }
        for keyword, theme_name in theme_keywords.items():
            if keyword in text_lower:
                theme = theme_name
                break

        # Also check explicit "tema X" or "con tema X"
        theme_explicit = re.search(r'(?:tema|theme|con tema) (\w+)', text_lower)
        if theme_explicit:
            theme = theme_explicit.group(1)

        # Extract repeat pattern
        repeat = None
        if any(w in text_lower for w in ["todos los días", "cada día", "diario", "diaria", "daily"]):
            repeat = "daily"
        elif any(w in text_lower for w in ["lunes a viernes", "entre semana", "weekdays", "días laborales"]):
            repeat = "weekdays"
        elif any(w in text_lower for w in ["fines de semana", "fin de semana", "weekends", "sábado y domingo"]):
            repeat = "weekends"
        else:
            # Check specific days
            day_map = {
                "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
                "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6,
            }
            found_days = []
            for day_name, day_num in day_map.items():
                if day_name in text_lower:
                    found_days.append(day_num)
            if found_days:
                repeat = sorted(set(found_days))

        # Extract message (after the time, cleaned up)
        message = "¡Alarma!"
        # Try to get descriptive part
        msg_patterns = [
            r'(?:para|con mensaje|mensaje|motivo|razón|porque)\s+["\']?(.+?)["\']?\s*$',
            r'(?:de|del?)\s+(trabajo|ejercicio|medicina|reunión|descanso)',
        ]
        for pat in msg_patterns:
            m = re.search(pat, text_lower)
            if m:
                message = m.group(1).strip().capitalize()
                break
        else:
            # Generate message from theme
            theme_messages = {
                "trabajo": "¡Hora de trabajar!",
                "ejercicio": "¡Hora del ejercicio!",
                "medicina": "¡Hora de la medicina!",
                "relajante": "¡Hora de despertar!",
                "urgente": "¡URGENTE!",
                "reunion": "¡Tienes una reunión!",
                "descanso": "¡Hora del break!",
                "default": "¡Alarma!",
            }
            message = theme_messages.get(theme, "¡Alarma!")

        # Extract snooze
        snooze = None
        snooze_match = re.search(r'snooze (\d+)', text_lower)
        if snooze_match:
            snooze = int(snooze_match.group(1))

        # Create the alarm
        alarm = mgr.add_alarm(
            hour=hour,
            minute=minute,
            message=message,
            theme=theme,
            repeat=repeat,
            snooze_minutes=snooze,
        )

        # Format response
        themes = mgr.load_themes()
        t = themes.get(theme, {})
        icon = t.get("icon", "⏰")

        repeat_str = "una vez"
        if repeat == "daily":
            repeat_str = "todos los días"
        elif repeat == "weekdays":
            repeat_str = "lunes a viernes"
        elif repeat == "weekends":
            repeat_str = "fines de semana"
        elif isinstance(repeat, list):
            days_map = {0: "Lun", 1: "Mar", 2: "Mié", 3: "Jue", 4: "Vie", 5: "Sáb", 6: "Dom"}
            repeat_str = ", ".join(days_map.get(d, "?") for d in repeat)

        response = (
            f"{icon} Alarma #{alarm['id']} creada\n\n"
            f"🕐 {hour:02d}:{minute:02d}\n"
            f"📝 {message}\n"
            f"🎨 Tema: {theme}\n"
            f"🔁 Repetir: {repeat_str}\n"
            f"💤 Snooze: {alarm.get('snooze_minutes', 5)} min\n"
            f"📱 Notificación Telegram: Sí\n\n"
            f"El cron está sincronizado. La alarma sonará en tu computadora y recibirás aviso por Telegram."
        )

        return SkillResult(success=True, message=response)

    def _list_alarms(self) -> SkillResult:
        mgr = _get_manager()
        result = mgr.format_list_all()
        return SkillResult(success=True, message=result)

    def _delete_alarm(self, args: str) -> SkillResult:
        mgr = _get_manager()
        id_match = re.search(r'(\d+)', args)
        if not id_match:
            return SkillResult(success=False, message="Necesito el número de alarma. Ejemplo: 'borra alarma 1'")

        alarm_id = int(id_match.group(1))
        if mgr.delete_alarm(alarm_id):
            return SkillResult(success=True, message=f"✅ Alarma #{alarm_id} eliminada y cron actualizado.")
        return SkillResult(success=False, message=f"❌ No encontré alarma #{alarm_id}")

    def _toggle_alarm(self, args: str) -> SkillResult:
        mgr = _get_manager()
        id_match = re.search(r'(\d+)', args)
        if not id_match:
            return SkillResult(success=False, message="Necesito el número de alarma.")

        alarm_id = int(id_match.group(1))
        result = mgr.toggle_alarm(alarm_id)
        if result:
            state = "activada ✅" if result["enabled"] else "desactivada ❌"
            return SkillResult(success=True, message=f"Alarma #{alarm_id} {state}")
        return SkillResult(success=False, message=f"❌ No encontré alarma #{alarm_id}")

    def _stop_alarm(self) -> SkillResult:
        """Kill any running alarm app."""
        try:
            # Find and kill alarm_app.py processes
            result = subprocess.run(
                ["pgrep", "-f", "alarm_app.py"],
                capture_output=True, text=True,
            )
            pids = result.stdout.strip().split("\n")
            killed = 0
            for pid in pids:
                if pid.strip():
                    try:
                        os.kill(int(pid.strip()), signal.SIGTERM)
                        killed += 1
                    except (ProcessLookupError, ValueError):
                        pass

            # Remove snooze file
            snooze_file = ALARM_DIR / ".snooze"
            if snooze_file.exists():
                snooze_file.unlink()

            if killed > 0:
                return SkillResult(success=True, message=f"✅ Alarma apagada ({killed} proceso(s) detenido(s)).")
            return SkillResult(success=True, message="No hay alarma sonando en este momento.")
        except Exception as e:
            return SkillResult(success=False, message=f"Error al detener alarma: {e}")

    def _list_themes(self) -> SkillResult:
        mgr = _get_manager()
        themes = mgr.load_themes()
        lines = ["🎨 Temas de alarma disponibles:\n"]
        for name, info in themes.items():
            icon = info.get("icon", "⏰")
            desc = info.get("description", "")
            sound = info.get("sound", "default.wav")
            image = info.get("image", "ninguna")
            has_sound = "✅" if (ALARM_DIR / "sounds" / sound).exists() else "📥 pendiente"
            has_image = "✅" if image and (ALARM_DIR / "images" / image).exists() else "📥 pendiente" if image else "—"
            lines.append(f"  {icon} {name}: {desc}")
            lines.append(f"     Sonido: {sound} ({has_sound}) | Imagen: {image or '—'} ({has_image})")
        lines.append("\nPara agregar sonidos: copiarlos a src/apps/alarm/sounds/")
        lines.append("Para agregar imágenes: copiarlas a src/apps/alarm/images/")
        return SkillResult(success=True, message="\n".join(lines))

    async def _test_alarm(self, args: str) -> SkillResult:
        """Fire a test alarm."""
        # Extract theme
        theme = "default"
        theme_match = re.search(r'(?:tema|theme|con) (\w+)', args.lower())
        if theme_match:
            theme = theme_match.group(1)

        trigger = _get_trigger()
        alarm = {
            "id": 0,
            "message": "🔔 Alarma de prueba — Firulais",
            "theme": theme,
            "snooze_minutes": 1,
        }
        trigger.launch_alarm_app(alarm)
        trigger.send_telegram(trigger.format_telegram_message(alarm))

        return SkillResult(success=True, message=f"🔔 Alarma de prueba lanzada con tema '{theme}'. Debería sonar ahora y llegar al Telegram.")
