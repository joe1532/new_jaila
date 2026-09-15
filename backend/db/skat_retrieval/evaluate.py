"""Evaluering af retrieval. Draft-gold er ikke fagligt valideret. Ingen OpenAI-kald."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from backend.db.skat_retrieval.engine import retrieve
from backend.db.skat_retrieval.errors import IdentifierNotFoundError
from backend.db.skat_retrieval.lookup import get_final_result, get_reasoning, get_summary
from backend.db.skat_retrieval.settings import DEFAULT_RETRIEVE_MODE, HNSW_EF_SEARCH


@dataclass
class CaseScore:
    eval_id: str
    query_type: str
    ok: bool
    detail: str
    reciprocal_rank: float = 0.0
    hit_at_5: bool = False
    hit_at_10: bool = False
    contaminated: bool = False
    empty: bool = False


@dataclass
class EvalReport:
    cases: list[CaseScore] = field(default_factory=list)
    gold_status_counts: dict[str, int] = field(default_factory=dict)
    mode: str = "lexical"

    def metric(self, query_type: str | None, predicate) -> float | None:
        selected = [case for case in self.cases if query_type is None or case.query_type == query_type]
        if not selected:
            return None
        return sum(1 for case in selected if predicate(case)) / len(selected)

    def as_dict(self) -> dict[str, object]:
        topical = [case for case in self.cases if case.query_type == "topical"]
        ranked = [
            case
            for case in self.cases
            if case.query_type in {"topical", "metadata_filter", "manual_source_check"}
            or (case.query_type in {"questions", "answers"} and case.reciprocal_rank)
            or case.hit_at_5
            or case.hit_at_10
        ]
        ranked_or_topical = topical or ranked
        mrr_vals = [case.reciprocal_rank for case in ranked_or_topical]
        type_counts: dict[str, int] = {}
        for case in self.cases:
            type_counts[case.query_type] = type_counts.get(case.query_type, 0) + 1
        return {
            "n_cases": len(self.cases),
            "mode": self.mode,
            "query_type_counts": type_counts,
            "hnsw_ef_search": None if self.mode == "lexical" else HNSW_EF_SEARCH,
            "gold_status_counts": self.gold_status_counts,
            "gold_note": (
                "Alle cases i dette sæt har gold_status=draft. "
                "Tallene er automatisk udledt og må ikke beskrives som fagligt valideret kvalitet."
            ),
            "routing_a_e_unchanged": True,
            "exact_lookup_accuracy": self.metric("exact_lookup", lambda c: c.ok),
            "summary_completeness": self.metric("summary", lambda c: c.ok),
            "final_result_accuracy": self.metric("final_result", lambda c: c.ok),
            "authoritative_reasoning_accuracy": self.metric(
                "authoritative_reasoning", lambda c: c.ok
            ),
            "prior_instance_contamination": self.metric(
                "prior_instance_exclusion", lambda c: c.contaminated
            ),
            "recall_at_5": (
                sum(1 for case in ranked_or_topical if case.hit_at_5) / len(ranked_or_topical)
                if ranked_or_topical
                else None
            ),
            "recall_at_10": (
                sum(1 for case in ranked_or_topical if case.hit_at_10) / len(ranked_or_topical)
                if ranked_or_topical
                else None
            ),
            "mean_reciprocal_rank": (
                sum(mrr_vals) / len(mrr_vals) if mrr_vals else None
            ),
            "section_role_accuracy": self.metric("section_role", lambda c: c.ok),
            "reference_retrieval_accuracy": self.metric("references", lambda c: c.ok),
            "queries_without_relevant_results": sum(1 for case in self.cases if case.empty),
            "n_ranked_cases": len(ranked_or_topical),
        }


def load_dataset(path: Path) -> list[dict]:
    cases = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        record = json.loads(stripped)
        if not isinstance(record, dict):
            raise ValueError(f"{path} linje {line_no}: forventede objekt")
        cases.append(record)
    return cases


def _first_relevant_rank(doc_ids: list[str], expected: list[str]) -> int | None:
    expected_set = set(expected)
    for index, document_id in enumerate(doc_ids, start=1):
        if document_id in expected_set:
            return index
    return None


def _score_case(
    conn,
    case: dict,
    *,
    search_limit: int,
    mode: str,
    exact_vector: bool = False,
) -> CaseScore:
    eval_id = case["eval_id"]
    query_type = case["query_type"]
    query = case["query"]
    expected_docs = list(case.get("expected_document_ids") or [])
    expected_chunks = list(case.get("expected_chunk_ids") or [])
    expected_sections = set(case.get("expected_section_types") or [])
    expected_weights = set(case.get("expected_legal_weights") or [])
    forbidden_weights = set(case.get("forbidden_legal_weights") or [])
    filters = dict(case.get("filters") or {})
    identifier = expected_docs[0] if expected_docs else None

    try:
        response = retrieve(
            conn,
            query,
            limit=search_limit,
            filters=filters,
            mode=mode,
            eval_id=eval_id,
            exact_vector=exact_vector,
        )
    except IdentifierNotFoundError as exc:
        return CaseScore(eval_id, query_type, False, str(exc), empty=True)

    hits = response.hits or []
    hit_docs = [hit.document_id for hit in hits]
    rank = _first_relevant_rank(hit_docs, expected_docs) if expected_docs else None
    rr = 0.0 if rank is None else 1.0 / rank
    hit5 = rank is not None and rank <= 5
    hit10 = rank is not None and rank <= 10

    if query_type == "exact_lookup":
        ok = bool(
            response.document and response.document.document_id in expected_docs
        )
        empty = response.document is None
        return CaseScore(eval_id, query_type, ok, "eksakt dokument", empty=empty)

    if query_type == "summary":
        if not identifier:
            return CaseScore(eval_id, query_type, False, "mangler expected_document_ids", empty=True)
        gold = get_summary(conn, identifier)
        got = response.summary or ""
        ok = got == gold and len(got) == len(gold) and got != ""
        return CaseScore(
            eval_id,
            query_type,
            ok,
            f"summary_len={len(got)} gold={len(gold)}",
            empty=not got,
        )

    if query_type == "final_result":
        chunks = response.chunks or []
        got_ids = [chunk.chunk_id for chunk in chunks]
        if expected_chunks:
            ok = got_ids == expected_chunks
        else:
            gold = [chunk.chunk_id for chunk in get_final_result(conn, identifier)]
            ok = got_ids == gold
        order_ok = [chunk.chunk_index for chunk in chunks] == sorted(
            chunk.chunk_index for chunk in chunks
        )
        return CaseScore(
            eval_id,
            query_type,
            ok and order_ok,
            f"chunks={len(got_ids)}",
            empty=not got_ids,
        )

    if query_type in {"authoritative_reasoning", "prior_instance_exclusion"}:
        chunks = response.chunks or []
        weights = {chunk.legal_weight for chunk in chunks}
        contaminated = bool(weights & forbidden_weights) or "prior_instance" in weights
        got_ids = [chunk.chunk_id for chunk in chunks]
        if expected_chunks:
            ok = got_ids == expected_chunks and not contaminated
        else:
            gold = [chunk.chunk_id for chunk in get_reasoning(conn, identifier)]
            ok = got_ids == gold and not contaminated
        if query_type == "prior_instance_exclusion":
            ok = not contaminated and bool(chunks)
        return CaseScore(
            eval_id,
            query_type,
            ok,
            f"weights={sorted(weights)}",
            contaminated=contaminated,
            empty=not chunks,
        )

    if query_type == "references":
        refs = response.references or []
        cited = {item.cited_identifier for item in refs if item.cited_identifier}
        target_ids = {item.target_document_id for item in refs if item.target_document_id}
        ok = True
        if expected_docs and response.document:
            ok = response.document.document_id in expected_docs or bool(
                target_ids & set(expected_docs)
            )
        notes = case.get("notes") or ""
        if "cited:" in notes:
            required = [
                part.strip().strip(",")
                for part in notes.split("cited:", 1)[1].split()
                if part.strip()
            ][:1]
            ok = ok and all(item in cited for item in required)
        return CaseScore(
            eval_id,
            query_type,
            ok and bool(refs),
            f"refs={len(refs)}",
            empty=not refs,
        )

    if query_type in {"questions", "answers"}:
        chunks = response.chunks or []
        if chunks:
            ok = all(
                (not expected_sections or chunk.section_type in expected_sections)
                for chunk in chunks
            ) and (
                not expected_docs
                or (
                    response.document is not None
                    and response.document.document_id in expected_docs
                )
            )
            return CaseScore(
                eval_id,
                query_type,
                ok and bool(chunks),
                f"section_chunks={len(chunks)}",
                empty=not chunks,
            )
        ok_hits = [
            hit
            for hit in hits
            if (not expected_sections or hit.section_type in expected_sections)
            and (not expected_weights or hit.legal_weight in expected_weights)
        ]
        forbidden = [hit for hit in hits if hit.legal_weight in forbidden_weights]
        ok = bool(ok_hits) and not forbidden
        if expected_docs:
            ok = ok and any(hit.document_id in expected_docs for hit in ok_hits)
        return CaseScore(
            eval_id,
            query_type,
            ok,
            f"hits={len(hits)} role_ok={len(ok_hits)}",
            hit_at_5=hit5,
            hit_at_10=hit10,
            reciprocal_rank=rr,
            contaminated=bool(forbidden),
            empty=not hits,
        )

    # topical / questions / answers / metadata_filter / manual_source_check
    if query_type == "manual_source_check":
        ok = bool(response.document and response.document.manual_source_check)
        if hits and not response.document:
            ok = any(hit.manual_source_check and hit.document_id in expected_docs for hit in hits)
        return CaseScore(eval_id, query_type, ok, "manual_source_check", empty=not ok)

    relevant = [hit for hit in hits if not expected_docs or hit.document_id in expected_docs]
    if expected_sections:
        relevant = [hit for hit in relevant if hit.section_type in expected_sections]
    if expected_weights:
        relevant = [hit for hit in relevant if hit.legal_weight in expected_weights]
    forbidden = [hit for hit in hits if hit.legal_weight in forbidden_weights]
    ok = bool(relevant) and not forbidden
    return CaseScore(
        eval_id,
        query_type,
        ok,
        f"hits={len(hits)} relevant={len(relevant)}",
        reciprocal_rank=rr,
        hit_at_5=hit5,
        hit_at_10=hit10,
        contaminated=bool(forbidden),
        empty=not relevant,
    )


def evaluate_dataset(
    conn,
    path: Path,
    *,
    search_limit: int = 10,
    mode: str = DEFAULT_RETRIEVE_MODE,
    exact_vector: bool = False,
) -> EvalReport:
    report = EvalReport(mode=mode)
    for case in load_dataset(path):
        status = str(case.get("gold_status") or "unknown")
        report.gold_status_counts[status] = report.gold_status_counts.get(status, 0) + 1
        report.cases.append(
            _score_case(
                conn,
                case,
                search_limit=search_limit,
                mode=mode,
                exact_vector=exact_vector,
            )
        )
    return report
