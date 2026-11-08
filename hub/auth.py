"""Supabase Auth (email + password logins) and the app_users profile."""
from __future__ import annotations

import requests

from . import db
from .config import cfg

TIMEOUT = 20


def endpoint(path: str) -> str:
    return cfg("SUPABASE_URL").rstrip("/") + path


def public_headers() -> dict:
    return {"apikey": cfg("SUPABASE_PUBLISHABLE_KEY")}


def admin_headers() -> dict:
    """New-style secret keys (sb_secret_...) go in the apikey header only; legacy
    service_role JWT keys are also sent as a Bearer token."""
    key = cfg("SUPABASE_SECRET_KEY")
    h = {"apikey": key}
    if not key.startswith("sb_secret_"):
        h["Authorization"] = f"Bearer {key}"
    return h


def call(method: str, url: str, headers: dict, json=None, params=None, data=None, extra_headers=None) -> dict:
    """{ok, status, body, message} - never raises."""
    h = dict(headers)
    if extra_headers:
        h.update(extra_headers)
    try:
        r = requests.request(method, url, headers=h, json=json, params=params, data=data, timeout=TIMEOUT)
    except requests.RequestException as e:
        return {"ok": False, "status": None, "body": {}, "message": f"Could not reach Supabase: {e}"}
    try:
        body = r.json()
    except ValueError:
        body = {}
    msg = ""
    if isinstance(body, dict):
        msg = body.get("error_description") or body.get("msg") or body.get("message") or body.get("error") or ""
    return {"ok": r.status_code < 300, "status": r.status_code, "body": body,
            "message": str(msg or f"HTTP {r.status_code}")}


def _session(r: dict) -> dict:
    if not r["ok"]:
        return {"ok": False, "status": r["status"],
                "message": "Wrong email or password." if r["status"] == 400 else r["message"]}
    b = r["body"]
    return {"ok": True, "user_id": b["user"]["id"], "email": b["user"]["email"],
            "access_token": b["access_token"], "refresh_token": b["refresh_token"]}


def password_login(email: str, password: str) -> dict:
    return _session(call("POST", endpoint("/auth/v1/token"), public_headers(),
                         params={"grant_type": "password"}, json={"email": email, "password": password}))


def refresh_login(refresh_token: str) -> dict:
    return _session(call("POST", endpoint("/auth/v1/token"), public_headers(),
                         params={"grant_type": "refresh_token"}, json={"refresh_token": refresh_token}))


def change_own_password(access_token: str, new_password: str) -> dict:
    return call("PUT", endpoint("/auth/v1/user"), public_headers(), json={"password": new_password},
                extra_headers={"Authorization": f"Bearer {access_token}"})


def create_user(email: str, password: str) -> dict:
    return call("POST", endpoint("/auth/v1/admin/users"), admin_headers(),
                json={"email": email, "password": password, "email_confirm": True})


def admin_set_password(user_id: str, new_password: str) -> dict:
    return call("PUT", endpoint(f"/auth/v1/admin/users/{user_id}"), admin_headers(), json={"password": new_password})


def admin_delete_user(user_id: str) -> dict:
    return call("DELETE", endpoint(f"/auth/v1/admin/users/{user_id}"), admin_headers())


def ensure_profile(user_id: str, email: str) -> dict:
    """Create or refresh the app profile row for a login and return it."""
    admins = [a.strip().lower() for a in cfg("ADMIN_EMAILS").split(",") if a.strip()]
    db.run("""insert into app_users (user_id, email, display_name, is_admin)
              values ($1::uuid, $2, $3, $4::boolean)
              on conflict (user_id) do update
                set email = excluded.email,
                    is_admin = app_users.is_admin or excluded.is_admin""",
           user_id, email, email.split("@")[0], email.lower() in admins)
    return db.one("""select user_id::text as user_id, email,
                            coalesce(display_name, email) as display_name, person_id, is_admin,
                            can_see_money, can_see_sensitive
                       from app_users where user_id = $1::uuid""", user_id)
