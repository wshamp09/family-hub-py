"""Family calendar: day / week / month view of everything with a date (FullCalendar)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import streamlit as st

from hub import data, db, ui
from hub.config import CAL_COLORS, TZ, has_text, today
from hub.dates import add_months, money, month_start
from hub.holidays import holiday_label, holidays_between

LAYERS = {"Appointments & reminders": "appt", "Kids duties": "kids", "Meals": "meals", "Bills": "bills",
          "Chores": "chores", "Workouts": "work", "Holidays": "hol"}
DEFAULT_ON = ["appt", "kids", "bills", "chores", "work", "hol"]
VIEWS = {"Day": "timeGridDay", "Week": "timeGridWeek", "Month": "dayGridMonth"}

# Smaller text on phones only; same look otherwise.
CSS = """
.fc { font-family: "Work Sans", system-ui, sans-serif; }
.fc .fc-toolbar-title { font-size: 1.15rem; font-weight: 700; }
.fc .fc-button { border-radius: 999px; background: #2E7D6B; border-color: #2E7D6B; text-transform: capitalize; }
.fc .fc-button:disabled { background: #8bbfb2; border-color: #8bbfb2; }
.fc .fc-day-today { background: #FFF3D6 !important; }
.fc-event { border-radius: 6px; font-size: .82rem; }
@media (max-width: 640px) {
  .fc .fc-toolbar { flex-wrap: wrap; gap: .3rem; }
  .fc .fc-toolbar-title { font-size: .95rem; }
  .fc .fc-button { padding: .2rem .5rem; font-size: .78rem; }
  .fc-event, .fc .fc-col-header-cell-cushion, .fc .fc-daygrid-day-number, .fc .fc-timegrid-slot-label { font-size: .68rem; }
}
"""


def _ts(t: datetime) -> str:
    return t.astimezone(TZ).strftime("%Y-%m-%dT%H:%M:%S")


def _ev(eid, layer, title, start, end=None, all_day=True, body=""):
    c = CAL_COLORS[layer]
    e = {"id": eid, "title": title, "start": start, "allDay": all_day, "backgroundColor": c, "borderColor": c,
         "textColor": "#ffffff", "extendedProps": {"layer": layer, "body": body}}
    if end:
        e["end"] = end
    return e


def calendar_events(frm: date, to: date, layers: list[str]) -> list[dict]:
    ppl = ui.people()
    ev = []
    if "appt" in layers:
        for a in data.appts_between(frm, to):
            pre = ("✓ " if a.get("done") else "⏰ ") if a["kind"] == "reminder" else ""
            body = " · ".join(x for x in [f"For: {a['who']}" if has_text(a.get("who")) else "",
                                          a.get("location") or "", a.get("notes") or ""] if x)
            if a.get("all_day"):
                ev.append(_ev(f"a{a['id']}-{a['occ_date']:%Y%m%d}", "appt", pre + a["title"], a["occ_date"].isoformat(),
                              body=body))
            else:
                end = a.get("end_at") or (a["start_at"] + timedelta(hours=1))
                ev.append(_ev(f"a{a['id']}-{a['occ_date']:%Y%m%d}", "appt", pre + a["title"], _ts(a["start_at"]),
                              _ts(end), all_day=False, body=body))
    if "kids" in layers:
        for d in data.duties_between(frm, to):
            who = data.duty_who(d, ppl)
            title = f"{d['duty_type']}{' ' + d['child'] if has_text(d.get('child')) else ''} – {who}"
            if has_text(d.get("duty_time")):
                st_ = datetime.combine(d["duty_date"], datetime.strptime(d["duty_time"][:5], "%H:%M").time())
                ev.append(_ev(f"k{d['id']}", "kids", title, st_.strftime("%Y-%m-%dT%H:%M:%S"),
                              (st_ + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S"), all_day=False,
                              body=d.get("location") or ""))
            else:
                ev.append(_ev(f"k{d['id']}", "kids", title, d["duty_date"].isoformat(), body=d.get("notes") or ""))
    if "meals" in layers:
        for m in data.meals_between(frm, to):
            ev.append(_ev(f"m{m['id']}", "meals", f"{m['slot']}: {m['meal_name']}", m["plan_date"].isoformat()))
    if "bills" in layers and ui.can("money"):
        m = month_start(frm)
        while m <= to:
            for b in data.bills_for_month(m):
                if frm <= b["due_date"] <= to:
                    payer = ui.name_of(b["payer_id"]) or "?"
                    ev.append(_ev(f"b{b['id']}-{m:%Y%m}", "bills", f"{'✓ ' if b['paid'] else ''}{b['name']} ({payer})",
                                  b["due_date"].isoformat(), body=f"Amount: {money(b['pay_amount'])}"))
            m = add_months(m, 1)
    if "chores" in layers:
        for c in data.chore_dates_between(frm, to):
            ev.append(_ev(f"c{c['id']}-{c['due_date']:%Y%m%d}", "chores", f"{'✓ ' if c['done'] else ''}{c['title']}",
                          c["due_date"].isoformat()))
    if "work" in layers:
        for w in db.get("""select id, workout_date, person_id, title, duration_min, done from workouts
                           where workout_date between $1::date and $2::date""", frm, to):
            who = ui.name_of(w["person_id"]) or "?"
            ev.append(_ev(f"w{w['id']}", "work", f"{'✓ ' if w['done'] else ''}{w['title']} – {who}",
                          w["workout_date"].isoformat(), body=f"{w['duration_min']} min" if w.get("duration_min") else ""))
    if "hol" in layers:
        for i, h in enumerate(holidays_between(frm, to)):
            body = ("Public holiday: offices, banks and the post office are closed" if h["day_off"]
                    else "Church calendar" if h["kind"] == "church" else "Observance")
            ev.append(_ev(f"h{h['date']:%Y%m%d}-{i}", "hol", holiday_label(h["name"], h["day_off"]),
                          h["date"].isoformat(), body=body))
    return ev


def page() -> None:
    from streamlit_calendar import calendar
    c1, c2 = st.columns([1, 3], vertical_alignment="center")
    view = c1.segmented_control("View", list(VIEWS), default="Week", key="cal_view", label_visibility="collapsed")
    names = [k for k, v in LAYERS.items() if v != "bills" or ui.can("money")]
    chosen = c2.pills("Layers", names, selection_mode="multi", key="cal_layers", label_visibility="collapsed",
                      default=[k for k in names if LAYERS[k] in DEFAULT_ON])
    layers = [LAYERS[k] for k in (chosen or [])]
    # A generous window so the calendar's own prev/next buttons have data.
    frm = month_start(today()) - timedelta(days=62)
    to = add_months(month_start(today()), 7) - timedelta(days=1)
    events = calendar_events(frm, to, layers)
    options = {"initialView": VIEWS.get(view or "Week", "timeGridWeek"), "firstDay": 1, "height": 680,
               "headerToolbar": {"left": "prev,next today", "center": "title", "right": ""},
               "nowIndicator": True, "slotMinTime": "06:00:00", "slotMaxTime": "22:00:00", "scrollTime": "07:00:00",
               "allDaySlot": True, "dayMaxEvents": 3, "timeZone": "local", "eventDisplay": "block"}
    res = calendar(events=events, options=options, custom_css=CSS, key=f"cal_{view}_{'-'.join(layers)}")
    clicked = (res or {}).get("eventClick", {}).get("event") if isinstance(res, dict) else None
    if clicked:
        props = clicked.get("extendedProps") or {}
        with st.container(border=True):
            st.markdown(f"**{clicked.get('title', '')}**")
            st.caption(" · ".join(x for x in [clicked.get("start", "")[:16].replace("T", " "), props.get("body", "")] if x))
    st.html('<div class="small sh-muted" style="display:flex;flex-wrap:wrap;gap:.8rem">' + "".join(
        f'<span><span style="display:inline-block;width:10px;height:10px;border-radius:3px;background:'
        f'{CAL_COLORS[LAYERS[k]]};margin-right:.3rem"></span>{k}</span>' for k in names) + "</div>")
