"""The Shamp House setup check.

Run from this folder before deploying:   python check_setup.py
Each step prints PASS / FAIL so you can see exactly what still needs fixing.
Steps that use the internet or your Supabase project come last; `--offline` skips them.
"""
from __future__ import annotations

import io

import sys
import time
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
OFFLINE = "--offline" in sys.argv
results: list[tuple[str, bool, str]] = []


def step(name: str, live: bool = False):
    """Decorator: run one check, print PASS/FAIL with a short message."""
    def wrap(fn):
        n = len(results) + 1
        if live and OFFLINE:
            print(f"[{n}] {name} … skipped (--offline)")
            results.append((name, True, "skipped"))
            return fn
        print(f"[{n}] {name} …", flush=True)
        t0 = time.time()
        try:
            msg = fn() or ""
            ok = True
        except Exception as e:  # noqa: BLE001
            ok, msg = False, f"{type(e).__name__}: {e}"
            if "--debug" in sys.argv:
                traceback.print_exc()
        print(f"    {'PASS' if ok else 'FAIL'} {msg}  ({time.time() - t0:.1f}s)", flush=True)
        results.append((name, ok, msg))
        return fn
    return wrap


def check(cond, msg="check failed"):
    if not cond:
        raise AssertionError(msg)


# ============================== Offline checks ==============================================
@step("Python version and packages installed")
def _():
    check(sys.version_info >= (3, 11), f"Python 3.11 or newer needed (this is {sys.version.split()[0]})")
    need = {"streamlit": "streamlit", "psycopg": "psycopg[binary]", "psycopg_pool": "psycopg-pool",
            "requests": "requests", "pandas": "pandas", "plotly": "plotly", "PIL": "Pillow",
            "reportlab": "reportlab", "streamlit_calendar": "streamlit-calendar", "pillow_heif": "pillow-heif"}
    miss = []
    for mod, pkg in need.items():
        try:
            __import__(mod)
        except ImportError:
            miss.append(pkg)
    check(not miss, "run:  pip install -r requirements.txt   (missing: " + ", ".join(miss) + ")")
    import streamlit
    v = tuple(int(x) for x in streamlit.__version__.split(".")[:2])
    check(v >= (1, 50), f"Streamlit {streamlit.__version__} is too old; pip install -r requirements.txt")
    note = ""
    import shutil
    cmd = shutil.which("streamlit")
    if cmd:      # the 'streamlit' command may belong to another Python than this one
        try:
            first = open(cmd, encoding="utf-8", errors="ignore").readline()
        except OSError:
            first = ""
        if first.startswith("#!") and str(Path(sys.prefix).resolve()) not in str(Path(first[2:].strip().split()[0]).resolve()):
            note = ("; note: the 'streamlit' command belongs to another Python, so start the app with "
                    "'python -m streamlit run streamlit_app.py'")
    return f"all present (Python {sys.version.split()[0]}, Streamlit {streamlit.__version__}){note}"


@step("Load app code (hub/ folder)")
def _():
    import importlib
    mods = sorted(p.stem for p in (HERE / "hub").glob("*.py") if p.stem != "__init__")
    for m in mods:
        importlib.import_module(f"hub.{m}")
    pages = sorted(p.stem for p in (HERE / "hub" / "pages").glob("*.py") if p.stem != "__init__")
    for p in pages:
        importlib.import_module(f"hub.pages.{p}")
    return f"{len(mods)} modules and {len(pages)} pages loaded"


@step("Secrets present (.streamlit/secrets.toml)")
def _():
    from hub.config import APP_TZ, cfg, missing_secrets
    miss = missing_secrets() + [n for n in ("GROQ_API_KEY", "TOMTOM_API_KEY") if not cfg(n)]
    check(not miss, "missing in .streamlit/secrets.toml: " + ", ".join(miss))
    return f"timezone {APP_TZ}"


@step("Date and calendar helpers")
def _():
    from hub.config import TZ
    from hub.dates import add_months, months_between, quarter_start, week_start
    from hub.ics import calendar
    check(week_start(date(2026, 11, 5)) == date(2026, 11, 2))
    check(quarter_start(date(2026, 11, 5)) == date(2026, 10, 1))
    check(add_months(date(2026, 1, 31), 1) == date(2026, 2, 28))
    check(add_months(date(2026, 11, 15), 3) == date(2027, 2, 15))
    check(months_between(date(2026, 1, 1), date(2026, 11, 1)) == 10)
    a = {"id": 1, "title": "Dentist, 6-month check", "who": "Dad", "all_day": False,
         "start_at": datetime(2026, 11, 5, 15, 30, tzinfo=TZ), "end_at": None,
         "location": "Main St; Suite 2", "notes": None, "recurrence": "none", "kind": "appointment"}
    ics = calendar([a])
    check("DTSTART:20261105T203000Z" in ics, "3:30 PM Eastern should be 20:30 UTC")
    check("SUMMARY:Dentist\\, 6-month check" in ics, "commas must be escaped")
    return "ok"


@step("Repeating appointments and reminders")
def _():
    from hub.config import TZ
    from hub.data import expand_occurrences

    def ex(d0, rule, frm, to):
        y, m, d = map(int, d0.split("-"))
        a = [{"id": 1, "recurrence": rule, "start_at": datetime(y, m, d, 9, 30, tzinfo=TZ), "end_at": None}]
        return [o["occ_date"].isoformat() for o in expand_occurrences(a, date.fromisoformat(frm), date.fromisoformat(to))]
    cases = [
        (ex("2026-01-31", "monthly", "2026-01-01", "2026-06-30"),
         ["2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30", "2026-05-31", "2026-06-30"]),
        (ex("2026-10-05", "weekly", "2026-11-03", "2026-11-20"), ["2026-11-09", "2026-11-16"]),
        (ex("2024-02-29", "yearly", "2025-01-01", "2028-12-31"), ["2025-02-28", "2026-02-28", "2027-02-28", "2028-02-29"]),
        (ex("2026-11-05", "none", "2026-11-03", "2026-11-10"), ["2026-11-05"]),
        (ex("2026-10-05", "none", "2026-11-03", "2026-11-10"), [])]
    bad = [i + 1 for i, (g, w) in enumerate(cases) if g != w]
    check(not bad, f"case(s) {bad} gave unexpected dates")
    t = expand_occurrences([{"id": 1, "recurrence": "weekly", "start_at": datetime(2026, 10, 5, 9, 30, tzinfo=TZ),
                             "end_at": None}], date(2026, 11, 2), date(2026, 11, 2))
    check(t[0]["start_at"].astimezone(TZ).strftime("%H:%M") == "09:30", "time of day not kept across the DST change")
    return "monthly, weekly, yearly (incl. 29 Feb), one-off and time of day all correct"


@step("Chore due dates and status")
def _():
    from hub.data import chore_due_date, chore_status
    from hub.starters import STARTER_CHORES
    D = date.fromisoformat
    cases = [(chore_due_date("monthly", D("2027-02-01"), 31), D("2027-02-28")),
             (chore_due_date("monthly", D("2026-11-01")), D("2026-11-30")),
             (chore_due_date("yearly", D("2027-01-01"), 29, 2), D("2027-02-28")),
             (chore_due_date("yearly", D("2026-01-01"), 18, 10), D("2026-10-18")),
             (chore_due_date("quarterly", D("2026-10-01")), D("2026-12-31")),
             (chore_due_date("weekly", D("2026-11-02")), D("2026-11-08"))]
    bad = [i + 1 for i, (g, w) in enumerate(cases) if g != w]
    check(not bad, f"due-date case(s) {bad} wrong")
    ref = D("2026-11-03")
    st = [chore_status(dn, D(d), ref) for dn, d in [(False, "2026-11-01"), (False, "2026-11-09"),
                                                   (False, "2026-11-21"), (True, "2026-11-01")]]
    check(st == ["overdue", "soon", "later", "done"], f"status wrong: {st}")
    keys = [c["starter_key"] for c in STARTER_CHORES]
    check(len(keys) == len(set(keys)), "duplicate starter chores")
    return f"{len(STARTER_CHORES)} starter chores; month ends and 29 February handled"


@step("Sitter sheet draws (PDF and image)")
def _():
    from hub.sitter import sitter_pdf, sitter_png
    d = {"title": "Info for the sitter", "subtitle": "Test", "address": "123 Example St",
         "contacts": [{"name": n, "category": c, "phone": p, "notes": None} for n, c, p in
                      [("Kate", "Family", "555-0100"), ("Scoop", "Family", "555-0101"), ("Dr. Example", "Doctor", "555-0102")]],
         "info": [{"label": "Door code", "value": "1234"}, {"label": "Wi-Fi", "value": "network / password"}],
         "notes": "Bedtime 7:30.\nSnacks in the pantry."}
    a, b = sitter_pdf(d), sitter_png(d)
    check(len(a) > 1000 and len(b) > 1000, "output files look empty")
    return f"PDF {len(a) / 1024:.0f} KB, image {len(b) / 1024:.0f} KB"


@step("Theme files present (fonts, logo, icons, config)")
def _():
    need = ["static/logo.svg", "static/icons/icon-180.png", "static/icons/icon-192.png", "static/icons/icon-512.png",
            "static/fonts/BricolageGrotesque-Bold.ttf", "static/fonts/WorkSans-Regular.ttf",
            "static/fonts/WorkSans-Bold.ttf", "static/fonts/Outfit-Regular.ttf", ".streamlit/config.toml"]
    miss = [n for n in need if not (HERE / n).exists()]
    check(not miss, "missing: " + ", ".join(miss))
    import tomllib
    c = tomllib.loads((HERE / ".streamlit/config.toml").read_text())
    check(c.get("server", {}).get("enableStaticServing") is True, "config.toml must turn on enableStaticServing")
    return f"{len(need)} files found"


@step("Gratitude jar: a prompt for every date, and the note from the jar")
def _():
    from hub.gratitude import GRATITUDE_PROMPTS, pick_index, prompt_for, prompt_index
    check(len(GRATITUDE_PROMPTS) == 366, f"gratitude_prompts.txt should have 366 prompts, has {len(GRATITUDE_PROMPTS)}")
    dup = sorted({p for p in GRATITUDE_PROMPTS if GRATITUDE_PROMPTS.count(p) > 1})
    check(not dup, f"repeated prompts: {dup[:3]}")
    leap = [prompt_for(date(2028, 1, 1) + timedelta(days=i)) for i in range(366)]
    check(len(set(leap)) == 366, "a leap year should use all 366 prompts")
    plain = [prompt_for(date(2027, 1, 1) + timedelta(days=i)) for i in range(365)]
    check(len(set(plain)) == 365 and GRATITUDE_PROMPTS[59] not in plain, "February 29's prompt should only be used in leap years")
    check(prompt_index(date(2027, 3, 1)) == prompt_index(date(2028, 3, 1)) == 60, "each date should keep its prompt every year")
    check(prompt_for(date(2026, 12, 21)).startswith("What's the shortest day"), "prompts are out of date order")
    check(pick_index(0, date(2026, 11, 10)) is None and all(0 <= pick_index(n, date(2026, 11, 10)) < n for n in (1, 2, 7, 365)),
          "the note from the jar should always be one of the earlier notes")
    return f"366 different prompts, one per date (Feb 29 in leap years only); note from the jar OK; today: {prompt_for(date.today())}"


@step("Animal of the day checks")
def _():
    from hub.extras import first_sentences, inat_candidates, inat_photo, pick_inat

    def obs(tid, common, rank=10, lic="cc-by-nc", group="Aves", day="2026-11-05"):
        return {"taxon": {"id": tid, "name": f"Sci {tid}", "preferred_common_name": common, "rank_level": rank,
                          "iconic_taxon_name": group},
                "photos": [{"url": f"https://static.inaturalist.org/photos/{tid}/square.jpg", "license_code": lic,
                            "attribution": "(c) someone, some rights reserved (CC BY-NC)"}],
                "observed_on": day, "uri": f"https://www.inaturalist.org/observations/{tid}"}
    res = [obs(5, "osprey"), obs(5, "osprey", day="2026-11-04"),        # same species twice -> one entry
           obs(7, "", group="Insecta"),                                  # no common name -> skipped
           obs(9, "lizards", rank=30),                                   # genus or higher -> skipped
           obs(11, "Gopher Tortoise", lic=None, group="Reptilia"),       # photo not CC licensed -> skipped
           obs(13, "Florida manatee", group="Mammalia"), obs(17, "green anole", group="Reptilia")]
    c = inat_candidates(res)
    check([x["taxon_id"] for x in c] == [5, 13, 17], f"species filter is off: {[x['taxon_id'] for x in c]}")
    check(c[0]["name"] == "Osprey" and c[0]["group"] == "Bird" and c[0]["seen"] == "2026-11-05",
          f"fields are off: {c[0]}")
    check(c[0]["image"].endswith("/5/medium.jpg"), f"photo size swap is off: {c[0]['image']}")
    check(inat_photo("https://x/photos/1/square.jpeg?1") == "https://x/photos/1/medium.jpeg?1", "photo url swap is off")
    d = date(2026, 11, 8)
    p1 = pick_inat(c, set(), d)
    check(p1 is not None and pick_inat(c, set(), d) == p1, "pick should be the same all day")
    p2 = pick_inat(c, {p1["taxon_id"]}, d)
    check(p2 is not None and p2["taxon_id"] != p1["taxon_id"], "a recent species should be skipped")
    check(pick_inat(c, {5, 13, 17}, d) is None, "all-recent list should give no pick")
    check(first_sentences("Otters are mammals. They swim. They eat fish.") == "Otters are mammals. They swim.",
          "summary trimming is off")
    return f"species filter, photo size, daily pick and no-repeat OK (today's test pick: {p1['name']})"


@step("Recipe of the day tidy-up (TheMealDB)")
def _():
    from hub.extras import parse_mealdb, recipe_ok
    raw = {"idMeal": "52772", "strMeal": "Teriyaki Chicken Casserole", "strCategory": "Chicken", "strArea": "Japanese",
           "strInstructions": "STEP 1\r\nPreheat oven to 350.\r\n\r\nSTEP 2\r\nCombine  soy sauce and water.\r\n",
           "strMealThumb": "https://www.themealdb.com/images/media/meals/wvpsxx1468256321.jpg",
           "strSource": "", "strYoutube": "https://www.youtube.com/watch?v=4aZr5hZXP_s",
           "strIngredient1": "soy sauce", "strMeasure1": "3/4 cup", "strIngredient2": "chicken breasts",
           "strMeasure2": " 2 ", "strIngredient3": "salt", "strMeasure3": "", "strIngredient4": "", "strMeasure4": " ",
           "strIngredient5": None, "strMeasure5": None}
    r = parse_mealdb(raw)
    check(r["ingredients"] == ["3/4 cup soy sauce", "2 chicken breasts", "salt"], f"ingredients: {r['ingredients']}")
    check(r["instructions"] == "Preheat oven to 350.\nCombine soy sauce and water.", f"steps: {r['instructions']!r}")
    check(r["meta"] == "Japanese · Chicken" and r["url"].endswith("/meal/52772"), f"meta/url: {r['meta']} {r['url']}")
    check(recipe_ok(r, set()) and not recipe_ok(r, {"52772"}), "repeat rule is off")
    check(not recipe_ok(dict(r, category="Dessert"), set()), "desserts should be skipped")
    check(not recipe_ok(dict(r, ingredients=[]), set()), "a recipe with no ingredients should be skipped")
    return "ingredients, steps, no desserts, no repeats OK"


@step("Daily learning: reading time, article trimming, quiz and streak rules")
def _():
    from hub.learn import clean_quiz, learn_streak, reading_minutes, trim_article
    check(reading_minutes("word " * 200, "adult") == 1 and reading_minutes("word " * 201, "adult") == 2
          and reading_minutes("word " * 401, "adult") == 3 and reading_minutes("", "adult") == 1,
          "reading time is off (200 words a minute, at least 1)")
    art = "Intro para.\n\nMore text.\n\n== See also ==\nOther page\n\n== References ==\n1. x"
    check(trim_article(art) == "Intro para.\n\nMore text.", f"reference sections not dropped: {trim_article(art)!r}")
    check(trim_article("aaaa\nbbbb\ncccc", 11) == "aaaa\nbbbb", "article not cut at a whole line")
    qs = [{"question": "Closest star?", "choices": ["Sirius", "The Sun", "Proxima Centauri"], "answer": 1},
          {"question": "Bad index", "choices": ["a", "b", "c"], "answer": 3},
          {"question": "Too few", "choices": ["a", "b"], "answer": 0},
          {"question": "Repeats", "choices": ["a", "a", "b"], "answer": 0},
          {"question": "", "choices": ["a", "b", "c"], "answer": 0},
          {"question": "Text answer", "choices": ["a", "b", "c"], "answer": "x"}]
    c = clean_quiz(qs)
    check(len(c) == 1 and c[0]["answer"] == 1, f"quiz filter is off: {c}")
    t = date(2026, 11, 8)
    d = {t - timedelta(days=i) for i in (0, 1, 2, 4)}
    check(learn_streak(d, t) == 3, "streak should count today and the days before it")
    check(learn_streak(d - {t}, t) == 2, "streak should still count up to yesterday before today's lesson")
    check(learn_streak({t - timedelta(days=3)}, t) == 0, "an old day shouldn't count as a streak")
    return "reading time, trimming, quiz filter and streaks OK"


@step("AI requests wait and retry when Groq's per-minute limit is hit")
def _():
    from hub.groq import GROQ_MAX_WAIT_S, rate_limit_wait
    cases = {"Please try again in 862.5ms. Need more tokens?": 1.4, "Please try again in 7.2s.": 7.7,
             "Please try again in 1m2.5s.": GROQ_MAX_WAIT_S, "Please try again in 2m.": GROQ_MAX_WAIT_S,
             "no hint here": 5.0}
    got = {k: rate_limit_wait(k) for k in cases}
    check(got == cases, f"wait times are off: {got}")
    check(rate_limit_wait("", "12") == 12.0, "Retry-After header not used")
    return "wait times from Groq's message (ms, s, minutes) and Retry-After OK"


@step("Headlines: feed reading, 3 national + 2 local, refresh timing")
def _():
    from datetime import datetime, timezone
    from hub.news import ago, is_stale, parse_feed, pick_headlines
    rss = ('<rss><channel><item><title>A &amp; B</title><link>https://n/1</link>'
           '<pubDate>Tue, 10 Nov 2026 15:00:00 GMT</pubDate></item><item><title>Two</title><link>https://n/2</link></item>'
           '<item><title>No link</title></item><item><title>Three</title><link>https://n/3</link></item>'
           '<item><title>Four</title><link>https://n/4</link></item></channel></rss>')
    atom = ('<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Local one</title><link href="https://l/1"/></entry>'
            '<entry><title>A &amp; B</title><link href="https://l/dup"/></entry><entry><title>Local two</title>'
            '<link href="https://l/2"/></entry><entry><title>Local three</title><link href="https://l/3"/></entry></feed>')
    n, l = parse_feed(rss, "NPR"), parse_feed(atom, "Jacksonville Today")
    check([x["title"] for x in n] == ["A & B", "Two", "Three", "Four"], f"RSS reading is off: {n}")
    check(l[0]["url"] == "https://l/1", "Atom links not read")
    p = pick_headlines({"national": n, "local": l})
    check([x["title"] for x in p] == ["A & B", "Two", "Three", "Local one", "Local two"],
          f"should be 3 national + 2 local with no repeats: {[x['title'] for x in p]}")
    at = datetime(2026, 11, 10, 17, 0, tzinfo=timezone.utc)
    check(ago(n[0]["published"], at) == "2h ago" and ago("", at) == "", "'time ago' is off")
    fresh = {"fetched_at": datetime(2026, 11, 10, 15, 30, tzinfo=timezone.utc).isoformat(), "items": [1]}
    check(not is_stale(fresh, at) and is_stale(fresh, at.replace(hour=18)) and is_stale(None, at),
          "headlines should refresh after 2 hours")
    return "RSS and Atom, 3 + 2 without repeats, time ago, 2-hour refresh OK"


@step("Space photo of the day tidy-up (NASA)")
def _():
    from hub.extras import apod_page, clean_apod
    img = clean_apod({"title": "Pillars of Creation", "date": "2026-11-10", "media_type": "image",
                      "url": "https://apod.nasa.gov/apod/image/2611/pillars.jpg", "copyright": "\nJane  Doe\n",
                      "explanation": "One. Two! Three? Four."})
    check(img["text"] == "One. Two! Three?" and img["credit"] == "© Jane Doe" and img["video"] == "",
          f"image day is off: {img}")
    check(img["url"] == "https://apod.nasa.gov/apod/ap261110.html", f"APOD page link is off: {img['url']}")
    vid = clean_apod({"title": "Eclipse", "date": "2026-11-11", "media_type": "video",
                      "url": "https://www.youtube.com/embed/x", "thumbnail_url": "https://img.youtube.com/x.jpg"})
    check(vid["image"].endswith("x.jpg") and vid["video"].startswith("https://www.youtube") and vid["credit"] == "NASA",
          f"video day is off: {vid}")
    check(apod_page("") == "https://apod.nasa.gov/apod/", "missing date should link to APOD's home page")
    return "image days, video days, credit and page link OK"


@step("Countdown labels")
def _():
    from hub.countdown import COUNTDOWN_DAYS, COUNTDOWN_SHOW, days_label
    check([days_label(n) for n in (0, 1, 2, 45)] == ["Today!", "Tomorrow", "2 days", "45 days"], "countdown labels are off")
    check(COUNTDOWN_SHOW == 4 and COUNTDOWN_DAYS == 365, "Today should show the next 4 within a year")
    return "Today!, Tomorrow, N days; next 4 within a year"


@step("Trivia rules")
def _():
    from hub.trivia import TRIVIA_WEDGES, trivia_difficulty_for, trivia_order, trivia_pie_svg, trivia_wedge_for
    days = [date(2026, 11, 2) + timedelta(days=i) for i in range(7)]
    keys = [trivia_wedge_for(d)["key"] for d in days]
    check(keys == [w["key"] for w in TRIVIA_WEDGES], f"weekday wedges are off: {keys}")
    check(trivia_wedge_for(date(2026, 11, 8))["name"] == "General Knowledge", "Sunday should be General Knowledge")
    diffs = [trivia_difficulty_for(date(2026, 1, 1) + timedelta(days=i)) for i in range(70)]
    med = sum(d == "medium" for d in diffs) / len(diffs)
    check(med >= 0.6 and "easy" in diffs and "hard" in diffs, "difficulty mix is off")
    o = trivia_order(4, date(2026, 11, 7))
    check(sorted(o) == [0, 1, 2, 3] and o == trivia_order(4, date(2026, 11, 7)), "choice shuffle is off")
    check(trivia_pie_svg(["geo", "his"]).count("<path") == 7, "pie should have 7 wedges")
    return f"7 weekday wedges; {round(100 * med)}% medium days"


@step("Weather notes")
def _():
    from hub.config import TZ
    from hub.weather import weather_notes
    t0 = datetime(2026, 11, 6, 0, 0, tzinfo=TZ)
    hrs = [t0 + timedelta(hours=i) for i in range(48)]
    rain = [0] * 48
    rain[15:18] = [60, 70, 40]
    rain[24 + 13] = 55
    d = {"now_temp": 80, "now_code": 1, "is_day": True, "hours": hrs, "rain": rain, "day_code": [1, 61],
         "hi": [94, 81], "lo": [70, 44], "rain_max": [70, 55], "uv": [9, 5]}
    n = [x["text"] for x in weather_notes(d, datetime(2026, 11, 6, 9, 0, tzinfo=TZ))]
    want = ["Rain likely after 3 PM (70%)", "Hot today: 94°", "Very high UV, wear sunscreen",
            "Rain likely tomorrow after 1 PM (55%)", "Chilly tomorrow morning: 44°"]
    check(n == want, f"got: {n}")
    return f"{len(n)} notes as expected"


@step("Moon phase")
def _():
    from datetime import timezone
    from hub.weather import moon_phase
    u = lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc)  # noqa: E731
    cases = {"2024-01-11 11:57": "New moon", "2024-01-25 17:54": "Full moon", "2024-01-18 03:53": "First quarter",
             "2024-02-02 23:18": "Last quarter", "2024-01-21 12:00": "Waxing gibbous",
             "2024-01-14 12:00": "Waxing crescent"}
    bad = [k for k, v in cases.items() if moon_phase(u(k))["name"] != v]
    check(not bad, f"wrong phase at: {bad}")
    check(moon_phase(u("2024-01-20 12:00"))["next_full"] == date(2024, 1, 25), "next full moon date is off")
    m = moon_phase()
    return f"tonight: {m['name']} ({m['lit']}% lit)"


@step("School run traffic rules")
def _():
    from hub.config import TZ
    from hub.traffic import TRAFFIC_WINDOWS, traffic_rain, traffic_summary, traffic_window
    t = lambda s: datetime.fromisoformat(s).replace(tzinfo=TZ)  # noqa: E731
    w = lambda s: (traffic_window(t(s)) or {}).get("key", "-")  # noqa: E731
    got = [w(s) for s in ["2026-11-09 06:29", "2026-11-09 06:30", "2026-11-09 09:29", "2026-11-09 09:30",
                          "2026-11-13 14:30", "2026-11-13 17:29", "2026-11-13 17:30", "2026-11-07 07:00"]]
    check(got == ["-", "am", "am", "-", "pm", "pm", "-", "-"], f"windows: {got}")
    am, pm = TRAFFIC_WINDOWS
    r = lambda travel, usual, delay=0: {"travel": travel, "usual": usual, "delay": delay, "free": None, "meters": 16093}  # noqa: E731
    a = traffic_summary(r(900, 600), am, t("2026-11-09 07:30"), "07:55")
    check(a["travel"] == 15 and a["slower"] == 5 and not a["heavy"] and a["compare"] == "5 min slower than usual"
          and a["miles"] == 10.0 and a["arrive"].strftime("%H:%M") == "07:45"
          and a["leave_by"]["at"].strftime("%H:%M") == "07:40" and not a["leave_by"]["late"], f"case 1: {a}")
    b = traffic_summary(r(1500, 600), am, t("2026-11-09 07:45"), "07:55")
    check(b["slower"] == 15 and b["heavy"] and b["leave_by"]["late"], "case 2")
    check(traffic_summary(r(900, 600), am, t("2026-11-09 08:00"), "07:55")["leave_by"] is None, "bell has gone")
    check(traffic_summary(r(900, 600), pm, t("2026-11-09 15:00"), "07:55")["leave_by"] is None, "afternoon")
    check(traffic_summary(r(600, None, 720), pm, t("2026-11-09 15:00"))["heavy"], "no 'usual': uses delay")
    check(traffic_summary(r(500, 620), pm, t("2026-11-09 15:00"))["compare"] == "2 min faster than usual", "faster")
    hrs = [t("2026-11-09 00:00") + timedelta(hours=i) for i in range(24)]
    rain = [0] * 24
    rain[8], rain[15] = 70, 40                     # 8 AM 70%, 3 PM 40%
    wx = {"hours": hrs, "rain": rain}
    x = traffic_rain(wx, am, t("2026-11-09 07:10"))
    check(x["p"] == 70 and x["at"].strftime("%H") == "08" and traffic_rain(wx, pm, t("2026-11-09 14:40")) is None, "rain")
    return "windows, slower-than-usual, leave-by and rain all as expected"


@step("In season produce tidy-up")
def _():
    import json
    from hub.seasonal import clean_produce, produce_prompt
    j = {"fruits": ["strawberries", "Citrus", "strawberries", ""], "vegetables": ["kale", "broccoli"], "herbs": [],
         "peak": ["Strawberries", "mango"], "tip": "Buy berries early."}
    p = clean_produce(j)
    check(p["fruits"] == ["Strawberries", "Citrus"] and p["peak"] == ["Strawberries"] and p["herbs"] == []
          and "Strawberries, Kale" in produce_prompt(p), f"got {p}")
    back = json.loads(json.dumps({**p, "peak": "Strawberries"}))     # the R app saved one-item lists as text
    check(clean_produce(back)["peak"] == ["Strawberries"], "saved copy doesn't read back")
    try:
        clean_produce({"fruits": [], "vegetables": []})
        raise AssertionError("an empty list should be rejected")
    except RuntimeError:
        pass
    return "ok"


WOTD_FEED = r"""<rss><channel><title>Word of the Day</title><item><guid>a</guid><title><![CDATA[valedictory]]></title><link><![CDATA[https://www.merriam-webster.com/word-of-the-day/valedictory-2026-06-06]]></link><description><![CDATA[<font size="-1" face="arial, helvetica">
<p><strong>valedictory</strong> &#149; \val-uh-DIK-tuh-ree\ &#149; <em>adjective</em></p>
<p><em>Valedictory</em> means "expressing or containing a farewell."</p>
<p>// The coach gave a valedictory speech at the banquet.</p>
<p><strong>Did you know?</strong><br />It comes from Latin <em>valedicere</em>, &#8220;to say farewell.&#8221;</p></font>]]></description><merriam:shortdef><![CDATA[expressing or containing a farewell]]></merriam:shortdef></item><item><guid>b</guid><title><![CDATA[interloper]]></title><link><![CDATA[https://www.merriam-webster.com/word-of-the-day/interloper-2026-06-05]]></link><description><![CDATA[<p><strong>interloper</strong> &#149; \IN-ter-loh-per\ &#149; <em>noun</em></p>]]></description><merriam:shortdef><![CDATA[one that intrudes]]></merriam:shortdef></item></channel></rss>"""


@step("Word of the day parsing (Merriam-Webster feed)")
def _():
    from hub.extras import parse_mw_feed
    w = parse_mw_feed(WOTD_FEED, date(2026, 6, 6))
    check(w["word"] == "valedictory" and w["pos"] == "adjective" and w["pron"] == "\\val-uh-DIK-tuh-ree\\"
          and w["definition"] == "expressing or containing a farewell"
          and w["example"] == "The coach gave a valedictory speech at the banquet."
          and w["origin"] == "It comes from Latin valedicere, “to say farewell.”"
          and "valedictory-2026-06-06" in w["url"], f"got {w}")
    check(parse_mw_feed(WOTD_FEED, date(2026, 6, 5))["word"] == "interloper", "second item")
    check(parse_mw_feed(WOTD_FEED, date(2026, 6, 7)) is None, "not published yet should be None")
    return "word, part of speech, pronunciation, definition, example and origin as expected"


@step("Photos: weeks, photo of the week and collage layout")
def _():
    from PIL import Image
    from hub.config import TZ
    from hub.photos import (COLLAGE_H, COLLAGE_W, collage_layout, featured_pick, make_collage, photo_date_label,
                            week_label)
    check(week_label(date(2026, 11, 2)) == "Nov 2 – 8, 2026", week_label(date(2026, 11, 2)))
    check(week_label(date(2026, 11, 30)) == "Nov 30 – Dec 6, 2026", week_label(date(2026, 11, 30)))
    check(week_label(date(2026, 12, 28)) == "Dec 28, 2026 – Jan 3, 2027", week_label(date(2026, 12, 28)))
    check(photo_date_label(date(2026, 11, 7)) == "Sat, Nov 7, 2026", photo_date_label(date(2026, 11, 7)))
    t = lambda s: datetime.fromisoformat(s).replace(tzinfo=TZ)  # noqa: E731
    w = [{"id": 5, "is_featured": False, "created_at": t("2026-11-03 10:00")},
         {"id": 3, "is_featured": False, "created_at": t("2026-11-02 09:00")},
         {"id": 9, "is_featured": False, "created_at": t("2026-11-04 08:00")}]
    check(featured_pick(w) == 3, "none chosen: should be the first one added")
    w[2]["is_featured"] = True
    check(featured_pick(w) == 9, "should keep the chosen one")
    tl = collage_layout([1, 3, 4, 8])["tiles"]
    per_week = [sum(1 for x in tl if x["week"] == k) for k in (1, 2, 3, 4)]
    check(len(tl) == 15 and per_week == [1, 3, 4, 7], f"tiles per week {per_week}")
    check(sum(x["more"] for x in tl) == 1 and tl[-1]["more"] == 1, "8 in a week: 6 shown + '+1'")
    check(tl[0]["w"] == COLLAGE_W - 140, "a lone photo should fill its band")
    check(all(x["x"] >= 70 and x["y"] >= 70 and x["x"] + x["w"] <= COLLAGE_W - 70 and x["y"] + x["h"] <= COLLAGE_H - 70
              for x in tl), "a tile falls outside the page")
    for i, a in enumerate(tl):
        for b in tl[i + 1:]:
            check(not (a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"] and a["y"] < b["y"] + b["h"]
                       and b["y"] < a["y"] + a["h"]), "collage tiles overlap")
    cols = ["#C9A37A", "#7FA99B", "#E3B66B", "#9BB7D4", "#D99A8B", "#A7C48A"]
    imgs = {i: Image.new("RGB", (1200, 800) if i % 2 else (800, 1200), cols[i % 6]) for i in range(1, 17)}
    wk = [date(2026, 11, 2)] + [date(2026, 11, 9)] * 3 + [date(2026, 11, 16)] * 4 + [date(2026, 11, 23)] * 8
    rows = [{"id": i, "week_start": wk[i - 1], "caption": "Pumpkin patch" if i == 1 else None} for i in range(1, 17)]
    out = make_collage(date(2026, 11, 1), rows=rows, images=imgs)
    im = Image.open(io.BytesIO(out))
    check(im.size == (COLLAGE_W, COLLAGE_H), f"collage is {im.size}")
    (HERE / "collage_test.jpg").write_bytes(out)
    return "layout ok; test collage written to collage_test.jpg (open it to check the look)"


@step("Holidays: Google feed parsing and church days")
def _():
    from hub.holidays import church_days, easter_date, holiday_label, merge_holidays, parse_holiday_ics
    ics = "\r\n".join([
        "BEGIN:VCALENDAR", "BEGIN:VEVENT", "DTSTART;VALUE=DATE:20261111", "DTEND;VALUE=DATE:20261112",
        "SUMMARY:Veterans Day", "DESCRIPTION:Public holiday", "END:VEVENT",
        "BEGIN:VEVENT", "DTSTART;VALUE=DATE:20260510", "SUMMARY:Mother's Day",
        "DESCRIPTION:Observance\\nTo hide observances\\, go to Google Calendar Settings > Holidays in United Stat",
        " es", "END:VEVENT",
        "BEGIN:VEVENT", "DTSTART;VALUE=DATE:20260331", "SUMMARY:Cesar Chavez Day",
        "DESCRIPTION:Public holiday in California\\, Colorado", "END:VEVENT",
        "BEGIN:VEVENT", "DTSTART;VALUE=DATE:20260405", "SUMMARY:Easter Sunday", "DESCRIPTION:Observance", "END:VEVENT",
        "END:VCALENDAR"])
    h = parse_holiday_ics(ics)
    check([x["name"] for x in h] == ["Easter Sunday", "Mother's Day", "Veterans Day"], f"got {h}")
    check([x["day_off"] for x in h] == [False, False, True] and h[2]["date"] == date(2026, 11, 11), "day off tags")
    e = [easter_date(y).isoformat() for y in (2000, 2024, 2025, 2026, 2027, 2038)]
    check(e == ["2000-04-23", "2024-03-31", "2025-04-20", "2026-04-05", "2027-03-28", "2038-04-25"], f"Easter {e}")
    c26 = [x["date"].isoformat() for x in church_days([2026])]
    check(c26 == ["2026-02-18", "2026-03-29", "2026-04-03", "2026-04-05", "2026-05-24", "2026-11-29"], f"2026: {c26}")
    check(church_days([2024])[5]["date"] == date(2024, 12, 1) and church_days([2025])[5]["date"] == date(2025, 11, 30),
          "Advent")
    m = merge_holidays(h, church_days([2026]))
    check(sum(x["name"] == "Easter Sunday" for x in m) == 1 and len(m) == 8, "Easter doubled")
    check(holiday_label("Veterans Day", True) == "Veterans Day · Day off", "label")
    return "feed parsing, day-off tags, Easter (2000-2038) and church days as expected"


@step("Art of the day tidy-up")
def _():
    from hub.extras import art_index, clean_art
    a = {"id": 27992, "title": "A Sunday on La Grande Jatte &#8212; 1884",
         "artist_display": "Georges Seurat\nFrench, 1859-1891", "date_display": "1884-86",
         "medium_display": "Oil on canvas", "image_id": "abc-123",
         "description": "<p>Seurat spent two years painting it. He used dots of color. It hangs in Chicago. More text.</p>"}
    from hub.extras import shrink_jpeg
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (1686, 1000), (200, 120, 40)).save(buf, "PNG")
    small = Image.open(io.BytesIO(shrink_jpeg(buf.getvalue())))
    check(small.format == "JPEG" and small.size == (640, 380), f"art picture shrink is off: {small.format} {small.size}")
    x = clean_art(a)
    check(x["title"] == "A Sunday on La Grande Jatte — 1884" and x["artist"] == "Georges Seurat, French, 1859-1891"
          and x["text"] == "Seurat spent two years painting it. He used dots of color. It hangs in Chicago."
          and x["image"] == "https://www.artic.edu/iiif/2/abc-123/full/843,/0/default.jpg"
          and x["url"] == "https://www.artic.edu/artworks/27992", f"got {x}")
    i = [art_index(date(2026, 11, 1) + timedelta(days=k), 4000) for k in range(30)]
    check(all(1 <= v <= 4000 for v in i) and len(set(i)) == 30 and art_index(date(2026, 11, 7), 50000) <= 9000, "index")
    return "ok"


@step("Grocery list combines duplicates")
def _():
    from hub.grocery import fmt_qty, parse_ingredient, qty_text

    def pc(x):
        r = parse_ingredient(x)
        q = "NA" if r["qty"] is None else (str(int(r["qty"])) if r["qty"] == int(r["qty"]) else str(r["qty"]))
        return f"{q}|{r['unit']}|{r['key']}"
    cases = {"1 onion": "1||onion", "2 onions": "2||onion", "1 1/2 cups milk": "1.5|cup|milk",
             "½ cup milk": "0.5|cup|milk", "3 cloves garlic, minced": "3|clove|garlic", "2-3 tomatoes": "3||tomato",
             "2 lb boneless skinless chicken thighs": "2|lb|chicken thigh", "milk": "NA||milk", "12 eggs": "12||egg"}
    bad = [k for k, v in cases.items() if pc(k) != v]
    check(not bad, f"parsed wrongly: {[(k, pc(k)) for k in bad]}")
    check(qty_text(1.5, "cup") == "1 1/2 cup" and fmt_qty(3) == "3", "amount formatting is off")
    return f"{len(cases)} ingredient lines parsed; 1 onion + 2 onions = 3 onion"


@step("Budget maths reproduces the spreadsheet (budget_temp.xlsx)")
def _():
    from hub.budget import budget_calc
    names = ["Mortgage", "HOA", "Fertilizer", "Pest Control", "Internet", "Lawn Care", "Daycare", "Pool", "Utilities",
             "Cleaning", "Netflix", "Groceries/Food", "Misc", "Savings"]
    vals = [4595, 210, 100, 15, 90, 220, 1775, 140, 500, 150, 16, 900, 300, 200]
    shared = [{"name": n, "monthly": v} for n, v in zip(names, vals)]
    personal = [{"person": p, "name": n, "monthly": v} for p, n, v in zip(
        ["Kate"] * 5 + ["Scoop"] * 3,
        ["Car", "Car/Home Insurance", "Loan", "Exercise", "Misc", "Exercise", "Car", "Misc"],
        [420, 215, 430, 90, 200, 0, 0, 800])]
    income = [{"person": "Kate", "net_per_check": 3200, "gross_per_check": 4400, "checks_per_year": 26},
              {"person": "Scoop", "net_per_check": 3587.87, "gross_per_check": 5396.15, "checks_per_year": 26}]
    k = budget_calc(shared, personal, income)
    row = lambda p: next(s for s in k["summary"] if s["person"] == p)  # noqa: E731
    pn = lambda who: sum(x["pct_net"] for x in k["personal"] if x["person"] == who)  # noqa: E731
    expect = {   # spreadsheet cell: (ours, spreadsheet's)
        "B17": (sum(x["monthly"] for x in k["shared"]), 9211), "B18": (k["shared_per_person"]["monthly"], 4605.5),
        "F3": (k["shared"][0]["pct_net"], 0.312435157239197), "G3": (k["shared"][0]["pct_gross"], 0.216490073219503),
        "B22": (row("Kate")["expense_monthly"], 5960.5), "C22": (row("Kate")["surplus_monthly"], 972.833333333333),
        "D22": (row("Kate")["expense_weekly"], 1375.5), "E22": (row("Kate")["surplus_weekly"], 224.5),
        "F22": (row("Kate")["expense_daily"], 196.5), "G22": (row("Kate")["surplus_daily"], 32.0714285714286),
        "B23": (row("Scoop")["expense_monthly"], 5405.5), "C23": (row("Scoop")["surplus_monthly"], 2368.21833333333),
        "B24": (row("Total")["expense_monthly"], 11366), "C24": (row("Total")["surplus_monthly"], 3341.05166666667),
        "B27": (row("Kate")["expense_yearly"], 71526), "C27": (row("Scoop")["expense_yearly"], 64866),
        "E27": (row("Total")["expense_yearly"], 136392), "B28": (row("Kate")["surplus_yearly"], 11674),
        "C28": (row("Scoop")["surplus_yearly"], 28418.62), "E28": (row("Total")["surplus_yearly"], 40092.62),
        "B30": (row("Kate")["expense_pct_net"], 0.8596875), "C30": (row("Scoop")["expense_pct_net"], 0.695355783193414),
        "E30": (row("Total")["expense_pct_net"], 0.772826549984922),
        "B31": (row("Kate")["expense_pct_gross"], 0.625227272727273),
        "C31": (row("Scoop")["expense_pct_gross"], 0.462338177005116),
        "E31": (row("Total")["expense_pct_gross"], 0.535500799175814),
        "N9": (pn("Kate"), 0.195432692307692), "U7": (pn("Scoop"), 0.102910854972663),
        "C39": (sum(x["net_monthly"] for x in k["income"]), 14707.0516666667),
        "L39": (sum(x["gross_yearly"] for x in k["income"]), 254699.9),
        "D42": (k["rules"][0]["amount"], 3676.76291666667), "D43": (k["rules"][1]["amount"], 5294.5386),
        "D44": (k["rules"][2]["amount"], 6618.17325), "H43": (k["rules"][3]["amount"], 5942.99766666667),
        "H44": (k["rules"][4]["amount"], 7640.997),
        "H47": (k["tax"][0]["pct"], 0.272727272727273), "H48": (k["tax"][1]["pct"], 0.335105584537124),
        "H49": (k["tax"][2]["pct"], 0.307087988648602)}
    bad = [c for c, (a, b) in expect.items() if abs(a - b) > 1e-6 * max(1, abs(b))]
    check(not bad, f"mismatch in cells: {bad}")
    return f"{len(expect)} spreadsheet values reproduced"


@step("Keep me signed in (saved on each device, read through the page)")
def _():
    from hub.session import pending_write, saved_login_state
    page = HERE / "hub" / "device_store" / "index.html"
    check(page.exists(), "hub/device_store/index.html is missing")
    js = page.read_text()
    for needed in ("streamlit:componentReady", "streamlit:setComponentValue", "streamlit:render", "localStorage"):
        check(needed in js, f"device store page doesn't use {needed}")
    check(saved_login_state(None, None, False, None) == ("wait", ""), "should wait until the device reports")
    check(saved_login_state(None, None, True, None) == ("none", ""), "'Sign in with email instead' should skip waiting")
    check(saved_login_state({"token": "T1"}, None, False, None) == ("try", "T1"), "a saved sign-in should be tried")
    check(saved_login_state({"token": "T1"}, None, False, "T1") == ("none", ""), "the same token shouldn't be tried twice")
    check(saved_login_state({"token": ""}, None, False, None) == ("none", ""), "nothing saved -> sign-in page")
    check(saved_login_state({"token": "T1"}, {"user_id": "u"}, False, None) == ("none", ""), "already signed in")
    q = {"token": "T2", "only_if": None, "write_id": "w1"}
    check(pending_write({"write_id": None}, q) == q and pending_write({"write_id": "w1"}, q) is None,
          "a queued save should stay queued until the device confirms it")
    import ast
    app = (HERE / "streamlit_app.py").read_text()
    first = [n.value.func.attr for n in ast.parse(app).body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
             and isinstance(n.value.func, ast.Attribute) and n.value.func.attr == "render_store"]
    check(first == ["render_store"] and app.index("render_store()") < app.index("try_saved_login()"),
          "streamlit_app.py should draw the device store once, before trying the saved sign-in")
    return "device page, wait/try/skip rules, and save-until-confirmed OK"


@step("Database connection (session pooler)", live=True)
def _():
    from hub import db
    r = db.one("select now() as now, current_setting('TimeZone') as tz")
    from hub.config import APP_TZ
    check(r["tz"] == APP_TZ, f"database session time zone is {r['tz']}, expected {APP_TZ}")
    return f"connected; server time {r['now']:%Y-%m-%d %H:%M} | session tz {r['tz']}"


@step("Database tables created (sql/schema.sql)", live=True)
def _():
    from hub import db
    from hub.data import get_people
    t = {r["table_name"] for r in db.get("select table_name from information_schema.tables where table_schema = 'public'")}
    need = ["people", "app_users", "household_settings", "chores", "chore_log", "meals_library", "meal_plan",
            "grocery_items", "childcare_duties", "bills", "bill_payments", "appointments", "contacts", "household_info",
            "income", "workouts", "notes", "daily_verse", "saved_verses", "chat_threads", "chat_messages",
            "gratitude", "countdowns", "daily_extras", "trivia_answers", "learn_log", "photos"]
    miss = [n for n in need if n not in t]
    check(not miss, f"missing tables: {miss}: run sql/schema.sql")
    return f"{len(need)} tables found; {len(get_people())} family members"


@step("Supabase Auth reachable and sign-ups locked", live=True)
def _():
    from hub import auth
    r = auth.call("GET", auth.endpoint("/auth/v1/settings"), auth.public_headers())
    check(r["ok"], r["message"])
    check(r["body"].get("disable_signup") is True,
          "public sign-ups are ON: turn off 'Allow new users to sign up' in Authentication settings")
    return "ok"


@step("Supabase secret key works (needed to add logins from the app)", live=True)
def _():
    from hub import auth
    r = auth.call("GET", auth.endpoint("/auth/v1/admin/users"), auth.admin_headers(), params={"per_page": 50})
    check(r["ok"], r["message"])
    emails = [u.get("email", "") for u in r["body"].get("users", [])]
    return f"{len(emails)} login(s): {', '.join(emails)}"


@step("Bible verse service (bible-api.com)", live=True)
def _():
    from hub.verses import BIBLE_TRANSLATION, fetch_verse
    check(BIBLE_TRANSLATION == "kjv", f"BIBLE_TRANSLATION is '{BIBLE_TRANSLATION}'; set it to \"kjv\" in secrets")
    v = fetch_verse("Psalm 118:24")
    check(v is not None, "couldn't reach bible-api.com")
    return f"{v['reference']} ({v['translation']}): {v['text'][:50]}…"


@step("Today's extras sources (Wikipedia, iNaturalist, Open Trivia DB, ZenQuotes)", live=True)
def _():
    from hub.config import today
    from hub.extras import fetch_animal, fetch_history, fetch_quote
    from hub.trivia import fetch_trivia
    d = today()
    h, a, tv, qt = fetch_history(d), fetch_animal(d), fetch_trivia(d), fetch_quote(d)
    return (f"{len(h)} history item(s); animal: {a['name']} ({a['seen']}); "
            f"trivia: {tv['question'][:40]}…; quote by {qt['author']}")


@step("Headline feeds (NPR, Jacksonville Today / News4JAX)", live=True)
def _():
    from hub.news import NEWS_FEEDS, fetch_group
    out = []
    for g in NEWS_FEEDS:
        items = fetch_group(g)
        check(items, f"no {g} headlines: none of its feeds could be read")
        out.append(f"{g}: {items[0]['source']} ({len(items)}), e.g. {items[0]['title'][:40]}")
    return "; ".join(out)


@step("Word of the day source (merriam-webster.com)", live=True)
def _():
    import requests
    from hub.config import today
    from hub.extras import EXTRA_UA, MW_FEED, html_to_text, parse_mw_feed, xml_tag
    xml = requests.get(MW_FEED, headers={"User-Agent": EXTRA_UA}, timeout=12).text
    w = parse_mw_feed(xml, today())
    if w is None:
        import re
        m = re.search(r"(?s)<item>.*?</item>", xml)
        return (f"feed reachable; today's word isn't posted yet (newest: {html_to_text(xml_tag(m.group(0), 'title'))}), "
                "the app retries every 30 min")
    return f"{w['word']} ({w['pos']}): {w['definition'][:50]}"


@step("Art of the day and holiday sources (artic.edu, Google Calendar)", live=True)
def _():
    from hub.config import today
    from hub.extras import fetch_art
    from hub.holidays import fetch_holiday_feed
    from hub.extras import art_image_src
    a = fetch_art(today())
    src = art_image_src(a["image"])
    check(src.startswith("data:image/jpeg;base64,"), "the painting's picture couldn't be downloaded from artic.edu")
    h = fetch_holiday_feed()
    nxt = [x for x in h if x["date"] >= today()][:3]
    return (f"art: {a['title']} ({a['artist'][:30]}), picture {len(src) * 3 // 4 // 1024} KB; holidays: {len(h)} in the feed, next: "
            + "; ".join(f"{x['name']} {x['date']:%b %d}{' (day off)' if x['day_off'] else ''}" for x in nxt))


@step("Space photo of the day (api.nasa.gov)", live=True)
def _():
    from hub.config import cfg, today
    from hub.extras import fetch_apod
    a = fetch_apod(today())
    key = "your NASA_API_KEY" if cfg("NASA_API_KEY", "") else "the shared DEMO_KEY (add NASA_API_KEY for a reliable limit)"
    return f"{a['title']} ({a['date']}{', video' if a['video'] else ''}) using {key}"


@step("Recipe of the day source (themealdb.com)", live=True)
def _():
    from hub.config import today
    from hub.extras import fetch_recipe
    r = fetch_recipe(today())
    return f"{r['name']} ({r['meta']}), {len(r['ingredients'])} ingredients"


@step("Daily learning (Wikipedia articles + Groq lessons; nothing is saved)", live=True)
def _():
    from hub.config import today
    from hub.learn import make_day
    d = make_day("adult", today(), progress=lambda m: print("    ·", m, flush=True))
    return f"{len(d['lessons'])} lessons, {len(d['quiz'])} questions, e.g. {d['lessons'][0]['title']}"


@step("Weather service (open-meteo.com)", live=True)
def _():
    from hub.weather import fetch_weather
    w = fetch_weather()
    check(w is not None, "couldn't reach api.open-meteo.com")
    return f"now {round(w['now_temp'])}°, high {round(w['hi'][0])}°, low {round(w['lo'][0])}°"


@step("Photo storage (Supabase Storage bucket 'photos')", live=True)
def _():
    from PIL import Image
    from hub import auth
    from hub.photos import st_download, st_remove, st_sign, st_upload
    r = auth.call("GET", auth.endpoint("/storage/v1/bucket/photos"), auth.admin_headers())
    check(r["ok"], f"no 'photos' bucket ({r['message']}): run sql/schema.sql in the Supabase SQL Editor")
    check(r["body"].get("public") is not True, "the 'photos' bucket is public; make it private in Storage")
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "#2E7D6B").save(buf, "JPEG")
    path = f"setup-check/{datetime.now():%Y%m%d%H%M%S}.jpg"
    st_upload(buf.getvalue(), path)
    link = st_sign([path])
    back = st_download(path)
    st_remove([path])
    check(link and len(back) >= 100, "upload worked but the file couldn't be read back")
    return "upload, viewing link, download and delete all work"


@step("TomTom traffic (school run)", live=True)
def _():
    from hub.config import cfg
    from hub.traffic import school_settings, traffic_key, tt_geocode, tt_route
    check(traffic_key(), "add TOMTOM_API_KEY to secrets (developer.tomtom.com > API Keys)")
    s = school_settings()
    sc = tt_geocode(s["school"])
    home = tt_geocode(s["home"]) if s["home"] else {"lat": float(cfg("WEATHER_LAT", "30.159")),
                                                    "lon": float(cfg("WEATHER_LON", "-81.628"))}
    r = tt_route(home, sc)
    return (f"school found at {sc['label']}; {'home' if s['home'] else 'Mandarin (no home address saved yet)'} → school "
            f"now {round(r['travel'] / 60)} min" + (f" (usual {round(r['usual'] / 60)} min)" if r["usual"] else ""))


@step("In season produce (Groq)", live=True)
def _():
    from hub.config import today
    from hub.seasonal import seasonal_produce
    p = seasonal_produce()
    return (f"{today():%B}: {len(p['fruits'])} fruits, {len(p['vegetables'])} vegetables, e.g. "
            + ", ".join((p["peak"] + p["vegetables"])[:3]))


@step("Groq meal ideas", live=True)
def _():
    from hub import groq
    from hub.config import cfg
    m = groq.meal_ideas(n=1, request_text="quick weeknight dinner")
    check(m, "no meal returned")
    model = groq.current_model()
    return f"got: {m[0]['name']} (model {model})" + (
        f": set GROQ_MODEL = \"{model}\" in secrets" if model != cfg("GROQ_MODEL") else "")


# ===============================================================================================
fails = [r for r in results if not r[1]]
print()
if not fails:
    print("All checks passed. Run the app with:  streamlit run streamlit_app.py")
else:
    print(f"{len(fails)} check(s) failed: fix those and run this again.")
    for n, _, m in fails:
        print(f"  - {n}: {m}")
try:
    from hub import db
    db.close()
except Exception:  # noqa: BLE001
    pass
sys.exit(1 if fails else 0)
