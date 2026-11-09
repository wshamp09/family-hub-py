"""Meals: AI ideas -> week plan -> saved library (ingredients go to the Grocery page), plus
what's in season now."""
from __future__ import annotations

import json
from datetime import timedelta

import streamlit as st

from hub import data, db, extras, groq, grocery, seasonal, ui
from hub.config import MEAL_SLOTS, has_text, nz, today
from hub.dates import fmt_day, text_lines, week_start

esc = ui.esc


def household() -> str:
    return db.get_setting("meal_preferences", "")


def ideas() -> list[dict]:
    return st.session_state.setdefault("meal_ideas", [])


def add_ideas(meals: list[dict], source: str, generated: bool = False) -> None:
    """New ideas go on top. A new generated set replaces the last generated set; meals you named stay."""
    n0 = st.session_state.get("meal_uid", 0)
    for k, m in enumerate(meals, 1):
        m["uid"], m["source"], m["generated"] = n0 + k, source, generated
    st.session_state["meal_uid"] = n0 + len(meals)
    keep = [m for m in ideas() if not (generated and m.get("generated"))]
    st.session_state["meal_ideas"] = meals + keep


def drop_idea(uid) -> None:
    st.session_state["meal_ideas"] = [m for m in ideas() if m["uid"] != uid]


def save_to_library(m: dict, source: str) -> int:
    hit = db.one("select id from meals_library where lower(name) = lower($1)", m["name"])
    if hit:
        return hit["id"]
    return db.one("""insert into meals_library (name, description, ingredients, instructions, prep_minutes, healthy, source)
                     values ($1, $2, $3, $4, $5, $6::boolean, $7) returning id""",
                  m["name"], nz(m.get("description")), nz("\n".join(m.get("ingredients") or [])),
                  nz(m.get("instructions")), m.get("prep_minutes"), bool(m.get("healthy")), source)["id"]


def recipe_body(description, ingredients, instructions) -> None:
    ing = text_lines(ingredients)
    if has_text(description):
        st.write(description)
    if ing:
        st.markdown("**Ingredients**\n" + "\n".join(f"- {i}" for i in ing))
    if has_text(instructions):
        st.markdown("**Steps**")
        st.markdown(instructions.replace("\n", "  \n"))
    if not ing and not has_text(instructions):
        ui.empty("No recipe saved for this meal.")


# ---- Dialogs ----------------------------------------------------------------------------------------
@st.dialog("Add to plan")
def plan_dialog(m: dict):
    st.markdown(f"**{m['name']}**")
    d = st.date_input("Day", value=None, key="p_date", format="MM/DD/YYYY")
    slot = st.selectbox("Meal", MEAL_SLOTS, index=MEAL_SLOTS.index("Dinner"), key="p_slot")
    groc = st.checkbox("Add its ingredients to the grocery list", value=True, key="p_grocery") if m.get("ingredients") else False
    if st.button("Add to plan", type="primary", key="p_save"):
        if d is None:
            st.warning("Pick a day.")
            return

        def save():
            db.run("""insert into meal_plan (plan_date, slot, meal_name, library_id, ingredients, instructions)
                      values ($1::date, $2, $3, $4, $5, $6)""",
                   d, slot, m["name"], m.get("library_id"), nz("\n".join(m.get("ingredients") or [])),
                   nz(m.get("instructions")))
            if groc and m.get("ingredients"):
                grocery.add_grocery_items(m["ingredients"], m["name"])
        if ui.try_db(save, f"{m['name']} added to {fmt_day(d)}"):
            if m.get("uid") is not None:
                drop_idea(m["uid"])
            st.session_state["meal_week"] = week_start(d)
            st.rerun()


@st.dialog("Add a meal")
def add_meal_dialog(d):
    st.markdown(f"**{fmt_day(d)}**")
    srcs = {"Type a meal": "custom", "From library": "library", "Leftovers": "leftovers"}
    src = srcs[st.radio("Source", list(srcs), horizontal=True, key="pa_src", label_visibility="collapsed")]
    vals = None
    if src == "custom":
        nm = st.text_input("Meal", key="pa_name")
        vals = (nz(nm), None, None, False, None, None) if has_text(nm) else None
    elif src == "library":
        lib = db.get("select id, name from meals_library order by name")
        if not lib:
            ui.empty("Your library is empty.")
        else:
            pick = st.selectbox("Saved meal", [r["id"] for r in lib], key="pa_lib",
                                format_func=lambda i: next(r["name"] for r in lib if r["id"] == i))
            r = db.one("select * from meals_library where id = $1", pick)
            vals = (r["name"], r["id"], r["ingredients"], False, None, r["instructions"])
    else:
        prev = db.get("""select id, plan_date, meal_name, library_id from meal_plan
                          where not is_leftovers and plan_date between $1::date and $2::date
                          order by plan_date desc""", d - timedelta(days=7), d)
        if not prev:
            ui.empty("No meals planned in the past week.")
        else:
            pick = st.selectbox("Leftovers from", [r["id"] for r in prev], key="pa_left",
                                format_func=lambda i: next(f"{r['meal_name']} ({fmt_day(r['plan_date'])})"
                                                           for r in prev if r["id"] == i))
            o = next(r for r in prev if r["id"] == pick)
            vals = (f"{o['meal_name']} (leftovers)", o["library_id"], None, True, o["id"], None)
    slot = st.selectbox("Meal", MEAL_SLOTS, index=MEAL_SLOTS.index("Dinner"), key="pa_slot")
    notes = st.text_input("Notes (optional)", key="pa_notes")
    if st.button("Add", type="primary", key="pa_save"):
        if not vals or not vals[0]:
            st.warning("Type a meal name." if src == "custom" else "Pick a meal.")
            return
        if ui.try_db(db.run, "Added", """insert into meal_plan (plan_date, slot, meal_name, library_id, ingredients,
                                            is_leftovers, leftover_of_id, notes, instructions)
                                          values ($1::date, $2, $3, $4, $5, $6::boolean, $7, $8, $9)""",
                     d, slot, vals[0], vals[1], vals[2], vals[3], vals[4], nz(notes), vals[5]):
            st.rerun()


@st.dialog("Recipe")
def recipe_dialog(title, description, ingredients, instructions):
    st.subheader(title)
    recipe_body(description, ingredients, instructions)


# ---- Sections ---------------------------------------------------------------------------------------
def run_ideas(seasonal_on: bool) -> bool:
    """Ask the AI for ideas; True when new ideas were added."""
    recent = [r["meal_name"] for r in db.get("select distinct meal_name from meal_plan where plan_date >= $1::date",
                                             today() - timedelta(days=21))]
    season_txt = ""
    if seasonal_on:
        try:
            season_txt = seasonal.produce_prompt(seasonal.seasonal_produce())
        except Exception as e:  # noqa: BLE001
            print("[season]", e)
        if not season_txt:
            st.toast("Couldn't load what's in season; making ideas without it.", icon="ℹ️")
    with st.spinner("Asking the AI for meal ideas…"):
        try:
            res = groq.meal_ideas(n=int(st.session_state.get("n_ideas", 4)), request_text=st.session_state.get("mood", ""),
                                  healthy=st.session_state.get("healthy", True), avoid=st.session_state.get("avoid", ""),
                                  household=household(), recent=recent, seasonal=season_txt)
            if res:
                add_ideas(res, "ai", generated=True)
                return True
            st.warning("The AI didn't return any ideas. Try again.")
        except Exception as e:  # noqa: BLE001
            st.error(str(e))
    return False


def idea_card(m: dict) -> None:
    with st.container(border=True):
        c1, c2 = st.columns([8, 1])
        badges = []
        if m.get("healthy"):
            badges.append(ui.md_badge("Healthy", "success"))
        if m.get("prep_minutes"):
            badges.append(ui.md_badge(f"{m['prep_minutes']} min", "light"))
        if m.get("source") == "manual" and not m.get("ingredients"):
            badges.append(ui.md_badge("No recipe", "light"))
        c1.markdown(f"**{m['name']}**  " + " ".join(badges))
        if c2.button(":material/close:", key=f"idea_x_{m['uid']}", help="Dismiss"):
            drop_idea(m["uid"])
            st.rerun()
        if m.get("description"):
            st.caption(m["description"])
        if m.get("ingredients") or m.get("instructions"):
            with st.popover("Ingredients & steps"):
                recipe_body(None, "\n".join(m.get("ingredients") or []), m.get("instructions"))
        b1, b2 = st.columns(2)
        if b1.button("Add to plan", key=f"idea_plan_{m['uid']}", type="primary", use_container_width=True):
            plan_dialog(m)
        if b2.button("Save to library", key=f"idea_save_{m['uid']}", use_container_width=True):
            ui.try_db(save_to_library, f"{m['name']} saved to library", m, m["source"])


def ideas_section() -> None:
    st.text_input("What are you in the mood for?", placeholder="e.g. chicken, sheet-pan, something cozy", key="mood")
    c1, c2, c3 = st.columns([1, 2, 2], vertical_alignment="bottom")
    c1.selectbox("How many", list(range(1, 8)), index=3, key="n_ideas")
    c2.checkbox("Healthy options only", value=True, key="healthy")
    c3.checkbox("Use what's in season", value=False, key="seasonal")
    st.text_input("Avoid (optional)", placeholder="e.g. mushrooms, pork", key="avoid")
    if st.button("Generate ideas", type="primary", icon=":material/auto_awesome:", key="generate"):
        run_ideas(st.session_state.get("seasonal", False))
    st.caption("or name a meal")
    named = st.text_input("Meal name", placeholder="e.g. Chicken fajitas", key="named", label_visibility="collapsed")
    b1, b2 = st.columns(2)
    if b1.button("Get recipe with AI", key="named_ai", use_container_width=True):
        if not has_text(named):
            st.toast("Type a meal name first.", icon="ℹ️")
        else:
            with st.spinner(f"Getting a recipe for {named}…"):
                try:
                    add_ideas([groq.recipe_for(named.strip(), household(), st.session_state.get("healthy", True))], "ai")
                except Exception as e:  # noqa: BLE001
                    st.error(str(e))
    if b2.button("Add without recipe", key="named_plain", use_container_width=True):
        if not has_text(named):
            st.toast("Type a meal name first.", icon="ℹ️")
        else:
            add_ideas([{"name": named.strip(), "description": "", "prep_minutes": None, "healthy": False,
                        "ingredients": [], "instructions": ""}], "manual")
    if ideas():
        if st.button("Clear ideas", icon=":material/clear_all:", key="ideas_clear"):
            st.session_state["meal_ideas"] = []
            st.rerun()
    for m in ideas():
        idea_card(m)


def season_section() -> None:
    saved = db.get_setting(seasonal.season_key(), "")
    pr = None
    if saved:
        try:
            pr = seasonal.clean_produce(json.loads(saved))
        except (ValueError, RuntimeError):
            pr = None
    if pr is None:
        st.caption("This month's list hasn't been made yet.")
        if st.button("Load this month's produce", key="season_load"):
            with st.spinner("Asking the AI what's in season…"):
                ui.try_db(seasonal.seasonal_produce, None, None, True)
            st.rerun()
        return
    st.html(f'<div class="small sh-muted">In season in {seasonal.SEASON_REGION} this {today():%B}. ⭐ = at its best.</div>')
    for g, label in seasonal.SEASON_GROUPS.items():
        if pr[g]:
            st.html(f'<div class="sh-season-h">{label}</div><div class="sh-produce-list">' + "".join(
                f'<span class="sh-produce">{"⭐ " if x in pr["peak"] else ""}{esc(x)}</span>' for x in pr[g]) + "</div>")
    if pr["tip"]:
        st.caption(f"💡 {pr['tip']}")
    b1, b2 = st.columns(2)
    # Ticking "Use what's in season" from code has to happen in a callback (the box is already drawn above)
    if b1.button("Meal ideas with these", type="primary", key="season_ideas", use_container_width=True,
                 on_click=lambda: st.session_state.update(seasonal=True)):
        if run_ideas(True):
            st.rerun()                  # the ideas list sits above this panel, so draw the page again
    if b2.button("Refresh", icon=":material/refresh:", key="season_refresh", use_container_width=True):
        with st.spinner("Asking the AI what's in season…"):
            ui.try_db(seasonal.seasonal_produce, "Updated", None, True)
        st.rerun()
    st.caption("Written by AI once a month; double-check at the market.")


def _grocery_from_plan(pid):
    r = db.one("select meal_name, ingredients from meal_plan where id = $1", int(pid))
    lines = text_lines(r["ingredients"]) if r else []
    ui.try_db(grocery.add_grocery_items, f"Added {len(lines)} items to the grocery list", lines, r["meal_name"])


def plan_section() -> None:
    wk = st.session_state.setdefault("meal_week", week_start(today()))
    c1, c2, c3, c4 = st.columns([1, 2, 1, 4], vertical_alignment="center")
    if c1.button(":material/chevron_left:", key="w_prev"):
        st.session_state["meal_week"] = wk - timedelta(days=7)
        st.rerun()
    if c2.button("This week", key="w_this"):
        st.session_state["meal_week"] = week_start(today())
        st.rerun()
    if c3.button(":material/chevron_right:", key="w_next"):
        st.session_state["meal_week"] = wk + timedelta(days=7)
        st.rerun()
    c4.markdown(f"**{fmt_day(wk)} – {fmt_day(wk + timedelta(days=6))}**")
    plan = data.meals_between(wk, wk + timedelta(days=6))
    for i in range(7):
        day = wk + timedelta(days=i)
        with st.container(border=True):
            h1, h2 = st.columns([6, 1], vertical_alignment="center")
            h1.markdown(("📍 " if day == today() else "") + f"**{fmt_day(day)}**")
            if h2.button("+", key=f"plan_add_{day}", help="Add a meal"):
                add_meal_dialog(day)
            s = [p for p in plan if p["plan_date"] == day]
            if not s:
                st.caption("—")
            for p in s:
                a, b = st.columns([4, 3], vertical_alignment="center")
                a.markdown(f":gray[{p['slot']}:] {p['meal_name']}"
                           + (" " + ui.md_badge("Leftovers", "warning") if p.get("is_leftovers") else ""))
                if p.get("notes"):
                    a.caption(p["notes"])
                with b:
                    x1, x2, x3 = st.columns(3)
                    if not p.get("is_leftovers") and x1.button("Recipe", key=f"plan_view_{p['id']}"):
                        r = db.one("""select p.meal_name, p.ingredients as p_ing, l.description, l.ingredients,
                                             coalesce(l.instructions, p.instructions) as instructions
                                        from meal_plan p left join meals_library l on l.id = p.library_id
                                       where p.id = $1""", p["id"])
                        recipe_dialog(r["meal_name"], r["description"], r["ingredients"] or r["p_ing"], r["instructions"])
                    if p.get("ingredients"):
                        x2.button(":material/add_shopping_cart:", key=f"plan_groc_{p['id']}", help="Add ingredients to grocery list",
                                  on_click=_grocery_from_plan, args=(p["id"],))
                    with x3:
                        ui.confirm_delete(":material/delete:", f"plan_del_{p['id']}", "Remove this meal from the plan?",
                                          db.run, "delete from meal_plan where id = $1", p["id"], success="Removed")


def library_section() -> None:
    term = st.text_input("Search", placeholder="Search saved meals", key="lib_search", label_visibility="collapsed")
    lib = (db.get("select * from meals_library where name ilike $1 or ingredients ilike $1 order by name",
                  f"%{term.strip()}%") if has_text(term) else db.get("select * from meals_library order by name"))
    if not lib:
        ui.empty("No matches." if has_text(term) else "No saved meals yet. Save ideas you like.")
    for r in lib:
        a, b = st.columns([4, 3], vertical_alignment="center")
        a.markdown(f"**{r['name']}** " + (ui.md_badge("Healthy", "success") if r.get("healthy") else "")
                   + (" " + ui.md_badge(f"{r['prep_minutes']} min", "light") if r.get("prep_minutes") else ""))
        with b:
            x1, x2, x3 = st.columns(3)
            if x1.button("View", key=f"lib_view_{r['id']}"):
                recipe_dialog(r["name"], r["description"], r["ingredients"], r["instructions"])
            if x2.button("Plan", key=f"lib_plan_{r['id']}"):
                plan_dialog({"name": r["name"], "library_id": r["id"], "ingredients": text_lines(r["ingredients"]),
                             "instructions": r["instructions"]})
            with x3:
                ui.confirm_delete(":material/delete:", f"lib_del_{r['id']}", "Delete this meal from the library?",
                                  db.run, "delete from meals_library where id = $1", r["id"])
    if st.toggle("Add your own recipe", key="lib_add_open"):
        nm = st.text_input("Meal name", key="lib_name")
        if "lib_fill" in st.session_state:          # filled in by the AI on the last run
            f = st.session_state.pop("lib_fill")
            st.session_state["lib_ing"], st.session_state["lib_steps"] = f
        ing = st.text_area("Ingredients (one per line)", height=130, key="lib_ing")
        steps = st.text_area("Steps", height=110, key="lib_steps")
        healthy = st.checkbox("Healthy option", value=True, key="lib_healthy")
        b1, b2 = st.columns(2)
        if b1.button("Fill in with AI", key="lib_ai", use_container_width=True):
            if not has_text(nm):
                st.toast("Type the meal name first.", icon="ℹ️")
            else:
                with st.spinner(f"Getting a recipe for {nm}…"):
                    try:
                        res = groq.recipe_for(nm.strip(), household(), healthy)
                        st.session_state["lib_fill"] = ("\n".join(res["ingredients"]), res["instructions"])
                        st.rerun()
                    except Exception as e:  # noqa: BLE001
                        st.error(str(e))
        if b2.button("Save to library", type="primary", key="lib_save", use_container_width=True):
            if not has_text(nm):
                st.toast("Type the meal name.", icon="ℹ️")
            elif ui.try_db(save_to_library, f"{nm.strip()} saved",
                           {"name": nm.strip(), "description": None, "ingredients": text_lines(ing),
                            "instructions": steps or "", "prep_minutes": None, "healthy": healthy}, "manual"):
                for k in ("lib_name", "lib_ing", "lib_steps"):
                    st.session_state.pop(k, None)
                st.rerun()


def recipe_of_day_section() -> None:
    r = extras.get_extra("recipe")
    if not r:
        ui.empty("Today's recipe couldn't be loaded. It will try again in a little while.")
        return
    c1, c2 = st.columns([1, 2])
    c1.image(r["image"], use_container_width=True)
    with c2:
        st.markdown(f"**{r['name']}**")
        if has_text(r.get("meta")):
            st.caption(r["meta"])
        with st.popover("Ingredients & steps"):
            recipe_body(None, "\n".join(r.get("ingredients") or []), r.get("instructions"))
        m = {"name": r["name"], "ingredients": r.get("ingredients") or [], "instructions": r.get("instructions"),
             "description": r.get("meta"), "healthy": False}
        b1, b2 = st.columns(2)
        if b1.button("Add to plan", key="rotd_plan", type="primary", use_container_width=True):
            plan_dialog(m)
        if b2.button("Save to library", key="rotd_save", use_container_width=True):
            ui.try_db(save_to_library, f"{r['name']} saved to library", m, "manual")
        links = [f"[TheMealDB]({r['url']})"] if has_text(r.get("url")) else []
        if has_text(r.get("source")):
            links.append(f"[Original recipe]({r['source']})")
        if has_text(r.get("video")):
            links.append(f"[Video]({r['video']})")
        if links:
            st.caption(" · ".join(links))


def page() -> None:
    with st.expander("🍽️ Recipe of the day", expanded=True):
        recipe_of_day_section()
    with st.expander("✨ Meal ideas", expanded=True):
        ideas_section()
    with st.expander("🥕 In season now"):
        season_section()
    with st.expander("🗓️ Week plan", expanded=True):
        plan_section()
    with st.expander("📚 Meal library"):
        library_section()
