"""Date helpers and formatting."""
from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta

from .config import TZ


def week_start(d: date) -> date:
    """Monday of d's week."""
    return d - timedelta(days=d.isoweekday() - 1)


def month_start(d: date) -> date:
    return d.replace(day=1)


def quarter_start(d: date) -> date:
    return date(d.year, (d.month - 1) // 3 * 3 + 1, 1)


def period_start(freq: str, d: date) -> date:
    return {"daily": d, "weekly": week_start(d), "monthly": month_start(d),
            "quarterly": quarter_start(d), "yearly": date(d.year, 1, 1)}[freq]


def days_in_month(d: date) -> int:
    return calendar.monthrange(d.year, d.month)[1]


def add_months(d: date | None, n: int | None) -> date | None:
    """Add n months, clamping to the month's end (Jan 31 + 1 month = Feb 28/29)."""
    if d is None or n is None:
        return None
    m0 = d.month - 1 + int(n)
    y, m = d.year + m0 // 12, m0 % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def months_between(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


def to_date(x) -> date | None:
    if x is None or x == "":
        return None
    if isinstance(x, datetime):
        return x.astimezone(TZ).date() if x.tzinfo else x.date()
    if isinstance(x, date):
        return x
    try:
        return date.fromisoformat(str(x)[:10])
    except ValueError:
        return None


def _nolead(s: str) -> str:
    return s.replace(" 0", " ")


def fmt_day(d: date) -> str:
    """'Sat, Nov 7'"""
    return _nolead(d.strftime("%a, %b %d"))


def fmt_long_day(d: date) -> str:
    """'Saturday, November 7'"""
    return _nolead(d.strftime("%A, %B %d"))


def fmt_month(d: date) -> str:
    return d.strftime("%B %Y")


def fmt_time(t) -> str:
    """'7:05 AM' from a datetime or time."""
    if isinstance(t, datetime) and t.tzinfo:
        t = t.astimezone(TZ)
    s = t.strftime("%I:%M %p")
    return s[1:] if s.startswith("0") else s


def parse_hhmm(x) -> time | None:
    if not x:
        return None
    if isinstance(x, time):
        return x
    try:
        h, m = str(x).strip()[:5].split(":")
        return time(int(h), int(m))
    except (ValueError, TypeError):
        return None


def fmt_hhmm(x) -> str:
    """'14:30' -> '2:30 PM'"""
    t = parse_hhmm(x)
    return fmt_time(t) if t else ""


def hhmm(t: time | None) -> str:
    return t.strftime("%H:%M") if t else ""


def money(x) -> str:
    if x is None:
        return "—"
    return f"${float(x):,.2f}"


def text_lines(x) -> list[str]:
    if not x:
        return []
    return [ln.strip() for ln in str(x).splitlines() if ln.strip()]


def local_dt(d: date, t: time | None) -> datetime:
    return datetime.combine(d, t or time(0, 0), tzinfo=TZ)


def day_num(d: date) -> int:
    """Days since 1970-01-01 (R's as.integer(Date)); keeps daily picks identical to the R app."""
    return d.toordinal() - 719163
