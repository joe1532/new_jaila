"""Faste embedding-konstanter. Ingen credentials."""

from __future__ import annotations

PROVIDER = "openai"
MODEL_NAME = "text-embedding-3-large"
DIMENSIONS = 1536
DISTANCE_METRIC = "inner_product"
ENCODING_FORMAT = "float"

# OpenAI embeddings.create: max 2048 inputs og 300000 tokens pr. request.
MAX_BATCH_INPUTS = 2048
MAX_BATCH_TOKENS = 300000
DEFAULT_BATCH_INPUTS = 2048
DEFAULT_BATCH_TOKENS = 250000

MAX_RETRIES = 8
BACKOFF_BASE_SECONDS = 1.0
BACKOFF_MAX_SECONDS = 60.0

PILOT_SIZE = 1000
PILOT_SELECTION_KEY = "skat_embed_pilot_v1"
CORPUS_SELECTION_KEY = "skat_embed_corpus_v1"

QUERY_PREFIX = "Forespørgsel:\n"

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
