"""Audit for embedding-kørsler. Logger chunk-id'er, tokens og status. Aldrig tekst eller API-nøgle."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from backend.db.skat_embed.keys import redact_secrets


def start_run(
    conn,
    *,
    phase: str,
    selection_key: str,
    embedding_model_id: UUID | None,
    expected_count: int | None,
    manifest: dict[str, Any],
) -> UUID:
    status = "dry_run" if phase == "dry_run" else "running"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO skat.embedding_runs (
                phase, selection_key, embedding_model_id, status,
                expected_count, manifest
            ) VALUES (
                %s, %s, %s, %s, %s, %s
            )
            RETURNING embedding_run_id
            """,
            (
                phase,
                selection_key,
                embedding_model_id,
                status,
                expected_count,
                Jsonb(manifest),
            ),
        )
        return cur.fetchone()[0]


def finish_run(
    conn,
    run_id: UUID,
    *,
    status: str,
    inserted_count: int = 0,
    skipped_count: int = 0,
    failed_count: int = 0,
    prompt_tokens: int = 0,
    total_tokens: int = 0,
    error_message: str | None = None,
) -> None:
    message = redact_secrets(error_message) if error_message else None
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE skat.embedding_runs
            SET status = %s,
                inserted_count = %s,
                skipped_count = %s,
                failed_count = %s,
                prompt_tokens = %s,
                total_tokens = %s,
                error_message = %s,
                completed_at = now()
            WHERE embedding_run_id = %s
            """,
            (
                status,
                inserted_count,
                skipped_count,
                failed_count,
                prompt_tokens,
                total_tokens,
                message,
                run_id,
            ),
        )


def add_tokens(conn, run_id: UUID, *, prompt_tokens: int, total_tokens: int, inserted: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE skat.embedding_runs
            SET prompt_tokens = prompt_tokens + %s,
                total_tokens = total_tokens + %s,
                inserted_count = inserted_count + %s
            WHERE embedding_run_id = %s
            """,
            (prompt_tokens, total_tokens, inserted, run_id),
        )


def log_request(
    conn,
    *,
    run_id: UUID,
    attempt: int,
    chunk_ids: list[str],
    model_name: str,
    dimensions: int,
    input_count: int,
    token_count: int | None,
    openai_request_id: str | None,
    http_status: int | None,
    error_code: str | None,
    error_message: str | None,
    completed: bool,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO skat.embedding_requests (
                embedding_run_id, attempt, chunk_ids, openai_request_id,
                model_name, dimensions, input_count, token_count,
                http_status, error_code, error_message, completed_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                CASE WHEN %s THEN now() ELSE NULL END
            )
            """,
            (
                run_id,
                attempt,
                chunk_ids,
                openai_request_id,
                model_name,
                dimensions,
                input_count,
                token_count,
                http_status,
                error_code,
                redact_secrets(error_message) if error_message else None,
                completed,
            ),
        )
