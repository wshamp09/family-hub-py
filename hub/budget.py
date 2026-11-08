"""Budget calculations. Mirrors the household budget spreadsheet:
  monthly -> weekly = monthly * 12 / 52 -> daily = weekly / 7 ; yearly = monthly * 12
  pay per check -> monthly = check * checks_per_year / 12 (26 = every 2 weeks)
  shared expenses are split equally between the people with income rows
  % of net / gross = yearly expense / yearly income
check_setup.py verifies these against the spreadsheet's own results."""
from __future__ import annotations

from collections import defaultdict

from . import db
from .data import get_people, person_name

BILL_MONTHS = {"monthly": 1, "quarterly": 3, "annual": 12}


def per_period(monthly: float) -> dict:
    weekly = monthly * 12 / 52
    return {"monthly": monthly, "weekly": weekly, "daily": weekly / 7, "yearly": monthly * 12}


def budget_calc(shared: list[dict], personal: list[dict], income: list[dict]) -> dict:
    """shared: [{name, monthly}], personal: [{person, name, monthly}],
    income: [{person, net_per_check, gross_per_check, checks_per_year}]"""
    inc = []
    for r in income:
        x = dict(r)
        x["net_monthly"] = float(x["net_per_check"] or 0) * float(x["checks_per_year"] or 0) / 12
        x["gross_monthly"] = float(x["gross_per_check"] or 0) * float(x["checks_per_year"] or 0) / 12
        x["net_weekly"] = x["net_monthly"] * 12 / 52
        x["net_daily"] = x["net_weekly"] / 7
        x["net_yearly"] = x["net_monthly"] * 12
        x["gross_weekly"] = x["gross_monthly"] * 12 / 52
        x["gross_daily"] = x["gross_weekly"] / 7
        x["gross_yearly"] = x["gross_monthly"] * 12
        inc.append(x)
    net_y = sum(x["net_yearly"] for x in inc)
    gross_y = sum(x["gross_yearly"] for x in inc)
    n_split = max(1, len(inc))
    by_person = {x["person"]: x for x in inc}

    def div(a, b):
        return a / b if b else float("nan")

    sh = []
    for r in shared:
        x = {"name": r["name"], **per_period(float(r["monthly"] or 0))}
        x["pct_net"] = div(x["yearly"], net_y)
        x["pct_gross"] = div(x["yearly"], gross_y)
        sh.append(x)
    shared_month = sum(x["monthly"] for x in sh)
    shared_pp = shared_month / n_split

    pe = []
    for r in personal:
        x = {"person": r["person"], "name": r["name"], **per_period(float(r["monthly"] or 0))}
        p = by_person.get(r["person"])
        x["pct_net"] = div(x["yearly"], p["net_yearly"]) if p else float("nan")
        pe.append(x)

    summary = []
    for x in inc:
        pers_month = sum(p["monthly"] for p in pe if p["person"] == x["person"])
        exp_m = shared_pp + pers_month
        sur_m = x["net_monthly"] - exp_m
        exp_y = shared_month * 12 / n_split + pers_month * 12
        summary.append({"person": x["person"], "expense_monthly": exp_m, "surplus_monthly": sur_m,
                        "expense_weekly": exp_m * 12 / 52, "surplus_weekly": sur_m * 12 / 52,
                        "expense_daily": exp_m * 12 / 52 / 7, "surplus_daily": sur_m * 12 / 52 / 7,
                        "expense_yearly": exp_y, "surplus_yearly": x["net_yearly"] - exp_y,
                        "expense_pct_net": div(exp_y, x["net_yearly"]),
                        "expense_pct_gross": div(exp_y, x["gross_yearly"])})
    e_m = sum(s["expense_monthly"] for s in summary)
    s_m = sum(s["surplus_monthly"] for s in summary)
    e_y = sum(s["expense_yearly"] for s in summary)
    summary.append({"person": "Total", "expense_monthly": e_m, "surplus_monthly": s_m,
                    "expense_weekly": e_m * 12 / 52, "surplus_weekly": s_m * 12 / 52,
                    "expense_daily": e_m * 12 / 52 / 7, "surplus_daily": s_m * 12 / 52 / 7,
                    "expense_yearly": e_y, "surplus_yearly": sum(s["surplus_yearly"] for s in summary),
                    "expense_pct_net": div(e_y, net_y), "expense_pct_gross": div(e_y, gross_y)})
    net_m = sum(x["net_monthly"] for x in inc)
    gross_m = sum(x["gross_monthly"] for x in inc)
    return {
        "income": inc, "shared": sh, "shared_total": per_period(shared_month),
        "shared_per_person": per_period(shared_pp), "personal": pe, "summary": summary,
        "rules": [{"rule": "25% of net", "amount": 0.25 * net_m}, {"rule": "36% of net", "amount": 0.36 * net_m},
                  {"rule": "45% of net", "amount": 0.45 * net_m}, {"rule": "28% of gross", "amount": 0.28 * gross_m},
                  {"rule": "36% of gross", "amount": 0.36 * gross_m}],
        "tax": [{"person": x["person"], "pct": div(x["gross_yearly"] - x["net_yearly"], x["gross_yearly"])}
                for x in inc] + [{"person": "Total", "pct": div(gross_y - net_y, gross_y)}],
    }


def budget_inputs() -> dict:
    """Everything the budget needs from the database (one table: bills = all expenses)."""
    ppl = get_people()
    inc = db.get("""select i.person_id, p.name as person, i.net_per_check, i.gross_per_check, i.checks_per_year
                      from income i join people p on p.id = i.person_id
                     where p.is_active order by p.sort_order, p.name""")
    ex = db.get("""select id, name, category, amount, frequency, budget_scope, default_payer_id, track, due_day, autopay
                     from bills where active order by id""")
    shared, personal = [], []
    for e in ex:
        e["monthly"] = float(e["amount"] or 0) / BILL_MONTHS.get(e["frequency"], 1)
        if e["budget_scope"] == "personal":
            e["person"] = person_name(ppl, e["default_payer_id"]) or "Unassigned"
            personal.append(e)
        else:
            shared.append(e)
    return {"shared": shared, "personal": personal, "income": inc, "people": ppl}


def budget_by_category(shared: list[dict], personal: list[dict]) -> list[dict]:
    """Monthly spending by category (shared at full value + everyone's personal items)."""
    tot = defaultdict(float)
    for e in shared + personal:
        tot[e.get("category") or "Other"] += float(e["monthly"] or 0)
    return sorted(({"category": k, "monthly": v} for k, v in tot.items()), key=lambda r: -r["monthly"])
