-- Lexikale retrieval-indekser. Ingen embeddings. Ingen ændring af juridisk indhold.

SET search_path TO skat, public;

CREATE INDEX IF NOT EXISTS legal_documents_title_trgm_idx
    ON skat.legal_documents
    USING gin (skat.immutable_unaccent(title) gin_trgm_ops);

CREATE INDEX IF NOT EXISTS chunks_heading_normalized_trgm_idx
    ON skat.chunks
    USING gin (skat.immutable_unaccent(coalesce(section_heading_normalized, '')) gin_trgm_ops);

COMMENT ON INDEX skat.legal_documents_title_trgm_idx IS
    'Trigram-søgning i titel til lexical baseline. Ikke vektorsøgning.';
COMMENT ON INDEX skat.chunks_heading_normalized_trgm_idx IS
    'Trigram-søgning i normaliseret afsnitsoverskrift til lexical baseline.';
