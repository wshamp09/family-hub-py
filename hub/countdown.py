"""Countdowns: events you add by hand (a trip, a party, a due date), counted down on Today and tagged in
Week ahead. Today shows the next COUNTDOWN_SHOW within COUNTDOWN_DAYS days; past ones drop off by themselves
(they stay in the list under "Manage" until deleted)."""
from __future__ import annotations

from datetime import date, timedelta

from . import db

COUNTDOWN_SHOW = 4
COUNTDOWN_DAYS = 365
COUNTDOWN_EMOJI = ["🎉", "✈️", "🏖️", "🎂", "💍", "🎄", "🎓", "🏥", "🚗", "⛺", "🎟️", "👶"]


def days_label(n: int) -> str:
    """0 -> 'Today!', 1 -> 'Tomorrow', otherwise 'N days'. Pure, for tests."""
    return "Today!" if n == 0 else ("Tomorrow" if n == 1 else f"{n} days")


def upcoming(today_d: date, limit: int = COUNTDOWN_SHOW, within: int = COUNTDOWN_DAYS) -> list[dict]:
    rows = db.get("""select * from countdowns where event_date between $1::date and $2::date
                     order by event_date, id limit $3""", today_d, today_d + timedelta(days=within), limit)
    for r in rows:
        r["days"] = (r["event_date"] - today_d).days
    return rows


def between(a: date, b: date) -> list[dict]:
    return db.get("select * from countdowns where event_date between $1::date and $2::date order by event_date, id", a, b)


def all_items() -> list[dict]:
    return db.get("select * from countdowns order by event_date desc, id")


def save(cid, title: str, event_date: date, emoji: str, by: str) -> None:
    if cid:
        db.run("update countdowns set title = $2, event_date = $3::date, emoji = $4 where id = $1",
               int(cid), title.strip()[:80], event_date, emoji)
    else:
        db.run("insert into countdowns (title, event_date, emoji, created_by) values ($1, $2::date, $3, $4)",
               title.strip()[:80], event_date, emoji, by)


def delete(cid) -> None:
    db.run("delete from countdowns where id = $1", int(cid))
