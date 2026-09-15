"""Read-only databaseforbindelse til retrieval-CLI. Kun JAILA_SKAT_DATABASE_URL."""

from __future__ import annotations

import os

from backend.db.skat_retrieval.errors import DatabaseUnavailableError


def load_env() -> None:
    from pathlib import Path

    env_path = Path(__file__).resolve().parents[3] / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def retrieval_dsn() -> str:
    """Læs kun JAILA_SKAT_DATABASE_URL. Ingen credentials i fejltekst."""
    load_env()
    value = (os.getenv("JAILA_SKAT_DATABASE_URL") or "").strip()
    if not value:
        raise DatabaseUnavailableError("JAILA_SKAT_DATABASE_URL mangler")
    return value


def connect_readonly(url: str | None = None):
    """Åbn en READ ONLY-transaktion. Kun SELECT og SET LOCAL."""
    try:
        import psycopg
    except ImportError as exc:
        raise DatabaseUnavailableError("psycopg mangler") from exc
    try:
        conn = psycopg.connect(
            url or retrieval_dsn(),
            autocommit=False,
            connect_timeout=5,
        )
    except Exception:
        # Ingen DSN/password i fejltekst eller __cause__.
        raise DatabaseUnavailableError("databaseforbindelse fejlede") from None
    try:
        with conn.cursor() as cur:
            # Første statement i transaktionen: read-only uden session-lækage.
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL search_path TO skat, public")
    except Exception:
        conn.close()
        raise DatabaseUnavailableError("kunne ikke starte read-only transaktion") from None
    return conn
