"""EXPLAIN: exact scan vs HNSW. Ingen dokumenttekst."""

from __future__ import annotations

VECTOR_SQL = """
SELECT chunk_id
FROM skat.chunk_embeddings
ORDER BY embedding <#> (
    SELECT embedding FROM skat.query_embeddings LIMIT 1
)
LIMIT 10
"""


def _plan(cur, *, title: str) -> str:
    cur.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) " + VECTOR_SQL)
    text = "\n".join(row[0] for row in cur.fetchall())
    print(f"--- {title} ---", flush=True)
    print(text, flush=True)
    return text.lower()


def explain_exact_and_hnsw(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.relname, i.indisvalid, pg_size_pretty(pg_relation_size(c.oid))
            FROM pg_class AS c
            JOIN pg_index AS i ON i.indexrelid = c.oid
            JOIN pg_am AS am ON am.oid = c.relam
            JOIN pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname = 'skat' AND am.amname = 'hnsw'
            ORDER BY c.relname
            """
        )
        indexes = cur.fetchall()
        print("hnsw_indexes", indexes, flush=True)

        cur.execute("SET enable_indexscan = off")
        cur.execute("SET enable_bitmapscan = off")
        cur.execute("SET enable_seqscan = on")
        exact = _plan(cur, title="exact (indexscan/bitmapscan off)")

        cur.execute("SET enable_indexscan = on")
        cur.execute("SET enable_bitmapscan = on")
        cur.execute("SET enable_seqscan = off")
        hnsw = _plan(cur, title="hnsw (seqscan off)")

        cur.execute("RESET enable_indexscan")
        cur.execute("RESET enable_bitmapscan")
        cur.execute("RESET enable_seqscan")

    exact_ok = ("seq scan" in exact or "gather" in exact) and "hnsw" not in exact
    hnsw_ok = "index scan" in hnsw and "hnsw" in hnsw
    if not exact_ok:
        raise RuntimeError("exact-planen bruger ikke sekventiel/parallel scan, eller den nævner HNSW")
    if not hnsw_ok:
        raise RuntimeError("HNSW-planen bruger ikke et HNSW-indeks")
    print("EXPLAIN OK: exact uden HNSW, HNSW via indeks", flush=True)
    return {"exact_uses_seq_or_parallel": True, "hnsw_uses_index": True, "indexes": indexes}


def main() -> int:
    from backend.db.skat_import.connect import connect, dsn
    from backend.db.skat_import.io import redact_dsn

    url = dsn()
    print(f"forbindelse {redact_dsn(url)}", flush=True)
    conn = connect(url, autocommit=True)
    try:
        explain_exact_and_hnsw(conn)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
