"""Sign-in: Supabase email + password, remembered on each device for 30 days.

The saved sign-in (a Supabase refresh token) is kept in the browser's own storage by a tiny component
(hub/device_store/index.html) that reports it to the app over Streamlit's live connection. Cookies can't be
used: Streamlit Community Cloud removes them before the app sees them.

Refresh tokens rotate (each one works once). So whenever one is used, the new one is saved straight away:
the change is queued, the app reruns, and the component (drawn at the top of every run) writes it and
confirms it. A change stays queued until the component confirms it."""
from __future__ import annotations

import uuid
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from . import auth, db, starters, verses
from .config import APP_TITLE

STORE_KEY = "fh_store"            # the component's value in session_state: {"token", "ok", "write_id"}
REMEMBER_DAYS = 30                # a saved sign-in is forgotten after this many days without a visit
_store_component = components.declare_component("fh_device_store", path=str(Path(__file__).parent / "device_store"))


def store_write(token: str, only_if: str | None = None) -> None:
    """Queue saving (or, with "", forgetting) the sign-in on this device."""
    st.session_state["_store_write"] = {"token": token, "only_if": only_if, "write_id": uuid.uuid4().hex}


def pending_write(value: dict | None, queued: dict | None) -> dict | None:
    """The queued change still to send, or None once the component has confirmed it. Pure, for tests."""
    if queued and value and value.get("write_id") == queued["write_id"]:
        return None
    return queued


def render_store() -> None:
    """Draw the component (once, at the top of every run), passing any change still to be saved."""
    w = pending_write(st.session_state.get(STORE_KEY), st.session_state.get("_store_write"))
    if w is None:
        st.session_state.pop("_store_write", None)
    _store_component(key=STORE_KEY, default=None, days=REMEMBER_DAYS,
                     **(w or {"token": None, "only_if": None, "write_id": None}))


def complete_login(s: dict, remember: bool) -> bool:
    # Save the new token first: the old one has just been used up, even if the rest of sign-in fails.
    store_write(s["refresh_token"] if remember else "")
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
    st.session_state["_remember"] = remember
    print(f"[auth] signed in: {s['email']}")
    return True


def saved_login_state(value: dict | None, user, skip: bool, tried: str | None) -> tuple[str, str]:
    """What to do about the saved sign-in: ("wait", "") until the device has reported, ("none", "") if
    there's nothing (new) to try, or ("try", token). Pure, for tests."""
    if user:
        return "none", ""
    if value is None:
        return ("none", "") if skip else ("wait", "")
    tok = str(value.get("token") or "")
    if not tok or tok == tried:
        return "none", ""
    return "try", tok


def try_saved_login() -> str:
    """Sign in with this device's saved sign-in. Returns "wait" while the device hasn't reported yet."""
    what, tok = saved_login_state(st.session_state.get(STORE_KEY), st.session_state.get("user"),
                                  bool(st.session_state.get("_skip_saved")), st.session_state.get("_tried_tok"))
    if what != "try":
        return what
    st.session_state["_tried_tok"] = tok
    s = auth.refresh_login(tok)
    if s["ok"]:
        complete_login(s, True)
        st.rerun()                      # saves the new token straight away (and shows the app)
    elif s.get("status") in (400, 401, 403):
        # Supabase says the saved sign-in is no longer valid: forget it (unless another tab replaced it)
        print(f"[auth] saved sign-in no longer valid: {s['message']}")
        store_write("", only_if=tok)
        st.rerun()
    else:
        # Supabase couldn't be reached: keep the saved sign-in and try again on the next run
        print(f"[auth] couldn't check saved sign-in: {s['message']}")
        st.session_state.pop("_tried_tok", None)
        st.session_state["_login_msg"] = "Couldn't reach the sign-in service. Reload in a moment, or sign in below."
    return "none"


def waiting_page() -> None:
    """Shown for a moment while the device reports its saved sign-in."""
    st.html(f'<div class="sh-login-head"><img src="app/static/logo.svg" alt=""><h1>{APP_TITLE}</h1></div>')
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        st.caption("Signing you in…")
        if st.button("Sign in with email instead", key="skip_saved", use_container_width=True):
            st.session_state["_skip_saved"] = True
            st.rerun()


def fresh_access_token() -> str | None:
    """A current access token (they last an hour), refreshing if needed."""
    u = st.session_state.get("user") or {}
    s = auth.refresh_login(u.get("refresh_token", "")) if u.get("refresh_token") else {"ok": False}
    if not s["ok"]:
        return u.get("access_token")
    u["access_token"], u["refresh_token"] = s["access_token"], s["refresh_token"]
    if st.session_state.get("_remember"):
        store_write(s["refresh_token"])
    return s["access_token"]


def sign_out() -> None:
    tok = str((st.session_state.get(STORE_KEY) or {}).get("token") or "")
    for k in list(st.session_state.keys()):
        if k != STORE_KEY:
            del st.session_state[k]
    st.session_state["_tried_tok"] = tok        # don't sign straight back in while it's being forgotten
    store_write("")
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
