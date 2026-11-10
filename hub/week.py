"""Week ahead: everything for one Monday-Sunday week, what's still unplanned, and the
Sunday 'plan next week' banner (1 pm to 10 pm)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from . import countdown, data, db, holidays
from .config import has_text, now
from .dates import fmt_day, month_start, week_start

WEEK_BANNER_DAY = 7      # Sunday (isoweekday)
WEEK_BANNER_START = 13   # 1 pm
WEEK_BANNER_END = 22     # until 10 pm


def week_data(ws: date) -> dict:
    we = ws + timedelta(days=6)
    bills = []
    for m in sorted({month_start(ws), month_start(we)}):
        bills += [b for b in data.bills_for_month(m) if ws <= b["due_date"] <= we]
    try:
        hols = holidays.holidays_between(ws, we)
    except Exception as e:  # noqa: BLE001
        print("[week] holidays:", e)
        hols = []
    return {"start": ws, "meals": data.meals_between(ws, we), "duties": data.duties_between(ws, we),
            "appts": data.appts_between(ws, we),
            "workouts": db.get("""select * from workouts where workout_date between $1::date and $2::date
                                  order by workout_date, id""", ws, we),
            "bills": bills, "chores": data.chore_dates_between(ws, we), "holidays": hols,
            "countdowns": countdown.between(ws, we)}


def week_gaps(w: dict) -> list[str]:
    """Plain-language list of things still to sort out for the week."""
    days = [w["start"] + timedelta(days=i) for i in range(7)]
    dinners = {m["plan_date"] for m in w["meals"] if m["slot"] == "Dinner"}
    no_dinner = [d for d in days if d not in dinners]
    unassigned = [d for d in w["duties"] if d.get("person_id") is None and not has_text(d.get("other_name"))]
    gaps = []
    if no_dinner:
        gaps.append(f"{len(no_dinner)} dinner{'s' if len(no_dinner) > 1 else ''} not planned "
                    f"({', '.join(d.strftime('%a') for d in no_dinner)})")
    gaps += [f"{fmt_day(d['duty_date'])} {d['duty_type'].lower()} has no one assigned" for d in unassigned]
    if not w["workouts"]:
        gaps.append("No workouts planned")
    return gaps


def week_planned_key(ws: date) -> str:
    return f"week_planned_{ws.isoformat()}"


def show_week_banner(t: datetime | None = None) -> bool:
    """True between Sunday 1 pm and 10 pm when next week hasn't been marked planned."""
    t = t or now()
    if t.isoweekday() != WEEK_BANNER_DAY or not (WEEK_BANNER_START <= t.hour < WEEK_BANNER_END):
        return False
    return db.get_setting(week_planned_key(week_start(t.date()) + timedelta(days=7)), "") != "yes"
