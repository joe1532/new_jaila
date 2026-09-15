-- JAILA SKAT-korpus: extensions og skema.
-- Idempotent. Køres som database-ejer/superuser.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

CREATE SCHEMA IF NOT EXISTS skat;

CREATE TABLE IF NOT EXISTS skat.schema_migrations (
    filename text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

-- unaccent(text) er STABLE (slår ordbog op). Generated columns kræver IMMUTABLE.
-- To-arguments-formen med navngiven ordbog er IMMUTABLE i PostgreSQL.
CREATE OR REPLACE FUNCTION skat.immutable_unaccent(input text)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
STRICT
AS $$
    SELECT public.unaccent('public.unaccent'::regdictionary, input);
$$;

COMMENT ON FUNCTION skat.immutable_unaccent(text) IS
    'IMMUTABLE wrapper om unaccent, så danish tsvector kan gemmes generated.';
