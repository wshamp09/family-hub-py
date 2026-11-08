"""Trivia of the day, Trivial Pursuit style.
One multiple-choice question a day from the Open Trivia Database (opentdb.com, free, no key,
CC BY-SA 4.0). Seven wedges, one per weekday (Monday Geography ... Sunday General Knowledge).
Difficulty is mostly medium, with some easy and some hard days. Everyone gets the same question;
each person answers once, up to midnight the next day. A correct answer earns that day's wedge; all
seven in a week (Monday to Sunday) wins the pie. A day left unanswered past the next midnight loses
its wedge."""
from __future__ import annotations

import math
import time
from datetime import date, timedelta
from urllib.parse import unquote

from . import db
from .config import today
from .dates import day_num, week_start
from .extras import get_json

# In weekday order, Monday first. cats = Open Trivia DB category ids.
TRIVIA_WEDGES = [
    {"key": "geo", "name": "Geography", "color": "#2B6CB0", "cats": "22"},
    {"key": "ent", "name": "Entertainment", "color": "#D9548F", "cats": "11,12,14"},
    {"key": "his", "name": "History", "color": "#E8B21E", "cats": "23"},
    {"key": "art", "name": "Arts & Literature", "color": "#8A5A3B", "cats": "10,25"},
    {"key": "sci", "name": "Science & Nature", "color": "#2E8B57", "cats": "17,19,27"},
    {"key": "spo", "name": "Sports & Leisure", "color": "#E07B2E", "cats": "21,16"},
    {"key": "gen", "name": "General Knowledge", "color": "#7E57C2", "cats": "9"},
]
TRIVIA_N = len(TRIVIA_WEDGES)
WEDGE = {w["key"]: w for w in TRIVIA_WEDGES}


def trivia_wedge_for(day: date) -> dict:
    return TRIVIA_WEDGES[day.isoweekday() - 1]


def trivia_difficulty_for(day: date) -> str:
    n = day_num(day)
    return "hard" if n % 5 == 0 else ("easy" if n % 7 == 0 else "medium")


def trivia_order(n_choices: int, day: date) -> list[int]:
    """Stable shuffle of the answer choices for a day (0-based; same order as the R app)."""
    order = list(range(n_choices))
    k = day_num(day)
    for i in range(n_choices, 1, -1):      # small Fisher-Yates driven by the date
        k = (k * 1103 + 12345) % 2147483648
        j = k % i
        order[i - 1], order[j] = order[j], order[i - 1]
    return order


def fetch_trivia(day: date) -> dict:
    w = trivia_wedge_for(day)
    cats = w["cats"].split(",")
    cat_id = cats[day_num(day) // 7 % len(cats)]          # sub-category changes week to week
    for diff in list(dict.fromkeys([trivia_difficulty_for(day), "medium", ""])):
        q = {"amount": 1, "category": cat_id, "type": "multiple", "encode": "url3986"}
        if diff:
            q["difficulty"] = diff
        j = get_json("https://opentdb.com/api.php", params=q)
        if int(j.get("response_code", -1)) == 0 and j.get("results"):
            r = j["results"][0]
            choices = [unquote(r["correct_answer"])] + [unquote(x) for x in r["incorrect_answers"]]
            choices = [choices[i] for i in trivia_order(len(choices), day)]
            return {"wedge": w["key"], "category": unquote(r["category"]), "difficulty": unquote(r["difficulty"]),
                    "question": unquote(r["question"]), "choices": choices, "answer": unquote(r["correct_answer"])}
        time.sleep(5)                                       # Open Trivia DB allows one request per 5 seconds
    raise RuntimeError("no trivia question available")


def trivia_my_answer(user_id: str, day: date | None = None) -> dict | None:
    return db.one("select choice, correct from trivia_answers where user_id = $1::uuid and answer_date = $2::date",
                  user_id, day or today())


def trivia_record(user_id: str, day: date, q: dict, choice: str) -> None:
    db.run("""insert into trivia_answers (user_id, answer_date, wedge, choice, correct)
              values ($1::uuid, $2::date, $3, $4, $5::boolean) on conflict (user_id, answer_date) do nothing""",
           user_id, day, q["wedge"], choice, choice == q["answer"])


def trivia_scores(day: date | None = None) -> list[dict]:
    """Wedges earned this week, and pies won so far, for each login."""
    ws = week_start(day or today())
    users = db.get("""select user_id::text as user_id, coalesce(display_name, email) as name from app_users
                      order by created_at""")
    week = db.get("""select user_id::text as user_id, wedge from trivia_answers
                      where correct and answer_date between $1::date and $2::date""", ws, ws + timedelta(days=6))
    pies = {r["user_id"]: int(r["pies"]) for r in db.get("""
        select user_id::text as user_id, count(*) as pies from (
          select user_id, date_trunc('week', answer_date) as wk
            from trivia_answers where correct and answer_date < $1::date
           group by user_id, wk having count(distinct wedge) = 7) x
        group by user_id""", ws)}
    for u in users:
        u["wedges"] = list(dict.fromkeys(w["wedge"] for w in week if w["user_id"] == u["user_id"]))
        u["pies"] = pies.get(u["user_id"], 0) + (1 if len(u["wedges"]) == TRIVIA_N else 0)
    return users


def trivia_pie_svg(earned: list[str], size: int = 44) -> str:
    """A Trivial Pursuit-style pie: earned wedges in colour, the rest pale."""
    r, c0, step = size / 2 - 1, size / 2, 2 * math.pi / TRIVIA_N

    def pt(a):
        return f"{c0 + r * math.sin(a):.2f} {c0 - r * math.cos(a):.2f}"
    slices = "".join(
        f'<path d="M {c0:.2f} {c0:.2f} L {pt(i * step)} A {r:.2f} {r:.2f} 0 0 1 {pt((i + 1) * step)} Z" '
        f'fill="{w["color"] if w["key"] in earned else "#EFE6D8"}" stroke="#FFFFFF" stroke-width="2"/>'
        for i, w in enumerate(TRIVIA_WEDGES))
    n = sum(1 for w in TRIVIA_WEDGES if w["key"] in earned)
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" role="img" '
            f'aria-label="{n} of {TRIVIA_N} wedges">{slices}</svg>')
