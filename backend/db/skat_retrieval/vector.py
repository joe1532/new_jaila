"""Vector- og hybrid-søgning. On-demand query-vektor udefra. Ingen OpenAI-kald her."""

from __future__ import annotations

import time
from dataclasses import replace

from backend.db.skat_retrieval.errors import SkatRetrievalError
from backend.db.skat_retrieval.query_embed import query_text_sha256, resolve_query_vector
from backend.db.skat_retrieval.search import SearchHit, hydrate_hits, lexical_search
from backend.db.skat_retrieval.search import _as_int, _as_text
from backend.db.skat_retrieval.settings import (
    EXACT_CANDIDATE_POOLS,
    HNSW_EF_SEARCH,
    LEXICAL_CANDIDATE_LIMIT,
    VECTOR_CANDIDATE_LIMIT,
)
from backend.db.skat_retrieval.tx import execute_with_local_settings


RRF_K = 60
STRUCTURED_LAW_REFERENCE_SIGNAL = "struktureret lovhenvisning"
STRUCTURED_REFERENCE_RRF_WEIGHT = 2.0
EXACT_RESTORE_SETTINGS = (
    "SET LOCAL enable_indexscan TO DEFAULT",
    "SET LOCAL enable_bitmapscan TO DEFAULT",
    "SET LOCAL enable_seqscan TO DEFAULT",
)

EXACT_CANDIDATE_SQL = """
SELECT e.chunk_id, (e.embedding <#> %s::vector) AS distance
FROM skat.chunk_embeddings AS e
WHERE e.embedding_model_id = %s::uuid
ORDER BY e.embedding <#> %s::vector, e.chunk_id
LIMIT %s
"""

HNSW_CANDIDATE_SQL = """
SELECT e.chunk_id, (e.embedding <#> %s::vector) AS distance
FROM skat.chunk_embeddings AS e
WHERE e.embedding_model_id = %s::uuid
-- Approximate ANN via chunk_embeddings_hnsw_ip_v2_idx with a bound query vector.
ORDER BY e.embedding <#> %s::vector
LIMIT %s
"""

CONSTRAINED_VECTOR_SQL = """
SELECT e.chunk_id, (e.embedding <#> %s::vector) AS distance
FROM skat.chunk_embeddings AS e
JOIN skat.chunks AS c ON c.chunk_id = e.chunk_id
WHERE e.embedding_model_id = %s::uuid
  AND c.document_id = ANY(%s)
ORDER BY e.embedding <#> %s::vector, e.chunk_id
LIMIT %s
"""

# Beholdt til EXPLAIN-tests af den gamle sammenføjede form.
EXACT_VECTOR_SQL = EXACT_CANDIDATE_SQL
HNSW_VECTOR_SQL = HNSW_CANDIDATE_SQL
VECTOR_SQL = EXACT_CANDIDATE_SQL


def _model_id(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT embedding_model_id
            FROM skat.embedding_models
            ORDER BY created_at
            LIMIT 1
            """
        )
        row = cur.fetchone()
    if not row:
        raise SkatRetrievalError("ingen embedding_models-række")
    return row[0]


def load_query_vector(conn, *, eval_id: str | None, query: str) -> str:
    """Bagudkompatibel wrapper. Gemmer ikke nye vektorer."""
    resolved = resolve_query_vector(conn, query, eval_id=eval_id, on_demand=True)
    return resolved.pgvector


def _hnsw_settings(ef_search: int) -> tuple[str, ...]:
    return (f"SET LOCAL hnsw.ef_search = {int(ef_search)}",)


def _exact_scan_settings() -> tuple[str, ...]:
    return (
        "SET LOCAL enable_indexscan = off",
        "SET LOCAL enable_bitmapscan = off",
        "SET LOCAL enable_seqscan = on",
    )


def _passes_filters(hit: SearchHit, filters: dict[str, object]) -> bool:
    year = filters.get("year")
    year_from = _as_int(filters.get("year_from", year))
    year_to = _as_int(filters.get("year_to", year))
    if year_from is not None and (hit.publication_year is None or hit.publication_year < year_from):
        return False
    if year_to is not None and (hit.publication_year is None or hit.publication_year > year_to):
        return False
    document_type = _as_text(filters.get("document_type"))
    if document_type and hit.document_type != document_type:
        return False
    section_type = _as_text(filters.get("section_type"))
    if section_type and hit.section_type != section_type:
        return False
    legal_weight = _as_text(filters.get("legal_weight"))
    if legal_weight and hit.legal_weight != legal_weight:
        return False
    if filters.get("is_final_result") is not None and bool(hit.is_final_result) != bool(
        filters.get("is_final_result")
    ):
        return False
    topic = _as_text(filters.get("topic"))
    if topic and topic not in hit.topics:
        return False
    return True


def _best_per_document(hits: list[SearchHit]) -> list[SearchHit]:
    chosen: dict[str, SearchHit] = {}
    for hit in hits:
        current = chosen.get(hit.document_id)
        if current is None:
            chosen[hit.document_id] = hit
            continue
        key_new = (-hit.rank_score, hit.chunk_index or 0, hit.chunk_id)
        key_old = (-current.rank_score, current.chunk_index or 0, current.chunk_id)
        if key_new < key_old:
            chosen[hit.document_id] = hit
    return sorted(
        chosen.values(),
        key=lambda item: (-item.rank_score, item.document_id, item.chunk_index or 0, item.chunk_id),
    )


def _candidate_hits(
    rows,
    *,
    signal: str,
    score_kind: str,
) -> list[SearchHit]:
    hits = []
    for index, row in enumerate(rows, start=1):
        chunk_id, distance = row[0], float(row[1])
        hits.append(
            SearchHit(
                document_id="",
                skm_number=None,
                chunk_id=chunk_id,
                title="",
                chunk_text="",
                section_type="",
                legal_weight="",
                is_final_result=False,
                source_url="",
                manual_source_check=False,
                rank_score=-distance,
                signals=(signal,),
                vector_rank=index,
                score_kind=score_kind,
            )
        )
    return hits


def _run_exact_candidates(conn, qvec: str, model_id, pool: int):
    owned = bool(getattr(conn, "autocommit", False))
    if owned:
        conn.autocommit = False
    try:
        with conn.cursor() as cur:
            for statement in _exact_scan_settings():
                cur.execute(statement)
            cur.execute(EXACT_CANDIDATE_SQL, (qvec, model_id, qvec, pool))
            rows = cur.fetchall()
            for statement in EXACT_RESTORE_SETTINGS:
                cur.execute(statement)
        if owned:
            conn.commit()
        return rows
    except Exception:
        if owned:
            conn.rollback()
        raise
    finally:
        if owned:
            conn.autocommit = True


def _vector_from_candidates(
    conn,
    rows,
    *,
    filters: dict[str, object],
    limit: int,
    signal: str,
    score_kind: str,
    timings: dict[str, float] | None,
    hydrate_text: bool,
) -> list[SearchHit]:
    slim = _candidate_hits(rows, signal=signal, score_kind=score_kind)
    started = time.perf_counter()
    with_meta = hydrate_hits(conn, slim, include_text=False)
    filtered = [hit for hit in with_meta if _passes_filters(hit, filters)]
    ranked = []
    for index, hit in enumerate(_best_per_document(filtered), start=1):
        ranked.append(replace(hit, vector_rank=index))
    ranked = ranked[: max(1, int(limit))]
    if hydrate_text:
        ranked = hydrate_hits(conn, ranked, include_text=True)
    if timings is not None:
        timings["hydrate"] = timings.get("hydrate", 0.0) + (time.perf_counter() - started) * 1000.0
    return ranked


def vector_search(
    conn,
    query: str,
    *,
    limit: int = 10,
    filters: dict[str, object] | None = None,
    eval_id: str | None = None,
    exact_vector: bool = False,
    ef_search: int = HNSW_EF_SEARCH,
    query_vector: str | None = None,
    embed_client=None,
    timings: dict[str, float] | None = None,
    hydrate: bool = True,
    candidate_document_ids: list[str] | None = None,
) -> list[SearchHit]:
    filters = filters or {}
    timings = timings if timings is not None else {}
    if query_vector is None:
        started = time.perf_counter()
        resolved = resolve_query_vector(
            conn, query, eval_id=eval_id, client=embed_client, on_demand=True
        )
        timings["query_embedding"] = (time.perf_counter() - started) * 1000.0
        query_vector = resolved.pgvector
    result_limit = max(1, int(limit))
    model_id = _model_id(conn)
    if candidate_document_ids is not None:
        if not candidate_document_ids:
            return []
        started = time.perf_counter()
        rows = execute_with_local_settings(
            conn,
            (),
            CONSTRAINED_VECTOR_SQL,
            (
                query_vector,
                model_id,
                candidate_document_ids,
                query_vector,
                max(result_limit, VECTOR_CANDIDATE_LIMIT),
            ),
        )
        timings["vector"] = (time.perf_counter() - started) * 1000.0
        return _vector_from_candidates(
            conn,
            rows,
            filters=filters,
            limit=result_limit,
            signal="vector_reference_scope",
            score_kind="reference_scoped_inner_product_order",
            timings=timings,
            hydrate_text=hydrate,
        )
    if exact_vector:
        started = time.perf_counter()
        max_pool = EXACT_CANDIDATE_POOLS[-1]
        rows = _run_exact_candidates(conn, query_vector, model_id, max_pool)
        timings["vector"] = (time.perf_counter() - started) * 1000.0
        started = time.perf_counter()
        with_meta = hydrate_hits(
            conn,
            _candidate_hits(rows, signal="vector_exact", score_kind="inner_product_order"),
            include_text=False,
        )
        chosen: list[SearchHit] = []
        for pool in EXACT_CANDIDATE_POOLS:
            filtered = [hit for hit in with_meta[:pool] if _passes_filters(hit, filters)]
            ranked = []
            for index, hit in enumerate(_best_per_document(filtered), start=1):
                ranked.append(replace(hit, vector_rank=index))
            chosen = ranked[:result_limit]
            if len(chosen) >= result_limit or pool == max_pool:
                break
        if hydrate:
            chosen = hydrate_hits(conn, chosen, include_text=True)
        timings["hydrate"] = timings.get("hydrate", 0.0) + (time.perf_counter() - started) * 1000.0
        return chosen
    started = time.perf_counter()
    ann_limit = max(result_limit, VECTOR_CANDIDATE_LIMIT)
    rows = execute_with_local_settings(
        conn,
        _hnsw_settings(ef_search),
        HNSW_CANDIDATE_SQL,
        (query_vector, model_id, query_vector, ann_limit),
    )
    timings["vector"] = (time.perf_counter() - started) * 1000.0
    return _vector_from_candidates(
        conn,
        rows,
        filters=filters,
        limit=result_limit,
        signal="vector_ip",
        score_kind="hnsw_inner_product_order",
        timings=timings,
        hydrate_text=hydrate,
    )


def hybrid_search(
    conn,
    query: str,
    *,
    limit: int = 10,
    filters: dict[str, object] | None = None,
    eval_id: str | None = None,
    exact_vector: bool = False,
    ef_search: int = HNSW_EF_SEARCH,
    query_vector: str | None = None,
    embed_client=None,
    timings: dict[str, float] | None = None,
) -> list[SearchHit]:
    """RRF over små lexical- og vector-kandidatsæt. Én hit pr. dokument."""
    filters = filters or {}
    timings = timings if timings is not None else {}
    pool = max(int(limit), LEXICAL_CANDIDATE_LIMIT, VECTOR_CANDIDATE_LIMIT)
    started = time.perf_counter()
    lexical = lexical_search(conn, query, limit=pool, filters=filters, hydrate=False)
    timings["lexical"] = (time.perf_counter() - started) * 1000.0
    structured_document_ids = [
        hit.document_id
        for hit in lexical
        if STRUCTURED_LAW_REFERENCE_SIGNAL in hit.signals
    ]
    vector = vector_search(
        conn,
        query,
        limit=pool,
        filters=filters,
        eval_id=eval_id,
        exact_vector=exact_vector,
        ef_search=ef_search,
        query_vector=query_vector,
        embed_client=embed_client,
        timings=timings,
        hydrate=False,
        candidate_document_ids=structured_document_ids or None,
    )
    started = time.perf_counter()
    scores: dict[str, float] = {}
    chosen: dict[str, SearchHit] = {}
    structured_reference_docs: set[str] = set()
    for rank, hit in enumerate(lexical, start=1):
        weight = (
            STRUCTURED_REFERENCE_RRF_WEIGHT
            if STRUCTURED_LAW_REFERENCE_SIGNAL in hit.signals
            else 1.0
        )
        scores[hit.document_id] = scores.get(hit.document_id, 0.0) + weight / (RRF_K + rank)
        if weight > 1.0:
            structured_reference_docs.add(hit.document_id)
        chosen.setdefault(hit.document_id, hit)
    for rank, hit in enumerate(vector, start=1):
        scores[hit.document_id] = scores.get(hit.document_id, 0.0) + 1.0 / (RRF_K + rank)
        chosen.setdefault(hit.document_id, hit)
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[: max(1, int(limit))]
    lex_rank = {hit.document_id: rank for rank, hit in enumerate(lexical, start=1)}
    vec_rank = {hit.document_id: rank for rank, hit in enumerate(vector, start=1)}
    fused = []
    for document_id, score in ordered:
        hit = chosen[document_id]
        extra = hit.signals
        if document_id in structured_reference_docs:
            extra += ("struktureret_reference_rrf_boost",)
            if document_id in vec_rank:
                extra += ("semantik_inden_for_referencefelt",)
        extra += ("hybrid_rrf",)
        fused.append(
            replace(
                hit,
                rank_score=score,
                signals=extra,
                lexical_rank=lex_rank.get(document_id),
                vector_rank=vec_rank.get(document_id),
                rrf_score=score,
                score_kind="rrf_reciprocal_rank_fusion",
            )
        )
    timings["fusion"] = (time.perf_counter() - started) * 1000.0
    started = time.perf_counter()
    hydrated = hydrate_hits(conn, fused, include_text=True)
    timings["hydrate"] = timings.get("hydrate", 0.0) + (time.perf_counter() - started) * 1000.0
    return hydrated
