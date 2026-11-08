"""Contacts & info hub, plus the sitter info sheet (PDF or image)."""
from __future__ import annotations

import re
from urllib.parse import quote

import streamlit as st

from hub import db, sitter, ui
from hub.config import APP_TITLE, CONTACT_CATS, INFO_CATS, has_text, nz, today
from hub.dates import fmt_long_day


def contact_form(p: str, row: dict | None = None) -> dict:
    row = row or {}
    name = st.text_input("Name", value=row.get("name") or "", placeholder="e.g. Dr. Smith (pediatrician)", key=f"{p}_name")
    cat = st.selectbox("Category", CONTACT_CATS, key=f"{p}_cat",
                       index=CONTACT_CATS.index(row["category"]) if row.get("category") in CONTACT_CATS else len(CONTACT_CATS) - 1)
    phone = st.text_input("Phone", value=row.get("phone") or "", key=f"{p}_phone")
    email = st.text_input("Email", value=row.get("email") or "", key=f"{p}_email")
    addr = st.text_input("Address", value=row.get("address") or "", key=f"{p}_addr")
    notes = st.text_area("Notes", value=row.get("notes") or "", height=70, key=f"{p}_notes")
    return {"name": nz(name), "cat": cat, "phone": nz(phone), "email": nz(email), "addr": nz(addr), "notes": nz(notes)}


def info_form(p: str, row: dict | None = None) -> dict:
    row = row or {}
    label = st.text_input("Label", value=row.get("label") or "", placeholder="e.g. Wi-Fi password, Car insurance policy",
                          key=f"{p}_label")
    value = st.text_input("Value", value=row.get("value") or "", key=f"{p}_value")
    cat = st.selectbox("Category", INFO_CATS, key=f"{p}_cat",
                       index=INFO_CATS.index(row["category"]) if row.get("category") in INFO_CATS else len(INFO_CATS) - 1)
    notes = st.text_area("Notes", value=row.get("notes") or "", height=70, key=f"{p}_notes")
    return {"label": nz(label), "value": nz(value), "cat": cat, "notes": nz(notes)}


@st.dialog("Edit contact")
def contact_dialog(cid: int):
    f = contact_form("ce", db.one("select * from contacts where id = $1", cid))
    if st.button("Save", type="primary", key="ce_save"):
        if not f["name"]:
            st.warning("Add a name.")
        elif ui.try_db(db.run, "Saved", "update contacts set name=$2, category=$3, phone=$4, email=$5, address=$6, notes=$7 where id=$1",
                       cid, f["name"], f["cat"], f["phone"], f["email"], f["addr"], f["notes"]):
            st.rerun()


@st.dialog("Edit info")
def info_dialog(iid: int):
    if not ui.can("sensitive"):
        st.stop()
    f = info_form("ie", db.one("select * from household_info where id = $1", iid))
    if st.button("Save", type="primary", key="ie_save"):
        if not f["label"]:
            st.warning("Add a label.")
        elif ui.try_db(db.run, "Saved", "update household_info set label=$2, value=$3, category=$4, notes=$5 where id=$1",
                       iid, f["label"], f["value"], f["cat"], f["notes"]):
            st.rerun()


@st.dialog("Sitter info sheet", width="large")
def sheet_dialog():
    if not ui.can("sensitive"):
        st.stop()
    ct = db.get("""select id, name, category, phone, notes from contacts
                   order by case when category = 'Family' then 0 else 1 end, category, name""")
    inf = db.get("select id, label, value, category from household_info order by category, label")
    title = st.text_input("Title", value="Info for the sitter", key="sh_title")
    addr = st.text_area("Home address", value=db.get_setting("home_address", ""), height=70, key="sh_addr")
    if ct:
        st.markdown("**Contacts to include**")
        pick_c = [c for c in ct if st.checkbox(f"{c['name']} ({c['category']})" + (f" · {c['phone']}" if c.get("phone") else ""),
                                              value=c["category"] == "Family", key=f"sh_c_{c['id']}")]
    else:
        pick_c = []
        st.caption("No contacts yet. Add Mom, Dad and the pediatrician under Contacts first.")
    if inf:
        st.markdown("**Codes & household info**")
        code = re.compile(r"code|wi-?fi|password|alarm|gate|garage|door", re.I)
        pick_i = [i for i in inf if st.checkbox(i["label"], value=bool(code.search(i["label"])), key=f"sh_i_{i['id']}")]
    else:
        pick_i = []
        st.caption("No household info yet (door code, Wi-Fi, etc.).")
    notes = st.text_area("Notes for tonight", height=100, key="sh_notes",
                         placeholder="Bedtime 7:30. No snacks after dinner. Allergies… Where things are…")
    if nz(addr) != nz(db.get_setting("home_address", "")):
        db.set_setting("home_address", (addr or "").strip())
    d = {"title": nz(title) or "Info for the sitter", "subtitle": f"{APP_TITLE} · updated {fmt_long_day(today())}",
         "address": nz(addr), "contacts": pick_c, "info": pick_i, "notes": nz(notes)}
    stem = f"sitter-info-{today():%Y%m%d}"
    c1, c2 = st.columns(2)
    c1.download_button("PDF", data=sitter.sitter_pdf(d), file_name=f"{stem}.pdf", mime="application/pdf",
                       type="primary", use_container_width=True, icon=":material/picture_as_pdf:")
    c2.download_button("Image", data=sitter.sitter_png(d), file_name=f"{stem}.png", mime="image/png",
                       use_container_width=True, icon=":material/image:")


def page() -> None:
    c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
    term = c1.text_input("Search", placeholder="Search contacts and info", key="ct_search", label_visibility="collapsed")
    if ui.can("sensitive") and c2.button("Sitter sheet", icon=":material/description:", type="primary",
                                         key="ct_sheet", use_container_width=True):
        sheet_dialog()
    like = f"%{term.strip()}%" if has_text(term) else None
    tabs = st.tabs(["Contacts", "Household info"] if ui.can("sensitive") else ["Contacts"])
    with tabs[0]:
        ct = (db.get("""select * from contacts where name ilike $1 or category ilike $1 or notes ilike $1
                        order by category, name""", like) if like else db.get("select * from contacts order by category, name"))
        if not ct:
            ui.empty("No contacts yet.")
        for cat in list(dict.fromkeys(c["category"] for c in ct)):
            with ui.card(cat):
                for c in [c for c in ct if c["category"] == cat]:
                    a, b = st.columns([4, 2], vertical_alignment="center")
                    lines = [f"**{c['name']}**"]
                    if c.get("phone"):
                        lines.append(f"📞 [{c['phone']}](tel:{re.sub(r'[^0-9+]', '', c['phone'])})")
                    if c.get("email"):
                        lines.append(f"✉️ [{c['email']}](mailto:{c['email']})")
                    if c.get("address"):
                        lines.append(f"📍 [{c['address']}](https://maps.google.com/?q={quote(c['address'], safe='')})")
                    a.markdown("  \n".join(lines))
                    if c.get("notes"):
                        a.caption(c["notes"])
                    x1, x2 = b.columns(2)
                    if x1.button("Edit", key=f"ce_{c['id']}"):
                        contact_dialog(c["id"])
                    with x2:
                        ui.confirm_delete(":material/delete:", f"cd_{c['id']}", "Delete this contact?", db.run,
                                          "delete from contacts where id = $1", c["id"])
        with st.expander("➕ Add a contact"):
            f = contact_form("c")
            if st.button("Add contact", type="primary", key="c_add"):
                if not f["name"]:
                    st.toast("Add a name.", icon="ℹ️")
                elif ui.try_db(db.run, "Contact added",
                               "insert into contacts (name, category, phone, email, address, notes) values ($1,$2,$3,$4,$5,$6)",
                               f["name"], f["cat"], f["phone"], f["email"], f["addr"], f["notes"]):
                    for k in [k for k in st.session_state if str(k).startswith("c_") and k != "c_add"]:
                        del st.session_state[k]
                    st.rerun()
    if ui.can("sensitive"):
        with tabs[1]:
            d = (db.get("""select * from household_info where label ilike $1 or value ilike $1 or notes ilike $1
                           order by category, label""", like) if like
                 else db.get("select * from household_info order by category, label"))
            if not d:
                ui.empty("Nothing saved yet. Wi-Fi password, insurance numbers, garage code…")
            for cat in list(dict.fromkeys(x["category"] for x in d)):
                with ui.card(cat):
                    for x in [x for x in d if x["category"] == cat]:
                        a, b = st.columns([4, 2], vertical_alignment="center")
                        a.caption(x["label"])
                        a.code(x.get("value") or "", language=None)     # tap to copy
                        if x.get("notes"):
                            a.caption(x["notes"])
                        y1, y2 = b.columns(2)
                        if y1.button("Edit", key=f"ie_{x['id']}"):
                            info_dialog(x["id"])
                        with y2:
                            ui.confirm_delete(":material/delete:", f"id_{x['id']}", "Delete this item?", db.run,
                                              "delete from household_info where id = $1", x["id"])
            with st.expander("➕ Add info"):
                f = info_form("i")
                if st.button("Add", type="primary", key="i_add"):
                    if not f["label"]:
                        st.toast("Add a label.", icon="ℹ️")
                    elif ui.try_db(db.run, "Saved", "insert into household_info (label, value, category, notes) values ($1,$2,$3,$4)",
                                   f["label"], f["value"], f["cat"], f["notes"]):
                        for k in [k for k in st.session_state if str(k).startswith("i_") and k != "i_add"]:
                            del st.session_state[k]
                        st.rerun()
