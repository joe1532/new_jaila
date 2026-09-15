"""Fase 2: dokumentindeks for hele korpusset."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.db.skat_import import audit
from backend.db.skat_import.constants import CORPUS, CorpusExpectations, PRODUCTION_EXPECTATIONS
from backend.db.skat_import.errors import HashIntegrityError
from backend.db.skat_import.io import documents_path, iter_jsonl
from backend.db.skat_import.mapping import DOCUMENT_COLUMNS, document_row, version_row
from backend.db.skat_import.preflight import PreflightResult, run_preflight


INSERT_DOCUMENTS_SQL = f"""
INSERT INTO skat.legal_documents ({DOCUMENT_COLUMNS})
VALUES ({", ".join(["%s"] * 31)})
"""

INSERT_VERSIONS_SQL = """
INSERT INTO skat.document_versions (
    document_id, content_sha256, schema_version, source_manifest_sha256,
    source_path, metadata_path, raw_record
) VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (document_id, content_sha256) DO NOTHING
"""


@dataclass
class Progress:
    read: int = 0
    inserted: int = 0
    skipped: int = 0


def import_documents(
    input_root: Path,
    work_conn,
    audit_conn,
    *,
    expected: CorpusExpectations = PRODUCTION_EXPECTATIONS,
    batch_size: int = 1000,
    preflight: PreflightResult | None = None,
) -> Progress:
    result = preflight or run_preflight(input_root, expected)
    manifest_sha = expected.source_manifest_sha256
    import_id = audit.start_run(
        audit_conn,
        corpus=CORPUS,
        phase="documents",
        source_manifest_sha256=manifest_sha,
        chunk_config_sha256=expected.chunk_config_sha256,
        publication_year=None,
        expected_document_count=expected.document_count,
        expected_chunk_count=None,
        expected_reference_count=None,
        manifest={"completed_years": result.years},
    )
    total = Progress()
    try:
        for year in result.years:
            year_progress = _import_year_documents(
                input_root,
                year,
                work_conn,
                source_manifest_sha256=manifest_sha,
                batch_size=batch_size,
            )
            work_conn.commit()
            total.read += year_progress.read
            total.inserted += year_progress.inserted
            total.skipped += year_progress.skipped
            print(
                f"dokumenter {year}: læst={year_progress.read} "
                f"indsat={year_progress.inserted} sprunget_over={year_progress.skipped}",
                flush=True,
            )
        actual = _count_documents(work_conn, manifest_sha)
        if actual != expected.document_count:
            raise HashIntegrityError(
                f"legal_documents har {actual} rækker for dette manifest, "
                f"forventet {expected.document_count}"
            )
        work_conn.commit()
        audit.finish_run(
            audit_conn,
            import_id,
            status="complete",
            actual_document_count=actual,
            records_read=total.read,
            records_inserted=total.inserted,
            records_skipped=total.skipped,
        )
        return total
    except Exception as exc:
        work_conn.rollback()
        audit.finish_run(
            audit_conn,
            import_id,
            status="failed",
            records_read=total.read,
            records_inserted=total.inserted,
            records_skipped=total.skipped,
            error_message=str(exc),
        )
        raise


def _count_documents(conn, source_manifest_sha256: str) -> int:
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
            (source_manifest_sha256,),
        )
        return int(cur.fetchone()[0])


def _import_year_documents(
    input_root: Path,
    year: int,
    conn,
    *,
    source_manifest_sha256: str,
    batch_size: int,
) -> Progress:
    path = documents_path(input_root, year)
    source_path = f"{year}/documents/{year}.jsonl"
    progress = Progress()
    batch: list[dict] = []
    for record in iter_jsonl(path):
        batch.append(record)
        if len(batch) >= batch_size:
            _flush_documents(conn, batch, source_manifest_sha256, source_path, progress, year=year)
            batch.clear()
    if batch:
        _flush_documents(conn, batch, source_manifest_sha256, source_path, progress, year=year)
    return progress


def _flush_documents(
    conn,
    records: list[dict],
    source_manifest_sha256: str,
    source_path: str,
    progress: Progress,
    *,
    year: int,
) -> None:
    progress.read += len(records)
    ids = [r["document_id"] for r in records]
    oids = [r["source_oid"] for r in records]
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT document_id, source_oid, content_sha256
            FROM skat.legal_documents
            WHERE document_id = ANY(%s) OR source_oid = ANY(%s)
            """,
            (ids, oids),
        )
        by_id = {}
        by_oid = {}
        for document_id, source_oid, content_sha256 in cur.fetchall():
            by_id[document_id] = (source_oid, content_sha256)
            by_oid[source_oid] = (document_id, content_sha256)

        to_insert = []
        versions = []
        for record in records:
            document_id = record["document_id"]
            source_oid = record["source_oid"]
            content_sha256 = record["content_sha256"]
            existing_id = by_id.get(document_id)
            existing_oid = by_oid.get(source_oid)
            if existing_id:
                existing_oid_value, existing_sha = existing_id
                if existing_sha != content_sha256:
                    raise HashIntegrityError(
                        f"document_id {document_id} findes allerede med andet content_sha256"
                    )
                if existing_oid_value != source_oid:
                    raise HashIntegrityError(
                        f"document_id {document_id} har source_oid {existing_oid_value}, "
                        f"JSONL har {source_oid}"
                    )
                progress.skipped += 1
            elif existing_oid:
                existing_document_id, existing_sha = existing_oid
                raise HashIntegrityError(
                    f"source_oid {source_oid} tilhører {existing_document_id} "
                    f"(sha={existing_sha[:12]}…), JSONL vil indsætte {document_id}"
                )
            else:
                to_insert.append(document_row(record, publication_year=year))
                by_id[document_id] = (source_oid, content_sha256)
                by_oid[source_oid] = (document_id, content_sha256)
                progress.inserted += 1
            versions.append(version_row(record, source_manifest_sha256=source_manifest_sha256, source_path=source_path))

        if to_insert:
            cur.executemany(INSERT_DOCUMENTS_SQL, to_insert)
        cur.executemany(INSERT_VERSIONS_SQL, versions)
