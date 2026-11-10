"""Gratitude jar: one short note a day for each person, shared with the family.

Each date of the year has its own simple prompt (gratitude_prompts.txt, 366 lines, themed by month), the same
for everyone, which you can follow or ignore. Today shows the day's notes and one note pulled "from the jar": an earlier
note, the same for everyone that day."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from . import db
from .dates import day_num

GRATITUDE_MAX = 300
PROMPTS_FILE = Path(__file__).parent / "gratitude_prompts.txt"


def load_prompts() -> list[str]:
    """The 366 prompts, January 1 first (lines starting with # are notes)."""
    return [ln.strip() for ln in PROMPTS_FILE.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]


GRATITUDE_PROMPTS = load_prompts()


def prompt_index(day: date) -> int:
    """Line for a date: its place in a leap year (Jan 1 = 0 ... Dec 31 = 365), so each date keeps its own
    prompt every year and February 29's is used only in leap years."""
    return (date(2024, day.month, day.day) - date(2024, 1, 1)).days


def prompt_for(day: date) -> str:
    """The day's prompt: one for each date of the year, the same for everyone."""
    return GRATITUDE_PROMPTS[prompt_index(day) % len(GRATITUDE_PROMPTS)]


def notes_on(day: date) -> list[dict]:
    return db.get("""select * from gratitude where entry_date = $1::date order by created_at""", day)


def save(uid: str, name: str, day: date, prompt: str, text: str) -> None:
    """One note a day each: saving again the same day updates it."""
    db.run("""insert into gratitude (entry_date, user_id, author_name, prompt, body)
              values ($1::date, $2::uuid, $3, $4, $5)
              on conflict (entry_date, user_id) do update
                set body = excluded.body, author_name = excluded.author_name, updated_at = now()""",
           day, uid, name, prompt, text.strip()[:GRATITUDE_MAX])


def delete(note_id: int, uid: str) -> None:
    db.run("delete from gratitude where id = $1 and user_id = $2::uuid", int(note_id), uid)


def pick_index(n: int, day: date) -> int | None:
    """Which earlier note comes 'from the jar' today (the same all day). Pure, for tests."""
    return (day_num(day) * 7919) % n if n > 0 else None


def from_the_jar(day: date) -> dict | None:
    n = int(db.value("select count(*) from gratitude where entry_date < $1::date", day) or 0)
    i = pick_index(n, day)
    if i is None:
        return None
    return db.one("""select * from gratitude where entry_date < $1::date order by id limit 1 offset $2""", day, i)


def shake(day: date, exclude_id: int | None = None) -> dict | None:
    """A random earlier note, for 'Shake the jar'."""
    return db.one("""select * from gratitude where entry_date < $1::date and id <> coalesce($2, -1)
                     order by random() limit 1""", day, exclude_id)


def search(q: str = "", who: str | None = None, limit: int = 200) -> list[dict]:
    like = f"%{q.strip()}%" if q and q.strip() else "%"
    return db.get("""select * from gratitude where (body ilike $1 or coalesce(prompt, '') ilike $1)
                     and ($2::uuid is null or user_id = $2::uuid)
                     order by entry_date desc, created_at limit $3""", like, who, limit)
