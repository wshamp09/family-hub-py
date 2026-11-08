"""Sign-in: Supabase email + password, remembered on each device for 30 days with a cookie that
holds the refresh token. Streamlit reads cookies natively (st.context.cookies); a tiny script
writes them. Refresh tokens rotate, so the cookie is rewritten every time it's used."""
from __future__ import annotations

import json

import streamlit as st
import streamlit.components.v1 as components

from . import auth, db, starters, verses
from .config import APP_TITLE

COOKIE = "fh_rt"
REMEMBER_DAYS = 30


def cookie_js(name: str, value: str, days: int = REMEMBER_DAYS) -> str:
    """JavaScript that sets (or, with days=0, clears) a cookie on the app's page."""
    c = f"{name}={value}; path=/; max-age={days * 86400}; SameSite=Lax"
    return ("(function(){var c=" + json.dumps(c) + "+(location.protocol==='https:'?'; Secure':'');"
            "try{window.parent.document.cookie=c}catch(e){}try{document.cookie=c}catch(e){}})();")


def _queue_cookie(value: str, days: int) -> None:
    st.session_state["_cookie_js"] = cookie_js(COOKIE, value, days)


def write_pending_cookie() -> None:
    """Call once near the top of every run: writes a queued cookie change."""
    js = st.session_state.pop("_cookie_js", None)
    if js:
        components.html(f"<script>{js}</script>", height=0)


def complete_login(s: dict, remember: bool) -> bool:
    try:
        prof = auth.ensure_profile(s["user_id"], s["email"])
    except Exception as e:  # noqa: BLE001
        print(f"[auth] profile error: {e}")
        st.session_state["_login_msg"] = f"Signed in, but the database is unreachable: {e}"
        return False
    for fn, label in ((starters.ensure_starter_chores, "chores"), (verses.sync_verse_translation, "verse")):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            print(f"[{label}] startup task failed: {e}")
    prof["access_token"] = s["access_token"]
    prof["refresh_token"] = s["refresh_token"]
    st.session_state["user"] = prof
    _queue_cookie(s["refresh_token"] if remember else "", REMEMBER_DAYS if remember else 0)
    st.session_state["_remember"] = remember
    print(f"[auth] signed in: {s['email']}")
    return True


def try_cookie_login() -> None:
    """Once per browser session: sign in with the saved refresh token, if there is one."""
    if st.session_state.get("user") or st.session_state.get("_cookie_tried"):
        return
    st.session_state["_cookie_tried"] = True
    try:
        tok = st.context.cookies.get(COOKIE)
    except Exception:  # noqa: BLE001
        tok = None
    if tok:
        s = auth.refresh_login(tok)
        if s["ok"]:
            complete_login(s, True)
        else:
            _queue_cookie("", 0)


def fresh_access_token() -> str | None:
    """A current access token (they last an hour), refreshing if needed."""
    u = st.session_state.get("user") or {}
    s = auth.refresh_login(u.get("refresh_token", "")) if u.get("refresh_token") else {"ok": False}
    if not s["ok"]:
        return u.get("access_token")
    u["access_token"], u["refresh_token"] = s["access_token"], s["refresh_token"]
    if st.session_state.get("_remember"):
        _queue_cookie(s["refresh_token"], REMEMBER_DAYS)
    return s["access_token"]


def sign_out() -> None:
    for k in list(st.session_state.keys()):
        if k not in ("_cookie_js",):
            del st.session_state[k]
    st.session_state["_cookie_tried"] = True     # don't sign straight back in
    _queue_cookie("", 0)
    st.rerun()


def login_page() -> None:
    st.html(f'<div class="sh-login-head"><img src="app/static/logo.svg" alt=""><h1>{APP_TITLE}</h1></div>')
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        with st.form("login"):
            email = st.text_input("Email", autocomplete="email")
            pw = st.text_input("Password", type="password", autocomplete="current-password")
            remember = st.checkbox("Keep me signed in on this device", value=True)
            ok = st.form_submit_button("Sign in", type="primary", use_container_width=True)
        if ok:
            if not email.strip() or not pw:
                st.session_state["_login_msg"] = "Enter your email and password."
            else:
                s = auth.password_login(email.strip(), pw)
                if not s["ok"]:
                    st.session_state["_login_msg"] = s["message"]
                elif complete_login(s, remember):
                    st.session_state.pop("_login_msg", None)
                    st.rerun()
        msg = st.session_state.get("_login_msg")
        if msg:
            st.error(msg)
        st.caption("Logins are added by an admin in Settings.")


def refresh_user() -> None:
    """Reload the profile (after a name or permission change)."""
    u = st.session_state.get("user")
    if not u:
        return
    p = db.one("""select user_id::text as user_id, email, coalesce(display_name, email) as display_name, person_id,
                         is_admin, can_see_money, can_see_sensitive from app_users where user_id = $1::uuid""",
               u["user_id"])
    if p:
        u.update(p)
