"""Bills: this month's checklist of tracked budget expenses. Expenses are added and edited in
Budget (or here); anything with "Track & remind" shows."""
from __future__ import annotations

import streamlit as st

from hub import data, forms, rows, ui
from hub.config import today
from hub.dates import add_months, fmt_month, money, month_start


def page() -> None:
    if not ui.can("money"):
        st.info("Ask an admin to turn on money pages for your login (Settings).")
        return
    mon = st.session_state.setdefault("bills_month", month_start(today()))
    c1, c2, c3, c4, c5 = st.columns([1, 2, 1, 3, 1.5], vertical_alignment="center")
    if c1.button(":material/chevron_left:", key="bills_prev"):
        st.session_state["bills_month"] = add_months(mon, -1)
        st.rerun()
    if c2.button("This month", key="bills_this"):
        st.session_state["bills_month"] = month_start(today())
        st.rerun()
    if c3.button(":material/chevron_right:", key="bills_next"):
        st.session_state["bills_month"] = add_months(mon, 1)
        st.rerun()
    c4.markdown(f"**{fmt_month(mon)}**")
    if c5.button("Add", icon=":material/add:", type="primary", key="bills_add", use_container_width=True):
        forms.expense_dialog(None, {"track": True})
    b = data.bills_for_month(mon)
    total = sum(x["pay_amount"] or 0 for x in b)
    paid = sum(x["pay_amount"] or 0 for x in b if x["paid"])
    with st.container(border=True):
        a, z = st.columns([2, 1])
        a.markdown(f"**{money(paid)} of {money(total)} paid**")
        z.caption(f"{sum(x['paid'] for x in b)} of {len(b)} bills")
        st.progress(paid / total if total > 0 else 0.0)
        for p in ui.people():
            s = [x for x in b if x.get("payer_id") == p["id"]]
            if s:
                l, r = st.columns([3, 1])
                l.markdown(f"**{p['name']}** :gray[{sum(x['paid'] for x in s)}/{len(s)} paid]")
                r.markdown(money(sum(x["pay_amount"] or 0 for x in s)))
    with ui.card("Bills this month"):
        st.caption("Tick when paid. Change the amount or who pays for just this month. "
                   "Autopay bills mark themselves paid after the due day.")
        if not b:
            ui.empty("No tracked bills this month. Tick 'Track & remind' on a budget expense to add one.")
        for x in b:
            rows.bill_row(x, "bills", mon, on_edit=forms.expense_dialog)
