"""Chores: the full list, ticked off each day / week / month / quarter / year."""
from __future__ import annotations

import calendar as _cal

import streamlit as st

from hub import data, db, rows, ui
from hub.config import CHORE_VIEWS, FREQS, has_text, nz, today

MONTHS = list(_cal.month_name)[1:]


@st.dialog("Chore")
def chore_dialog(cid=None):
    row = db.one("select * from chores where id = $1", int(cid)) if cid else {}
    row = row or {}
    title = st.text_input("Chore", value=row.get("title") or "", placeholder="e.g. Change fridge water filter", key="cf_title")
    freq_label = st.selectbox("How often", list(FREQS), index=list(FREQS.values()).index(row.get("frequency") or "weekly"),
                              key="cf_freq")
    freq = FREQS[freq_label]
    due_day = due_month = None
    if freq == "monthly":
        due_day = int(st.number_input("Day of the month", value=int(row.get("due_day") or 1), min_value=1, max_value=31,
                                      step=1, key="cf_mday"))
    elif freq == "yearly":
        c1, c2 = st.columns(2)
        due_month = MONTHS.index(c1.selectbox("Month", MONTHS, index=(row.get("due_month") or 1) - 1, key="cf_ymonth")) + 1
        due_day = int(c2.number_input("Day", value=int(row.get("due_day") or 1), min_value=1, max_value=31, step=1,
                                      key="cf_yday"))
    optional = st.checkbox("Optional (not shown on Today)", value=bool(row.get("optional")), key="cf_optional")
    notes = st.text_area("Notes", value=row.get("notes") or "", height=70, key="cf_notes")
    c1, c2 = st.columns(2)
    if c1.button("Save" if cid else "Add", type="primary", use_container_width=True, key="cf_save"):
        if not has_text(title):
            st.warning("Give the chore a name.")
            return
        if cid:
            ok = ui.try_db(db.run, "Saved", """update chores set title = $2, frequency = $3, due_day = $4, due_month = $5,
                                                optional = $6::boolean, notes = $7 where id = $1""",
                           int(cid), title.strip(), freq, due_day, due_month, optional, nz(notes))
        else:
            ok = ui.try_db(db.run, "Added to the list", """insert into chores (title, frequency, due_day, due_month, optional, notes)
                                                           values ($1, $2, $3, $4, $5::boolean, $6)""",
                           title.strip(), freq, due_day, due_month, optional, nz(notes))
        if ok:
            st.rerun()
    if cid:
        with c2:
            if has_text(row.get("starter_key")):
                if st.button("Hide", use_container_width=True, key="cf_hide"):
                    ui.try_db(db.run, "Hidden (find it under Hidden chores)",
                              "update chores set active = false where id = $1", int(cid))
                    st.rerun()
            else:
                ui.confirm_delete("Delete", "cf_del", "Delete this chore?", db.run,
                                  "delete from chores where id = $1 and starter_key is null", int(cid), full_width=True)


def page() -> None:
    c1, c2, c3, c4 = st.columns([2, 1, 2, 2], vertical_alignment="bottom")
    ref = c1.date_input("Showing chores for", value=today(), key="chores_ref", format="MM/DD/YYYY")
    # Changing the date box from code has to happen in a callback (before the box is drawn on the next run)
    c2.button("Today", key="chores_today", on_click=lambda: st.session_state.update(chores_ref=today()))
    view_label = c3.selectbox("Show", list(CHORE_VIEWS), index=list(CHORE_VIEWS).index("Daily"), key="chores_view")
    if c4.button("Add to list", icon=":material/add:", type="primary", key="chores_add", use_container_width=True):
        chore_dialog()
    st.caption("Tick chores off as they're done. Ticks clear at the start of each day, week, month, quarter or year.")
    view = CHORE_VIEWS[view_label]
    d = data.chores_for_date(ref or today())
    if not d:
        with st.container(border=True):
            ui.empty("No chores yet. Tap 'Add to list'.")
        return
    if view == "due":
        d = [c for c in d if c["frequency"] in ("daily", "weekly") or c["status"] in ("soon", "overdue")]
        if not d:
            with st.container(border=True):
                ui.empty("Nothing due right now.")
    groups = [k for k, v in FREQS.items() if v == view] if view in FREQS.values() else list(FREQS)
    for lbl in groups:
        f = FREQS[lbl]
        s = [c for c in d if c["frequency"] == f]
        if not s:
            if view in FREQS.values():
                with st.container(border=True):
                    ui.empty(f"No {lbl.lower()} chores yet.")
            continue
        s = sorted(s, key=(lambda c: (c["due_date"], c["title"])) if f in ("monthly", "yearly")
                   else (lambda c: (bool(c.get("optional")), c["title"])))
        with st.container(border=True):
            h1, h2 = st.columns([1, 2])
            h1.markdown(f"**{lbl}**")
            h2.caption(f"{sum(c['done'] for c in s)}/{len(s)} · {rows.period_label(f, s[0]['period_start'])}")
            for c in s:
                rows.chore_row(c, "chores", on_edit=chore_dialog)
    hidden = db.get("select id, title, frequency from chores where not active and starter_key is not null order by title")
    if hidden:
        with st.expander(f"Hidden chores ({len(hidden)})"):
            for h in hidden:
                a, b = st.columns([4, 1], vertical_alignment="center")
                a.markdown(f"{h['title']} :gray[· {rows.FREQ_NAMES.get(h['frequency'], h['frequency'])}]")
                if b.button("Show", key=f"unhide_{h['id']}"):
                    ui.try_db(db.run, "Back on the list", "update chores set active = true where id = $1", h["id"])
                    st.rerun()
