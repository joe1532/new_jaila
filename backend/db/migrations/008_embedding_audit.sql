-- Audit for embedding-worker. Ingen HNSW. Ingen ændring af juridisk indhold.

SET search_path TO skat, public;

CREATE TABLE IF NOT EXISTS skat.embedding_runs (
    embedding_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    phase text NOT NULL,
    selection_key text NOT NULL,
    embedding_model_id uuid REFERENCES skat.embedding_models (embedding_model_id),
    status text NOT NULL,
    expected_count integer,
    inserted_count integer NOT NULL DEFAULT 0,
    skipped_count integer NOT NULL DEFAULT 0,
    failed_count integer NOT NULL DEFAULT 0,
    prompt_tokens bigint NOT NULL DEFAULT 0,
    total_tokens bigint NOT NULL DEFAULT 0,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    error_message text,
    manifest jsonb NOT NULL DEFAULT '{}',
    CONSTRAINT embedding_runs_phase_chk
        CHECK (phase IN ('pilot', 'corpus', 'query', 'verify', 'dry_run')),
    CONSTRAINT embedding_runs_status_chk
        CHECK (status IN ('running', 'complete', 'failed', 'dry_run'))
);

CREATE INDEX IF NOT EXISTS embedding_runs_selection_started_idx
    ON skat.embedding_runs (selection_key, started_at DESC);

CREATE TABLE IF NOT EXISTS skat.embedding_requests (
    request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    embedding_run_id uuid NOT NULL
        REFERENCES skat.embedding_runs (embedding_run_id) ON DELETE CASCADE,
    attempt integer NOT NULL,
    chunk_ids text[] NOT NULL,
    openai_request_id text,
    model_name text NOT NULL,
    dimensions integer NOT NULL,
    input_count integer NOT NULL,
    token_count integer,
    http_status integer,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    error_code text,
    error_message text,
    CONSTRAINT embedding_requests_attempt_chk CHECK (attempt >= 1),
    CONSTRAINT embedding_requests_dimensions_chk CHECK (dimensions = 1536)
);

CREATE INDEX IF NOT EXISTS embedding_requests_run_idx
    ON skat.embedding_requests (embedding_run_id, started_at);

CREATE TABLE IF NOT EXISTS skat.query_embeddings (
    query_key text NOT NULL,
    embedding_model_id uuid NOT NULL
        REFERENCES skat.embedding_models (embedding_model_id),
    query_text_sha256 text NOT NULL,
    embedding vector(1536) NOT NULL,
    purpose text NOT NULL,
    eval_id text,
    embedded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (query_key, embedding_model_id),
    CONSTRAINT query_embeddings_sha256_chk
        CHECK (query_text_sha256 ~* '^[0-9a-f]{64}$'),
    CONSTRAINT query_embeddings_purpose_chk
        CHECK (purpose IN ('eval', 'adhoc'))
);

COMMENT ON TABLE skat.embedding_runs IS
    'Audit for embedding-kørsler. Genoptagelse styres af chunk_embeddings-hashes.';
COMMENT ON TABLE skat.embedding_requests IS
    'Requestlog uden API-nøgle og uden dokumenttekst. chunk_ids i inputrækkefølge.';
COMMENT ON TABLE skat.query_embeddings IS
    'Query-vektorer med samme model og 1536 dimensioner som chunks.';

GRANT SELECT ON skat.embedding_runs, skat.embedding_requests, skat.query_embeddings TO jaila_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON skat.embedding_runs, skat.embedding_requests, skat.query_embeddings TO jaila_ingest;
