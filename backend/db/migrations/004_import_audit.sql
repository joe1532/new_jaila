-- Import-audit. Ikke sandhedskilde ved genoptagelse; hashes og tællinger i data tabellerne er det.

SET search_path TO skat, public;

CREATE TABLE IF NOT EXISTS skat.import_runs (
    import_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    corpus text NOT NULL,
    publication_year integer,
    phase text NOT NULL,
    source_manifest_sha256 text NOT NULL,
    chunk_config_sha256 text NOT NULL,
    status text NOT NULL,
    expected_document_count integer,
    actual_document_count integer,
    expected_chunk_count integer,
    actual_chunk_count integer,
    expected_reference_count integer,
    actual_reference_count integer,
    records_read integer NOT NULL DEFAULT 0,
    records_inserted integer NOT NULL DEFAULT 0,
    records_skipped integer NOT NULL DEFAULT 0,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    error_message text,
    manifest jsonb NOT NULL DEFAULT '{}',
    CONSTRAINT import_runs_phase_chk
        CHECK (phase IN ('documents', 'year', 'verify')),
    CONSTRAINT import_runs_status_chk
        CHECK (status IN ('running', 'complete', 'failed')),
    CONSTRAINT import_runs_year_chk
        CHECK (publication_year IS NULL OR publication_year BETWEEN 1900 AND 2200),
    CONSTRAINT import_runs_source_sha256_chk
        CHECK (source_manifest_sha256 ~* '^[0-9a-f]{64}$'),
    CONSTRAINT import_runs_config_sha256_chk
        CHECK (chunk_config_sha256 ~* '^[0-9a-f]{64}$')
);

CREATE INDEX IF NOT EXISTS import_runs_corpus_phase_year_idx
    ON skat.import_runs (corpus, phase, publication_year, started_at DESC);

COMMENT ON TABLE skat.import_runs IS
    'Audit for SKAT-import. Genoptagelse skal stadig kontrollere rækker og hashes i datatabellerne.';

GRANT SELECT ON skat.import_runs TO jaila_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON skat.import_runs TO jaila_ingest;
