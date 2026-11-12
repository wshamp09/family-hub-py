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

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

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
PREVIEW_PX = 220


def preview_jpeg(raw: bytes, px: int = PREVIEW_PX) -> bytes | None:
    """A small, right-way-up JPEG of an upload for the caption list (browsers can't show iPhone HEIC files)."""
    try:
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw)))
        im.thumbnail((px, px))
        out = io.BytesIO()
        im.convert("RGB").save(out, "JPEG", quality=80)
        return out.getvalue()
    except Exception:  # noqa: BLE001
        return None


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


# Monthly collage: an 8 x 10 in page (2400 x 3000 px at 300 dpi). Each week is a band headed by its dates; the
# photo of the week is a large print on the left, and up to 6 others are smaller prints scattered in one or two
# staggered rows to its right (the last shows "+N" if there are more). Prints overlap a little, like a scrapbook.
COLLAGE_W, COLLAGE_H = 2400, 3000
PRINT_FRAME = (0.045, 3.4)       # side border (share of the shorter side) and bottom border (times the side)


def print_size(box_h: float, aspect: float) -> tuple[int, int]:
    """A print's outer size for a given height and photo shape (width / height, held to 0.75-1.5)."""
    a = min(1.5, max(0.75, aspect or 1.0))
    side = box_h * PRINT_FRAME[0]
    photo_h = box_h - side - side * PRINT_FRAME[1]
    return round(photo_h * a + 2 * side), round(box_h)


def scrapbook_layout(weeks: list[list[float]], W: int = COLLAGE_W, H: int = COLLAGE_H, margin: int = 70,
                     header: int = 290, label: int = 62, gap: int = 46, max_extra: int = 6) -> dict:
    """weeks: each week's photo shapes (width / height), photo of the week first. Returns the prints
    (centre, size, week, slot, "+N") and the week labels. Pure; tested in check_setup."""
    k = len(weeks)
    if not k:
        raise ValueError("no photos this month")
    bh = (H - 2 * margin - header - k * label - (k - 1) * gap) / k
    inner = W - 2 * margin
    prints, labels = [], []
    y = margin + header
    for i, shapes in enumerate(weeks, 1):
        labels.append({"week": i, "x": margin, "y": round(y), "h": label})
        top = y + label
        fw, fh = print_size(min(bh * 1.06, H - 40 - top), shapes[0])
        extra = shapes[1:]
        shown = min(len(extra), max_extra)
        fcx = margin + fw / 2 + 8 if shown else margin + inner / 2
        prints.append({"week": i, "slot": 1, "cx": round(fcx), "cy": round(top + bh / 2), "w": fw, "h": fh, "more": 0})
        if shown:
            x0 = margin + fw + gap
            rw = W - margin - x0
            rows = 1 if shown <= 3 else 2
            per_row = math.ceil(shown / rows)
            cell_w, cell_h = rw / per_row, bh / rows
            for j in range(shown):
                r, c = j // per_row, j % per_row
                in_row = per_row if r < rows - 1 else shown - per_row * (rows - 1)
                pad = (per_row - in_row) * cell_w / 2                     # centre a shorter last row
                stagger = (cell_w * 0.18) * (1 if r % 2 else -1) if rows == 2 else 0
                pw, ph = print_size(min(cell_h * (1.26 if rows == 2 else 1.0), bh), extra[j])
                if pw > cell_w * 1.18:                                    # keep wide prints from crowding
                    pw, ph = print_size(ph * cell_w * 1.18 / pw, extra[j])
                cx = x0 + pad + cell_w * (c + 0.5) + stagger
                cx = min(max(cx, x0 + pw / 2), W - margin - pw / 2)
                cy = top + cell_h * (r + 0.5) + (cell_h * 0.08 * (1 if r else -1) if rows == 2 else 0)
                cy = min(max(cy, ph / 2 + 20), H - 20 - ph / 2)
                prints.append({"week": i, "slot": j + 2, "cx": round(cx), "cy": round(cy), "w": pw, "h": ph,
                               "more": len(extra) - shown if j == shown - 1 else 0})
        y = top + bh + gap
    return {"prints": prints, "labels": labels, "band": bh}


def _cover(img: Image.Image, w: int, h: int) -> Image.Image:
    """Scale to fill w x h, cropping the middle."""
    img = img.convert("RGB")
    return ImageOps.fit(img, (w, h), Image.LANCZOS, centering=(0.5, 0.5))


# Polaroid scrapbook look: each photo is a white-framed print (deeper bottom edge with its caption), tilted a
# little and slightly overlapping its neighbours, held on with washi tape. Tilts and offsets come from a seeded
# random generator (month + photo), so remaking a month's collage gives the same arrangement.
PAPER = "#F3E8D6"
INK, MUTED = "#2E2A24", "#6B5A3E"
TAPE_COLOURS = ["#E8B4B8", "#A8D5BA", "#F6D186", "#9EC1E6", "#C7B7E2", "#F4A582"]
TILT_FEATURED, TILT_OTHER = 2.5, 6.0     # largest tilt in degrees


def _font(file: str, size: int):
    try:
        return ImageFont.truetype(str(FONTS / file), size)
    except OSError:
        return ImageFont.load_default()


def _fit_text(dr, text: str, font, max_w: int) -> str:
    if dr.textlength(text, font=font) <= max_w:
        return text
    while text and dr.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return text.rstrip() + "…"


def polaroid(img: Image.Image, w: int, h: int, caption: str = "", more: int = 0) -> Image.Image:
    """A white-framed print, w x h (RGBA): the photo fills the top, the caption sits in the deeper bottom edge."""
    side = max(10, round(h * PRINT_FRAME[0]))
    bottom = round(side * PRINT_FRAME[1])
    pw, ph_ = w - 2 * side, h - side - bottom
    card = Image.new("RGBA", (w, h), "#FFFDF8")
    photo = _cover(img, pw, ph_)
    if more > 0:
        photo = Image.blend(photo, Image.new("RGB", photo.size, "#23363A"), 0.55)
        ImageDraw.Draw(photo).text((pw / 2, ph_ / 2), f"+{more}", font=_font("BricolageGrotesque-Bold.ttf", max(40, ph_ // 4)),
                                   fill="white", anchor="mm")
    card.paste(photo, (side, side))
    dr = ImageDraw.Draw(card)
    dr.rectangle([0, 0, w - 1, h - 1], outline="#E9E1D2", width=2)
    if caption:
        f = _font("WorkSans-Italic.ttf", max(22, min(58, round(bottom * 0.42))))
        dr.text((w / 2, h - bottom / 2 - side * 0.1), _fit_text(dr, caption, f, w - 2 * side), font=f, fill=INK, anchor="mm")
    return card


def _tape(w: int, h: int, colour: str, angle: float) -> Image.Image:
    t = Image.new("RGBA", (w, h), colour + "B4")          # see-through, like real washi tape
    d = ImageDraw.Draw(t)
    for x in range(0, w, max(6, h // 3)):                 # faint stripes
        d.line([(x, 0), (x - h, h)], fill=(255, 255, 255, 40), width=max(2, h // 10))
    for x in (0, w - 1):                                  # torn ends
        for y in range(0, h, 6):
            d.point((x, y), fill=(0, 0, 0, 0))
    return t.rotate(angle, resample=Image.BICUBIC, expand=True)


def _place(canvas: Image.Image, card: Image.Image, cx: int, cy: int, angle: float, rng: random.Random) -> None:
    """Rotate a print, drop a soft shadow, paste it centred on (cx, cy) and tape it on."""
    rot = card.rotate(angle, resample=Image.BICUBIC, expand=True)
    alpha = rot.split()[3]
    shadow = Image.new("RGBA", rot.size, (40, 30, 20, 0))
    shadow.putalpha(alpha.point(lambda a: int(a * 0.38)).filter(ImageFilter.GaussianBlur(14)))
    x, y = cx - rot.width // 2, cy - rot.height // 2
    canvas.alpha_composite(shadow, (max(0, x + 10), max(0, y + 14)))
    canvas.alpha_composite(rot, (max(0, x), max(0, y)))
    tw, th = max(90, card.width // 3), max(34, card.width // 11)
    tape = _tape(tw, th, rng.choice(TAPE_COLOURS), angle + rng.uniform(-8, 8))
    canvas.alpha_composite(tape, (max(0, cx - tape.width // 2 + rng.randint(-20, 20)), max(0, y - tape.height // 3)))


def _paper(w: int, h: int) -> Image.Image:
    base = Image.new("RGB", (w, h), PAPER)
    grain = Image.effect_noise((w, h), 18).convert("RGB")
    return Image.blend(base, grain, 0.06).convert("RGBA")


def make_collage(month_start: date, rows: list[dict] | None = None, images: dict | None = None) -> bytes:
    """Draw the month's polaroid collage and return JPEG bytes. `rows` + `images` ({id: PIL image}) let
    check_setup draw from made-up photos instead of storage."""
    ph = rows if rows is not None else photos_in_month(month_start)
    if not ph:
        raise ValueError(f"no photos in {month_start:%B %Y}")
    weeks = list(dict.fromkeys(p["week_start"] for p in ph))
    by_week = [[p for p in ph if p["week_start"] == w] for w in weeks]
    srcs = {p["id"]: (images[p["id"]] if images is not None else Image.open(io.BytesIO(st_download(p["path"]))))
            for p in ph}
    lay = scrapbook_layout([[srcs[p["id"]].width / srcs[p["id"]].height for p in wk] for wk in by_week])
    print(f"[collage] {month_start:%B %Y}: {len(ph)} photos in {len(weeks)} weeks")
    canvas = _paper(COLLAGE_W, COLLAGE_H)
    dr = ImageDraw.Draw(canvas)
    # title on a big strip of tape
    head, sub = _font("BricolageGrotesque-Bold.ttf", 118), _font("WorkSans-Italic.ttf", 46)
    title = month_start.strftime("%B %Y")
    tw = int(dr.textlength(title, font=head)) + 120
    banner = Image.new("RGBA", (tw, 170), TAPE_COLOURS[month_start.month % len(TAPE_COLOURS)] + "D0")
    ImageDraw.Draw(banner).text((tw / 2, 85), title, font=head, fill=INK, anchor="mm")
    banner = banner.rotate(-1.5, resample=Image.BICUBIC, expand=True)
    canvas.alpha_composite(banner, (60, 40))
    dr.text((80, 212), f"{APP_TITLE} · {len(ph)} {'photo' if len(ph) == 1 else 'photos'}", font=sub, fill=MUTED)
    lab = _font("BricolageGrotesque-Bold.ttf", 38)
    week_tags = []          # week date labels go on last, on top of the prints
    for i, w in enumerate(weeks, 1):
        rng = random.Random(f"{month_start:%Y-%m}-{i}")
        wk = by_week[i - 1]
        lb = next(l for l in lay["labels"] if l["week"] == i)
        text = week_label(w)
        lw = int(dr.textlength(text, font=lab)) + 50
        strip = Image.new("RGBA", (lw, 56), TAPE_COLOURS[(i + 2) % len(TAPE_COLOURS)] + "E6")
        ImageDraw.Draw(strip).text((lw / 2, 28), text, font=lab, fill=INK, anchor="mm")
        week_tags.append((strip.rotate(rng.uniform(-2, 2), resample=Image.BICUBIC, expand=True), (lb["x"], lb["y"] + 2)))
        mine = [t for t in lay["prints"] if t["week"] == i]
        for t in sorted(mine, key=lambda t: t["slot"] == 1):          # the photo of the week goes on top
            p = wk[t["slot"] - 1]
            prng = random.Random(f"{month_start:%Y-%m}-{p['id']}")
            tilt = TILT_FEATURED if t["slot"] == 1 else TILT_OTHER
            card = polaroid(srcs[p["id"]], t["w"], t["h"], (p.get("caption") or "").strip(), t["more"])
            _place(canvas, card, t["cx"] + prng.randint(-10, 10), t["cy"] + prng.randint(-8, 8),
                   prng.uniform(-tilt, tilt), prng)
        print(f"[collage]   week {i} of {len(weeks)} drawn")
    for tag, at in week_tags:
        canvas.alpha_composite(tag, at)
    out = io.BytesIO()
    canvas.convert("RGB").save(out, "JPEG", quality=90, dpi=(300, 300))
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
