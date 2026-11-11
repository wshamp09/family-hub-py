"""Today's headlines in three groups, as headlines and links only (no summaries):
  national  Google News, U.S. section: its top 3 stories
  sports    Google News, Sports section: its top 3 stories
  local     News4JAX (WJXT): its top 2 local stories (then its news feed, then its main feed, as backups)
Google News collects stories from many outlets; each headline shows the outlet it came from. Its feeds list
stories in Google's order of importance, which is kept.
The set is saved in daily_extras (kind "news") and fetched again when it's more than NEWS_REFRESH_HOURS old,
so everyone sees the same headlines and the feeds are read at most about 12 times a day. If the feeds can't
be reached, the last set stays up (and is tried again after NEWS_RETRY_MIN minutes)."""
from __future__ import annotations

import html
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests

from . import db
from .config import TZ, now, today

GOOGLE_NEWS = "https://news.google.com/rss/headlines/section/topic/{topic}?hl=en-US&gl=US&ceid=US:en"
NEWS_FEEDS = {      # group: [(feed name, address), ...] tried in order until one works
    "national": [("Google News", GOOGLE_NEWS.format(topic="NATION"))],
    "sports": [("Google News", GOOGLE_NEWS.format(topic="SPORTS"))],
    "local": [("News4JAX", "https://www.news4jax.com/arc/outboundfeeds/rss/category/news/local/?outputType=xml"),
              ("News4JAX", "https://www.news4jax.com/arc/outboundfeeds/rss/category/news/?outputType=xml"),
              ("News4JAX", "https://www.news4jax.com/arc/outboundfeeds/rss/?outputType=xml")],
}
NEWS_GROUPS = {"national": "National", "sports": "Sports", "local": "Local"}   # order and headings on Today
NEWS_COUNT = {"national": 3, "sports": 3, "local": 2}
NEWS_REFRESH_HOURS = 2
NEWS_RETRY_MIN = 30
NEWS_MAX_BYTES = 3_000_000
NEWS_UA = "Mozilla/5.0 (compatible; TheShampHouse/1.0; family organizer)"   # some news sites refuse unknown programs
NEWS_PARTIAL_RETRY_MIN = 30    # if a group came back empty, try again sooner
_fail = {"at": 0.0}


def _text(el, *names) -> str:
    for n in names:
        x = el.find(n)
        if x is not None and (x.text or "").strip():
            return x.text.strip()
    return ""


def parse_feed(xml_data, source: str) -> list[dict]:
    """RSS or Atom (bytes, so the feed's own declared character set is used) into
    [{title, url, source (the outlet), via (the feed), published}], in the feed's own order."""
    root = ET.fromstring(xml_data)
    atom = "{http://www.w3.org/2005/Atom}"
    items = root.findall("./channel/item") or root.findall(f"{atom}entry")
    out = []
    for it in items:
        title = _text(it, "title", f"{atom}title")
        link = _text(it, "link")
        if not link:
            le = it.find(f"{atom}link")
            link = le.get("href", "") if le is not None else ""
        when = _text(it, "pubDate", f"{atom}updated", f"{atom}published")
        pub = ""
        if when:
            try:
                d = parsedate_to_datetime(when)
            except (TypeError, ValueError):
                try:
                    d = datetime.fromisoformat(when.replace("Z", "+00:00"))
                except ValueError:
                    d = None
            if d is not None:
                pub = (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).isoformat()
        title = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", title))).strip()
        outlet = _text(it, "source") or source            # Google News names each story's outlet
        if outlet != source:
            title = re.sub(rf"\s+[-–—]\s+{re.escape(outlet)}\s*$", "", title)
        if title and link.startswith("http"):
            out.append({"title": title, "url": link, "source": outlet, "via": source, "published": pub})
    return out


def pick_headlines(groups: dict[str, list[dict]], counts: dict[str, int] = NEWS_COUNT) -> list[dict]:
    """The first N of each group, in NEWS_GROUPS order, skipping repeated headlines."""
    seen, out = set(), []
    for g in NEWS_GROUPS:
        n = 0
        for it in groups.get(g) or []:
            key = re.sub(r"\W+", "", it["title"].lower())
            if key in seen:
                continue
            seen.add(key)
            out.append(dict(it, group=g))
            n += 1
            if n >= counts.get(g, 0):
                break
    return out


def fetch_group(group: str) -> list[dict]:
    for source, url in NEWS_FEEDS[group]:
        try:
            r = requests.get(url, headers={"User-Agent": NEWS_UA, "Accept": "application/rss+xml, application/xml, text/xml"},
                             timeout=15)
            r.raise_for_status()
            items = parse_feed(r.content[:NEWS_MAX_BYTES], source)
            if items:
                return items
            print(f"[news] {source} feed had no headlines: {url}")
        except Exception as e:  # noqa: BLE001
            print(f"[news] {source} feed failed ({url}): {e}")
    return []


def fetch_news() -> dict:
    print("[news] fetching headlines")
    groups = {g: fetch_group(g) for g in NEWS_FEEDS}
    heads = pick_headlines(groups)
    if not heads:
        raise RuntimeError("no headlines from any feed")
    return {"fetched_at": now().isoformat(), "items": heads}


def is_stale(saved: dict | None, at: datetime, hours: float = NEWS_REFRESH_HOURS) -> bool:
    """Due for a refresh: after NEWS_REFRESH_HOURS, after NEWS_PARTIAL_RETRY_MIN if a group was missing, or
    straight away if a saved headline came from a feed or group no longer in NEWS_FEEDS."""
    if not saved or not saved.get("items"):
        return True
    feeds = {(g, name) for g, fl in NEWS_FEEDS.items() for name, _ in fl}
    if any((it.get("group"), it.get("via")) not in feeds for it in saved["items"]):
        return True
    groups = {it.get("group") for it in saved["items"]}
    if not set(NEWS_GROUPS) <= groups:
        hours = min(hours, NEWS_PARTIAL_RETRY_MIN / 60)
    try:
        return at - datetime.fromisoformat(saved["fetched_at"]) >= timedelta(hours=hours)
    except (KeyError, ValueError, TypeError):
        return True


def get_news() -> dict | None:
    day = today()
    r = db.one("select content from daily_extras where extra_date = $1::date and kind = 'news'", day)
    saved = json.loads(r["content"]) if r else None
    if not is_stale(saved, now()):
        return saved
    if time.time() - _fail["at"] < NEWS_RETRY_MIN * 60:
        return saved
    try:
        val = fetch_news()
    except Exception as e:  # noqa: BLE001
        print(f"[news] failed: {e}")
        _fail["at"] = time.time()
        return saved
    db.run("""insert into daily_extras (extra_date, kind, content) values ($1::date, 'news', $2)
              on conflict (extra_date, kind) do update set content = excluded.content""", day, json.dumps(val))
    return val


def ago(published: str, at: datetime) -> str:
    """'25m ago', '3h ago', or 'Nov 8' for older items."""
    try:
        d = datetime.fromisoformat(published)
    except (TypeError, ValueError):
        return ""
    mins = int((at - d).total_seconds() // 60)
    if mins < 0:
        return ""
    if mins < 60:
        return f"{max(mins, 1)}m ago"
    if mins < 24 * 60:
        return f"{mins // 60}h ago"
    d = d.astimezone(TZ)
    return f"{d:%b} {d.day}"
