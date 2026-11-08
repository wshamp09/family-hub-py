"""Row widgets shared by Today and the section pages: chores, kids duties, bills, workouts.
Each tick or dropdown saves straight away (on_change callbacks), then the page reruns.
Widget keys include the saved value, so a change made on another phone always shows."""
from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from . import data, db, ui
from .config import FREQS, has_text, today
from .dates import fmt_day, fmt_hhmm, fmt_long_day, fmt_month, money

FREQ_NAMES = {v: k for k, v in FREQS.items()}


def period_label(freq: str, start: date) -> str:
    return {"daily": fmt_day(start), "weekly": f"Week of {fmt_day(start)}", "monthly": fmt_month(start),
            "quarterly": f"Q{(start.month - 1) // 3 + 1} {start.year}", "yearly": str(start.year)}[freq]


def _strike(text: str, done: bool) -> str:
    return f"~~{text}~~" if done else text


# ---- Chores ---------------------------------------------------------------------------------------
def _chore_toggle(key: str, chore_id: int, start: date):
    ui.try_db(data.chore_set_done, None, chore_id, start, st.session_state[key], ui.user()["display_name"])


def chore_row(c: dict, kp: str, show_freq: bool = False, on_edit=None) -> None:
    label = _strike(c["title"], c["done"])
    if show_freq:
        label += " " + ui.md_badge(FREQ_NAMES.get(c["frequency"], c["frequency"]), "light")
    if c.get("optional"):
        label += " " + ui.md_badge("Optional", "light")
    if c["frequency"] in ("monthly", "yearly") and not c["done"]:
        if c["status"] == "overdue":
            label += " " + ui.md_badge("Overdue", "danger")
        elif c["status"] == "soon":
            label += " " + ui.md_badge("Due soon", "warning")
    key = f"{kp}_chore_{c['id']}_{c['period_start']}_{int(c['done'])}"
    cols = st.columns([12, 3] if on_edit else [1], vertical_alignment="center")
    with cols[0]:
        st.checkbox(label, value=c["done"], key=key, on_change=_chore_toggle, args=(key, c["id"], c["period_start"]))
        sub = []
        if c["frequency"] in ("monthly", "yearly"):
            sub.append(f"due {fmt_day(c['due_date'])}")
        if c["done"] and has_text(c.get("done_by")):
            sub.append(f"✓ {c['done_by']}")
        if has_text(c.get("notes")):
            sub.append(c["notes"])
        if sub:
            st.caption(" · ".join(sub))
    if on_edit:
        with cols[1]:
            if st.button(":material/edit:", key=f"{key}_edit", help="Edit"):
                on_edit(c["id"])


# ---- Kids duties --------------------------------------------------------------------------------
def _duty_done(key, did):
    ui.try_db(data.duty_set_done, None, did, st.session_state[key])


def _duty_person(key, did):
    v = st.session_state[key]
    if v == "other":
        st.session_state["_duty_other"] = did
    else:
        ui.try_db(data.duty_set_person, None, did, v)


@st.dialog("Who is covering it?")
def duty_other_dialog(did: int):
    nm = st.text_input("Name", placeholder="e.g. Grandma, neighbor")
    if st.button("Save", type="primary"):
        if not has_text(nm):
            st.warning("Enter a name")
            return
        if ui.try_db(data.duty_set_person, "Saved", did, None, nm.strip()):
            st.session_state.pop("_duty_other", None)
            st.rerun()


def duty_dialogs() -> None:
    """Call once per page that shows duty rows (opens the 'Other…' name box)."""
    did = st.session_state.pop("_duty_other", None)
    if did is not None:
        duty_other_dialog(did)


def duty_row(d: dict, kp: str, show_date: bool = False) -> None:
    has_other = has_text(d.get("other_name"))
    what = " · ".join(x for x in [d["duty_type"], d.get("child") if has_text(d.get("child")) else None] if x)
    sub = [x for x in [fmt_day(d["duty_date"]) if show_date else None,
                       fmt_hhmm(d.get("duty_time")) or None,
                       d.get("location") if has_text(d.get("location")) else None] if x]
    key = f"{kp}_duty_{d['id']}_{int(bool(d['done']))}_{d.get('person_id')}_{has_other}"
    c1, c2 = st.columns([3, 2], vertical_alignment="center")
    with c1:
        st.checkbox(_strike(f"**{what}**", d["done"]), value=bool(d["done"]), key=key,
                    on_change=_duty_done, args=(key, d["id"]))
        extra = []
        if sub:
            extra.append(" · ".join(sub))
        if has_other:
            extra.append(f"Covered by {d['other_name']}")
        if has_text(d.get("notes")):
            extra.append(d["notes"])
        if extra:
            st.caption(" · ".join(extra))
    with c2:
        opts, fmt = ui.person_options(other=True)
        cur = "other" if has_other else d.get("person_id")
        pk = f"{key}_who"
        st.selectbox("Who", opts, index=opts.index(cur) if cur in opts else 0, format_func=fmt, key=pk,
                     label_visibility="collapsed", on_change=_duty_person, args=(pk, d["id"]))


# ---- Bills ------------------------------------------------------------------------------------------
def _bill_paid(key, bid, month):
    if ui.can("money"):
        ui.try_db(data.bill_payment_upsert, None, bid, month, "paid", st.session_state[key])


def _bill_payer(key, bid, month):
    if ui.can("money"):
        ui.try_db(data.bill_payment_upsert, None, bid, month, "payer", st.session_state[key])


def _bill_amount(key, bid, month):
    if ui.can("money"):
        v = st.session_state[key]
        ui.try_db(data.bill_payment_upsert, None, bid, month, "amount", None if v is None else round(float(v), 2))


def bill_status(b: dict, ref: date | None = None) -> tuple[str, str] | None:
    """(label, colour) for a bill's badge."""
    ref = ref or today()
    auto = bool(b.get("autopay"))
    due_soon = not b["paid"] and ref <= b["due_date"] <= ref + timedelta(days=7)
    if b.get("auto_paid"):
        return "Autopay ✓", "success"
    if auto and due_soon:
        return "Due soon · auto", "info"
    if auto:
        return "Autopay", "info"
    if not b["paid"] and b["due_date"] < ref:
        return "Overdue", "danger"
    if due_soon:
        return "Due soon", "warning"
    return None


def bill_row(b: dict, kp: str, month: date, editable_amount: bool = True, on_edit=None) -> None:
    st_ = bill_status(b)
    label = _strike(f"**{b['name']}**", b["paid"]) + (" " + ui.md_badge(*st_) if st_ else "")
    sub = f"Due {fmt_day(b['due_date'])} · {b.get('category') or ''}"
    if b["paid"] and b.get("paid_on") and not b.get("auto_paid"):
        sub += f" · paid {fmt_day(b['paid_on'])}"
    key = f"{kp}_bill_{b['id']}_{month}_{int(b['paid'])}_{b.get('payer_id')}_{b['pay_amount']}"
    c1, c2, c3, c4 = st.columns([5, 2, 2, 1] if on_edit else [5, 2, 2, 0.01], vertical_alignment="center")
    with c1:
        if b.get("autopay"):   # autopay pays itself: show its state, no manual tick
            st.checkbox(label, value=bool(b["paid"]), key=key, disabled=True)
        else:
            st.checkbox(label, value=bool(b["paid"]), key=key, on_change=_bill_paid, args=(key, b["id"], month))
        st.caption(sub)
    with c2:
        if editable_amount:
            ak = f"{key}_amt"
            st.number_input("Amount", value=None if b["pay_amount"] is None else float(b["pay_amount"]),
                            step=1.0, format="%.2f", key=ak, label_visibility="collapsed", placeholder="$",
                            on_change=_bill_amount, args=(ak, b["id"], month))
        else:
            st.markdown(f"**{money(b['pay_amount'])}**")
    with c3:
        opts, fmt = ui.person_options()
        pk = f"{key}_payer"
        cur = b.get("payer_id")
        st.selectbox("Payer", opts, index=opts.index(cur) if cur in opts else 0, format_func=fmt, key=pk,
                     label_visibility="collapsed", on_change=_bill_payer, args=(pk, b["id"], month))
    if on_edit:
        with c4:
            if st.button(":material/edit:", key=f"{key}_edit", help="Edit"):
                on_edit(b["id"])


# ---- Workouts --------------------------------------------------------------------------------------
def _wk_done(key, wid):
    ui.try_db(db.run, None, """update workouts set done = $2::boolean,
                                 done_at = case when $2::boolean then now() end where id = $1""",
              int(wid), bool(st.session_state[key]))


def workout_row(w: dict, kp: str, show_date: bool = False, actions=None) -> None:
    sub = " · ".join(str(x) for x in [
        fmt_day(w["workout_date"]) if show_date else None,
        ui.name_of(w.get("person_id")) or "Unassigned", w.get("workout_type"),
        f"{w['duration_min']} min" if w.get("duration_min") else None, w.get("intensity")] if x)
    key = f"{kp}_wk_{w['id']}_{int(bool(w['done']))}"
    cols = st.columns([5, 1.3, 2.2] if actions else [5, 1.3], vertical_alignment="center")
    with cols[0]:
        st.checkbox(_strike(f"**{w['title']}**", w["done"]), value=bool(w["done"]), key=key,
                    on_change=_wk_done, args=(key, w["id"]))
        st.caption(sub)
    with cols[1]:
        with st.popover("View", use_container_width=True):
            st.markdown(f"**{w['title']}**")
            st.caption(" · ".join(str(x) for x in [fmt_long_day(w["workout_date"]), w.get("workout_type"),
                                                   f"{w['duration_min']} min" if w.get("duration_min") else None,
                                                   w.get("intensity")] if x))
            if has_text(w.get("details")):
                st.markdown(w["details"].replace("\n", "  \n"))
            else:
                ui.empty("No details.")
    if actions:
        with cols[2]:
            actions(w)
