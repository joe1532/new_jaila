"""Drop v1 HNSW så planneren bruger v2. Ingen embeddings ændres. CONCURRENTLY."""

from backend.db.skat_import.connect import connect, dsn
from backend.db.skat_import.io import redact_dsn


def main() -> int:
    conn = connect(dsn(), autocommit=True)
    print("forbindelse", redact_dsn(dsn()), flush=True)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM skat.chunk_embeddings")
            before = int(cur.fetchone()[0])
            print("embeddings_before", before, flush=True)
            cur.execute("DROP INDEX CONCURRENTLY IF EXISTS skat.chunk_embeddings_hnsw_ip_idx")
            print("dropped chunk_embeddings_hnsw_ip_idx", flush=True)
            cur.execute("ANALYZE skat.chunk_embeddings")
            print("ANALYZE færdig", flush=True)
            cur.execute("SELECT count(*) FROM skat.chunk_embeddings")
            after = int(cur.fetchone()[0])
            print("embeddings_after", after, flush=True)
            if after != before:
                raise SystemExit(f"embedding-antal ændret: {before} -> {after}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
