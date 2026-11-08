"""Look and feel (the warm "Shamp House" theme) and small UI helpers shared by every page."""
from __future__ import annotations

import html
import traceback
from contextlib import contextmanager

import streamlit as st

from . import data

# Section chips: one tint per section (same colours as the R app)
SECTIONS = {
    "appt": ("#DCE9F8", "#2B62A6"), "meals": ("#DDF1E3", "#2B7346"), "notes": ("#FFF0B3", "#8A6A00"),
    "kids": ("#FDE3CF", "#B35A1F"), "chores": ("#D8EFEC", "#1F6E66"), "work": ("#F7DFE8", "#A63E66"),
    "bills": ("#EAE1F6", "#6C4A9E"),
}

FONT_URL = "app/static/fonts"

CSS = """
@font-face { font-family: "Bricolage Grotesque"; font-weight: 400; font-display: swap;
  src: url("%(f)s/BricolageGrotesque-Regular.ttf") format("truetype"); }
@font-face { font-family: "Bricolage Grotesque"; font-weight: 700; font-display: swap;
  src: url("%(f)s/BricolageGrotesque-Bold.ttf") format("truetype"); }
@font-face { font-family: "Work Sans"; font-weight: 400; font-display: swap;
  src: url("%(f)s/WorkSans-Regular.ttf") format("truetype"); }
@font-face { font-family: "Work Sans"; font-weight: 400; font-style: italic; font-display: swap;
  src: url("%(f)s/WorkSans-Italic.ttf") format("truetype"); }
@font-face { font-family: "Work Sans"; font-weight: 600 700; font-display: swap;
  src: url("%(f)s/WorkSans-Bold.ttf") format("truetype"); }
@font-face { font-family: "Outfit"; font-weight: 400; font-display: swap;
  src: url("%(f)s/Outfit-Regular.ttf") format("truetype"); }
@font-face { font-family: "Outfit"; font-weight: 600 700; font-display: swap;
  src: url("%(f)s/Outfit-Bold.ttf") format("truetype"); }

:root {
  --sh-sand: #F6EEE3; --sh-paper: #FFFFFF; --sh-line: #E9DCCB; --sh-ink: #23363A; --sh-muted: #63706C;
  --sh-palm: #2E7D6B; --sh-palm-deep: #1F5C4F; --sh-sun: #F2A33A; --sh-sun-soft: #FFE9C6;
  --sh-head: "Bricolage Grotesque", "Work Sans", system-ui, sans-serif;
  --sh-body: "Work Sans", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --sh-note: "Outfit", "Work Sans", system-ui, sans-serif;
}

/* ---- Streamlit base ------------------------------------------------------------------- */
html, body, .stApp, [data-testid="stAppViewContainer"] { background: var(--sh-sand); color: var(--sh-ink);
  font-family: var(--sh-body); }
.stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea, .stApp button, .stApp select,
[data-testid="stMarkdownContainer"] { font-family: var(--sh-body); }
h1, h2, h3, h4, h5, h6, [data-testid="stHeading"] * { font-family: var(--sh-head) !important;
  font-weight: 700 !important; letter-spacing: -0.01em; color: var(--sh-ink); }
.block-container { padding-top: 3.2rem; padding-bottom: 5rem; max-width: 1100px; }
@media (max-width: 640px) { .block-container { padding-left: 1rem; padding-right: 1rem; padding-top: 3rem; } }
[data-testid="stCaptionContainer"], .stCaption { color: var(--sh-muted) !important; }

/* Cards: bordered containers */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) { border-radius: 16px; }
div[data-testid="stVerticalBlockBorderWrapper"] { background: var(--sh-paper); border-color: var(--sh-line) !important;
  border-radius: 16px !important; }
.st-key-plain div[data-testid="stVerticalBlockBorderWrapper"] { background: transparent; }

/* Buttons and inputs */
.stButton button, .stDownloadButton button, .stFormSubmitButton button, .stLinkButton a, [data-testid="stPopover"] button {
  border-radius: 999px !important; font-weight: 600; }
.stButton button[kind="primary"], .stFormSubmitButton button[kind="primaryFormSubmit"] { background: var(--sh-palm);
  border-color: var(--sh-palm); }
.stButton button[kind="primary"]:hover { background: var(--sh-palm-deep); border-color: var(--sh-palm-deep); }
.stTextInput input, .stNumberInput input, .stTextArea textarea, .stDateInput input, .stTimeInput input,
[data-baseweb="select"] > div { border-radius: 12px !important; }
[data-testid="stCheckbox"] label p { font-size: 1rem; }
[data-testid="stExpander"] details { border-radius: 16px; border-color: var(--sh-line); background: var(--sh-paper); }
[data-testid="stExpander"] summary p { font-family: var(--sh-head); font-weight: 700; }
[data-testid="stMetric"] { background: var(--sh-paper); border: 1px solid var(--sh-line); border-radius: 16px;
  padding: .6rem .9rem; }

/* ---- Card header with a coloured section chip ------------------------------------------- */
.sh-head { display: flex; align-items: center; gap: .55rem; font-family: var(--sh-head); font-weight: 700;
  font-size: 1.08rem; margin: .1rem 0 .2rem; }
.sh-chip { display: inline-flex; align-items: center; justify-content: center; width: 30px; height: 30px;
  border-radius: 10px; font-size: .95rem; flex-shrink: 0; }
.sh-muted { color: var(--sh-muted); font-size: .88rem; }
.sh-empty { color: var(--sh-muted); font-style: italic; padding: .2rem 0; }
.sh-badge { display: inline-block; border-radius: 999px; font-weight: 600; font-size: .75rem; padding: .05rem .55rem;
  margin-left: .3rem; vertical-align: middle; }
.sh-done { text-decoration: line-through; color: var(--sh-muted); }

/* ---- The porch: Today's greeting and weather ---------------------------------------------- */
.sh-porch { position: relative; background: var(--sh-sun-soft); border-radius: 24px; padding: 1.2rem 1.25rem 2.4rem;
  margin-bottom: .5rem; overflow: hidden; }
.sh-porch::after { content: ""; position: absolute; left: 0; right: 0; bottom: 0; height: 26px;
  background: url("data:image/svg+xml,%%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 400 26' preserveAspectRatio='none'%%3E%%3Cpath d='M0 12 C50 2 100 22 150 12 S250 2 300 12 S370 20 400 10 V26 H0Z' fill='%%23F2A33A' fill-opacity='.28'/%%3E%%3Cpath d='M0 18 C60 10 110 26 170 17 S280 9 330 18 S385 24 400 17 V26 H0Z' fill='%%232E7D6B' fill-opacity='.22'/%%3E%%3C/svg%%3E") no-repeat bottom / 100%% 100%%; }
.sh-porch-top { display: flex; justify-content: space-between; gap: 1rem; align-items: flex-start; }
.sh-hello { font-family: var(--sh-head); font-weight: 700; font-size: 1.9rem; line-height: 1.05; margin: 0; padding: 0; }
.sh-date { color: #6B5A3E; margin-top: .3rem; font-size: .95rem; }
.sh-wx { text-align: right; flex-shrink: 0; }
.sh-wx-now { display: flex; align-items: center; gap: .45rem; justify-content: flex-end; }
.sh-wx-icon { font-size: 1.7rem; }
.sh-wx-temp { font-family: var(--sh-head); font-weight: 700; font-size: 2.1rem; line-height: 1; }
.sh-wx-range { font-size: .85rem; color: #6B5A3E; margin-top: .2rem; }
.sh-wx-hilo { font-weight: 700; color: var(--sh-ink); }
.sh-wx-notes { display: flex; flex-wrap: wrap; gap: .4rem; margin-top: .9rem; }
.sh-wx-note { background: rgba(255,255,255,.7); border-radius: 999px; padding: .2rem .7rem; font-size: .85rem; }
.sh-days { display: grid; grid-template-columns: repeat(5, 1fr); gap: .35rem; margin-top: .9rem; }
.sh-day { background: rgba(255,255,255,.6); border-radius: 14px; padding: .45rem .2rem; text-align: center; }
.sh-day-name { font-size: .78rem; font-weight: 600; color: #6B5A3E; }
.sh-day-icon { font-size: 1.05rem; margin: .15rem 0; }
.sh-day-temp { font-size: .9rem; line-height: 1.1; }
.sh-day-lo { color: var(--sh-muted); margin-left: .2rem; }
.sh-day-rain { font-size: .72rem; color: #2B62A6; margin-top: .1rem; }
.sh-sun { display: flex; gap: 1rem; flex-wrap: wrap; font-size: .82rem; color: #6B5A3E; margin-top: .7rem; }
.sh-moon-next { color: #8A7A5E; }
.sh-holiday { margin-top: .35rem; font-weight: 600; color: #8A5A0B; font-size: .95rem; }
.sh-holiday-chip { display: inline-flex; align-items: center; gap: .25rem; margin-left: .5rem; font-size: .82rem;
  font-weight: 600; color: #8A5A0B; background: #FCEFD6; border-radius: 999px; padding: .1rem .6rem; }
.sh-holiday-off { margin-left: .4rem; font-size: .72rem; font-weight: 700; text-transform: uppercase; letter-spacing: .03em;
  background: #C98512; color: #fff; border-radius: 999px; padding: .05rem .5rem; }
@media (max-width: 575.98px) {
  .sh-porch-top { flex-direction: column; gap: .75rem; }
  .sh-wx { text-align: left; display: flex; align-items: center; gap: .75rem; }
  .sh-wx-now { justify-content: flex-start; }
  .sh-hello { font-size: 1.75rem; }
}

/* ---- School run ------------------------------------------------------------------------------ */
.sh-traffic { display: flex; gap: .8rem; align-items: flex-start; background: var(--sh-paper);
  border: 1px solid var(--sh-line); border-left: 4px solid var(--sh-palm); border-radius: 16px;
  padding: .75rem .9rem; margin: 0 0 .5rem; }
.sh-traffic.is-heavy { border-left-color: #E07B2E; background: #FFF4E8; }
.sh-traffic-icon { font-size: 1.3rem; padding-top: .1rem; }
.sh-traffic-warn { color: #C2621C; font-weight: 600; }
.sh-traffic-body { flex: 1; min-width: 0; }
.sh-traffic-top { display: flex; justify-content: space-between; gap: .5rem; align-items: baseline; }
.sh-traffic-map { font-size: .85rem; white-space: nowrap; }
.sh-traffic-min { font-family: var(--sh-head); font-weight: 700; font-size: 1.35rem; }
.sh-traffic-sub { font-size: .85rem; color: #6B5A3E; margin-top: .2rem; }

/* ---- Verse ------------------------------------------------------------------------------------ */
.fh-verse { background: var(--sh-paper); border: 1px solid var(--sh-line); border-left: 4px solid var(--sh-sun);
  border-radius: 16px; padding: .8rem 1rem; }
.fh-verse-text { font-style: italic; font-size: 1.08rem; line-height: 1.55; }
.fh-verse-ref { font-weight: 700; margin-top: .3rem; }

/* ---- Today's extras ---------------------------------------------------------------------------- */
.sh-extra { display: flex; gap: .7rem; align-items: flex-start; padding: .55rem 0; border-bottom: 1px solid #F1E8DC; }
.sh-extra:last-child { border-bottom: 0; }
.sh-extra-label { font-weight: 700; font-size: .88rem; color: var(--sh-muted); }
.sh-extra-text { font-size: .97rem; line-height: 1.45; }
.sh-extra-text + .sh-extra-text { margin-top: .3rem; }
.sh-extra a { color: var(--sh-palm-deep); font-weight: 600; }
.sh-animal { display: flex; gap: .75rem; align-items: flex-start; margin-top: .15rem; }
.sh-animal-img { width: 92px; height: 92px; object-fit: cover; border-radius: 14px; flex-shrink: 0;
  background: var(--sh-sand); border: 1px solid var(--sh-line); }
.sh-quote { font-style: italic; font-size: 1.02rem; }
.sh-word { font-family: var(--sh-head); font-weight: 700; font-size: 1.15rem; }
.sh-word-pos { font-style: italic; color: #6B5A3E; margin-left: .45rem; font-size: .9rem; }
.sh-word-ex { font-style: italic; color: #4A5A5D; margin-top: .25rem; }
.sh-art { display: flex; gap: .8rem; align-items: flex-start; }
.sh-art-img { width: 120px; max-height: 160px; object-fit: cover; border-radius: 10px; flex-shrink: 0;
  box-shadow: 0 1px 4px rgba(0,0,0,.12); }
@media (max-width: 575.98px) { .sh-art { flex-direction: column; } .sh-art > a { display: block; width: 100%%; }
  .sh-art-img { width: 100%%; max-height: 280px; } }
.sh-pies { display: flex; flex-wrap: wrap; gap: 1rem; }
.sh-pie { display: flex; align-items: center; gap: .55rem; }
.sh-trivia-q { font-weight: 600; margin: .2rem 0 .4rem; }
.sh-trivia-result { border-radius: 12px; padding: .5rem .75rem; margin-top: .3rem; }
.sh-trivia-right { background: #D7EFE3; color: #1F6B47; }
.sh-trivia-wrong { background: #FBD9D3; color: #A3322A; }

/* ---- Journal ------------------------------------------------------------------------------------ */
.sh-nudge { display: flex; align-items: flex-start; gap: .75rem; background: var(--sh-paper);
  border: 1px solid var(--sh-line); border-radius: 16px; padding: .75rem 1rem; margin-bottom: .5rem; }
.sh-nudge.is-year { background: #FFF0B3; border-color: #F1DE8A; }
.sh-nudge-prompt { font-family: var(--sh-head); font-weight: 700; font-size: 1.05rem; line-height: 1.25; }
.sh-prompt-text { font-family: var(--sh-head); font-weight: 700; font-size: 1.35rem; line-height: 1.25; margin: 0 0 .8rem; }

/* ---- Sticky notes ----------------------------------------------------------------------------- */
.fh-sticky { position: relative; background: var(--note, #fff3a8); border-radius: 4px 4px 14px 4px;
  padding: 1rem .9rem .6rem; min-height: 120px; box-shadow: 0 6px 14px -8px rgba(60,45,20,.35);
  font-family: var(--sh-note); margin-bottom: .2rem; }
.fh-sticky::before { content: ""; position: absolute; top: -9px; left: 50%%; width: 64px; height: 18px;
  transform: translateX(-50%%) rotate(-2deg); background: rgba(255,255,255,.55); border-radius: 2px; }
.fh-sticky-body { font-family: var(--sh-note); font-size: 1.12rem; line-height: 1.35; color: #26231D;
  white-space: pre-wrap; word-wrap: break-word; }
.fh-sticky-meta { font-size: .78rem; color: rgba(38,35,29,.68); margin-top: .5rem; font-family: var(--sh-body); }
.fh-sticky-done .fh-sticky-body { text-decoration: line-through; opacity: .6; }
.fh-reply { font-family: var(--sh-note); font-size: 1rem; border-top: 1px dashed rgba(0,0,0,.15); margin-top: .4rem;
  padding-top: .3rem; }
.fh-note-yellow { --note: #fff3a8; } .fh-note-pink { --note: #ffd6e5; } .fh-note-blue { --note: #d4ebff; }
.fh-note-green { --note: #d9f5d3; } .fh-note-purple { --note: #e8dcff; }

/* ---- Photos, produce ------------------------------------------------------------------------- */
.sh-photo-star { display: inline-block; background: #FFF3D6; color: #B7791F; border-radius: 999px;
  padding: .05rem .6rem; font-size: .8rem; font-weight: 600; }
.sh-produce-list { display: flex; flex-wrap: wrap; gap: .35rem; margin-bottom: .5rem; }
.sh-produce { background: #EEF6F1; color: var(--sh-ink); border-radius: 999px; padding: .15rem .65rem; font-size: .88rem; }
.sh-season-h { font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; color: #6B5A3E; margin: .2rem 0 .3rem; }

/* ---- Sign-in ------------------------------------------------------------------------------------ */
.sh-login-head { text-align: center; margin: 1.5rem 0 1rem; }
.sh-login-head img { width: 64px; height: 64px; }
.sh-login-head h1 { margin: .4rem 0 0; font-size: 1.8rem; }
""" % {"f": FONT_URL}


def inject_css() -> None:
    st.html(f"<style>{CSS}</style>")


# ---- Small building blocks ------------------------------------------------------------------------
def esc(x) -> str:
    return html.escape("" if x is None else str(x))


def chip(sec: str, emoji: str) -> str:
    bg, ink = SECTIONS.get(sec, ("#EEE", "#333"))
    return f'<span class="sh-chip" style="background:{bg};color:{ink}">{emoji}</span>'


def head(title: str, sec: str | None = None, emoji: str = "", extra: str = "") -> None:
    st.html(f'<div class="sh-head">{chip(sec, emoji) if sec else ""}<span>{esc(title)}</span>{extra}</div>')


@contextmanager
def card(title: str | None = None, sec: str | None = None, emoji: str = "", key: str | None = None):
    """A white rounded card with an optional header (section chip + title)."""
    with st.container(border=True, key=key):
        if title:
            head(title, sec, emoji)
        yield


BADGE_COLORS = {"danger": ("#FBD9D3", "#A3322A"), "warning": ("#FFE9C6", "#8A5A00"),
                "success": ("#D7EFE3", "#1F6B47"), "info": ("#DCE9F8", "#2B62A6"),
                "light": ("#F6EEE3", "#63706C"), "secondary": ("#E9E4DC", "#4A4A4A")}


def badge(text: str, color: str = "secondary") -> str:
    bg, ink = BADGE_COLORS.get(color, BADGE_COLORS["secondary"])
    return f'<span class="sh-badge" style="background:{bg};color:{ink}">{esc(text)}</span>'


def md_badge(text: str, color: str = "secondary") -> str:
    """Badge for widget labels (markdown): Streamlit's coloured backgrounds."""
    c = {"danger": "red", "warning": "orange", "success": "green", "info": "blue",
         "light": "gray", "secondary": "gray"}.get(color, "gray")
    return f":{c}-background[{text}]"


def empty(text: str) -> None:
    st.html(f'<div class="sh-empty">{esc(text)}</div>')


def muted(text: str) -> None:
    st.caption(text)


# ---- Session helpers -----------------------------------------------------------------------------
def user() -> dict | None:
    return st.session_state.get("user")


def can(what: str) -> bool:
    """Admins see everything; others need the switch on in Settings."""
    u = user()
    if not u:
        return False
    return bool(u.get("is_admin")) or bool(u.get({"money": "can_see_money", "sensitive": "can_see_sensitive"}[what]))


def people() -> list[dict]:
    """Active family members, read once per run."""
    run = st.session_state.get("_run_id")
    c = st.session_state.get("_people_cache")
    if c is None or c[0] != run:
        c = (run, data.get_people())
        st.session_state["_people_cache"] = c
    return c[1]


def person_options(allow_none: bool = True, other: bool = False):
    """Options and labels for a person selectbox: None = '—', 'other' = 'Other…'."""
    ppl = people()
    opts = ([None] if allow_none else []) + [p["id"] for p in ppl] + (["other"] if other else [])
    names = {p["id"]: p["name"] for p in ppl}
    return opts, (lambda v: "—" if v is None else ("Other…" if v == "other" else names.get(v, "?")))


def name_of(pid) -> str | None:
    return data.person_name(people(), pid)


def flash(msg: str, icon: str = "✅") -> None:
    st.toast(msg, icon=icon)


def try_db(fn, success: str | None = None, *args, **kwargs) -> bool:
    """Run a write, show a toast, and never crash the page on an error."""
    try:
        fn(*args, **kwargs)
        if success:
            flash(success)
        return True
    except Exception as e:  # noqa: BLE001 - show any failure to the user
        print("[db] error:", e)
        traceback.print_exc()
        st.toast(f"Something went wrong: {e}", icon="⚠️")
        return False


# ---- Navigation between pages (streamlit_app.py fills PAGES on every run) ----------------------
PAGES: dict = {}


def go(page_key: str) -> None:
    """Switch to another page."""
    if page_key in PAGES:
        st.switch_page(PAGES[page_key])


def link(page_key: str, label: str, icon: str | None = None) -> None:
    if page_key in PAGES:
        st.page_link(PAGES[page_key], label=label, icon=icon)


def go_button(page_key: str, label: str, key: str, primary: bool = False) -> None:
    if st.button(label, key=key, type="primary" if primary else "secondary"):
        go(page_key)


def confirm_delete(label: str, key: str, question: str, fn, *args, success: str = "Deleted",
                   full_width: bool = False) -> None:
    """A small 'Delete' popover that asks before deleting (Streamlit has no confirm box)."""
    with st.popover(label, use_container_width=full_width):
        st.write(question)
        if st.button("Yes, delete", key=key, type="primary"):
            if try_db(fn, success, *args):
                st.rerun()
