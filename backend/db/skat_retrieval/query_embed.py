"""On-demand query-embedding. Gemmes ikke. Ingen nøgle eller vektor i logs."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

from backend.db.skat_embed.client import EmbeddingsAPI, embed_texts
from backend.db.skat_embed.constants import DIMENSIONS, MODEL_NAME, QUERY_PREFIX
from backend.db.skat_embed.errors import MissingApiKeyError, SkatEmbedError, VectorValidationError
from backend.db.skat_embed.keys import openai_api_key
from backend.db.skat_embed.queries import query_input_text
from backend.db.skat_embed.vectors import pgvector_literal, validate_embedding
from backend.db.skat_retrieval.errors import QueryEmbeddingUnavailableError


def query_text_sha256(query: str) -> str:
    payload = QUERY_PREFIX + query.strip()
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ResolvedQueryVector:
    pgvector: str
    source: str
    latency_ms: float
    input_tokens: int | None
    model: str = MODEL_NAME
    dimensions: int = DIMENSIONS

    def usage_payload(self) -> dict[str, object] | None:
        if self.source != "on_demand":
            return None
        return {
            "model": self.model,
            "dimensions": self.dimensions,
            "input_tokens": self.input_tokens,
            "source": self.source,
        }


def _stored_vector(conn, *, eval_id: str | None, query: str) -> str | None:
    with conn.cursor() as cur:
        if eval_id:
            cur.execute(
                """
                SELECT embedding::text
                FROM skat.query_embeddings
                WHERE eval_id = %s
                LIMIT 1
                """,
                (eval_id,),
            )
        else:
            cur.execute(
                """
                SELECT embedding::text
                FROM skat.query_embeddings
                WHERE query_text_sha256 = %s
                LIMIT 1
                """,
                (query_text_sha256(query),),
            )
        row = cur.fetchone()
    return str(row[0]) if row else None


def embed_query_on_demand(
    query: str,
    *,
    client: EmbeddingsAPI | None = None,
) -> ResolvedQueryVector:
    """Kald OpenAI. Gemmer ikke vektoren. Logger ikke nøgle, input eller vektor."""
    try:
        openai_api_key()
    except MissingApiKeyError as exc:
        raise QueryEmbeddingUnavailableError(
            "OPENAI_API_KEY mangler",
            reason="missing_openai_api_key",
        ) from exc
    payload = query_input_text(query.strip())
    started = time.perf_counter()
    try:
        result = embed_texts([payload], client=client)
        vector = validate_embedding(result.embeddings[0])
    except VectorValidationError as exc:
        raise QueryEmbeddingUnavailableError(
            "ugyldig query-embedding",
            reason="invalid_query_embedding",
        ) from exc
    except SkatEmbedError as exc:
        if isinstance(exc.__cause__, VectorValidationError):
            raise QueryEmbeddingUnavailableError(
                "ugyldig query-embedding",
                reason="invalid_query_embedding",
            ) from exc
        raise QueryEmbeddingUnavailableError(
            "query-embedding API-fejl",
            reason="query_embedding_api_error",
        ) from exc
    except Exception as exc:
        raise QueryEmbeddingUnavailableError(
            "query-embedding API-fejl",
            reason="query_embedding_api_error",
        ) from exc
    return ResolvedQueryVector(
        pgvector=pgvector_literal(vector),
        source="on_demand",
        latency_ms=(time.perf_counter() - started) * 1000.0,
        input_tokens=result.prompt_tokens,
        model=result.model or MODEL_NAME,
        dimensions=DIMENSIONS,
    )


def resolve_query_vector(
    conn,
    query: str,
    *,
    eval_id: str | None = None,
    client: EmbeddingsAPI | None = None,
    on_demand: bool = True,
) -> ResolvedQueryVector:
    """Prioritet: gemt kompatibel vektor, derefter on-demand API."""
    started = time.perf_counter()
    stored = _stored_vector(conn, eval_id=eval_id, query=query)
    if stored:
        return ResolvedQueryVector(
            pgvector=stored,
            source="stored",
            latency_ms=(time.perf_counter() - started) * 1000.0,
            input_tokens=None,
        )
    if not on_demand:
        raise QueryEmbeddingUnavailableError(
            "ingen query-embedding",
            reason="missing_query_embedding",
        )
    return embed_query_on_demand(query, client=client)
