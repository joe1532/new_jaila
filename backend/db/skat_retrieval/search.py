"""Lexical retrieval-baseline. Dansk FTS, trigram, emneord og titel. Ingen embeddings."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace

from backend.db.skat_retrieval.law_refs import (
    is_bare_law_reference,
    law_reference_variants,
    structured_reference_payload,
)
from backend.db.skat_retrieval.routing import fold
from backend.db.skat_retrieval.settings import LEXICAL_CANDIDATE_LIMIT


@dataclass(frozen=True)
class SearchHit:
    document_id: str
    skm_number: str | None
    chunk_id: str
    title: str
    chunk_text: str
    section_type: str
    legal_weight: str
    is_final_result: bool
    source_url: str
    manual_source_check: bool
    rank_score: float
    signals: tuple[str, ...] = field(default_factory=tuple)
    source_oid: str | None = None
    publication_year: int | None = None
    document_type: str | None = None
    topics: tuple[str, ...] = field(default_factory=tuple)
    chunk_index: int | None = None
    token_count: int | None = None
    lexical_rank: int | None = None
    vector_rank: int | None = None
    rrf_score: float | None = None
    score_kind: str = "lexical_rank_score"


SEARCH_SQL = """
WITH params AS (
    SELECT
        %s::text AS q_raw,
        skat.immutable_unaccent(%s::text) AS q_fold,
        NULLIF(plainto_tsquery('danish'::regconfig, skat.immutable_unaccent(%s::text)), ''::tsquery) AS tsq,
        %s::int AS year_from,
        %s::int AS year_to,
        %s::text AS authority,
        %s::text AS document_type,
        %s::text AS section_type,
        %s::text AS legal_weight,
        %s::boolean AS is_final_result,
        %s::text[] AS subject_terms,
        %s::text AS topic,
        %s::int AS seed_limit
),
fts AS MATERIALIZED (
    SELECT c.chunk_id
    FROM skat.chunks AS c
    CROSS JOIN params AS p
    WHERE p.tsq IS NOT NULL
      AND c.search_vector @@ p.tsq
      AND (p.year_from IS NULL OR c.publication_year >= p.year_from)
      AND (p.year_to IS NULL OR c.publication_year <= p.year_to)
      AND (p.authority IS NULL OR c.authority = p.authority)
      AND (p.document_type IS NULL OR c.document_type = p.document_type)
      AND (p.section_type IS NULL OR c.section_type = p.section_type)
      AND (p.legal_weight IS NULL OR c.legal_weight = p.legal_weight)
      AND (p.is_final_result IS NULL OR c.is_final_result = p.is_final_result)
    ORDER BY ts_rank_cd(c.search_vector, p.tsq) DESC, c.chunk_id
    LIMIT (SELECT seed_limit FROM params)
),
meta_ids AS MATERIALIZED (
    SELECT c.chunk_id
    FROM skat.chunks AS c
    JOIN skat.legal_documents AS d ON d.document_id = c.document_id
    CROSS JOIN params AS p
    WHERE p.q_raw <> ''
      AND (p.year_from IS NULL OR c.publication_year >= p.year_from)
      AND (p.year_to IS NULL OR c.publication_year <= p.year_to)
      AND (p.authority IS NULL OR c.authority = p.authority)
      AND (p.document_type IS NULL OR c.document_type = p.document_type)
      AND (p.section_type IS NULL OR c.section_type = p.section_type)
      AND (p.legal_weight IS NULL OR c.legal_weight = p.legal_weight)
      AND (p.is_final_result IS NULL OR c.is_final_result = p.is_final_result)
      AND (
            (d.skm_number IS NOT NULL
             AND upper(replace(d.skm_number, ' ', '')) = upper(replace(p.q_raw, ' ', '')))
         OR d.document_id = p.q_raw
         OR d.source_oid = p.q_raw
         OR d.document_id = 'skat-info:oid:' || p.q_raw
      )
    ORDER BY c.chunk_id
    LIMIT (SELECT seed_limit FROM params)
),
meta_terms AS MATERIALIZED (
    SELECT c.chunk_id
    FROM skat.chunks AS c
    CROSS JOIN params AS p
    WHERE p.subject_terms IS NOT NULL
      AND c.subject_terms && p.subject_terms
      AND (p.year_from IS NULL OR c.publication_year >= p.year_from)
      AND (p.year_to IS NULL OR c.publication_year <= p.year_to)
      AND (p.authority IS NULL OR c.authority = p.authority)
      AND (p.document_type IS NULL OR c.document_type = p.document_type)
      AND (p.section_type IS NULL OR c.section_type = p.section_type)
      AND (p.legal_weight IS NULL OR c.legal_weight = p.legal_weight)
      AND (p.is_final_result IS NULL OR c.is_final_result = p.is_final_result)
    ORDER BY c.chunk_id
    LIMIT (SELECT seed_limit FROM params)
),
meta_topic AS MATERIALIZED (
    SELECT c.chunk_id
    FROM skat.chunks AS c
    JOIN skat.legal_documents AS d ON d.document_id = c.document_id
    CROSS JOIN params AS p
    WHERE p.topic IS NOT NULL
      AND (d.main_topic = p.topic OR c.subject_terms && ARRAY[p.topic])
      AND (p.year_from IS NULL OR c.publication_year >= p.year_from)
      AND (p.year_to IS NULL OR c.publication_year <= p.year_to)
      AND (p.authority IS NULL OR c.authority = p.authority)
      AND (p.document_type IS NULL OR c.document_type = p.document_type)
      AND (p.section_type IS NULL OR c.section_type = p.section_type)
      AND (p.legal_weight IS NULL OR c.legal_weight = p.legal_weight)
      AND (p.is_final_result IS NULL OR c.is_final_result = p.is_final_result)
    ORDER BY c.chunk_id
    LIMIT (SELECT seed_limit FROM params)
),
title_docs AS MATERIALIZED (
    SELECT d.document_id
    FROM skat.legal_documents AS d
    CROSS JOIN params AS p
    WHERE p.subject_terms IS NOT NULL
      AND (p.year_from IS NULL OR d.publication_year >= p.year_from)
      AND (p.year_to IS NULL OR d.publication_year <= p.year_to)
      AND (p.authority IS NULL OR d.authority = p.authority)
      AND (p.document_type IS NULL OR d.document_type = p.document_type)
      AND EXISTS (
          SELECT 1
          FROM unnest(p.subject_terms) AS tok
          WHERE skat.immutable_unaccent(d.title) ILIKE '%%' || tok || '%%'
      )
    LIMIT 50
),
title_chunks AS (
    SELECT DISTINCT ON (c.document_id) c.chunk_id
    FROM skat.chunks AS c
    JOIN title_docs AS t ON t.document_id = c.document_id
    CROSS JOIN params AS p
    WHERE (p.year_from IS NULL OR c.publication_year >= p.year_from)
      AND (p.year_to IS NULL OR c.publication_year <= p.year_to)
      AND (p.authority IS NULL OR c.authority = p.authority)
      AND (p.document_type IS NULL OR c.document_type = p.document_type)
      AND (p.section_type IS NULL OR c.section_type = p.section_type)
      AND (p.legal_weight IS NULL OR c.legal_weight = p.legal_weight)
      AND (p.is_final_result IS NULL OR c.is_final_result = p.is_final_result)
    ORDER BY c.document_id, c.chunk_index, c.chunk_id
),
candidates AS MATERIALIZED (
    SELECT chunk_id FROM fts
    UNION
    SELECT chunk_id FROM meta_ids
    UNION
    SELECT chunk_id FROM meta_terms
    UNION
    SELECT chunk_id FROM meta_topic
    UNION
    SELECT chunk_id FROM title_chunks
),
scored AS (
    SELECT
        c.document_id,
        c.skm_number,
        c.chunk_id,
        d.title,
        c.section_type,
        c.legal_weight,
        c.is_final_result,
        c.source_url,
        c.manual_source_check,
        c.chunk_index,
        d.source_oid,
        c.publication_year,
        c.document_type,
        d.subject_terms,
        c.token_count,
        (
            CASE
                WHEN d.skm_number IS NOT NULL
                     AND upper(replace(d.skm_number, ' ', '')) = upper(replace(p.q_raw, ' ', ''))
                THEN 1000 ELSE 0
            END
            + CASE
                WHEN d.document_id = p.q_raw
                  OR d.source_oid = p.q_raw
                  OR d.document_id = 'skat-info:oid:' || p.q_raw
                THEN 1000 ELSE 0
            END
            + CASE
                WHEN p.subject_terms IS NOT NULL
                 AND c.subject_terms && p.subject_terms
                THEN 180 ELSE 0
            END
            + CASE
                WHEN p.subject_terms IS NOT NULL
                 AND EXISTS (
                    SELECT 1
                    FROM unnest(p.subject_terms) AS tok
                    WHERE skat.immutable_unaccent(d.title) ILIKE '%%' || tok || '%%'
                )
                THEN 120 ELSE 0
            END
            + CASE
                WHEN p.subject_terms IS NOT NULL
                 AND EXISTS (
                    SELECT 1
                    FROM unnest(p.subject_terms) AS tok
                    WHERE skat.immutable_unaccent(coalesce(c.section_heading_normalized, ''))
                          ILIKE '%%' || tok || '%%'
                )
                THEN 90 ELSE 0
            END
            + CASE
                WHEN p.tsq IS NOT NULL
                THEN round(ts_rank_cd(c.search_vector, p.tsq) * 400.0)::numeric
                ELSE 0
            END
        )::numeric AS rank_score,
        (
            ARRAY_remove(ARRAY[
                CASE
                    WHEN d.skm_number IS NOT NULL
                     AND upper(replace(d.skm_number, ' ', '')) = upper(replace(p.q_raw, ' ', ''))
                    THEN 'eksakt SKM-nummer' END,
                CASE
                    WHEN d.document_id = p.q_raw
                      OR d.source_oid = p.q_raw
                      OR d.document_id = 'skat-info:oid:' || p.q_raw
                    THEN 'eksakt OID' END,
                CASE
                    WHEN p.subject_terms IS NOT NULL
                     AND c.subject_terms && p.subject_terms
                    THEN 'emneord' END,
                CASE
                    WHEN p.subject_terms IS NOT NULL
                     AND EXISTS (
                        SELECT 1
                        FROM unnest(p.subject_terms) AS tok
                        WHERE skat.immutable_unaccent(d.title) ILIKE '%%' || tok || '%%'
                    )
                    THEN 'titel' END,
                CASE
                    WHEN p.subject_terms IS NOT NULL
                     AND EXISTS (
                        SELECT 1
                        FROM unnest(p.subject_terms) AS tok
                        WHERE skat.immutable_unaccent(coalesce(c.section_heading_normalized, ''))
                              ILIKE '%%' || tok || '%%'
                    )
                    THEN 'afsnitsoverskrift' END,
                CASE
                    WHEN p.tsq IS NOT NULL AND c.search_vector @@ p.tsq
                    THEN 'dansk full-text' END
            ], NULL)
        ) AS signals
    FROM candidates AS k
    JOIN skat.chunks AS c ON c.chunk_id = k.chunk_id
    JOIN skat.legal_documents AS d ON d.document_id = c.document_id
    CROSS JOIN params AS p
    WHERE
        (p.year_from IS NULL OR c.publication_year >= p.year_from)
        AND (p.year_to IS NULL OR c.publication_year <= p.year_to)
        AND (p.authority IS NULL OR c.authority = p.authority)
        AND (p.document_type IS NULL OR c.document_type = p.document_type)
        AND (p.section_type IS NULL OR c.section_type = p.section_type)
        AND (p.legal_weight IS NULL OR c.legal_weight = p.legal_weight)
        AND (p.is_final_result IS NULL OR c.is_final_result = p.is_final_result)
        AND (p.topic IS NULL OR d.main_topic = p.topic OR c.subject_terms && ARRAY[p.topic])
)
SELECT
    document_id, skm_number, chunk_id, title, section_type,
    legal_weight, is_final_result, source_url, manual_source_check,
    rank_score, signals, source_oid, publication_year, document_type,
    subject_terms, chunk_index, token_count
FROM (
    SELECT
        scored.*,
        row_number() OVER (
            PARTITION BY document_id
            ORDER BY rank_score DESC, chunk_index, chunk_id
        ) AS document_rank
    FROM scored
    WHERE rank_score > 0
) AS best
WHERE document_rank = 1
ORDER BY rank_score DESC, document_id, chunk_index, chunk_id
LIMIT %s
"""

HYDRATE_SQL = """
SELECT
    c.document_id, c.skm_number, c.chunk_id, d.title, c.chunk_text,
    c.section_type, c.legal_weight, c.is_final_result, c.source_url,
    c.manual_source_check, d.source_oid, c.publication_year, c.document_type,
    d.subject_terms, c.chunk_index, c.token_count
FROM skat.chunks AS c
JOIN skat.legal_documents AS d ON d.document_id = c.document_id
WHERE c.chunk_id = ANY(%s)
"""

# Samme opslag uden chunk_text, så fusion kan køre før fuld hydration.
CANDIDATE_META_SQL = """
SELECT
    c.document_id, c.skm_number, c.chunk_id, d.title, NULL::text AS chunk_text,
    c.section_type, c.legal_weight, c.is_final_result, c.source_url,
    c.manual_source_check, d.source_oid, c.publication_year, c.document_type,
    d.subject_terms, c.chunk_index, c.token_count
FROM skat.chunks AS c
JOIN skat.legal_documents AS d ON d.document_id = c.document_id
WHERE c.chunk_id = ANY(%s)
"""


REFERENCE_CANDIDATE_SQL = """
WITH params AS (
    SELECT
        %s::jsonb AS structured_references,
        %s::int AS required_matches,
        %s::text[] AS legacy_variants,
        %s::int AS year_from,
        %s::int AS year_to,
        %s::text AS authority,
        %s::text AS document_type,
        %s::text AS section_type,
        %s::text AS legal_weight,
        %s::boolean AS is_final_result,
        %s::text AS topic,
        %s::int AS result_limit
),
query_refs AS MATERIALIZED (
    SELECT
        q.ordinal, q.law_key, q.section_number,
        COALESCE(q.section_suffix, '') AS section_suffix,
        q.section_end_number,
        COALESCE(q.section_end_suffix, '') AS section_end_suffix,
        q.subsection, q.item_number, q.letter
    FROM params AS p
    CROSS JOIN LATERAL jsonb_to_recordset(p.structured_references) AS q(
        ordinal int,
        law_key text,
        section_number int,
        section_suffix text,
        section_end_number int,
        section_end_suffix text,
        subsection text,
        item_number text,
        letter text
    )
),
structured_matches AS MATERIALIZED (
    SELECT
        q.ordinal,
        r.source_document_id,
        r.source_chunk_id,
        (
            CASE
                WHEN q.subsection IS NULL THEN 0
                WHEN r.cited_subsection = q.subsection THEN 8
                WHEN r.cited_subsection IS NULL THEN 2
                ELSE 0
            END
            + CASE
                WHEN q.item_number IS NULL THEN 0
                WHEN r.cited_item_number = q.item_number THEN 4
                WHEN r.cited_item_number IS NULL THEN 1
                ELSE 0
            END
            + CASE
                WHEN q.letter IS NULL THEN 0
                WHEN r.cited_letter = q.letter THEN 2
                ELSE 0
            END
        )::int AS specificity
    FROM query_refs AS q
    JOIN skat.document_references AS r
      ON r.cited_law_key = q.law_key
     AND ROW(r.cited_section_number, COALESCE(r.cited_section_suffix, ''))
         <= ROW(COALESCE(q.section_end_number, q.section_number),
                CASE WHEN q.section_end_number IS NULL
                     THEN q.section_suffix ELSE q.section_end_suffix END)
     AND ROW(COALESCE(r.cited_section_end_number, r.cited_section_number),
             CASE WHEN r.cited_section_end_number IS NULL
                  THEN COALESCE(r.cited_section_suffix, '')
                  ELSE COALESCE(r.cited_section_end_suffix, '') END)
         >= ROW(q.section_number, q.section_suffix)
    WHERE r.cited_law_key IS NOT NULL
      AND r.source_chunk_id IS NOT NULL
),
legacy_matches AS MATERIALIZED (
    SELECT
        1 AS ordinal,
        r.source_document_id,
        r.source_chunk_id,
        0 AS specificity
    FROM skat.document_references AS r
    CROSS JOIN params AS p
    WHERE jsonb_array_length(p.structured_references) = 1
      AND NOT EXISTS (SELECT 1 FROM structured_matches)
      AND r.cited_law_key IS NULL
      AND r.source_chunk_id IS NOT NULL
      AND r.cited_identifier = ANY(p.legacy_variants)
),
raw_matches AS MATERIALIZED (
    SELECT * FROM structured_matches
    UNION ALL
    SELECT * FROM legacy_matches
),
eligible_documents AS MATERIALIZED (
    SELECT
        m.source_document_id,
        count(DISTINCT m.ordinal)::int AS matched_references,
        count(*)::int AS document_matches
    FROM raw_matches AS m
    CROSS JOIN params AS p
    GROUP BY m.source_document_id, p.required_matches
    HAVING count(DISTINCT m.ordinal) >= p.required_matches
),
matched_chunks AS MATERIALIZED (
    SELECT
        m.source_document_id,
        m.source_chunk_id,
        count(DISTINCT m.ordinal)::int AS chunk_reference_matches,
        max(m.specificity)::int AS specificity
    FROM raw_matches AS m
    GROUP BY m.source_document_id, m.source_chunk_id
),
ranked AS (
    SELECT
        c.document_id, c.skm_number, c.chunk_id, d.title,
        c.section_type, c.legal_weight, c.is_final_result, c.source_url,
        c.manual_source_check,
        (
            600
            + 100 * e.matched_references
            + 10 * m.specificity
            + least(e.document_matches, 99)
        )::numeric AS rank_score,
        ARRAY['struktureret lovhenvisning']::text[] AS signals,
        d.source_oid, c.publication_year, c.document_type, d.subject_terms,
        c.chunk_index, c.token_count,
        row_number() OVER (
            PARTITION BY c.document_id
            ORDER BY
                e.matched_references DESC,
                m.specificity DESC,
                m.chunk_reference_matches DESC,
                e.document_matches DESC,
                CASE c.legal_weight
                    WHEN 'authoritative_reasoning' THEN 0
                    WHEN 'source_material' THEN 1
                    WHEN 'editorial' THEN 2
                    ELSE 3
                END,
                c.chunk_index,
                c.chunk_id
        ) AS document_rank
    FROM matched_chunks AS m
    JOIN eligible_documents AS e ON e.source_document_id = m.source_document_id
    JOIN skat.chunks AS c ON c.chunk_id = m.source_chunk_id
    JOIN skat.legal_documents AS d ON d.document_id = c.document_id
    CROSS JOIN params AS p
    WHERE (p.year_from IS NULL OR c.publication_year >= p.year_from)
      AND (p.year_to IS NULL OR c.publication_year <= p.year_to)
      AND (p.authority IS NULL OR c.authority = p.authority)
      AND (p.document_type IS NULL OR c.document_type = p.document_type)
      AND (p.section_type IS NULL OR c.section_type = p.section_type)
      AND (p.legal_weight IS NULL OR c.legal_weight = p.legal_weight)
      AND (p.is_final_result IS NULL OR c.is_final_result = p.is_final_result)
      AND (p.topic IS NULL OR d.main_topic = p.topic OR c.subject_terms && ARRAY[p.topic])
)
SELECT
    document_id, skm_number, chunk_id, title, section_type,
    legal_weight, is_final_result, source_url, manual_source_check,
    rank_score, signals, source_oid, publication_year, document_type,
    subject_terms, chunk_index, token_count
FROM ranked
WHERE document_rank = 1
ORDER BY rank_score DESC, document_id, chunk_index, chunk_id
LIMIT (SELECT result_limit FROM params)
"""


def _as_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _as_text(value: object) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


QUERY_STOPWORDS = {
    "find",
    "sager",
    "hvad",
    "hvilke",
    "hvilken",
    "giver",
    "give",
    "vis",
    "finde",
    "omkring",
}


def _subject_terms(query: str, extra: object) -> list[str] | None:
    terms: list[str] = []
    if extra:
        if isinstance(extra, (list, tuple)):
            terms.extend(str(item) for item in extra)
        else:
            terms.append(str(extra))
    for token in fold(query).replace(",", " ").split():
        if len(token) >= 4 and token not in QUERY_STOPWORDS:
            terms.append(token)
    unique = list(dict.fromkeys(terms))
    return unique or None


def hydrate_hits(conn, hits: list[SearchHit], *, include_text: bool = True) -> list[SearchHit]:
    """Hent metadata (og valgfrit chunk-tekst) for et lille kandidatsæt. Ingen N+1."""
    if not hits:
        return []
    ids = [hit.chunk_id for hit in hits]
    sql = HYDRATE_SQL if include_text else CANDIDATE_META_SQL
    with conn.cursor() as cur:
        cur.execute(sql, (ids,))
        rows = cur.fetchall()
    by_id = {}
    for row in rows:
        by_id[row[2]] = row
    hydrated = []
    for hit in hits:
        row = by_id.get(hit.chunk_id)
        if row is None:
            hydrated.append(hit)
            continue
        hydrated.append(
            replace(
                hit,
                document_id=row[0],
                skm_number=row[1],
                title=row[3],
                chunk_text=(row[4] or "") if include_text else hit.chunk_text,
                section_type=row[5],
                legal_weight=row[6],
                is_final_result=bool(row[7]),
                source_url=row[8],
                manual_source_check=bool(row[9]),
                source_oid=row[10],
                publication_year=int(row[11]) if row[11] is not None else None,
                document_type=row[12],
                topics=tuple(row[13] or ()),
                chunk_index=int(row[14]) if row[14] is not None else None,
                token_count=int(row[15]) if row[15] is not None else None,
            )
        )
    return hydrated


def _lexical_params(query: str, filters: dict[str, object], limit: int) -> tuple:
    year = filters.get("year")
    year_from = _as_int(filters.get("year_from", year))
    year_to = _as_int(filters.get("year_to", year))
    q_raw = (query or "").strip()
    q_fold = fold(q_raw)
    seed_limit = max(int(limit), LEXICAL_CANDIDATE_LIMIT)
    return (
        q_raw,
        q_fold,
        q_fold,
        year_from,
        year_to,
        _as_text(filters.get("authority")),
        _as_text(filters.get("document_type")),
        _as_text(filters.get("section_type")),
        _as_text(filters.get("legal_weight")),
        None if filters.get("is_final_result") is None else bool(filters.get("is_final_result")),
        _subject_terms(q_raw, filters.get("subject_terms")),
        _as_text(filters.get("topic")),
        seed_limit,
        max(1, int(limit)),
    )


def _reference_params(query: str, filters: dict[str, object], limit: int) -> tuple | None:
    structured, required_matches = structured_reference_payload(query)
    if not structured:
        return None
    variants = law_reference_variants(query)
    year = filters.get("year")
    return (
        json.dumps(structured, ensure_ascii=False),
        required_matches,
        list(variants),
        _as_int(filters.get("year_from", year)),
        _as_int(filters.get("year_to", year)),
        _as_text(filters.get("authority")),
        _as_text(filters.get("document_type")),
        _as_text(filters.get("section_type")),
        _as_text(filters.get("legal_weight")),
        None if filters.get("is_final_result") is None else bool(filters.get("is_final_result")),
        _as_text(filters.get("topic")),
        max(int(limit), LEXICAL_CANDIDATE_LIMIT),
    )


def _rows_to_lexical_hits(rows) -> list[SearchHit]:
    hits = []
    for row in rows:
        hits.append(
            SearchHit(
                document_id=row[0],
                skm_number=row[1],
                chunk_id=row[2],
                title=row[3],
                chunk_text="",
                section_type=row[4],
                legal_weight=row[5],
                is_final_result=bool(row[6]),
                source_url=row[7],
                manual_source_check=bool(row[8]),
                rank_score=float(row[9]),
                signals=tuple(row[10] or ()),
                source_oid=row[11],
                publication_year=int(row[12]) if row[12] is not None else None,
                document_type=row[13],
                topics=tuple(row[14] or ()),
                chunk_index=int(row[15]) if row[15] is not None else None,
                token_count=int(row[16]) if row[16] is not None else None,
                score_kind="lexical_rank_score",
            )
        )
    return hits


def _best_lexical_per_document(hits: list[SearchHit]) -> list[SearchHit]:
    chosen: dict[str, SearchHit] = {}
    for hit in hits:
        current = chosen.get(hit.document_id)
        if current is None:
            chosen[hit.document_id] = hit
            continue
        hit_key = (-hit.rank_score, hit.chunk_index or 0, hit.chunk_id)
        current_key = (-current.rank_score, current.chunk_index or 0, current.chunk_id)
        if hit_key < current_key:
            chosen[hit.document_id] = hit
    return sorted(
        chosen.values(),
        key=lambda hit: (-hit.rank_score, hit.document_id, hit.chunk_index or 0, hit.chunk_id),
    )


def lexical_search(
    conn,
    query: str,
    *,
    limit: int = 10,
    filters: dict[str, object] | None = None,
    hydrate: bool = True,
) -> list[SearchHit]:
    """Lexical ranking med tidlig kandidatbegrænsning. Ingen embeddings."""
    filters = filters or {}
    params = _lexical_params(query, filters, limit)
    with conn.cursor() as cur:
        if is_bare_law_reference(query):
            rows = []
        else:
            cur.execute(SEARCH_SQL, params)
            rows = cur.fetchall()
        reference_params = _reference_params(query, filters, limit)
        reference_rows = []
        if reference_params is not None:
            cur.execute(REFERENCE_CANDIDATE_SQL, reference_params)
            reference_rows = cur.fetchall()
    hits = _best_lexical_per_document(
        _rows_to_lexical_hits(rows) + _rows_to_lexical_hits(reference_rows)
    )[: max(1, int(limit))]
    hits = [replace(hit, lexical_rank=index) for index, hit in enumerate(hits, start=1)]
    if hydrate:
        return hydrate_hits(conn, hits)
    return hits
