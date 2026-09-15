"""Vis HNSW-indekser og embedding-antal. Ingen dokumenttekst."""

from backend.db.skat_import.connect import connect, dsn
from backend.db.skat_import.io import redact_dsn


def main() -> None:
    conn = connect(dsn(), autocommit=True)
    print("forbindelse", redact_dsn(dsn()), flush=True)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM skat.chunk_embeddings")
            print("chunk_embeddings", cur.fetchone()[0], flush=True)
            cur.execute("SELECT count(*) FROM skat.chunks")
            print("chunks", cur.fetchone()[0], flush=True)
            cur.execute(
                """
                SELECT c.relname, c.reloptions, i.indisvalid,
                       pg_size_pretty(pg_relation_size(c.oid))
                FROM pg_class AS c
                JOIN pg_index AS i ON i.indexrelid = c.oid
                JOIN pg_am AS am ON am.oid = c.relam
                JOIN pg_namespace AS n ON n.oid = c.relnamespace
                WHERE n.nspname = 'skat' AND am.amname = 'hnsw'
                ORDER BY c.relname
                """
            )
            for row in cur.fetchall():
                print("index", row, flush=True)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
