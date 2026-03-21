#!/usr/bin/env python3
"""Recordatorio único: chequear reloj de bolsillo — 23 marzo 2026."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

# Cargar .env
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

def _load_env() -> None:
    if not _ENV_FILE.exists():
        return
    for line in _ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and value and key not in os.environ:
            os.environ[key] = value

_load_env()

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("AUTHORIZED_CHAT_ID", "")


def send_telegram(text: str) -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        print("Error: TELEGRAM_BOT_TOKEN o AUTHORIZED_CHAT_ID no configurados", file=sys.stderr)
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": int(CHAT_ID),
        "text": text,
        "parse_mode": "",
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"Error enviando Telegram: {e}", file=sys.stderr)
        return False


def remove_from_cron() -> None:
    """Auto-elimina esta entrada del crontab después de ejecutarse."""
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if result.returncode != 0:
            return
        lines = result.stdout.splitlines()
        new_lines = [l for l in lines if "reminder_watch_20260323" not in l]
        if len(new_lines) < len(lines):
            proc = subprocess.run(["crontab", "-"], input="\n".join(new_lines) + "\n", text=True)
            if proc.returncode == 0:
                print("Cron entry auto-removed")
    except Exception as e:
        print(f"Error removing cron: {e}", file=sys.stderr)


if __name__ == "__main__":
    send_telegram(
        "⏰ RECORDATORIO Mi Jefe:\n\n"
        "Hoy lunes 23 de marzo tiene que chequear el reloj de bolsillo."
    )
    remove_from_cron()
