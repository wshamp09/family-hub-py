"""Starter chore list (everyday cleaning schedule, plus outdoor/system jobs).
Loaded automatically. Monthly chores have a day of the month and yearly chores a date,
spread out so they don't pile up. All of it can be edited (or hidden) in the app."""
from __future__ import annotations

import re

from . import db

_DAILY = ["Sweep or vacuum crumbs off floors", "Wipe kitchen countertops",
          "Wipe dining table and tidy living room", "Do the dishes", "Wipe stovetop",
          "Take out food/organic garbage", "Make bed", "Tidy bedside table",
          "Fold and put away clothes", "Wipe condensation from shower", "Put away kids' toys"]
_WEEKLY = ["Clean toilet and behind toilet", "Clean bathroom sink and mirror",
           "Spray shower walls and floor (vinegar)", "Wash bath and hand towels",
           "Clear out fridge leftovers and expired food", "Vacuum bedroom floors", "Wash bedding",
           "Sweep and mop floors", "Dust surfaces", "Wipe down window sills"]
_MONTHLY = [(3, "Mop floors (deep)"), (6, "Wipe microwave and oven"), (9, "Dust all surfaces in living room"),
            (12, "Clean dishwasher"), (15, "Deep clean shower walls and floor"),
            (18, "Clean fridge drawers and shelves"), (21, "Reorganize closets and drawers")]
_MONTHLY_OPT = [(24, "Clean interior/exterior windows"), (1, "Remove scuff marks on walls"),
                (28, "Deep clean oven"), (26, "Clean baseboards")]
_YEARLY = [(1, 15, "Clean kitchen and bathroom drains"), (2, 15, "Clean behind fridge"),
           (12, 6, "Wash or dry clean curtains"), (3, 15, "Pressure wash driveway"),
           (4, 5, "Clean outside A/C units"), (4, 12, "Clean gutters (spring)"), (5, 10, "Clean HVAC vents"),
           (5, 24, "Deep clean deck or patio"), (6, 14, "Deep clean range hood"),
           (7, 12, "Wipe out kitchen cabinets and drawers"), (8, 16, "Deep clean appliances"),
           (9, 13, "Dust blinds and light fixtures"), (10, 4, "Clean fireplace exterior"),
           (10, 18, "Clean gutters (fall)"), (11, 8, "Deep clean carpets")]


def _key(freq: str, title: str) -> str:
    return f"{freq}:" + re.sub(r"[^a-z0-9]+", "-", title.lower())


STARTER_CHORES = (
    [{"frequency": "daily", "optional": False, "due_month": None, "due_day": None, "title": t} for t in _DAILY]
    + [{"frequency": "weekly", "optional": False, "due_month": None, "due_day": None, "title": t} for t in _WEEKLY]
    + [{"frequency": "monthly", "optional": False, "due_month": None, "due_day": d, "title": t} for d, t in _MONTHLY]
    + [{"frequency": "monthly", "optional": True, "due_month": None, "due_day": d, "title": t} for d, t in _MONTHLY_OPT]
    + [{"frequency": "yearly", "optional": False, "due_month": m, "due_day": d, "title": t} for m, d, t in _YEARLY]
)
for _c in STARTER_CHORES:
    _c["starter_key"] = _key(_c["frequency"], _c["title"])

_checked = {"done": False}


def ensure_starter_chores() -> int:
    """Add any starter chore that isn't in the database yet (hidden ones stay hidden). A chore with
    the same name that was added by hand is adopted instead of duplicated. Returns how many were added."""
    if _checked["done"]:
        return 0
    have = {r["starter_key"] for r in db.get("select starter_key from chores where starter_key is not null")}
    todo = [c for c in STARTER_CHORES if c["starter_key"] not in have]
    if todo:
        print(f"[chores] loading {len(todo)} starter chores")
    for r in todo:
        n = db.run("""update chores set starter_key = $1, due_day = coalesce(due_day, $2),
                        due_month = coalesce(due_month, $3)
                      where starter_key is null and lower(title) = lower($4) and frequency = $5""",
                   r["starter_key"], r["due_day"], r["due_month"], r["title"], r["frequency"])
        if n == 0:
            db.run("""insert into chores (title, frequency, optional, due_day, due_month, starter_key)
                      values ($1, $2, $3::boolean, $4, $5, $6) on conflict (starter_key) do nothing""",
                   r["title"], r["frequency"], r["optional"], r["due_day"], r["due_month"], r["starter_key"])
    _checked["done"] = True
    return len(todo)
