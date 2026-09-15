"""Resumérbar corpusimport og slutverifikation. Ingen embeddings."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from backend.db.skat_import.constants import (
    EXPECTED_AUTHORITATIVE_REASONING_COUNT,
    EXPECTED_AUTHORITATIVE_RESULT_COUNT,
    EXPECTED_DOCUMENT_COUNT,
    EXPECTED_FINAL_RESULT_COUNT,
    EXPECTED_PUBLICATION_YEAR_INFERRED,
    EXPECTED_SUMMARY_CHUNK_COUNT,
    EXPECTED_YEARS_WITH_CHUNKS,
    PRODUCTION_EXPECTATIONS,
    SMOKE_2026,
    CorpusExpectations,
)
from backend.db.skat_import.errors import SkatImportError, VerifyError
from backend.db.skat_import.preflight import PreflightResult, run_preflight
from backend.db.skat_import.verify import VerifyResult, verify_year, _expect, _smoke_test
from backend.db.skat_import.year import import_year
from backend.db.skat_import.year_expect import (
    APPROVED_PILOT_YEAR,
    descending_years,
    expectations_from_year_files,
)


@dataclass
class YearOutcome:
    year: int
    action: str
    chunks_inserted: int = 0
    chunks_skipped: int = 0
    spans_inserted: int = 0
    spans_skipped: int = 0
    references_inserted: int = 0
    references_skipped: int = 0


@dataclass
class CorpusImportResult:
    years: list[YearOutcome] = field(default_factory=list)
    skipped: list[int] = field(default_factory=list)
    imported: list[int] = field(default_factory=list)


def has_complete_year_run(conn, year: int) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM skat.import_runs
            WHERE publication_year = %s
              AND phase = 'year'
              AND status = 'complete'
            LIMIT 1
            """,
            (year,),
        )
        return cur.fetchone() is not None


def assert_document_register(conn, expected: int = EXPECTED_DOCUMENT_COUNT) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM skat.legal_documents")
        actual = int(cur.fetchone()[0])
    if actual != expected:
        raise SkatImportError(
            f"legal_documents har {actual} rækker, forventet {expected}"
        )
    return actual


def import_corpus(
    input_root: Path,
    start_year: int,
    end_year: int,
    work_conn,
    audit_conn,
    *,
    expected: CorpusExpectations = PRODUCTION_EXPECTATIONS,
    batch_size: int = 1000,
    skip_years: set[int] | None = None,
    verify_each_year: bool = True,
    preflight: PreflightResult | None = None,
) -> CorpusImportResult:
    skip_years = set(skip_years) if skip_years is not None else {APPROVED_PILOT_YEAR}
    result = preflight or run_preflight(input_root, expected)
    available = set(result.years)
    years = descending_years(start_year, end_year, skip=skip_years)
    missing = [year for year in years if year not in available]
    if missing:
        raise SkatImportError(f"år mangler i korpus: {missing}")
    assert_document_register(work_conn, expected.document_count)
    work_conn.rollback()

    outcomes = CorpusImportResult()
    for year in descending_years(start_year, end_year, skip=None):
        if year in skip_years:
            print(f"år {year}: sprunget over (allerede godkendt pilotår)", flush=True)
            outcomes.skipped.append(year)
            outcomes.years.append(YearOutcome(year=year, action="approved-skip"))
            continue
        year_expected = expectations_from_year_files(input_root, year)
        if has_complete_year_run(work_conn, year):
            try:
                verify_year(
                    input_root,
                    year,
                    work_conn,
                    corpus=expected,
                    year_expected=year_expected,
                    smoke=None,
                    check_hashes=True,
                )
            except VerifyError:
                print(f"år {year}: FEJL fase=verify (complete run matchede ikke data)", flush=True)
                raise
            work_conn.rollback()
            print(
                f"år {year}: sprunget over "
                f"(complete import_run, tællinger og hashes OK)",
                flush=True,
            )
            outcomes.skipped.append(year)
            outcomes.years.append(YearOutcome(year=year, action="resume-skip"))
            continue

        print(
            f"år {year}: importerer chunks={year_expected.chunk_count} "
            f"refs={year_expected.reference_count}",
            flush=True,
        )

        def _pre_commit(conn, *, current_year=year, current_expected=year_expected):
            if not verify_each_year:
                return
            verify_year(
                input_root,
                current_year,
                conn,
                corpus=expected,
                year_expected=current_expected,
                smoke=None,
                check_hashes=True,
            )

        try:
            progress = import_year(
                input_root,
                year,
                work_conn,
                audit_conn,
                expectations=year_expected,
                batch_size=batch_size,
                pre_commit_verify=_pre_commit if verify_each_year else None,
            )
        except Exception as exc:
            print(f"år {year}: FEJL fase=import: {exc}", flush=True)
            raise
        outcomes.imported.append(year)
        outcomes.years.append(
            YearOutcome(
                year=year,
                action="imported",
                chunks_inserted=progress.chunks_inserted,
                chunks_skipped=progress.chunks_skipped,
                spans_inserted=progress.spans_inserted,
                spans_skipped=progress.spans_skipped,
                references_inserted=progress.references_inserted,
                references_skipped=progress.references_skipped,
            )
        )
        print(f"år {year}: complete efter verify", flush=True)
    return outcomes


def verify_corpus(
    input_root: Path,
    conn,
    *,
    expected: CorpusExpectations = PRODUCTION_EXPECTATIONS,
) -> VerifyResult:
    preflight = run_preflight(input_root, expected)
    result = VerifyResult()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM skat.legal_documents")
        _expect(result, "legal_documents", int(cur.fetchone()[0]), expected.document_count)
        cur.execute("SELECT count(*) FROM skat.document_versions")
        _expect(result, "document_versions", int(cur.fetchone()[0]), expected.document_count)
        cur.execute("SELECT count(*) FROM skat.chunks")
        _expect(result, "chunks", int(cur.fetchone()[0]), expected.chunk_count)
        cur.execute("SELECT count(*) FROM skat.document_references")
        _expect(result, "document_references", int(cur.fetchone()[0]), expected.reference_count)
        cur.execute("SELECT count(*) FROM skat.chunks WHERE section_type = 'summary'")
        _expect(result, "summary-chunks", int(cur.fetchone()[0]), EXPECTED_SUMMARY_CHUNK_COUNT)
        cur.execute(
            "SELECT count(*) FROM skat.chunks WHERE legal_weight = 'authoritative_reasoning'"
        )
        _expect(
            result,
            "authoritative_reasoning",
            int(cur.fetchone()[0]),
            EXPECTED_AUTHORITATIVE_REASONING_COUNT,
        )
        cur.execute(
            "SELECT count(*) FROM skat.chunks WHERE legal_weight = 'authoritative_result'"
        )
        _expect(
            result,
            "authoritative_result",
            int(cur.fetchone()[0]),
            EXPECTED_AUTHORITATIVE_RESULT_COUNT,
        )
        cur.execute("SELECT count(*) FROM skat.chunks WHERE is_final_result = true")
        _expect(result, "is_final_result", int(cur.fetchone()[0]), EXPECTED_FINAL_RESULT_COUNT)
        cur.execute(
            "SELECT count(*) FROM skat.legal_documents WHERE publication_year_inferred = true"
        )
        _expect(
            result,
            "publication_year_inferred",
            int(cur.fetchone()[0]),
            EXPECTED_PUBLICATION_YEAR_INFERRED,
        )
        cur.execute("SELECT coalesce(max(token_count), 0) FROM skat.chunks")
        token_max = int(cur.fetchone()[0])
        if token_max > 1000:
            result.errors.append(f"token_count max={token_max} overstiger 1000")
        else:
            result.checks.append(f"token_count max={token_max} <= 1000")
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
        cur.execute("SELECT count(*) FROM skat.embedding_models")
        result.checks.append(f"embedding_models: {int(cur.fetchone()[0])}")
        cur.execute("SELECT count(DISTINCT publication_year) FROM skat.chunks")
        _expect(result, "år med chunks", int(cur.fetchone()[0]), EXPECTED_YEARS_WITH_CHUNKS)
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

        jsonl_spans = 0
        status_years = {int(item["year"]): item for item in (preflight.corpus_status.get("years") or [])}
        for year_check in preflight.year_checks:
            year = year_check.year
            year_expected = expectations_from_year_files(input_root, year)
            jsonl_spans += year_expected.span_count or 0
            cur.execute(
                """
                SELECT count(*) FROM skat.chunks
                WHERE publication_year = %s AND chunk_config_sha256 = %s
                """,
                (year, expected.chunk_config_sha256),
            )
            db_chunks = int(cur.fetchone()[0])
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
            cur.execute(
                "SELECT count(*) FROM skat.legal_documents WHERE publication_year = %s",
                (year,),
            )
            db_docs = int(cur.fetchone()[0])
            status = status_years.get(year) or {}
            _expect(result, f"{year} dokumenter", db_docs, year_check.document_count)
            _expect(result, f"{year} chunks", db_chunks, year_check.chunk_count)
            _expect(result, f"{year} referencer", db_refs, year_check.reference_count)
            if status:
                _expect(result, f"{year} manifest chunks", db_chunks, int(status["chunk_count"]))
                _expect(result, f"{year} manifest refs", db_refs, int(status["reference_count"]))
            verify_year(
                input_root,
                year,
                conn,
                corpus=expected,
                year_expected=year_expected,
                smoke=None,
                check_hashes=True,
            )

        cur.execute("SELECT count(*) FROM skat.chunk_source_spans")
        _expect(result, "chunk_source_spans", int(cur.fetchone()[0]), jsonl_spans)

    _smoke_test(conn, SMOKE_2026, result)
    if result.errors:
        raise VerifyError("corpus-verify fejlede:\n- " + "\n- ".join(result.errors))
    return result


def _lookup_columns(cur) -> dict[str, int]:
    return {col.name: index for index, col in enumerate(cur.description)}


def retrieval_check(conn) -> list[str]:
    """Eksakte opslag på tværs af år. Logger ikke chunk- eller dokumenttekst."""
    lines: list[str] = []
    with conn.cursor() as cur:
        specs = [
            ("2026", SMOKE_2026.skm_number),
        ]
        for label, low, high in (
            ("2020-2025", 2020, 2025),
            ("2010-2019", 2010, 2019),
            ("2001-2009", 2001, 2009),
        ):
            cur.execute(
                """
                SELECT d.skm_number
                FROM skat.legal_documents AS d
                WHERE d.publication_year BETWEEN %s AND %s
                  AND d.skm_number IS NOT NULL
                  AND EXISTS (
                        SELECT 1 FROM skat.chunks c
                        WHERE c.document_id = d.document_id AND c.is_final_result
                  )
                  AND EXISTS (
                        SELECT 1 FROM skat.chunks c
                        WHERE c.document_id = d.document_id
                          AND c.legal_weight = 'authoritative_reasoning'
                  )
                ORDER BY d.skm_number
                LIMIT 1
                """,
                (low, high),
            )
            row = cur.fetchone()
            if not row:
                raise VerifyError(f"ingen retrieval-kandidat i {label}")
            specs.append((label, row[0]))

        for label, skm in specs:
            lines.extend(_check_document_retrieval(cur, label, skm))

        cur.execute(
            """
            SELECT r.cited_identifier, d.publication_year, t.publication_year
            FROM skat.document_references AS r
            JOIN skat.legal_documents AS d ON d.document_id = r.source_document_id
            JOIN skat.legal_documents AS t ON t.document_id = r.target_document_id
            WHERE r.resolution_status = 'resolved'
              AND d.publication_year <> t.publication_year
            ORDER BY d.publication_year DESC, t.publication_year
            LIMIT 1
            """
        )
        chain = cur.fetchone()
        if not chain:
            raise VerifyError("ingen resolved referencekæde mellem forskellige år")
        cited, source_year, target_year = chain
        lines.append(
            f"referencekæde {cited}: {source_year} -> {target_year}"
        )
    return lines


def _check_document_retrieval(cur, label: str, skm: str) -> list[str]:
    cur.execute("SELECT * FROM skat.get_document_by_identifier(%s)", (skm,))
    doc = cur.fetchone()
    if not doc:
        raise VerifyError(f"{label}: {skm} findes ikke")
    cols = _lookup_columns(cur)
    summary = doc[cols["summary"]] or ""
    source_url = doc[cols["source_url"]]
    manual = doc[cols["manual_source_check"]]
    if not summary.strip():
        raise VerifyError(f"{label}: {skm} har tomt summary")
    if not source_url:
        raise VerifyError(f"{label}: {skm} mangler source_url")

    db_summary = summary
    cur.execute("SELECT skat.get_document_summary(%s)", (skm,))
    func_summary = cur.fetchone()[0] or ""
    if func_summary != db_summary:
        raise VerifyError(f"{label}: {skm} summary-funktionen afviger fra legal_documents.summary")

    cur.execute(
        "SELECT is_final_result, legal_weight FROM skat.get_document_final_result(%s)",
        (skm,),
    )
    finals = cur.fetchall()
    if not finals or not all(row[0] for row in finals):
        raise VerifyError(f"{label}: {skm} final_result er tom eller ikke-flagget")

    cur.execute(
        "SELECT legal_weight FROM skat.get_document_reasoning(%s)",
        (skm,),
    )
    weights = [row[0] for row in cur.fetchall()]
    if not weights or any(w != "authoritative_reasoning" for w in weights):
        raise VerifyError(f"{label}: {skm} reasoning er ikke kun authoritative_reasoning")
    if "prior_instance" in weights:
        raise VerifyError(f"{label}: {skm} reasoning indeholdt prior_instance")

    cur.execute(
        """
        SELECT count(*) FROM skat.chunks
        WHERE document_id = skat.resolve_document_id(%s)
          AND legal_weight = 'prior_instance'
        """,
        (skm,),
    )
    prior = int(cur.fetchone()[0])

    cur.execute(
        """
        SELECT direction, count(*)
        FROM skat.get_document_references(%s)
        GROUP BY direction
        """,
        (skm,),
    )
    directions = {row[0]: int(row[1]) for row in cur.fetchall()}
    return [
        f"{label} {skm}: summary={len(summary)} tegn, "
        f"source_url={'ja' if source_url else 'nej'}, "
        f"manual_source_check={manual}, "
        f"final_result={len(finals)}, reasoning={len(weights)}, "
        f"prior_instance_chunks={prior}, "
        f"outgoing={directions.get('outgoing', 0)}, incoming={directions.get('incoming', 0)}"
    ]
