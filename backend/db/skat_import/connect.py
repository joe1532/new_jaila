"""Databaseforbindelse via JAILA_SKAT_DATABASE_URL. Ingen credentials i koden."""

from __future__ import annotations

from backend.db.migrate import connect as migrate_connect
from backend.db.migrate import dsn as migrate_dsn


def dsn() -> str:
    return migrate_dsn()


def connect(url: str | None = None, *, autocommit: bool = False):
    conn = migrate_connect(url or dsn())
    conn.autocommit = autocommit
    with conn.cursor() as cur:
        cur.execute("SET search_path TO skat, public")
    if not autocommit:
        conn.commit()
    return conn
