"""Eksakte opslag via eksisterende SQL-funktioner. Ingen embeddings."""

from __future__ import annotations

from dataclasses import dataclass

from backend.db.skat_retrieval.errors import IdentifierNotFoundError, RetrievalIntegrityError


DOCUMENT_COLUMNS = (
    "document_id",
    "source_oid",
    "skm_number",
    "title",
    "document_type",
    "authority",
    "publication_year",
    "publication_date",
    "decision_date",
    "source_url",
    "document_status",
    "manual_source_check",
    "summary",
)


@dataclass(frozen=True)
class DocumentRecord:
    document_id: str
    source_oid: str
    skm_number: str | None
    title: str
    document_type: str | None
    authority: str | None
    publication_year: int
    publication_date: object
    decision_date: object
    source_url: str
    document_status: str
    manual_source_check: bool
    summary: str | None


@dataclass(frozen=True)
class ChunkRecord:
    chunk_id: str
    chunk_index: int
    section_type: str
    legal_weight: str
    chunk_text: str
    source_url: str
    manual_source_check: bool | None = None
    is_final_result: bool | None = None
    token_count: int | None = None


@dataclass(frozen=True)
class ReferenceRecord:
    direction: str
    reference_id: str
    reference_key: str
    reference_type: str
    cited_identifier: str | None
    exact_reference_text: str
    source_document_id: str
    source_chunk_id: str | None
    target_document_id: str | None
    target_url: str | None
    resolution_status: str
    occurrence_index: int | None = None
    original_target_document_id: str | None = None
    source_url: str | None = None


def get_document(conn, identifier: str) -> DocumentRecord:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM skat.get_document_by_identifier(%s)", (identifier,))
        row = cur.fetchone()
        if not row:
            raise IdentifierNotFoundError(
                "Dokumentet blev ikke fundet",
                details={"identifier": identifier},
            )
        cols = {col.name: i for i, col in enumerate(cur.description)}
    return DocumentRecord(*(row[cols[name]] for name in DOCUMENT_COLUMNS))


def get_summary(conn, identifier: str) -> str:
    document = get_document(conn, identifier)
    summary = document.summary or ""
    with conn.cursor() as cur:
        cur.execute("SELECT skat.get_document_summary(%s)", (identifier,))
        from_fn = cur.fetchone()[0] or ""
    if from_fn != summary:
        raise RetrievalIntegrityError(
            "summary-funktionen afviger fra legal_documents.summary"
        )
    return summary


def get_final_result(conn, identifier: str) -> list[ChunkRecord]:
    get_document(conn, identifier)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT f.chunk_id, f.chunk_index, f.section_type, f.legal_weight, f.chunk_text,
                   f.source_url, f.manual_source_check, f.is_final_result, c.token_count
            FROM skat.get_document_final_result(%s) AS f
            JOIN skat.chunks AS c ON c.chunk_id = f.chunk_id
            ORDER BY f.chunk_index, f.chunk_id
            """,
            (identifier,),
        )
        rows = cur.fetchall()
    records = [ChunkRecord(*row) for row in rows]
    if any(not row.is_final_result for row in records):
        raise RetrievalIntegrityError("final_result indeholdt ikke-flaggede chunks")
    return records


def get_reasoning(conn, identifier: str) -> list[ChunkRecord]:
    get_document(conn, identifier)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT r.chunk_id, r.chunk_index, r.section_type, r.legal_weight, r.chunk_text,
                   r.source_url, c.token_count, c.manual_source_check, c.is_final_result
            FROM skat.get_document_reasoning(%s) AS r
            JOIN skat.chunks AS c ON c.chunk_id = r.chunk_id
            ORDER BY r.chunk_index, r.chunk_id
            """,
            (identifier,),
        )
        rows = cur.fetchall()
    records = []
    for row in rows:
        (
            chunk_id,
            chunk_index,
            section_type,
            legal_weight,
            chunk_text,
            source_url,
            token_count,
            manual_source_check,
            is_final_result,
        ) = row
        if legal_weight == "prior_instance":
            raise RetrievalIntegrityError("reasoning indeholdt prior_instance")
        if legal_weight != "authoritative_reasoning":
            raise RetrievalIntegrityError(
                f"reasoning indeholdt legal_weight={legal_weight}"
            )
        records.append(
            ChunkRecord(
                chunk_id=chunk_id,
                chunk_index=chunk_index,
                section_type=section_type,
                legal_weight=legal_weight,
                chunk_text=chunk_text,
                source_url=source_url,
                manual_source_check=manual_source_check,
                is_final_result=is_final_result,
                token_count=token_count,
            )
        )
    return records


def get_section_chunks(conn, identifier: str, section_type: str) -> list[ChunkRecord]:
    document = get_document(conn, identifier)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT chunk_id, chunk_index, section_type, legal_weight, chunk_text,
                   source_url, manual_source_check, is_final_result
            FROM skat.chunks
            WHERE document_id = %s AND section_type = %s
            ORDER BY chunk_index
            """,
            (document.document_id, section_type),
        )
        rows = cur.fetchall()
    return [ChunkRecord(*row) for row in rows]


def count_prior_instance_chunks(conn, identifier: str) -> int:
    document = get_document(conn, identifier)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
            FROM skat.chunks
            WHERE document_id = %s AND legal_weight = 'prior_instance'
            """,
            (document.document_id,),
        )
        return int(cur.fetchone()[0])


def get_references(conn, identifier: str) -> list[ReferenceRecord]:
    get_document(conn, identifier)
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH resolved AS (
                SELECT skat.resolve_document_id(%s) AS document_id
            )
            SELECT
                'outgoing'::text,
                r.reference_id::text,
                r.reference_key,
                r.reference_type,
                r.cited_identifier,
                r.exact_reference_text,
                r.source_document_id,
                r.source_chunk_id,
                r.target_document_id,
                r.target_url,
                r.resolution_status,
                r.occurrence_index,
                r.original_target_document_id,
                src.source_url
            FROM skat.document_references AS r
            JOIN resolved ON r.source_document_id = resolved.document_id
            LEFT JOIN skat.legal_documents AS src ON src.document_id = r.source_document_id
            UNION ALL
            SELECT
                'incoming'::text,
                r.reference_id::text,
                r.reference_key,
                r.reference_type,
                r.cited_identifier,
                r.exact_reference_text,
                r.source_document_id,
                r.source_chunk_id,
                r.target_document_id,
                r.target_url,
                r.resolution_status,
                r.occurrence_index,
                r.original_target_document_id,
                src.source_url
            FROM skat.document_references AS r
            JOIN resolved ON r.target_document_id = resolved.document_id
            LEFT JOIN skat.legal_documents AS src ON src.document_id = r.source_document_id
            ORDER BY 1, 12, 2
            """,
            (identifier,),
        )
        rows = cur.fetchall()
    return [ReferenceRecord(*row) for row in rows]
