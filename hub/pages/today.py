"""Today: the daily dashboard."""
from __future__ import annotations

import json
from datetime import date, timedelta

import streamlit as st

from hub import data, db, extras, forms, journal, learn, rows, traffic, trivia, ui, verses, weather
from hub import week as weekmod
from hub.config import CHORE_VIEWS, FREQS, has_text, now, today
from hub.dates import add_months, fmt_day, fmt_long_day, fmt_time, week_start
from hub.holidays import holidays_between

APPT_CAP = 8   # items shown on Today; the rest are a tap away
NOTE_COLORS = ["yellow", "pink", "blue", "green", "purple"]
esc = ui.esc


# ---- The porch: greeting, date, holiday, weather ---------------------------------------------
def porch() -> None:
    t = now()
    hello = "Good morning" if t.hour < 12 else ("Good afternoon" if t.hour < 17 else "Good evening")
    wx = weather.fetch_weather()
    hol = []
    try:
        hol = holidays_between(today(), today())
    except Exception as e:  # noqa: BLE001
        print("[today] holidays:", e)
    hol_html = ""
    if hol:
        hol_html = (f'<div class="sh-holiday">⭐ Today is {esc(" and ".join(h["name"] for h in hol))}'
                    + ('<span class="sh-holiday-off">Day off</span>' if any(h["day_off"] for h in hol) else "")
                    + "</div>")
    wx_html = notes_html = days_html = sun_html = ""
    if wx:
        info = weather.wx_code_info(wx["now_code"], wx["is_day"])
        wx_html = (f'<div class="sh-wx"><div class="sh-wx-now"><span class="sh-wx-icon">{info["icon"]}</span>'
                   f'<span class="sh-wx-temp">{round(wx["now_temp"])}°</span></div>'
                   f'<div class="sh-wx-range"><span class="sh-wx-hilo">High {round(wx["hi"][0])}° / Low {round(wx["lo"][0])}°'
                   f'</span><br>{esc(info["label"])}</div></div>')
        notes = weather.weather_notes(wx, t)
        if notes:
            notes_html = '<div class="sh-wx-notes">' + "".join(
                f'<span class="sh-wx-note">{n["icon"]} {esc(n["text"])}</span>' for n in notes) + "</div>"
        days = weather.weather_days(wx)
        days_html = '<div class="sh-days" role="list" aria-label="5-day forecast">' + "".join(
            f'<div class="sh-day" role="listitem" title="{esc(d["cond"])}"><div class="sh-day-name">{d["label"]}</div>'
            f'<div class="sh-day-icon">{d["icon"]}</div><div class="sh-day-temp"><strong>{d["hi"]}°</strong>'
            f'<span class="sh-day-lo">{d["lo"]}°</span></div>'
            + (f'<div class="sh-day-rain">💧{d["rain"]}%</div>' if d["rain"] >= 20 else "") + "</div>"
            for d in days) + "</div>"
        m = weather.moon_phase(t)
        nxt = f'<span class="sh-moon-next"> · full {fmt_day(m["next_full"])}</span>' if m["name"] != "Full moon" else ""
        sun_html = (f'<div class="sh-sun"><span>🌅 Sunrise {fmt_time(wx["sunrise"][0])}</span>'
                    f'<span>🌇 Sunset {fmt_time(wx["sunset"][0])}</span>'
                    f'<span title="{m["lit"]}% lit">{m["emoji"]} {m["name"]}{nxt}</span></div>')
    st.html(f'<section class="sh-porch"><div class="sh-porch-top"><div>'
            f'<h1 class="sh-hello">{hello}, {esc(ui.user()["display_name"])}</h1>'
            f'<div class="sh-date">{fmt_long_day(today())}</div>{hol_html}</div>{wx_html}</div>'
            f'{notes_html}{days_html}{sun_html}</section>')


# ---- School run (weekdays 6:30-9:30 AM and 2:30-5:30 PM), refreshed every 5 minutes ------------
@st.fragment(run_every="5m")
def school_run() -> None:
    t = now()
    win = traffic.traffic_window(t)
    if not win:
        return
    s = traffic.school_settings()
    where = s["label"] or "School"
    title = f"Home → {where}" if win["key"] == "am" else f"{where} → home"
    r = traffic.traffic_now(win, t)

    def wrap(body, heavy=False):
        st.html(f'<div class="sh-traffic{" is-heavy" if heavy else ""}" role="status">'
                f'<div class="sh-traffic-icon">🚗</div><div class="sh-traffic-body">{body}</div></div>')
    if "error" in r:
        wrap(f'<strong>{esc(title)}</strong><div class="sh-traffic-sub">{esc(r["error"])}</div>')
        return
    x = traffic.traffic_summary(r["route"], win, t, s["arrive_by"])
    rain = traffic.traffic_rain(weather.fetch_weather(), win, t)
    stale = (t - r["fetched"]) > timedelta(minutes=traffic.TRAFFIC_CACHE_MIN + 5)
    maps = (f'<a class="sh-traffic-map" href="{traffic.maps_link(r["from"], r["to"])}" target="_blank" '
            f'rel="noopener">🗺️ Maps</a>' if ui.can("sensitive") else "")
    sub = ((f'<span class="sh-traffic-warn">⚠️ Heavier than usual: </span>' if x["heavy"] else "") + x["compare"]
           + (f" · {x['miles']} mi" if x["miles"] is not None else "")
           + (f" · as of {fmt_time(r['fetched'])}" if stale else ""))
    body = (f'<div class="sh-traffic-top"><strong>{esc(title)}</strong>{maps}</div>'
            f'<div><span class="sh-traffic-min">{x["travel"]} min</span> · arrive {fmt_time(x["arrive"])} '
            f'if you leave now</div><div class="sh-traffic-sub">{sub}</div>')
    lb = x["leave_by"]
    if lb:
        body += ('<div class="sh-traffic-sub">🕒 ' + (
            f"Running late for {fmt_time(lb['target'])}: leaving now gets you there {fmt_time(x['arrive'])}"
            if lb["late"] else f"Leave by {fmt_time(lb['at'])} to arrive {fmt_time(lb['target'])}") + "</div>")
    if rain:
        when = "now" if rain["at"] <= t else f"around {weather.hour_label(rain['at'])}"
        body += f'<div class="sh-traffic-sub">☂️ Rain likely {when} ({rain["p"]}%): allow extra time</div>'
    wrap(body, x["heavy"])


# ---- Daily verse --------------------------------------------------------------------------------
def _save_verse(v: dict, theme: str) -> None:
    if db.one("select 1 as x from saved_verses where reference = $1", v["reference"]):
        ui.flash("Already saved.", "ℹ️")
        return
    ui.try_db(db.run, "Verse saved", """insert into saved_verses (reference, verse_text, translation, theme, saved_by)
                                         values ($1, $2, $3, $4, $5)""",
              v["reference"], v.get("verse_text"), v.get("translation"), theme, ui.user()["display_name"])


@st.dialog("Saved verses")
def saved_verses_dialog():
    s = db.get("select * from saved_verses order by saved_at desc")
    if not s:
        ui.empty("No saved verses yet. Tap Save on a verse to keep it.")
    for v in s:
        c1, c2 = st.columns([6, 1], vertical_alignment="center")
        c1.html(f'<div class="fh-verse-text" style="font-size:.95rem">{esc(v.get("verse_text") or "")}</div>'
                f'<div class="small"><strong>{esc(v["reference"])}</strong> '
                f'<span class="sh-muted">· saved by {esc(v.get("saved_by") or "?")}</span></div>')
        if c2.button(":material/delete:", key=f"unsave_{v['id']}", help="Remove"):
            ui.try_db(db.run, "Removed", "delete from saved_verses where id = $1", v["id"])
            st.rerun(scope="fragment")     # keep the list open


def verse_block(v: dict, label: str, key: str, theme: str) -> None:
    txt = v.get("verse_text") or "(text unavailable right now)"
    c1, c2 = st.columns([6, 1], vertical_alignment="top")
    c1.html(f'<div class="fh-verse"><div class="sh-muted">{esc(label)}</div>'
            f'<div class="fh-verse-text">{esc(txt)}</div>'
            f'<div class="fh-verse-ref">{esc(v["reference"])} <span class="sh-muted">· {esc(v.get("translation") or "")}'
            f'</span></div></div>')
    if c2.button(":material/bookmark:", key=f"save_{key}", help="Save verse"):
        _save_verse(v, theme)


def verse_card() -> None:
    try:
        v = verses.get_daily_verse(today())
    except Exception as e:  # noqa: BLE001
        print("[verse]", e)
        v = None
    if v:
        verse_block(v, "Verse of the day", "daily", "Verse of the day")
    else:
        ui.empty("Today's verse couldn't load.")
    extra = st.session_state.get("extra_verse")
    if extra:
        verse_block(extra, extra["theme"], "extra", extra["theme"])
    c1, c2, c3, c4 = st.columns([4, 1.2, 1.4, 1.3], vertical_alignment="bottom")
    theme = c1.text_input("Theme", placeholder="A verse about… (e.g. being kind)", label_visibility="collapsed",
                          key="verse_theme")
    if c2.button("Find", key="verse_find", use_container_width=True):
        if not has_text(theme):
            st.toast("Type a theme, or tap Random.", icon="ℹ️")
        else:
            with st.spinner("Finding a verse…"):
                try:
                    f = verses.verse_for_theme(theme.strip())
                    st.session_state["extra_verse"] = {"reference": f["reference"], "verse_text": f["text"],
                                                       "translation": f["translation"], "theme": f"About {theme.strip()}"}
                    st.rerun()
                except Exception as e:  # noqa: BLE001
                    st.toast(str(e), icon="⚠️")
    if c3.button("Random", key="verse_random", use_container_width=True):
        try:
            f = verses.random_verse()
            st.session_state["extra_verse"] = {"reference": f["reference"], "verse_text": f["text"],
                                               "translation": f["translation"], "theme": "Random verse"}
            st.rerun()
        except Exception as e:  # noqa: BLE001
            st.toast(str(e), icon="⚠️")
    if c4.button("Saved", key="verse_saved", icon=":material/bookmarks:", use_container_width=True):
        saved_verses_dialog()


# ---- Today's extras -----------------------------------------------------------------------------
def _item(sec: str, emoji: str, label: str, body: str) -> str:
    return (f'<div class="sh-extra">{ui.chip(sec, emoji)}<div style="flex:1;min-width:0">'
            f'<div class="sh-extra-label">{esc(label)}</div>{body}</div></div>')


def _link(url) -> str:
    return f' <a href="{esc(url)}" target="_blank" rel="noopener" class="small">Read more</a>' if has_text(url) else ""


def _pick(day, k: int):
    """Record a trivia answer (today's, or yesterday's until midnight)."""
    if day not in (today(), today() - timedelta(days=1)):
        return
    if day == today():
        tv = extras.get_extra("trivia")
    else:
        r = db.one("select content from daily_extras where extra_date = $1::date and kind = 'trivia'", day)
        tv = json.loads(r["content"]) if r else None
    if not tv or not (0 <= k < len(tv["choices"])):
        return
    ui.try_db(trivia.trivia_record, None, ui.user()["user_id"], day, tv, tv["choices"][k])


def trivia_block(day, tv: dict, mine: dict | None, late: bool = False) -> None:
    w = trivia.WEDGE.get(tv["wedge"], trivia.TRIVIA_WEDGES[6])
    head = (f'<div class="sh-extra" style="border:0;padding-bottom:0">'
            f'<span class="sh-chip" style="background:{w["color"]};color:#fff">?</span><div style="flex:1">'
            f'<div class="sh-extra-label">{"Yesterday" + chr(39) + "s trivia" if late else "Trivia"}: '
            f'<span style="color:{w["color"]}">{esc(w["name"])}</span> '
            f'<span style="font-weight:400">({esc(tv["difficulty"])})</span></div>'
            + ('<div class="small sh-muted">Still open until midnight tonight.</div>' if late and not mine else "")
            + f'<div class="sh-trivia-q">{esc(tv["question"])}</div></div></div>')
    st.html(head)
    choices = list(tv["choices"])
    if not mine:
        cols = st.columns(2)
        for k, ch in enumerate(choices):
            with cols[k % 2]:
                st.button(ch, key=f"trivia_{day}_{k}", use_container_width=True, on_click=_pick, args=(day, k))
        return
    out = []
    for ch in choices:
        if ch == tv["answer"]:
            out.append(f"✅ **{ch}**")
        elif ch == mine["choice"]:
            out.append(f"❌ ~~{ch}~~")
        else:
            out.append(ch)
    st.markdown("  \n".join(out))
    if mine["correct"]:
        st.html(f'<div class="sh-trivia-result sh-trivia-right"><strong>Correct! You earned the {esc(w["name"])} '
                f'wedge.</strong></div>')
    else:
        st.html(f'<div class="sh-trivia-result sh-trivia-wrong">Not this time. The answer is '
                f'<strong>{esc(tv["answer"])}</strong>.</div>')


def trivia_section(tv: dict) -> None:
    uid = ui.user()["user_id"]
    mine = trivia.trivia_my_answer(uid, today())
    yday = today() - timedelta(days=1)
    y = db.one("select content from daily_extras where extra_date = $1::date and kind = 'trivia'", yday)
    if y and not trivia.trivia_my_answer(uid, yday):
        with st.container(border=True):
            trivia_block(yday, json.loads(y["content"]), None, late=True)
    trivia_block(today(), tv, mine)
    if mine:
        pies = []
        for s in trivia.trivia_scores():
            n = len(s["wedges"])
            status = "Pie complete this week!" if n == trivia.TRIVIA_N else f"{n} of {trivia.TRIVIA_N} wedges this week"
            pies.append(f'<div class="sh-pie">{trivia.trivia_pie_svg(s["wedges"])}<div><strong>{esc(s["name"])}</strong>'
                        f'<div class="small sh-muted">{status}</div><div class="small sh-muted">Pies won: {s["pies"]}'
                        f'</div></div></div>')
        st.html(f'<div class="sh-pies" style="margin:.5rem 0">{"".join(pies)}</div>')
    st.html('<div class="small sh-muted">Questions from <a href="https://opentdb.com" target="_blank" '
            'rel="noopener">Open Trivia DB</a> (CC BY-SA 4.0)</div>')


def extras_card() -> None:
    g = {k: extras.get_extra(k) for k in ("trivia", "quote", "history", "animal", "art", "recipe", "joke", "dinner")}
    if not any(g.values()):
        return
    with ui.card("Today's extras", "appt", "⭐"):
        if g["trivia"]:
            trivia_section(g["trivia"])
        parts = []
        qt = g["quote"]
        if qt:
            parts.append(_item("notes", "❝", "Quote of the day",
                               f'<div class="sh-extra-text sh-quote">“{esc(qt["text"])}”</div>'
                               + (f'<div class="small" style="font-weight:600">— {esc(qt["author"])}</div>' if qt.get("author") else "")
                               + '<div class="small sh-muted">Inspirational quotes provided by <a href="https://zenquotes.io/" '
                                 'target="_blank" rel="noopener">ZenQuotes API</a></div>'))
        if g["history"]:
            parts.append(_item("appt", "🏛️", "This day in history", "".join(
                f'<div class="sh-extra-text"><strong>{esc(e["year"])}</strong> {esc(e["text"])}{_link(e.get("url"))}</div>'
                for e in g["history"])))
        an = g["animal"]
        if an:
            seen = ""
            try:
                seen = f'{an.get("group", "Animal")} spotted near home on {date.fromisoformat(an["seen"]):%b} ' \
                       f'{date.fromisoformat(an["seen"]).day}'
            except (KeyError, TypeError, ValueError):
                pass
            sci = f' <em class="sh-muted">{esc(an["sci"])}</em>' if has_text(an.get("sci")) else ""
            credit = (f'<div class="small sh-muted">Photo {esc(an["credit"])} · via '
                      f'<a href="https://www.inaturalist.org" target="_blank" rel="noopener">iNaturalist</a></div>'
                      if has_text(an.get("credit")) else "")
            parts.append(_item("work", "🐾", "Animal of the day",
                               f'<div class="sh-animal"><img src="{esc(an["image"])}" alt="{esc(an["name"])}" '
                               f'class="sh-animal-img" loading="lazy"><div class="sh-extra-text"><strong>{esc(an["name"])}'
                               f'</strong>{sci}' + (f'<div class="sh-muted">{esc(seen)}</div>' if seen else "")
                               + f'<div>{esc(an.get("text") or "")}</div>{_link(an.get("url"))}{credit}</div></div>'))
        art = g["art"]
        if art:
            src = extras.art_image_src(art["image"])
            pic = (f'<a href="{esc(art["url"])}" target="_blank" rel="noopener"><img src="{src}" '
                   f'alt="{esc(art["title"])}" class="sh-art-img"></a>' if src else "")
            parts.append(_item("notes", "🎨", "Art of the day",
                               f'<div class="sh-art">{pic}'
                               f'<div class="sh-extra-text"><div><strong><em>{esc(art["title"])}</em></strong>'
                               + (f'<span class="sh-muted">, {esc(art["date"])}</span>' if has_text(art.get("date")) else "")
                               + "</div>"
                               + (f'<div class="small">{esc(art["artist"])}</div>' if has_text(art.get("artist")) else "")
                               + (f'<div style="margin-top:.25rem">{esc(art["text"])}</div>' if has_text(art.get("text")) else "")
                               + f'<div class="small sh-muted"><a href="{esc(art["url"])}" target="_blank" rel="noopener">'
                                 'Art Institute of Chicago</a> · description CC BY</div></div></div>'))
        rc = g["recipe"]
        if rc:
            parts.append(_item("meals", "🍽️", "Recipe of the day",
                               f'<div class="sh-animal"><img src="{esc(rc["image"])}" alt="{esc(rc["name"])}" '
                               f'class="sh-animal-img" loading="lazy"><div class="sh-extra-text"><strong>{esc(rc["name"])}'
                               f'</strong>' + (f'<div class="sh-muted">{esc(rc["meta"])}</div>' if has_text(rc.get("meta")) else "")
                               + f'<div>{len(rc.get("ingredients") or [])} ingredients · add it to the plan from Meals</div>'
                                 '<div class="small sh-muted">Recipe from TheMealDB</div></div></div>'))
        if g["joke"]:
            parts.append(_item("kids", "😄", "Kids' joke", f'<div class="sh-extra-text">{esc(g["joke"]["text"])}</div>'))
        if g["dinner"]:
            parts.append(_item("meals", "💬", "Dinner question", f'<div class="sh-extra-text">{esc(g["dinner"]["text"])}</div>'))
        ls = learn.saved_day("adult", today())
        parts.append(_item("appt", "📚", "Today's lessons",
                           "".join(f'<div class="sh-extra-text">{esc(l["title"])} <span class="sh-muted">· {l["minutes"]} min</span></div>'
                                   for l in (ls or {}).get("lessons", []))
                           or '<div class="sh-extra-text">Science, history, money and how things work, plus the word of the day.</div>'))
        if parts:
            st.html("".join(parts))
        c1, c2 = st.columns(2)
        with c1:
            ui.link("learn", "Open Learn", icon=":material/school:")
        if rc:
            with c2:
                ui.link("meals", "Recipe of the day on Meals", icon=":material/restaurant:")


# ---- Banners: plan next week (Sunday 1-10 pm), journal prompt, a year ago ---------------------------
def banners() -> None:
    if weekmod.show_week_banner():
        ws = week_start(today()) + timedelta(days=7)
        g = weekmod.week_gaps(weekmod.week_data(ws))
        with st.container(border=True):
            st.markdown("**Time to plan next week**")
            st.caption(f"{len(g)} thing(s) to sort out: {'; '.join(g[:3])}" if g else "Everything looks covered.")
            c1, c2 = st.columns(2)
            with c1:
                ui.go_button("week", "Open Week ahead", "banner_week", primary=True)
            if c2.button("Week planned", key="banner_planned"):
                ui.try_db(db.set_setting, "Marked as planned", weekmod.week_planned_key(ws), "yes")
                st.rerun()
    uid = ui.user()["user_id"]
    ya = db.one("""select entry_date, prompt, body from journal_entries
                   where user_id = $1::uuid and entry_date = $2::date""", uid, add_months(today(), -12))
    if ya:
        body = ya["body"] or ""
        c1, c2 = st.columns([5, 1], vertical_alignment="center")
        c1.html(f'<div class="sh-nudge is-year">{ui.chip("notes", "⏳")}<div><strong>A year ago today you wrote</strong>'
                f'<div>{esc(body[:160])}{"…" if len(body) > 160 else ""}</div></div></div>')
        with c2:
            ui.go_button("journal", "Read", "year_read")
    if not journal.journal_get(uid, today()):
        try:
            prompt = journal.journal_prompt(uid, today())
        except Exception as e:  # noqa: BLE001
            print("[journal]", e)
            prompt = journal.journal_fallback_prompt(today())
        label = "This week's reflection" if journal.is_reflection_day(today()) else "Journal/reflection"
        c1, c2 = st.columns([5, 1], vertical_alignment="center")
        c1.html(f'<div class="sh-nudge">{ui.chip("notes", "📓")}<div><div class="small sh-muted">{label}</div>'
                f'<div class="sh-nudge-prompt">{esc(prompt)}</div></div></div>')
        with c2:
            ui.go_button("journal", "Write", "journal_write", primary=True)


# ---- Priority cards ---------------------------------------------------------------------------------
def appts_card() -> None:
    with ui.card("Appointments & reminders", "appt", "📅"):
        late = data.overdue_reminders(today())
        for r in late:
            r["occ_date"] = r["start_at"].date()
        late_ids = {r["id"] for r in late}
        a = [x for x in data.appts_between(today(), today() + timedelta(days=6))
             if not (x["kind"] == "reminder" and x["id"] in late_ids)]
        if not a and not late:
            ui.empty("Nothing in the next 7 days.")
            return
        total = len(late) + len(a)
        late = late[:APPT_CAP]
        a = a[:max(0, APPT_CAP - len(late))]
        if late:
            st.caption("**Overdue reminders**")
            for r in late:
                forms.appt_row(r, "today_late")
        days = list(dict.fromkeys(x["occ_date"] for x in a))
        for d in days:
            st.caption("**" + ("Today" if d == today() else "Tomorrow" if d == today() + timedelta(days=1) else fmt_day(d)) + "**")
            for r in [x for x in a if x["occ_date"] == d]:
                forms.appt_row(r, "today")
        if total > APPT_CAP:
            ui.link("appts", f"See all {total}", ":material/arrow_forward:")


def meals_card() -> None:
    with ui.card("Meals today", "meals", "🍽️"):
        m = data.meals_between(today(), today())
        if not m:
            ui.empty("Nothing planned. Add a meal on the Meals page.")
        for x in m:
            st.markdown(f"**{x['slot']}:** {x['meal_name']}" + (" " + ui.md_badge("Leftovers", "warning")
                                                                  if x.get("is_leftovers") else ""))


def notes_card() -> None:
    with ui.card("Notes", "notes", "🗒️"):
        d = db.get("""select * from notes where parent_id is null and not done
                      order by pinned desc, created_at desc limit 4""")
        if not d:
            ui.empty("No open notes.")
        else:
            cells = "".join(
                f'<div class="fh-sticky fh-note-{n["color"] if n.get("color") in NOTE_COLORS else "yellow"}" '
                f'style="min-height:0;padding:.7rem .7rem .4rem">'
                f'<div class="fh-sticky-body" style="font-size:1rem;display:-webkit-box;-webkit-line-clamp:4;'
                f'-webkit-box-orient:vertical;overflow:hidden">{"📌 " if n.get("pinned") else ""}{esc(n["body"])}</div>'
                f'<div class="fh-sticky-meta">— {esc(n.get("author") or "Someone")}</div></div>' for n in d)
            st.html(f'<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:.8rem;margin-top:.4rem">{cells}</div>')
        ui.link("notes", "Open notes", ":material/arrow_forward:")


def duties_card() -> None:
    with ui.card("Drop-off & pick-up", "kids", "🧒"):
        d = data.duties_between(today(), today())
        if not d:
            ui.empty("No drop-offs or pick-ups today.")
        for x in d:
            rows.duty_row(x, "today")


def chores_card() -> None:
    with ui.card("Chores to do", "chores", "🧹"):
        view_label = st.selectbox("Show", list(CHORE_VIEWS), key="today_chore_view", label_visibility="collapsed")
        view = CHORE_VIEWS[view_label]
        ch = [c for c in data.chores_for_date(today()) if not c.get("optional")]
        if not ch:
            ui.empty("No chores on the list.")
            return
        soon = today() + timedelta(days=7)
        if view == "due":   # daily and weekly always; others when due within a week or overdue
            ch = [c for c in ch if c["frequency"] in ("daily", "weekly") or c["status"] in ("soon", "overdue")
                  or (c["done"] and c["due_date"] <= soon)]
        elif view != "all":
            ch = [c for c in ch if c["frequency"] == view]
        if not ch:
            ui.empty(f"No {view_label.lower()} chores.")
            return
        order = list(FREQS.values())
        todo = sorted([c for c in ch if not c["done"]],
                      key=lambda c: (c["status"] != "overdue", order.index(c["frequency"]), c["due_date"], c["title"]))
        if not todo:
            ui.empty("All caught up!")
        for c in todo:
            rows.chore_row(c, "today", show_freq=view in ("due", "all"))
        done_n = sum(1 for c in ch if c["done"])
        if done_n:
            st.caption(f"{done_n} done so far")


def workouts_card() -> None:
    with ui.card("Workouts", "work", "🏃"):
        w = db.get("select * from workouts where workout_date = $1::date order by id", today())
        if not w:
            ui.empty("No workouts planned today.")
        for x in w:
            rows.workout_row(x, "today")


def bills_card() -> None:
    if not ui.can("money"):
        return
    with ui.card("Bills due soon", "bills", "💳"):
        b = [x for x in data.bills_for_month(today()) if not x["paid"] and x["due_date"] <= today() + timedelta(days=7)]
        if not b:
            ui.empty("Nothing due in the next 7 days.")
        for x in b:
            rows.bill_row(x, "today", today(), editable_amount=False)


def page() -> None:
    porch()
    school_run()
    verse_card()
    extras_card()
    banners()
    rows.duty_dialogs()
    # Priority order (phones stack these in this order): appointments, meals, notes, kids, chores,
    # workouts, bills.
    pairs = [(appts_card, meals_card), (notes_card, duties_card), (chores_card, workouts_card), (bills_card, None)]
    for left, right in pairs:
        c1, c2 = st.columns(2)
        with c1:
            left()
        if right:
            with c2:
                right()
