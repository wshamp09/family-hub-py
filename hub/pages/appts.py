"""Appointments & reminders, with repeats and .ics export for phone calendars."""
from __future__ import annotations



import streamlit as st

from hub import data, db, forms, ics, ui
from hub.config import APP_TZ, today
from hub.dates import fmt_day


def upcoming() -> list[dict]:
    """Overdue reminders, then each item's next date (repeats shown once)."""
    t0 = today()
    a = db.get("""select * from appointments
                  where recurrence <> 'none'
                     or (kind = 'appointment' and start_at >= ($1::date::timestamp at time zone $2))
                     or (kind = 'reminder' and not done)""", t0, APP_TZ)
    for r in a:
        r["start_at"] = forms._local(r["start_at"])
        r["end_at"] = forms._local(r.get("end_at"))
        r["next_date"] = r["start_at"].date()
        if r["recurrence"] != "none" and r["kind"] == "appointment":
            d = data.next_occurrence(r["next_date"], r["recurrence"], t0)
            r["start_at"], r["end_at"] = data.shift_to_date(r["start_at"], r["end_at"], d)
            r["next_date"] = d
    return sorted(a, key=lambda r: (r["next_date"], r["start_at"]))


def past() -> list[dict]:
    a = db.get("""select * from appointments
                  where (recurrence = 'none' and kind = 'appointment'
                         and start_at < ($1::date::timestamp at time zone $2)
                         and start_at >= (($1::date - 90)::timestamp at time zone $2))
                     or (recurrence = 'none' and kind = 'reminder' and done)
                  order by start_at desc limit 100""", today(), APP_TZ)
    for r in a:
        r["start_at"] = forms._local(r["start_at"])
        r["end_at"] = forms._local(r.get("end_at"))
        r["next_date"] = r["start_at"].date()
    return a


def _actions(r):
    a, b, c = st.columns(3)
    a.download_button(".ics", data=ics.calendar([db.one("select * from appointments where id = $1", r["id"])]),
                      file_name=f"family-hub-{r['id']}.ics", mime="text/calendar", key=f"ics_{r['id']}_{r['next_date']}")
    if b.button("Edit", key=f"aedit_{r['id']}_{r['next_date']}"):
        forms.appt_dialog(r["id"])
    with c:
        ui.confirm_delete(":material/delete:", f"adel_{r['id']}_{r['next_date']}",
                          "Delete this item and all its repeats?" if r["recurrence"] != "none" else "Delete this item?",
                          db.run, "delete from appointments where id = $1", r["id"])


def all_ics() -> str:
    rows = db.get("""select * from appointments where recurrence <> 'none' or start_at >= ($1::date::timestamp at time zone $2)
                     order by start_at""", today(), APP_TZ)
    return ics.calendar([r for r in rows if not (r["kind"] == "reminder" and r["done"])])


def page() -> None:
    c1, c2, _ = st.columns([1, 1, 2])
    if c1.button("Appointment", icon=":material/add:", type="primary", key="ap_new", use_container_width=True):
        forms.appt_dialog(None, "appointment")
    if c2.button("Reminder", icon=":material/add:", key="ap_rem", use_container_width=True):
        forms.appt_dialog(None, "reminder")
    r1, r2 = st.columns([2, 1], vertical_alignment="center")
    rng = r1.segmented_control("Show", ["Upcoming", "Past & done"], default="Upcoming", key="ap_range",
                               label_visibility="collapsed") or "Upcoming"
    r2.download_button("Export upcoming (.ics)", data=all_ics(), mime="text/calendar", use_container_width=True,
                       file_name=f"family-appointments-{today():%Y%m%d}.ics", key="ics_all")
    a = upcoming() if rng == "Upcoming" else past()
    if not a:
        with st.container(border=True):
            ui.empty("Nothing here yet.")
    t0 = today()
    groups = {}
    for r in a:
        g = "Overdue" if (rng == "Upcoming" and r["next_date"] < t0) else fmt_day(r["next_date"])
        groups.setdefault(g, []).append(r)
    for g, s in groups.items():
        with st.container(border=True):
            st.markdown(("🔴 " if g == "Overdue" else "📍 " if s[0]["next_date"] == t0 else "") + f"**{g}**")
            for r in s:
                forms.appt_row(r, "appts", show_date=g == "Overdue", actions=_actions)
    st.caption("Tap .ics to add an item to your phone's calendar; repeating items come through as a repeating series. "
               "Re-adding an edited item updates the copy already in your calendar on most apps.")
