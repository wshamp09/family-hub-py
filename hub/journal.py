"""Journal/reflection: AI-written prompts and private entries.
Each person's entries are private (always filtered by their login's user_id). Every day the AI
writes a fresh prompt for each person (often naming the kids); Sundays get a deeper weekly
reflection. "New prompt" asks for another; "Prompt me" uses a chosen theme. The day's prompt is
saved, so it stays the same until you ask for a new one."""
from __future__ import annotations

from datetime import date, timedelta

from . import db, groq
from .config import today
from .dates import day_num

JOURNAL_THEMES = ["Gratitude", "Patience", "Marriage", "The kids", "Faith", "Growing as a parent",
                  "Fun memories", "Hard days"]
# Used only when the AI can't be reached.
JOURNAL_FALLBACK = ["What's one moment from today you want to remember?", "What made you smile today?"]
JOURNAL_FALLBACK_SUNDAY = ("Looking back on this week, what went well, and what would you like to carry "
                           "into next week?")


def kids_names() -> list[str]:
    return [k.strip() for k in db.get_setting("kids_names", "").split(",") if k.strip()]


def join_names(n: list[str]) -> str:
    if not n:
        return "the kids"
    if len(n) == 1:
        return n[0]
    return ", ".join(n[:-1]) + " and " + n[-1]


def is_reflection_day(day: date) -> bool:
    return day.isoweekday() == 7     # Sunday


def journal_fallback_prompt(day: date) -> str:
    return JOURNAL_FALLBACK_SUNDAY if is_reflection_day(day) else JOURNAL_FALLBACK[day_num(day) % len(JOURNAL_FALLBACK)]


def journal_ai_prompt(day: date | None = None, theme: str | None = None, kids: list[str] | None = None,
                      avoid: list[str] | None = None) -> str:
    """Ask the AI for one prompt. theme None = a varied daily prompt."""
    day = day or today()
    kids = kids_names() if kids is None else kids
    if theme:
        kind = f"Theme: {theme}"
    elif is_reflection_day(day):
        kind = "It's Sunday: write a deeper weekly reflection that looks back on the past week and ahead to the next one."
    else:
        kind = ("Vary the kind of prompt: a memory of the kids, gratitude, a feeling, marriage, faith, "
                "growing as a parent, or something light.")
    sys = ("You write one warm, specific journal prompt for a parent of young children. Reply with JSON only: "
           '{"prompt": "..."}. One or two questions, under 30 words, easy to start writing in a minute. Avoid cliches.')
    usr = (f"{kind} Children: {join_names(kids)} (mention one by name only if it fits). Today is "
           f"{day.strftime('%A, %B %d')}." + (f" Don't repeat these: {' | '.join(avoid)}" if avoid else ""))
    p = str(groq.chat_json(sys, usr, temperature=0.95).get("prompt") or "").strip()
    if not p:
        raise RuntimeError("The AI didn't return a prompt.")
    return p


def journal_save_prompt(user_id: str, day: date, prompt: str) -> None:
    db.run("""insert into journal_prompts (user_id, prompt_date, prompt) values ($1::uuid, $2::date, $3)
              on conflict (user_id, prompt_date) do update set prompt = excluded.prompt""", user_id, day, prompt)


def new_journal_prompt(user_id: str, day: date | None = None, theme: str | None = None) -> str:
    """A new AI prompt for the day (saved). Falls back to a simple prompt if the AI is unavailable."""
    day = day or today()
    recent = [r["prompt"] for r in db.get("""select prompt from journal_prompts
                                              where user_id = $1::uuid and prompt_date >= $2::date""",
                                          user_id, day - timedelta(days=30))]
    try:
        p = journal_ai_prompt(day, theme, avoid=recent)
    except Exception as e:  # noqa: BLE001
        print(f"[journal] AI prompt failed: {e}")
        return journal_fallback_prompt(day)      # not saved, so it's tried again later
    journal_save_prompt(user_id, day, p)
    return p


def journal_prompt(user_id: str, day: date | None = None) -> str:
    """Today's prompt for one person: the saved one, or a fresh AI prompt the first time."""
    day = day or today()
    r = db.one("select prompt from journal_prompts where user_id = $1::uuid and prompt_date = $2::date", user_id, day)
    return r["prompt"] if r else new_journal_prompt(user_id, day)


def journal_get(user_id: str, day: date) -> dict | None:
    return db.one("select * from journal_entries where user_id = $1::uuid and entry_date = $2::date", user_id, day)


def journal_save(user_id: str, day: date, prompt: str, body: str) -> None:
    db.run("""insert into journal_entries (user_id, entry_date, prompt, body) values ($1::uuid, $2::date, $3, $4)
              on conflict (user_id, entry_date) do update
                set prompt = excluded.prompt, body = excluded.body, updated_at = now()""", user_id, day, prompt, body)


def journal_on_this_day(user_id: str, day: date | None = None) -> list[dict]:
    """Entries written on this day of the month in earlier years (newest first)."""
    return db.get("""select * from journal_entries
                      where user_id = $1::uuid and entry_date < $2::date
                        and extract(month from entry_date) = extract(month from $2::date)
                        and extract(day from entry_date) = extract(day from $2::date)
                      order by entry_date desc""", user_id, day or today())
