"""Notes: shared sticky-note board (pin, done, reply, delete, colours)."""
from __future__ import annotations

from datetime import datetime

import streamlit as st

from hub import db, ui
from hub.config import has_text, now
from hub.dates import fmt_day

NOTE_COLORS = {"Yellow": "yellow", "Pink": "pink", "Blue": "blue", "Green": "green", "Purple": "purple"}
SWATCH = {"yellow": "#fff3a8", "pink": "#ffd6e5", "blue": "#d4ebff", "green": "#d9f5d3", "purple": "#e8dcff"}
DOT = {"yellow": "🟨", "pink": "🩷", "blue": "🟦", "green": "🟩", "purple": "🟪"}
esc = ui.esc


def time_ago(t: datetime) -> str:
    secs = (now() - t).total_seconds()
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)} min ago"
    if secs < 86400:
        return f"{int(secs // 3600)} h ago"
    return fmt_day(t.date())


@st.dialog("Reply")
def reply_dialog(nid: int):
    body = st.text_area("Reply", height=100, key="reply_body", label_visibility="collapsed")
    if st.button("Reply", type="primary", key="reply_save"):
        if not has_text(body):
            st.warning("Write something first.")
        elif ui.try_db(db.run, None, "insert into notes (parent_id, author, body) values ($1, $2, $3)",
                       nid, ui.user()["display_name"], body.strip()):
            st.rerun()


def _recolor(nid, cur):
    vals = list(NOTE_COLORS.values())
    nxt = vals[(vals.index(cur) + 1) % len(vals)] if cur in vals else "pink"
    ui.try_db(db.run, None, "update notes set color = $2 where id = $1", nid, nxt)


def note_card(n: dict, replies: list[dict]) -> None:
    col = n["color"] if n.get("color") in SWATCH else "yellow"
    rep = "".join(f'<div class="fh-reply">{esc(r["body"])}<div class="fh-sticky-meta">— {esc(r.get("author") or "Someone")}, '
                  f'{time_ago(r["created_at"])}</div></div>' for r in replies)
    st.html(f'<div class="fh-sticky fh-note-{col}{" fh-sticky-done" if n.get("done") else ""}">'
            f'{"<div>📌</div>" if n.get("pinned") else ""}<div class="fh-sticky-body">{esc(n["body"])}</div>{rep}'
            f'<div class="fh-sticky-meta">— {esc(n.get("author") or "Someone")}, {time_ago(n["created_at"])}</div></div>')
    with st.popover("⋯", help="Note actions"):
        if st.button("Unpin" if n.get("pinned") else "📌 Pin", key=f"pin_{n['id']}", use_container_width=True):
            ui.try_db(db.run, None, "update notes set pinned = not pinned where id = $1", n["id"])
            st.rerun()
        if st.button("Mark not done" if n.get("done") else "✓ Mark done", key=f"done_{n['id']}", use_container_width=True):
            ui.try_db(db.run, None, "update notes set done = not done where id = $1", n["id"])
            st.rerun()
        if st.button("🎨 Change color", key=f"color_{n['id']}", use_container_width=True):
            _recolor(n["id"], n.get("color"))
            st.rerun()
        if st.button("↩ Reply", key=f"reply_{n['id']}", use_container_width=True):
            reply_dialog(n["id"])
        for r in replies:
            if st.button(f"Delete reply: {r['body'][:24]}…", key=f"delr_{r['id']}", use_container_width=True):
                ui.try_db(db.run, "Deleted", "delete from notes where id = $1", r["id"])
                st.rerun()
        st.divider()
        if st.button("🗑 Delete note", key=f"del_{n['id']}", use_container_width=True):
            ui.try_db(db.run, "Deleted", "delete from notes where id = $1", n["id"])
            st.rerun()


def page() -> None:
    color = st.session_state.get("note_color_pick", "Yellow") or "Yellow"
    st.html(f"<style>.st-key-note_composer div[data-testid='stVerticalBlockBorderWrapper'],"
            f".st-key-note_composer {{background:{SWATCH[NOTE_COLORS[color]]} !important;border-radius:4px 4px 14px 4px}}"
            f".st-key-note_composer textarea {{font-family:'Outfit',sans-serif;font-size:1.1rem;background:transparent}}</style>")
    with st.container(key="note_composer", border=True):
        body = st.text_area("Note", placeholder="Write a note…", height=100, key="note_body", label_visibility="collapsed")
        c1, c2 = st.columns([3, 1], vertical_alignment="center")
        c1.segmented_control("Color", list(NOTE_COLORS), default="Yellow", key="note_color_pick",
                             format_func=lambda k: DOT[NOTE_COLORS[k]], label_visibility="collapsed")
        if c2.button("Stick it", type="primary", key="note_post", use_container_width=True):
            if has_text(body):
                if ui.try_db(db.run, None, "insert into notes (author, body, color) values ($1, $2, $3)",
                             ui.user()["display_name"], body.strip(), NOTE_COLORS[color]):
                    st.session_state.pop("note_body", None)
                    st.rerun()
    show_done = st.toggle("Show done", value=False, key="notes_show_done")
    d = db.get("select * from notes order by pinned desc, created_at desc")
    top = [n for n in d if n.get("parent_id") is None and (show_done or not n.get("done"))]
    if not top:
        ui.empty("No notes yet. Write the first one above.")
        return
    for i in range(0, len(top), 3):
        cols = st.columns(3)
        for c, n in zip(cols, top[i:i + 3]):
            with c:
                rp = sorted([r for r in d if r.get("parent_id") == n["id"]], key=lambda r: r["created_at"])
                note_card(n, rp)
