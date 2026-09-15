ALTER TABLE skat.document_references
    ADD COLUMN IF NOT EXISTS cited_law_key text,
    ADD COLUMN IF NOT EXISTS cited_section_number integer,
    ADD COLUMN IF NOT EXISTS cited_section_suffix text,
    ADD COLUMN IF NOT EXISTS cited_section_end_number integer,
    ADD COLUMN IF NOT EXISTS cited_section_end_suffix text,
    ADD COLUMN IF NOT EXISTS cited_subsection text,
    ADD COLUMN IF NOT EXISTS cited_item_number text,
    ADD COLUMN IF NOT EXISTS cited_letter text;

CREATE INDEX IF NOT EXISTS document_references_law_section_idx
    ON skat.document_references (
        cited_law_key,
        cited_section_number,
        cited_section_suffix
    )
    WHERE cited_law_key IS NOT NULL;

COMMENT ON COLUMN skat.document_references.cited_law_key IS
    'Kanonisk, casefoldet lovnøgle fra den generiske lovforkortelsesordbog.';
COMMENT ON COLUMN skat.document_references.cited_section_number IS
    'Numerisk begyndelsesparagraf; original citation bevares i cited_identifier.';
COMMENT ON COLUMN skat.document_references.cited_section_end_number IS
    'Slutparagraf ved interval; NULL ved en enkelt paragraf.';
