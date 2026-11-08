"""Budget: monthly plan mirroring the household spreadsheet. Every expense is one row in `bills`;
"Track & remind" puts it on the Bills checklist. All maths is in hub/budget.py."""
from __future__ import annotations

import hashlib
import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from hub import budget, db, forms, ui
from hub.budget import BILL_MONTHS, per_period
from hub.config import CHART_COLORS
from hub.dates import money


def pct(x) -> str:
    return "—" if x is None or not math.isfinite(x) else f"{100 * x:.1f}%"


def _layout(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(barmode="stack", bargap=0.5, height=height, paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=8, r=12, t=8, b=8),
                      font=dict(family="Work Sans, system-ui, sans-serif", size=12, color="#52514e"),
                      xaxis=dict(title="", tickprefix="$", tickformat=",.0f", gridcolor="#e9e9e6", zeroline=False,
                                 fixedrange=True),
                      yaxis=dict(title="", autorange="reversed", automargin=True, fixedrange=True),
                      legend=dict(orientation="h", x=0, y=-0.25),
                      hoverlabel=dict(bgcolor="#ffffff", bordercolor="#d9d9d6", font=dict(color="#0b0b0b")))
    return fig


def chart_people(k: dict) -> go.Figure:
    """Each person's monthly take-home split into: half of shared, own expenses, what's left."""
    s = [x for x in k["summary"] if x["person"] != "Total"]
    names = [x["person"] for x in s]
    own = [sum(p["monthly"] for p in k["personal"] if p["person"] == n) for n in names]
    half = [k["shared_per_person"]["monthly"]] * len(s)
    left = [max(0, x["surplus_monthly"]) for x in s]
    gap = dict(color="#ffffff", width=2)
    fig = go.Figure()
    for vals, name, col in [(half, "Shared (half)", "shared"), (own, "Own expenses", "personal"), (left, "Left over", "surplus")]:
        fig.add_bar(y=names, x=vals, orientation="h", name=name, marker=dict(color=CHART_COLORS[col], line=gap),
                    hovertemplate=f"%{{y}} · {name.lower()}: %{{x:$,.0f}}<extra></extra>")
    return _layout(fig, 210)


def chart_categories(cats: list[dict]) -> go.Figure:
    """Monthly spending by category, largest first (one hue: magnitude, not identity)."""
    tot = sum(c["monthly"] for c in cats) or 1
    fig = go.Figure(go.Bar(y=[c["category"] for c in cats], x=[c["monthly"] for c in cats], orientation="h",
                           marker=dict(color=CHART_COLORS["shared"]),
                           customdata=[f"{100 * c['monthly'] / tot:.0f}%" for c in cats],
                           hovertemplate="%{y}: %{x:$,.0f} a month (%{customdata} of spending)<extra></extra>"))
    fig = _layout(fig, 60 + 32 * len(cats))
    fig.update_layout(showlegend=False, bargap=0.35)
    return fig


def _key(prefix: str, df: pd.DataFrame) -> str:
    return prefix + hashlib.md5(pd.util.hash_pandas_object(df, index=True).values.tobytes()).hexdigest()[:10]


def expense_table(nums: list[dict], meta: list[dict], pct_cols: dict, all_cols: bool, prefix: str,
                  total: dict | None = None, per_person: dict | None = None) -> None:
    """Editable table: change the Monthly column to update an expense; tick ✏️ to edit everything."""
    cols = ["monthly", "weekly", "daily", "yearly"] if all_cols else ["monthly", "yearly"]
    rows = []
    for n, m in zip(nums, meta):
        due = (("auto · " if m.get("autopay") else "") + f"due {m['due_day']}") if m.get("track") else ""
        r = {"id": m["id"], "✏️": False, "Expense": m["name"], "Category": m.get("category") or "", "Bills": due}
        for c in cols:
            r[c.capitalize()] = round(n[c], 2)
        for lbl, c in pct_cols.items():
            r[lbl] = pct(n[c])
        rows.append(r)
    df = pd.DataFrame(rows)
    key = _key(prefix, df)
    cfg = {"id": None, "✏️": st.column_config.CheckboxColumn("✏️", help="Tick to edit or delete", width="small"),
           "Monthly": st.column_config.NumberColumn("Monthly", format="$%.2f", min_value=0.0, step=1.0)}
    for c in cols[1:]:
        cfg[c.capitalize()] = st.column_config.NumberColumn(c.capitalize(), format="$%.2f")
    disabled = [c for c in df.columns if c not in ("✏️", "Monthly")]
    out = st.data_editor(df, key=key, hide_index=True, use_container_width=True, column_config=cfg, disabled=disabled)
    for i, r in out.iterrows():
        if r["✏️"]:
            forms.expense_dialog(int(r["id"]))
            break
        old = df.loc[i, "Monthly"]
        if r["Monthly"] is not None and not pd.isna(r["Monthly"]) and abs(float(r["Monthly"]) - float(old)) > 0.004:
            m = next(x for x in meta if x["id"] == r["id"])
            amount = round(float(r["Monthly"]) * BILL_MONTHS.get(m["frequency"], 1), 2)
            if ui.try_db(db.run, "Updated", "update bills set amount = $2 where id = $1", int(r["id"]), amount):
                st.rerun()
    if total is not None:
        t = " · ".join(f"{c.capitalize()} {money(total[c])}" for c in cols)
        st.caption(f"**Total:** {t}" + (" · **Per person:** " + " · ".join(f"{c.capitalize()} {money(per_person[c])}"
                                                                            for c in cols) if per_person else ""))
    if any(m["frequency"] != "monthly" for m in meta):
        st.caption("Quarterly and yearly expenses show their monthly share; changing it updates the full amount to match.")


def page() -> None:
    if not ui.can("money"):
        st.info("Ask an admin to turn on money pages for your login (Settings).")
        return
    b = budget.budget_inputs()
    inc_people = {x["person"] for x in b["income"]}
    k = budget.budget_calc(b["shared"], [p for p in b["personal"] if p["person"] in inc_people], b["income"]) \
        if b["income"] else None
    if k is None:
        st.warning("Add each person's pay per paycheck under Income below to see the budget.")
    else:
        tot = next(x for x in k["summary"] if x["person"] == "Total")
        c1, c2, c3 = st.columns(3)
        c1.metric("Monthly expenses", money(tot["expense_monthly"]))
        c2.metric("Monthly surplus", money(tot["surplus_monthly"]),
                  delta="on track" if tot["surplus_monthly"] >= 0 else "over budget",
                  delta_color="normal" if tot["surplus_monthly"] >= 0 else "inverse")
        c3.metric("Of take-home pay", pct(tot["expense_pct_net"]), f"{pct(tot['expense_pct_gross'])} of gross",
                  delta_color="off")
        with ui.card("Where the money goes"):
            t1, t2 = st.tabs(["By person", "By category"])
            with t1:
                st.caption("Each person's take-home pay per month.")
                st.plotly_chart(chart_people(k), use_container_width=True, config={"displayModeBar": False})
            with t2:
                st.caption("Monthly spending, shared and personal combined.")
                cats = budget.budget_by_category(b["shared"], b["personal"])
                if cats:
                    st.plotly_chart(chart_categories(cats), use_container_width=True, config={"displayModeBar": False})
    all_cols = st.toggle("Show weekly / daily columns", value=False, key="bud_all")
    if k:
        with ui.card("Per person each month"):
            cols = {"Expense": "expense_monthly", "Surplus": "surplus_monthly"}
            if all_cols:
                cols.update({"Weekly exp.": "expense_weekly", "Weekly surplus": "surplus_weekly",
                             "Daily exp.": "expense_daily", "Daily surplus": "surplus_daily"})
            st.dataframe(pd.DataFrame([{"": s["person"], **{l: money(s[c]) for l, c in cols.items()}} for s in k["summary"]]),
                         hide_index=True, use_container_width=True)
            st.dataframe(pd.DataFrame([{"Yearly": s["person"], "Expense": money(s["expense_yearly"]),
                                        "Surplus": money(s["surplus_yearly"]), "% of net": pct(s["expense_pct_net"]),
                                        "% of gross": pct(s["expense_pct_gross"])} for s in k["summary"]]),
                         hide_index=True, use_container_width=True)
        with ui.card(f"Shared expenses (split {len(k['income'])} ways)"):
            if not k["shared"]:
                ui.empty("No shared expenses yet.")
            else:
                expense_table(k["shared"], b["shared"], {"% net": "pct_net", "% gross": "pct_gross"}, all_cols, "bud_sh_",
                              total=k["shared_total"], per_person=k["shared_per_person"])
        for x in k["income"]:
            p = x["person"]
            nums = [n for n in k["personal"] if n["person"] == p]
            meta = [m for m in b["personal"] if m["person"] == p]
            with ui.card(f"{p}'s expenses"):
                if not nums:
                    ui.empty("None yet.")
                else:
                    expense_table(nums, meta, {"% of net": "pct_net"}, all_cols, f"bud_p{x['person_id']}_",
                                  total=per_period(sum(n["monthly"] for n in nums)))
    # ---- Income ----
    with ui.card("Income (per paycheck, paid every 2 weeks)"):
        ppl = ui.people()
        inc = {r["person_id"]: r for r in db.get("select * from income")}
        kin = {x["person_id"]: x for x in (k["income"] if k else [])}
        df = pd.DataFrame([{"person_id": p["id"], "Person": p["name"],
                            "Net / check": float(inc.get(p["id"], {}).get("net_per_check") or 0),
                            "Gross / check": float(inc.get(p["id"], {}).get("gross_per_check") or 0),
                            "Net / month": money(kin[p["id"]]["net_monthly"]) if p["id"] in kin else "—",
                            "Gross / month": money(kin[p["id"]]["gross_monthly"]) if p["id"] in kin else "—",
                            "Net / year": money(kin[p["id"]]["net_yearly"]) if p["id"] in kin else "—"} for p in ppl])
        if not df.empty:
            out = st.data_editor(df, key=_key("bud_inc_", df), hide_index=True, use_container_width=True,
                                 column_config={"person_id": None,
                                                "Net / check": st.column_config.NumberColumn(format="$%.2f", min_value=0.0),
                                                "Gross / check": st.column_config.NumberColumn(format="$%.2f", min_value=0.0)},
                                 disabled=["Person", "Net / month", "Gross / month", "Net / year"])
            for i, r in out.iterrows():
                for field, col in (("net_per_check", "Net / check"), ("gross_per_check", "Gross / check")):
                    if abs(float(r[col] or 0) - float(df.loc[i, col])) > 0.004:
                        if ui.try_db(db.run, "Income updated",
                                     f"""insert into income (person_id, {field}) values ($1, $2)
                                         on conflict (person_id) do update set {field} = excluded.{field}""",
                                     int(r["person_id"]), round(float(r[col]), 2)):
                            st.rerun()
    if k:
        with ui.card("Guidelines"):
            c1, c2 = st.columns(2)
            c1.markdown("**Monthly amounts**\n\n" + "\n".join(f"- {r['rule']}: {money(r['amount'])}" for r in k["rules"]))
            c2.markdown("**Taxes & deductions (share of gross)**\n\n"
                        + "\n".join(f"- {t['person']}: {pct(t['pct'])}" for t in k["tax"]))
    with st.expander("➕ Add an expense"):
        f = forms.expense_form("xb")
        if st.button("Add to budget", type="primary", key="xb_add"):
            msg = forms.check_expense(f)
            if msg:
                st.warning(msg)
            elif ui.try_db(forms.save_expense, "Added (also on the Bills page)" if f["track"] else "Added", f):
                for kk in [k_ for k_ in st.session_state if str(k_).startswith("xb_")]:
                    del st.session_state[kk]
                st.rerun()
