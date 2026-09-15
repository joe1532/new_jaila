"""Fase 3: chunks, source_spans og referencer for ét år."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from backend.db.skat_import import audit
from backend.db.skat_import.constants import CORPUS, YearExpectations
from backend.db.skat_import.errors import HashIntegrityError
from backend.db.skat_import.io import (
    ReferenceOccurrenceAssigner,
    chunks_path,
    iter_jsonl,
    jsonb,
    references_path,
    year_dir,
)
from backend.db.skat_import.mapping import (
    CHUNK_COLUMNS,
    chunk_row,
    reference_row,
    span_rows,
)
from backend.db.skat_import.preflight import load_json
from backend.db.skat_import.year_expect import expectations_from_year_files


INSERT_CHUNKS_SQL = f"""
INSERT INTO skat.chunks ({CHUNK_COLUMNS})
VALUES ({", ".join(["%s"] * 40)})
"""

INSERT_SPANS_SQL = """
INSERT INTO skat.chunk_source_spans (
    chunk_id, span_index, source, start_offset, end_offset, role
) VALUES (%s, %s, %s, %s, %s, %s)
"""

INSERT_REFS_SQL = """
INSERT INTO skat.document_references (
    reference_id, reference_key, source_document_id, source_chunk_id,
    reference_type, cited_identifier, exact_reference_text,
    target_document_id, target_url, resolution_status,
    canonical_reference_sha256, occurrence_index, original_target_document_id,
    raw_record, cited_law_key, cited_section_number, cited_section_suffix,
    cited_section_end_number, cited_section_end_suffix, cited_subsection,
    cited_item_number, cited_letter
) VALUES (
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s, %s, %s
)
"""


@dataclass
class YearProgress:
    chunks_read: int = 0
    chunks_inserted: int = 0
    chunks_skipped: int = 0
    spans_inserted: int = 0
    spans_skipped: int = 0
    references_read: int = 0
    references_inserted: int = 0
    references_skipped: int = 0


def import_year(
    input_root: Path,
    year: int,
    work_conn,
    audit_conn,
    *,
    expectations: YearExpectations | None = None,
    batch_size: int = 1000,
    pre_commit_verify: Callable[[object], None] | None = None,
) -> YearProgress:
    folder = year_dir(input_root, year)
    manifest = load_json(folder / "manifest.json")
    expected = expectations or expectations_from_year_files(input_root, year)
    if year != expected.year:
        raise HashIntegrityError(f"år {year} matcher ikke forventningerne for {expected.year}")
    source_sha = manifest["source_manifest_sha256"]
    config_sha = manifest["chunk_config_sha256"]
    import_id = audit.start_run(
        audit_conn,
        corpus=CORPUS,
        phase="year",
        source_manifest_sha256=source_sha,
        chunk_config_sha256=config_sha,
        publication_year=year,
        expected_document_count=expected.document_count,
        expected_chunk_count=expected.chunk_count,
        expected_reference_count=expected.reference_count,
        manifest=manifest,
    )
    progress = YearProgress()
    try:
        chunk_run_id = _ensure_chunk_run(work_conn, manifest)
        _import_chunks(input_root, year, work_conn, chunk_run_id, batch_size, progress)
        _import_spans(input_root, year, work_conn, batch_size, progress)
        known_ids = _document_ids(work_conn)
        _import_references(input_root, year, work_conn, batch_size, progress, known_ids)
        actual_docs = _count_year_documents(work_conn, year)
        actual_chunks = _count_year_chunks(work_conn, year, config_sha)
        actual_refs = _count_year_references(work_conn, year)
        actual_spans = _count_year_spans(work_conn, year, config_sha)
        if actual_chunks != expected.chunk_count:
            raise HashIntegrityError(
                f"{year}: chunks i db={actual_chunks}, forventet {expected.chunk_count}"
            )
        if expected.span_count is not None and actual_spans != expected.span_count:
            raise HashIntegrityError(
                f"{year}: spans i db={actual_spans}, forventet {expected.span_count}"
            )
        if progress.references_read != expected.reference_count:
            raise HashIntegrityError(
                f"{year}: referencelinjer læst={progress.references_read}, "
                f"forventet {expected.reference_count}"
            )
        if actual_refs != expected.reference_count:
            raise HashIntegrityError(
                f"{year}: referencer i db={actual_refs}, forventet {expected.reference_count}"
            )
        if (
            progress.references_inserted + progress.references_skipped
            != progress.references_read
        ):
            raise HashIntegrityError(
                f"{year}: referencer indsat+sprunget_over "
                f"{progress.references_inserted + progress.references_skipped} "
                f"matcher ikke læst {progress.references_read}"
            )
        _upsert_year_manifest(work_conn, year, chunk_run_id, manifest, expected)
        if pre_commit_verify is not None:
            pre_commit_verify(work_conn)
        work_conn.commit()
        audit.finish_run(
            audit_conn,
            import_id,
            status="complete",
            actual_document_count=actual_docs,
            actual_chunk_count=actual_chunks,
            actual_reference_count=actual_refs,
            records_read=progress.chunks_read + progress.references_read,
            records_inserted=(
                progress.chunks_inserted
                + progress.spans_inserted
                + progress.references_inserted
            ),
            records_skipped=(
                progress.chunks_skipped
                + progress.spans_skipped
                + progress.references_skipped
            ),
        )
        print(
            f"år {year}: chunks indsat={progress.chunks_inserted} "
            f"sprunget_over={progress.chunks_skipped} "
            f"spans_indsat={progress.spans_inserted} "
            f"refs_indsat={progress.references_inserted} "
            f"refs_sprunget_over={progress.references_skipped}",
            flush=True,
        )
        return progress
    except Exception as exc:
        work_conn.rollback()
        audit.finish_run(
            audit_conn,
            import_id,
            status="failed",
            records_read=progress.chunks_read + progress.references_read,
            records_inserted=(
                progress.chunks_inserted
                + progress.spans_inserted
                + progress.references_inserted
            ),
            records_skipped=(
                progress.chunks_skipped
                + progress.spans_skipped
                + progress.references_skipped
            ),
            error_message=str(exc),
        )
        raise


def _ensure_chunk_run(conn, manifest: dict):
    config = manifest.get("chunk_config") or {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT chunk_run_id
            FROM skat.chunk_runs
            WHERE chunk_config_sha256 = %s AND source_manifest_sha256 = %s
            """,
            (manifest["chunk_config_sha256"], manifest["source_manifest_sha256"]),
        )
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute(
            """
            INSERT INTO skat.chunk_runs (
                chunker_name, chunker_version, chunk_config_sha256, schema_version,
                source_manifest_sha256, tokenizer_model, tokenizer_encoding,
                target_tokens, hard_max_tokens, overlap_tokens, config
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING chunk_run_id
            """,
            (
                config.get("chunker_name") or "skat-skm-structural",
                manifest["chunker_version"],
                manifest["chunk_config_sha256"],
                manifest["schema_version"],
                manifest["source_manifest_sha256"],
                config.get("tokenizer_model") or "text-embedding-3-large",
                manifest.get("tokenizer_encoding") or "cl100k_base",
                int(config.get("target_tokens") or 800),
                int(config.get("hard_max_tokens") or 1000),
                int(config.get("overlap_tokens") or 100),
                jsonb(config),
            ),
        )
        return cur.fetchone()[0]


def _import_chunks(input_root, year, conn, chunk_run_id, batch_size, progress: YearProgress) -> None:
    batch: list[dict] = []
    for record in iter_jsonl(chunks_path(input_root, year)):
        batch.append(record)
        if len(batch) >= batch_size:
            _flush_chunks(conn, batch, chunk_run_id, progress, year=year)
            batch.clear()
    if batch:
        _flush_chunks(conn, batch, chunk_run_id, progress, year=year)


def _flush_chunks(conn, records: list[dict], chunk_run_id, progress: YearProgress, *, year: int) -> None:
    progress.chunks_read += len(records)
    ids = [r["chunk_id"] for r in records]
    triples = [
        (r["document_id"], r["chunk_index"], r["chunk_config_sha256"]) for r in records
    ]
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT chunk_id, text_sha256, embedding_text_sha256,
                   document_id, chunk_index, chunk_config_sha256
            FROM skat.chunks
            WHERE chunk_id = ANY(%s)
               OR (document_id, chunk_index, chunk_config_sha256) IN (
                    SELECT x.document_id, x.chunk_index, x.chunk_config_sha256
                    FROM unnest(%s::text[], %s::int[], %s::text[])
                         AS x(document_id, chunk_index, chunk_config_sha256)
               )
            """,
            (
                ids,
                [t[0] for t in triples],
                [t[1] for t in triples],
                [t[2] for t in triples],
            ),
        )
        by_id = {}
        by_triple = {}
        for row in cur.fetchall():
            chunk_id, text_sha, embed_sha, document_id, chunk_index, config_sha = row
            by_id[chunk_id] = (text_sha, embed_sha, document_id, chunk_index, config_sha)
            by_triple[(document_id, chunk_index, config_sha)] = chunk_id

        to_insert = []
        for record in records:
            chunk_id = record["chunk_id"]
            triple = (record["document_id"], record["chunk_index"], record["chunk_config_sha256"])
            existing = by_id.get(chunk_id)
            other = by_triple.get(triple)
            if existing:
                text_sha, embed_sha, *_rest = existing
                if text_sha != record["text_sha256"] or embed_sha != record["embedding_text_sha256"]:
                    raise HashIntegrityError(
                        f"chunk_id {chunk_id} findes med afvigende text/embedding-hash"
                    )
                progress.chunks_skipped += 1
                continue
            if other and other != chunk_id:
                raise HashIntegrityError(
                    f"chunk-indeks {triple} er optaget af {other}, JSONL har {chunk_id}"
                )
            to_insert.append(chunk_row(record, chunk_run_id, publication_year=year))
            by_id[chunk_id] = (
                record["text_sha256"],
                record["embedding_text_sha256"],
                record["document_id"],
                record["chunk_index"],
                record["chunk_config_sha256"],
            )
            by_triple[triple] = chunk_id
            progress.chunks_inserted += 1
        if to_insert:
            cur.executemany(INSERT_CHUNKS_SQL, to_insert)
        print(
            f"  chunks læst={progress.chunks_read} indsat={progress.chunks_inserted} "
            f"sprunget_over={progress.chunks_skipped}",
            flush=True,
        )


def _import_spans(input_root, year, conn, batch_size, progress: YearProgress) -> None:
    batch: list[tuple] = []
    for record in iter_jsonl(chunks_path(input_root, year)):
        batch.extend(span_rows(record))
        if len(batch) >= batch_size:
            _flush_spans(conn, batch, progress)
            batch.clear()
    if batch:
        _flush_spans(conn, batch, progress)


def _flush_spans(conn, rows: list[tuple], progress: YearProgress) -> None:
    chunk_ids = list({row[0] for row in rows})
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT chunk_id, span_index, source, start_offset, end_offset, role
            FROM skat.chunk_source_spans
            WHERE chunk_id = ANY(%s)
            """,
            (chunk_ids,),
        )
        existing = {
            (chunk_id, span_index): (source, start, end, role)
            for chunk_id, span_index, source, start, end, role in cur.fetchall()
        }
        to_insert = []
        for row in rows:
            key = (row[0], row[1])
            found = existing.get(key)
            if found:
                if found != (row[2], row[3], row[4], row[5]):
                    raise HashIntegrityError(
                        f"source_span {key} findes med andet indhold"
                    )
                progress.spans_skipped += 1
            else:
                to_insert.append(row)
                existing[key] = (row[2], row[3], row[4], row[5])
                progress.spans_inserted += 1
        if to_insert:
            cur.executemany(INSERT_SPANS_SQL, to_insert)


def _import_references(input_root, year, conn, batch_size, progress: YearProgress, known_document_ids: set[str]) -> None:
    assigner = ReferenceOccurrenceAssigner()
    batch: list[tuple] = []
    for record in iter_jsonl(references_path(input_root, year)):
        canonical, index, key = assigner.assign(record)
        batch.append(
            reference_row(
                record,
                canonical_sha=canonical,
                occurrence_index=index,
                reference_key=key,
                known_document_ids=known_document_ids,
            )
        )
        progress.references_read += 1
        if len(batch) >= batch_size:
            _flush_references(conn, batch, progress)
            batch.clear()
    if batch:
        _flush_references(conn, batch, progress)


def _flush_references(conn, rows: list[tuple], progress: YearProgress) -> None:
    keys = [row[1] for row in rows]
    ids = [row[0] for row in rows]
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT reference_id::text, reference_key
            FROM skat.document_references
            WHERE reference_key = ANY(%s) OR reference_id = ANY(%s::uuid[])
            """,
            (keys, ids),
        )
        by_key = {}
        by_id = {}
        for reference_id, reference_key in cur.fetchall():
            by_key[reference_key] = reference_id
            by_id[reference_id] = reference_key
        to_insert = []
        for row in rows:
            ref_id, key = row[0], row[1]
            if key in by_key:
                progress.references_skipped += 1
                continue
            if ref_id in by_id and by_id[ref_id] != key:
                raise HashIntegrityError(
                    f"reference_id {ref_id} findes med anden reference_key"
                )
            to_insert.append(row)
            by_key[key] = ref_id
            by_id[ref_id] = key
            progress.references_inserted += 1
        if to_insert:
            cur.executemany(INSERT_REFS_SQL, to_insert)
        print(
            f"  referencer læst={progress.references_read} "
            f"indsat={progress.references_inserted} "
            f"sprunget_over={progress.references_skipped}",
            flush=True,
        )


def _upsert_year_manifest(conn, year, chunk_run_id, manifest, expected: YearExpectations) -> None:
    jsonl = manifest.get("jsonl") or {}
    chunk_sha = (jsonl.get("chunks") or {}).get("sha256")
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT document_count, chunk_count, reference_count, validation_status
            FROM skat.ingest_year_manifests
            WHERE ingest_year = %s
              AND chunk_config_sha256 = %s
              AND source_manifest_sha256 = %s
            """,
            (year, manifest["chunk_config_sha256"], manifest["source_manifest_sha256"]),
        )
        existing = cur.fetchone()
        if existing:
            if existing != (
                expected.document_count,
                expected.chunk_count,
                expected.reference_count,
                "pass",
            ):
                raise HashIntegrityError(
                    f"{year}: ingest_year_manifests afviger fra forventede tællinger"
                )
            return
        cur.execute(
            """
            INSERT INTO skat.ingest_year_manifests (
                ingest_year, chunk_run_id, source_manifest_sha256, chunk_config_sha256,
                document_count, chunk_count, reference_count, validation_status,
                chunk_sha256, raw_manifest
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'pass', %s, %s)
            """,
            (
                year,
                chunk_run_id,
                manifest["source_manifest_sha256"],
                manifest["chunk_config_sha256"],
                expected.document_count,
                expected.chunk_count,
                expected.reference_count,
                chunk_sha,
                jsonb(manifest),
            ),
        )


def _document_ids(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT document_id FROM skat.legal_documents")
        return {row[0] for row in cur.fetchall()}


def _count_year_documents(conn, year: int) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM skat.legal_documents WHERE publication_year = %s",
            (year,),
        )
        return int(cur.fetchone()[0])


def _count_year_chunks(conn, year: int, config_sha: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM skat.chunks
            WHERE publication_year = %s AND chunk_config_sha256 = %s
            """,
            (year, config_sha),
        )
        return int(cur.fetchone()[0])


def _count_year_references(conn, year: int) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
            FROM skat.document_references AS r
            JOIN skat.legal_documents AS d ON d.document_id = r.source_document_id
            WHERE d.publication_year = %s
            """,
            (year,),
        )
        return int(cur.fetchone()[0])


def _count_year_spans(conn, year: int, config_sha: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
            FROM skat.chunk_source_spans AS s
            JOIN skat.chunks AS c ON c.chunk_id = s.chunk_id
            WHERE c.publication_year = %s AND c.chunk_config_sha256 = %s
            """,
            (year, config_sha),
        )
        return int(cur.fetchone()[0])
