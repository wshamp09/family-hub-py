"""Photos: as many as you like each week, one of them the photo of the week.
Files go to the private Supabase Storage bucket "photos" (sql/schema.sql creates it); the photos
table lists them. Every upload is turned the right way up, stripped of its metadata (including
location) and shrunk: about 1600 px for viewing and 600 px for the timeline, so the free 1 GB of
storage holds thousands of photos. A photo belongs to the week (Monday to Sunday) of the date it was
taken: the camera's date when the file has one, otherwise the day it was added. The date can be changed.
iPhone HEIC photos are read with pillow-heif."""
from __future__ import annotations

import io
import math
import random
from datetime import date, datetime, timedelta

from PIL import Image, ImageDraw, ImageFont, ImageOps

from . import auth, db
from .config import APP_DIR, APP_TITLE, has_text, now, today
from .dates import add_months, week_start

try:                                  # iPhone photos (HEIC)
    from pillow_heif import register_heif_opener
    register_heif_opener()
except Exception:  # noqa: BLE001 - optional
    pass

PHOTO_BUCKET = "photos"
PHOTO_FULL_PX = 1600
PHOTO_THUMB_PX = 600
PHOTO_LINK_MIN = 60                 # how long a viewing link lasts
FONTS = APP_DIR / "static" / "fonts"


# ---- Supabase Storage -----------------------------------------------------------------------------
def _obj(path: str) -> str:
    return auth.endpoint(f"/storage/v1/object/{PHOTO_BUCKET}/{path}")


def st_upload(data: bytes, path: str, content_type: str = "image/jpeg") -> str:
    r = auth.call("POST", _obj(path), auth.admin_headers(), data=data,
                  extra_headers={"x-upsert": "true", "Content-Type": content_type})
    if not r["ok"]:
        raise RuntimeError(f"couldn't save the photo to storage: {r['message']}")
    return path


def st_download(path: str) -> bytes:
    import requests
    r = requests.get(_obj(path), headers=auth.admin_headers(), timeout=30)
    if r.status_code >= 300:
        raise RuntimeError(f"couldn't download {path} (HTTP {r.status_code})")
    return r.content


def st_remove(paths: list[str]) -> bool:
    paths = [p for p in paths if has_text(p)]
    if not paths:
        return True
    r = auth.call("DELETE", auth.endpoint(f"/storage/v1/object/{PHOTO_BUCKET}"), auth.admin_headers(),
                  json={"prefixes": paths})
    if not r["ok"]:
        print(f"[photos] couldn't remove files: {r['message']}")
    return r["ok"]


def st_sign(paths: list[str], minutes: int = PHOTO_LINK_MIN) -> dict:
    """Short-lived viewing links for many files in one call: {path: url}."""
    paths = list(dict.fromkeys(p for p in paths if has_text(p)))
    if not paths:
        return {}
    r = auth.call("POST", auth.endpoint(f"/storage/v1/object/sign/{PHOTO_BUCKET}"), auth.admin_headers(),
                  json={"expiresIn": minutes * 60, "paths": paths})
    if not r["ok"]:
        print(f"[photos] couldn't make links: {r['message']}")
        return {}
    out = {}
    for x in r["body"] if isinstance(r["body"], list) else []:
        if x.get("signedURL") and not x.get("error"):
            out[x["path"]] = auth.endpoint("/storage/v1") + x["signedURL"]
    return out


# ---- Preparing an upload ------------------------------------------------------------------------------
def exif_date(img: Image.Image) -> date | None:
    """The date the camera recorded (None if there isn't one)."""
    try:
        ex = img.getexif()
        vals = []
        sub = ex.get_ifd(0x8769) if hasattr(ex, "get_ifd") else {}
        for tag in (36867, 36868):          # DateTimeOriginal, DateTimeDigitized
            if sub.get(tag):
                vals.append(sub[tag])
        if ex.get(306):                      # DateTime
            vals.append(ex[306])
        for v in vals:
            d = datetime.strptime(str(v)[:10], "%Y:%m:%d").date()
            if date(1990, 1, 1) <= d <= today() + timedelta(days=1):
                return d
    except Exception:  # noqa: BLE001
        pass
    return None


def _jpeg(img: Image.Image, px: int, quality: int) -> tuple[bytes, int, int]:
    im = img.copy()
    im.thumbnail((px, px), Image.LANCZOS)
    if im.mode != "RGB":
        bg = Image.new("RGB", im.size, "white")
        bg.paste(im, mask=im.split()[-1] if im.mode in ("RGBA", "LA") else None)
        im = bg
    out = io.BytesIO()
    im.save(out, "JPEG", quality=quality, optimize=True)     # saved fresh: no EXIF/GPS carried over
    return out.getvalue(), im.width, im.height


def photo_prepare(raw: bytes) -> dict:
    img = Image.open(io.BytesIO(raw))
    taken = exif_date(img)
    img = ImageOps.exif_transpose(img)
    full, w, h = _jpeg(img, PHOTO_FULL_PX, 85)
    thumb, _, _ = _jpeg(img, PHOTO_THUMB_PX, 78)
    return {"full": full, "thumb": thumb, "width": w, "height": h, "taken": taken}


# ---- Photo-of-the-week rules ------------------------------------------------------------------------
def featured_pick(w: list[dict]):
    """Given a week's photos ({id, is_featured, created_at}), which id should be the photo of the week?
    The one already chosen, otherwise the first one added. Pure; tested in check_setup."""
    if not w:
        return None
    for p in w:
        if p["is_featured"]:
            return p["id"]
    return sorted(w, key=lambda p: (p["created_at"], p["id"]))[0]["id"]


def photo_fix_week(week: date) -> None:
    """Make sure a week has exactly one photo of the week (after a delete or a date change)."""
    w = db.get("select id, is_featured, created_at from photos where week_start = $1::date", week)
    if not w or sum(1 for p in w if p["is_featured"]) == 1:
        return
    keep = featured_pick(w)
    db.run("update photos set is_featured = false where week_start = $1::date and id <> $2", week, keep)
    db.run("update photos set is_featured = true where id = $1", keep)


PHOTO_CAPTION_MAX = 200


def photo_add(raw: bytes, user: dict, fallback_date: date | None = None, caption: str = "") -> dict:
    p = photo_prepare(raw)
    taken = p["taken"] or fallback_date or today()
    week = week_start(taken)
    stem = f"{week:%Y/%m-%d}/{now():%Y%m%d%H%M%S}-{random.randint(1, 999999):06d}"
    path, thumb = stem + ".jpg", stem + "-thumb.jpg"
    st_upload(p["full"], path)
    st_upload(p["thumb"], thumb)
    cap = (caption or "").strip()[:PHOTO_CAPTION_MAX] or None
    db.run("""insert into photos (week_start, taken_on, path, thumb_path, width, height, added_by, added_by_name,
                                  is_featured, caption)
              values ($1::date, $2::date, $3, $4, $5, $6, $7::uuid, $8,
                      not exists (select 1 from photos where week_start = $1::date and is_featured), $9)""",
           week, taken, path, thumb, p["width"], p["height"], user["user_id"], user["display_name"], cap)
    return {"week": week, "taken": taken, "from_camera": p["taken"] is not None}


def photo_get(pid) -> dict | None:
    return db.one("select * from photos where id = $1", int(pid))


def photo_make_featured(pid) -> None:
    r = photo_get(pid)
    if not r:
        return
    db.run("update photos set is_featured = false where week_start = $1::date", r["week_start"])
    db.run("update photos set is_featured = true where id = $1", r["id"])


def photo_update(pid, caption, taken_on: date) -> None:
    """Caption and/or a new date (which can move the photo to another week)."""
    r = photo_get(pid)
    if not r:
        return
    old_week, new_week = r["week_start"], week_start(taken_on)
    if new_week != old_week:
        db.run("""update photos set taken_on = $2::date, week_start = $3::date, caption = $4, is_featured = false
                  where id = $1""", r["id"], taken_on, new_week, caption)
        photo_fix_week(old_week)
        photo_fix_week(new_week)
    else:
        db.run("update photos set taken_on = $2::date, caption = $3 where id = $1", r["id"], taken_on, caption)


def photo_delete(pid) -> None:
    r = photo_get(pid)
    if not r:
        return
    st_remove([r["path"], r["thumb_path"]])
    db.run("delete from photos where id = $1", r["id"])
    photo_fix_week(r["week_start"])


def photos_in_month(month_start: date) -> list[dict]:
    """Photos taken in one month, oldest week first; the photo of the week leads each week."""
    return db.get("""select * from photos where coalesce(taken_on, week_start) >= $1::date
                       and coalesce(taken_on, week_start) < $2::date
                     order by week_start, is_featured desc, taken_on, created_at, id""",
                  month_start, add_months(month_start, 1))


def photo_months() -> list[dict]:
    return db.get("""select date_trunc('month', coalesce(taken_on, week_start))::date as month, count(*)::int as n
                     from photos group by 1 order by 1 desc""")


def week_has_photo(day: date | None = None) -> bool:
    return db.one("select 1 as x from photos where week_start = $1::date limit 1", week_start(day or today())) is not None


def _nolead(s: str) -> str:
    return s.replace(" 0", " ")


def week_label(ws: date) -> str:
    """'Nov 2 – 8, 2026', 'Nov 30 – Dec 6, 2026', 'Dec 28, 2026 – Jan 3, 2027'"""
    we = ws + timedelta(days=6)
    if ws.year != we.year:
        return f"{_nolead(ws.strftime('%b %d, %Y'))} – {_nolead(we.strftime('%b %d, %Y'))}"
    if ws.month != we.month:
        return f"{_nolead(ws.strftime('%b %d'))} – {_nolead(we.strftime('%b %d, %Y'))}"
    return f"{_nolead(ws.strftime('%b %d'))} – {we.day}, {we.year}"


def photo_date_label(d: date) -> str:
    return _nolead(d.strftime("%a, %b %d, %Y"))


# ---- Monthly collage ---------------------------------------------------------------------------------
# One band per week, top to bottom. The photo of the week fills the left of its band (all of it when
# it's the only one); up to 6 others sit in a grid on the right, the last showing "+N" if there are
# more. Sizes are in pixels on a 2400 x 3000 canvas (8 x 10 in at 300 dpi).
COLLAGE_W, COLLAGE_H = 2400, 3000


def collage_layout(counts: list[int], W: int = COLLAGE_W, H: int = COLLAGE_H, margin: int = 70, header: int = 250,
                   label: int = 64, gap: int = 26, max_extra: int = 6) -> dict:
    """Pure; tested in check_setup. Weeks and slots are 1-based (as in the R app)."""
    k = len(counts)
    if not k:
        raise ValueError("no photos this month")
    bh = math.floor((H - 2 * margin - header - k * label - (k - 1) * gap) / k)
    inner = W - 2 * margin
    tiles, labels = [], []
    y = margin + header
    for i, c in enumerate(counts, 1):
        labels.append({"week": i, "x": margin, "y": y, "w": inner, "h": label})
        y += label
        n_extra = c - 1
        shown = min(n_extra, max_extra)
        if shown == 0:
            tiles.append({"week": i, "slot": 1, "x": margin, "y": y, "w": inner, "h": bh, "more": 0})
        else:
            fw = math.floor(inner * 0.58)
            tiles.append({"week": i, "slot": 1, "x": margin, "y": y, "w": fw, "h": bh, "more": 0})
            cols = 1 if shown <= 2 else 2
            rows = math.ceil(shown / cols)
            ex, ew = margin + fw + gap, inner - fw - gap
            cw = math.floor((ew - (cols - 1) * gap) / cols)
            ch = math.floor((bh - (rows - 1) * gap) / rows)
            for j in range(1, shown + 1):
                r, cc = (j - 1) // cols, (j - 1) % cols
                wide = cols == 2 and j == shown and shown % 2 == 1   # a lone last tile spans both columns
                tiles.append({"week": i, "slot": j + 1, "x": ex + cc * (cw + gap), "y": y + r * (ch + gap),
                              "w": ew if wide else cw, "h": ch, "more": n_extra - shown if j == shown else 0})
        y += bh + gap
    return {"tiles": tiles, "labels": labels, "band": bh}


def _cover(img: Image.Image, w: int, h: int) -> Image.Image:
    """Scale to fill w x h, cropping the middle."""
    img = img.convert("RGB")
    return ImageOps.fit(img, (w, h), Image.LANCZOS, centering=(0.5, 0.5))


def make_collage(month_start: date, rows: list[dict] | None = None, images: dict | None = None) -> bytes:
    """Draw the collage for a month and return JPEG bytes. `rows` + `images` ({id: PIL image}) let
    check_setup draw from made-up photos instead of storage."""
    ph = rows if rows is not None else photos_in_month(month_start)
    if not ph:
        raise ValueError(f"no photos in {month_start:%B %Y}")
    weeks = list(dict.fromkeys(p["week_start"] for p in ph))
    counts = [sum(1 for p in ph if p["week_start"] == w) for w in weeks]
    lay = collage_layout(counts)
    print(f"[collage] {month_start:%B %Y}: {len(ph)} photos in {len(weeks)} weeks")
    ink, muted = "#23363A", "#6B5A3E"

    def font(file, size):
        try:
            return ImageFont.truetype(str(FONTS / file), size)
        except OSError:
            return ImageFont.load_default()
    head, body = font("BricolageGrotesque-Bold.ttf", 120), font("WorkSans-Regular.ttf", 46)
    lab = font("BricolageGrotesque-Bold.ttf", 40)
    more_f = font("BricolageGrotesque-Bold.ttf", 90)
    canvas = Image.new("RGB", (COLLAGE_W, COLLAGE_H), "#F6EEE3")
    dr = ImageDraw.Draw(canvas)
    dr.text((70, 60), month_start.strftime("%B %Y"), font=head, fill=ink)
    dr.text((74, 200), f"{APP_TITLE} · {len(ph)} {'photo' if len(ph) == 1 else 'photos'}", font=body, fill=muted)
    for i, w in enumerate(weeks, 1):
        wk = [p for p in ph if p["week_start"] == w]
        lb = next(l for l in lay["labels"] if l["week"] == i)
        cap = (wk[0].get("caption") or "").strip()
        if len(cap) > 70:
            cap = cap[:68] + "…"
        dr.text((lb["x"], lb["y"] + 8), week_label(w) + (f"  ·  {cap}" if cap else ""), font=lab, fill=ink)
        for t in [t for t in lay["tiles"] if t["week"] == i]:
            p = wk[t["slot"] - 1]
            src = images[p["id"]] if images is not None else Image.open(io.BytesIO(st_download(p["path"])))
            tile = _cover(src, t["w"], t["h"])
            if t["more"] > 0:
                shade = Image.new("RGB", tile.size, "#23363A")
                tile = Image.blend(tile, shade, 0.55)
                td = ImageDraw.Draw(tile)
                td.text((t["w"] / 2, t["h"] / 2), f"+{t['more']}", font=more_f, fill="white", anchor="mm")
            canvas.paste(tile, (t["x"], t["y"]))
        print(f"[collage]   week {i} of {len(weeks)} drawn")
    out = io.BytesIO()
    canvas.save(out, "JPEG", quality=90, dpi=(300, 300))
    return out.getvalue()


def collage_key(month_start: date) -> str:
    return f"collage:{month_start:%Y-%m}"


def collage_path(month_start: date) -> str:
    return f"collages/{month_start:%Y-%m}.jpg"


def save_collage(month_start: date) -> bytes:
    """Make (or remake) the collage and keep a copy in storage."""
    data = make_collage(month_start)
    st_upload(data, collage_path(month_start))
    db.set_setting(collage_key(month_start), now().strftime("%Y-%m-%d %H:%M"))
    return data
