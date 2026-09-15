-- Provenance for publication_year og bevarede referenceforekomster.
-- document_references skal være tom, eller rækkerne skal allerede have de nye felter,
-- før NOT NULL sættes. 2026-pilotens referencer slettes før denne migration.

SET search_path TO skat, public;

ALTER TABLE skat.legal_documents
    ADD COLUMN IF NOT EXISTS publication_year_inferred boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS publication_year_original integer;

COMMENT ON COLUMN skat.legal_documents.publication_year_inferred IS
    'true når publication_year er sat til JSONL-mappens år, fordi JSONL havde null.';
COMMENT ON COLUMN skat.legal_documents.publication_year_original IS
    'JSONL-værdien. null hvis JSONL ikke havde publication_year.';

UPDATE skat.legal_documents
SET
    publication_year_original = CASE
        WHEN jsonb_typeof(raw_record -> 'publication_year') = 'number'
        THEN (raw_record ->> 'publication_year')::integer
        ELSE NULL
    END,
    publication_year_inferred = (
        jsonb_typeof(raw_record -> 'publication_year') IS DISTINCT FROM 'number'
    );

ALTER TABLE skat.document_references
    ADD COLUMN IF NOT EXISTS canonical_reference_sha256 text,
    ADD COLUMN IF NOT EXISTS occurrence_index integer,
    ADD COLUMN IF NOT EXISTS original_target_document_id text;

ALTER TABLE skat.document_references
    ALTER COLUMN canonical_reference_sha256 SET NOT NULL,
    ALTER COLUMN occurrence_index SET NOT NULL;

ALTER TABLE skat.document_references
    DROP CONSTRAINT IF EXISTS document_references_canonical_sha256_chk,
    DROP CONSTRAINT IF EXISTS document_references_occurrence_index_chk;

ALTER TABLE skat.document_references
    ADD CONSTRAINT document_references_canonical_sha256_chk
        CHECK (canonical_reference_sha256 ~* '^[0-9a-f]{64}$'),
    ADD CONSTRAINT document_references_occurrence_index_chk
        CHECK (occurrence_index >= 0);

ALTER TABLE skat.document_references
    DROP CONSTRAINT IF EXISTS document_references_canonical_occurrence_key;

ALTER TABLE skat.document_references
    ADD CONSTRAINT document_references_canonical_occurrence_key
        UNIQUE (canonical_reference_sha256, occurrence_index);

COMMENT ON COLUMN skat.document_references.canonical_reference_sha256 IS
    'SHA-256 af den kanoniske originale JSONL-referencepost.';
COMMENT ON COLUMN skat.document_references.occurrence_index IS
    'Nulbaseret løbenummer for identiske canonical_reference_sha256 i filrækkefølge.';
COMMENT ON COLUMN skat.document_references.original_target_document_id IS
    'JSONL-target når dokumentet ikke findes i legal_documents. FK-feltet er da null.';
