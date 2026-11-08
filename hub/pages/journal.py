"""Journal/reflection: private daily prompt and entry, past entries and "on this day"."""
from __future__ import annotations

import streamlit as st

from hub import db, journal, ui
from hub.config import has_text, today
from hub.dates import fmt_long_day

esc = ui.esc


def entry_block(e: dict, actions: bool = True) -> None:
    d = e["entry_date"]
    title = fmt_long_day(d) + (f", {d.year}" if d.year != today().year else "")
    c1, c2 = st.columns([8, 1], vertical_alignment="center")
    c1.markdown(f"**{title}**")
    if actions:
        with c2:
            ui.confirm_delete(":material/delete:", f"jdel_{e['id']}", "Delete this entry?", db.run,
                              "delete from journal_entries where id = $1 and user_id = $2::uuid", e["id"],
                              ui.user()["user_id"])
    if has_text(e.get("prompt")):
        st.caption(f"_{e['prompt']}_")
    body = e.get("body") or ""
    if len(body) <= 140:
        st.write(body)
    else:
        with st.expander(body[:140] + "…"):
            st.write(body)


def page() -> None:
    uid = ui.user()["user_id"]
    entry = journal.journal_get(uid, today())
    if "journal_prompt" not in st.session_state:
        st.session_state["journal_prompt"] = (entry["prompt"] if entry and has_text(entry.get("prompt"))
                                              else journal.journal_prompt(uid, today()))
    if "journal_body" not in st.session_state and entry:
        st.session_state["journal_body"] = entry["body"]
    with ui.card("This week's reflection" if journal.is_reflection_day(today()) else "Today's prompt", "notes", "📓"):
        st.caption(fmt_long_day(today()))
        st.html(f'<p class="sh-prompt-text">{esc(st.session_state["journal_prompt"])}</p>')
        c1, c2, c3 = st.columns([2, 2, 2], vertical_alignment="bottom")
        if c1.button("New prompt", icon=":material/refresh:", key="j_next", use_container_width=True):
            with st.spinner("Writing a prompt…"):
                st.session_state["journal_prompt"] = journal.new_journal_prompt(uid, today())
            st.rerun()
        theme = c2.selectbox("Theme", journal.JOURNAL_THEMES, key="j_theme", label_visibility="collapsed")
        if c3.button("Prompt me", icon=":material/auto_awesome:", key="j_ai", use_container_width=True):
            with st.spinner("Writing a prompt…"):
                st.session_state["journal_prompt"] = journal.new_journal_prompt(uid, today(), theme)
            st.rerun()
        body = st.text_area("Entry", height=200, placeholder="Write as much or as little as you like…",
                            key="journal_body", label_visibility="collapsed")
        a, b = st.columns([3, 1], vertical_alignment="center")
        a.caption("Only you can see your journal.")
        if b.button("Save entry", type="primary", icon=":material/save:", key="j_save", use_container_width=True):
            if not has_text(body):
                st.toast("Write something first.", icon="ℹ️")
            else:
                ui.try_db(journal.journal_save, "Saved", uid, today(), st.session_state["journal_prompt"], body.strip())
    otd = journal.journal_on_this_day(uid, today())
    if otd:
        with ui.card("On this day", "notes", "⏳"):
            for e in otd:
                entry_block(e, actions=False)
    with ui.card("Past entries", "notes", "🕰️"):
        term = st.text_input("Search", placeholder="Search your entries", key="j_search", label_visibility="collapsed")
        if has_text(term):
            e = db.get("""select * from journal_entries where user_id = $1::uuid and (body ilike $2 or prompt ilike $2)
                          order by entry_date desc limit 60""", uid, f"%{term.strip()}%")
        else:
            e = db.get("select * from journal_entries where user_id = $1::uuid order by entry_date desc limit 60", uid)
        if not e:
            ui.empty("No matches." if has_text(term) else "Your entries will show here.")
        for x in e:
            entry_block(x)
