"""Daily learning: four short lessons a day for grown-ups, plus a knowledge check.

How a day's lessons are made (once a day, then saved in daily_extras and shared by everyone):
  1. AI picks one topic per subject, each tied to a real English Wikipedia article, avoiding recent topics.
  2. Each article is looked up on Wikipedia (title, picture, link and the article text).
  3. AI writes each lesson ONLY from that article's text, plus 3 multiple-choice questions on the lessons.
Reading time is worked out from the lesson's word count (LEARN_WPM words a minute, at least 1 minute).
Who has read what, and knowledge-check answers, are kept per login in learn_log."""
from __future__ import annotations

import json
import math
import re
import time
from datetime import date, timedelta

from . import db, groq
from .extras import get_json

LEARN_TRACKS = {"adult": "Grown-ups"}     # the track key is kept in saved lessons and learn_log
LEARN_SUBJECTS = {            # key: (label, emoji, section colour, what the subject covers)
    "science": ("Science", "🔭", "appt", "space, physics, chemistry, earth science, animals and plants"),
    "history": ("History", "🏛️", "bills", "world and American history, inventions, famous places and people from the past"),
    "money": ("Money", "💵", "meals", "personal finance, how money and the economy work, saving, investing, taxes"),
    "health": ("Health & how things work", "⚙️", "work",
               "the human body, health and nutrition science, everyday technology and how machines work"),
}
LEARN_WPM = {"adult": 200}                     # reading speed, words a minute
LEARN_NO_REPEAT_DAYS = 180
LEARN_ARTICLE_CHARS = 3500                     # how much of each article the AI is given (keeps each request
                                               # well under Groq's free per-minute token limit)
LEARN_QUIZ_N = 3
WIKI_API = "https://en.wikipedia.org/w/api.php"


# ---- Small pure helpers (tested in check_setup.py) --------------------------------------------------
def reading_minutes(text: str, track: str) -> int:
    words = len(re.findall(r"\b\w+\b", text or ""))
    return max(1, math.ceil(words / LEARN_WPM.get(track, 200)))


def trim_article(text: str, limit: int = LEARN_ARTICLE_CHARS) -> str:
    """Drop the reference sections and cut to whole paragraphs within the limit."""
    text = re.split(r"\n=+\s*(See also|References|Notes|External links|Further reading|Bibliography)\s*=+",
                    text or "")[0]
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    return cut[:cut.rfind("\n")].strip() if "\n" in cut else cut


def subject_key(x) -> str:
    """'Science', 'science' or 'Health & how things work' -> the subject's key ('' if it isn't one)."""
    t = re.sub(r"[^a-z]", "", str(x or "").lower())
    for k, (label, *_) in LEARN_SUBJECTS.items():
        if t and (t == k or t == re.sub(r"[^a-z]", "", label.lower()) or t.startswith(k)):
            return k
    return ""


def _answer_index(a, choices: list[str]):
    """The correct choice's position from a 0-based number, a letter (A-E) or the choice's own text."""
    if isinstance(a, bool):
        return None
    if isinstance(a, int):
        return a
    t = str(a or "").strip()
    low = [c.lower() for c in choices]
    plain = re.sub(r"^\(?[A-Ea-e][).:]\s+", "", t).lower()
    if plain in low:                       # the choice's own text wins (choices can be numbers or letters)
        return low.index(plain)
    if re.fullmatch(r"\d+", t):
        return int(t)
    m = re.fullmatch(r"\(?([A-Ea-e])[).:]?", t)
    return "abcde".index(m.group(1).lower()) if m else None


def clean_quiz(qs, n: int = LEARN_QUIZ_N) -> list[dict]:
    """Keep well-formed questions: 3-5 different choices and a correct answer that's one of them.
    Accepts the answer as a 0-based number, a letter or the choice's text, and drops 'A) ' labels."""
    out = []
    for q in qs or []:
        if not isinstance(q, dict):
            continue
        ch = [re.sub(r"^\(?[A-Ea-e][).:]\s+", "", str(c).strip()) for c in (q.get("choices") or q.get("options") or [])]
        ch = [c for c in ch if c]
        a = _answer_index(next((q[k] for k in ("answer", "answer_index", "correct", "correct_answer") if k in q), None), ch)
        if str(q.get("question") or "").strip() and 3 <= len(ch) <= 5 and len(set(ch)) == len(ch) \
                and a is not None and 0 <= a < len(ch):
            out.append({"question": str(q["question"]).strip(), "choices": ch, "answer": a,
                        "why": str(q.get("why") or q.get("explanation") or "").strip(),
                        "subject": subject_key(q.get("subject"))})
    return out[:n]


def learn_streak(days_done: set[date], today_d: date) -> int:
    """Days in a row with at least one lesson read or question answered (today, or up to yesterday)."""
    d = today_d if today_d in days_done else today_d - timedelta(days=1)
    n = 0
    while d in days_done:
        n += 1
        d -= timedelta(days=1)
    return n


# ---- Wikipedia --------------------------------------------------------------------------------------
def wiki_article(title: str) -> dict | None:
    """Article text, picture and link for a title (follows redirects; falls back to a search)."""
    def lookup(t):
        j = get_json(WIKI_API, params={"action": "query", "titles": t, "redirects": 1, "format": "json",
                                       "formatversion": 2, "prop": "extracts|pageimages|info", "explaintext": 1,
                                       "exsectionformat": "wiki", "piprop": "thumbnail", "pithumbsize": 640,
                                       "inprop": "url"})
        pages = (j.get("query") or {}).get("pages") or []
        p = pages[0] if pages else {}
        if p.get("missing") or not p.get("extract") or len(p["extract"]) < 800:
            return None
        return {"title": p["title"], "text": trim_article(p["extract"]),
                "image": (p.get("thumbnail") or {}).get("source", ""), "url": p.get("fullurl", "")}
    a = lookup(title)
    if a:
        return a
    s = get_json(WIKI_API, params={"action": "query", "list": "search", "srsearch": title, "srlimit": 1,
                                   "format": "json", "formatversion": 2})
    hits = (s.get("query") or {}).get("search") or []
    return lookup(hits[0]["title"]) if hits else None


# ---- AI steps ---------------------------------------------------------------------------------------
def _audience(track: str) -> str:
    return "curious adults (parents of young children)"


def pick_topics(track: str, avoid: list[str]) -> dict:
    subj = "\n".join(f'- "{k}": {v[0]} ({v[3]})' for k, v in LEARN_SUBJECTS.items())
    sys = ("You choose one short daily lesson topic per subject for " + _audience(track) + ". "
           "Each topic must be covered well by ONE existing English Wikipedia article; give its exact title. "
           "Prefer interesting, concrete questions over broad surveys. "
           'Return JSON: {"topics": {"<subject key>": {"article": "<Wikipedia title>", '
           '"question": "<the lesson as a short, friendly question, under 10 words>"}}}.')
    usr = (f"Subjects:\n{subj}\n" + (f"Don't use these recent articles: {' | '.join(avoid[-120:])}" if avoid else ""))
    return (groq.chat_json(sys, usr, temperature=1).get("topics") or {})


def write_lessons(track: str, arts: dict) -> dict:
    style = ("Clear and engaging, 280 to 420 words, short paragraphs, with one concrete example. "
             "End with a one-line 'Takeaway'.")
    sys = ("You write short daily lessons for " + _audience(track) + ". Use ONLY facts stated in the article text "
           "given for each subject; don't add facts from elsewhere. If the article doesn't support a point, leave "
           "it out. " + style + " Then write " + str(LEARN_QUIZ_N) + " multiple-choice questions whose answers are "
           "stated in the lessons (each with 3 or 4 choices, one correct). "
           'Return JSON: {"lessons": {"<subject key>": {"title": "<the question>", "hook": "<one sentence>", '
           '"body": "<the lesson, plain text paragraphs separated by blank lines>"}}, '
           '"quiz": [{"subject": "<subject key>", "question": "...", "choices": ["..."], "answer": <0-based index>, '
           '"why": "<one sentence>"}]}.')
    usr = "\n\n".join(f'### Subject "{k}" — lesson question: {a["question"]}\nArticle "{a["title"]}":\n{a["text"]}'
                      for k, a in arts.items())
    return groq.chat_json(sys, usr, temperature=0.5)


def write_quiz(lessons: list[dict]) -> list:
    """A second try at the knowledge check, from the finished lessons."""
    sys = ("Write " + str(LEARN_QUIZ_N) + " multiple-choice questions whose answers are stated in the lessons below. "
           "Each has exactly 4 different choices and one correct answer. "
           'Return JSON: {"quiz": [{"subject": "<subject key>", "question": "...", "choices": ["...", "...", "...", "..."], '
           '"answer": <0-based index of the correct choice>, "why": "<one sentence>"}]}.')
    usr = "\n\n".join(f'Subject key "{l["subject"]}": {l["title"]}\n{l["body"]}' for l in lessons)
    return groq.chat_json(sys, usr, temperature=0.3).get("quiz") or []


def _recent_articles(track: str, day: date) -> list[str]:
    out = []
    for r in db.get("""select content from daily_extras where kind = $1 and extra_date >= $2::date
                       and extra_date < $3::date order by extra_date""",
                    f"learn_{track}", day - timedelta(days=LEARN_NO_REPEAT_DAYS), day):
        try:
            out += [l["article"] for l in json.loads(r["content"]).get("lessons", [])]
        except (ValueError, TypeError, KeyError, AttributeError):
            pass
    return out


def make_day(track: str, day: date, progress=print) -> dict:
    """Build one track's lessons for a day. progress(msg) gets a line at each step."""
    recent = _recent_articles(track, day)
    arts, tried = {}, list(recent)
    for rnd in (1, 2):              # a second round fills subjects whose article was missing or used recently
        progress("Choosing today's topics…" if rnd == 1 else "Choosing replacement topics…")
        topics = pick_topics(track, tried)
        todo = [k for k in LEARN_SUBJECTS if k not in arts]
        for i, k in enumerate(todo, 1):
            t = topics.get(k) or {}
            progress(f"Reading Wikipedia ({i}/{len(todo)}): {t.get('article', LEARN_SUBJECTS[k][0])}")
            a = wiki_article(str(t.get("article") or "")) if t.get("article") else None
            if t.get("article"):
                tried.append(str(t["article"]))
            if a and a["title"] not in tried[:len(recent)] and all(a["title"] != x["title"] for x in arts.values()):
                arts[k] = dict(a, question=str(t.get("question") or a["title"]))
        if len(arts) == len(LEARN_SUBJECTS):
            break
    if len(arts) < 2:
        raise RuntimeError("couldn't find enough Wikipedia articles today")
    progress("Writing the lessons…")
    w = write_lessons(track, arts)
    got = w.get("lessons") or {}
    lessons = []
    for k, a in arts.items():
        l = got.get(k) or {}
        body = str(l.get("body") or "").strip()
        if len(body) < 200:
            continue
        lessons.append({"subject": k, "title": str(l.get("title") or a["question"]).strip(),
                        "hook": str(l.get("hook") or "").strip(), "body": body,
                        "minutes": reading_minutes(body, track), "article": a["title"], "url": a["url"],
                        "image": a["image"]})
    if not lessons:
        raise RuntimeError("no lessons came back")
    keep = {l["subject"] for l in lessons}
    quiz = [q for q in clean_quiz(w.get("quiz")) if q["subject"] in keep or not q["subject"]]
    if len(quiz) < LEARN_QUIZ_N:
        progress("Writing the knowledge check…")
        try:
            more = [q for q in clean_quiz(write_quiz(lessons)) if q["subject"] in keep or not q["subject"]]
            have = {q["question"] for q in quiz}
            quiz += [q for q in more if q["question"] not in have][:LEARN_QUIZ_N - len(quiz)]
        except Exception as e:  # noqa: BLE001
            print(f"[learn] knowledge check failed: {e}")
    progress("Done")
    return {"track": track, "lessons": lessons, "quiz": quiz}


_fail: dict = {}
LEARN_RETRY_MIN = 30


def get_day(track: str, day: date, progress=print) -> dict | None:
    """Today's saved lessons for a track; builds them the first time they're needed (shared with everyone).
    If building fails, it isn't tried again for LEARN_RETRY_MIN minutes."""
    saved = saved_day(track, day)
    if saved and not saved.get("quiz") and (track, day, "quiz") not in _fail:
        _fail[(track, day, "quiz")] = time.time()        # one top-up try per day (per app start)
        try:
            keep = {l["subject"] for l in saved["lessons"]}
            quiz = [q for q in clean_quiz(write_quiz(saved["lessons"])) if q["subject"] in keep or not q["subject"]]
            if quiz:
                saved["quiz"] = quiz
                db.run("update daily_extras set content = $3 where extra_date = $1::date and kind = $2",
                       day, f"learn_{track}", json.dumps(saved))
        except Exception as e:  # noqa: BLE001
            print(f"[learn] knowledge check top-up failed: {e}")
    if saved:
        return saved
    last = _fail.get((track, day))
    if last and (time.time() - last) < LEARN_RETRY_MIN * 60:
        return None
    try:
        val = make_day(track, day, progress)
    except Exception as e:  # noqa: BLE001
        print(f"[learn] {track} failed: {e}")
        _fail[(track, day)] = time.time()
        return None
    db.run("""insert into daily_extras (extra_date, kind, content) values ($1::date, $2, $3)
              on conflict (extra_date, kind) do nothing""", day, f"learn_{track}", json.dumps(val))
    return saved_day(track, day) or val     # if two people built it at once, everyone gets the saved one


def saved_day(track: str, day: date) -> dict | None:
    """Only what's already saved (Today uses this, so it never waits for lessons to be written)."""
    r = db.one("select content from daily_extras where extra_date = $1::date and kind = $2", day, f"learn_{track}")
    return json.loads(r["content"]) if r else None


# ---- Progress per login -----------------------------------------------------------------------------
def log_for(uid: str, day: date, track: str) -> dict:
    return {r["item"]: r for r in db.get("""select item, answer, correct from learn_log
                                             where user_id = $1::uuid and learn_date = $2::date and track = $3""",
                                          uid, day, track)}


def mark_read(uid: str, day: date, track: str, subject: str) -> None:
    db.run("""insert into learn_log (learn_date, track, item, user_id) values ($1::date, $2, $3, $4::uuid)
              on conflict (learn_date, track, item, user_id) do nothing""", day, track, subject, uid)


def answer(uid: str, day: date, track: str, qi: int, choice: int, correct: bool) -> None:
    db.run("""insert into learn_log (learn_date, track, item, user_id, answer, correct)
              values ($1::date, $2, $3, $4::uuid, $5, $6::boolean)
              on conflict (learn_date, track, item, user_id) do nothing""",
           day, track, f"q{qi}", uid, choice, correct)


def streak(uid: str, today_d: date) -> int:
    days = {r["learn_date"] for r in db.get("""select distinct learn_date from learn_log where user_id = $1::uuid
                                                and learn_date >= $2::date""", uid, today_d - timedelta(days=400))}
    return learn_streak(days, today_d)
