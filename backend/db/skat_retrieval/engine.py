"""Samler routing, opslag og søgning. Routing A–E bruger aldrig vector eller OpenAI."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from backend.db.skat_retrieval.errors import (
    CliArgumentError,
    IdentifierNotFoundError,
    QueryEmbeddingUnavailableError,
    SkatRetrievalError,
)
from backend.db.skat_retrieval.lookup import (
    ChunkRecord,
    DocumentRecord,
    ReferenceRecord,
    get_document,
    get_final_result,
    get_reasoning,
    get_references,
    get_section_chunks,
    get_summary,
)
from backend.db.skat_retrieval.law_refs import is_bare_law_reference
from backend.db.skat_retrieval.query_embed import ResolvedQueryVector, resolve_query_vector
from backend.db.skat_retrieval.routing import (
    INTENT_ANSWERS,
    INTENT_EXACT,
    INTENT_QUESTIONS,
    INTENT_REASONING,
    INTENT_REFERENCES,
    INTENT_RESULT,
    INTENT_SUMMARY,
    INTENT_TOPICAL,
    Route,
    route_query,
)
from backend.db.skat_retrieval.search import SearchHit, lexical_search
from backend.db.skat_retrieval.settings import (
    CLI_SEARCH_MODES,
    DEFAULT_RETRIEVE_MODE,
    HNSW_EF_SEARCH,
    TIMING_KEYS,
)
from backend.db.skat_retrieval.vector import hybrid_search, vector_search

SEARCH_MODES = CLI_SEARCH_MODES
LOOKUP_INTENTS = {
    INTENT_EXACT,
    INTENT_SUMMARY,
    INTENT_RESULT,
    INTENT_REASONING,
    INTENT_REFERENCES,
}
ROUTE_LETTERS = {
    INTENT_EXACT: "A",
    INTENT_SUMMARY: "B",
    INTENT_RESULT: "C",
    INTENT_REASONING: "D",
    INTENT_REFERENCES: "E",
    INTENT_TOPICAL: "F",
    INTENT_QUESTIONS: "F",
    INTENT_ANSWERS: "F",
}


@dataclass
class RetrievalResponse:
    route: Route
    document: DocumentRecord | None = None
    summary: str | None = None
    chunks: list[ChunkRecord] | None = None
    hits: list[SearchHit] | None = None
    references: list[ReferenceRecord] | None = None
    note: str = ""
    requested_mode: str = DEFAULT_RETRIEVE_MODE
    effective_mode: str = "lookup"
    fallback_reason: str | None = None
    resolved_route: str = "F"
    exact_vector: bool = False
    timings_ms: dict[str, float | None] = field(default_factory=dict)
    embedding_usage: dict[str, object] | None = None


def route_letter(intent: str) -> str:
    return ROUTE_LETTERS.get(intent, "F")


def _ranked_mode(requested: str, exact_vector: bool) -> tuple[str, bool, str]:
    """Returnér (ranked_mode, exact_vector, effective_label)."""
    if requested == "auto":
        return "hybrid", exact_vector, "exact" if exact_vector else "hybrid"
    if requested == "exact":
        return "vector", True, "exact"
    if requested == "hybrid":
        return "hybrid", exact_vector, "exact" if exact_vector else "hybrid"
    if requested == "vector":
        return "vector", exact_vector, "exact" if exact_vector else "vector"
    if requested == "lexical":
        return "lexical", False, "lexical"
    raise CliArgumentError(f"ukendt søgemode {requested}")


def _timing_payload(timings: dict[str, float]) -> dict[str, float | None]:
    return {key: round(timings[key], 3) if key in timings else None for key in TIMING_KEYS}


def _lookup_response(**kwargs) -> RetrievalResponse:
    kwargs.setdefault("embedding_usage", None)
    kwargs.setdefault("timings_ms", {})
    return RetrievalResponse(**kwargs)


def _vector_required(ranked_mode: str, exact_vector: bool) -> bool:
    """vector/exact/--exact-vector/--high-risk må ikke falde tilbage til lexical."""
    return ranked_mode == "vector" or exact_vector


def retrieve(
    conn,
    query: str,
    *,
    limit: int = 10,
    filters: dict[str, object] | None = None,
    mode: str = DEFAULT_RETRIEVE_MODE,
    eval_id: str | None = None,
    exact_vector: bool = False,
    high_risk: bool = False,
    embed_client=None,
    honor_route_lookup: bool = True,
) -> RetrievalResponse:
    requested = mode
    if requested not in SEARCH_MODES:
        raise CliArgumentError(f"ukendt søgemode {requested}")
    if high_risk:
        exact_vector = True
    ranked_mode, exact_vector, effective_ranked = _ranked_mode(requested, exact_vector)
    route = route_query(query, filters=filters)
    merged = dict(route.filters)
    letter = route_letter(route.intent)
    if honor_route_lookup and route.intent in LOOKUP_INTENTS:
        if not route.identifier:
            if route.intent == INTENT_RESULT:
                merged.setdefault("is_final_result", True)
            if route.intent == INTENT_REASONING:
                merged.setdefault("legal_weight", "authoritative_reasoning")
            hits = lexical_search(conn, route.search_text or query, limit=limit, filters=merged)
            return _lookup_response(
                route=route,
                hits=hits,
                note="ingen identifier; lexical baseline med intent-filter; embeddings ikke anvendt",
                requested_mode=requested,
                effective_mode="lexical",
                fallback_reason="missing_identifier",
                resolved_route=letter,
                exact_vector=False,
            )
        try:
            document = get_document(conn, route.identifier)
        except IdentifierNotFoundError:
            raise
        if route.intent == INTENT_EXACT:
            return _lookup_response(
                route=route,
                document=document,
                summary=document.summary,
                note="eksakt opslag i legal_documents; embeddings ikke anvendt",
                requested_mode=requested,
                effective_mode="lookup",
                resolved_route=letter,
            )
        if route.intent == INTENT_SUMMARY:
            return _lookup_response(
                route=route,
                document=document,
                summary=get_summary(conn, route.identifier),
                note="direkte legal_documents.summary; aldrig rekonstrueret fra embeddings",
                requested_mode=requested,
                effective_mode="lookup",
                resolved_route=letter,
            )
        if route.intent == INTENT_RESULT:
            return _lookup_response(
                route=route,
                document=document,
                chunks=get_final_result(conn, route.identifier),
                note="direkte is_final_result-chunks efter chunk_index; aldrig embedding-rekonstruktion",
                requested_mode=requested,
                effective_mode="lookup",
                resolved_route=letter,
            )
        if route.intent == INTENT_REASONING:
            return _lookup_response(
                route=route,
                document=document,
                chunks=get_reasoning(conn, route.identifier),
                note="direkte authoritative_reasoning uden prior_instance; aldrig embedding-rekonstruktion",
                requested_mode=requested,
                effective_mode="lookup",
                resolved_route=letter,
            )
        return _lookup_response(
            route=route,
            document=document,
            references=get_references(conn, route.identifier),
            note="direkte document_references; embeddings ikke anvendt",
            requested_mode=requested,
            effective_mode="lookup",
            resolved_route=letter,
        )

    if honor_route_lookup and route.intent in (INTENT_QUESTIONS, INTENT_ANSWERS) and route.identifier:
        section = str(merged.get("section_type") or route.intent)
        document = get_document(conn, route.identifier)
        return _lookup_response(
            route=route,
            document=document,
            chunks=get_section_chunks(conn, route.identifier, section),
            note=f"direkte section_type={section} for identificeret dokument; embeddings ikke anvendt",
            requested_mode=requested,
            effective_mode="lookup",
            resolved_route=letter,
        )

    if not honor_route_lookup:
        letter = route_letter(INTENT_TOPICAL)

    search_text = route.search_text or query
    if requested == "auto" and is_bare_law_reference(search_text):
        ranked_mode = "lexical"
        exact_vector = False
        effective_ranked = "lexical"
    timings: dict[str, float] = {}
    total_started = time.perf_counter()
    fallback_reason = None
    effective = effective_ranked
    usage = None
    resolved: ResolvedQueryVector | None = None
    query_vector = None

    if ranked_mode == "lexical":
        started = time.perf_counter()
        hits = lexical_search(conn, search_text, limit=limit, filters=merged)
        timings["lexical"] = (time.perf_counter() - started) * 1000.0
        note = "lexical baseline (FTS, titel, emneord, overskrift)"
        if is_bare_law_reference(search_text):
            note += "; struktureret lovhenvisning; embeddings ikke anvendt"
    else:
        try:
            started = time.perf_counter()
            resolved = resolve_query_vector(
                conn,
                search_text,
                eval_id=eval_id,
                client=embed_client,
                on_demand=True,
            )
            timings["query_embedding"] = (time.perf_counter() - started) * 1000.0
            query_vector = resolved.pgvector
            usage = resolved.usage_payload()
        except QueryEmbeddingUnavailableError as exc:
            if not _vector_required(ranked_mode, exact_vector):
                fallback_reason = exc.reason
                effective = "lexical"
                exact_vector = False
                started = time.perf_counter()
                hits = lexical_search(conn, search_text, limit=limit, filters=merged)
                timings["lexical"] = (time.perf_counter() - started) * 1000.0
                note = f"lexical fallback ({exc.reason}); routing A–E uændret"
            else:
                raise
        else:
            if ranked_mode == "vector":
                hits = vector_search(
                    conn,
                    search_text,
                    limit=limit,
                    filters=merged,
                    eval_id=eval_id,
                    exact_vector=exact_vector,
                    query_vector=query_vector,
                    embed_client=embed_client,
                    timings=timings,
                )
                note = (
                    "exact vector-scan (udtømmende, uden HNSW); routing A–E uændret"
                    if exact_vector
                    else f"vector-only HNSW v2 ef_search={HNSW_EF_SEARCH}; routing A–E uændret"
                )
            else:
                hits = hybrid_search(
                    conn,
                    search_text,
                    limit=limit,
                    filters=merged,
                    eval_id=eval_id,
                    exact_vector=exact_vector,
                    query_vector=query_vector,
                    embed_client=embed_client,
                    timings=timings,
                )
                note = (
                    "hybrid lexical + exact vector-scan; routing A–E uændret"
                    if exact_vector
                    else f"hybrid lexical + HNSW v2 ef_search={HNSW_EF_SEARCH}; routing A–E uændret"
                )

    if route.intent in (INTENT_QUESTIONS, INTENT_ANSWERS):
        note = f"{note}; section_type={merged.get('section_type')}"
    timings["total"] = (time.perf_counter() - total_started) * 1000.0
    return RetrievalResponse(
        route=route,
        hits=hits,
        note=note,
        requested_mode=requested,
        effective_mode=effective,
        fallback_reason=fallback_reason,
        resolved_route=letter,
        exact_vector=exact_vector,
        timings_ms=_timing_payload(timings),
        embedding_usage=usage,
    )


def require_identifier(query: str) -> str:
    route = route_query(query)
    if not route.identifier:
        raise SkatRetrievalError("kommandoen kræver SKM-nummer eller OID")
    return route.identifier
