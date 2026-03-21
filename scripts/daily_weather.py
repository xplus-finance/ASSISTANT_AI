#!/usr/bin/env python3
"""Envía el pronóstico del clima diario completo para Cape Coral, FL por Telegram."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Cargar .env manualmente (sin dependencias externas)
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
LOCATION = "Cape+Coral,FL"
TZ = ZoneInfo("America/New_York")

# --- Weather fetch ---

def fetch_weather_json() -> dict | None:
    """Obtiene el pronóstico JSON completo de wttr.in."""
    url = f"https://wttr.in/{LOCATION}?format=j1&lang=es"
    req = urllib.request.Request(url, headers={
        "User-Agent": "curl/7.88.0",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        print(f"Error fetching weather: {e}", file=sys.stderr)
        return None


def format_weather(data: dict) -> str:
    """Formatea el pronóstico en un mensaje bonito para Telegram."""
    now = datetime.now(TZ)
    lines: list[str] = []

    lines.append(f"Buenos dias Mi Jefe")
    lines.append(f"Clima para hoy {now.strftime('%A %d de %B, %Y')}")
    lines.append(f"Cape Coral, Florida")
    lines.append("")

    # Current conditions
    current = data.get("current_condition", [{}])[0]
    desc = current.get("lang_es", [{}])
    desc_text = desc[0].get("value", current.get("weatherDesc", [{}])[0].get("value", "")) if desc else current.get("weatherDesc", [{}])[0].get("value", "")
    temp_c = current.get("temp_C", "?")
    temp_f = current.get("temp_F", "?")
    humidity = current.get("humidity", "?")
    wind_mph = current.get("windspeedMiles", "?")
    wind_dir = current.get("winddir16Point", "")
    feels_f = current.get("FeelsLikeF", "?")
    uv = current.get("uvIndex", "?")
    visibility = current.get("visibilityMiles", "?")

    lines.append(f"AHORA MISMO:")
    lines.append(f"  {desc_text}")
    lines.append(f"  Temperatura: {temp_f}F ({temp_c}C)")
    lines.append(f"  Sensacion termica: {feels_f}F")
    lines.append(f"  Humedad: {humidity}%")
    lines.append(f"  Viento: {wind_mph} mph {wind_dir}")
    lines.append(f"  UV: {uv}  |  Visibilidad: {visibility} mi")
    lines.append("")

    # Today's forecast (hourly highlights)
    weather_list = data.get("weather", [])
    if weather_list:
        today = weather_list[0]
        max_f = today.get("maxtempF", "?")
        min_f = today.get("mintempF", "?")
        max_c = today.get("maxtempC", "?")
        min_c = today.get("mintempC", "?")
        sunrise = today.get("astronomy", [{}])[0].get("sunrise", "?")
        sunset = today.get("astronomy", [{}])[0].get("sunset", "?")
        total_sun = today.get("sunHour", "?")

        lines.append(f"PRONOSTICO DEL DIA:")
        lines.append(f"  Maxima: {max_f}F ({max_c}C)  |  Minima: {min_f}F ({min_c}C)")
        lines.append(f"  Amanecer: {sunrise}  |  Atardecer: {sunset}")
        lines.append(f"  Horas de sol: {total_sun}")
        lines.append("")

        # Hourly breakdown (key hours: morning, noon, afternoon, evening)
        hourly = today.get("hourly", [])
        hour_labels = {
            "600": "6 AM (Manana)",
            "900": "9 AM",
            "1200": "12 PM (Mediodia)",
            "1500": "3 PM (Tarde)",
            "1800": "6 PM",
            "2100": "9 PM (Noche)",
        }

        if hourly:
            lines.append("POR HORAS:")
            for h in hourly:
                time_val = h.get("time", "0").zfill(4)
                # Only show key hours
                label = hour_labels.get(time_val)
                if not label:
                    # Show all in steps of 3
                    hour_int = int(time_val) // 100
                    if hour_int % 3 != 0:
                        continue
                    ampm = "AM" if hour_int < 12 else "PM"
                    display = hour_int if hour_int <= 12 else hour_int - 12
                    if display == 0:
                        display = 12
                    label = f"{display} {ampm}"

                h_desc = h.get("lang_es", [{}])
                h_desc_text = h_desc[0].get("value", "") if h_desc else h.get("weatherDesc", [{}])[0].get("value", "")
                h_temp_f = h.get("tempF", "?")
                h_rain = h.get("chanceofrain", "0")
                h_wind = h.get("windspeedMiles", "?")

                rain_indicator = f"  Lluvia: {h_rain}%" if int(h_rain or 0) > 10 else ""
                lines.append(f"  {label}: {h_temp_f}F - {h_desc_text} - Viento {h_wind}mph{rain_indicator}")

    lines.append("")

    # Tomorrow preview
    if len(weather_list) > 1:
        tomorrow = weather_list[1]
        t_max_f = tomorrow.get("maxtempF", "?")
        t_min_f = tomorrow.get("mintempF", "?")
        t_hourly = tomorrow.get("hourly", [])
        t_desc = ""
        if t_hourly:
            mid = t_hourly[len(t_hourly) // 2]
            t_desc_data = mid.get("lang_es", [{}])
            t_desc = t_desc_data[0].get("value", "") if t_desc_data else mid.get("weatherDesc", [{}])[0].get("value", "")

        lines.append(f"MANANA: {t_max_f}F / {t_min_f}F - {t_desc}")

    return "\n".join(lines)


def send_telegram(text: str) -> bool:
    """Envía mensaje por Telegram Bot API."""
    if not BOT_TOKEN or not CHAT_ID:
        print("Error: TELEGRAM_BOT_TOKEN o AUTHORIZED_CHAT_ID no configurados", file=sys.stderr)
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": int(CHAT_ID),
        "text": text,
        "parse_mode": "",  # plain text for reliability
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


def main() -> None:
    data = fetch_weather_json()
    if not data:
        # Fallback: enviar al menos algo
        now = datetime.now(TZ)
        send_telegram(
            f"Buenos dias Mi Jefe ({now.strftime('%A %d de %B')})\n\n"
            f"No pude obtener el pronostico del clima para hoy. "
            f"Revisare mas tarde."
        )
        return

    message = format_weather(data)
    if send_telegram(message):
        print("Weather sent OK")
    else:
        print("Failed to send weather", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
