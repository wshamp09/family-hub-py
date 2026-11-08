"""Sitter info sheet: a one-page PDF (reportlab) or image (Pillow) built from selected contacts
and info. Text shrinks until everything fits on one page (never below 60%)."""
from __future__ import annotations

import io
import textwrap

from .config import APP_DIR, has_text

SHEET_INK, SHEET_MUTED, SHEET_ACCENT, SHEET_RULE = "#23363A", "#5f6b67", "#2E7D6B", "#d5e2dd"
FONTS = APP_DIR / "static" / "fonts"
PT = {"title": 26, "sub": 11, "head": 13, "pair": 12, "kv": 12, "text": 12, "small": 10.5}
GAP = {"title": 1.2, "sub": 1.9, "head": 2.6, "pair": 1.75, "kv": 1.75, "text": 1.45, "small": 1.35}


def sitter_lines(d: dict, scale: float, width_in: float) -> list[dict]:
    """The sheet as a list of lines at a given text scale (1 = 12 pt body text)."""
    body_pt = 12 * scale
    chars = max(30, int(width_in / (0.52 * body_pt / 72)))

    def wrap(x, w=chars):
        if not has_text(x):
            return []
        out = []
        for p in str(x).split("\n"):
            out += [""] if not p.strip() else textwrap.wrap(p, width=w)
        return out

    L = [{"kind": "title", "text": d["title"]}, {"kind": "sub", "text": d["subtitle"]}]
    if has_text(d.get("address")):
        L.append({"kind": "head", "text": "Home address"})
        L += [{"kind": "text", "text": ln} for ln in wrap(d["address"])]
    if d.get("contacts"):
        L.append({"kind": "head", "text": "Contacts"})
        for c in d["contacts"]:
            L.append({"kind": "pair", "left": c["name"], "sub": c.get("category") or "", "right": c.get("phone") or ""})
            L += [{"kind": "small", "text": ln} for ln in wrap(c.get("notes"), chars - 4)]
    if d.get("info"):
        L.append({"kind": "head", "text": "Codes & Wi-Fi"})
        L += [{"kind": "kv", "left": i["label"], "right": i.get("value") or ""} for i in d["info"]]
    if has_text(d.get("notes")):
        L.append({"kind": "head", "text": "Notes"})
        L += [{"kind": "text", "text": ln} for ln in wrap(d["notes"])]
    return L


def line_height(kind: str, scale: float) -> float:
    """Height in inches."""
    return PT[kind] * scale * GAP[kind] / 72


def fit(d: dict, width_in: float, avail: float):
    scale = 1.0
    while True:
        L = sitter_lines(d, scale, width_in)
        need = sum(line_height(x["kind"], scale) for x in L)
        if need <= avail or scale <= 0.6:
            return L, scale
        scale = round(scale - 0.05, 2)


# ---- PDF -------------------------------------------------------------------------------------------
def _register_pdf_fonts():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    if "WorkSans" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("WorkSans", str(FONTS / "WorkSans-Regular.ttf")))
        pdfmetrics.registerFont(TTFont("WorkSans-Bold", str(FONTS / "WorkSans-Bold.ttf")))
        pdfmetrics.registerFont(TTFont("Bricolage-Bold", str(FONTS / "BricolageGrotesque-Bold.ttf")))


def sitter_pdf(d: dict, page_w: float = 8.5, page_h: float = 11, margin: float = 0.7) -> bytes:
    from reportlab.lib.colors import HexColor
    from reportlab.pdfgen import canvas
    _register_pdf_fonts()
    width_in, avail = page_w - 2 * margin, page_h - 2 * margin
    L, scale = fit(d, width_in, avail)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_w * 72, page_h * 72))
    c.setTitle(d["title"])
    x0, top = margin * 72, (page_h - margin) * 72
    y = top

    def txt(s, x, y_, pt, font="WorkSans", col=SHEET_INK, right=False):
        c.setFont(font, pt * scale)
        c.setFillColor(HexColor(col))
        base = y_ - pt * scale * 0.85            # draw from the top of the line
        (c.drawRightString if right else c.drawString)(x, base, s or "")

    W = width_in * 72
    for ln in L:
        h = line_height(ln["kind"], scale) * 72
        k = ln["kind"]
        if k == "title":
            txt(ln["text"], x0, y, 26, "Bricolage-Bold", SHEET_ACCENT)
        elif k == "sub":
            txt(ln["text"], x0, y, 11, col=SHEET_MUTED)
        elif k == "head":
            t2 = y - 0.9 * 13 * scale
            txt(ln["text"].upper(), x0, t2, 10.5, "WorkSans-Bold", SHEET_ACCENT)
            ry = t2 - 1.25 * 10.5 * scale - 2
            c.setStrokeColor(HexColor(SHEET_RULE)); c.setLineWidth(1)
            c.line(x0, ry, x0 + W, ry)
        elif k == "pair":
            txt(ln["left"], x0, y, 12, "WorkSans-Bold")
            if has_text(ln["sub"]):
                from reportlab.pdfbase.pdfmetrics import stringWidth
                nw = stringWidth(ln["left"], "WorkSans-Bold", 12 * scale)
                txt("  " + ln["sub"], x0 + nw, y - 1.2 * scale, 10.5, col=SHEET_MUTED)
            txt(ln["right"], x0 + W, y, 12, "WorkSans-Bold", right=True)
        elif k == "kv":
            txt(ln["left"], x0, y, 12, col=SHEET_MUTED)
            txt(ln["right"], x0 + W, y, 13, "WorkSans-Bold", right=True)
        elif k == "text":
            txt(ln["text"], x0, y, 12)
        elif k == "small":
            txt(ln["text"], x0 + 0.2 * 72, y, 10.5, col=SHEET_MUTED)
        y -= h
    c.showPage()
    c.save()
    return buf.getvalue()


# ---- Image (portrait, phone-friendly, easy to text) ---------------------------------------------------
def sitter_png(d: dict, page_w: float = 6, page_h: float = 9, margin: float = 0.45, dpi: int = 200) -> bytes:
    from PIL import Image, ImageDraw, ImageFont
    width_in, avail = page_w - 2 * margin, page_h - 2 * margin
    L, scale = fit(d, width_in, avail)
    img = Image.new("RGB", (int(page_w * dpi), int(page_h * dpi)), "white")
    dr = ImageDraw.Draw(img)
    px = lambda inch: int(round(inch * dpi))  # noqa: E731
    font_cache = {}

    def font(name, pt):
        k = (name, pt)
        if k not in font_cache:
            file = {"WorkSans": "WorkSans-Regular.ttf", "WorkSans-Bold": "WorkSans-Bold.ttf",
                    "Bricolage-Bold": "BricolageGrotesque-Bold.ttf"}[name]
            font_cache[k] = ImageFont.truetype(str(FONTS / file), max(8, int(pt * scale * dpi / 72)))
        return font_cache[k]

    def txt(s, x_in, y_in, pt, name="WorkSans", col=SHEET_INK, right=False):
        f = font(name, pt)
        x = px(x_in)
        if right:
            x -= int(dr.textlength(s or "", font=f))
        dr.text((x, px(y_in)), s or "", font=f, fill=col)

    x0, y, W = margin, margin, width_in
    for ln in L:
        h = line_height(ln["kind"], scale)
        k = ln["kind"]
        if k == "title":
            txt(ln["text"], x0, y, 26, "Bricolage-Bold", SHEET_ACCENT)
        elif k == "sub":
            txt(ln["text"], x0, y, 11, col=SHEET_MUTED)
        elif k == "head":
            t2 = y + 0.9 * 13 * scale / 72
            txt(ln["text"].upper(), x0, t2, 10.5, "WorkSans-Bold", SHEET_ACCENT)
            ry = px(t2 + 1.35 * 10.5 * scale / 72)
            dr.line([(px(x0), ry), (px(x0 + W), ry)], fill=SHEET_RULE, width=2)
        elif k == "pair":
            txt(ln["left"], x0, y, 12, "WorkSans-Bold")
            if has_text(ln["sub"]):
                nw = dr.textlength(ln["left"], font=font("WorkSans-Bold", 12)) / dpi
                txt("  " + ln["sub"], x0 + nw, y + 1.2 * scale / 72, 10.5, col=SHEET_MUTED)
            txt(ln["right"], x0 + W, y, 12, "WorkSans-Bold", right=True)
        elif k == "kv":
            txt(ln["left"], x0, y, 12, col=SHEET_MUTED)
            txt(ln["right"], x0 + W, y, 13, "WorkSans-Bold", right=True)
        elif k == "text":
            txt(ln["text"], x0, y, 12)
        elif k == "small":
            txt(ln["text"], x0 + 0.2, y, 10.5, col=SHEET_MUTED)
        y += h
    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()
