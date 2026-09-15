-- JAILA SKAT-korpus: tabeller, constraints, indekser, funktioner og grants.
-- Embeddings-søgning og HNSW er bevidst ikke med her.

SET search_path TO skat, public;

-- Tilladte klassifikationer fra skat_chunking_embedding_spec.md §9.
-- Text + CHECK, ikke ENUM, så en senere chunkerversion kan udvide via migration.

CREATE TABLE IF NOT EXISTS skat.legal_documents (
    document_id text PRIMARY KEY,
    schema_version text NOT NULL,
    corpus text NOT NULL,
    source_oid text NOT NULL,
    skm_number text,
    title text NOT NULL,
    document_type text,
    authority text,
    responsible_agency text,
    case_number text,
    publication_date date,
    decision_date date,
    publication_year integer NOT NULL,
    main_topic text,
    subtopic text,
    subject_terms text[] NOT NULL DEFAULT '{}',
    summary text,
    source_url text NOT NULL,
    document_status text NOT NULL,
    replaced_by text,
    has_body boolean NOT NULL,
    has_assets boolean NOT NULL,
    has_ocr boolean NOT NULL,
    manual_source_check boolean NOT NULL,
    image_text_authority text NOT NULL,
    content_sha256 text NOT NULL,
    canonical_text_sha256 jsonb NOT NULL,
    canonical_text_length jsonb NOT NULL,
    raw_record jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT legal_documents_source_oid_key UNIQUE (source_oid),
    CONSTRAINT legal_documents_publication_year_chk
        CHECK (publication_year BETWEEN 1900 AND 2200),
    CONSTRAINT legal_documents_content_sha256_chk
        CHECK (content_sha256 ~* '^[0-9a-f]{64}$')
);

CREATE UNIQUE INDEX IF NOT EXISTS legal_documents_skm_number_upper_uidx
    ON skat.legal_documents (upper(skm_number))
    WHERE skm_number IS NOT NULL;

CREATE INDEX IF NOT EXISTS legal_documents_publication_year_idx
    ON skat.legal_documents (publication_year);
CREATE INDEX IF NOT EXISTS legal_documents_document_type_idx
    ON skat.legal_documents (document_type);
CREATE INDEX IF NOT EXISTS legal_documents_authority_idx
    ON skat.legal_documents (authority);
CREATE INDEX IF NOT EXISTS legal_documents_document_status_idx
    ON skat.legal_documents (document_status);
CREATE INDEX IF NOT EXISTS legal_documents_subject_terms_gin
    ON skat.legal_documents USING gin (subject_terms);

CREATE OR REPLACE FUNCTION skat.touch_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS legal_documents_touch_updated_at ON skat.legal_documents;
CREATE TRIGGER legal_documents_touch_updated_at
    BEFORE UPDATE ON skat.legal_documents
    FOR EACH ROW
    EXECUTE FUNCTION skat.touch_updated_at();

CREATE TABLE IF NOT EXISTS skat.document_versions (
    version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id text NOT NULL REFERENCES skat.legal_documents (document_id) ON DELETE CASCADE,
    content_sha256 text NOT NULL,
    schema_version text NOT NULL,
    source_manifest_sha256 text NOT NULL,
    source_path text,
    metadata_path text,
    imported_at timestamptz NOT NULL DEFAULT now(),
    raw_record jsonb NOT NULL,
    CONSTRAINT document_versions_content_sha256_chk
        CHECK (content_sha256 ~* '^[0-9a-f]{64}$'),
    CONSTRAINT document_versions_manifest_sha256_chk
        CHECK (source_manifest_sha256 ~* '^[0-9a-f]{64}$'),
    CONSTRAINT document_versions_document_sha_key UNIQUE (document_id, content_sha256)
);

CREATE TABLE IF NOT EXISTS skat.chunk_runs (
    chunk_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    chunker_name text NOT NULL,
    chunker_version text NOT NULL,
    chunk_config_sha256 text NOT NULL,
    schema_version text NOT NULL,
    source_manifest_sha256 text NOT NULL,
    tokenizer_model text NOT NULL,
    tokenizer_encoding text NOT NULL,
    target_tokens integer NOT NULL,
    hard_max_tokens integer NOT NULL,
    overlap_tokens integer NOT NULL,
    config jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chunk_runs_config_sha256_chk
        CHECK (chunk_config_sha256 ~* '^[0-9a-f]{64}$'),
    CONSTRAINT chunk_runs_manifest_sha256_chk
        CHECK (source_manifest_sha256 ~* '^[0-9a-f]{64}$'),
    CONSTRAINT chunk_runs_config_manifest_key
        UNIQUE (chunk_config_sha256, source_manifest_sha256)
);

-- Årskørsel, så senere import kan afvise et år hvis manifesttællinger ikke matcher.
CREATE TABLE IF NOT EXISTS skat.ingest_year_manifests (
    ingest_year integer NOT NULL,
    chunk_run_id uuid NOT NULL REFERENCES skat.chunk_runs (chunk_run_id) ON DELETE CASCADE,
    source_manifest_sha256 text NOT NULL,
    chunk_config_sha256 text NOT NULL,
    document_count integer NOT NULL,
    chunk_count integer NOT NULL,
    reference_count integer NOT NULL DEFAULT 0,
    validation_status text NOT NULL,
    chunk_sha256 text,
    raw_manifest jsonb NOT NULL DEFAULT '{}',
    imported_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (ingest_year, chunk_config_sha256, source_manifest_sha256),
    CONSTRAINT ingest_year_manifests_source_sha256_chk
        CHECK (source_manifest_sha256 ~* '^[0-9a-f]{64}$'),
    CONSTRAINT ingest_year_manifests_config_sha256_chk
        CHECK (chunk_config_sha256 ~* '^[0-9a-f]{64}$'),
    CONSTRAINT ingest_year_manifests_year_chk
        CHECK (ingest_year BETWEEN 1900 AND 2200),
    CONSTRAINT ingest_year_manifests_counts_chk
        CHECK (document_count >= 0 AND chunk_count >= 0 AND reference_count >= 0),
    CONSTRAINT ingest_year_manifests_status_chk
        CHECK (validation_status IN ('pass', 'fail', 'incomplete'))
);

CREATE TABLE IF NOT EXISTS skat.chunks (
    chunk_id text PRIMARY KEY,
    document_id text NOT NULL REFERENCES skat.legal_documents (document_id) ON DELETE CASCADE,
    chunk_run_id uuid NOT NULL REFERENCES skat.chunk_runs (chunk_run_id),
    schema_version text NOT NULL,
    source_oid text NOT NULL,
    skm_number text,
    chunker_version text NOT NULL,
    chunk_config_sha256 text NOT NULL,
    chunk_index integer NOT NULL,
    publication_date date,
    decision_date date,
    publication_year integer NOT NULL,
    document_type text,
    authority text,
    case_number text,
    subject_terms text[] NOT NULL DEFAULT '{}',
    source_url text NOT NULL,
    section_type text NOT NULL,
    legal_weight text NOT NULL,
    section_heading_original text,
    section_heading_normalized text,
    section_path_original text[] NOT NULL DEFAULT '{}',
    section_path_normalized text[] NOT NULL DEFAULT '{}',
    classification_method text NOT NULL,
    question_number text,
    is_final_result boolean NOT NULL,
    chunk_kind text NOT NULL,
    chunk_text text NOT NULL,
    decision_context text NOT NULL DEFAULT '',
    embedding_text text NOT NULL,
    contains_table boolean NOT NULL,
    contains_image boolean NOT NULL,
    contains_ocr boolean NOT NULL,
    previous_chunk_id text,
    next_chunk_id text,
    manual_source_check boolean NOT NULL,
    token_count integer NOT NULL,
    text_sha256 text NOT NULL,
    embedding_text_sha256 text NOT NULL,
    raw_record jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    search_vector tsvector GENERATED ALWAYS AS (
        to_tsvector('danish'::regconfig, skat.immutable_unaccent(coalesce(chunk_text, '')))
    ) STORED,
    CONSTRAINT chunks_document_index_config_key
        UNIQUE (document_id, chunk_index, chunk_config_sha256),
    CONSTRAINT chunks_chunk_index_chk CHECK (chunk_index >= 0),
    CONSTRAINT chunks_token_count_chk CHECK (token_count > 0 AND token_count <= 1000),
    CONSTRAINT chunks_text_sha256_chk CHECK (text_sha256 ~* '^[0-9a-f]{64}$'),
    CONSTRAINT chunks_embedding_text_sha256_chk
        CHECK (embedding_text_sha256 ~* '^[0-9a-f]{64}$'),
    CONSTRAINT chunks_chunk_config_sha256_chk
        CHECK (chunk_config_sha256 ~* '^[0-9a-f]{64}$'),
    CONSTRAINT chunks_publication_year_chk
        CHECK (publication_year BETWEEN 1900 AND 2200),
    CONSTRAINT chunks_section_type_chk CHECK (section_type IN (
        'summary',
        'questions',
        'answers',
        'facts',
        'claimant_arguments',
        'other_party_arguments',
        'authority_reasoning',
        'authority_recommendation',
        'authority_decision',
        'court_reasoning',
        'court_result',
        'court_reasoning_and_result',
        'prior_instance_reasoning',
        'prior_instance_result',
        'legal_basis',
        'preparatory_material',
        'case_law',
        'administrative_guidance',
        'references',
        'ocr_supplement',
        'other',
        'unstructured'
    )),
    CONSTRAINT chunks_legal_weight_chk CHECK (legal_weight IN (
        'editorial',
        'party_statement',
        'factual_record',
        'authoritative_reasoning',
        'authoritative_result',
        'authority_recommendation',
        'source_material',
        'prior_instance',
        'supplementary_non_authoritative',
        'unclassified'
    )),
    CONSTRAINT chunks_previous_chunk_id_fkey
        FOREIGN KEY (previous_chunk_id) REFERENCES skat.chunks (chunk_id)
        ON DELETE SET NULL
        DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT chunks_next_chunk_id_fkey
        FOREIGN KEY (next_chunk_id) REFERENCES skat.chunks (chunk_id)
        ON DELETE SET NULL
        DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX IF NOT EXISTS chunks_document_id_chunk_index_idx
    ON skat.chunks (document_id, chunk_index);
CREATE INDEX IF NOT EXISTS chunks_publication_year_idx
    ON skat.chunks (publication_year);
CREATE INDEX IF NOT EXISTS chunks_section_type_idx
    ON skat.chunks (section_type);
CREATE INDEX IF NOT EXISTS chunks_legal_weight_idx
    ON skat.chunks (legal_weight);
CREATE INDEX IF NOT EXISTS chunks_is_final_result_idx
    ON skat.chunks (is_final_result);
CREATE INDEX IF NOT EXISTS chunks_authority_idx
    ON skat.chunks (authority);
CREATE INDEX IF NOT EXISTS chunks_document_type_idx
    ON skat.chunks (document_type);
CREATE INDEX IF NOT EXISTS chunks_chunk_config_sha256_idx
    ON skat.chunks (chunk_config_sha256);
CREATE INDEX IF NOT EXISTS chunks_subject_terms_gin
    ON skat.chunks USING gin (subject_terms);
CREATE INDEX IF NOT EXISTS chunks_final_result_document_idx
    ON skat.chunks (document_id)
    WHERE is_final_result = true;
CREATE INDEX IF NOT EXISTS chunks_summary_document_idx
    ON skat.chunks (document_id)
    WHERE section_type = 'summary';
CREATE INDEX IF NOT EXISTS chunks_authoritative_reasoning_document_idx
    ON skat.chunks (document_id)
    WHERE legal_weight = 'authoritative_reasoning';
CREATE INDEX IF NOT EXISTS chunks_search_vector_gin
    ON skat.chunks USING gin (search_vector);

CREATE TABLE IF NOT EXISTS skat.chunk_source_spans (
    chunk_id text NOT NULL REFERENCES skat.chunks (chunk_id) ON DELETE CASCADE,
    span_index integer NOT NULL,
    source text NOT NULL,
    start_offset integer NOT NULL,
    end_offset integer NOT NULL,
    role text NOT NULL,
    PRIMARY KEY (chunk_id, span_index),
    CONSTRAINT chunk_source_spans_span_index_chk CHECK (span_index >= 0),
    CONSTRAINT chunk_source_spans_start_offset_chk CHECK (start_offset >= 0),
    CONSTRAINT chunk_source_spans_end_offset_chk CHECK (end_offset > start_offset),
    CONSTRAINT chunk_source_spans_role_chk CHECK (role IN (
        'primary',
        'overlap',
        'context',
        'repeated_context'
    ))
);

CREATE TABLE IF NOT EXISTS skat.document_references (
    reference_id uuid PRIMARY KEY,
    reference_key text NOT NULL UNIQUE,
    source_document_id text NOT NULL
        REFERENCES skat.legal_documents (document_id) ON DELETE CASCADE,
    source_chunk_id text REFERENCES skat.chunks (chunk_id) ON DELETE SET NULL,
    reference_type text NOT NULL,
    cited_identifier text,
    exact_reference_text text NOT NULL,
    target_document_id text REFERENCES skat.legal_documents (document_id) ON DELETE SET NULL,
    target_url text,
    resolution_status text NOT NULL,
    raw_record jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT document_references_status_chk
        CHECK (resolution_status IN ('resolved', 'unresolved', 'external')),
    CONSTRAINT document_references_resolved_target_chk
        CHECK (resolution_status <> 'resolved' OR target_document_id IS NOT NULL),
    CONSTRAINT document_references_external_url_chk
        CHECK (resolution_status <> 'external' OR target_url IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS document_references_source_document_id_idx
    ON skat.document_references (source_document_id);
CREATE INDEX IF NOT EXISTS document_references_source_chunk_id_idx
    ON skat.document_references (source_chunk_id);
CREATE INDEX IF NOT EXISTS document_references_target_document_id_idx
    ON skat.document_references (target_document_id);
CREATE INDEX IF NOT EXISTS document_references_reference_type_idx
    ON skat.document_references (reference_type);
CREATE INDEX IF NOT EXISTS document_references_cited_identifier_idx
    ON skat.document_references (cited_identifier);
CREATE INDEX IF NOT EXISTS document_references_resolution_status_idx
    ON skat.document_references (resolution_status);

CREATE TABLE IF NOT EXISTS skat.embedding_models (
    embedding_model_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    provider text NOT NULL,
    model_name text NOT NULL,
    dimensions integer NOT NULL,
    distance_metric text NOT NULL,
    model_revision text,
    configuration jsonb NOT NULL DEFAULT '{}',
    active boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT embedding_models_dimensions_chk CHECK (dimensions = 1536),
    CONSTRAINT embedding_models_distance_metric_chk CHECK (distance_metric = 'inner_product')
);

-- UNIQUE-constraint tillader flere NULL i model_revision. Indekset gør identiteten unik.
CREATE UNIQUE INDEX IF NOT EXISTS embedding_models_identity_uidx
    ON skat.embedding_models (
        provider,
        model_name,
        dimensions,
        coalesce(model_revision, '')
    );

CREATE TABLE IF NOT EXISTS skat.chunk_embeddings (
    chunk_id text NOT NULL REFERENCES skat.chunks (chunk_id) ON DELETE CASCADE,
    embedding_model_id uuid NOT NULL
        REFERENCES skat.embedding_models (embedding_model_id),
    embedding vector(1536) NOT NULL,
    embedding_text_sha256 text NOT NULL,
    embedded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (chunk_id, embedding_model_id),
    CONSTRAINT chunk_embeddings_sha256_chk
        CHECK (embedding_text_sha256 ~* '^[0-9a-f]{64}$')
);

-- Eksakt dokumentopslag. Aldrig embeddings.
CREATE OR REPLACE FUNCTION skat.resolve_document_id(identifier text)
RETURNS text
LANGUAGE sql
STABLE
PARALLEL SAFE
AS $$
    WITH normalized AS (
        SELECT btrim(identifier) AS raw,
               upper(replace(btrim(identifier), ' ', '')) AS compact
    )
    SELECT d.document_id
    FROM skat.legal_documents AS d
    CROSS JOIN normalized AS n
    WHERE d.document_id = n.raw
       OR d.source_oid = n.raw
       OR d.document_id = 'skat-info:oid:' || n.raw
       OR (
            d.skm_number IS NOT NULL
            AND upper(replace(d.skm_number, ' ', '')) = n.compact
       )
    ORDER BY
        CASE
            WHEN d.document_id = n.raw THEN 0
            WHEN d.skm_number IS NOT NULL
                 AND upper(replace(d.skm_number, ' ', '')) = n.compact THEN 1
            ELSE 2
        END
    LIMIT 1;
$$;

CREATE OR REPLACE FUNCTION skat.get_document_by_identifier(identifier text)
RETURNS TABLE (
    document_id text,
    source_oid text,
    skm_number text,
    title text,
    document_type text,
    authority text,
    publication_year integer,
    publication_date date,
    decision_date date,
    source_url text,
    document_status text,
    manual_source_check boolean,
    summary text
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        d.document_id,
        d.source_oid,
        d.skm_number,
        d.title,
        d.document_type,
        d.authority,
        d.publication_year,
        d.publication_date,
        d.decision_date,
        d.source_url,
        d.document_status,
        d.manual_source_check,
        d.summary
    FROM skat.legal_documents AS d
    WHERE d.document_id = skat.resolve_document_id(identifier);
$$;

COMMENT ON FUNCTION skat.get_document_by_identifier(text) IS
    'Eksakt SKM- eller OID-opslag. Returnerer metadata og hele summary uden embeddings.';

CREATE OR REPLACE FUNCTION skat.get_document_summary(identifier text)
RETURNS text
LANGUAGE sql
STABLE
AS $$
    SELECT d.summary
    FROM skat.legal_documents AS d
    WHERE d.document_id = skat.resolve_document_id(identifier);
$$;

COMMENT ON FUNCTION skat.get_document_summary(text) IS
    'Hele legal_documents.summary. Aldrig et afkortet resuméchunk.';

CREATE OR REPLACE FUNCTION skat.get_document_final_result(identifier text)
RETURNS TABLE (
    chunk_id text,
    chunk_index integer,
    section_type text,
    legal_weight text,
    chunk_text text,
    source_url text,
    manual_source_check boolean,
    is_final_result boolean
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        c.chunk_id,
        c.chunk_index,
        c.section_type,
        c.legal_weight,
        c.chunk_text,
        c.source_url,
        c.manual_source_check,
        c.is_final_result
    FROM skat.chunks AS c
    WHERE c.document_id = skat.resolve_document_id(identifier)
      AND c.is_final_result = true
    ORDER BY c.chunk_index;
$$;

CREATE OR REPLACE FUNCTION skat.get_document_reasoning(identifier text)
RETURNS TABLE (
    chunk_id text,
    chunk_index integer,
    section_type text,
    legal_weight text,
    chunk_text text,
    source_url text
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        c.chunk_id,
        c.chunk_index,
        c.section_type,
        c.legal_weight,
        c.chunk_text,
        c.source_url
    FROM skat.chunks AS c
    WHERE c.document_id = skat.resolve_document_id(identifier)
      AND c.legal_weight = 'authoritative_reasoning'
    ORDER BY c.chunk_index;
$$;

COMMENT ON FUNCTION skat.get_document_reasoning(text) IS
    'Kun authoritative_reasoning. prior_instance er udeladt.';

CREATE OR REPLACE FUNCTION skat.get_document_references(identifier text)
RETURNS TABLE (
    direction text,
    reference_id uuid,
    reference_key text,
    reference_type text,
    cited_identifier text,
    exact_reference_text text,
    source_document_id text,
    source_chunk_id text,
    target_document_id text,
    target_url text,
    resolution_status text
)
LANGUAGE sql
STABLE
AS $$
    WITH resolved AS (
        SELECT skat.resolve_document_id(identifier) AS document_id
    )
    SELECT
        'outgoing'::text,
        r.reference_id,
        r.reference_key,
        r.reference_type,
        r.cited_identifier,
        r.exact_reference_text,
        r.source_document_id,
        r.source_chunk_id,
        r.target_document_id,
        r.target_url,
        r.resolution_status
    FROM skat.document_references AS r
    JOIN resolved ON r.source_document_id = resolved.document_id
    UNION ALL
    SELECT
        'incoming'::text,
        r.reference_id,
        r.reference_key,
        r.reference_type,
        r.cited_identifier,
        r.exact_reference_text,
        r.source_document_id,
        r.source_chunk_id,
        r.target_document_id,
        r.target_url,
        r.resolution_status
    FROM skat.document_references AS r
    JOIN resolved ON r.target_document_id = resolved.document_id;
$$;

CREATE OR REPLACE VIEW skat.document_retrieval_overview AS
SELECT
    d.document_id,
    d.source_oid,
    d.skm_number,
    d.title,
    d.document_type,
    d.authority,
    d.publication_year,
    d.publication_date,
    d.source_url,
    d.document_status,
    d.manual_source_check,
    coalesce(c.chunk_count, 0) AS chunk_count,
    coalesce(c.final_result_count, 0) AS final_result_count,
    coalesce(c.authoritative_reasoning_count, 0) AS authoritative_reasoning_count,
    coalesce(out_ref.outgoing_count, 0) AS outgoing_reference_count,
    coalesce(in_ref.incoming_count, 0) AS incoming_reference_count
FROM skat.legal_documents AS d
LEFT JOIN (
    SELECT
        document_id,
        count(*)::integer AS chunk_count,
        count(*) FILTER (WHERE is_final_result)::integer AS final_result_count,
        count(*) FILTER (WHERE legal_weight = 'authoritative_reasoning')::integer
            AS authoritative_reasoning_count
    FROM skat.chunks
    GROUP BY document_id
) AS c ON c.document_id = d.document_id
LEFT JOIN (
    SELECT
        source_document_id AS document_id,
        count(*)::integer AS outgoing_count
    FROM skat.document_references
    GROUP BY source_document_id
) AS out_ref ON out_ref.document_id = d.document_id
LEFT JOIN (
    SELECT
        target_document_id AS document_id,
        count(*)::integer AS incoming_count
    FROM skat.document_references
    WHERE target_document_id IS NOT NULL
    GROUP BY target_document_id
) AS in_ref ON in_ref.document_id = d.document_id;

COMMENT ON VIEW skat.document_retrieval_overview IS
    'Dokumentmetadata plus chunk- og referencetællinger til retrieval uden embeddings.';

-- Stub. Ingen embeddingsøgning før model og vektorer er på plads.
CREATE OR REPLACE FUNCTION skat.hybrid_search_chunks(
    query_text text,
    query_embedding vector(1536) DEFAULT NULL,
    result_limit integer DEFAULT 20
)
RETURNS TABLE (
    chunk_id text,
    score double precision
)
LANGUAGE sql
STABLE
AS $$
    SELECT NULL::text AS chunk_id, NULL::double precision AS score
    WHERE false;
$$;

COMMENT ON FUNCTION skat.hybrid_search_chunks(text, vector, integer) IS
    'Stub. Implementeres først når embeddingmodellen er valgt og vektorer er indlæst.';

CREATE OR REPLACE FUNCTION skat.year_manifest_matches(
    p_year integer,
    p_source_manifest_sha256 text,
    p_chunk_config_sha256 text,
    p_document_count integer,
    p_chunk_count integer,
    p_validation_status text
)
RETURNS boolean
LANGUAGE sql
STABLE
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM skat.ingest_year_manifests AS m
        WHERE m.ingest_year = p_year
          AND m.source_manifest_sha256 = p_source_manifest_sha256
          AND m.chunk_config_sha256 = p_chunk_config_sha256
          AND m.document_count = p_document_count
          AND m.chunk_count = p_chunk_count
          AND m.validation_status = p_validation_status
    );
$$;

COMMENT ON FUNCTION skat.year_manifest_matches(integer, text, text, integer, integer, text) IS
    'True kun når årets gemte manifest matcher hashes, tællinger og validation_status. Tom tabel = false, så første import kan indsætte rækken.';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'jaila_app') THEN
        CREATE ROLE jaila_app NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'jaila_ingest') THEN
        CREATE ROLE jaila_ingest NOLOGIN;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA skat TO jaila_app, jaila_ingest;

GRANT SELECT ON
    skat.legal_documents,
    skat.document_versions,
    skat.chunk_runs,
    skat.ingest_year_manifests,
    skat.chunks,
    skat.chunk_source_spans,
    skat.document_references,
    skat.embedding_models,
    skat.chunk_embeddings,
    skat.document_retrieval_overview
TO jaila_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA skat TO jaila_ingest;

GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA skat TO jaila_app, jaila_ingest;

ALTER DEFAULT PRIVILEGES IN SCHEMA skat
    GRANT SELECT ON TABLES TO jaila_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA skat
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO jaila_ingest;
ALTER DEFAULT PRIVILEGES IN SCHEMA skat
    GRANT EXECUTE ON FUNCTIONS TO jaila_app, jaila_ingest;

COMMENT ON TABLE skat.legal_documents IS
    'Én logisk afgørelse. UPSERT på document_id. Summary hentes her, aldrig fra chunks.';
COMMENT ON TABLE skat.document_versions IS
    'Provenance. UPSERT på (document_id, content_sha256).';
COMMENT ON TABLE skat.chunk_runs IS
    'Deterministisk chunkerkonfiguration. Unik på (chunk_config_sha256, source_manifest_sha256).';
COMMENT ON TABLE skat.ingest_year_manifests IS
    'Årskørsel til genoptagelig import. Afvis året hvis hashes, tællinger eller validation_status ikke matcher.';
COMMENT ON TABLE skat.chunks IS
    'Valideret chunk. UPSERT på chunk_id.';
COMMENT ON TABLE skat.document_references IS
    'Referencegraf. UPSERT på reference_key. reference_id sættes deterministisk af importscriptet.';
COMMENT ON TABLE skat.chunk_embeddings IS
    'Modelafhængige vektorer. UPSERT på (chunk_id, embedding_model_id). HNSW oprettes i 003 efter bulk-import.';
