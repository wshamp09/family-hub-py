"""Kids: drop-off / pick-up duties."""
from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from hub import data, db, rows, ui
from hub.config import DUTY_TYPES, has_text, nz, today
from hub.dates import fmt_day, hhmm, parse_hhmm, week_start


def duty_form(p: str, row: dict | None = None, repeat_field: bool = True) -> dict:
    row = row or {}
    ppl = ui.people()
    d = st.date_input("Date", value=row.get("duty_date"), key=f"{p}_date", format="MM/DD/YYYY")
    typ = st.radio("Type", DUTY_TYPES, horizontal=True,
                   index=DUTY_TYPES.index(row["duty_type"]) if row.get("duty_type") in DUTY_TYPES else 0, key=f"{p}_type")
    t = st.time_input("Time (optional)", value=parse_hhmm(row.get("duty_time")), key=f"{p}_time", step=300)
    child = st.text_input("Child", value=row.get("child") or "", key=f"{p}_child")
    loc = st.text_input("Where", value=row.get("location") or "", placeholder="School, daycare, practice…", key=f"{p}_loc")
    opts = [x["id"] for x in ppl] + ["other"]
    names = {x["id"]: x["name"] for x in ppl}
    cur = "other" if has_text(row.get("other_name")) else row.get("person_id")
    who = st.radio("Who's doing it", opts, horizontal=True, index=opts.index(cur) if cur in opts else None,
                   format_func=lambda v: "Other" if v == "other" else names.get(v, "?"), key=f"{p}_who")
    other = st.text_input("Other person's name", value=row.get("other_name") or "", key=f"{p}_other") if who == "other" else None
    notes = st.text_input("Notes", value=row.get("notes") or "", key=f"{p}_notes")
    rep = int(st.number_input("Repeat weekly for how many more weeks?", value=0, min_value=0, max_value=52, step=1,
                              key=f"{p}_repeat")) if repeat_field else 0
    return {"date": d, "type": typ, "time": hhmm(t) or None, "child": nz(child), "loc": nz(loc),
            "person": who if who not in (None, "other") else None, "other": nz(other) if who == "other" else None,
            "notes": nz(notes), "repeat": rep}


def insert_duty(f: dict) -> None:
    for k in range(max(0, f["repeat"]) + 1):
        db.run("""insert into childcare_duties (duty_date, duty_type, duty_time, child, location, person_id, other_name, notes)
                  values ($1::date, $2, $3, $4, $5, $6, $7, $8)""",
               f["date"] + timedelta(days=7 * k), f["type"], f["time"], f["child"], f["loc"], f["person"], f["other"],
               f["notes"])


@st.dialog("Drop-off / pick-up")
def duty_dialog(did=None, day: date | None = None):
    row = db.one("select * from childcare_duties where id = $1", int(did)) if did else {"duty_date": day}
    f = duty_form("dd", row, repeat_field=did is None)
    if st.button("Save" if did else "Add", type="primary", key="dd_save"):
        if f["date"] is None:
            st.warning("Pick a date.")
            return
        if did:
            ok = ui.try_db(db.run, "Saved", """update childcare_duties set duty_date = $2::date, duty_type = $3, duty_time = $4,
                                                child = $5, location = $6, person_id = $7, other_name = $8, notes = $9
                                              where id = $1""",
                           int(did), f["date"], f["type"], f["time"], f["child"], f["loc"], f["person"], f["other"], f["notes"])
        else:
            ok = ui.try_db(insert_duty, f"Added for {f['repeat'] + 1} weeks" if f["repeat"] else "Added", f)
        if ok:
            st.session_state["kids_wk"] = week_start(f["date"])
            st.rerun()


def page() -> None:
    rows.duty_dialogs()
    wk = st.session_state.setdefault("kids_wk", week_start(today()))
    c1, c2, c3, c4 = st.columns([1, 2, 1, 4], vertical_alignment="center")
    if c1.button(":material/chevron_left:", key="kids_prev"):
        st.session_state["kids_wk"] = wk - timedelta(days=7)
        st.rerun()
    if c2.button("This week", key="kids_this"):
        st.session_state["kids_wk"] = week_start(today())
        st.rerun()
    if c3.button(":material/chevron_right:", key="kids_next"):
        st.session_state["kids_wk"] = wk + timedelta(days=7)
        st.rerun()
    c4.markdown(f"**{fmt_day(wk)} – {fmt_day(wk + timedelta(days=6))}**")
    d = data.duties_between(wk, wk + timedelta(days=6))
    for i in range(7):
        day = wk + timedelta(days=i)
        with st.container(border=True):
            h1, h2 = st.columns([6, 1], vertical_alignment="center")
            h1.markdown(("📍 " if day == today() else "") + f"**{fmt_day(day)}**")
            if h2.button("+", key=f"kids_add_{day}", help="Add for this day"):
                duty_dialog(None, day)
            s = [x for x in d if x["duty_date"] == day]
            if not s:
                st.caption("Nothing scheduled")
            for x in s:
                rows.duty_row(x, "kids")
                e1, e2, _ = st.columns([1, 1, 4])
                if e1.button("Edit", key=f"kids_edit_{x['id']}"):
                    duty_dialog(x["id"])
                with e2:
                    ui.confirm_delete("Delete", f"kids_del_{x['id']}", "Delete this duty?", db.run,
                                      "delete from childcare_duties where id = $1", x["id"])
    with st.expander("➕ Add a drop-off / pick-up"):
        f = duty_form("add")
        if st.button("Add", type="primary", key="kids_add"):
            if f["date"] is None:
                st.toast("Pick a date.", icon="ℹ️")
            elif ui.try_db(insert_duty, f"Added for {f['repeat'] + 1} weeks" if f["repeat"] else "Added", f):
                st.session_state["kids_wk"] = week_start(f["date"])
                st.rerun()
    with st.expander("📋 Copy a week"):
        st.caption("Copies every duty from the week shown above into the following week (unticked).")
        if st.button("Copy this week to next week", key="kids_copy"):
            try:
                n = db.run("""insert into childcare_duties (duty_date, duty_type, duty_time, child, location, person_id,
                                                            other_name, notes)
                              select duty_date + 7, duty_type, duty_time, child, location, person_id, other_name, notes
                                from childcare_duties where duty_date between $1::date and $2::date""",
                           wk, wk + timedelta(days=6))
                ui.flash(f"Copied {n} duties to next week")
                st.session_state["kids_wk"] = wk + timedelta(days=7)
                st.rerun()
            except Exception as e:  # noqa: BLE001
                st.error(str(e))
