"""School run traffic on Today (TomTom Routing + Geocoding).
Weekdays only: 6:30-9:30 AM home -> school, 2:30-5:30 PM school -> home. Needs TOMTOM_API_KEY.
Routes are fetched at most every 10 minutes and shared by everyone (about 36 requests a weekday,
well inside TomTom's free tier). Addresses live in household settings (Settings > School run);
the home address is the same one the sitter sheet uses."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from urllib.parse import quote

import requests

from . import db
from .config import TZ, cfg, now

TRAFFIC_CACHE_MIN = 10
TRAFFIC_HEAVY_MIN = 10        # minutes slower than usual before the line turns orange
SCHOOL_DEFAULT = "8985 Annie Eliza Rd, Jacksonville, FL 32256"
TRAFFIC_WINDOWS = [
    {"key": "am", "from": "06:30", "to": "09:30", "start": "home", "end": "school"},
    {"key": "pm", "from": "14:30", "to": "17:30", "start": "school", "end": "home"},
]
_cache: dict = {}


def traffic_key() -> str:
    return cfg("TOMTOM_API_KEY", "")


def school_settings() -> dict:
    return {"home": db.get_setting("home_address", "").strip(),
            "school": db.get_setting("school_address", SCHOOL_DEFAULT).strip(),
            "label": db.get_setting("school_label", "School").strip(),
            "arrive_by": db.get_setting("school_arrive_by", "").strip()}


def traffic_window(t: datetime | None = None) -> dict | None:
    """Which window t falls in, or None (weekends and other hours)."""
    t = (t or now()).astimezone(TZ)
    if t.isoweekday() > 5:
        return None
    hm = t.strftime("%H:%M")
    for w in TRAFFIC_WINDOWS:
        if w["from"] <= hm < w["to"]:
            return w
    return None


def clock_today(hm: str, t: datetime | None = None) -> datetime | None:
    """Today's clock time 'HH:MM' as a datetime (None if the text isn't a time)."""
    if not re.match(r"^\d{1,2}:\d{2}$", hm or ""):
        return None
    t = (t or now()).astimezone(TZ)
    h, m = hm.split(":")
    return t.replace(hour=int(h), minute=int(m), second=0, microsecond=0)


# ---- TomTom calls ----------------------------------------------------------------------------------
def tt_get(url: str, params: dict | None = None) -> dict:
    key = traffic_key()
    if not key:
        raise RuntimeError("TOMTOM_API_KEY is not set in the app's secrets")
    r = requests.get(url, params={"key": key, **(params or {})}, timeout=10)
    if r.status_code >= 300:
        raise RuntimeError(f"TomTom returned {r.status_code}: {r.text[:200]}")
    return r.json()


def tt_geocode(address: str) -> dict | None:
    """Address -> {lat, lon, label}. Saved in household settings, so each address is looked up once."""
    address = (address or "").strip()
    if not address:
        return None
    key = "geo:" + re.sub(r"\s+", " ", address.lower())
    hit = db.get_setting(key, "")
    if hit:
        try:
            g = json.loads(hit)
            if g.get("lat") is not None:
                return g
        except ValueError:
            pass
    print(f"[traffic] geocoding {address}")
    j = tt_get(f"https://api.tomtom.com/search/2/geocode/{quote(address, safe='')}.json",
               {"limit": 1, "countrySet": "US"})
    res = j.get("results") or []
    if not res:
        raise RuntimeError(f"TomTom couldn't find the address: {address}")
    g = {"lat": res[0]["position"]["lat"], "lon": res[0]["position"]["lon"],
         "label": (res[0].get("address") or {}).get("freeformAddress") or address}
    db.set_setting(key, json.dumps(g))
    return g


def tt_route(frm: dict, to: dict) -> dict:
    """Route leaving now, with live traffic."""
    loc = f"{frm['lat']:.6f},{frm['lon']:.6f}:{to['lat']:.6f},{to['lon']:.6f}"
    j = tt_get(f"https://api.tomtom.com/routing/1/calculateRoute/{loc}/json",
               {"traffic": "true", "travelMode": "car", "computeTravelTimeFor": "all"})
    s = j["routes"][0]["summary"]
    if s.get("travelTimeInSeconds") is None:
        raise RuntimeError("TomTom returned no route")
    num = lambda x: None if x is None else float(x)  # noqa: E731
    return {"travel": num(s.get("travelTimeInSeconds")), "delay": num(s.get("trafficDelayInSeconds")),
            "usual": num(s.get("historicTrafficTravelTimeInSeconds")), "free": num(s.get("noTrafficTravelTimeInSeconds")),
            "meters": num(s.get("lengthInMeters"))}


# ---- What the Today line says (pure; tested in check_setup) -------------------------------------------
def traffic_summary(route: dict, win: dict, t: datetime | None = None, arrive_by: str = "") -> dict:
    t = t or now()
    mins = lambda s: int(round(s / 60))  # noqa: E731
    travel = mins(route["travel"])
    # "Slower than usual" compares with TomTom's typical time for this hour; if that's missing,
    # with the delay TomTom reports against free-flowing traffic.
    if route.get("usual") is not None:
        slower = mins(route["travel"] - route["usual"])
    else:
        slower = mins(route.get("delay") or 0)
    arrive = t + timedelta(seconds=route["travel"])
    leave_by = None
    if win["key"] == "am" and arrive_by:
        target = clock_today(arrive_by, t)
        if target is not None and target > t:       # nothing to say once the bell has gone
            lb = target - timedelta(seconds=route["travel"])
            leave_by = {"at": lb, "late": lb < t, "target": target}
    compare = (f"{slower} min slower than usual" if slower >= 2
               else f"{-slower} min faster than usual" if slower <= -2 else "about usual")
    return {"travel": travel, "slower": slower, "arrive": arrive, "heavy": slower >= TRAFFIC_HEAVY_MIN,
            "compare": compare, "leave_by": leave_by,
            "miles": round(route["meters"] / 1609.34, 1) if route.get("meters") is not None else None}


def traffic_rain(wx: dict | None, win: dict | None, t: datetime | None = None) -> dict | None:
    """Rain during the rest of this window, from the hourly forecast (50%+)."""
    if not wx or not win or not wx.get("hours"):
        return None
    t = t or now()
    end = clock_today(win["to"], t)
    ks = [i for i, h in enumerate(wx["hours"]) if t - timedelta(hours=1) <= h < end and wx["rain"][i] is not None]
    if not ks:
        return None
    p = max(wx["rain"][i] for i in ks)
    if p < 50:
        return None
    first = next(i for i in ks if wx["rain"][i] >= 50)
    return {"p": round(p), "at": wx["hours"][first]}


def traffic_now(win: dict | None, t: datetime | None = None) -> dict | None:
    """Fetch (or reuse) the route for this window: {route, from, to, fetched} or {error}."""
    if not win:
        return None
    t = t or now()
    s = school_settings()
    if not traffic_key():
        return {"error": "Add TOMTOM_API_KEY to the app's secrets to see the school run."}
    if not s["home"]:
        return {"error": "Add your home address under Settings > School run."}
    if not s["school"]:
        return {"error": "Add the school address under Settings > School run."}
    ck = f"{win['key']} {s['home']} {s['school']}"
    hit = _cache.get("route")
    if hit and hit["key"] == ck and (t - hit["at"]) < timedelta(minutes=TRAFFIC_CACHE_MIN):
        return hit["data"]
    try:
        pts = {"home": tt_geocode(s["home"]), "school": tt_geocode(s["school"])}
        frm, to = pts[win["start"]], pts[win["end"]]
        print(f"[traffic] route {win['start']} -> {win['end']}")
        data = {"route": tt_route(frm, to), "from": frm, "to": to, "fetched": t}
    except Exception as e:  # noqa: BLE001
        print(f"[traffic] {e}")
        data = {"error": str(e)}
    # On a failed call keep showing the last good route for this window (marked by its time).
    if "error" in data and hit and hit["key"] == ck and "error" not in hit["data"]:
        return hit["data"]
    _cache["route"] = {"key": ck, "at": t, "data": data}
    return data


def clear_cache() -> None:
    _cache.pop("route", None)


def maps_link(frm: dict, to: dict) -> str:
    return ("https://www.google.com/maps/dir/?api=1&origin={:.6f},{:.6f}&destination={:.6f},{:.6f}"
            "&travelmode=driving").format(frm["lat"], frm["lon"], to["lat"], to["lon"])
