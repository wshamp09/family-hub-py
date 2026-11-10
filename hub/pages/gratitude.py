"""Gratitude jar: today's prompt and notes, a note from the jar, and every note so far."""
from __future__ import annotations

import streamlit as st

from hub import gratitude as g
from hub import ui
from hub.config import has_text, today

esc = ui.esc


def fmt_day(d) -> str:
    return f"{d:%a, %b} {d.day}, {d.year}"


def note_html(n: dict, show_date: bool = True) -> str:
    when = f" · {fmt_day(n['entry_date'])}" if show_date else ""
    prompt = (f'<div class="small sh-muted">{esc(n["prompt"])}</div>' if has_text(n.get("prompt")) else "")
    return (f'<div class="sh-jar-note">{prompt}<div>{esc(n["body"])}</div>'
            f'<div class="who">— {esc(n.get("author_name") or "")}{when}</div></div>')


def today_box(where: str) -> None:
    """Today's prompt, your note (add or edit) and everyone else's note today. Used on Today and the page."""
    u = ui.user()
    day = today()
    prompt = g.prompt_for(day)
    notes = g.notes_on(day)
    mine = next((n for n in notes if str(n["user_id"]) == str(u["user_id"])), None)
    st.html(f'<p class="sh-nudge-prompt" style="margin:0 0 .4rem">{esc(prompt)}</p>')
    editing = st.session_state.get(f"jar_edit_{where}", False)
    if mine and not editing:
        st.html(note_html(mine, show_date=False))
        if st.button("Edit my note", key=f"jar_editbtn_{where}", icon=":material/edit:"):
            st.session_state[f"jar_edit_{where}"] = True
            st.rerun()
    else:
        with st.form(f"jar_form_{where}", clear_on_submit=False, border=False):
            text = st.text_area("Your note", value=(mine or {}).get("body", ""), max_chars=g.GRATITUDE_MAX,
                                key=f"jar_text_{where}_{(mine or {}).get('id', 'new')}",
                                height=80, placeholder="One thing you're grateful for today…",
                                label_visibility="collapsed")
            if st.form_submit_button("Put it in the jar" if not mine else "Save", type="primary"):
                if not text.strip():
                    st.warning("Write a few words first.")
                else:
                    ui.try_db(g.save, "In the jar", u["user_id"], u["display_name"], day, prompt, text)
                    st.session_state[f"jar_edit_{where}"] = False
                    st.rerun()
        st.caption("One note a day each; you and the family can see it.")
    for n in notes:
        if mine is None or n["id"] != mine["id"]:
            st.html(note_html(n, show_date=False))


def page() -> None:
    with ui.card("Today", "notes", "🫙"):
        today_box("page")

    with ui.card("From the jar", "kids", "✨"):
        pick = st.session_state.get("jar_shaken") or g.from_the_jar(today())
        if pick:
            st.html(note_html(pick))
            if st.button("Shake the jar", key="jar_shake", icon=":material/casino:"):
                st.session_state["jar_shaken"] = g.shake(today(), pick["id"]) or pick
                st.rerun()
        else:
            ui.empty("Notes from earlier days will show up here.")

    with ui.card("All notes", "appt", "📜"):
        c1, c2 = st.columns([2, 1])
        q = c1.text_input("Search", key="jar_q", placeholder="Search notes", label_visibility="collapsed")
        opts = {"Everyone": None}
        uid = ui.user()["user_id"]
        opts[f"Just me ({ui.user()['display_name']})"] = uid
        who = opts[c2.selectbox("Who", list(opts), key="jar_who", label_visibility="collapsed")]
        rows = g.search(q, who)
        if not rows:
            ui.empty("No notes yet." if not q else "Nothing matches that search.")
        st.caption(f"{len(rows)} note{'s' if len(rows) != 1 else ''}" + (" (latest 200)" if len(rows) == 200 else ""))
        for n in rows:
            a, b = st.columns([8, 1], vertical_alignment="center")
            a.html(note_html(n))
            if str(n["user_id"]) == str(uid):
                with b:
                    ui.confirm_delete(":material/delete:", f"jar_del_{n['id']}", "Delete this note?", g.delete, n["id"], uid,
                                      success="Deleted")
