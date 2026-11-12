"""Weather on Today (Open-Meteo: free, no key). Default location: Mandarin, Jacksonville; override
with WEATHER_LAT / WEATHER_LON. Fetched at most every 30 minutes and shared by everyone.
Also the moon phase (calculated; no outside source)."""
from __future__ import annotations

import math
import time as _time
from datetime import date, datetime, timedelta, timezone

import requests

from .config import APP_TZ, TZ, cfg, now, today

WEATHER_CACHE_MIN = 15          # often enough for the next-hour rain line
RAIN_MM = 0.1                   # rain in a 15-minute slot counts from this much (mm)
NEXT_HOUR_WATCH = 2             # hours ahead to look for rain stopping
_cache: dict = {}


def wx_code_info(code, is_day: bool = True) -> dict:
    """label + emoji for an Open-Meteo weather code."""
    try:
        c = int(code)
    except (TypeError, ValueError):
        return {"label": "", "icon": "☁️"}
    if c == 0:
        return {"label": "Clear", "icon": "☀️" if is_day else "🌙"}
    if c == 1:
        return {"label": "Mostly clear", "icon": "🌤️" if is_day else "🌙"}
    if c == 2:
        return {"label": "Partly cloudy", "icon": "⛅" if is_day else "☁️"}
    if c == 3:
        return {"label": "Cloudy", "icon": "☁️"}
    if c in (45, 48):
        return {"label": "Foggy", "icon": "🌫️"}
    if 51 <= c <= 57:
        return {"label": "Drizzle", "icon": "🌦️"}
    if c in (61, 63, 80, 81):
        return {"label": "Rain", "icon": "🌧️"}
    if c in (65, 82):
        return {"label": "Heavy rain", "icon": "🌧️"}
    if c in (66, 67):
        return {"label": "Freezing rain", "icon": "🌧️"}
    if 71 <= c <= 77 or c in (85, 86):
        return {"label": "Snow", "icon": "❄️"}
    if c in (95, 96, 99):
        return {"label": "Thunderstorms", "icon": "⛈️"}
    return {"label": "", "icon": "☁️"}


def _local(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M").replace(tzinfo=TZ)


def fetch_weather() -> dict | None:
    hit = _cache.get("wx")
    if hit and _time.time() - hit[0] < WEATHER_CACHE_MIN * 60:
        return hit[1]
    print("[weather] fetching forecast")
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", timeout=10, params={
            "latitude": cfg("WEATHER_LAT", "30.159"), "longitude": cfg("WEATHER_LON", "-81.628"),
            "current": "temperature_2m,weather_code,is_day", "hourly": "precipitation_probability",
            "minutely_15": "precipitation", "forecast_minutely_15": 12,
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
                     "uv_index_max,sunrise,sunset",
            "temperature_unit": "fahrenheit", "timezone": APP_TZ, "forecast_days": 5})
        j = r.json() if r.status_code < 300 else {}
    except (requests.RequestException, ValueError) as e:
        print(f"[weather] {e}")
        j = {}
    if not j.get("current"):
        return hit[1] if hit else None   # keep the last good forecast
    dl = j["daily"]
    d = {"now_temp": j["current"]["temperature_2m"], "now_code": j["current"]["weather_code"],
         "is_day": j["current"].get("is_day") == 1,
         "hours": [_local(t) for t in j["hourly"]["time"]], "rain": j["hourly"]["precipitation_probability"],
         "days": [date.fromisoformat(t) for t in dl["time"]], "day_code": dl["weather_code"],
         "hi": dl["temperature_2m_max"], "lo": dl["temperature_2m_min"],
         "rain_max": dl["precipitation_probability_max"], "uv": dl["uv_index_max"],
         "sunrise": [_local(t) for t in dl["sunrise"]], "sunset": [_local(t) for t in dl["sunset"]]}
    m15 = j.get("minutely_15") or {}
    d["q_times"] = [_local(t) for t in m15.get("time") or []]
    d["q_rain"] = m15.get("precipitation") or []
    _cache["wx"] = (_time.time(), d)
    return d


def hour_label(t: datetime) -> str:
    s = t.strftime("%I %p")
    return s[1:] if s.startswith("0") else s


def next_hour_rain(d: dict, t: datetime | None = None) -> dict | None:
    """The always-shown line under the temperature. From the 15-minute forecast: rain starting within the hour,
    or rain now and when it eases (within NEXT_HOUR_WATCH hours). Otherwise the hourly chance for the next hour
    (the higher of this hour and the next)."""
    t = t or now()
    q = [(tm, mm) for tm, mm in zip(d.get("q_times") or [], d.get("q_rain") or []) if mm is not None
         and tm + timedelta(minutes=15) > t and tm <= t + timedelta(hours=NEXT_HOUR_WATCH)]
    if q:
        wet = [mm >= RAIN_MM for _, mm in q]
        if wet[0]:
            stop = next((tm for (tm, _), w in zip(q, wet) if not w), None)
            return {"icon": "☔", "text": f"Raining now, easing around {fmt_clock(stop)}" if stop else "Raining now"}
        start = next((tm for (tm, _), w in zip(q, wet) if w and tm <= t + timedelta(hours=1)), None)
        if start:
            return {"icon": "☔", "text": f"Rain starting around {fmt_clock(start)}"}
    probs = [p for h, p in zip(d.get("hours") or [], d.get("rain") or [])
             if p is not None and h <= t + timedelta(hours=1) and h + timedelta(hours=1) > t]
    if not probs:
        return None
    p = round(max(probs))
    return {"icon": "🌂" if p < 30 else "☂️", "text": f"Next hour: {p}% chance of rain"}


def fmt_clock(tm: datetime) -> str:
    s = tm.strftime("%I:%M %p")
    return s[1:] if s.startswith("0") else s


def weather_notes(d: dict, t: datetime | None = None) -> list[dict]:
    """Short, plain notes for the porch (the 5-day strip shows each day's high, low and rain).
    Day index 0 = today, 1 = tomorrow."""
    t = t or now()
    notes = []

    def add(icon, text):
        notes.append({"icon": icon, "text": text})

    today_d = t.date()

    def rain_after(day, frm):
        ks = [i for i, h in enumerate(d["hours"]) if h.date() == day and h >= frm]
        hits = [i for i in ks if d["rain"][i] is not None and d["rain"][i] >= 50]
        if not hits:
            return None
        return {"at": d["hours"][hits[0]], "p": max(d["rain"][i] for i in ks if d["rain"][i] is not None)}

    late = t.hour >= 18
    r_today = rain_after(today_d, t - timedelta(hours=1))
    if r_today and not late:
        add("☂️", f"Rain likely now ({round(r_today['p'])}%)" if r_today["at"] <= t
            else f"Rain likely after {hour_label(r_today['at'])} ({round(r_today['p'])}%)")
    elif not late and (d["rain_max"][0] or 0) >= 30:
        add("🌦️", f"Chance of rain today ({round(d['rain_max'][0])}%)")
    if not late and (d["hi"][0] or 0) >= 92:
        add("🥵", f"Hot today: {round(d['hi'][0])}°")
    if not late and (d["uv"][0] or 0) >= 8:
        add("🧴", "Very high UV, wear sunscreen")
    if t.hour < 11 and d["lo"][0] is not None and d["lo"][0] <= 45:
        add("🧥", f"Chilly morning: {round(d['lo'][0])}°")
    if len(d["hi"]) >= 2:
        r_tom = rain_after(today_d + timedelta(days=1), datetime.combine(today_d + timedelta(days=1),
                                                                         datetime.min.time(), tzinfo=TZ))
        if r_tom:
            add("☂️", f"Rain likely tomorrow after {hour_label(r_tom['at'])} ({round(r_tom['p'])}%)")
        if d["lo"][1] is not None and d["lo"][1] <= 45:
            add("🧥", f"Chilly tomorrow morning: {round(d['lo'][1])}°")
    return notes


def weather_days(d: dict, n: int = 5) -> list[dict]:
    """Today plus the next 4 days, for the strip under the notes."""
    out = []
    for i, day in enumerate(d["days"][:n]):
        info = wx_code_info(d["day_code"][i])
        out.append({"label": "Today" if day == today() else day.strftime("%a"), "icon": info["icon"],
                    "cond": info["label"], "hi": round(d["hi"][i]), "lo": round(d["lo"][i]),
                    "rain": round(d["rain_max"][i] or 0)})
    return out


# ---- Moon phase ---------------------------------------------------------------------------------------
# Mean synodic month from a known new moon (2000-01-06 18:14 UTC); within about half a day.
MOON_SYNODIC = 29.530588853
MOON_REF = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)


def moon_phase(t: datetime | None = None) -> dict:
    t = t or now()
    age = ((t - MOON_REF).total_seconds() / 86400) % MOON_SYNODIC
    lit = (1 - math.cos(2 * math.pi * age / MOON_SYNODIC)) / 2
    q = MOON_SYNODIC / 4

    def near(x):
        return abs(age - x) <= 1 or abs(age - x - MOON_SYNODIC) <= 1

    if near(0):
        name, emoji = "New moon", "🌑"
    elif near(q):
        name, emoji = "First quarter", "🌓"
    elif near(2 * q):
        name, emoji = "Full moon", "🌕"
    elif near(3 * q):
        name, emoji = "Last quarter", "🌗"
    elif age < q:
        name, emoji = "Waxing crescent", "🌒"
    elif age < 2 * q:
        name, emoji = "Waxing gibbous", "🌔"
    elif age < 3 * q:
        name, emoji = "Waning gibbous", "🌖"
    else:
        name, emoji = "Waning crescent", "🌘"
    to_full = (2 * q - age) % MOON_SYNODIC
    return {"name": name, "emoji": emoji, "lit": round(100 * lit), "age": age,
            "next_full": (t + timedelta(days=to_full)).astimezone(TZ).date()}
