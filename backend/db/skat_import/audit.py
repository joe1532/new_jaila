"""Import-auditrækker. Egen autocommit-forbindelse, så rollback af data bevares i audit."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb


def start_run(
    audit_conn,
    *,
    corpus: str,
    phase: str,
    source_manifest_sha256: str,
    chunk_config_sha256: str,
    publication_year: int | None,
    expected_document_count: int | None,
    expected_chunk_count: int | None,
    expected_reference_count: int | None,
    manifest: dict[str, Any],
) -> UUID:
    with audit_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO skat.import_runs (
                corpus, publication_year, phase,
                source_manifest_sha256, chunk_config_sha256, status,
                expected_document_count, expected_chunk_count, expected_reference_count,
                manifest
            ) VALUES (
                %s, %s, %s, %s, %s, 'running', %s, %s, %s, %s
            )
            RETURNING import_id
            """,
            (
                corpus,
                publication_year,
                phase,
                source_manifest_sha256,
                chunk_config_sha256,
                expected_document_count,
                expected_chunk_count,
                expected_reference_count,
                Jsonb(manifest),
            ),
        )
        return cur.fetchone()[0]


def finish_run(
    audit_conn,
    import_id: UUID,
    *,
    status: str,
    actual_document_count: int | None = None,
    actual_chunk_count: int | None = None,
    actual_reference_count: int | None = None,
    records_read: int = 0,
    records_inserted: int = 0,
    records_skipped: int = 0,
    error_message: str | None = None,
) -> None:
    with audit_conn.cursor() as cur:
        cur.execute(
            """
            UPDATE skat.import_runs
            SET status = %s,
                actual_document_count = %s,
                actual_chunk_count = %s,
                actual_reference_count = %s,
                records_read = %s,
                records_inserted = %s,
                records_skipped = %s,
                error_message = %s,
                completed_at = now()
            WHERE import_id = %s
            """,
            (
                status,
                actual_document_count,
                actual_chunk_count,
                actual_reference_count,
                records_read,
                records_inserted,
                records_skipped,
                error_message,
                import_id,
            ),
        )
