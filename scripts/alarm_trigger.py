#!/usr/bin/env python3
"""Alarm trigger — called by cron, launches visual alarm + sends Telegram notification."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
ALARM_DIR = PROJECT_DIR / "src" / "apps" / "alarm"
ALARMS_FILE = ALARM_DIR / "alarms.json"
ALARM_APP = ALARM_DIR / "alarm_app.py"
THEMES_FILE = ALARM_DIR / "themes.json"
SNOOZE_FILE = ALARM_DIR / ".snooze"
ENV_FILE = PROJECT_DIR / ".env"

# Load environment
def load_env():
    if ENV_FILE.exists():
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())

load_env()

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("AUTHORIZED_CHAT_ID", "")


def send_telegram(message: str):
    """Send alarm notification via Telegram."""
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram not configured, skipping notification", file=sys.stderr)
        return False
    try:
        import urllib.request
        import urllib.parse
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": int(CHAT_ID),
            "text": message,
            "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"Telegram error: {e}", file=sys.stderr)
        return False


def load_alarms() -> dict:
    if ALARMS_FILE.exists():
        with open(ALARMS_FILE) as f:
            return json.load(f)
    return {"alarms": [], "next_id": 1}


def save_alarms(data: dict):
    with open(ALARMS_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_theme_info(theme_name: str) -> dict:
    if THEMES_FILE.exists():
        with open(THEMES_FILE) as f:
            themes = json.load(f).get("themes", {})
            return themes.get(theme_name, themes.get("default", {}))
    return {}


def launch_alarm_app(alarm: dict):
    """Launch the PyQt6 alarm window."""
    display = os.environ.get("DISPLAY", ":0")
    env = os.environ.copy()
    env["DISPLAY"] = display

    # Get XAUTHORITY
    xauth = os.environ.get("XAUTHORITY", "")
    if not xauth:
        home = os.path.expanduser("~")
        for candidate in [
            f"{home}/.Xauthority",
            f"/run/user/{os.getuid()}/.Xauthority",
        ]:
            if os.path.exists(candidate):
                xauth = candidate
                break
    if xauth:
        env["XAUTHORITY"] = xauth

    # PulseAudio
    pulse_server = os.environ.get("PULSE_SERVER", "")
    if not pulse_server:
        runtime_dir = f"/run/user/{os.getuid()}"
        pulse_sock = f"{runtime_dir}/pulse/native"
        if os.path.exists(pulse_sock):
            env["PULSE_SERVER"] = f"unix:{pulse_sock}"

    cmd = [
        sys.executable, str(ALARM_APP),
        "--message", alarm.get("message", "¡Alarma!"),
        "--theme", alarm.get("theme", "default"),
        "--snooze", str(alarm.get("snooze_minutes", 5)),
    ]
    if alarm.get("id"):
        cmd.extend(["--alarm-id", str(alarm["id"])])

    try:
        subprocess.Popen(cmd, env=env, start_new_session=True)
        return True
    except Exception as e:
        print(f"Error launching alarm app: {e}", file=sys.stderr)
        return False


def format_telegram_message(alarm: dict) -> str:
    """Format a nice Telegram notification for the alarm."""
    theme = get_theme_info(alarm.get("theme", "default"))
    icon = theme.get("icon", "⏰")
    theme_name = theme.get("name", alarm.get("theme", "default").title())
    now = datetime.now()

    msg = f"{icon} <b>ALARMA — {theme_name}</b>\n\n"
    msg += f"🕐 {now.strftime('%H:%M')}\n"
    msg += f"📝 {alarm.get('message', 'Alarma')}\n"

    if alarm.get("repeat"):
        repeat = alarm["repeat"]
        if repeat == "daily":
            msg += "🔁 Se repite: Todos los días\n"
        elif repeat == "weekdays":
            msg += "🔁 Se repite: Lunes a viernes\n"
        elif repeat == "weekends":
            msg += "🔁 Se repite: Fines de semana\n"
        elif isinstance(repeat, list):
            days_map = {0: "Lun", 1: "Mar", 2: "Mié", 3: "Jue", 4: "Vie", 5: "Sáb", 6: "Dom"}
            days_str = ", ".join(days_map.get(d, str(d)) for d in repeat)
            msg += f"🔁 Se repite: {days_str}\n"

    msg += "\n💡 <i>La alarma visual está sonando en tu computadora.</i>"
    msg += "\n<i>Apágala desde la pantalla o con el comando !alarma apagar</i>"
    return msg


def check_snooze():
    """Check if there's a pending snooze to re-trigger."""
    if not SNOOZE_FILE.exists():
        return

    try:
        with open(SNOOZE_FILE) as f:
            snooze = json.load(f)

        snoozed_at = datetime.fromisoformat(snooze["snoozed_at"])
        snooze_min = snooze.get("snooze_minutes", 5)
        trigger_at = snoozed_at + timedelta(minutes=snooze_min)

        now = datetime.now()
        if now >= trigger_at:
            # Time to re-trigger
            SNOOZE_FILE.unlink(missing_ok=True)
            alarm = {
                "id": snooze.get("alarm_id"),
                "message": snooze.get("message", "¡Alarma! (snooze)"),
                "theme": snooze.get("theme", "default"),
                "snooze_minutes": snooze_min,
            }
            launch_alarm_app(alarm)
            send_telegram(f"💤 Snooze terminó — {alarm['message']}")
    except Exception as e:
        print(f"Snooze check error: {e}", file=sys.stderr)
        SNOOZE_FILE.unlink(missing_ok=True)


def should_fire(alarm: dict) -> bool:
    """Check if an alarm should fire right now."""
    if not alarm.get("enabled", True):
        return False

    now = datetime.now()
    hour, minute = alarm.get("hour", -1), alarm.get("minute", -1)

    if hour != now.hour or minute != now.minute:
        return False

    repeat = alarm.get("repeat")
    weekday = now.weekday()  # 0=Monday, 6=Sunday

    if repeat == "daily":
        return True
    elif repeat == "weekdays":
        return weekday < 5
    elif repeat == "weekends":
        return weekday >= 5
    elif isinstance(repeat, list):
        return weekday in repeat
    elif repeat is None or repeat == "once":
        # One-time alarm — check date
        alarm_date = alarm.get("date")
        if alarm_date:
            return alarm_date == now.strftime("%Y-%m-%d")
        return True  # No date specified, fire once then disable

    return False


def main():
    """Main trigger — check all alarms and fire matching ones."""
    # Check snooze first
    check_snooze()

    # Load alarms
    data = load_alarms()
    alarms = data.get("alarms", [])
    fired = []

    for alarm in alarms:
        if should_fire(alarm):
            print(f"Firing alarm #{alarm.get('id')}: {alarm.get('message')}")
            # Launch visual alarm
            launch_alarm_app(alarm)
            # Send Telegram notification
            telegram_msg = format_telegram_message(alarm)
            send_telegram(telegram_msg)
            fired.append(alarm)

    # Disable one-time alarms that fired
    modified = False
    for alarm in fired:
        repeat = alarm.get("repeat")
        if repeat is None or repeat == "once":
            alarm["enabled"] = False
            alarm["last_fired"] = datetime.now().isoformat()
            modified = True
        else:
            alarm["last_fired"] = datetime.now().isoformat()
            modified = True

    if modified:
        save_alarms(data)

    if not fired:
        # Silent — no alarms to fire right now
        pass


if __name__ == "__main__":
    main()
