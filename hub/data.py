"""Shared data functions used by several pages: people, chores, kids duties, meals, bills,
appointments & reminders (repeats are stored once and expanded here)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from . import db
from .config import APP_TZ, TZ, as_id, has_text, today
from .dates import add_months, days_in_month, month_start, months_between, period_start, to_date


def kids_names() -> list[str]:
    """From Settings > Kids' names (used by the dinner question)."""
    return [k.strip() for k in db.get_setting("kids_names", "").split(",") if k.strip()]


def join_names(n: list[str]) -> str:
    if not n:
        return "the kids"
    if len(n) == 1:
        return n[0]
    return ", ".join(n[:-1]) + " and " + n[-1]


def get_people(active_only: bool = True) -> list[dict]:
    return db.get("select id, name, is_active, sort_order from people"
                  + (" where is_active" if active_only else "") + " order by sort_order, name")


def person_name(people: list[dict], pid) -> str | None:
    for p in people:
        if p["id"] == pid:
            return p["name"]
    return None


# ---- Chores ------------------------------------------------------------------------------------
# Each chore resets at the start of its period. Monthly chores fall due on a day of the month and
# yearly chores on a date; days past the end of a month use its last day.

def safe_date(y: int, m: int, d: int) -> date:
    first = date(int(y), int(m), 1)
    return first + timedelta(days=min(int(d), days_in_month(first)) - 1)


def chore_due_date(freq: str, start: date, due_day=None, due_month=None) -> date:
    """When a chore is due within the period that starts on `start`."""
    if freq == "daily":
        return start
    if freq == "weekly":
        return start + timedelta(days=6)
    if freq == "monthly":
        return add_months(start, 1) - timedelta(days=1) if due_day is None else safe_date(start.year, start.month, due_day)
    if freq == "quarterly":
        return add_months(start, 3) - timedelta(days=1)
    if freq == "yearly":
        if due_month is None or due_day is None:
            return date(start.year, 12, 31)
        return safe_date(start.year, due_month, due_day)
    raise ValueError(freq)


def chore_status(done: bool, due: date, ref: date) -> str:
    """done / overdue / soon (within 7 days) / later"""
    if done:
        return "done"
    if due < ref:
        return "overdue"
    return "soon" if (due - ref).days <= 7 else "later"


def chores_for_date(ref: date) -> list[dict]:
    """One row per active chore, with its status for the period containing `ref`."""
    ch = db.get("""select id, title, frequency, notes, optional, due_day, due_month, starter_key
                     from chores where active order by title""")
    if not ch:
        return []
    for c in ch:
        c["period_start"] = period_start(c["frequency"], ref)
        c["due_date"] = chore_due_date(c["frequency"], c["period_start"], c["due_day"], c["due_month"])
    logs = db.get("""select chore_id, period_start, done, done_by from chore_log
                      where period_start between $1::date and $2::date""",
                  min(c["period_start"] for c in ch), max(c["period_start"] for c in ch))
    by = {(l["chore_id"], to_date(l["period_start"])): l for l in logs}
    for c in ch:
        l = by.get((c["id"], c["period_start"]))
        c["done"] = bool(l and l["done"])
        c["done_by"] = l["done_by"] if c["done"] else None
        c["status"] = chore_status(c["done"], c["due_date"], ref)
    return ch


def chore_dates_between(frm: date, to: date) -> list[dict]:
    """Monthly / yearly chore due dates between two dates (Calendar and Week ahead)."""
    ch = db.get("""select id, title, frequency, due_day, due_month from chores
                    where active and frequency in ('monthly', 'yearly')""")
    out = []
    for c in ch:
        if c["frequency"] == "monthly":
            starts, s = [], month_start(frm)
            while s <= month_start(to):
                starts.append(s)
                s = add_months(s, 1)
        else:
            starts = [date(y, 1, 1) for y in range(frm.year, to.year + 1)]
        for s in starts:
            d = chore_due_date(c["frequency"], s, c["due_day"], c["due_month"])
            if frm <= d <= to:
                out.append({"id": c["id"], "title": c["title"], "period_start": s, "due_date": d})
    if not out:
        return []
    logs = db.get("""select chore_id, period_start from chore_log
                      where done and period_start between $1::date and $2::date""",
                  min(o["period_start"] for o in out), max(o["period_start"] for o in out))
    done = {(l["chore_id"], to_date(l["period_start"])) for l in logs}
    for o in out:
        o["done"] = (o["id"], o["period_start"]) in done
    return sorted(out, key=lambda o: (o["due_date"], o["title"]))


def chore_set_done(chore_id, start: date, done: bool, by: str | None) -> None:
    db.run("""insert into chore_log (chore_id, period_start, done, done_at, done_by)
              values ($1, $2::date, $3::boolean, case when $3::boolean then now() end, $4)
              on conflict (chore_id, period_start) do update
                set done = excluded.done, done_at = excluded.done_at, done_by = excluded.done_by""",
           int(chore_id), start, bool(done), by if done else None)


# ---- Kids duties ---------------------------------------------------------------------------------
def duties_between(frm: date, to: date) -> list[dict]:
    return db.get("""select * from childcare_duties where duty_date between $1::date and $2::date
                     order by duty_date, coalesce(duty_time, '99:99'), id""", frm, to)


def duty_set_done(did, done: bool) -> None:
    db.run("update childcare_duties set done = $2::boolean where id = $1", int(did), bool(done))


def duty_set_person(did, person_id, other_name=None) -> None:
    db.run("update childcare_duties set person_id = $2, other_name = $3 where id = $1",
           int(did), as_id(person_id), other_name)


def duty_who(d: dict, people: list[dict]) -> str:
    if has_text(d.get("other_name")):
        return d["other_name"]
    return person_name(people, d.get("person_id")) or "Unassigned"


# ---- Meals -----------------------------------------------------------------------------------------
def meals_between(frm: date, to: date) -> list[dict]:
    return db.get("""select * from meal_plan where plan_date between $1::date and $2::date
                     order by plan_date, array_position(array['Breakfast','Lunch','Dinner','Snack'], slot), id""",
                  frm, to)


# ---- Bills -----------------------------------------------------------------------------------------
def bills_for_month(m: date, ref: date | None = None) -> list[dict]:
    """Tracked bills that fall in month m, with this month's payer, amount and paid status.
    Autopay can't be overdue: once the due day has passed it counts as paid."""
    m = month_start(m)
    ref = ref or today()
    out = []
    pays = {p["bill_id"]: p for p in db.get(
        "select bill_id, payer_id, amount, paid, paid_on from bill_payments where month = $1::date", m)}
    for b in db.get("select * from bills where active and track order by due_day, name"):
        ms = months_between(to_date(b["start_month"]), m)
        f = b["frequency"]
        if ms < 0 or not (f == "monthly" or (f == "quarterly" and ms % 3 == 0) or (f == "annual" and ms % 12 == 0)):
            continue
        alt = b["payer_rule"] == "alternate" and b["alt_payer_id"] is not None and ms % 2 == 1
        b["rule_payer"] = b["alt_payer_id"] if alt else b["default_payer_id"]
        p = pays.get(b["id"])
        b["payer_id"] = p["payer_id"] if p and p["payer_id"] is not None else b["rule_payer"]
        b["pay_amount"] = p["amount"] if p and p["amount"] is not None else b["amount"]
        b["due_date"] = m + timedelta(days=min(int(b["due_day"] or 1), days_in_month(m)) - 1)
        b["auto_paid"] = bool(b["autopay"]) and b["due_date"] < ref
        b["paid"] = bool(p and p["paid"]) or b["auto_paid"]
        b["paid_on"] = to_date(p["paid_on"]) if p else None
        if b["auto_paid"] and b["paid_on"] is None:
            b["paid_on"] = b["due_date"]
        out.append(b)
    return out


def bill_payment_upsert(bill_id, month: date, field: str, val) -> None:
    month = month_start(month)
    if field == "paid":
        db.run("""insert into bill_payments (bill_id, month, paid, paid_on)
                  values ($1, $2::date, $3::boolean, case when $3::boolean then current_date end)
                  on conflict (bill_id, month) do update set paid = excluded.paid, paid_on = excluded.paid_on""",
               int(bill_id), month, bool(val))
    else:
        col = {"payer": "payer_id", "amount": "amount"}[field]
        db.run(f"""insert into bill_payments (bill_id, month, {col}) values ($1, $2::date, $3)
                   on conflict (bill_id, month) do update set {col} = excluded.{col}""",
               int(bill_id), month, val)


# ---- Appointments & reminders ------------------------------------------------------------------------
def occurrence_date(d0: date, rule: str, k: int) -> date:
    """The k-th occurrence after d0 for a repeat rule (month ends are clamped)."""
    if rule == "weekly":
        return d0 + timedelta(days=7 * k)
    if rule == "monthly":
        return add_months(d0, k)
    if rule == "yearly":
        return add_months(d0, 12 * k)
    return d0


def next_k(d0: date, rule: str, day: date) -> int:
    """Smallest k >= 0 whose occurrence falls on or after `day`."""
    if rule == "none" or d0 >= day:
        return 0
    if rule == "weekly":
        k = -(-(day - d0).days // 7)
    elif rule == "monthly":
        k = max(0, months_between(d0, day) - 1)
    else:
        k = max(0, months_between(d0, day) // 12 - 1)
    while occurrence_date(d0, rule, k) < day:
        k += 1
    return k


def next_occurrence(d0: date, rule: str, day: date) -> date:
    return occurrence_date(d0, rule, next_k(d0, rule, day))


def _local(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.astimezone(TZ) if dt.tzinfo else dt.replace(tzinfo=TZ)


def shift_to_date(start: datetime, end: datetime | None, new_date: date):
    """Move a start/end to another date, keeping the local clock time and duration."""
    s = _local(start)
    st = datetime.combine(new_date, s.time(), tzinfo=TZ)
    en = None if end is None else st + (_local(end) - s)
    return st, en


def expand_occurrences(rows: list[dict], frm: date, to: date) -> list[dict]:
    """One row per occurrence between frm and to, sorted by time."""
    out = []
    for r in rows:
        rule = r["recurrence"]
        d0 = _local(r["start_at"]).date()
        if rule == "none":
            if frm <= d0 <= to:
                out.append({**r, "start_at": _local(r["start_at"]), "end_at": _local(r["end_at"]), "occ_date": d0})
            continue
        k, n = next_k(d0, rule, frm), 0
        while n < 400:
            d = occurrence_date(d0, rule, k)
            if d > to:
                break
            st, en = shift_to_date(r["start_at"], r["end_at"], d)
            out.append({**r, "start_at": st, "end_at": en, "occ_date": d})
            k += 1
            n += 1
    return sorted(out, key=lambda x: x["start_at"])


def appts_between(frm: date, to: date) -> list[dict]:
    """Everything that happens between two dates (repeats expanded)."""
    a = db.get("""select * from appointments
                   where (recurrence = 'none'
                          and start_at >= ($1::date::timestamp at time zone $3)
                          and start_at <  (($2::date + 1)::timestamp at time zone $3))
                      or (recurrence <> 'none'
                          and start_at <  (($2::date + 1)::timestamp at time zone $3))
                   order by start_at""", frm, to, APP_TZ)
    return expand_occurrences(a, frm, to)


def overdue_reminders(day: date | None = None) -> list[dict]:
    return db.get("""select * from appointments
                      where kind = 'reminder' and not done
                        and start_at < ($1::date::timestamp at time zone $2)
                      order by start_at""", day or today(), APP_TZ)


def reminder_done(rid, done: bool = True):
    """One-off reminders are marked done; repeating ones move to their next date
    (returned)."""
    r = db.one("select * from appointments where id = $1", int(rid))
    if not r:
        return None
    if r["recurrence"] == "none" or not done:
        db.run("""update appointments set done = $2::boolean, done_at = case when $2::boolean then now() end
                  where id = $1""", r["id"], bool(done))
        return None
    d0 = _local(r["start_at"]).date()
    nxt = next_occurrence(d0, r["recurrence"], max(d0, today()) + timedelta(days=1))
    st, en = shift_to_date(r["start_at"], r["end_at"], nxt)
    db.run("update appointments set start_at = $2, end_at = $3, done = false, done_at = now() where id = $1",
           r["id"], st, en)
    return nxt


def local_ts(d: date | None, hhmm: str | None = "00:00") -> str | None:
    """Local date + 'HH:MM' as text; use in SQL as ($n::timestamp at time zone $m) with APP_TZ."""
    if d is None:
        return None
    return f"{d.isoformat()} {hhmm if has_text(hhmm) else '00:00'}"
