"""embedding_models: get-or-create for text-embedding-3-large / 1536."""

from __future__ import annotations

from uuid import UUID

from psycopg.types.json import Jsonb

from backend.db.skat_embed.constants import (
    DEFAULT_BATCH_INPUTS,
    DEFAULT_BATCH_TOKENS,
    DIMENSIONS,
    DISTANCE_METRIC,
    ENCODING_FORMAT,
    MODEL_NAME,
    PROVIDER,
)


def model_configuration() -> dict:
    return {
        "encoding_format": ENCODING_FORMAT,
        "dimensions": DIMENSIONS,
        "distance_metric": DISTANCE_METRIC,
        "max_batch_inputs": DEFAULT_BATCH_INPUTS,
        "max_batch_tokens": DEFAULT_BATCH_TOKENS,
        "api": "embeddings.create",
    }


def ensure_embedding_model(conn) -> UUID:
    """Opretter rækken én gang. created_at ændres ikke ved senere kørsler."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT embedding_model_id
            FROM skat.embedding_models
            WHERE provider = %s
              AND model_name = %s
              AND dimensions = %s
              AND model_revision IS NULL
            """,
            (PROVIDER, MODEL_NAME, DIMENSIONS),
        )
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute(
            """
            INSERT INTO skat.embedding_models (
                provider, model_name, dimensions, distance_metric,
                model_revision, configuration, active
            ) VALUES (
                %s, %s, %s, %s, NULL, %s, true
            )
            RETURNING embedding_model_id
            """,
            (
                PROVIDER,
                MODEL_NAME,
                DIMENSIONS,
                DISTANCE_METRIC,
                Jsonb(model_configuration()),
            ),
        )
        return cur.fetchone()[0]
