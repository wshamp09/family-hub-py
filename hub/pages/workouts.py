"""Workouts: generate with AI or add manually, assign to a person, tick when done."""
from __future__ import annotations

from datetime import timedelta

import streamlit as st

from hub import db, groq, rows, ui
from hub.config import EQUIPMENT, INTENSITIES, WORKOUT_TYPES, nz, today
from hub.dates import fmt_day, month_start, week_start


def workout_form(p: str, row: dict | None = None, multi: bool = True) -> dict:
    row = row or {}
    ppl = ui.people()
    names = {x["id"]: x["name"] for x in ppl}
    title = st.text_input("Workout", value=row.get("title") or "", placeholder="e.g. 3-mile easy run", key=f"{p}_title")
    c1, c2 = st.columns(2)
    t0 = row.get("workout_type") or row.get("type") or "Run"
    typ = c1.selectbox("Type", WORKOUT_TYPES, index=WORKOUT_TYPES.index(t0) if t0 in WORKOUT_TYPES else 0, key=f"{p}_type")
    mins = int(c2.number_input("Minutes", value=int(row.get("duration_min") or 30), min_value=5, step=5, key=f"{p}_min"))
    inten = st.radio("Intensity", INTENSITIES, horizontal=True,
                     index=INTENSITIES.index(row["intensity"]) if row.get("intensity") in INTENSITIES else 1, key=f"{p}_int")
    d = st.date_input("Day", value=row.get("workout_date"), key=f"{p}_date", format="MM/DD/YYYY")
    if multi:
        who = st.pills("For", list(names), selection_mode="multi", format_func=lambda v: names[v], key=f"{p}_who") or []
    else:
        ids = list(names)
        w = st.radio("For", ids, horizontal=True, format_func=lambda v: names[v],
                     index=ids.index(row["person_id"]) if row.get("person_id") in ids else None, key=f"{p}_who")
        who = [w] if w is not None else []
    details = st.text_area("Details", value=row.get("details") or "", height=170, key=f"{p}_details")
    return {"title": nz(title), "type": typ, "minutes": mins, "intensity": inten, "date": d, "who": who,
            "details": nz(details)}


@st.dialog("Workout", width="large")
def add_dialog(row: dict | None, source: str):
    f = workout_form("wf", row, multi=True)
    st.caption("Pick both people to add a copy for each.")
    if st.button("Add", type="primary", key="wf_save"):
        if not f["title"]:
            st.warning("Name the workout.")
            return
        if f["date"] is None:
            st.warning("Pick a day.")
            return
        if not f["who"]:
            st.warning("Pick who it's for.")
            return

        def save():
            for pid in f["who"]:
                db.run("""insert into workouts (workout_date, person_id, title, workout_type, duration_min, intensity,
                                                details, source)
                          values ($1::date, $2, $3, $4, $5, $6, $7, $8)""",
                       f["date"], pid, f["title"], f["type"], f["minutes"], f["intensity"], f["details"], source)
        if ui.try_db(save, f"Added for {fmt_day(f['date'])}"):
            if source == "ai":
                st.session_state.pop("wk_draft", None)
            st.session_state["wo_wk"] = week_start(f["date"])
            st.rerun()


@st.dialog("Edit workout", width="large")
def edit_dialog(wid: int):
    row = db.one("select * from workouts where id = $1", wid)
    f = workout_form("we", row, multi=False)
    if st.button("Save", type="primary", key="we_save"):
        if not f["title"] or f["date"] is None:
            st.warning("Name and day are required.")
            return
        if ui.try_db(db.run, "Saved", """update workouts set workout_date = $2::date, person_id = $3, title = $4,
                                           workout_type = $5, duration_min = $6, intensity = $7, details = $8 where id = $1""",
                     wid, f["date"], f["who"][0] if f["who"] else None, f["title"], f["type"], f["minutes"],
                     f["intensity"], f["details"]):
            st.rerun()


def _generate():
    with st.spinner("Building your workout…"):
        try:
            eq = [e for e in (st.session_state.get("g_equip") or []) if e != "None (bodyweight)"]
            st.session_state["wk_draft"] = groq.workout(st.session_state["g_type"], int(st.session_state["g_min"]),
                                                        st.session_state["g_int"], eq, st.session_state.get("g_focus", ""))
        except Exception as e:  # noqa: BLE001
            st.error(str(e))


def _actions(w):
    a, b = st.columns(2)
    if a.button("Edit", key=f"wo_edit_{w['id']}"):
        edit_dialog(w["id"])
    with b:
        ui.confirm_delete(":material/delete:", f"wo_del_{w['id']}", "Delete this workout?", db.run,
                          "delete from workouts where id = $1", w["id"])


def page() -> None:
    # ---- Counts: workouts done this week and month, per person ----
    ws, ms = week_start(today()), month_start(today())
    d = {r["person_id"]: r for r in db.get("""select person_id,
            count(*) filter (where workout_date between $1::date and $1::date + 6) as week_n,
            count(*) filter (where workout_date >= $2::date and workout_date < ($2::date + interval '1 month')) as month_n
          from workouts where done group by person_id""", ws, ms)}
    ppl = ui.people()
    if ppl:
        cols = st.columns(min(4, len(ppl)))
        for i, p in enumerate(ppl):
            r = d.get(p["id"], {})
            cols[i % len(cols)].metric(p["name"], f"{int(r.get('week_n') or 0)} this week",
                                       f"{int(r.get('month_n') or 0)} this month", delta_color="off")
    with st.expander("✨ Generate a workout", expanded=True):
        c1, c2 = st.columns(2)
        c1.selectbox("Type", WORKOUT_TYPES, key="g_type")
        c2.selectbox("Time (min)", list(range(10, 95, 5)), index=4, key="g_min")
        st.radio("Intensity", INTENSITIES, index=1, horizontal=True, key="g_int")
        st.pills("Equipment", EQUIPMENT, selection_mode="multi", default=["None (bodyweight)"], key="g_equip")
        st.text_input("Focus or avoid (optional)", placeholder="e.g. upper body, go easy on knees", key="g_focus")
        if st.button("Generate", type="primary", icon=":material/auto_awesome:", key="g_go"):
            _generate()
        w = st.session_state.get("wk_draft")
        if w:
            with st.container(border=True):
                st.markdown(f"**{w['title']}**")
                st.caption(f"{w['type']} · {w['duration_min']} min · {w['intensity']}")
                st.markdown(w["details"].replace("\n", "  \n"))
                b1, b2 = st.columns(2)
                if b1.button("Edit & add", type="primary", key="draft_add", use_container_width=True):
                    add_dialog({"title": w["title"], "workout_type": w["type"], "duration_min": w["duration_min"],
                                "intensity": w["intensity"], "details": w["details"]}, "ai")
                if b2.button("Try another", key="draft_again", use_container_width=True):
                    _generate()
                    st.rerun()
    wk = st.session_state.setdefault("wo_wk", week_start(today()))
    c1, c2, c3, c4, c5 = st.columns([1, 2, 1, 3, 2], vertical_alignment="center")
    if c1.button(":material/chevron_left:", key="wo_prev"):
        st.session_state["wo_wk"] = wk - timedelta(days=7)
        st.rerun()
    if c2.button("This week", key="wo_this"):
        st.session_state["wo_wk"] = week_start(today())
        st.rerun()
    if c3.button(":material/chevron_right:", key="wo_next"):
        st.session_state["wo_wk"] = wk + timedelta(days=7)
        st.rerun()
    c4.markdown(f"**{fmt_day(wk)} – {fmt_day(wk + timedelta(days=6))}**")
    if c5.button("Add manually", icon=":material/add:", type="primary", key="wo_manual", use_container_width=True):
        add_dialog(None, "manual")
    w = db.get("select * from workouts where workout_date between $1::date and $2::date order by workout_date, id",
               wk, wk + timedelta(days=6))
    for i in range(7):
        day = wk + timedelta(days=i)
        with st.container(border=True):
            st.markdown(("📍 " if day == today() else "") + f"**{fmt_day(day)}**")
            s = [x for x in w if x["workout_date"] == day]
            if not s:
                st.caption("Rest day")
            for x in s:
                rows.workout_row(x, "wo", actions=_actions)
