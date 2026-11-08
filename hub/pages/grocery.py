"""Grocery: the shared shopping list, on its own page for use in the store. The list refreshes
every 10 seconds, so two people can shop together."""
from __future__ import annotations

from datetime import timedelta

import streamlit as st

from hub import data, db, grocery, ui
from hub.config import has_text, today
from hub.dates import text_lines, week_start


def _check(key, gid):
    ui.try_db(db.run, None, "update grocery_items set checked = $2::boolean where id = $1", gid,
              bool(st.session_state[key]))


def _delete(gid):
    ui.try_db(db.run, None, "delete from grocery_items where id = $1", gid)


def grocery_row(g: dict) -> None:
    label = (f"**{g['quantity']}** " if has_text(g.get("quantity")) else "") + g["item"]
    key = f"groc_{g['id']}_{int(g['checked'])}"
    c1, c2 = st.columns([10, 1], vertical_alignment="center")
    with c1:
        st.checkbox(f"~~{label}~~" if g["checked"] else label, value=g["checked"], key=key,
                    on_change=_check, args=(key, g["id"]))
        if has_text(g.get("for_meal")):
            st.caption(f"for {g['for_meal']}")
    c2.button(":material/close:", key=f"gdel_{g['id']}", help="Remove", on_click=_delete, args=(g["id"],))


@st.fragment(run_every="10s")
def grocery_list() -> None:
    g = db.get("select * from grocery_items order by checked, lower(item), id")
    if not g:
        ui.empty("The list is empty.")
        return
    open_, got = [x for x in g if not x["checked"]], [x for x in g if x["checked"]]
    st.caption(f"{len(open_)} to get")
    if not open_:
        ui.empty("All done!")
    for x in open_:
        grocery_row(x)
    if got:
        with st.expander(f"In the cart ({len(got)})"):
            for x in got:
                grocery_row(x)


def add_week(start) -> None:
    p = [m for m in data.meals_between(start, start + timedelta(days=6))
         if not m.get("is_leftovers") and has_text(m.get("ingredients"))]
    if not p:
        st.toast("No planned meals with ingredients that week.", icon="ℹ️")
        return
    res = {"added": 0, "merged": 0}

    def go():
        for m in p:
            r = grocery.add_grocery_items(text_lines(m["ingredients"]), m["meal_name"])
            res["added"] += r["added"]
            res["merged"] += r["merged"]
    if ui.try_db(go):
        ui.flash(f"Added {res['added']} items ({res['merged']} combined with ones already on the list)")


def page() -> None:
    with st.form("grocery_add", clear_on_submit=True, border=False):
        c1, c2 = st.columns([6, 1], vertical_alignment="bottom")
        item = c1.text_input("Add an item", placeholder="Add an item, e.g. 2 lb chicken", label_visibility="collapsed")
        if c2.form_submit_button(":material/add:", type="primary", use_container_width=True) and has_text(item):
            ui.try_db(grocery.add_grocery_items, None, [item.strip()])
    grocery_list()
    st.write("")
    b1, b2, b3, b4 = st.columns(4)
    if b1.button("Add this week's meal ingredients", key="g_this", use_container_width=True):
        add_week(week_start(today()))
    if b2.button("Add next week's", key="g_next", use_container_width=True):
        add_week(week_start(today()) + timedelta(days=7))
    if b3.button("Clear checked", key="g_clear_checked", use_container_width=True):
        ui.try_db(db.run, "Cleared checked items", "delete from grocery_items where checked")
        st.rerun()
    with b4:
        ui.confirm_delete("Clear all", "g_clear_all", "Clear the whole list?", db.run, "delete from grocery_items",
                          success="List cleared", full_width=True)
    st.caption("Matching items are combined (1 onion + 2 onions = 3 onion). The list refreshes every few seconds, "
               "so you can shop together.")
