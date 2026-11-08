"""Ask AI: general-questions chat, private to each login."""
from __future__ import annotations

import streamlit as st

from hub import db, groq, ui
from hub.dates import fmt_day

MAX_THREADS = 20      # saved chats kept per person
MAX_HISTORY = 20      # messages sent back to the AI for context


def page() -> None:
    uid = ui.user()["user_id"]
    threads = db.get("""select id, title, updated_at from chat_threads where user_id = $1::uuid
                        order by updated_at desc limit $2""", uid, MAX_THREADS)
    opts = [None] + [t["id"] for t in threads]
    names = {t["id"]: f"{t['title']} · {fmt_day(t['updated_at'].date())}" for t in threads}
    cur = st.session_state.get("ask_thread")
    if cur not in opts:
        cur = None
    c1, c2, c3 = st.columns([5, 2, 1], vertical_alignment="bottom")
    pick = c1.selectbox("Chat", opts, index=opts.index(cur), format_func=lambda v: "New chat" if v is None else names[v],
                        key=f"ask_pick_{cur}", label_visibility="collapsed")
    if pick != cur:
        st.session_state["ask_thread"] = pick
        st.rerun()
    if c2.button("New chat", icon=":material/add:", key="ask_new", use_container_width=True):
        st.session_state["ask_thread"] = None
        st.rerun()
    if cur is not None:
        with c3:
            ui.confirm_delete(":material/delete:", "ask_del", "Delete this chat?", db.run,
                              "delete from chat_threads where id = $1 and user_id = $2::uuid", cur, uid)
    msgs = db.get("""select m.role, m.content from chat_messages m join chat_threads t on t.id = m.thread_id
                     where m.thread_id = $1 and t.user_id = $2::uuid order by m.id""", cur, uid) if cur else []
    if not msgs:
        st.caption('Ask a question to start. e.g. "Rainy-day activities for a 4-year-old" or '
                   '"How do I get crayon off a wall?"')
    for m in msgs:
        with st.chat_message("user" if m["role"] == "user" else "assistant"):
            st.markdown(m["content"])     # Streamlit doesn't render raw HTML from the model
    q = st.chat_input("Ask anything: recipes, kids' activities, how-tos, ideas…")
    st.caption("Private to you. Answers come from AI and can be wrong.")
    if q and q.strip():
        q = q.strip()
        th = cur
        if th is None:
            title = q if len(q) <= 48 else q[:45] + "…"
            th = db.one("insert into chat_threads (user_id, title) values ($1::uuid, $2) returning id", uid, title)["id"]
            st.session_state["ask_thread"] = th
        db.run("insert into chat_messages (thread_id, role, content) values ($1, 'user', $2)", th, q)
        with st.chat_message("user"):
            st.markdown(q)
        hist = db.get("""select role, content from (select id, role, content from chat_messages where thread_id = $1
                         order by id desc limit $2) x order by id""", th, MAX_HISTORY)
        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                try:
                    reply = groq.chat_reply(hist)
                except Exception as e:  # noqa: BLE001
                    st.error(str(e))
                    reply = None
        if reply:
            db.run("insert into chat_messages (thread_id, role, content) values ($1, 'assistant', $2)", th, reply)
            db.run("update chat_threads set updated_at = now() where id = $1", th)
            # keep only the newest MAX_THREADS chats for this person
            db.run("""delete from chat_threads where user_id = $1::uuid and id not in
                        (select id from chat_threads where user_id = $1::uuid order by updated_at desc limit $2)""",
                   uid, MAX_THREADS)
        st.rerun()
