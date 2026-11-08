"""Grocery list: parse ingredient lines and combine duplicates.
"1 onion" + "2 onions" -> "3 onion"; "1 cup milk" + "1/2 cup milk" -> "1 1/2 cup milk".
Items only combine when the name and unit match; anything unparseable is added as is."""
from __future__ import annotations

import math
import re

from . import db

UNIT_MAP = {
    "cup": "cup", "cups": "cup", "c": "cup", "tbsp": "tbsp", "tbs": "tbsp", "tablespoon": "tbsp",
    "tablespoons": "tbsp", "tsp": "tsp", "teaspoon": "tsp", "teaspoons": "tsp",
    "lb": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb", "oz": "oz", "ounce": "oz", "ounces": "oz",
    "g": "g", "gram": "g", "grams": "g", "kg": "kg", "ml": "ml", "l": "l", "liter": "l", "liters": "l",
    "can": "can", "cans": "can", "clove": "clove", "cloves": "clove", "pinch": "pinch",
    "bunch": "bunch", "bunches": "bunch", "package": "pkg", "packages": "pkg", "pkg": "pkg",
    "bag": "bag", "bags": "bag", "slice": "slice", "slices": "slice", "stick": "stick", "sticks": "stick",
    "jar": "jar", "jars": "jar", "head": "head", "heads": "head", "dozen": "dozen", "box": "box",
    "boxes": "box", "bottle": "bottle", "bottles": "bottle", "container": "container",
    "containers": "container", "qt": "qt", "quart": "qt", "quarts": "qt", "pint": "pt", "pints": "pt",
    "gallon": "gal", "gallons": "gal"}

DESCRIPTORS = {"large", "medium", "small", "fresh", "chopped", "diced", "minced", "sliced", "shredded", "grated",
               "boneless", "skinless", "ripe", "whole", "frozen", "raw", "cooked", "peeled", "of"}

FRACTION_CHARS = {"½": " 1/2", "¼": " 1/4", "¾": " 3/4", "⅓": " 1/3", "⅔": " 2/3", "⅛": " 1/8"}


def parse_number(x: str) -> float:
    """'1', '1.5', '1/2', '1 1/2' -> number"""
    total = 0.0
    for p in x.strip().split():
        if "/" in p:
            a, b = p.split("/")
            total += float(a) / float(b)
        else:
            total += float(p)
    return total


def singular(w: str) -> str:
    if w.endswith("ies"):
        return w[:-3] + "y"
    if re.search(r"(oes|ches|shes|sses|xes)$", w):
        return w[:-2]
    if re.search(r"[^s]s$", w):
        return w[:-1]
    return w


def name_key(name: str) -> str:
    k = name.lower()
    k = re.sub(r",.*$", "", k)            # drop ", chopped" etc.
    k = re.sub(r"\([^)]*\)", " ", k)      # drop "(14 oz)"
    k = re.sub(r"[^a-z ]", " ", k)
    w = [x for x in k.split() if x and x not in DESCRIPTORS]
    if not w:
        return name.lower().strip()
    w[-1] = singular(w[-1])
    return " ".join(w)


def parse_ingredient(line: str) -> dict:
    txt = line.strip()
    for ch, rep in FRACTION_CHARS.items():
        txt = txt.replace(ch, rep)
    txt = re.sub(r"\s+", " ", txt).strip()
    qty, rest = None, txt
    m = re.match(r"^(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s+(.*)$", txt)   # range "2-3": use the larger
    if m:
        qty, rest = float(m.group(2)), m.group(3)
    else:
        m = re.match(r"^(\d+(?:\.\d+)?(?:\s+\d+/\d+)?|\d+/\d+)\s+(.*)$", txt)
        if m:
            qty, rest = parse_number(m.group(1)), m.group(2)
    unit = ""
    if qty is not None:
        first = rest.split(" ")[0].lower().rstrip(".")
        if first in UNIT_MAP and " " in rest:
            unit = UNIT_MAP[first]
            rest = re.sub(r"^\S+\s+", "", rest)
    rest = rest.strip()
    return {"qty": qty, "unit": unit, "name": rest, "key": name_key(rest)}


def fmt_qty(q) -> str:
    """1.5 -> '1 1/2', 0.333 -> '1/3', 2 -> '2'"""
    if q is None:
        return ""
    whole = math.floor(q + 1e-9)
    frac = q - whole
    if frac < 0.02:
        return str(int(whole))
    for name, val in [("1/8", .125), ("1/4", .25), ("1/3", 1 / 3), ("1/2", .5), ("2/3", 2 / 3), ("3/4", .75)]:
        if abs(val - frac) < 0.02:
            return f"{int(whole)} {name}" if whole > 0 else name
    r = round(q, 2)
    return str(int(r)) if r == int(r) else f"{r:g}"


def qty_text(q, unit: str) -> str:
    return f"{fmt_qty(q)} {unit}".strip()


def add_grocery_items(lines: list[str], for_meal: str | None = None) -> dict:
    """Add lines to the list, combining with matching unticked items. Returns counts."""
    added = merged = 0
    for ln in [l for l in lines if l and l.strip()]:
        p = parse_ingredient(ln)
        hit = db.one("""select id, qty_num, for_meal from grocery_items
                         where not checked and name_key = $1 and coalesce(unit, '') = $2
                         order by id limit 1""", p["key"], p["unit"])
        if hit:
            q = None if hit["qty_num"] is None and p["qty"] is None else (hit["qty_num"] or 0) + (p["qty"] or 0)
            meals = [m for m in (hit["for_meal"] or "").split(", ") if m]
            if for_meal and for_meal not in meals:
                meals.append(for_meal)
            db.run("update grocery_items set qty_num = $2, quantity = $3, item = $4, for_meal = $5 where id = $1",
                   hit["id"], q, None if q is None else qty_text(q, p["unit"]), p["name"],
                   ", ".join(meals) if meals else None)
            merged += 1
        else:
            db.run("""insert into grocery_items (item, quantity, qty_num, unit, name_key, for_meal)
                      values ($1, $2, $3, $4, $5, $6)""",
                   p["name"], None if p["qty"] is None else qty_text(p["qty"], p["unit"]), p["qty"], p["unit"],
                   p["key"], for_meal)
            added += 1
    print(f"[grocery] {added} added, {merged} combined")
    return {"added": added, "merged": merged}
