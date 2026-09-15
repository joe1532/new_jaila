"""Anvend nummererede SQL-migrations på en tom eller eksisterende Postgres.

Bruger JAILA_SKAT_DATABASE_URL. Ingen hemmeligheder i filen.
003 (HNSW) køres kun med --with-hnsw, efter embeddings er indlæst.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
DEFAULT_FILES = (
    "001_extensions.sql",
    "002_skat_schema.sql",
    "004_import_audit.sql",
    "005_question_number_text.sql",
    "006_provenance_and_reference_occurrences.sql",
    "007_lexical_retrieval_indexes.sql",
    "008_embedding_audit.sql",
    "010_structured_law_references.sql",
)
HNSW_FILE = "003_chunk_embeddings_hnsw.sql"
HNSW_V2_FILE = "009_chunk_embeddings_hnsw_v2.sql"


def load_env() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
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


def dsn() -> str:
    load_env()
    value = os.getenv("JAILA_SKAT_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
    if not value.strip():
        raise SystemExit(
            "Sæt JAILA_SKAT_DATABASE_URL, fx "
            "postgresql://jaila:jaila@127.0.0.1:5433/jaila_skat"
        )
    return value.strip()


def connect(url: str):
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit(
            "psycopg mangler. Installer med: pip install -r backend/db/requirements.txt"
        ) from exc
    return psycopg.connect(url, autocommit=False)


def applied(cur) -> set[str]:
    cur.execute(
        """
        SELECT filename
        FROM skat.schema_migrations
        """
    )
    return {row[0] for row in cur.fetchall()}


def apply_file(conn, filename: str, *, autocommit: bool) -> None:
    path = MIGRATIONS_DIR / filename
    sql = path.read_text(encoding="utf-8")
    if autocommit:
        conn.autocommit = True
    cur = conn.cursor()
    if filename != "001_extensions.sql":
        try:
            already = applied(cur)
        except Exception:
            already = set()
        if filename in already:
            print(f"springer over {filename} (allerede kørt)")
            if not autocommit:
                conn.rollback()
            return
    cur.execute(sql)
    if filename == "001_extensions.sql":
        conn.commit()
        conn.autocommit = False
        cur = conn.cursor()
    cur.execute(
        "INSERT INTO skat.schema_migrations (filename) VALUES (%s) ON CONFLICT DO NOTHING",
        (filename,),
    )
    if not autocommit:
        conn.commit()
    print(f"anvendt {filename}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Kør JAILA SKAT Postgres-migrations")
    parser.add_argument(
        "--with-hnsw",
        action="store_true",
        help="Kør også 003 (HNSW). Kun efter bulk-import af embeddings.",
    )
    parser.add_argument(
        "--with-hnsw-v2",
        action="store_true",
        help="Kør 009 (HNSW v2, m=32, ef_construction=256). Ingen nye embeddings.",
    )
    args = parser.parse_args()
    url = dsn()
    conn = connect(url)
    try:
        apply_file(conn, "001_extensions.sql", autocommit=False)
        apply_file(conn, "002_skat_schema.sql", autocommit=False)
        apply_file(conn, "004_import_audit.sql", autocommit=False)
        apply_file(conn, "005_question_number_text.sql", autocommit=False)
        apply_file(conn, "006_provenance_and_reference_occurrences.sql", autocommit=False)
        apply_file(conn, "007_lexical_retrieval_indexes.sql", autocommit=False)
        apply_file(conn, "008_embedding_audit.sql", autocommit=False)
        apply_file(conn, "010_structured_law_references.sql", autocommit=False)
        if args.with_hnsw:
            apply_file(conn, HNSW_FILE, autocommit=True)
        if args.with_hnsw_v2:
            apply_file(conn, HNSW_V2_FILE, autocommit=True)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
