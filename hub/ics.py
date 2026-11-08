""".ics calendar export for appointments and reminders.
Repeating items are exported as a repeating series (RRULE). Timed events are written in UTC
("Z"), all-day events as dates, so Google and Apple Calendar show the right local time."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .config import APP_TITLE, TZ, has_text


def escape(x) -> str:
    x = "" if x is None else str(x)
    x = x.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    return x.replace("\r\n", "\\n").replace("\n", "\\n")


def fold(line: str) -> str:
    """Fold long lines (RFC 5545 continuation lines start with a space)."""
    if len(line) <= 74:
        return line
    parts = [line[i:i + 73] for i in range(0, len(line), 73)]
    return "\r\n".join([parts[0]] + [" " + p for p in parts[1:]])


def utc(t: datetime) -> str:
    if t.tzinfo is None:
        t = t.replace(tzinfo=TZ)
    return t.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def event(a: dict) -> list[str]:
    start = a["start_at"]
    end = a.get("end_at") or (start + timedelta(hours=1))
    if a.get("all_day"):
        d = start.astimezone(TZ).date() if start.tzinfo else start.date()
        when = [f"DTSTART;VALUE=DATE:{d:%Y%m%d}", f"DTEND;VALUE=DATE:{d + timedelta(days=1):%Y%m%d}"]
    else:
        when = [f"DTSTART:{utc(start)}", f"DTEND:{utc(end)}"]
    desc = "\n".join(x for x in [f"For: {a['who']}" if has_text(a.get("who")) else "",
                                 a.get("notes") if has_text(a.get("notes")) else ""] if x)
    title = f"Reminder: {a['title']}" if a.get("kind") == "reminder" else a["title"]
    lines = ["BEGIN:VEVENT", f"UID:familyhub-appt-{a['id']}@familyhub", f"DTSTAMP:{utc(datetime.now(timezone.utc))}",
             *when]
    if (a.get("recurrence") or "none") != "none":
        lines.append(f"RRULE:FREQ={a['recurrence'].upper()}")
    lines.append(f"SUMMARY:{escape(title)}")
    if has_text(a.get("location")):
        lines.append(f"LOCATION:{escape(a['location'])}")
    if desc:
        lines.append(f"DESCRIPTION:{escape(desc)}")
    lines.append("END:VEVENT")
    return [fold(l) for l in lines]


def calendar(appts: list[dict]) -> str:
    events = [l for a in appts for l in event(a)]
    return "\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:-//{APP_TITLE}//EN",
                        "CALSCALE:GREGORIAN", "METHOD:PUBLISH", *events, "END:VCALENDAR"]) + "\r\n"
