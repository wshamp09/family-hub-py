"""Quick add: the floating "+" for adding things from any page."""
from __future__ import annotations

import streamlit as st

from hub import db, forms, grocery, ui
from hub.config import MEAL_SLOTS, has_text, today
from hub.dates import fmt_day

QUICK = {"🔔 Reminder": "reminder", "📅 Appointment": "appointment", "🗒️ Note": "note",
         "🛒 Grocery item": "grocery", "🍽️ Meal": "meal"}
NOTE_COLORS = {"🟨": "yellow", "🩷": "pink", "🟦": "blue", "🟩": "green", "🟪": "purple"}

FAB_CSS = """<style>
.st-key-quick_fab { position: fixed; right: 18px; bottom: 24px; z-index: 999; width: auto !important; }
.st-key-quick_fab button { width: 56px; height: 56px; border-radius: 50% !important; font-size: 1.5rem;
  background: #2E7D6B; color: #fff; border: 0; box-shadow: 0 6px 16px -6px rgba(31,92,79,.6); }
.st-key-quick_fab button:hover { background: #1F5C4F; color: #fff; }
</style>"""


@st.dialog("Add")
def quick_dialog():
    pick = st.segmented_control("What", list(QUICK), key="q_kind", label_visibility="collapsed")
    kind = QUICK.get(pick)
    if not kind:
        st.caption("Pick what to add.")
        return
    by = ui.user()["display_name"]
    if kind in ("reminder", "appointment"):
        f = forms.appt_form(f"qa_{kind}", kind=kind)
        if st.button("Add", type="primary", key="q_save_appt"):
            msg = forms.check_appt(f)
            if msg:
                st.warning(msg)
            elif ui.try_db(forms.appt_save, "Added", f, None, by):
                st.rerun()
    elif kind == "note":
        body = st.text_area("Note", height=90, placeholder="Write a note…", key="q_note", label_visibility="collapsed")
        col = st.segmented_control("Color", list(NOTE_COLORS), default="🟨", key="q_color", label_visibility="collapsed")
        if st.button("Add", type="primary", key="q_save_note"):
            if not has_text(body):
                st.warning("Write something first.")
            elif ui.try_db(db.run, "Note added", "insert into notes (author, body, color) values ($1, $2, $3)",
                           by, body.strip(), NOTE_COLORS.get(col or "🟨", "yellow")):
                st.rerun()
    elif kind == "grocery":
        it = st.text_input("Items", placeholder="e.g. 2 lb chicken, milk", key="q_item", label_visibility="collapsed")
        if st.button("Add", type="primary", key="q_save_groc"):
            if not has_text(it):
                st.warning("Type an item.")
            elif ui.try_db(grocery.add_grocery_items, "Added to the grocery list", [x.strip() for x in it.split(",")]):
                st.rerun()
    elif kind == "meal":
        m = st.text_input("Meal", placeholder="e.g. Tacos", key="q_meal")
        c1, c2 = st.columns(2)
        d = c1.date_input("Day", value=today(), key="q_day", format="MM/DD/YYYY")
        slot = c2.selectbox("Meal", MEAL_SLOTS, index=MEAL_SLOTS.index("Dinner"), key="q_slot")
        if st.button("Add", type="primary", key="q_save_meal"):
            if not has_text(m) or d is None:
                st.warning("Add the meal and the day.")
            elif ui.try_db(db.run, f"{m.strip()} added to {fmt_day(d)}",
                           "insert into meal_plan (plan_date, slot, meal_name) values ($1::date, $2, $3)",
                           d, slot, m.strip()):
                st.rerun()


def fab() -> None:
    """The round "+" button in the corner of every page."""
    st.html(FAB_CSS)
    if st.button(":material/add:", key="quick_fab", help="Quick add"):
        quick_dialog()
