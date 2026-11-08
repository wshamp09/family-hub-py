"""Learn: today's short lessons (grown-ups and kids), the word of the day, and a knowledge check."""
from __future__ import annotations

import streamlit as st

from hub import extras, learn, ui
from hub.config import has_text, today

esc = ui.esc


def md_safe(x: str) -> str:
    """Plain text for st.markdown: '$' would otherwise start a maths formula."""
    return (x or "").replace("\\", "\\\\").replace("$", "\\$")


def word_html(wd: dict) -> str:
    det = ""
    if has_text(wd.get("pron")) or has_text(wd.get("origin")):
        det = ('<details class="small" style="margin-top:.25rem"><summary>Pronunciation and origin</summary>'
               + (f'<div><strong>Say it:</strong> {esc(wd["pron"])}</div>' if has_text(wd.get("pron")) else "")
               + (f'<div>{esc(wd["origin"])}</div>' if has_text(wd.get("origin")) else "") + "</details>")
    return (f'<div class="sh-extra-text"><span class="sh-word">{esc(wd["word"])}</span>'
            + (f'<span class="sh-word-pos">{esc(wd["pos"])}</span>' if has_text(wd.get("pos")) else "") + "</div>"
            + (f'<div class="sh-extra-text">{esc(wd["definition"])}</div>' if has_text(wd.get("definition")) else "")
            + (f'<div class="sh-extra-text sh-word-ex">{esc(wd["example"])}</div>' if has_text(wd.get("example")) else "")
            + det + f'<div class="small sh-muted">From <a href="{esc(wd.get("url") or "https://www.merriam-webster.com/word-of-the-day")}"'
                    ' target="_blank" rel="noopener">Merriam-Webster\'s Word of the Day</a></div>')


def lesson_card(l: dict, track: str, done: bool, uid: str) -> None:
    label, emoji, sec, _ = learn.LEARN_SUBJECTS.get(l["subject"], (l["subject"].title(), "📘", "appt", ""))
    with st.container(border=True):
        if has_text(l.get("image")):
            st.image(l["image"], use_container_width=True)
        ui.head(label, sec, emoji)
        st.markdown(f"**{md_safe(l['title'])}**")
        if has_text(l.get("hook")):
            st.caption(md_safe(l["hook"]))
        st.markdown(ui.md_badge(f"{l['minutes']} min", "light") + ("  " + ui.md_badge("✓ Read", "success") if done else ""))
        with st.expander("Read" if not done else "Read again"):
            st.markdown(md_safe(l["body"]))
            st.caption(f"Based on the Wikipedia article [{md_safe(l['article'])}]({l['url']}) (CC BY-SA)."
                       if has_text(l.get("url")) else "Based on Wikipedia.")
            if not done and st.button("✓ Done reading", key=f"learn_read_{track}_{l['subject']}", type="primary"):
                ui.try_db(learn.mark_read, None, uid, today(), track, l["subject"])
                st.rerun()


def quiz_section(day_data: dict, track: str, log: dict, uid: str) -> None:
    qs = day_data.get("quiz") or []
    if not qs:
        return
    with ui.card("Daily knowledge check", "chores", "🧠"):
        right = 0
        for i, q in enumerate(qs):
            st.markdown(f"**{i + 1}. {md_safe(q['question'])}**")
            got = log.get(f"q{i}")
            if got is not None and got.get("answer") is not None:
                for j, c in enumerate(q["choices"]):
                    mark = "✅" if j == q["answer"] else ("❌" if j == got["answer"] else "▫️")
                    st.markdown(f"{mark} {md_safe(c)}")
                right += bool(got.get("correct"))
                if has_text(q.get("why")):
                    st.caption(md_safe(q["why"]))
            else:
                pick = st.radio("Answer", q["choices"], index=None, key=f"learn_q_{track}_{i}",
                                label_visibility="collapsed")
                if st.button("Check", key=f"learn_check_{track}_{i}", disabled=pick is None) and pick in q["choices"]:
                    k = q["choices"].index(pick)
                    ui.try_db(learn.answer, None, uid, today(), track, i, k, k == q["answer"])
                    st.rerun()
        answered = sum(1 for i in range(len(qs)) if (log.get(f"q{i}") or {}).get("answer") is not None)
        if answered == len(qs):
            st.success(f"{right} of {len(qs)} right today.")


def page() -> None:
    uid = ui.user()["user_id"]
    c1, c2 = st.columns([3, 2], vertical_alignment="center")
    tlabel = c1.segmented_control("Track", list(learn.LEARN_TRACKS.values()), default="Grown-ups",
                                  key="learn_track", label_visibility="collapsed") or "Grown-ups"
    track = next(k for k, v in learn.LEARN_TRACKS.items() if v == tlabel)
    n = learn.streak(uid, today())
    c2.markdown(f"🔥 **{n}-day streak**" if n > 1 else ("🔥 **Started today**" if n == 1 else "Read one to start a streak"))
    if track == "kids":
        st.caption("Short read-aloud lessons, with something to try together at the end.")

    day = learn.saved_day(track, today())
    if not day:
        with st.status("Writing today's lessons (about 20 seconds, once a day)…", expanded=True) as s:
            day = learn.get_day(track, today(), progress=s.write)
            s.update(label="Today's lessons are ready" if day else "Couldn't write today's lessons",
                     state="complete" if day else "error", expanded=False)
    if not day:
        ui.empty("Today's lessons couldn't be written right now (Wikipedia or the AI may be busy). "
                 "It will try again in about 30 minutes.")
        return

    log = learn.log_for(uid, today(), track)
    lessons = day["lessons"]
    cols = st.columns(2)
    for i, l in enumerate(lessons):
        with cols[i % 2]:
            lesson_card(l, track, l["subject"] in log, uid)
    if track == "adult":
        wd = extras.get_extra("word")
        if wd:
            with cols[len(lessons) % 2]:
                with ui.card("Vocabulary", "bills", "📖"):
                    st.html(word_html(wd))
    quiz_section(day, track, log, uid)
