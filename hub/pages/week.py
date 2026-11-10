"""Week ahead: one screen for planning the coming week."""
from __future__ import annotations

from datetime import timedelta

import streamlit as st

from hub import db, forms, ui
from hub import week as weekmod
from hub.config import today
from hub.dates import fmt_day, fmt_long_day, money, week_start

esc = ui.esc


def page() -> None:
    # Friday to Sunday it opens on next week; otherwise on this week.
    default = week_start(today()) + timedelta(days=7 if today().isoweekday() >= 5 else 0)
    ws = st.session_state.setdefault("week_ws", default)
    c1, c2, c3, c4 = st.columns([1, 2, 2, 4], vertical_alignment="center")
    if c1.button(":material/chevron_left:", key="wk_prev"):
        st.session_state["week_ws"] = ws - timedelta(days=7)
        st.rerun()
    if c2.button("This week", key="wk_this"):
        st.session_state["week_ws"] = week_start(today())
        st.rerun()
    if c3.button("Next week", key="wk_next"):
        st.session_state["week_ws"] = week_start(today()) + timedelta(days=7)
        st.rerun()
    c4.markdown(f"**{fmt_day(ws)} – {fmt_day(ws + timedelta(days=6))}**")

    w = weekmod.week_data(ws)
    g = weekmod.week_gaps(w)
    planned = db.get_setting(weekmod.week_planned_key(ws), "") == "yes"
    with st.container(border=True):
        if g:
            st.markdown("**Still to plan**\n" + "\n".join(f"- {x}" for x in g))
        else:
            st.markdown("✅ **Nothing missing. This week is planned.**")
        b1, b2, b3, b4 = st.columns(4)
        with b1:
            ui.go_button("meals", "Plan meals", "wk_meals")
        with b2:
            ui.go_button("kids", "Kids duties", "wk_kids")
        with b3:
            ui.go_button("workouts", "Workouts", "wk_workouts")
        if planned:
            b4.markdown(ui.md_badge("Marked planned", "success"))
        elif b4.button("Week planned", icon=":material/check:", type="primary", key="wk_planned"):
            ui.try_db(db.set_setting, "Marked as planned", weekmod.week_planned_key(ws), "yes")
            st.rerun()

    ppl = ui.people()
    for i in range(7):
        day = ws + timedelta(days=i)
        hol = [h for h in (w["holidays"] or []) if h["date"] == day]
        chips = "".join(f'<span class="sh-holiday-chip">⭐ {esc(h["name"])}'
                        + ('<span class="sh-holiday-off">Day off</span>' if h["day_off"] else "") + "</span>" for h in hol)
        chips += "".join(f'<span class="sh-holiday-chip sh-count-chip">{esc(c["emoji"])} {esc(c["title"])}</span>'
                         for c in (w.get("countdowns") or []) if c["event_date"] == day)
        lines = []
        dinner = [m for m in w["meals"] if m["plan_date"] == day and m["slot"] == "Dinner"]
        lines.append("🍽️ " + (", ".join(esc(m["meal_name"]) for m in dinner) if dinner
                              else '<span style="color:#8A5A00">No dinner planned</span>'))
        for m in [m for m in w["meals"] if m["plan_date"] == day and m["slot"] != "Dinner"]:
            lines.append(f'🍽️ <span class="sh-muted">{m["slot"]}:</span> {esc(m["meal_name"])}')
        from hub.data import duty_who
        from hub.dates import fmt_hhmm
        for d in [d for d in w["duties"] if d["duty_date"] == day]:
            who = duty_who(d, ppl)
            bits = " · ".join(x for x in [d["duty_type"], d.get("child"), fmt_hhmm(d.get("duty_time"))] if x)
            lines.append(f"🧒 {esc(bits)} – " + ('<span style="color:#8A5A00">no one assigned</span>'
                                                 if who == "Unassigned" else esc(who)))
        for a in [a for a in w["appts"] if a["occ_date"] == day]:
            lines.append(f'{"🔔" if a["kind"] == "reminder" else "📅"} {esc(a["title"])} '
                         f'<span class="sh-muted">· {esc(forms.appt_when(a))}</span>')
        for c in [c for c in w["chores"] if c["due_date"] == day]:
            lines.append(f'🧹 <span class="{"sh-done" if c["done"] else ""}">{esc(c["title"])}</span>')
        for x in [x for x in w["workouts"] if x["workout_date"] == day]:
            lines.append(f'🏃 {esc(x["title"])} <span class="sh-muted">· {esc(ui.name_of(x["person_id"]) or "?")}</span>')
        if ui.can("money"):
            for b in [b for b in w["bills"] if b["due_date"] == day]:
                tail = " · autopay" if b.get("autopay") else f" · {ui.name_of(b['payer_id']) or 'no payer'}"
                lines.append(f'💳 {esc(b["name"])} <span class="sh-muted">· {money(b["pay_amount"])}{esc(tail)}</span>')
        border = "border-left:4px solid #F2A33A;" if day == today() else ""
        st.html(f'<div style="background:#fff;border:1px solid #E9DCCB;{border}border-radius:16px;padding:.6rem .9rem;'
                f'margin-bottom:.5rem"><div style="font-family:var(--sh-head);font-weight:700">{fmt_long_day(day)}{chips}</div>'
                + "".join(f'<div style="padding:.15rem 0">{l}</div>' for l in lines) + "</div>")
