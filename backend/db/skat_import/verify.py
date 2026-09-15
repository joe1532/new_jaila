"""Verifikation og retrieval-smoketest. Ingen embeddings."""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.db.skat_import.constants import (
    SMOKE_2026,
    CorpusExpectations,
    PRODUCTION_EXPECTATIONS,
    SmokeSpec,
    YearExpectations,
)
from backend.db.skat_import.errors import VerifyError
from backend.db.skat_import.io import (
    ReferenceOccurrenceAssigner,
    chunks_path,
    documents_path,
    iter_jsonl,
    references_path,
)
from backend.db.skat_import.year_expect import expectations_from_year_files


@dataclass
class VerifyResult:
    checks: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def verify_year(
    input_root,
    year: int,
    conn,
    *,
    corpus: CorpusExpectations = PRODUCTION_EXPECTATIONS,
    year_expected: YearExpectations | None = None,
    smoke: SmokeSpec | None = None,
    check_hashes: bool = True,
) -> VerifyResult:
    result = VerifyResult()
    expected = year_expected or expectations_from_year_files(input_root, year)
    if year != expected.year:
        raise VerifyError(f"verify --year {year} matcher ikke {expected.year}")

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(DISTINCT d.document_id)
            FROM skat.legal_documents AS d
            JOIN skat.document_versions AS v
              ON v.document_id = d.document_id
             AND v.content_sha256 = d.content_sha256
            WHERE v.source_manifest_sha256 = %s
            """,
            (corpus.source_manifest_sha256,),
        )
        docs = int(cur.fetchone()[0])
        _expect(result, "legal_documents for manifest", docs, corpus.document_count)

        cur.execute(
            "SELECT count(*) FROM skat.legal_documents WHERE publication_year = %s",
            (year,),
        )
        _expect(result, f"dokumenter {year}", int(cur.fetchone()[0]), expected.document_count)

        cur.execute(
            """
            SELECT count(*) FROM skat.chunks
            WHERE publication_year = %s AND chunk_config_sha256 = %s
            """,
            (year, corpus.chunk_config_sha256),
        )
        _expect(result, f"chunks {year}", int(cur.fetchone()[0]), expected.chunk_count)

        if expected.span_count is not None:
            cur.execute(
                """
                SELECT count(*)
                FROM skat.chunk_source_spans AS s
                JOIN skat.chunks AS c ON c.chunk_id = s.chunk_id
                WHERE c.publication_year = %s AND c.chunk_config_sha256 = %s
                """,
                (year, corpus.chunk_config_sha256),
            )
            _expect(result, f"source_spans {year}", int(cur.fetchone()[0]), expected.span_count)

        cur.execute(
            """
            SELECT count(*)
            FROM skat.document_references AS r
            JOIN skat.legal_documents AS d ON d.document_id = r.source_document_id
            WHERE d.publication_year = %s
            """,
            (year,),
        )
        db_refs = int(cur.fetchone()[0])
        jsonl_lines = 0
        for _record in iter_jsonl(references_path(input_root, year)):
            jsonl_lines += 1
        _expect(result, f"referencelinjer {year}", jsonl_lines, expected.reference_count)
        _expect(result, f"referencer {year}", db_refs, expected.reference_count)

        cur.execute(
            """
            SELECT count(*) FROM skat.chunks
            WHERE publication_year = %s AND section_type = 'summary'
            """,
            (year,),
        )
        _expect(result, "summary-chunks", int(cur.fetchone()[0]), expected.summary_chunk_count)

        cur.execute(
            """
            SELECT count(*) FROM skat.chunks
            WHERE publication_year = %s AND is_final_result = true
            """,
            (year,),
        )
        _expect(result, "is_final_result", int(cur.fetchone()[0]), expected.final_result_count)

        cur.execute(
            """
            SELECT count(*) FROM skat.chunks
            WHERE publication_year = %s AND legal_weight = 'authoritative_reasoning'
            """,
            (year,),
        )
        _expect(
            result,
            "authoritative_reasoning",
            int(cur.fetchone()[0]),
            expected.authoritative_reasoning_count,
        )

        cur.execute(
            """
            SELECT count(*) FROM skat.chunks
            WHERE publication_year = %s AND legal_weight = 'authoritative_result'
            """,
            (year,),
        )
        _expect(
            result,
            "authoritative_result",
            int(cur.fetchone()[0]),
            expected.authoritative_result_count,
        )

        cur.execute(
            "SELECT coalesce(max(token_count), 0) FROM skat.chunks WHERE publication_year = %s",
            (year,),
        )
        token_max = int(cur.fetchone()[0])
        if token_max > expected.token_max:
            result.errors.append(f"token_count max={token_max} overstiger {expected.token_max}")
        else:
            result.checks.append(f"token_count max={token_max} <= {expected.token_max}")

        cur.execute(
            """
            SELECT count(*) FROM skat.chunks c
            WHERE NOT EXISTS (
                SELECT 1 FROM skat.legal_documents d WHERE d.document_id = c.document_id
            )
            """
        )
        _expect(result, "orphan chunks", int(cur.fetchone()[0]), 0)

        cur.execute(
            """
            SELECT count(*) FROM skat.chunk_source_spans s
            WHERE NOT EXISTS (
                SELECT 1 FROM skat.chunks c WHERE c.chunk_id = s.chunk_id
            )
            """
        )
        _expect(result, "orphan spans", int(cur.fetchone()[0]), 0)

        cur.execute(
            """
            SELECT count(*) FROM skat.document_references r
            WHERE NOT EXISTS (
                SELECT 1 FROM skat.legal_documents d WHERE d.document_id = r.source_document_id
            )
            """
        )
        _expect(result, "orphan referencekilder", int(cur.fetchone()[0]), 0)

        cur.execute(
            """
            SELECT count(*) FROM skat.document_references
            WHERE resolution_status = 'resolved'
              AND (
                    target_document_id IS NULL
                    OR NOT EXISTS (
                        SELECT 1 FROM skat.legal_documents d
                        WHERE d.document_id = target_document_id
                    )
              )
            """
        )
        _expect(result, "resolved uden target", int(cur.fetchone()[0]), 0)

        cur.execute(
            """
            SELECT count(*) FROM skat.chunk_embeddings e
            WHERE NOT EXISTS (
                SELECT 1 FROM skat.chunks c WHERE c.chunk_id = e.chunk_id
            )
            """
        )
        _expect(result, "orphan embeddings", int(cur.fetchone()[0]), 0)
        cur.execute("SELECT count(*) FROM skat.chunk_embeddings")
        result.checks.append(f"chunk_embeddings: {int(cur.fetchone()[0])}")

    if check_hashes:
        _verify_hashes(input_root, year, conn, corpus, result)
    if smoke is not None:
        _smoke_test(conn, smoke, result)

    if result.errors:
        raise VerifyError("verify fejlede:\n- " + "\n- ".join(result.errors))
    return result


def _expect(result: VerifyResult, label: str, actual: int, expected: int) -> None:
    if actual != expected:
        result.errors.append(f"{label}: {actual}, forventet {expected}")
    else:
        result.checks.append(f"{label}: {actual}")


def _verify_hashes(input_root, year, conn, corpus: CorpusExpectations, result: VerifyResult) -> None:
    """Sammenlign JSONL-hashes med databasen i batches. Ingen dokumenttekst i fejl."""
    with conn.cursor() as cur:
        doc_ids = []
        doc_sha = {}
        for record in iter_jsonl(documents_path(input_root, year)):
            document_id = record["document_id"]
            doc_ids.append(document_id)
            doc_sha[document_id] = record["content_sha256"]
        if doc_ids:
            cur.execute(
                """
                SELECT document_id, content_sha256
                FROM skat.legal_documents
                WHERE document_id = ANY(%s)
                """,
                (doc_ids,),
            )
            found = {row[0]: row[1] for row in cur.fetchall()}
            for document_id, digest in doc_sha.items():
                if found.get(document_id) != digest:
                    result.errors.append(f"hash-mismatch dokument {document_id}")
                    return

        chunk_ids = []
        chunk_sha = {}
        for record in iter_jsonl(chunks_path(input_root, year)):
            chunk_id = record["chunk_id"]
            chunk_ids.append(chunk_id)
            chunk_sha[chunk_id] = (record["text_sha256"], record["embedding_text_sha256"])
        if chunk_ids:
            cur.execute(
                """
                SELECT chunk_id, text_sha256, embedding_text_sha256
                FROM skat.chunks
                WHERE chunk_id = ANY(%s)
                """,
                (chunk_ids,),
            )
            found_chunks = {row[0]: (row[1], row[2]) for row in cur.fetchall()}
            for chunk_id, digests in chunk_sha.items():
                if found_chunks.get(chunk_id) != digests:
                    result.errors.append(f"hash-mismatch chunk {chunk_id}")
                    return

        assigner = ReferenceOccurrenceAssigner()
        keys = []
        for record in iter_jsonl(references_path(input_root, year)):
            _canonical, _index, key = assigner.assign(record)
            keys.append(key)
        if keys:
            cur.execute(
                "SELECT reference_key FROM skat.document_references WHERE reference_key = ANY(%s)",
                (keys,),
            )
            found_keys = {row[0] for row in cur.fetchall()}
            missing = [key for key in keys if key not in found_keys]
            if missing:
                result.errors.append(f"mangler {len(missing)} reference_key for {year}")
                return
    result.checks.append(f"JSONL-hashes matcher databasen for {year}")


def _smoke_test(conn, smoke: SmokeSpec, result: VerifyResult) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM skat.get_document_by_identifier(%s)", (smoke.skm_number,))
        doc = cur.fetchone()
        if not doc:
            result.errors.append(f"SKM-opslag {smoke.skm_number} gav intet dokument")
            return
        result.checks.append(f"SKM-opslag {smoke.skm_number}")

        cur.execute("SELECT skat.get_document_summary(%s)", (smoke.skm_number,))
        summary = cur.fetchone()[0] or ""
        if len(summary) < smoke.summary_min_length:
            result.errors.append(
                f"summary-længde {len(summary)} < {smoke.summary_min_length}"
            )
        else:
            result.checks.append(f"fuldt resumé {len(summary)} tegn")

        cur.execute(
            "SELECT is_final_result FROM skat.get_document_final_result(%s)",
            (smoke.skm_number,),
        )
        flags = [row[0] for row in cur.fetchall()]
        if not flags or not all(flags):
            result.errors.append("final_result indeholdt ikke-flaggede chunks")
        else:
            result.checks.append(f"final_result {len(flags)} chunks")

        cur.execute(
            "SELECT legal_weight FROM skat.get_document_reasoning(%s)",
            (smoke.skm_number,),
        )
        weights = [row[0] for row in cur.fetchall()]
        if any(w != "authoritative_reasoning" for w in weights) or "prior_instance" in weights:
            result.errors.append("reasoning indeholdt andet end authoritative_reasoning")
        elif not weights:
            result.errors.append("reasoning var tom")
        else:
            result.checks.append(f"reasoning {len(weights)} chunks")

        cur.execute(
            """
            SELECT cited_identifier FROM skat.get_document_references(%s)
            WHERE direction = 'outgoing'
            """,
            (smoke.skm_number,),
        )
        citations = {row[0] for row in cur.fetchall()}
        if smoke.older_citation not in citations:
            result.errors.append(
                f"mangler udgående reference {smoke.older_citation}"
            )
        else:
            result.checks.append(f"reference til {smoke.older_citation}")

        cur.execute(
            """
            SELECT manual_source_check
            FROM skat.get_document_by_identifier(%s)
            """,
            (smoke.manual_skm_number,),
        )
        row = cur.fetchone()
        if not row or row[0] is not True:
            result.errors.append(
                f"{smoke.manual_skm_number} har ikke manual_source_check=true"
            )
        else:
            result.checks.append(f"manual_source_check {smoke.manual_skm_number}")
