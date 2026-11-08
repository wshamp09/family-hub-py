"""Database access (Supabase Postgres through the session pooler).

Queries are written with $1, $2 … placeholders (as in the R version); they are turned into
psycopg's named placeholders here, so the same placeholder can appear twice.
Rows come back as plain dicts; numeric columns come back as float, dates as date.
"""
from __future__ import annotations

import re
import threading

from .config import APP_TZ, cfg

_PARAM = re.compile(r"\$(\d+)")
_lock = threading.Lock()
_pool = None
# Tests can swap in another backend with the same get/run interface.
backend = None


def _sql(q: str) -> str:
    return _PARAM.sub(lambda m: f"%(p{m.group(1)})s", q.replace("%", "%%"))


def _params(args) -> dict:
    return {f"p{i + 1}": a for i, a in enumerate(args)}


def conninfo() -> str:
    from psycopg.conninfo import make_conninfo
    return make_conninfo(
        host=cfg("PG_HOST"), port=cfg("PG_PORT", "5432"), dbname=cfg("PG_DB", "postgres"),
        user=cfg("PG_USER"), password=cfg("PG_PASSWORD"), sslmode=cfg("PG_SSLMODE", "require"),
        options=f"-c timezone={APP_TZ}", connect_timeout="15")


def _configure(conn):
    from psycopg.types.numeric import FloatLoader
    conn.adapters.register_loader("numeric", FloatLoader)
    # Supabase's pooler ignores the time zone sent when connecting, so set it on each new connection.
    conn.execute("select set_config('TimeZone', %s, false)", [APP_TZ])
    if not conn.autocommit:
        conn.commit()


def pool():
    global _pool
    with _lock:
        if _pool is None:
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool
            print(f"[db] opening connection pool to {cfg('PG_HOST')}")
            _pool = ConnectionPool(
                conninfo(), min_size=1, max_size=4, open=True, configure=_configure,
                # prepare_threshold=None: works with both Supabase poolers (no server-side prepares)
                kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": None},
                check=ConnectionPool.check_connection)
    return _pool


def get(sql: str, *args) -> list[dict]:
    """Rows of a query as a list of dicts."""
    if backend is not None:
        return backend.get(sql, *args)
    with pool().connection() as conn:
        cur = conn.execute(_sql(sql), _params(args))
        return cur.fetchall() if cur.description else []


def one(sql: str, *args) -> dict | None:
    r = get(sql, *args)
    return r[0] if r else None


def value(sql: str, *args, default=None):
    r = one(sql, *args)
    return default if not r else next(iter(r.values()))


def run(sql: str, *args) -> int:
    """Run a write; returns the number of rows changed."""
    if backend is not None:
        return backend.run(sql, *args)
    with pool().connection() as conn:
        cur = conn.execute(_sql(sql), _params(args))
        return cur.rowcount


def close():
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


# ---- Household settings (key/value) ----------------------------------------------------------
def get_setting(key: str, default: str = "") -> str:
    r = one("select value from household_settings where key = $1", key)
    v = r["value"] if r else None
    return default if v is None else v


def set_setting(key: str, val) -> None:
    run("""insert into household_settings (key, value) values ($1, $2)
           on conflict (key) do update set value = excluded.value""", key, None if val is None else str(val))
