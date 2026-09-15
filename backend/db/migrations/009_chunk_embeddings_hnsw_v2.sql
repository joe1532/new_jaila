-- Stærkere HNSW. Ingen ændring af embeddings. CONCURRENTLY kræver autocommit.
-- Bygges ved siden af chunk_embeddings_hnsw_ip_idx; det gamle indeks droppes efter verifikation.

CREATE INDEX CONCURRENTLY IF NOT EXISTS chunk_embeddings_hnsw_ip_v2_idx
    ON skat.chunk_embeddings
    USING hnsw (embedding vector_ip_ops)
    WITH (m = 32, ef_construction = 256);
