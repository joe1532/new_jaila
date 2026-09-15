"""Approximate Recall@10: HNSW vs exact inner-product. Indekskvalitet, ikke faglig retrieval."""

from __future__ import annotations

import time


def _eval_query_vectors(conn) -> list[tuple[str, str]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT coalesce(eval_id, query_key), embedding::text
            FROM skat.query_embeddings
            WHERE purpose = 'eval'
            ORDER BY eval_id, query_key
            """
        )
        return [(str(row[0]), str(row[1])) for row in cur.fetchall()]


def _top_chunk_ids(
    conn,
    vector_literal: str,
    *,
    k: int,
    use_index: bool,
    ef_search: int | None,
    iterative_scan: str | None = None,
) -> tuple[list[str], float]:
    started = time.perf_counter()
    with conn.cursor() as cur:
        if use_index:
            if ef_search is not None:
                cur.execute(f"SET hnsw.ef_search = {int(ef_search)}")
            if iterative_scan:
                cur.execute(f"SET hnsw.iterative_scan = {iterative_scan}")
            cur.execute("SET enable_seqscan = off")
            cur.execute("SET enable_indexscan = on")
            cur.execute("SET enable_bitmapscan = on")
        else:
            cur.execute("SET enable_indexscan = off")
            cur.execute("SET enable_bitmapscan = off")
            cur.execute("SET enable_seqscan = on")
        cur.execute(
            """
            SELECT chunk_id
            FROM skat.chunk_embeddings
            ORDER BY embedding <#> %s::vector
            LIMIT %s
            """,
            (vector_literal, k),
        )
        ids = [str(row[0]) for row in cur.fetchall()]
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return ids, elapsed_ms


def run_hnsw_recall(
    conn,
    *,
    k: int = 10,
    ef_values: list[int] | None = None,
    skip_iterative: bool = False,
) -> dict:
    queries = _eval_query_vectors(conn)
    if not queries:
        raise RuntimeError("ingen eval query-embeddings")
    ef_values = ef_values or [20, 40, 64, 80, 100, 200, 400, 800, 1600, 4000]
    exact_hits: list[set[str]] = []
    exact_latencies: list[float] = []
    for _eval_id, vector in queries:
        ids, latency = _top_chunk_ids(conn, vector, k=k, use_index=False, ef_search=None)
        exact_hits.append(set(ids))
        exact_latencies.append(latency)
    print(
        f"exact færdig n={len(queries)} mean_ms={sum(exact_latencies)/len(exact_latencies):.1f}",
        flush=True,
    )

    sweeps = []
    chosen_ef = None
    for ef in ef_values:
        recalls: list[float] = []
        latencies: list[float] = []
        for (_eval_id, vector), gold in zip(queries, exact_hits):
            ids, latency = _top_chunk_ids(conn, vector, k=k, use_index=True, ef_search=ef)
            denom = min(k, len(gold)) or 1
            recalls.append(len(set(ids) & gold) / denom)
            latencies.append(latency)
        mean_recall = sum(recalls) / len(recalls)
        mean_latency = sum(latencies) / len(latencies)
        row = {
            "ef_search": ef,
            "recall_at_10": round(mean_recall, 6),
            "mean_latency_ms": round(mean_latency, 3),
            "p50_latency_ms": round(sorted(latencies)[len(latencies) // 2], 3),
        }
        sweeps.append(row)
        if chosen_ef is None and mean_recall >= 0.98:
            chosen_ef = ef
        print(
            f"ef_search={ef} recall@10={mean_recall:.4f} mean_ms={mean_latency:.1f}",
            flush=True,
        )

    iterative = []
    chosen_iter = None
    if not skip_iterative:
        for ef in [40, 80, 100, 200, 400]:
            recalls: list[float] = []
            latencies: list[float] = []
            for (_eval_id, vector), gold in zip(queries, exact_hits):
                ids, latency = _top_chunk_ids(
                    conn,
                    vector,
                    k=k,
                    use_index=True,
                    ef_search=ef,
                    iterative_scan="strict_order",
                )
                denom = min(k, len(gold)) or 1
                recalls.append(len(set(ids) & gold) / denom)
                latencies.append(latency)
            mean_recall = sum(recalls) / len(recalls)
            mean_latency = sum(latencies) / len(latencies)
            iterative.append(
                {
                    "ef_search": ef,
                    "iterative_scan": "strict_order",
                    "recall_at_10": round(mean_recall, 6),
                    "mean_latency_ms": round(mean_latency, 3),
                }
            )
            print(
                f"iterative_scan=strict_order ef_search={ef} recall@10={mean_recall:.4f} mean_ms={mean_latency:.1f}",
                flush=True,
            )
            if chosen_iter is None and mean_recall >= 0.98:
                chosen_iter = ef

    with conn.cursor() as cur:
        cur.execute("RESET enable_indexscan")
        cur.execute("RESET enable_bitmapscan")
        cur.execute("RESET enable_seqscan")
        try:
            cur.execute("RESET hnsw.ef_search")
        except Exception:
            pass
        try:
            cur.execute("RESET hnsw.iterative_scan")
        except Exception:
            pass

    return {
        "note": (
            "Approximate Recall@10 mod exact vector search. "
            "Måler HNSW-indekskvalitet, ikke faglig retrievalkvalitet. "
            "Alle evalueringsqueries har gold_status=draft."
        ),
        "n_queries": len(queries),
        "k": k,
        "exact_mean_latency_ms": round(sum(exact_latencies) / len(exact_latencies), 3),
        "exact_p50_latency_ms": round(sorted(exact_latencies)[len(exact_latencies) // 2], 3),
        "ef_sweep": sweeps,
        "chosen_ef_search": chosen_ef,
        "iterative_scan_strict": iterative,
        "chosen_ef_search_with_iterative_scan": chosen_iter,
        "chosen_rule": "laveste ef_search med mindst 98 % Recall@10 mod exact",
        "ef_search_max": 1000,
    }
