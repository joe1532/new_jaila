"""Faste retrieval-indstillinger. Ingen credentials."""

SCHEMA_VERSION = "1.0"
HNSW_EF_SEARCH = 800
HNSW_INDEX_NAME = "chunk_embeddings_hnsw_ip_v2_idx"
DEFAULT_RETRIEVE_MODE = "hybrid"
DEFAULT_CLI_SEARCH_MODE = "auto"
CLI_SEARCH_MODES = ("auto", "hybrid", "vector", "lexical", "exact")
OUTPUT_FORMATS = ("text", "json", "jsonl")
LEXICAL_CANDIDATE_LIMIT = 200
VECTOR_CANDIDATE_LIMIT = 200
EXACT_CANDIDATE_POOLS = (200, 500, 1000)
TIMING_KEYS = (
    "query_embedding",
    "lexical",
    "vector",
    "fusion",
    "hydrate",
    "total",
)
