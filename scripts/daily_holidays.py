#!/usr/bin/env python3
"""Envia recordatorios de fechas conmemorativas diarias por Telegram.

Corre via cron a las 7:05 AM ET (justo despues del clima).
Revisa: fechas de hoy, manana, y proximos 7 dias.
"""

from __future__ import annotations

import json
import os
import sys
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
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "holidays.json"

# ---------------------------------------------------------------------------
# Nth weekday calculator
# ---------------------------------------------------------------------------

_DAY_MAP = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

_ORD_MAP = {"1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5, "last": -1}


def nth_weekday(year: int, month: int, weekday: int, n: int) -> datetime:
    """Return the nth weekday of a given month/year. n=-1 means last."""
    if n == -1:
        # Start from end of month
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
        # Find first occurrence of weekday
        days_ahead = weekday - first.weekday()
        if days_ahead < 0:
            days_ahead += 7
        first_occ = first + timedelta(days=days_ahead)
        return first_occ + timedelta(weeks=n - 1)


def resolve_date(date_str: str, year: int, easter_dates: dict) -> datetime | None:
    """Resolve a date string from config to an actual datetime for the given year."""

    # Fixed date: MM-DD
    if len(date_str) == 5 and date_str[2] == "-":
        month, day = int(date_str[:2]), int(date_str[3:])
        try:
            return datetime(year, month, day, tzinfo=TZ)
        except ValueError:
            return None

    # Nth weekday: "3rd-monday-01"
    parts = date_str.split("-")
    if len(parts) == 3 and parts[0] in _ORD_MAP and parts[1] in _DAY_MAP:
        n = _ORD_MAP[parts[0]]
        wd = _DAY_MAP[parts[1]]
        month = int(parts[2])
        return nth_weekday(year, month, wd, n)

    # Special: election day — 1st tuesday after 1st monday of november
    if "election" in date_str or "1st-tuesday-after-1st-monday" in date_str:
        first_monday = nth_weekday(year, 11, 0, 1)  # Monday=0
        election_day = first_monday + timedelta(days=1)
        return election_day

    # Special: cyber monday (monday after thanksgiving)
    if "cyber" in date_str or "monday-after-thanksgiving" in date_str:
        thanksgiving = nth_weekday(year, 11, 3, 4)  # Thursday=3, 4th
        return thanksgiving + timedelta(days=4)

    # Special: giving tuesday (tuesday after thanksgiving)
    if "giving-tuesday" in date_str:
        thanksgiving = nth_weekday(year, 11, 3, 4)
        return thanksgiving + timedelta(days=5)

    # Special: small business saturday (saturday after thanksgiving)
    if "small-business" in date_str:
        thanksgiving = nth_weekday(year, 11, 3, 4)
        return thanksgiving + timedelta(days=2)

    # Easter-based dates
    if "easter" in date_str.lower():
        easter_str = easter_dates.get(str(year))
        if easter_str:
            m, d = int(easter_str[:2]), int(easter_str[3:])
            return datetime(year, m, d, tzinfo=TZ)

    return None


def get_easter(year: int, easter_dates: dict) -> datetime | None:
    """Get Easter date for a given year."""
    easter_str = easter_dates.get(str(year))
    if easter_str:
        m, d = int(easter_str[:2]), int(easter_str[3:])
        return datetime(year, m, d, tzinfo=TZ)
    return None


# ---------------------------------------------------------------------------
# Load config and match dates
# ---------------------------------------------------------------------------

def load_holidays() -> dict:
    if not CONFIG_PATH.exists():
        print(f"Config not found: {CONFIG_PATH}", file=sys.stderr)
        sys.exit(1)
    return json.loads(CONFIG_PATH.read_text("utf-8"))


def get_matching_holidays(config: dict, target_date: datetime) -> list[dict]:
    """Return all holidays that match a specific date."""
    year = target_date.year
    easter_dates = config.get("easter_dates", {})
    matches = []

    for h in config.get("holidays", []):
        resolved = resolve_date(h["date"], year, easter_dates)
        if resolved and resolved.month == target_date.month and resolved.day == target_date.day:
            matches.append(h)

    # Check Easter itself
    easter = get_easter(year, easter_dates)
    if easter and easter.month == target_date.month and easter.day == target_date.day:
        matches.append({
            "name": "Domingo de Pascua (Easter)",
            "type": "cultural",
            "emoji": "🐣",
            "description": "Easter Sunday"
        })

    # Good Friday (2 days before Easter)
    if easter:
        good_friday = easter - timedelta(days=2)
        if good_friday.month == target_date.month and good_friday.day == target_date.day:
            matches.append({
                "name": "Viernes Santo (Good Friday)",
                "type": "cultural",
                "emoji": "✝️",
                "description": "Good Friday — feriado estatal en Florida"
            })

    return matches


def get_upcoming_holidays(config: dict, from_date: datetime, days_ahead: int = 7) -> list[tuple[datetime, dict]]:
    """Return holidays in the next N days (excluding today)."""
    upcoming = []
    year = from_date.year
    easter_dates = config.get("easter_dates", {})

    for day_offset in range(1, days_ahead + 1):
        check_date = from_date + timedelta(days=day_offset)
        check_year = check_date.year

        for h in config.get("holidays", []):
            resolved = resolve_date(h["date"], check_year, easter_dates)
            if resolved and resolved.month == check_date.month and resolved.day == check_date.day:
                upcoming.append((check_date, h))

        # Easter
        easter = get_easter(check_year, easter_dates)
        if easter and easter.month == check_date.month and easter.day == check_date.day:
            upcoming.append((check_date, {
                "name": "Domingo de Pascua (Easter)",
                "type": "cultural", "emoji": "🐣",
                "description": "Easter Sunday"
            }))
        if easter:
            gf = easter - timedelta(days=2)
            if gf.month == check_date.month and gf.day == check_date.day:
                upcoming.append((check_date, {
                    "name": "Viernes Santo (Good Friday)",
                    "type": "cultural", "emoji": "✝️",
                    "description": "Good Friday"
                }))

    return upcoming


# ---------------------------------------------------------------------------
# Format message
# ---------------------------------------------------------------------------

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

_WEEKDAYS_ES = {
    0: "lunes", 1: "martes", 2: "miercoles", 3: "jueves",
    4: "viernes", 5: "sabado", 6: "domingo",
}

_MONTHS_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}


def format_date_es(dt: datetime) -> str:
    wd = _WEEKDAYS_ES[dt.weekday()]
    m = _MONTHS_ES[dt.month]
    return f"{wd} {dt.day} de {m}"


def build_message(today: datetime, today_holidays: list[dict],
                  upcoming: list[tuple[datetime, dict]]) -> str | None:
    """Build Telegram message. Returns None if nothing to report."""

    if not today_holidays and not upcoming:
        return None

    lines: list[str] = []
    lines.append(f"CALENDARIO — {format_date_es(today).upper()}")
    lines.append("")

    if today_holidays:
        lines.append("HOY:")
        for h in today_holidays:
            label = _TYPE_LABELS.get(h.get("type", ""), "")
            emoji = h.get("emoji", "")
            lines.append(f"  {emoji} {h['name']}  [{label}]")
            if h.get("description"):
                lines.append(f"     {h['description']}")
        lines.append("")

    if upcoming:
        lines.append("PROXIMOS 7 DIAS:")
        # Group by date
        by_date: dict[str, list] = {}
        for dt, h in upcoming:
            key = format_date_es(dt)
            if key not in by_date:
                by_date[key] = []
            by_date[key].append(h)

        for date_label, holidays in by_date.items():
            for h in holidays:
                emoji = h.get("emoji", "")
                label = _TYPE_LABELS.get(h.get("type", ""), "")
                lines.append(f"  {date_label}: {emoji} {h['name']}  [{label}]")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Telegram send
# ---------------------------------------------------------------------------

def send_telegram(text: str) -> bool:
    import urllib.request
    import urllib.error

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
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    config = load_holidays()
    now = datetime.now(TZ)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    today_holidays = get_matching_holidays(config, today)
    upcoming = get_upcoming_holidays(config, today, days_ahead=7)

    message = build_message(today, today_holidays, upcoming)

    if message:
        if send_telegram(message):
            print(f"Holidays sent OK — {len(today_holidays)} today, {len(upcoming)} upcoming")
        else:
            print("Failed to send holidays", file=sys.stderr)
            sys.exit(1)
    else:
        print("No holidays today or in the next 7 days")


if __name__ == "__main__":
    main()
