"""Photos: a family photo timeline by week (as many as you like; one is the photo of the week),
browsed by year and month, with a monthly collage."""
from __future__ import annotations

import time
from datetime import date

import streamlit as st

from hub import db, photos, ui
from hub.config import has_text, nz, today
from hub.dates import add_months, month_start, week_start

esc = ui.esc


def link_for(paths: list[str]) -> dict:
    """Viewing links, signed for an hour and reused for 50 minutes."""
    cache = st.session_state.setdefault("photo_links", {})
    t = time.time()
    need = [p for p in paths if p not in cache or cache[p][1] < t]
    if need:
        for p, u in photos.st_sign(need).items():
            cache[p] = (u, t + (photos.PHOTO_LINK_MIN - 10) * 60)
    return {p: cache[p][0] for p in paths if p in cache}


@st.dialog("Photo", width="large")
def photo_dialog(pid: int):
    r = photos.photo_get(pid)
    if not r:
        st.stop()
    url = link_for([r["path"]]).get(r["path"])
    if url:
        st.image(url, use_container_width=True)
    st.subheader(photos.photo_date_label(r["taken_on"] or r["week_start"]))
    if r["is_featured"]:
        st.caption(f"⭐ Photo of the week for {photos.week_label(r['week_start'])}")
    cap = st.text_input("Caption (optional)", value=r.get("caption") or "", key=f"pd_cap_{pid}")
    d = st.date_input("Date taken", value=r["taken_on"] or r["week_start"], max_value=today(), key=f"pd_date_{pid}",
                      format="MM/DD/YYYY")
    st.caption(f"Added by {r.get('added_by_name') or 'someone'} on {photos.photo_date_label(r['created_at'].date())}")
    c1, c2, c3 = st.columns(3)
    if c1.button("Save", type="primary", key=f"pd_save_{pid}", use_container_width=True):
        if d is None:
            st.warning("Pick the date it was taken.")
        elif ui.try_db(photos.photo_update, "Saved", pid, nz(cap), d):
            st.session_state["photo_month"] = month_start(d)
            st.rerun()
    if not r["is_featured"] and c2.button("Make photo of the week", icon=":material/star:", key=f"pd_feat_{pid}",
                                          use_container_width=True):
        if ui.try_db(photos.photo_make_featured, "Photo of the week set", pid):
            st.rerun()
    with c3:
        ui.confirm_delete("Delete", f"pd_del_{pid}", "Delete this photo? This can't be undone.", photos.photo_delete, pid,
                          success="Photo deleted", full_width=True)


def upload_card() -> None:
    with ui.card("Add photos"):
        n = len(db.get("select id from photos where week_start = $1::date", week_start(today())))
        wl = photos.week_label(week_start(today()))
        st.caption(f"🟠 No photo yet this week ({wl})." if n == 0 else f"✅ {n} photo{'s' if n != 1 else ''} this week ({wl}).")
        k = st.session_state.get("photo_up_key", 0)
        files = st.file_uploader("Choose photos", type=["jpg", "jpeg", "png", "heic", "heif", "webp"],
                                 accept_multiple_files=True, key=f"photo_up_{k}", label_visibility="collapsed")
        cap = st.text_input("Caption (optional)", key=f"photo_cap_{k}", max_chars=photos.PHOTO_CAPTION_MAX,
                            placeholder="e.g. First trip to the beach",
                            help="Saved on every photo you add this time. Change any of them later with Open.")
        if files and st.button(f"Add {len(files)} photo{'s' if len(files) != 1 else ''}", type="primary", key="photo_add"):
            added, failed = [], []
            bar = st.progress(0.0, text="Adding photos…")
            for i, f in enumerate(files, 1):
                print(f"[photos] adding {i} of {len(files)}: {f.name}")
                try:
                    added.append(photos.photo_add(f.getvalue(), ui.user(), caption=cap))
                except Exception as e:  # noqa: BLE001
                    print(f"[photos] {f.name}: {e}")
                    failed.append(f.name)
                bar.progress(i / len(files), text=f"Adding photos… {i} of {len(files)}")
            if added:
                weeks = "; ".join(dict.fromkeys(photos.week_label(a["week"]) for a in added))
                ui.flash(f"Added {len(added)} photo{'s' if len(added) != 1 else ''} to {weeks}.")
                st.session_state["photo_month"] = month_start(added[-1]["taken"])
            if failed:
                st.error(f"Couldn't add: {', '.join(failed)}. If it's an iPhone photo, try again or set "
                         "Camera > Formats > Most Compatible.")
            st.session_state["photo_up_key"] = k + 1        # clears the picker
            if not failed:
                st.rerun()
        st.caption("Each photo goes in the week it was taken (from the camera's date, or today if there isn't one). "
                   "The first one in a week becomes the photo of the week; tap Open on any photo to change that, "
                   "edit its caption or fix the date.")


def ready_banner(months: list[dict]) -> None:
    """From the 1st, last month's collage is offered at the top until someone makes it."""
    lm = add_months(month_start(today()), -1)
    n = next((m["n"] for m in months if m["month"] == lm), 0)
    if n and not db.get_setting(photos.collage_key(lm), ""):
        c1, c2 = st.columns([3, 1], vertical_alignment="center")
        c1.info(f"🖼️ {lm:%B %Y} is ready: {n} photo{'s' if n != 1 else ''} for its collage.")
        if c2.button("Make collage", type="primary", key="ready_make", use_container_width=True):
            make(lm)


def make(m: date) -> None:
    with st.spinner(f"Making the {m:%B %Y} collage…"):
        if ui.try_db(photos.save_collage, "Collage ready", m):
            st.session_state.get("photo_links", {}).pop(photos.collage_path(m), None)   # fresh link for the new file
            st.session_state["photo_month"] = m
            st.rerun()


def page() -> None:
    months = photos.photo_months()
    ready_banner(months)
    upload_card()
    target = st.session_state.get("photo_month", month_start(today()))
    years = sorted({str(today().year), str(target.year)} | {str(m["month"].year) for m in months}, reverse=True)
    with ui.card("Timeline"):
        c1, c2 = st.columns(2)
        yr = c1.selectbox("Year", years, index=years.index(str(target.year)), key=f"ph_year_{target}")
        all_m = [date(int(yr), k, 1) for k in range(1, 13)]
        if int(yr) == today().year:
            all_m = [m for m in all_m if m <= month_start(today())]
        cnt = {m["month"]: m["n"] for m in months}
        all_m = list(reversed(all_m))
        sel = target if target in all_m else next((m for m in all_m if cnt.get(m)), all_m[0])
        shown = c2.selectbox("Month", all_m, index=all_m.index(sel), key=f"ph_month_{yr}_{sel}",
                             format_func=lambda m: f"{m:%B}" + (f" ({cnt[m]})" if cnt.get(m) else ""))
        if shown != target:
            st.session_state["photo_month"] = shown
        ph = photos.photos_in_month(shown)
        if not ph:
            ui.empty(f"No photos in {shown:%B %Y} yet.")
        else:
            # The photo of the week uses the larger copy; the rest use the small one.
            src = {p["id"]: p["path"] if p["is_featured"] else p["thumb_path"] for p in ph}
            urls = link_for(list(src.values()))
            weeks = list(dict.fromkeys(p["week_start"] for p in ph))[::-1]     # newest week first
            for w in weeks:
                st.markdown(f"#### {photos.week_label(w)}")
                wk = [p for p in ph if p["week_start"] == w]
                feat = [p for p in wk if p["is_featured"]]
                rest = [p for p in wk if not p["is_featured"]]
                for p in feat:
                    if urls.get(src[p["id"]]):
                        st.image(urls[src[p["id"]]], use_container_width=True)
                    st.html(f'<span class="sh-photo-star">⭐ Photo of the week</span> '
                            f'<span class="sh-muted">{esc(photos.photo_date_label(p["taken_on"] or w))}</span>'
                            + (f'<div>{esc(p["caption"])}</div>' if has_text(p.get("caption")) else ""))
                    if st.button("Open", key=f"ph_open_{p['id']}"):
                        photo_dialog(p["id"])
                for i in range(0, len(rest), 3):
                    cols = st.columns(3)
                    for c, p in zip(cols, rest[i:i + 3]):
                        with c:
                            if urls.get(src[p["id"]]):
                                st.image(urls[src[p["id"]]], use_container_width=True)
                            st.caption(photos.photo_date_label(p["taken_on"] or w)
                                       + (f" · {p['caption']}" if has_text(p.get("caption")) else ""))
                            if st.button("Open", key=f"ph_open_{p['id']}"):
                                photo_dialog(p["id"])
    with ui.card("Monthly collage"):
        n = next((m["n"] for m in months if m["month"] == shown), 0)
        label = f"{shown:%B %Y}"
        if not n:
            ui.empty(f"Add photos to {label} to make its collage.")
            return
        made = db.get_setting(photos.collage_key(shown), "")
        if made:
            url = link_for([photos.collage_path(shown)]).get(photos.collage_path(shown))
            if url:
                st.image(url, width=420)
            st.caption(f"Made {made}. Remake it after adding or changing photos.")
        else:
            st.caption(f"{n} photo{'s' if n != 1 else ''} in {label}.")
        c1, c2 = st.columns(2)
        if c1.button("Remake collage" if made else "Make collage", type="primary", key="col_make", use_container_width=True):
            make(shown)
        if made:
            url = link_for([photos.collage_path(shown)]).get(photos.collage_path(shown))
            if url:
                c2.link_button("Open full size to save", url, use_container_width=True)
        st.caption("One band per week: the photo of the week large, up to six others beside it. "
                   "8 × 10 in at 300 dpi, ready to print.")
