"""Settings, constants and small shared helpers.

Secrets come from Streamlit's secrets (Streamlit Community Cloud: app Settings > Secrets;
on your computer: .streamlit/secrets.toml). Outside Streamlit (check_setup.py) the same
file is read directly, and environment variables work too.
"""
from __future__ import annotations

import os
import tomllib
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

APP_DIR = Path(__file__).resolve().parent.parent
_FILE_SECRETS: dict | None = None


def _file_secrets() -> dict:
    global _FILE_SECRETS
    if _FILE_SECRETS is None:
        p = APP_DIR / ".streamlit" / "secrets.toml"
        try:
            _FILE_SECRETS = tomllib.loads(p.read_text()) if p.exists() else {}
        except Exception as e:  # a typo in secrets.toml shouldn't crash imports
            print(f"[config] couldn't read {p}: {e}")
            _FILE_SECRETS = {}
    return _FILE_SECRETS


# Secrets the app can't start without (TomTom and Groq are optional: those features say the key is missing).
REQUIRED_SECRETS = ["SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_SECRET_KEY",
                    "PG_HOST", "PG_USER", "PG_PASSWORD", "ADMIN_EMAILS"]


def missing_secrets() -> list[str]:
    return [n for n in REQUIRED_SECRETS if not cfg(n)]


def cfg(name: str, default: str = "") -> str:
    """A setting by name: Streamlit secrets, then .streamlit/secrets.toml, then environment."""
    try:
        import streamlit as st  # only when running inside Streamlit
        if name in st.secrets:
            v = st.secrets[name]
            return default if v in (None, "") else str(v)
    except Exception:
        pass
    v = _file_secrets().get(name)
    if v not in (None, ""):
        return str(v)
    v = os.environ.get(name, "")
    return v if v != "" else default


APP_TITLE = cfg("APP_TITLE", "The Shamp House")
APP_TZ = cfg("APP_TZ", "America/New_York")
TZ = ZoneInfo(APP_TZ)


def now() -> datetime:
    """Local time (Streamlit Cloud servers run in UTC; 'today' must be Jacksonville's)."""
    return datetime.now(TZ)


def today() -> date:
    return now().date()


# ---- Constants (same as the R app) --------------------------------------------------------
FREQS = {"Daily": "daily", "Weekly": "weekly", "Monthly": "monthly", "Quarterly": "quarterly",
         "Yearly": "yearly"}
CHORE_VIEWS = {"Due now": "due", **FREQS, "All": "all"}
MEAL_SLOTS = ["Breakfast", "Lunch", "Dinner", "Snack"]
DUTY_TYPES = ["Drop-off", "Pick-up", "Other"]
EXPENSE_CATS = ["Housing", "Utilities", "Home services", "Childcare", "Food", "Transportation",
                "Insurance", "Loan", "Subscription", "Health & fitness", "Savings", "Personal", "Other"]
CHART_COLORS = {"shared": "#2a78d6", "personal": "#eb6834", "surplus": "#1baf7a"}
WORKOUT_TYPES = ["Run", "Strength", "HIIT", "Walk", "Cycling", "Yoga", "Stretching", "Swim", "Other"]
INTENSITIES = ["Easy", "Moderate", "Hard"]
EQUIPMENT = ["None (bodyweight)", "Dumbbells", "Kettlebell", "Resistance bands", "Pull-up bar",
             "Jump rope", "Treadmill", "Bike", "Jogging stroller", "Pool"]
CONTACT_CATS = ["Doctor", "Dentist", "School", "Childcare", "Family", "Friends",
                "Home services", "Emergency", "Other"]
INFO_CATS = ["Wi-Fi & home", "Insurance", "Vehicles", "Medical", "Emergency", "Other"]
REPEATS = {"Doesn't repeat": "none", "Weekly": "weekly", "Monthly": "monthly", "Yearly": "yearly"}

CAL_COLORS = {"appt": "#3b6ea8", "kids": "#c46a2f", "meals": "#2f7d5b", "bills": "#8a4fa3",
              "chores": "#7a6a3a", "work": "#b5446e", "hol": "#C98512"}

# Theme colours (also in hub/ui.py CSS)
SAND, INK, PALM, MARIGOLD = "#F6EEE3", "#23363A", "#2E7D6B", "#F2A33A"


# ---- Small value helpers (R's nz / nnum / %||%) --------------------------------------------
def has_text(x) -> bool:
    return x is not None and not (isinstance(x, float) and x != x) and str(x).strip() != ""


def nz(x):
    """Trimmed text, or None when empty."""
    return str(x).strip() if has_text(x) else None


def nnum(x):
    try:
        if x is None or x == "":
            return None
        f = float(x)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def as_id(x):
    if x in (None, "", "other", "none"):
        return None
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def first(*vals):
    """First value that isn't None/empty (R's %||%)."""
    for v in vals:
        if v is not None and v != "" and v != [] and v != {}:
            return v
    return vals[-1] if vals else None
