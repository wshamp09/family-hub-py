"""Daily Bible verse. References come from a curated list of popular verses (or the AI, for a
theme); the exact wording always comes from bible-api.com, never from the AI.
Translation: King James Version ("kjv"). Others bible-api.com offers: web, asv, bbe, darby, ylt,
oeb-us. Changing it re-fetches saved verses once (see sync_verse_translation)."""
from __future__ import annotations

import random
import re
from datetime import date, timedelta
from urllib.parse import quote

import requests

from . import db, groq
from .config import cfg, today

BIBLE_TRANSLATION = cfg("BIBLE_TRANSLATION", "kjv")

POPULAR_VERSES = [
    "John 3:16",
    "Jeremiah 29:11",
    "Philippians 4:13",
    "Romans 8:28",
    "Proverbs 3:5-6",
    "Isaiah 41:10",
    "Psalm 23:1-3",
    "Matthew 11:28-30",
    "Joshua 1:9",
    "Philippians 4:6-7",
    "Romans 12:2",
    "Galatians 5:22-23",
    "2 Timothy 1:7",
    "1 Corinthians 13:4-7",
    "Psalm 46:1",
    "Isaiah 40:31",
    "Matthew 6:33",
    "Romans 15:13",
    "Hebrews 11:1",
    "Psalm 118:24",
    "Lamentations 3:22-23",
    "Psalm 37:4",
    "1 Peter 5:7",
    "Ephesians 4:32",
    "Colossians 3:12-14",
    "Micah 6:8",
    "Matthew 5:14-16",
    "Matthew 7:12",
    "Luke 6:31",
    "1 John 4:7-8",
    "John 13:34-35",
    "Romans 12:10",
    "Galatians 6:2",
    "Galatians 6:9",
    "Hebrews 13:16",
    "Proverbs 16:3",
    "Proverbs 16:9",
    "Proverbs 22:6",
    "Psalm 127:3",
    "Joshua 24:15",
    "Deuteronomy 6:6-7",
    "Ephesians 6:1-4",
    "Colossians 3:20-21",
    "Psalm 139:14",
    "Psalm 121:1-2",
    "Psalm 34:18",
    "Psalm 55:22",
    "Psalm 91:1-2",
    "Psalm 16:8",
    "Psalm 27:1",
    "Psalm 28:7",
    "Psalm 32:8",
    "Psalm 62:1-2",
    "Psalm 103:2-5",
    "Psalm 107:1",
    "1 Thessalonians 5:16-18",
    "Colossians 3:23",
    "1 Corinthians 16:14",
    "Ecclesiastes 3:1",
    "James 1:5",
    "James 1:17",
    "James 1:19",
    "Proverbs 15:1",
    "Proverbs 17:17",
    "Proverbs 18:10",
    "Proverbs 31:25",
    "Isaiah 26:3",
    "Isaiah 43:2",
    "Isaiah 54:10",
    "Zephaniah 3:17",
    "Nahum 1:7",
    "Deuteronomy 31:6",
    "Numbers 6:24-26",
    "Matthew 5:9",
    "Matthew 6:34",
    "Matthew 19:26",
    "Mark 10:27",
    "Luke 1:37",
    "John 14:27",
    "John 16:33",
    "Romans 5:8",
    "Romans 8:38-39",
    "Romans 12:12",
    "2 Corinthians 5:17",
    "2 Corinthians 12:9",
    "Ephesians 2:8-9",
    "Ephesians 3:20",
    "Philippians 1:6",
    "Philippians 4:8",
    "Philippians 4:19",
    "Colossians 3:15",
    "2 Thessalonians 3:16",
    "Hebrews 12:1-2",
    "Hebrews 13:5",
    "1 Peter 4:8",
    "1 John 1:9",
    "1 John 4:18",
    "Psalm 19:14",
    "Psalm 51:10",
    "Psalm 90:12",
    "Psalm 119:105",
    "Psalm 145:9",
    "Psalm 147:3",
    "Proverbs 4:23",
    "Proverbs 11:25",
    "Isaiah 30:15",
    "Romans 15:7",
    "1 Corinthians 15:58",
    "Galatians 5:13-14",
    "Ephesians 4:2-3",
]


def fetch_verse(reference: str, translation: str | None = None) -> dict | None:
    """Exact text for a reference, or None if it isn't valid / the service is down."""
    try:
        r = requests.get(f"https://bible-api.com/{quote(reference)}",
                         params={"translation": translation or BIBLE_TRANSLATION}, timeout=15)
    except requests.RequestException as e:
        print(f"[verse] fetch failed: {e}")
        return None
    if r.status_code >= 300:
        return None
    try:
        b = r.json()
    except ValueError:
        return None
    if not b.get("text"):
        return None
    return {"reference": b.get("reference") or reference, "text": re.sub(r"\s+", " ", b["text"]).strip(),
            "translation": b.get("translation_name") or (translation or BIBLE_TRANSLATION).upper()}


def get_daily_verse(day: date | None = None) -> dict | None:
    """Today's verse: the same for everyone, picked from the list (avoiding the last 60 days),
    fetched once and stored."""
    day = day or today()
    v = db.one("select reference, verse_text, translation from daily_verse where verse_date = $1::date", day)
    if v:
        return v
    recent = {r["reference"] for r in db.get("select reference from daily_verse where verse_date >= $1::date",
                                              day - timedelta(days=60))}
    pool = [r for r in POPULAR_VERSES if r not in recent] or POPULAR_VERSES
    # Deterministic per day, so two people opening the app at the same moment get the same verse.
    ref = pool[(day.toordinal() - 719163) * 7919 % len(pool)]
    print(f"[verse] today's verse: {ref}")
    f = fetch_verse(ref) or {}
    db.run("""insert into daily_verse (verse_date, reference, verse_text, translation)
              values ($1::date, $2, $3, $4) on conflict (verse_date) do nothing""",
           day, f.get("reference", ref), f.get("text"), f.get("translation"))
    return db.one("select reference, verse_text, translation from daily_verse where verse_date = $1::date", day)


def verse_for_theme(theme: str) -> dict:
    """The AI suggests references, the API supplies the exact text."""
    sys = ('You suggest Bible verses. Reply with JSON only: {"references": ["Book Chapter:Verse", ...]} '
           "with 3 well-known, real references that fit the theme. Use standard English book names; "
           "a short range like 4:6-7 is fine.")
    out = groq.chat_json(sys, f"Theme: {theme}", temperature=0.9)
    for r in out.get("references") or []:
        f = fetch_verse(str(r))
        if f:
            return f
    raise RuntimeError("Couldn't find a verse for that theme. Try different words.")


def random_verse() -> dict:
    for r in random.sample(POPULAR_VERSES, 3):
        f = fetch_verse(r)
        if f:
            return f
    raise RuntimeError("The verse service didn't respond. Try again shortly.")


def sync_verse_translation() -> int:
    """After the translation changes, re-fetch saved verses and today's (and any later) verse in the
    new one, once. Runs at sign-in."""
    if db.get_setting("verse_translation", "") == BIBLE_TRANSLATION:
        return 0
    sv = db.get("select id, reference from saved_verses")
    dv = db.get("select verse_date, reference from daily_verse where verse_date >= $1::date", today())
    n, done, failed = len(sv) + len(dv), 0, 0
    print(f"[verse] switching {n} verse(s) to {BIBLE_TRANSLATION}")
    for r in sv:
        f = fetch_verse(r["reference"])
        if f is None:
            failed += 1
        else:
            db.run("update saved_verses set verse_text = $2, translation = $3 where id = $1", r["id"], f["text"],
                   f["translation"])
        done += 1
        print(f"[verse]   {done} of {n}: {r['reference']}")
    for r in dv:
        f = fetch_verse(r["reference"])
        if f is None:
            failed += 1
        else:
            db.run("update daily_verse set verse_text = $2, translation = $3 where verse_date = $1::date",
                   r["verse_date"], f["text"], f["translation"])
        done += 1
        print(f"[verse]   {done} of {n}: {r['reference']}")
    # Only mark it done when everything came back, so a hiccup is retried at the next sign-in.
    if failed == 0:
        db.set_setting("verse_translation", BIBLE_TRANSLATION)
    else:
        print(f"[verse] {failed} verse(s) couldn't be fetched; will retry at next sign-in")
    return n
