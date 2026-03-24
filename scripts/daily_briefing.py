#!/usr/bin/env python3
"""Briefing diario 8 AM: calendario, notas pendientes, ultimos 5 correos por cuenta.

Corre via cron a las 8:00 AM ET.
Envia resumen por Telegram.
"""

from __future__ import annotations

import email
import email.header
import email.utils
import imaplib
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# ENV
# ---------------------------------------------------------------------------
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
TZ = ZoneInfo("America/New_York")
BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Telegram sender
# ---------------------------------------------------------------------------

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

    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
    })

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            return result.get("ok", False)
    except Exception as e:
        print(f"Error sending Telegram: {e}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# 1. CALENDARIO — fechas del dia (reusa logica de daily_holidays)
# ---------------------------------------------------------------------------

_DAY_MAP = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}
_ORD_MAP = {"1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5, "last": -1}

_WEEKDAYS_ES = {
    0: "lunes", 1: "martes", 2: "miercoles", 3: "jueves",
    4: "viernes", 5: "sabado", 6: "domingo",
}
_MONTHS_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}

_TYPE_LABELS = {
    "federal": "FERIADO FEDERAL",
    "state_fl": "FLORIDA",
    "local_fl": "FLORIDA",
    "local_capecoral": "CAPE CORAL",
    "cultural": "CULTURAL",
    "commercial": "COMERCIAL",
    "civic": "CIVICO",
    "observance": "OBSERVANCIA",
    "seasonal": "ESTACIONAL",
    "international": "INTERNACIONAL",
    "financial": "FINANCIERO",
}


def nth_weekday(year: int, month: int, weekday: int, n: int) -> datetime:
    if n == -1:
        if month == 12:
            last_day = datetime(year + 1, 1, 1, tzinfo=TZ) - timedelta(days=1)
        else:
            last_day = datetime(year, month + 1, 1, tzinfo=TZ) - timedelta(days=1)
        day = last_day
        while day.weekday() != weekday:
            day -= timedelta(days=1)
        return day
    else:
        first = datetime(year, month, 1, tzinfo=TZ)
        days_ahead = weekday - first.weekday()
        if days_ahead < 0:
            days_ahead += 7
        first_occ = first + timedelta(days=days_ahead)
        return first_occ + timedelta(weeks=n - 1)


def resolve_date(date_str: str, year: int, easter_dates: dict) -> datetime | None:
    if len(date_str) == 5 and date_str[2] == "-":
        month, day = int(date_str[:2]), int(date_str[3:])
        try:
            return datetime(year, month, day, tzinfo=TZ)
        except ValueError:
            return None

    parts = date_str.split("-")
    if len(parts) == 3 and parts[0] in _ORD_MAP and parts[1] in _DAY_MAP:
        n = _ORD_MAP[parts[0]]
        wd = _DAY_MAP[parts[1]]
        month = int(parts[2])
        return nth_weekday(year, month, wd, n)

    if "election" in date_str or "1st-tuesday-after-1st-monday" in date_str:
        first_monday = nth_weekday(year, 11, 0, 1)
        return first_monday + timedelta(days=1)

    if "cyber" in date_str or "monday-after-thanksgiving" in date_str:
        thanksgiving = nth_weekday(year, 11, 3, 4)
        return thanksgiving + timedelta(days=4)

    if "giving-tuesday" in date_str:
        thanksgiving = nth_weekday(year, 11, 3, 4)
        return thanksgiving + timedelta(days=5)

    if "small-business" in date_str:
        thanksgiving = nth_weekday(year, 11, 3, 4)
        return thanksgiving + timedelta(days=2)

    if "easter" in date_str.lower():
        easter_str = easter_dates.get(str(year))
        if easter_str:
            m, d = int(easter_str[:2]), int(easter_str[3:])
            return datetime(year, m, d, tzinfo=TZ)

    return None


def get_calendar_section(today: datetime) -> str:
    """Retorna las fechas/eventos del dia desde holidays.json."""
    config_path = BASE_DIR / "config" / "holidays.json"
    if not config_path.exists():
        return ""

    try:
        config = json.loads(config_path.read_text("utf-8"))
    except Exception:
        return ""

    year = today.year
    easter_dates = config.get("easter_dates", {})
    matches = []

    for h in config.get("holidays", []):
        resolved = resolve_date(h["date"], year, easter_dates)
        if resolved and resolved.month == today.month and resolved.day == today.day:
            matches.append(h)

    # Easter check
    easter_str = easter_dates.get(str(year))
    if easter_str:
        m, d = int(easter_str[:2]), int(easter_str[3:])
        easter = datetime(year, m, d, tzinfo=TZ)
        if easter.month == today.month and easter.day == today.day:
            matches.append({"name": "Domingo de Pascua (Easter)", "type": "cultural", "emoji": "🐣"})
        good_friday = easter - timedelta(days=2)
        if good_friday.month == today.month and good_friday.day == today.day:
            matches.append({"name": "Viernes Santo (Good Friday)", "type": "cultural", "emoji": "✝️"})

    if not matches:
        return "CALENDARIO HOY:\n  No hay fechas especiales hoy.\n"

    lines = ["CALENDARIO HOY:"]
    for h in matches:
        label = _TYPE_LABELS.get(h.get("type", ""), "")
        emoji = h.get("emoji", "")
        lines.append(f"  {emoji} {h['name']}  [{label}]")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 2. NOTAS PENDIENTES — via StickyNotes REST API
# ---------------------------------------------------------------------------

def get_notes_section() -> str:
    """Obtiene notas activas del StickyNotes desktop app."""
    try:
        url = "http://127.0.0.1:17532/notes"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        notes = data.get("notes", [])
        if not notes:
            return ""

        lines = [f"NOTAS PENDIENTES ({len(notes)}):"]
        for n in notes:
            title = n.get("title", "(sin titulo)")
            content = n.get("content", "")
            # Truncar contenido largo
            if content and len(content) > 80:
                content = content[:80] + "..."
            if content:
                lines.append(f"  - {title}: {content}")
            else:
                lines.append(f"  - {title}")
        lines.append("")
        return "\n".join(lines)
    except Exception:
        # StickyNotes app no corriendo — no pasa nada
        return ""


# ---------------------------------------------------------------------------
# 3. CORREOS — ultimos 5 de cada cuenta Gmail
# ---------------------------------------------------------------------------

def _get_encryption_key() -> str:
    env_key = os.environ.get("GMAIL_ENCRYPTION_KEY")
    if env_key:
        return env_key
    key_file = BASE_DIR / "data" / ".gmail_key"
    if key_file.exists():
        return key_file.read_text().strip()
    return ""


def _load_gmail_accounts() -> list[dict[str, str]]:
    """Carga cuentas Gmail del archivo encriptado."""
    cred_file = BASE_DIR / "data" / "gmail_accounts.enc.json"
    if not cred_file.exists():
        return []

    key = _get_encryption_key()
    if not key:
        return []

    try:
        # Importar crypto del proyecto
        sys.path.insert(0, str(BASE_DIR))
        from src.utils.crypto import decrypt_value
        encrypted = cred_file.read_text().strip()
        decrypted = decrypt_value(encrypted, key)
        return json.loads(decrypted)
    except Exception as e:
        print(f"Error loading Gmail accounts: {e}", file=sys.stderr)
        return []


def _decode_header(raw: str) -> str:
    if not raw:
        return ""
    parts = email.header.decode_header(raw)
    decoded = []
    for data, charset in parts:
        if isinstance(data, bytes):
            decoded.append(data.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(data)
    return " ".join(decoded)


def _fetch_emails(email_addr: str, app_password: str, count: int = 5) -> list[str]:
    """Obtiene los ultimos N emails de una cuenta via IMAP."""
    try:
        ctx = ssl.create_default_context()
        imap = imaplib.IMAP4_SSL("imap.gmail.com", 993, ssl_context=ctx)
        imap.login(email_addr, app_password)
        imap.select("INBOX", readonly=True)

        _, data = imap.uid("search", None, "ALL")
        all_uids = data[0].split() if data[0] else []

        if not all_uids:
            imap.logout()
            return ["  (inbox vacio)"]

        recent_uids = all_uids[-count:]
        recent_uids.reverse()

        lines = []
        for i, uid in enumerate(recent_uids, 1):
            _, msg_data = imap.uid("fetch", uid, "(RFC822.HEADER)")
            if msg_data[0] is None:
                continue
            raw = msg_data[0][1]
            parsed = email.message_from_bytes(raw)

            from_addr = _decode_header(parsed.get("From", ""))
            # Simplificar nombre del remitente
            if "<" in from_addr:
                from_name = from_addr.split("<")[0].strip().strip('"')
                if not from_name:
                    from_name = from_addr
            else:
                from_name = from_addr

            subject = _decode_header(parsed.get("Subject", "")) or "(sin asunto)"
            date_raw = parsed.get("Date", "")
            try:
                dt = email.utils.parsedate_to_datetime(date_raw)
                date_short = dt.strftime("%d/%m %H:%M")
            except Exception:
                date_short = date_raw[:16] if date_raw else "?"

            lines.append(f"  {i}. {date_short} | {from_name}\n     {subject}")

        imap.logout()
        return lines
    except Exception as e:
        return [f"  Error: {e}"]


def get_emails_section() -> str:
    """Obtiene ultimos 5 correos de cada cuenta configurada."""
    accounts = _load_gmail_accounts()
    if not accounts:
        return "CORREOS:\n  No hay cuentas Gmail configuradas.\n"

    sections = ["CORREOS:"]
    for acc in accounts:
        addr = acc.get("email", "?")
        pwd = acc.get("app_password", "")
        sections.append(f"\n  {addr}:")
        email_lines = _fetch_emails(addr, pwd, count=5)
        sections.extend(email_lines)

    sections.append("")
    return "\n".join(sections)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    now = datetime.now(TZ)
    wd = _WEEKDAYS_ES[now.weekday()]
    m = _MONTHS_ES[now.month]
    date_str = f"{wd} {now.day} de {m}, {now.year}"

    lines: list[str] = []
    lines.append(f"BRIEFING DIARIO — {date_str.upper()}")
    lines.append("=" * 40)
    lines.append("")

    # 1. Calendario
    cal = get_calendar_section(now)
    if cal:
        lines.append(cal)

    # 2. Notas pendientes
    notes = get_notes_section()
    if notes:
        lines.append(notes)

    # 3. Correos
    emails = get_emails_section()
    lines.append(emails)

    message = "\n".join(lines)

    # Telegram tiene limite de 4096 chars
    if len(message) > 4000:
        message = message[:4000] + "\n... (truncado)"

    if send_telegram(message):
        print("Briefing sent OK")
    else:
        print("Failed to send briefing", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
