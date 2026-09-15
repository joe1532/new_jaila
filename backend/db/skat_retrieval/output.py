"""Maskinlæsbart JSON/JSONL-output. Ingen credentials eller vektorer.

JSONL-valg: første linje er `record_type=query_metadata` (søgemetadata uden
resultater). Efterfølgende linjer er selvstændige resultatrækker med
`record_type=result`. Lookup-kommandoer bruger tilsvarende metadata-linje
plus én linje pr. chunk/reference.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from backend.db.skat_retrieval.engine import RetrievalResponse
from backend.db.skat_retrieval.lookup import (
    ChunkRecord,
    DocumentRecord,
    ReferenceRecord,
    count_prior_instance_chunks,
)
from backend.db.skat_retrieval.search import SearchHit
from backend.db.skat_retrieval.settings import HNSW_EF_SEARCH, SCHEMA_VERSION


def dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, allow_nan=False)


def emit_json(payload: dict[str, Any]) -> None:
    sys.stdout.write(dumps(payload) + "\n")
    sys.stdout.flush()


def emit_jsonl(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        sys.stdout.write(dumps(row) + "\n")
    sys.stdout.flush()


def emit_error(*, error: Exception, identifier: str | None, debug: bool) -> None:
    from backend.db.skat_retrieval.errors import SkatRetrievalError

    code = getattr(error, "error_code", "retrieval_error")
    details = dict(getattr(error, "details", {}) or {})
    if identifier:
        details.setdefault("identifier", identifier)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "error": {
            "code": code,
            "message": str(error),
            **details,
        },
    }
    sys.stderr.write(dumps(payload) + "\n")
    if debug:
        import traceback

        traceback.print_exc(file=sys.stderr)
    sys.stderr.flush()


def _filters_payload(filters: dict[str, object] | None) -> dict[str, object | None]:
    filters = filters or {}
    return {
        "year_from": filters.get("year_from", filters.get("year")),
        "year_to": filters.get("year_to", filters.get("year")),
        "document_type": filters.get("document_type"),
        "topic": filters.get("topic"),
        "section_type": filters.get("section_type"),
    }


def _ranking_signals(hit: SearchHit) -> dict[str, object]:
    signals: dict[str, object] = {"score_kind": hit.score_kind}
    if hit.lexical_rank is not None:
        signals["lexical_rank"] = hit.lexical_rank
    if hit.vector_rank is not None:
        signals["vector_rank"] = hit.vector_rank
    if hit.rrf_score is not None:
        signals["rrf_score"] = hit.rrf_score
    if hit.signals:
        signals["applied"] = list(hit.signals)
    return signals


def hit_to_result(hit: SearchHit, *, rank: int) -> dict[str, object | None]:
    return {
        "rank": rank,
        "document_id": hit.document_id,
        "source_oid": hit.source_oid,
        "skm_number": hit.skm_number,
        "title": hit.title,
        "publication_year": hit.publication_year,
        "document_type": hit.document_type,
        "topics": list(hit.topics) if hit.topics else [],
        "chunk_id": hit.chunk_id,
        "chunk_index": hit.chunk_index,
        "section_type": hit.section_type,
        "legal_weight": hit.legal_weight,
        "text": hit.chunk_text,
        "token_count": hit.token_count,
        "score": hit.rank_score,
        "ranking_signals": _ranking_signals(hit),
        "source_url": hit.source_url,
        "manual_source_check": hit.manual_source_check,
    }


def search_payload(
    response: RetrievalResponse,
    *,
    query: str,
    limit: int,
    filters: dict[str, object] | None,
    elapsed_ms: float,
    include_references: bool,
    extra_references: dict[str, list[dict]] | None = None,
) -> dict[str, object]:
    results = []
    for rank, hit in enumerate(response.hits or [], start=1):
        item = hit_to_result(hit, rank=rank)
        if include_references and extra_references:
            item["references"] = extra_references.get(hit.document_id) or []
        results.append(item)
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "query": query,
        "requested_mode": response.requested_mode,
        "effective_mode": response.effective_mode,
        "fallback_reason": response.fallback_reason,
        "resolved_route": response.resolved_route,
        "retrieval_mode": response.effective_mode,
        "limit": limit,
        "hnsw_ef_search": None if response.effective_mode in {"lexical", "lookup", "exact"} else HNSW_EF_SEARCH,
        "filters": _filters_payload(filters),
        "result_count": len(results),
        "elapsed_ms": round(elapsed_ms, 3),
        "timings_ms": response.timings_ms or None,
        "embedding_usage": response.embedding_usage if response.embedding_usage else None,
        "note": response.note,
        "results": results,
    }
    if response.document is not None:
        payload["document"] = document_meta(response.document)
    if response.summary is not None:
        payload["summary"] = response.summary
    if response.chunks is not None:
        payload["chunks"] = [chunk_payload(chunk) for chunk in response.chunks]
    if response.references is not None:
        payload["references"] = [reference_payload(row) for row in response.references]
    return payload


def document_meta(document: DocumentRecord) -> dict[str, object | None]:
    return {
        "document_id": document.document_id,
        "source_oid": document.source_oid,
        "skm_number": document.skm_number,
        "title": document.title,
        "source_url": document.source_url,
        "manual_source_check": document.manual_source_check,
        "publication_year": document.publication_year,
        "document_type": document.document_type,
    }


def chunk_payload(chunk: ChunkRecord) -> dict[str, object | None]:
    return {
        "chunk_id": chunk.chunk_id,
        "chunk_index": chunk.chunk_index,
        "section_type": chunk.section_type,
        "legal_weight": chunk.legal_weight,
        "text": chunk.chunk_text,
        "token_count": chunk.token_count,
        "source_url": chunk.source_url,
        "manual_source_check": chunk.manual_source_check,
        "is_final_result": chunk.is_final_result,
    }


def summary_payload(document: DocumentRecord, summary: str, *, identifier: str) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "command": "summary",
        "identifier": identifier,
        "requested_mode": "lookup",
        "effective_mode": "lookup",
        "fallback_reason": None,
        "resolved_route": "B",
        **document_meta(document),
        "summary": summary,
        "summary_length": len(summary),
    }


def result_payload(document: DocumentRecord, chunks: list[ChunkRecord], *, identifier: str) -> dict[str, object]:
    texts = [chunk.chunk_text for chunk in chunks]
    return {
        "schema_version": SCHEMA_VERSION,
        "command": "result",
        "identifier": identifier,
        "requested_mode": "lookup",
        "effective_mode": "lookup",
        "fallback_reason": None,
        "resolved_route": "C",
        **document_meta(document),
        "chunk_count": len(chunks),
        "chunks": [chunk_payload(chunk) for chunk in chunks],
        "combined_text": "\n\n".join(texts) if texts else "",
    }


def reasoning_payload(
    conn,
    document: DocumentRecord,
    chunks: list[ChunkRecord],
    *,
    identifier: str,
) -> dict[str, object]:
    omitted = count_prior_instance_chunks(conn, identifier)
    return {
        "schema_version": SCHEMA_VERSION,
        "command": "reasoning",
        "identifier": identifier,
        "requested_mode": "lookup",
        "effective_mode": "lookup",
        "fallback_reason": None,
        "resolved_route": "D",
        **document_meta(document),
        "prior_instance_omitted": omitted > 0,
        "prior_instance_chunk_count": omitted,
        "chunk_count": len(chunks),
        "chunks": [chunk_payload(chunk) for chunk in chunks],
        "combined_text": "\n\n".join(chunk.chunk_text for chunk in chunks),
    }


def reference_payload(row: ReferenceRecord) -> dict[str, object | None]:
    return {
        "direction": row.direction,
        "reference_id": row.reference_id,
        "reference_key": row.reference_key,
        "reference_type": row.reference_type,
        "cited_identifier": row.cited_identifier,
        "exact_reference_text": row.exact_reference_text,
        "source_document_id": row.source_document_id,
        "source_chunk_id": row.source_chunk_id,
        "target_document_id": row.target_document_id,
        "original_target_document_id": row.original_target_document_id,
        "target_url": row.target_url,
        "source_url": row.source_url,
        "resolution_status": row.resolution_status,
        "occurrence_index": row.occurrence_index,
    }


def references_payload(
    document: DocumentRecord,
    rows: list[ReferenceRecord],
    *,
    identifier: str,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "command": "references",
        "identifier": identifier,
        "requested_mode": "lookup",
        "effective_mode": "lookup",
        "fallback_reason": None,
        "resolved_route": "E",
        **document_meta(document),
        "reference_count": len(rows),
        "outgoing_count": sum(1 for row in rows if row.direction == "outgoing"),
        "incoming_count": sum(1 for row in rows if row.direction == "incoming"),
        "references": [reference_payload(row) for row in rows],
    }
