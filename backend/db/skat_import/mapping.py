"""Mapping fra JSONL-records til tabelrækker."""

from __future__ import annotations

from backend.db.skat_import.errors import MissingResolvedTargetError
from backend.db.skat_import.io import jsonb, reference_id


def document_row(record: dict, *, publication_year: int) -> tuple:
    jsonl_year = record.get("publication_year")
    if jsonl_year is None:
        # JSONL ændres ikke. Mappeåret bruges kun i den relationelle kolonne.
        year = publication_year
        original = None
        inferred = True
    else:
        year = jsonl_year
        original = jsonl_year
        inferred = False
    return (
        record["document_id"],
        record["schema_version"],
        record["corpus"],
        record["source_oid"],
        record.get("skm_number"),
        record["title"],
        record.get("document_type"),
        record.get("authority"),
        record.get("responsible_agency"),
        record.get("case_number"),
        record.get("publication_date"),
        record.get("decision_date"),
        year,
        original,
        inferred,
        record.get("main_topic"),
        record.get("subtopic"),
        record.get("subject_terms") or [],
        record.get("summary"),
        record["source_url"],
        record["document_status"],
        record.get("replaced_by"),
        record["has_body"],
        record["has_assets"],
        record["has_ocr"],
        record["manual_source_check"],
        record["image_text_authority"],
        record["content_sha256"],
        jsonb(record["canonical_text_sha256"]),
        jsonb(record["canonical_text_length"]),
        jsonb(record),
    )


DOCUMENT_COLUMNS = """
    document_id, schema_version, corpus, source_oid, skm_number, title,
    document_type, authority, responsible_agency, case_number,
    publication_date, decision_date, publication_year,
    publication_year_original, publication_year_inferred,
    main_topic, subtopic,
    subject_terms, summary, source_url, document_status, replaced_by,
    has_body, has_assets, has_ocr, manual_source_check, image_text_authority,
    content_sha256, canonical_text_sha256, canonical_text_length, raw_record
"""


def version_row(
    record: dict, *, source_manifest_sha256: str, source_path: str
) -> tuple:
    return (
        record["document_id"],
        record["content_sha256"],
        record["schema_version"],
        source_manifest_sha256,
        source_path,
        None,
        jsonb(record),
    )


def chunk_row(record: dict, chunk_run_id, *, publication_year: int) -> tuple:
    year = record.get("publication_year")
    if year is None:
        year = publication_year
    return (
        record["chunk_id"],
        record["document_id"],
        chunk_run_id,
        record["schema_version"],
        record["source_oid"],
        record.get("skm_number"),
        record["chunker_version"],
        record["chunk_config_sha256"],
        record["chunk_index"],
        record.get("publication_date"),
        record.get("decision_date"),
        year,
        record.get("document_type"),
        record.get("authority"),
        record.get("case_number"),
        record.get("subject_terms") or [],
        record["source_url"],
        record["section_type"],
        record["legal_weight"],
        record.get("section_heading_original"),
        record.get("section_heading_normalized"),
        record.get("section_path_original") or [],
        record.get("section_path_normalized") or [],
        record["classification_method"],
        record.get("question_number"),
        record["is_final_result"],
        record["chunk_kind"],
        record["chunk_text"],
        record.get("decision_context") or "",
        record["embedding_text"],
        record["contains_table"],
        record["contains_image"],
        record["contains_ocr"],
        record.get("previous_chunk_id"),
        record.get("next_chunk_id"),
        record["manual_source_check"],
        record["token_count"],
        record["text_sha256"],
        record["embedding_text_sha256"],
        jsonb(record),
    )


CHUNK_COLUMNS = """
    chunk_id, document_id, chunk_run_id, schema_version, source_oid, skm_number,
    chunker_version, chunk_config_sha256, chunk_index, publication_date,
    decision_date, publication_year, document_type, authority, case_number,
    subject_terms, source_url, section_type, legal_weight,
    section_heading_original, section_heading_normalized,
    section_path_original, section_path_normalized, classification_method,
    question_number, is_final_result, chunk_kind, chunk_text, decision_context,
    embedding_text, contains_table, contains_image, contains_ocr,
    previous_chunk_id, next_chunk_id, manual_source_check, token_count,
    text_sha256, embedding_text_sha256, raw_record
"""


def span_rows(record: dict) -> list[tuple]:
    rows = []
    for index, span in enumerate(record.get("source_spans") or []):
        rows.append(
            (
                record["chunk_id"],
                index,
                span["source"],
                span["start"],
                span["end"],
                span["role"],
            )
        )
    return rows


def reference_row(
    record: dict,
    *,
    canonical_sha: str,
    occurrence_index: int,
    reference_key: str,
    known_document_ids: set[str] | None = None,
) -> tuple:
    from backend.db.skat_retrieval.law_refs import normalized_reference_columns

    jsonl_target = record.get("target_document_id")
    target = jsonl_target
    original_target = None
    status = record["resolution_status"]
    missing = (
        bool(jsonl_target)
        and known_document_ids is not None
        and jsonl_target not in known_document_ids
    )
    if missing:
        if status == "resolved":
            raise MissingResolvedTargetError(
                f"resolved reference {record.get('cited_identifier')} "
                f"peger på manglende target_document_id {jsonl_target}"
            )
        # unresolved/external: bevar JSONL-id uden for FK-feltet.
        original_target = jsonl_target
        target = None
    normalized = (
        normalized_reference_columns(
            record.get("cited_identifier") or record.get("exact_reference_text") or ""
        )
        if record.get("reference_type") == "law_section"
        else (None,) * 8
    )
    return (
        str(reference_id(reference_key)),
        reference_key,
        record["source_document_id"],
        record.get("source_chunk_id"),
        record["reference_type"],
        record.get("cited_identifier"),
        record["exact_reference_text"],
        target,
        record.get("target_url"),
        status,
        canonical_sha,
        occurrence_index,
        original_target,
        jsonb(record),
    ) + normalized
