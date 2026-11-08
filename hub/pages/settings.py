"""Settings: my account, family members, kids' names, meal preferences, school run, logins (admins)."""
from __future__ import annotations

import streamlit as st

from hub import auth, db, session, traffic, ui
from hub.config import has_text, nz
from hub.data import get_people
from hub.dates import hhmm, parse_hhmm


def account_card() -> None:
    u = ui.user()
    with ui.card("My account"):
        st.caption(f"Signed in as {u['email']}" + (" · admin" if u.get("is_admin") else ""))
        nm = st.text_input("Display name", value=u["display_name"], key="set_name")
        if st.button("Save name", key="set_name_save"):
            if has_text(nm) and ui.try_db(db.run, "Name saved", "update app_users set display_name = $2 where user_id = $1::uuid",
                                          u["user_id"], nm.strip()):
                u["display_name"] = nm.strip()
                st.rerun()
        p1 = st.text_input("New password", type="password", key="set_pw1")
        p2 = st.text_input("Repeat new password", type="password", key="set_pw2")
        if st.button("Change password", key="set_pw_save"):
            if len(p1 or "") < 8:
                st.toast("Use at least 8 characters.", icon="ℹ️")
            elif p1 != p2:
                st.toast("Passwords don't match.", icon="ℹ️")
            else:
                r = auth.change_own_password(session.fresh_access_token(), p1)
                if r["ok"]:
                    ui.flash("Password changed.")
                    for k in ("set_pw1", "set_pw2"):
                        st.session_state.pop(k, None)
                else:
                    st.error(f"Couldn't change password: {r['message']}")


def _move(pid, direction):
    p = get_people(active_only=False)
    ids = [x["id"] for x in p]
    i = ids.index(pid)
    j = i + direction
    if not 0 <= j < len(ids):
        return
    ids[i], ids[j] = ids[j], ids[i]

    def save():
        for k, x in enumerate(ids, 1):
            db.run("update people set sort_order = $2 where id = $1", x, k)
    ui.try_db(save)


def _rename(key, pid):
    nm = nz(st.session_state[key])
    if nm:
        ui.try_db(db.run, "Renamed", "update people set name = $2 where id = $1", pid, nm)


def people_card() -> None:
    with ui.card("Family members"):
        st.caption("These names appear in every 'who' dropdown. Logins are separate.")
        for p in get_people(active_only=False):
            a, b, c = st.columns([4, 1, 2], vertical_alignment="center")
            k = f"pname_{p['id']}_{p['name']}"
            a.text_input("Name", value=p["name"], key=k, label_visibility="collapsed", on_change=_rename, args=(k, p["id"]),
                         disabled=not p["is_active"])
            b.button(":material/arrow_upward:", key=f"pup_{p['id']}", help="Move up", on_click=_move, args=(p["id"], -1))
            if c.button("Hide" if p["is_active"] else "Show", key=f"ptog_{p['id']}", use_container_width=True):
                ui.try_db(db.run, None, "update people set is_active = not is_active where id = $1", p["id"])
                st.rerun()
        with st.form("add_person", clear_on_submit=True, border=False):
            x, y = st.columns([4, 1], vertical_alignment="bottom")
            nm = x.text_input("Add a name", placeholder="Add a name, e.g. Grandma", label_visibility="collapsed")
            if y.form_submit_button("Add", type="primary") and has_text(nm):
                ui.try_db(db.run, "Added", """insert into people (name, sort_order)
                                               values ($1, coalesce((select max(sort_order) from people), 0) + 1)""",
                          nm.strip())


def prefs_cards() -> None:
    with ui.card("Kids' names"):
        st.caption("Used in journal prompts and dinner questions. Separate names with commas.")
        k = st.text_input("Kids", value=db.get_setting("kids_names", ""), placeholder="e.g. Alan, Betty", key="set_kids",
                          label_visibility="collapsed")
        if st.button("Save", key="set_kids_save"):
            ui.try_db(db.set_setting, "Saved", "kids_names", (k or "").strip())
    with ui.card("Meal preferences for AI ideas"):
        m = st.text_area("Preferences", value=db.get_setting("meal_preferences", ""), height=100, key="set_meal",
                         placeholder="Family size, ages, dislikes, allergies, budget, cooking time…",
                         label_visibility="collapsed")
        if st.button("Save", key="set_meal_save"):
            ui.try_db(db.set_setting, "Saved", "meal_preferences", m or "")


def school_card() -> None:
    with ui.card("School run"):
        st.caption("Weekdays on Today: 6:30-9:30 AM home to school, 2:30-5:30 PM school to home.")
        s = traffic.school_settings()
        label = st.text_input("School name (shown on Today)", value=s["label"], placeholder="e.g. Alan's school", key="sch_label")
        school = st.text_area("School address", value=s["school"], height=70, key="sch_addr")
        home = None
        if ui.can("sensitive"):
            home = st.text_area("Home address (also used on the sitter sheet)", value=s["home"], height=70, key="sch_home")
        else:
            st.caption("The home address is set by someone who can see sensitive info.")
        arrive = st.time_input("Arrive at school by (optional, adds a leave-by time)", value=parse_hhmm(s["arrive_by"]),
                               step=300, key="sch_arrive")
        if st.button("Save", key="sch_save"):
            def save():
                db.set_setting("school_label", (label or "").strip())
                db.set_setting("school_address", (school or "").strip())
                db.set_setting("school_arrive_by", hhmm(arrive))
                if home is not None:
                    db.set_setting("home_address", home.strip())
            if ui.try_db(save, "Saved"):
                traffic.clear_cache()
                # Look the addresses up now, so a typo shows here rather than on Today.
                s = traffic.school_settings()
                with st.spinner("Checking addresses…"):
                    for addr, what in ((s["school"], "School"), (s["home"], "Home")):
                        if not addr:
                            st.warning(f"{what} address is empty")
                        elif not traffic.traffic_key():
                            st.warning("Add TOMTOM_API_KEY to the app's secrets to check addresses")
                            break
                        else:
                            try:
                                g = traffic.tt_geocode(addr)
                                st.success(f"{what} found: " + ("yes" if what == "Home" and not ui.can("sensitive") else g["label"]))
                            except Exception as e:  # noqa: BLE001
                                st.warning(f"{what}: {e}")


@st.dialog("Set a new password")
def reset_dialog(uid: str):
    pw = st.text_input("New password (8+ characters)", type="password", key="reset_pw")
    if st.button("Save", type="primary", key="reset_save"):
        if len(pw or "") < 8:
            st.warning("Use at least 8 characters.")
            return
        r = auth.admin_set_password(uid, pw)
        if r["ok"]:
            ui.flash("Password updated.")
            st.rerun()
        else:
            st.error(f"Couldn't update: {r['message']}")


def _perm(key, uid, field):
    if ui.user().get("is_admin") and field in ("can_see_money", "can_see_sensitive"):
        ui.try_db(db.run, "Updated (takes effect next time they open the app)",
                  f"update app_users set {field} = $2::boolean where user_id = $1::uuid", uid, bool(st.session_state[key]))


def _link(key, uid):
    """Linking a login to a family member also sets its display name (used in the greeting)."""
    pid = st.session_state[key]
    nm = ui.name_of(pid) if pid is not None else None
    ui.try_db(db.run, f"Linked to {nm}" if nm else "Unlinked",
              "update app_users set person_id = $2, display_name = coalesce($3, display_name) where user_id = $1::uuid",
              uid, pid, nm)
    if uid == ui.user()["user_id"] and nm:
        ui.user()["display_name"] = nm


def logins_card() -> None:
    if not ui.user().get("is_admin"):
        return
    with ui.card("Logins"):
        users = db.get("""select user_id::text as user_id, email, display_name, person_id, is_admin, can_see_money,
                                 can_see_sensitive from app_users order by created_at""")
        opts, fmt = ui.person_options()
        for u in users:
            me = u["user_id"] == ui.user()["user_id"]
            with st.container(border=True):
                st.markdown(f"**{u.get('display_name') or u['email']}** "
                            + (ui.md_badge("admin", "info") if u.get("is_admin") else ""))
                st.caption(u["email"])
                lk = f"link_{u['user_id']}_{u.get('person_id')}"
                st.selectbox("Family member", opts, index=opts.index(u.get("person_id")) if u.get("person_id") in opts else 0,
                             format_func=fmt, key=lk, on_change=_link, args=(lk, u["user_id"]))
                if u.get("is_admin"):
                    st.caption("Sees everything")
                else:
                    a, b = st.columns(2)
                    for col, field, label in ((a, "can_see_money", "Money"), (b, "can_see_sensitive", "Sensitive info")):
                        k = f"perm_{u['user_id']}_{field}_{int(bool(u.get(field)))}"
                        col.toggle(label, value=bool(u.get(field)), key=k, on_change=_perm, args=(k, u["user_id"], field))
                if not me:
                    x, y, z = st.columns(3)
                    if x.button("Reset password", key=f"ureset_{u['user_id']}", use_container_width=True):
                        reset_dialog(u["user_id"])
                    if y.button("Remove admin" if u.get("is_admin") else "Make admin", key=f"uadm_{u['user_id']}",
                                use_container_width=True):
                        ui.try_db(db.run, "Updated", "update app_users set is_admin = not is_admin where user_id = $1::uuid",
                                  u["user_id"])
                        st.rerun()
                    with z.popover("Remove", use_container_width=True):
                        st.write("Remove this login? They will no longer be able to sign in.")
                        if st.button("Yes, remove", type="primary", key=f"udel_{u['user_id']}"):
                            r = auth.admin_delete_user(u["user_id"])
                            if not r["ok"] and r["status"] != 404:
                                st.error(f"Couldn't remove login: {r['message']}")
                            elif ui.try_db(db.run, "Login removed", "delete from app_users where user_id = $1::uuid",
                                           u["user_id"]):
                                st.rerun()
        with st.expander("Add a login"):
            email = st.text_input("Email", key="u_email")
            name = st.text_input("Display name", key="u_name")
            pw = st.text_input("Temporary password (8+ characters)", type="password", key="u_pw")
            adm = st.checkbox("Can manage logins", value=False, key="u_admin")
            if st.button("Create login", type="primary", key="u_add"):
                email = (email or "").strip().lower()
                if "@" not in email:
                    st.warning("Enter a valid email.")
                elif len(pw or "") < 8:
                    st.warning("Password needs 8+ characters.")
                else:
                    with st.spinner("Creating login…"):
                        r = auth.create_user(email, pw)
                    if not r["ok"]:
                        st.error(f"Couldn't create login: {r['message']}")
                    elif ui.try_db(db.run, f"Login created for {email}",
                                   """insert into app_users (user_id, email, display_name, is_admin)
                                      values ($1::uuid, $2, $3, $4::boolean) on conflict (user_id) do nothing""",
                                   r["body"]["id"], email, nz(name) or email.split("@")[0], adm):
                        for k in ("u_email", "u_name", "u_pw", "u_admin"):
                            st.session_state.pop(k, None)
                        st.rerun()
            st.caption("Share the password with them; they can change it under My account.")


def page() -> None:
    c1, c2 = st.columns(2)
    with c1:
        account_card()
        prefs_cards()
    with c2:
        people_card()
        school_card()
    logins_card()
