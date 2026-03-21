#!/usr/bin/env python3
"""Alarm manager — add, edit, delete, list alarms and auto-configure cron."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
ALARM_DIR = PROJECT_DIR / "src" / "apps" / "alarm"
ALARMS_FILE = ALARM_DIR / "alarms.json"
THEMES_FILE = ALARM_DIR / "themes.json"
TRIGGER_SCRIPT = PROJECT_DIR / "scripts" / "alarm_trigger.py"
CRON_TAG = "FIRULAIS_ALARM"


def load_alarms() -> dict:
    if ALARMS_FILE.exists():
        with open(ALARMS_FILE) as f:
            return json.load(f)
    return {"alarms": [], "next_id": 1, "default_snooze_minutes": 5, "default_theme": "default", "telegram_backup": True}


def save_alarms(data: dict):
    with open(ALARMS_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_themes() -> dict:
    if THEMES_FILE.exists():
        with open(THEMES_FILE) as f:
            return json.load(f).get("themes", {})
    return {}


def add_alarm(
    hour: int,
    minute: int,
    message: str = "¡Alarma!",
    theme: str = "default",
    repeat: str | list | None = None,
    date: str | None = None,
    snooze_minutes: int | None = None,
    enabled: bool = True,
) -> dict:
    """Add a new alarm."""
    data = load_alarms()
    alarm_id = data.get("next_id", 1)

    if snooze_minutes is None:
        snooze_minutes = data.get("default_snooze_minutes", 5)

    alarm = {
        "id": alarm_id,
        "hour": hour,
        "minute": minute,
        "message": message,
        "theme": theme,
        "repeat": repeat,
        "date": date,
        "snooze_minutes": snooze_minutes,
        "enabled": enabled,
        "created": datetime.now().isoformat(),
        "last_fired": None,
    }

    data["alarms"].append(alarm)
    data["next_id"] = alarm_id + 1
    save_alarms(data)
    sync_cron(data)
    return alarm


def edit_alarm(alarm_id: int, **kwargs) -> dict | None:
    """Edit an existing alarm."""
    data = load_alarms()
    for alarm in data["alarms"]:
        if alarm["id"] == alarm_id:
            for key, val in kwargs.items():
                if key in alarm and val is not None:
                    alarm[key] = val
            alarm["modified"] = datetime.now().isoformat()
            save_alarms(data)
            sync_cron(data)
            return alarm
    return None


def delete_alarm(alarm_id: int) -> bool:
    """Delete an alarm by ID."""
    data = load_alarms()
    original_len = len(data["alarms"])
    data["alarms"] = [a for a in data["alarms"] if a["id"] != alarm_id]
    if len(data["alarms"]) < original_len:
        save_alarms(data)
        sync_cron(data)
        return True
    return False


def toggle_alarm(alarm_id: int) -> dict | None:
    """Toggle alarm enabled/disabled."""
    data = load_alarms()
    for alarm in data["alarms"]:
        if alarm["id"] == alarm_id:
            alarm["enabled"] = not alarm.get("enabled", True)
            save_alarms(data)
            sync_cron(data)
            return alarm
    return None


def list_alarms() -> list[dict]:
    """List all alarms."""
    data = load_alarms()
    return data.get("alarms", [])


def get_alarm(alarm_id: int) -> dict | None:
    """Get a specific alarm."""
    data = load_alarms()
    for alarm in data["alarms"]:
        if alarm["id"] == alarm_id:
            return alarm
    return None


def format_alarm(alarm: dict) -> str:
    """Format alarm for display."""
    themes = load_themes()
    theme = themes.get(alarm.get("theme", "default"), {})
    icon = theme.get("icon", "⏰")
    status = "✅" if alarm.get("enabled", True) else "❌"

    time_str = f"{alarm['hour']:02d}:{alarm['minute']:02d}"
    repeat = alarm.get("repeat")

    if repeat == "daily":
        repeat_str = "Todos los días"
    elif repeat == "weekdays":
        repeat_str = "Lun-Vie"
    elif repeat == "weekends":
        repeat_str = "Sáb-Dom"
    elif isinstance(repeat, list):
        days_map = {0: "L", 1: "M", 2: "X", 3: "J", 4: "V", 5: "S", 6: "D"}
        repeat_str = "".join(days_map.get(d, "?") for d in repeat)
    elif alarm.get("date"):
        repeat_str = f"Una vez ({alarm['date']})"
    else:
        repeat_str = "Una vez"

    return f"{status} #{alarm['id']} {icon} {time_str} | {repeat_str} | {alarm.get('theme', 'default')} | {alarm.get('message', '')}"


def sync_cron(data: dict | None = None):
    """Synchronize cron to check alarms every minute."""
    if data is None:
        data = load_alarms()

    active_alarms = [a for a in data.get("alarms", []) if a.get("enabled", True)]

    try:
        # Get current crontab
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        current = result.stdout if result.returncode == 0 else ""

        # Remove old alarm entries
        lines = [l for l in current.splitlines() if CRON_TAG not in l]

        if active_alarms:
            # Add cron that runs every minute to check alarms
            python = sys.executable
            trigger = str(TRIGGER_SCRIPT)
            env_file = str(PROJECT_DIR / ".env")

            cron_line = f"* * * * * . {env_file} 2>/dev/null; DISPLAY=:0 {python} {trigger} >> /tmp/alarm_trigger.log 2>&1 # {CRON_TAG}"
            lines.append(cron_line)

            # Also add snooze checker (every minute same script handles it)

        new_cron = "\n".join(lines)
        if not new_cron.endswith("\n"):
            new_cron += "\n"

        subprocess.run(["crontab", "-"], input=new_cron, text=True, check=True)
        return True
    except Exception as e:
        print(f"Cron sync error: {e}", file=sys.stderr)
        return False


def format_list_all() -> str:
    """Format all alarms for display."""
    alarms = list_alarms()
    if not alarms:
        return "No hay alarmas configuradas."

    lines = ["📋 Alarmas configuradas:\n"]
    for alarm in sorted(alarms, key=lambda a: (a["hour"], a["minute"])):
        lines.append(format_alarm(alarm))
    return "\n".join(lines)


# CLI interface
def main():
    import argparse

    parser = argparse.ArgumentParser(description="Firulais Alarm Manager")
    sub = parser.add_subparsers(dest="command")

    # Add
    add_p = sub.add_parser("add", help="Add new alarm")
    add_p.add_argument("time", help="Time HH:MM")
    add_p.add_argument("--message", "-m", default="¡Alarma!")
    add_p.add_argument("--theme", "-t", default="default")
    add_p.add_argument("--repeat", "-r", default=None, help="daily|weekdays|weekends|0,1,2...")
    add_p.add_argument("--date", "-d", default=None, help="YYYY-MM-DD for one-time")
    add_p.add_argument("--snooze", "-s", type=int, default=None)

    # Edit
    edit_p = sub.add_parser("edit", help="Edit alarm")
    edit_p.add_argument("id", type=int)
    edit_p.add_argument("--time", default=None)
    edit_p.add_argument("--message", "-m", default=None)
    edit_p.add_argument("--theme", "-t", default=None)
    edit_p.add_argument("--repeat", "-r", default=None)
    edit_p.add_argument("--snooze", "-s", type=int, default=None)

    # Delete
    del_p = sub.add_parser("delete", help="Delete alarm")
    del_p.add_argument("id", type=int)

    # Toggle
    tog_p = sub.add_parser("toggle", help="Toggle alarm")
    tog_p.add_argument("id", type=int)

    # List
    sub.add_parser("list", help="List all alarms")

    # Themes
    sub.add_parser("themes", help="List available themes")

    # Test
    test_p = sub.add_parser("test", help="Test alarm (fires immediately)")
    test_p.add_argument("--theme", "-t", default="default")
    test_p.add_argument("--message", "-m", default="Alarma de prueba")

    args = parser.parse_args()

    if args.command == "add":
        h, m = map(int, args.time.split(":"))
        repeat = args.repeat
        if repeat and "," in repeat:
            repeat = [int(x) for x in repeat.split(",")]
        alarm = add_alarm(h, m, args.message, args.theme, repeat, args.date, args.snooze)
        print(f"✅ Alarma #{alarm['id']} creada: {format_alarm(alarm)}")

    elif args.command == "edit":
        kwargs = {}
        if args.time:
            h, m = map(int, args.time.split(":"))
            kwargs["hour"] = h
            kwargs["minute"] = m
        if args.message:
            kwargs["message"] = args.message
        if args.theme:
            kwargs["theme"] = args.theme
        if args.repeat:
            r = args.repeat
            if "," in r:
                r = [int(x) for x in r.split(",")]
            kwargs["repeat"] = r
        if args.snooze:
            kwargs["snooze_minutes"] = args.snooze
        result = edit_alarm(args.id, **kwargs)
        if result:
            print(f"✅ Alarma #{args.id} editada: {format_alarm(result)}")
        else:
            print(f"❌ Alarma #{args.id} no encontrada")

    elif args.command == "delete":
        if delete_alarm(args.id):
            print(f"✅ Alarma #{args.id} eliminada")
        else:
            print(f"❌ Alarma #{args.id} no encontrada")

    elif args.command == "toggle":
        result = toggle_alarm(args.id)
        if result:
            state = "activada" if result["enabled"] else "desactivada"
            print(f"✅ Alarma #{args.id} {state}")
        else:
            print(f"❌ Alarma #{args.id} no encontrada")

    elif args.command == "list":
        print(format_list_all())

    elif args.command == "themes":
        themes = load_themes()
        print("🎨 Temas disponibles:\n")
        for name, info in themes.items():
            icon = info.get("icon", "⏰")
            desc = info.get("description", "")
            print(f"  {icon} {name}: {desc}")

    elif args.command == "test":
        from alarm_trigger import launch_alarm_app, send_telegram, format_telegram_message
        alarm = {"id": 0, "message": args.message, "theme": args.theme, "snooze_minutes": 5}
        launch_alarm_app(alarm)
        send_telegram(format_telegram_message(alarm))
        print(f"🔔 Alarma de prueba lanzada con tema '{args.theme}'")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
