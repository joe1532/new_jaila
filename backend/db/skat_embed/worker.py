"""Genoptagelig embedding af chunks.embedding_text. Ingen HNSW. Ingen dokumenttekst i logs."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Callable
from uuid import UUID

from backend.db.skat_embed.audit import add_tokens, finish_run, log_request, start_run
from backend.db.skat_embed.client import (
    BatchItem,
    EmbeddingsAPI,
    embed_texts,
    split_batches,
)
from backend.db.skat_embed.constants import (
    CORPUS_SELECTION_KEY,
    DEFAULT_BATCH_INPUTS,
    DEFAULT_BATCH_TOKENS,
    DIMENSIONS,
    MODEL_NAME,
    PILOT_SELECTION_KEY,
    PILOT_SIZE,
)
from backend.db.skat_embed.errors import (
    FullCorpusNotApprovedError,
    IntegrityError,
    SkatEmbedError,
)
from backend.db.skat_embed.keys import redact_secrets
from backend.db.skat_embed.model import ensure_embedding_model
from backend.db.skat_embed.select import coverage_report, select_pilot_chunks
from backend.db.skat_embed.vectors import pgvector_literal


@dataclass
class ChunkWork:
    chunk_id: str
    embedding_text: str
    token_count: int
    text_sha256: str


@dataclass
class EmbedStats:
    selected: int = 0
    pending: int = 0
    inserted: int = 0
    skipped: int = 0
    failed: int = 0
    prompt_tokens: int = 0
    total_tokens: int = 0
    api_requests: int = 0
    retries: int = 0
    duration_s: float = 0.0
    run_id: UUID | None = None
    coverage: dict | None = None


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _existing_model_id(conn) -> UUID | None:
    from backend.db.skat_embed.constants import DIMENSIONS, MODEL_NAME, PROVIDER

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT embedding_model_id
            FROM skat.embedding_models
            WHERE provider = %s AND model_name = %s AND dimensions = %s
              AND model_revision IS NULL
            """,
            (PROVIDER, MODEL_NAME, DIMENSIONS),
        )
        row = cur.fetchone()
    return row[0] if row else None


def _load_work(conn, chunk_ids: list[str]) -> list[ChunkWork]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT chunk_id, embedding_text, token_count, embedding_text_sha256
            FROM skat.chunks
            WHERE chunk_id = ANY(%s)
            ORDER BY chunk_id
            """,
            (chunk_ids,),
        )
        rows = cur.fetchall()
    found = {row[0] for row in rows}
    missing = [chunk_id for chunk_id in chunk_ids if chunk_id not in found]
    if missing:
        raise SkatEmbedError(f"mangler {len(missing)} chunks i skat.chunks")
    work = []
    for chunk_id, embedding_text, token_count, stored_sha in rows:
        computed = _sha256_text(embedding_text)
        if computed != stored_sha:
            raise IntegrityError(
                f"chunks.embedding_text_sha256 afviger for {chunk_id}"
            )
        work.append(
            ChunkWork(
                chunk_id=chunk_id,
                embedding_text=embedding_text,
                token_count=int(token_count),
                text_sha256=computed,
            )
        )
    return work


def classify_chunks(conn, model_id: UUID, work: list[ChunkWork]) -> tuple[list[ChunkWork], int]:
    """Returnér pending chunks og antal skips. Afvigende hash er integritetsfejl."""
    pending: list[ChunkWork] = []
    skipped = 0
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT chunk_id, embedding_text_sha256
            FROM skat.chunk_embeddings
            WHERE embedding_model_id = %s
              AND chunk_id = ANY(%s)
            """,
            (model_id, [item.chunk_id for item in work]),
        )
        existing = {row[0]: row[1] for row in cur.fetchall()}
    for item in work:
        stored = existing.get(item.chunk_id)
        if stored is None:
            pending.append(item)
            continue
        if stored == item.text_sha256:
            skipped += 1
            continue
        raise IntegrityError(
            f"eksisterende embedding med afvigende hash for {item.chunk_id}"
        )
    return pending, skipped


def _insert_embedding(conn, model_id: UUID, chunk_id: str, vector: list[float], text_sha: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO skat.chunk_embeddings (
                chunk_id, embedding_model_id, embedding, embedding_text_sha256
            ) VALUES (
                %s, %s, %s::vector, %s
            )
            """,
            (chunk_id, model_id, pgvector_literal(vector), text_sha),
        )


def embed_chunk_ids(
    conn,
    chunk_ids: list[str],
    *,
    phase: str,
    selection_key: str,
    dry_run: bool = False,
    client: EmbeddingsAPI | None = None,
    max_inputs: int = DEFAULT_BATCH_INPUTS,
    max_tokens: int = DEFAULT_BATCH_TOKENS,
    log: Callable[[str], None] | None = print,
    coverage: dict | None = None,
) -> EmbedStats:
    stats = EmbedStats(selected=len(chunk_ids), coverage=coverage)
    if dry_run:
        model_id = _existing_model_id(conn)
    else:
        model_id = ensure_embedding_model(conn)
    work = _load_work(conn, chunk_ids)
    if model_id:
        pending, skipped = classify_chunks(conn, model_id, work)
    else:
        pending, skipped = work, 0
    stats.pending = len(pending)
    stats.skipped = skipped
    manifest = {
        "selection_key": selection_key,
        "chunk_count": len(chunk_ids),
        "pending": len(pending),
        "skipped": skipped,
        "coverage": coverage or {},
        "model": MODEL_NAME,
        "dimensions": DIMENSIONS,
    }
    run_id = start_run(
        conn,
        phase="dry_run" if dry_run else phase,
        selection_key=selection_key,
        embedding_model_id=model_id,
        expected_count=len(chunk_ids),
        manifest=manifest,
    )
    stats.run_id = run_id
    _log = log or (lambda _msg: None)
    _log(
        f"selection={selection_key} valgt={stats.selected} "
        f"pending={stats.pending} skip={stats.skipped}"
    )
    if dry_run:
        finish_run(
            conn,
            run_id,
            status="dry_run",
            inserted_count=0,
            skipped_count=skipped if model_id else 0,
            failed_count=0,
        )
        _log("dry-run: ingen API-kald og ingen embedding-inserts")
        return stats

    batches = split_batches(
        [
            BatchItem(item.chunk_id, item.embedding_text, item.token_count)
            for item in pending
        ],
        max_inputs=max_inputs,
        max_tokens=max_tokens,
    )
    by_id = {item.chunk_id: item for item in pending}
    try:
        for batch_no, batch in enumerate(batches, start=1):
            ids = [item.item_id for item in batch]
            texts = [item.text for item in batch]
            budget = sum(max(1, item.token_count) for item in batch)
            _log(
                f"batch {batch_no}/{len(batches)} inputs={len(ids)} tokenbudget={budget}"
            )
            try:
                result = embed_texts(texts, client=client)
            except Exception as exc:
                log_request(
                    conn,
                    run_id=run_id,
                    attempt=1,
                    chunk_ids=ids,
                    model_name=MODEL_NAME,
                    dimensions=DIMENSIONS,
                    input_count=len(ids),
                    token_count=budget,
                    openai_request_id=None,
                    http_status=getattr(exc, "status_code", None),
                    error_code=type(exc).__name__,
                    error_message=redact_secrets(str(exc)),
                    completed=True,
                )
                raise
            log_request(
                conn,
                run_id=run_id,
                attempt=1,
                chunk_ids=ids,
                model_name=result.model,
                dimensions=DIMENSIONS,
                input_count=len(ids),
                token_count=result.total_tokens,
                openai_request_id=result.request_id,
                http_status=result.http_status,
                error_code=None,
                error_message=None,
                completed=True,
            )
            if len(result.embeddings) != len(ids):
                raise SkatEmbedError("API-rækkefølge afviger fra inputantal")
            for chunk_id, vector in zip(ids, result.embeddings):
                _insert_embedding(
                    conn, model_id, chunk_id, vector, by_id[chunk_id].text_sha256
                )
            stats.inserted += len(ids)
            stats.prompt_tokens += result.prompt_tokens
            stats.total_tokens += result.total_tokens
            stats.api_requests += 1
            stats.retries += max(0, result.attempts - 1)
            add_tokens(
                conn,
                run_id,
                prompt_tokens=result.prompt_tokens,
                total_tokens=result.total_tokens,
                inserted=len(ids),
            )
            _log(
                f"færdig chunks={stats.inserted} "
                f"skip={stats.skipped} "
                f"prompt_tokens={stats.prompt_tokens} "
                f"total_tokens={stats.total_tokens}"
            )
        finish_run(
            conn,
            run_id,
            status="complete",
            inserted_count=stats.inserted,
            skipped_count=stats.skipped,
            failed_count=stats.failed,
            prompt_tokens=stats.prompt_tokens,
            total_tokens=stats.total_tokens,
        )
    except Exception as exc:
        stats.failed = stats.pending - stats.inserted
        finish_run(
            conn,
            run_id,
            status="failed",
            inserted_count=stats.inserted,
            skipped_count=stats.skipped,
            failed_count=stats.failed,
            prompt_tokens=stats.prompt_tokens,
            total_tokens=stats.total_tokens,
            error_message=redact_secrets(str(exc)),
        )
        raise
    return stats


def run_pilot(
    conn,
    *,
    dry_run: bool = False,
    client: EmbeddingsAPI | None = None,
    size: int = PILOT_SIZE,
) -> EmbedStats:
    selected = select_pilot_chunks(conn, size=size)
    coverage = coverage_report(selected, conn)
    if coverage["missing_section_types"] or coverage["missing_legal_weights"]:
        raise SkatEmbedError(
            "pilot dækker ikke alle section_type/legal_weight: "
            f"{coverage['missing_section_types']} {coverage['missing_legal_weights']}"
        )
    for label, count in coverage["decades"].items():
        if count < 1:
            raise SkatEmbedError(f"pilot mangler årti {label}")
    if coverage["final_result"] < 1:
        raise SkatEmbedError("pilot mangler resultatchunks")
    if coverage["authoritative_reasoning"] < 1:
        raise SkatEmbedError("pilot mangler begrundelser")
    if coverage["summary"] < 1:
        raise SkatEmbedError("pilot mangler resuméer")
    if coverage["manual_source_check"] < 1:
        raise SkatEmbedError("pilot mangler manual_source_check")
    return embed_chunk_ids(
        conn,
        [item.chunk_id for item in selected],
        phase="pilot",
        selection_key=PILOT_SELECTION_KEY,
        dry_run=dry_run,
        client=client,
        coverage=coverage,
    )


def _fetch_pending_page(conn, model_id: UUID, after_id: str | None, limit: int) -> list[ChunkWork]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.chunk_id, c.embedding_text, c.token_count, c.embedding_text_sha256
            FROM skat.chunks AS c
            WHERE NOT EXISTS (
                SELECT 1
                FROM skat.chunk_embeddings AS e
                WHERE e.chunk_id = c.chunk_id
                  AND e.embedding_model_id = %s
            )
              AND (%s::text IS NULL OR c.chunk_id > %s)
            ORDER BY c.chunk_id
            LIMIT %s
            """,
            (model_id, after_id, after_id, limit),
        )
        rows = cur.fetchall()
    work = []
    for chunk_id, embedding_text, token_count, stored_sha in rows:
        computed = _sha256_text(embedding_text)
        if computed != stored_sha:
            raise IntegrityError(f"chunks.embedding_text_sha256 afviger for {chunk_id}")
        work.append(
            ChunkWork(
                chunk_id=chunk_id,
                embedding_text=embedding_text,
                token_count=int(token_count),
                text_sha256=computed,
            )
        )
    return work


def _insert_batch(conn, model_id: UUID, rows: list[tuple[str, list[float], str]]) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO skat.chunk_embeddings (
                chunk_id, embedding_model_id, embedding, embedding_text_sha256
            ) VALUES (
                %s, %s, %s::vector, %s
            )
            """,
            [
                (chunk_id, model_id, pgvector_literal(vector), text_sha)
                for chunk_id, vector, text_sha in rows
            ],
        )


def pending_counts(conn, model_id: UUID) -> tuple[int, int, int]:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM skat.chunks")
        chunks = int(cur.fetchone()[0])
        cur.execute(
            """
            SELECT count(*)
            FROM skat.chunk_embeddings
            WHERE embedding_model_id = %s
            """,
            (model_id,),
        )
        existing = int(cur.fetchone()[0])
        cur.execute(
            """
            SELECT count(*)
            FROM skat.chunks AS c
            JOIN skat.chunk_embeddings AS e
              ON e.chunk_id = c.chunk_id
             AND e.embedding_model_id = %s
            WHERE e.embedding_text_sha256 <> c.embedding_text_sha256
            """,
            (model_id,),
        )
        conflicts = int(cur.fetchone()[0])
    if conflicts:
        raise IntegrityError(f"{conflicts} eksisterende embeddings med afvigende hash")
    return chunks, existing, chunks - existing


def embed_pending(
    conn,
    *,
    phase: str,
    selection_key: str,
    dry_run: bool = False,
    client: EmbeddingsAPI | None = None,
    max_inputs: int = DEFAULT_BATCH_INPUTS,
    max_tokens: int = DEFAULT_BATCH_TOKENS,
    log: Callable[[str], None] | None = print,
) -> EmbedStats:
    """Embed kun manglende chunks. Genbruger embedding_models. Ingen fuld tekstload."""
    started = time.monotonic()
    model_id = _existing_model_id(conn)
    if model_id is None:
        if dry_run:
            raise SkatEmbedError("ingen embedding_models-række at genbruge")
        raise SkatEmbedError("ingen embedding_models-række fra piloten")
    chunks, existing, pending = pending_counts(conn, model_id)
    stats = EmbedStats(selected=chunks, pending=pending, skipped=existing)
    run_id = start_run(
        conn,
        phase="dry_run" if dry_run else phase,
        selection_key=selection_key,
        embedding_model_id=model_id,
        expected_count=chunks,
        manifest={
            "chunks": chunks,
            "existing": existing,
            "pending": pending,
            "model": MODEL_NAME,
            "dimensions": DIMENSIONS,
            "reuse_embedding_model_id": str(model_id),
        },
    )
    stats.run_id = run_id
    _log = log or (lambda _msg: None)
    _log(f"selection={selection_key} valgt={chunks} pending={pending} skip={existing}")
    if dry_run or pending == 0:
        finish_run(
            conn,
            run_id,
            status="dry_run" if dry_run else "complete",
            inserted_count=0,
            skipped_count=existing,
        )
        stats.duration_s = time.monotonic() - started
        if dry_run:
            _log("dry-run: ingen API-kald og ingen embedding-inserts")
        else:
            _log("ingen manglende embeddings; 0 API-kald")
        return stats

    after_id = None
    page_size = max(32, min(max_inputs, 2048))
    try:
        while True:
            page = _fetch_pending_page(conn, model_id, after_id, page_size)
            if not page:
                break
            after_id = page[-1].chunk_id
            batches = split_batches(
                [BatchItem(item.chunk_id, item.embedding_text, item.token_count) for item in page],
                max_inputs=max_inputs,
                max_tokens=max_tokens,
            )
            by_id = {item.chunk_id: item for item in page}
            for batch in batches:
                ids = [item.item_id for item in batch]
                texts = [item.text for item in batch]
                budget = sum(max(1, item.token_count) for item in batch)
                stats.api_requests += 1
                _log(
                    f"batch {stats.api_requests} inputs={len(ids)} "
                    f"tokenbudget={budget} indsat={stats.inserted}/{pending}"
                )
                try:
                    result = embed_texts(texts, client=client)
                except Exception as exc:
                    log_request(
                        conn,
                        run_id=run_id,
                        attempt=1,
                        chunk_ids=ids,
                        model_name=MODEL_NAME,
                        dimensions=DIMENSIONS,
                        input_count=len(ids),
                        token_count=budget,
                        openai_request_id=None,
                        http_status=getattr(exc, "status_code", None),
                        error_code=type(exc).__name__,
                        error_message=redact_secrets(str(exc)),
                        completed=True,
                    )
                    raise
                stats.retries += max(0, result.attempts - 1)
                log_request(
                    conn,
                    run_id=run_id,
                    attempt=result.attempts,
                    chunk_ids=ids,
                    model_name=result.model,
                    dimensions=DIMENSIONS,
                    input_count=len(ids),
                    token_count=result.total_tokens,
                    openai_request_id=result.request_id,
                    http_status=result.http_status,
                    error_code=None,
                    error_message=None,
                    completed=True,
                )
                _insert_batch(
                    conn,
                    model_id,
                    [
                        (chunk_id, vector, by_id[chunk_id].text_sha256)
                        for chunk_id, vector in zip(ids, result.embeddings)
                    ],
                )
                if not getattr(conn, "autocommit", True):
                    conn.commit()
                stats.inserted += len(ids)
                stats.prompt_tokens += result.prompt_tokens
                stats.total_tokens += result.total_tokens
                add_tokens(
                    conn,
                    run_id,
                    prompt_tokens=result.prompt_tokens,
                    total_tokens=result.total_tokens,
                    inserted=len(ids),
                )
                _log(
                    f"færdig chunks={stats.inserted} skip={stats.skipped} "
                    f"prompt_tokens={stats.prompt_tokens} total_tokens={stats.total_tokens} "
                    f"api={stats.api_requests} retries={stats.retries}"
                )
        finish_run(
            conn,
            run_id,
            status="complete",
            inserted_count=stats.inserted,
            skipped_count=stats.skipped,
            prompt_tokens=stats.prompt_tokens,
            total_tokens=stats.total_tokens,
        )
    except Exception as exc:
        stats.failed = stats.pending - stats.inserted
        if not getattr(conn, "autocommit", True):
            conn.rollback()
        finish_run(
            conn,
            run_id,
            status="failed",
            inserted_count=stats.inserted,
            skipped_count=stats.skipped,
            failed_count=stats.failed,
            prompt_tokens=stats.prompt_tokens,
            total_tokens=stats.total_tokens,
            error_message=redact_secrets(str(exc)),
        )
        raise
    stats.duration_s = time.monotonic() - started
    return stats


def run_resume_pilot(conn, *, client: EmbeddingsAPI | None = None) -> EmbedStats:
    return run_pilot(conn, dry_run=False, client=client)


def run_corpus(
    conn,
    *,
    approved: bool,
    dry_run: bool = False,
    client: EmbeddingsAPI | None = None,
) -> EmbedStats:
    if not approved:
        raise FullCorpusNotApprovedError(
            "fuld korpus-embedding kræver --i-approve-full-corpus"
        )
    return embed_pending(
        conn,
        phase="corpus",
        selection_key=CORPUS_SELECTION_KEY,
        dry_run=dry_run,
        client=client,
        max_inputs=DEFAULT_BATCH_INPUTS,
        max_tokens=DEFAULT_BATCH_TOKENS,
    )


def run_resume_corpus(conn, *, client: EmbeddingsAPI | None = None) -> EmbedStats:
    return run_corpus(conn, approved=True, dry_run=False, client=client)
