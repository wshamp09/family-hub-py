"""In season now (Meals page). Produce in season in Northeast Florida this month, written by the AI
once a month and saved in household settings (key "produce:YYYY-MM"), so everyone sees the same list
and the AI is asked about 12 times a year. "Refresh" on the Meals page asks again."""
from __future__ import annotations

import json
from datetime import date

from . import db, groq
from .config import today

SEASON_REGION = "Northeast Florida (Jacksonville area)"
SEASON_GROUPS = {"fruits": "Fruit", "vegetables": "Vegetables", "herbs": "Herbs"}


def season_key(day: date | None = None) -> str:
    return "produce:" + (day or today()).strftime("%Y-%m")


def _items(x) -> list[str]:
    if x is None:
        return []
    if isinstance(x, str):
        x = [x]
    out = []
    for i in x:
        v = " ".join(str(z) for z in (i if isinstance(i, list) else [i])).strip()
        if v:
            v = v[0].upper() + v[1:]
            if v not in out:
                out.append(v)
    return out[:20]


def clean_produce(j: dict) -> dict:
    """Tidy the model's reply into {fruits, vegetables, herbs, peak, tip}. Pure, for tests."""
    out = {"fruits": _items(j.get("fruits")), "vegetables": _items(j.get("vegetables")),
           "herbs": _items(j.get("herbs")), "peak": _items(j.get("peak")),
           "tip": str((j.get("tip") or "")).strip()}
    allv = out["fruits"] + out["vegetables"] + out["herbs"]
    out["peak"] = [p for p in out["peak"] if p in allv]
    if not out["fruits"] and not out["vegetables"]:
        raise RuntimeError("The AI didn't return a produce list")
    return out


def ai_produce(day: date | None = None) -> dict:
    month = (day or today()).strftime("%B")
    sys = ("You know local farming and farmers markets well. Reply with JSON only, no prose. "
           'Return {"fruits": [...], "vegetables": [...], "herbs": [...], "peak": [...], "tip": "..."}. '
           'Each list holds short common names (e.g. "strawberries"), at most 15 each. '
           '"peak" names up to 5 items from those lists that are at their very best this month. '
           '"tip" is one short sentence on shopping or cooking with this month\'s produce.')
    usr = (f"What fresh produce is in season and locally grown in {SEASON_REGION} during {month}? "
           "Only include items that are genuinely in season there that month.")
    return clean_produce(groq.chat_json(sys, usr, temperature=0.3))


def seasonal_produce(day: date | None = None, refresh: bool = False) -> dict | None:
    """This month's list: saved copy, or ask the AI (and save). refresh=True asks again."""
    day = day or today()
    key = season_key(day)
    if not refresh:
        hit = db.get_setting(key, "")
        if hit:
            try:
                return clean_produce(json.loads(hit))
            except (ValueError, RuntimeError):
                return None
    print(f"[season] asking the AI for {day:%B %Y}")
    p = ai_produce(day)
    db.set_setting(key, json.dumps(p))
    return p


def produce_prompt(p: dict | None) -> str:
    """Short text for the meal-ideas prompt."""
    if not p:
        return ""
    pick = p["peak"] + [x for x in p["vegetables"] + p["fruits"] + p["herbs"] if x not in p["peak"]]
    return (f"Build the meals around produce in season in {SEASON_REGION} right now "
            f"(use at least one in each meal, and name it in the description): {', '.join(pick[:25])}.")
