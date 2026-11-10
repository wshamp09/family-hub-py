"""Today's extras: trivia, quote, word, history, animal, art, recipe, dinner question.
Each is fetched once a day from its source, saved (daily_extras), and shown to everyone that day:
  history  Wikipedia "On this day" (selected events), 1-2 items
  dinner   a conversation starter written by AI (Groq), avoiding recent ones
  space    NASA's Astronomy Picture of the Day (api.nasa.gov; NASA_API_KEY optional)
  recipe   a random main-dish recipe with a photo, from TheMealDB (free key "1", personal use)
  animal   a wild animal spotted near home in the last two weeks, from iNaturalist (photo credited)
  quote    ZenQuotes quote of the day (zenquotes.io; credit link required)
  word     Merriam-Webster's Word of the Day (free daily feed)
  art      a public-domain painting from the Art Institute of Chicago
  trivia   a multiple-choice question from the Open Trivia Database (see hub/trivia.py)
If a source can't be reached, that line is skipped and tried again in 30 minutes."""
from __future__ import annotations

import json
import re
import time
from datetime import date, timedelta

import requests

from . import db, groq
from .config import has_text, today
from .dates import day_num
from .data import join_names, kids_names

EXTRA_UA = "TheShampHouse/1.0 (family organizer; Python requests)"
EXTRA_RETRY_MIN = 30
_fail: dict = {}

_ENTS = {"&amp;": "&", "&quot;": '"', "&#39;": "'", "&#039;": "'", "&nbsp;": " ", "&lt;": "<", "&gt;": ">",
         "&#8211;": "–", "&#8212;": "—", "&#160;": " "}


def html_to_text(x) -> str:
    x = re.sub(r"<[^>]+>", "", "" if x is None else str(x))
    for e, r in _ENTS.items():
        x = x.replace(e, r)

    def num(m):   # any other numeric entity; 128-159 are old Windows codes (149 = bullet)
        n = int(m.group(1))
        return "•" if n == 149 else (" " if 128 <= n <= 159 else chr(n))
    x = re.sub(r"&#([0-9]{2,6});", num, x)
    return re.sub(r"\s+", " ", x).strip()


def get_json(url: str, params: dict | None = None, headers: dict | None = None):
    h = {"User-Agent": EXTRA_UA, "Accept": "application/json"}
    h.update(headers or {})
    r = requests.get(url, params=params, headers=h, timeout=12)
    if r.status_code >= 300:
        raise RuntimeError(f"HTTP {r.status_code} from {url}")
    return r.json()


def first_sentences(x: str, n: int = 2) -> str:
    s = re.findall(r"[^.!?]+[.!?]+(?:\s|$)", x or "")
    out = " ".join(t.strip() for t in s[:n])
    return out or (x or "").strip()


# ---- Sources --------------------------------------------------------------------------------------
def fetch_history(day: date) -> list[dict]:
    j = get_json(f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/selected/{day:%m/%d}")
    ev = j.get("selected") or []
    if not ev:
        raise RuntimeError("no events returned")
    n = day_num(day)
    pick = list(dict.fromkeys([(n * 1) % len(ev), (n * 7) % len(ev)]))[:2]
    out = []
    for i in pick:
        e = ev[i]
        try:
            url = e["pages"][0]["content_urls"]["mobile"]["page"]
        except (KeyError, IndexError, TypeError):
            url = ""
        out.append({"year": str(e.get("year", "")), "text": str(e.get("text", "")), "url": url})
    return out


def fetch_dinner_question(day: date) -> dict:
    recent = []
    for r in db.get("""select content from daily_extras where kind = 'dinner' and extra_date >= $1::date
                       order by extra_date desc""", day - timedelta(days=21)):
        try:
            recent.append(json.loads(r["content"]).get("text", ""))
        except (ValueError, AttributeError):
            pass
    sys = ("You write one dinner-table conversation question for a family with young children. "
           'Reply with JSON only: {"question": "..."}. Under 20 words, fun, easy for a 4-year-old to answer, '
           "and interesting for parents too.")
    usr = f"Children: {join_names(kids_names())}." + (f" Don't repeat these: {' | '.join(recent)}" if recent else "")
    q = str(groq.chat_json(sys, usr, temperature=1).get("question") or "").strip()
    if not q:
        raise RuntimeError("no question returned")
    return {"text": q}


# ---- Animal of the day (iNaturalist: spotted near home) --------------------------------------------
# A wild animal someone photographed and the iNaturalist community identified ("research grade") within
# INAT_RADIUS_KM of WEATHER_LAT/WEATHER_LON in the last INAT_DAYS days. Only photos under a Creative Commons
# licence are used, and the photographer's credit is shown with it. No species repeats within INAT_NO_REPEAT_DAYS.
INAT_API = "https://api.inaturalist.org/v1"
INAT_RADIUS_KM = 40            # about 25 miles
INAT_DAYS = 14
INAT_WIDE_DAYS = 60            # used if the last two weeks have nothing new
INAT_NO_REPEAT_DAYS = 60
INAT_TAXA = "Mammalia,Aves,Reptilia,Amphibia,Actinopterygii,Mollusca,Arachnida,Insecta,Animalia"
INAT_LICENSES = "cc0,cc-by,cc-by-nc,cc-by-sa,cc-by-nd,cc-by-nc-sa,cc-by-nc-nd"
INAT_GROUP = {"Mammalia": "Mammal", "Aves": "Bird", "Reptilia": "Reptile", "Amphibia": "Amphibian",
              "Actinopterygii": "Fish", "Mollusca": "Mollusk", "Arachnida": "Spider or relative", "Insecta": "Insect"}


def inat_photo(url: str, size: str = "medium") -> str:
    """iNaturalist returns the small 'square' photo; swap in a bigger size."""
    return re.sub(r"/(square|thumb|small|medium|large|original)\.", f"/{size}.", url or "", count=1)


def inat_candidates(results: list[dict]) -> list[dict]:
    """One entry per species (first observation of each), only species with a common name and a CC photo."""
    out, seen = [], set()
    for o in results or []:
        t = o.get("taxon") or {}
        tid, common = t.get("id"), str(t.get("preferred_common_name") or "").strip()
        if not tid or tid in seen or not common or (t.get("rank_level") or 99) > 10:
            continue
        ph = next((p for p in o.get("photos") or [] if p.get("license_code") and p.get("url")), None)
        if not ph:
            continue
        seen.add(tid)
        out.append({"taxon_id": int(tid), "name": common[:1].upper() + common[1:], "sci": str(t.get("name") or ""),
                    "group": INAT_GROUP.get(str(t.get("iconic_taxon_name") or ""), "Animal"),
                    "image": inat_photo(ph["url"]), "credit": str(ph.get("attribution") or ""),
                    "seen": str(o.get("observed_on") or ""), "url": str(o.get("uri") or "")})
    return out


def pick_inat(cands: list[dict], recent_ids: set[int], day: date) -> dict | None:
    """Same pick for everyone on a given day: skip recent species, then choose by date among the rest."""
    fresh = sorted((c for c in cands if c["taxon_id"] not in recent_ids), key=lambda c: c["taxon_id"])
    return fresh[(day_num(day) * 37) % len(fresh)] if fresh else None


def _inat_recent_ids(day: date) -> set[int]:
    ids = set()
    for r in db.get("""select content from daily_extras where kind = 'animal' and extra_date >= $1::date
                       and extra_date < $2::date""", day - timedelta(days=INAT_NO_REPEAT_DAYS), day):
        try:
            tid = json.loads(r["content"]).get("taxon_id")
        except (ValueError, TypeError, AttributeError):
            tid = None
        if tid:
            ids.add(int(tid))
    return ids


def fetch_animal(day: date) -> dict:
    from .config import cfg
    recent = _inat_recent_ids(day)
    pick = None
    for days in (INAT_DAYS, INAT_WIDE_DAYS):
        j = get_json(f"{INAT_API}/observations", params={
            "lat": cfg("WEATHER_LAT", "30.159"), "lng": cfg("WEATHER_LON", "-81.628"), "radius": INAT_RADIUS_KM,
            "d1": (day - timedelta(days=days)).isoformat(), "d2": day.isoformat(), "quality_grade": "research",
            "captive": "false", "photos": "true", "iconic_taxa": INAT_TAXA, "photo_license": INAT_LICENSES,
            "per_page": 200, "order": "desc", "order_by": "observed_on"})
        pick = pick_inat(inat_candidates(j.get("results") or []), recent, day)
        if pick:
            break
    if not pick:
        raise RuntimeError("no new animal sightings with a photo nearby")
    try:   # a short description from the species page
        t = (get_json(f"{INAT_API}/taxa/{pick['taxon_id']}").get("results") or [{}])[0]
        pick["text"] = first_sentences(html_to_text(t.get("wikipedia_summary") or ""))
    except Exception:  # noqa: BLE001
        pick["text"] = ""
    return pick


# ---- Space photo of the day (NASA Astronomy Picture of the Day) ----------------------------------------
# api.nasa.gov: a free key (NASA_API_KEY) allows 1,000 requests an hour; without one the shared DEMO_KEY is
# used (30 an hour, 50 a day), which is enough for one request a day but can be used up by other apps on
# the same server. Some days are a video: then its thumbnail is shown with a link to watch.
APOD_API = "https://api.nasa.gov/planetary/apod"


def apod_page(d: str) -> str:
    """APOD's own page for a date, e.g. 2026-11-10 -> https://apod.nasa.gov/apod/ap261110.html"""
    return f"https://apod.nasa.gov/apod/ap{d[2:4]}{d[5:7]}{d[8:10]}.html" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d or "") else "https://apod.nasa.gov/apod/"


def clean_apod(a: dict) -> dict:
    video = a.get("media_type") == "video"
    image = (a.get("thumbnail_url") if video else a.get("url")) or ""
    credit = re.sub(r"\s+", " ", str(a.get("copyright") or "")).strip()
    return {"title": str(a.get("title") or "").strip(), "date": str(a.get("date") or ""),
            "text": first_sentences(str(a.get("explanation") or ""), 3), "image": image,
            "video": str(a.get("url") or "") if video else "", "credit": f"© {credit}" if credit else "NASA",
            "url": apod_page(str(a.get("date") or ""))}


def fetch_apod(day: date) -> dict:
    from .config import cfg
    key = cfg("NASA_API_KEY", "") or "DEMO_KEY"
    try:
        a = get_json(APOD_API, params={"api_key": key, "date": day.isoformat(), "thumbs": "true"})
    except RuntimeError as e:
        if "HTTP 400" not in str(e) and "HTTP 404" not in str(e):
            raise
        # just after midnight today's picture may not be posted yet: use the latest one
        a = get_json(APOD_API, params={"api_key": key, "thumbs": "true"})
    r = clean_apod(a)
    if not r["title"] or not r["image"].startswith("http"):
        raise RuntimeError("no picture today (it may be an interactive page)")
    return r


# ---- Recipe of the day (TheMealDB) -------------------------------------------------------------------
# TheMealDB's free test key "1" is for development and personal projects; one request a day (or a few,
# to skip desserts and repeats) is very light use.
MEALDB_API = "https://www.themealdb.com/api/json/v1/1"
RECIPE_SKIP_CATEGORIES = {"Dessert"}      # recipe of the day is a meal idea, not a dessert
RECIPE_NO_REPEAT_DAYS = 90
RECIPE_TRIES = 6


def parse_mealdb(m: dict) -> dict:
    """TheMealDB's numbered fields (strIngredient1..20, strMeasure1..20) into the app's recipe shape."""
    ings = []
    for i in range(1, 21):
        ing = str(m.get(f"strIngredient{i}") or "").strip()
        if not ing:
            continue
        meas = re.sub(r"\s+", " ", str(m.get(f"strMeasure{i}") or "")).strip()
        ings.append(f"{meas} {ing}".strip() if meas else ing)
    steps = [re.sub(r"\s+", " ", ln).strip() for ln in re.split(r"[\r\n]+", str(m.get("strInstructions") or ""))]
    steps = [ln for ln in steps if ln and not re.fullmatch(r"(?i)(step\s*)?\d+[.:)]?", ln)]
    meta = " · ".join(x for x in (str(m.get("strArea") or "").strip(), str(m.get("strCategory") or "").strip())
                      if x and x.lower() != "unknown")
    return {"meal_id": str(m.get("idMeal") or ""), "name": str(m.get("strMeal") or "").strip(),
            "category": str(m.get("strCategory") or ""), "meta": meta, "image": str(m.get("strMealThumb") or ""),
            "ingredients": ings, "instructions": "\n".join(steps),
            "source": str(m.get("strSource") or ""), "video": str(m.get("strYoutube") or ""),
            "url": f"https://www.themealdb.com/meal/{m.get('idMeal')}" if m.get("idMeal") else ""}


def _recent_recipe_ids(day: date) -> set[str]:
    ids = set()
    for r in db.get("""select content from daily_extras where kind = 'recipe' and extra_date >= $1::date
                       and extra_date < $2::date""", day - timedelta(days=RECIPE_NO_REPEAT_DAYS), day):
        try:
            ids.add(str(json.loads(r["content"]).get("meal_id") or ""))
        except (ValueError, TypeError, AttributeError):
            pass
    return ids


def recipe_ok(r: dict, recent: set[str]) -> bool:
    return bool(r["name"] and r["ingredients"] and r["instructions"] and r["image"]) \
        and r["category"] not in RECIPE_SKIP_CATEGORIES and r["meal_id"] not in recent


def fetch_recipe(day: date) -> dict:
    recent = _recent_recipe_ids(day)
    for _ in range(RECIPE_TRIES):
        meals = get_json(f"{MEALDB_API}/random.php").get("meals") or []
        if meals:
            r = parse_mealdb(meals[0])
            if recipe_ok(r, recent):
                return r
    raise RuntimeError("no suitable recipe found")


def fetch_quote(day: date) -> dict:
    """ZenQuotes 'today' (free, no key; requires the credit link shown on Today)."""
    j = get_json("https://zenquotes.io/api/today")
    q = j[0] if j else {}
    if not has_text(q.get("q")):
        raise RuntimeError("no quote returned")
    return {"text": str(q["q"]).strip(), "author": str(q.get("a") or "").strip()}


# ---- Word of the day (Merriam-Webster's free daily feed) -----------------------------------------
MW_FEED = "https://www.merriam-webster.com/wotd/feed/rss2"


def xml_tag(x: str, tag: str) -> str:
    m = re.search(rf"(?s)<{re.escape(tag)}>(.*?)</{re.escape(tag)}>", x)
    if not m:
        return ""
    v = m.group(1)
    return re.sub(r"(?s)^\s*<!\[CDATA\[(.*)\]\]>\s*$", r"\1", v).strip()


def parse_mw_feed(xml: str, day: date | None = None) -> dict | None:
    """The feed's text -> that day's word, or None if the feed doesn't have it yet (updates overnight)."""
    day = day or today()
    items = re.findall(r"(?s)<item>.*?</item>", xml)
    if not items:
        raise RuntimeError("the feed has no words")
    links = [xml_tag(i, "link") for i in items]
    hit = [k for k, l in enumerate(links) if re.sub(r".*(\d{4}-\d{2}-\d{2}).*", r"\1", l, flags=re.S) == day.isoformat()]
    if not hit:
        return None
    it = items[hit[0]]
    word = html_to_text(xml_tag(it, "title"))
    desc = xml_tag(it, "description")
    if not word:
        raise RuntimeError("no word in the feed item")
    paras = [html_to_text(p) for p in re.sub(r"(?i)</p>|<br\s*/?>", "\x01", desc).split("\x01")]
    paras = [p for p in paras if p]
    pron = re.search(r"\\[^\\<>]{2,60}\\", desc)
    pos = re.search(r"(?i)<em>\s*[a-z][a-z ]{1,24}\s*</em>", desc)
    ex = [p for p in paras if p.startswith("//")]
    dyk = ""
    k = [i for i, p in enumerate(paras) if re.match(r"(?i)^Did you know\??", p)]
    if k:
        rest = re.sub(r"(?i)^Did you know\??", "", paras[k[0]]).strip()
        dyk = rest or (paras[k[0] + 1] if len(paras) > k[0] + 1 else "")
    definition = html_to_text(xml_tag(it, "merriam:shortdef"))
    if not definition:   # fall back to the paragraph after the headword line
        j = [i for i, p in enumerate(paras) if word in p]
        definition = paras[j[0] + 1] if j and len(paras) > j[0] + 1 else ""
    return {"word": word,
            "pos": re.sub(r"(?i)^<em>\s*|\s*</em>$", "", pos.group(0)).lower() if pos else "",
            "pron": pron.group(0) if pron else "", "definition": definition,
            "example": re.sub(r"^//\s*", "", ex[0]).strip() if ex else "", "origin": dyk, "url": links[hit[0]]}


def fetch_word(day: date) -> dict:
    r = requests.get(MW_FEED, headers={"User-Agent": EXTRA_UA}, timeout=12)
    if r.status_code >= 300:
        raise RuntimeError(f"HTTP {r.status_code} from Merriam-Webster")
    w = parse_mw_feed(r.text, day)
    if w is None:
        raise RuntimeError("today's word isn't in the feed yet")
    return w


# ---- Art of the day (Art Institute of Chicago, free, no key) ---------------------------------------
# Descriptions are CC BY (credited on Today); images are public domain.
AIC_SEARCH = "https://api.artic.edu/api/v1/artworks/search"
AIC_FILTER = {"bool": {"filter": [{"term": {"is_public_domain": True}},
                                  {"match": {"artwork_type_title": "Painting"}},
                                  {"exists": {"field": "image_id"}}, {"exists": {"field": "description"}}]}}


def aic_search(limit: int, page: int = 1) -> dict:
    return get_json(AIC_SEARCH, params={
        "params": json.dumps({"query": AIC_FILTER}), "limit": limit, "page": page,
        "fields": "id,title,artist_display,date_display,medium_display,image_id,description,short_description,"
                  "artwork_type_title"}, headers={"AIC-User-Agent": EXTRA_UA})


def art_index(day: date, total: int) -> int:
    """1-based result to show on `day` (the search pages through the first 10,000 only)."""
    n = min(total, 9000)
    return (day_num(day) * 7919) % n + 1


def clean_art(a: dict) -> dict:
    desc = html_to_text(a.get("description") or "") or html_to_text(a.get("short_description") or "")
    return {"id": a["id"], "title": html_to_text(a.get("title") or "Untitled"),
            "artist": str(a.get("artist_display") or "").replace("\n", ", ").strip(),
            "date": a.get("date_display") or "", "medium": a.get("medium_display") or "",
            "text": first_sentences(desc, 3),
            "image": f"https://www.artic.edu/iiif/2/{a['image_id']}/full/843,/0/default.jpg",
            "url": f"https://www.artic.edu/artworks/{a['id']}"}


# The museum's picture server refuses requests that don't come from www.artic.edu (HTTP 403), so a phone
# can't load the picture directly. The app downloads it once with that Referer, shrinks it, and shows its
# own copy (a small JPEG inside the page). Kept in memory per picture; a failure is retried after 30 minutes.
AIC_REFERER = "https://www.artic.edu/"
ART_SHOW_WIDTH = 640
_art_img: dict = {}


def shrink_jpeg(raw: bytes, width: int = ART_SHOW_WIDTH, quality: int = 82) -> bytes:
    import io
    from PIL import Image
    im = Image.open(io.BytesIO(raw))
    im = im.convert("RGB")
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, "JPEG", quality=quality, optimize=True, progressive=True)
    return out.getvalue()


def art_image_src(url: str) -> str:
    """A data: URL for the art picture, or "" if it couldn't be downloaded."""
    import base64
    hit = _art_img.get(url)
    if hit and (hit[1] or time.time() - hit[0] < 30 * 60):
        return hit[1]
    src = ""
    try:
        r = requests.get(url, headers={"Referer": AIC_REFERER, "User-Agent": EXTRA_UA}, timeout=20)
        r.raise_for_status()
        src = "data:image/jpeg;base64," + base64.b64encode(shrink_jpeg(r.content)).decode()
    except Exception as e:  # noqa: BLE001
        print(f"[extras] art picture failed: {e}")
    if len(_art_img) > 8:
        _art_img.clear()
    _art_img[url] = (time.time(), src)
    return src


def fetch_art(day: date) -> dict:
    first = aic_search(limit=1, page=1)
    total = (first.get("pagination") or {}).get("total") or 0
    if total < 1:
        raise RuntimeError("no paintings found")
    k = art_index(day, total)
    hit = first if k == 1 else aic_search(limit=1, page=k)
    a = hit["data"][0]
    if not has_text(a.get("image_id")):
        raise RuntimeError("that painting has no image")
    return clean_art(a)


def _trivia(day):
    from .trivia import fetch_trivia
    return fetch_trivia(day)


EXTRA_SOURCES = {"history": fetch_history,
                 "dinner": fetch_dinner_question, "animal": fetch_animal, "quote": fetch_quote,
                 "word": fetch_word, "art": fetch_art, "space": fetch_apod, "recipe": fetch_recipe, "trivia": _trivia}


def current_format(kind: str, saved) -> bool:
    """False for a saved item from an older source, which is then fetched again and replaced: an animal
    saved before the switch to iNaturalist (or by the R version of the app) has no taxon_id."""
    if kind == "animal":
        return isinstance(saved, dict) and bool(saved.get("taxon_id"))
    return True


def get_extra(kind: str, day: date | None = None):
    """Today's saved value for one kind, fetching and saving it the first time it's needed."""
    day = day or today()
    r = db.one("select content from daily_extras where extra_date = $1::date and kind = $2", day, kind)
    saved = json.loads(r["content"]) if r else None
    if saved is not None and current_format(kind, saved):
        return saved
    last = _fail.get(kind)
    if last and time.time() - last < EXTRA_RETRY_MIN * 60:
        return None
    print(f"[extras] fetching {kind}")
    try:
        val = EXTRA_SOURCES[kind](day)
    except Exception as e:  # noqa: BLE001
        print(f"[extras] {kind} failed: {e}")
        _fail[kind] = time.time()
        return saved            # an older-format item is still better than nothing
    # "do update" only replaces an older-format item (see current_format); otherwise the first one saved wins
    db.run("""insert into daily_extras (extra_date, kind, content) values ($1::date, $2, $3)
              on conflict (extra_date, kind) do update set content = excluded.content
              where daily_extras.content not like '%"taxon_id"%' and excluded.kind = 'animal'""",
           day, kind, json.dumps(val))
    return val
