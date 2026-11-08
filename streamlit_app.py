"""The Shamp House: family organizer (Streamlit).

Run locally:   python -m streamlit run streamlit_app.py
Deploy:        Streamlit Community Cloud, main file = streamlit_app.py (see README.md)
"""
from __future__ import annotations

import streamlit as st

from hub.config import APP_DIR, APP_TITLE

st.set_page_config(page_title=APP_TITLE, page_icon=str(APP_DIR / "static" / "icons" / "icon-192.png"),
                   layout="wide", initial_sidebar_state="collapsed")

from hub import photos, quick, session, ui  # noqa: E402  (after set_page_config)
from hub.pages import (appts, ask, bills, budget, calendar, chores, contacts, grocery, journal, kids, learn,  # noqa: E402
                       meals, notes, settings, today, week, workouts)
from hub.pages import photos as photos_page  # noqa: E402

ui.inject_css()

from hub.config import missing_secrets  # noqa: E402
_missing = missing_secrets()
if _missing:
    st.error("The app's secrets are missing: " + ", ".join(_missing) + ". On Streamlit Community Cloud, paste the "
             "whole of your secrets.toml into the app's Settings → Secrets. On your computer, fill in "
             ".streamlit/secrets.toml (see README step 7).")
    st.stop()

session.write_pending_cookie()
session.try_cookie_login()

if not ui.user():
    session.login_page()
    st.stop()

st.session_state["_run_id"] = st.session_state.get("_run_id", 0) + 1


def sign_out_page():
    session.sign_out()


# key, title, icon, page function. The first four are the main menu; the rest sit under "More"
# (on phones the whole menu folds into the menu button).
try:
    photo_title = "Photos" if photos.week_has_photo() else "Photos 🟠"   # small reminder: no photo yet this week
except Exception:  # noqa: BLE001
    photo_title = "Photos"
MAIN = [("today", "Today", ":material/today:", today.page),
        ("calendar", "Calendar", ":material/calendar_month:", calendar.page),
        ("meals", "Meals", ":material/restaurant:", meals.page),
        ("notes", "Notes", ":material/sticky_note_2:", notes.page)]
MORE = [("grocery", "Grocery", ":material/shopping_cart:", grocery.page),
        ("chores", "Chores", ":material/cleaning_services:", chores.page),
        ("appts", "Appointments & reminders", ":material/event:", appts.page),
        ("week", "Week ahead", ":material/date_range:", week.page),
        ("kids", "Kids", ":material/child_care:", kids.page),
        ("learn", "Learn", ":material/school:", learn.page),
        ("journal", "Journal/reflection", ":material/menu_book:", journal.page),
        ("photos", photo_title, ":material/photo_library:", photos_page.page),
        ("workouts", "Workouts", ":material/directions_run:", workouts.page),
        ("bills", "Bills", ":material/receipt_long:", bills.page),
        ("budget", "Budget", ":material/account_balance_wallet:", budget.page),
        ("ask", "Ask AI", ":material/forum:", ask.page),
        ("contacts", "Contacts", ":material/contacts:", contacts.page),
        ("settings", "Settings", ":material/settings:", settings.page)]
MONEY_PAGES = {"bills", "budget"}
NO_FAB = {"ask", "journal"}          # keep writing areas clear

pages = {}
for key, title, icon, fn in MAIN + MORE:
    if key in MONEY_PAGES and not ui.can("money"):
        continue
    pages[key] = st.Page(fn, title=title, icon=icon, url_path=key, default=(key == "today"))
ui.PAGES = pages
signout = st.Page(sign_out_page, title="Sign out", icon=":material/logout:", url_path="sign-out")

nav = st.navigation({"": [pages[k] for k, *_ in MAIN],
                     "More": [pages[k] for k, *_ in MORE if k in pages] + [signout]},
                    position="top")
nav.run()
if nav.url_path not in NO_FAB and nav.url_path != "sign-out":
    quick.fab()
