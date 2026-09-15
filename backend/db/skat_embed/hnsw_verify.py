"""Efter HNSW: ANALYZE, indeksvaliditet, størrelse og query-plan. Ingen dokumenttekst."""

from __future__ import annotations

from backend.db.skat_import.connect import connect, dsn
from backend.db.skat_import.io import redact_dsn


def main() -> int:
    url = dsn()
    print(f"forbindelse {redact_dsn(url)}", flush=True)
    conn = connect(url, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("ANALYZE skat.chunk_embeddings")
            cur.execute("ANALYZE skat.chunks")
            cur.execute("ANALYZE skat.query_embeddings")
            cur.execute("ANALYZE skat.legal_documents")
            print("ANALYZE færdig", flush=True)

            cur.execute(
                """
                SELECT c.relname, i.indisvalid, i.indisready, am.amname,
                       pg_size_pretty(pg_relation_size(c.oid)),
                       pg_relation_size(c.oid)
                FROM pg_class AS c
                JOIN pg_index AS i ON i.indexrelid = c.oid
                JOIN pg_am AS am ON am.oid = c.relam
                JOIN pg_namespace AS n ON n.oid = c.relnamespace
                WHERE n.nspname = 'skat'
                  AND c.relname = 'chunk_embeddings_hnsw_ip_idx'
                """
            )
            idx = cur.fetchone()
            print("index_row", idx, flush=True)

            cur.execute(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = 'skat'
                  AND indexname = 'chunk_embeddings_hnsw_ip_idx'
                """
            )
            print("indexdef", cur.fetchone(), flush=True)

            cur.execute(
                """
                SELECT a.atttypid::regtype
                FROM pg_attribute AS a
                JOIN pg_class AS c ON c.oid = a.attrelid
                JOIN pg_namespace AS n ON n.oid = c.relnamespace
                WHERE n.nspname = 'skat'
                  AND c.relname = 'chunk_embeddings'
                  AND a.attname = 'embedding'
                """
            )
            print("embedding_type", cur.fetchone(), flush=True)

            cur.execute("SELECT pg_size_pretty(pg_database_size(current_database())), pg_database_size(current_database())")
            print("database_size", cur.fetchone(), flush=True)

            cur.execute("SELECT pg_size_pretty(pg_total_relation_size('skat.chunk_embeddings')), pg_total_relation_size('skat.chunk_embeddings')")
            print("chunk_embeddings_total", cur.fetchone(), flush=True)

            cur.execute(
                """
                EXPLAIN (FORMAT TEXT)
                SELECT chunk_id
                FROM skat.chunk_embeddings
                ORDER BY embedding <#> (
                    SELECT embedding FROM skat.query_embeddings LIMIT 1
                )
                LIMIT 10
                """
            )
            plan = "\n".join(row[0] for row in cur.fetchall())
            print("query_plan:", flush=True)
            print(plan, flush=True)
            if "chunk_embeddings_hnsw_ip_idx" not in plan and "Hnsw" not in plan and "hnsw" not in plan.lower():
                print("FEJL: query-plan bruger ikke HNSW", flush=True)
                return 1
            if not idx or not idx[1] or idx[3] != "hnsw":
                print("FEJL: HNSW-indeks mangler eller er ugyldigt", flush=True)
                return 1
        print("HNSW-verifikation OK", flush=True)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
