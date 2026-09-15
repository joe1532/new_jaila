-- Køres EFTER bulk-import af chunk_embeddings. Ikke en del af tom-skema-migrationen.
-- CONCURRENTLY kan ikke køres i en transaktion.

CREATE INDEX CONCURRENTLY IF NOT EXISTS chunk_embeddings_hnsw_ip_idx
    ON skat.chunk_embeddings
    USING hnsw (embedding vector_ip_ops);
