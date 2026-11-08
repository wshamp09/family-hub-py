"""Holidays: Calendar layer, a line on Today and notes in Week ahead.
Source: Google's public "Holidays in the United States" calendar (free, no key): federal holidays and
everyday observances (Mother's Day, Halloween, Easter ...). Each entry is labelled "Public holiday"
(offices, banks and the post office closed: shown as "Day off") or "Observance". The feed is saved in
household settings and refreshed weekly. Church days the feed may not carry (Ash Wednesday, Palm
Sunday, Good Friday, Pentecost, first Sunday of Advent) are worked out from the date of Easter."""
from __future__ import annotations

import json
import re
import time
from datetime import date, timedelta

import requests

from . import db
from .config import today
from .extras import EXTRA_UA

HOLIDAY_FEED = ("https://calendar.google.com/calendar/ical/"
                "en.usa%23holiday%40group.v.calendar.google.com/public/basic.ics")
HOLIDAY_REFRESH_DAYS = 7
HOLIDAY_STATE = "Florida"            # regional holidays are kept only for this state
_fail: dict = {}


def ics_unescape(x: str) -> str:
    x = re.sub(r"(?i)\\n", "\n", x)
    x = re.sub(r"\\([,;\\])", r"\1", x)
    return x.strip()


def parse_holiday_ics(txt: str) -> list[dict]:
    """.ics text -> [{date, name, day_off, kind}] sorted by date. Pure; tested in check_setup."""
    txt = re.sub(r"\r\n?", "\n", txt or "")
    txt = re.sub(r"\n[ \t]", "", txt)                 # undo line folding
    out = []
    for b in re.findall(r"(?s)BEGIN:VEVENT.*?END:VEVENT", txt):
        def field(key):
            m = re.search(rf"(?m)^{key}(;[^:\n]*)?:([^\n]*)", b)
            return m.group(2) if m else ""
        try:
            d = date(int(field("DTSTART")[:4]), int(field("DTSTART")[4:6]), int(field("DTSTART")[6:8]))
        except ValueError:
            continue
        name = ics_unescape(field("SUMMARY"))
        desc1 = ics_unescape(field("DESCRIPTION")).split("\n")[0]
        public = re.match(r"(?i)^Public holiday", desc1) is not None
        if " in " in desc1 and HOLIDAY_STATE not in desc1:      # another state's day
            continue
        if not name:
            continue
        out.append({"date": d, "name": name, "day_off": public, "kind": "public" if public else "observance"})
    return sorted(out, key=lambda h: (h["date"], not h["day_off"], h["name"]))


def fetch_holiday_feed() -> list[dict]:
    r = requests.get(HOLIDAY_FEED, headers={"User-Agent": EXTRA_UA}, timeout=15)
    if r.status_code >= 300:
        raise RuntimeError(f"HTTP {r.status_code} from Google Calendar")
    h = parse_holiday_ics(r.text)
    if not h:
        raise RuntimeError("the holiday feed was empty")
    return h


def holiday_feed() -> list[dict]:
    """The saved feed, refreshed weekly (a failed refresh keeps the saved copy and retries after 30 min)."""
    try:
        saved = json.loads(db.get_setting("holiday_feed", "") or "null")
    except ValueError:
        saved = None
    fresh = bool(saved and saved.get("fetched")) and \
        date.fromisoformat(saved["fetched"]) > today() - timedelta(days=HOLIDAY_REFRESH_DAYS)
    last = _fail.get("at")
    if not fresh and (last is None or time.time() - last >= 30 * 60):
        print("[holidays] refreshing the Google holiday feed")
        try:
            h = fetch_holiday_feed()
            rows = [{**x, "date": x["date"].isoformat()} for x in h]
            db.set_setting("holiday_feed", json.dumps({"fetched": today().isoformat(), "rows": rows}))
            saved = {"fetched": today().isoformat(), "rows": rows}
        except Exception as e:  # noqa: BLE001
            print(f"[holidays] {e}")
            _fail["at"] = time.time()
    rows = (saved or {}).get("rows") or []
    # Saved by either app: R saves a column-wise data frame as a list of row objects too.
    return [{"date": date.fromisoformat(str(r["date"])[:10]), "name": r["name"], "day_off": bool(r["day_off"]),
             "kind": r.get("kind", "observance")} for r in rows]


# ---- Church days from the date of Easter ----------------------------------------------------------
def easter_date(year: int) -> date:
    """Easter Sunday (Western), by the Anonymous Gregorian algorithm (Meeus/Jones/Butcher)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def church_days(years) -> list[dict]:
    out = []
    for y in years:
        e = easter_date(y)
        nov27 = date(y, 11, 27)
        advent = nov27 + timedelta(days=(7 - nov27.isoweekday()) % 7)    # first Sunday on/after Nov 27
        for d, name in [(e - timedelta(days=46), "Ash Wednesday"), (e - timedelta(days=7), "Palm Sunday"),
                        (e - timedelta(days=2), "Good Friday"), (e, "Easter Sunday"),
                        (e + timedelta(days=49), "Pentecost"), (advent, "First Sunday of Advent")]:
            out.append({"date": d, "name": name, "day_off": False, "kind": "church"})
    return out


def merge_holidays(feed: list[dict], church: list[dict]) -> list[dict]:
    """Google's entry wins when both have the same day (e.g. Easter Sunday)."""
    key = lambda h: (h["date"], re.sub(r"[^a-z]", "", h["name"].lower()))  # noqa: E731
    have = {key(h) for h in feed}
    out = feed + [c for c in church if key(c) not in have]
    return sorted(out, key=lambda h: (h["date"], not h["day_off"], h["name"]))


def holidays_between(frm: date, to: date) -> list[dict]:
    try:
        feed = holiday_feed()
    except Exception as e:  # noqa: BLE001
        print(f"[holidays] {e}")
        feed = []
    h = merge_holidays(feed, church_days(range(frm.year, to.year + 1)))
    return [x for x in h if frm <= x["date"] <= to]


def holiday_label(name: str, day_off: bool) -> str:
    return name + (" · Day off" if day_off else "")
