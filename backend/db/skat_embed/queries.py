"""Query-embeddings med samme model og dimensioner som chunks."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from backend.db.skat_embed.audit import finish_run, log_request, start_run
from backend.db.skat_embed.client import EmbeddingsAPI, embed_texts, split_batches, BatchItem
from backend.db.skat_embed.constants import DIMENSIONS, MODEL_NAME, QUERY_PREFIX
from backend.db.skat_embed.model import ensure_embedding_model
from backend.db.skat_embed.vectors import pgvector_literal, validate_embedding


@dataclass(frozen=True)
class QueryEmbed:
    query_key: str
    eval_id: str | None
    purpose: str
    sha256: str
    vector: list[float]


def query_input_text(query: str) -> str:
    return QUERY_PREFIX + query.strip()


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def embed_query_text(
    query: str,
    *,
    client: EmbeddingsAPI | None = None,
) -> QueryEmbed:
    payload = query_input_text(query)
    result = embed_texts([payload], client=client)
    vector = validate_embedding(result.embeddings[0])
    digest = _sha(payload)
    return QueryEmbed(
        query_key=digest,
        eval_id=None,
        purpose="adhoc",
        sha256=digest,
        vector=vector,
    )


def store_query_embedding(conn, model_id: UUID, item: QueryEmbed) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO skat.query_embeddings (
                query_key, embedding_model_id, query_text_sha256,
                embedding, purpose, eval_id
            ) VALUES (
                %s, %s, %s, %s::vector, %s, %s
            )
            ON CONFLICT (query_key, embedding_model_id) DO UPDATE
            SET query_text_sha256 = EXCLUDED.query_text_sha256,
                embedding = EXCLUDED.embedding,
                purpose = EXCLUDED.purpose,
                eval_id = EXCLUDED.eval_id,
                embedded_at = now()
            """,
            (
                item.query_key,
                model_id,
                item.sha256,
                pgvector_literal(item.vector),
                item.purpose,
                item.eval_id,
            ),
        )


def embed_eval_queries(
    conn,
    dataset: Path,
    *,
    client: EmbeddingsAPI | None = None,
    log=print,
) -> int:
    from backend.db.skat_retrieval.evaluate import load_dataset

    cases = load_dataset(dataset)
    model_id = ensure_embedding_model(conn)
    run_id = start_run(
        conn,
        phase="query",
        selection_key=f"eval:{dataset.name}",
        embedding_model_id=model_id,
        expected_count=len(cases),
        manifest={"dataset": str(dataset), "n": len(cases)},
    )
    items = []
    for case in cases:
        payload = query_input_text(str(case["query"]))
        items.append(
            BatchItem(
                item_id=str(case["eval_id"]),
                text=payload,
                token_count=max(8, len(payload.split())),
            )
        )
    inserted = 0
    tokens = 0
    try:
        for batch in split_batches(items, max_inputs=64, max_tokens=50000):
            result = embed_texts([item.text for item in batch], client=client)
            log_request(
                conn,
                run_id=run_id,
                attempt=1,
                chunk_ids=[item.item_id for item in batch],
                model_name=result.model,
                dimensions=DIMENSIONS,
                input_count=len(batch),
                token_count=result.total_tokens,
                openai_request_id=result.request_id,
                http_status=result.http_status,
                error_code=None,
                error_message=None,
                completed=True,
            )
            for item, vector in zip(batch, result.embeddings):
                digest = _sha(item.text)
                store_query_embedding(
                    conn,
                    model_id,
                    QueryEmbed(
                        query_key=item.item_id,
                        eval_id=item.item_id,
                        purpose="eval",
                        sha256=digest,
                        vector=vector,
                    ),
                )
                inserted += 1
            tokens += result.total_tokens
            if log:
                log(f"query-embeddings {inserted}/{len(items)} total_tokens={tokens}")
        finish_run(
            conn,
            run_id,
            status="complete",
            inserted_count=inserted,
            total_tokens=tokens,
            prompt_tokens=tokens,
        )
    except Exception as exc:
        finish_run(
            conn,
            run_id,
            status="failed",
            inserted_count=inserted,
            total_tokens=tokens,
            error_message=str(exc),
        )
        raise
    return inserted
