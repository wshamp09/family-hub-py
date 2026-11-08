"""Forms and rows shared by several pages: appointments & reminders (Appointments, Today, quick
add) and budget expenses (Bills, Budget). Dialog widgets rerun only the dialog, so fields that
depend on other fields (e.g. "All day" hides the time) update as you tap."""
from __future__ import annotations



import streamlit as st

from . import data, db, ui
from .config import APP_TZ, EXPENSE_CATS, REPEATS, TZ, has_text, nnum, nz, today
from .dates import fmt_day, fmt_time, hhmm, month_start

REPEAT_NAMES = {v: k for k, v in REPEATS.items()}


# ============================== Appointments & reminders =======================================
def _local(t):
    return t.astimezone(TZ) if t is not None and t.tzinfo else t


def appt_form(p: str, row: dict | None = None, kind: str = "appointment") -> dict:
    """Draw the fields (inside a dialog) and return what's entered."""
    is_new = row is None
    row = row or {}
    kind0 = kind if is_new else row["kind"]
    kinds = {"Appointment": "appointment", "Reminder": "reminder"}
    k = st.radio("Kind", list(kinds), index=list(kinds.values()).index(kind0), horizontal=True,
                 key=f"{p}_kind", label_visibility="collapsed")
    kind = kinds[k]
    title = st.text_input("What", value=row.get("title") or "",
                          placeholder="e.g. Pediatrician check-up / Renew car tags", key=f"{p}_title")
    who = st.text_input("For whom (optional)", value=row.get("who") or "", key=f"{p}_who")
    start = _local(row.get("start_at"))
    d = st.date_input("Date", value=start.date() if start else None, key=f"{p}_date", format="MM/DD/YYYY")
    all_day = st.checkbox("All day", value=(kind == "reminder") if is_new else bool(row.get("all_day")),
                          key=f"{p}_allday")
    st_t = en_t = None
    if not all_day:
        c1, c2 = st.columns(2)
        with c1:
            st_t = st.time_input("Time", value=start.time() if (start and not row.get("all_day")) else None,
                                 key=f"{p}_start", step=300)
        if kind == "appointment":
            with c2:
                end = _local(row.get("end_at"))
                en_t = st.time_input("Ends (optional)", value=end.time() if end and not row.get("all_day") else None,
                                     key=f"{p}_end", step=300)
    rep_label = st.selectbox("Repeats", list(REPEATS), index=list(REPEATS.values()).index(row.get("recurrence") or "none"),
                             key=f"{p}_rep")
    loc = st.text_input("Where", value=row.get("location") or "", key=f"{p}_loc") if kind == "appointment" else None
    notes = st.text_area("Notes", value=row.get("notes") or "", height=80, key=f"{p}_notes")
    return {"kind": kind, "title": nz(title), "who": nz(who), "date": d, "all_day": all_day,
            "start": data.local_ts(d, "00:00" if all_day else hhmm(st_t)) if d else None,
            "end": data.local_ts(d, hhmm(en_t)) if (d and en_t and not all_day and kind == "appointment") else None,
            "needs_time": not all_day and st_t is None, "rep": REPEATS[rep_label],
            "loc": nz(loc) if kind == "appointment" else None, "notes": nz(notes)}


def check_appt(f: dict) -> str | None:
    if not f["title"]:
        return "Say what it is."
    if f["date"] is None:
        return "Pick a date."
    if f["needs_time"]:
        return "Add a time or tick All day."
    return None


def appt_save(f: dict, aid=None, by: str | None = None) -> None:
    """Insert (aid None) or update an appointment / reminder."""
    if aid is None:
        db.run("""insert into appointments (kind, title, who, all_day, start_at, end_at, recurrence, location, notes, created_by)
                  values ($1, $2, $3, $4::boolean, ($5::timestamp at time zone $11), ($6::timestamp at time zone $11),
                          $7, $8, $9, $10)""",
               f["kind"], f["title"], f["who"], f["all_day"], f["start"], f["end"], f["rep"], f["loc"], f["notes"], by,
               APP_TZ)
    else:
        db.run("""update appointments set kind = $2, title = $3, who = $4, all_day = $5::boolean,
                    start_at = ($6::timestamp at time zone $11), end_at = ($7::timestamp at time zone $11),
                    recurrence = $8, location = $9, notes = $10 where id = $1""",
               int(aid), f["kind"], f["title"], f["who"], f["all_day"], f["start"], f["end"], f["rep"], f["loc"],
               f["notes"], APP_TZ)


@st.dialog("Appointment or reminder")
def appt_dialog(aid=None, kind: str = "appointment"):
    row = db.one("select * from appointments where id = $1", int(aid)) if aid else None
    f = appt_form("af", row, kind)
    c1, c2 = st.columns(2)
    if c1.button("Save", type="primary", use_container_width=True, key="af_save"):
        msg = check_appt(f)
        if msg:
            st.warning(msg)
        elif ui.try_db(appt_save, "Saved", f, aid, ui.user()["display_name"]):
            st.rerun()
    if c2.button("Cancel", use_container_width=True, key="af_cancel"):
        st.rerun()


def appt_when(r: dict) -> str:
    if r.get("all_day"):
        return "All day"
    return fmt_time(r["start_at"]) + (f"–{fmt_time(r['end_at'])}" if r.get("end_at") else "")


def _rem_done(key, rid):
    try:
        nxt = data.reminder_done(rid, bool(st.session_state[key]))
        if nxt:
            ui.flash(f"Done. Next one: {fmt_day(nxt)}")
    except Exception as e:  # noqa: BLE001
        st.toast(str(e), icon="⚠️")


def appt_row(r: dict, kp: str, show_date: bool = False, actions=None) -> None:
    reminder = r["kind"] == "reminder"
    label = f"**{r['title']}**"
    if reminder:
        label += " " + ui.md_badge("Reminder", "warning")
    if r["recurrence"] != "none":
        label += " " + ui.md_badge(REPEAT_NAMES.get(r["recurrence"], r["recurrence"]), "light")
    sub = " · ".join(x for x in [fmt_day(_local(r["start_at"]).date()) if show_date else None, appt_when(r),
                                 r.get("who") if has_text(r.get("who")) else None,
                                 r.get("location") if has_text(r.get("location")) else None] if x)
    if r.get("notes"):
        sub += f" · {r['notes']}"
    cols = st.columns([5, 3] if actions else [1], vertical_alignment="center")
    with cols[0]:
        if reminder:
            key = f"{kp}_rem_{r['id']}_{r.get('occ_date', '')}_{int(bool(r.get('done')))}"
            st.checkbox(f"~~{label}~~" if r.get("done") else label, value=bool(r.get("done")), key=key,
                        on_change=_rem_done, args=(key, r["id"]))
        else:
            st.markdown(label)
        st.caption(sub)
    if actions:
        with cols[1]:
            actions(r)


# ============================== Budget expenses ==================================================
FREQ_OPTS = {"Month": "monthly", "Quarter": "quarterly", "Year": "annual"}


def expense_form(p: str, row: dict | None = None) -> dict:
    row = row or {}
    ppl = ui.people()
    pid = {x["id"]: x["name"] for x in ppl}
    name = st.text_input("Expense", value=row.get("name") or "", placeholder="e.g. Gym membership", key=f"{p}_name")
    c1, c2 = st.columns(2)
    amount = c1.number_input("Amount ($)", value=row.get("amount"), min_value=0.0, step=1.0, format="%.2f",
                             key=f"{p}_amount")
    freq_l = c2.selectbox("Per", list(FREQ_OPTS), index=list(FREQ_OPTS.values()).index(row.get("frequency") or "monthly"),
                          key=f"{p}_freq")
    whose_opts = ["shared"] + list(pid)
    whose0 = row.get("default_payer_id") if row.get("budget_scope") == "personal" else "shared"
    c3, c4 = st.columns(2)
    whose = c3.selectbox("Whose", whose_opts, index=whose_opts.index(whose0) if whose0 in whose_opts else 0,
                         format_func=lambda v: "Shared (split 50/50)" if v == "shared" else pid.get(v, "?"),
                         key=f"{p}_whose")
    cat = c4.selectbox("Category", EXPENSE_CATS,
                       index=EXPENSE_CATS.index(row["category"]) if row.get("category") in EXPENSE_CATS else
                       EXPENSE_CATS.index("Other"), key=f"{p}_cat")
    shared = whose == "shared"
    track = st.checkbox("**Track & remind**", value=bool(row.get("track")) if row else False, key=f"{p}_track")
    due, start, rule, payer, alt, autopay = 1, month_start(today()), "fixed", None, None, False
    if track:
        st.caption("Shows on the Bills page each month and on Today when it's due.")
        c5, c6 = st.columns(2)
        due = int(c5.number_input("Due day", value=int(row.get("due_day") or 1), min_value=1, max_value=31, step=1,
                                  key=f"{p}_due"))
        start = c6.date_input("First due (month)", value=row.get("start_month") or month_start(today()),
                              key=f"{p}_start", format="MM/DD/YYYY")
        autopay = st.checkbox("On autopay (never overdue)", value=bool(row.get("autopay")), key=f"{p}_autopay")
        if shared:
            rules = {"Same person": "fixed", "Alternate monthly": "alternate"}
            rule = rules[st.radio("Who pays", list(rules), horizontal=True,
                                  index=list(rules.values()).index(row.get("payer_rule") or "fixed"), key=f"{p}_rule")]
            opts = [None] + list(pid)
            fmt = lambda v: "—" if v is None else pid.get(v, "?")  # noqa: E731
            c7, c8 = st.columns(2)
            cur = row.get("default_payer_id") if row.get("budget_scope") != "personal" else None
            payer = c7.selectbox("Payer", opts, index=opts.index(cur) if cur in opts else 0, format_func=fmt,
                                 key=f"{p}_payer")
            if rule == "alternate":
                alt = c8.selectbox("Alternates with", opts,
                                   index=opts.index(row.get("alt_payer_id")) if row.get("alt_payer_id") in opts else 0,
                                   format_func=fmt, key=f"{p}_alt")
    notes = st.text_input("Notes", value=row.get("notes") or "", key=f"{p}_notes")
    return {"name": nz(name), "amount": nnum(amount), "freq": FREQ_OPTS[freq_l], "scope": "shared" if shared else "personal",
            "payer": (None if shared else whose) if not (shared and track) else payer, "cat": cat, "track": track,
            "due": max(1, min(31, due)), "start": month_start(start or today()),
            "rule": rule if (shared and track) else "fixed", "alt": alt if rule == "alternate" else None,
            "autopay": track and autopay, "notes": nz(notes)}


def check_expense(f: dict) -> str | None:
    if not f["name"]:
        return "Name the expense."
    if f["amount"] is None:
        return "Enter the amount."
    if f["rule"] == "alternate" and (f["payer"] is None or f["alt"] is None):
        return "Pick both people who alternate."
    return None


def save_expense(f: dict, eid=None) -> None:
    vals = [f["name"], f["cat"], f["amount"], f["freq"], f["scope"], f["payer"], f["track"], f["due"], f["start"],
            f["rule"], f["alt"], f["autopay"], f["notes"]]
    if eid is None:
        db.run("""insert into bills (name, category, amount, frequency, budget_scope, default_payer_id, track, due_day,
                                     start_month, payer_rule, alt_payer_id, autopay, notes)
                  values ($1, $2, $3, $4, $5, $6, $7::boolean, $8, $9::date, $10, $11, $12::boolean, $13)""", *vals)
    else:
        db.run("""update bills set name = $1, category = $2, amount = $3, frequency = $4, budget_scope = $5,
                    default_payer_id = $6, track = $7::boolean, due_day = $8, start_month = $9::date,
                    payer_rule = $10, alt_payer_id = $11, autopay = $12::boolean, notes = $13
                  where id = $14""", *vals, int(eid))


@st.dialog("Expense")
def expense_dialog(eid=None, defaults: dict | None = None):
    if not ui.can("money"):
        st.stop()
    row = db.one("select * from bills where id = $1", int(eid)) if eid else defaults
    f = expense_form("xe", row)
    c1, c2, c3 = st.columns(3)
    if c1.button("Save", type="primary", use_container_width=True, key="xe_save"):
        msg = check_expense(f)
        if msg:
            st.warning(msg)
        elif ui.try_db(save_expense, "Saved", f, eid):
            st.rerun()
    if c2.button("Cancel", use_container_width=True, key="xe_cancel"):
        st.rerun()
    if eid:
        with c3.popover("Delete", use_container_width=True):
            st.write("Delete this expense? Past payment records are kept.")
            if st.button("Yes, delete", type="primary", key="xe_del"):
                if ui.try_db(db.run, "Deleted", "update bills set active = false where id = $1", int(eid)):
                    st.rerun()
