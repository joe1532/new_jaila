"""Deterministisk, stratificeret udsnit til embedding-pilot."""

from __future__ import annotations

from dataclasses import dataclass

from backend.db.skat_embed.constants import PILOT_SELECTION_KEY, PILOT_SIZE

DECADE_BOUNDS = (
    (2001, 2009, "2001-2009"),
    (2010, 2019, "2010-2019"),
    (2020, 2026, "2020-2026"),
)


@dataclass(frozen=True)
class SelectedChunk:
    chunk_id: str
    publication_year: int
    section_type: str
    legal_weight: str
    is_final_result: bool
    manual_source_check: bool
    token_count: int
    embedding_text_sha256: str


def _fetch(cur, sql: str, params: tuple = ()) -> list[dict]:
    cur.execute(sql, params)
    cols = [col.name for col in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _add(selected: dict[str, dict], rows: list[dict], limit: int | None = None) -> None:
    taken = 0
    for row in rows:
        if limit is not None and taken >= limit:
            return
        chunk_id = row["chunk_id"]
        if chunk_id in selected:
            continue
        selected[chunk_id] = row
        taken += 1


def select_pilot_chunks(conn, *, size: int = PILOT_SIZE) -> list[SelectedChunk]:
    """Alle årtier, section_type, legal_weight, resultat, begrundelse, resumé og manual_source_check."""
    selected: dict[str, dict] = {}
    with conn.cursor() as cur:
        section_types = [
            row["section_type"]
            for row in _fetch(cur, "SELECT DISTINCT section_type FROM skat.chunks ORDER BY 1")
        ]
        legal_weights = [
            row["legal_weight"]
            for row in _fetch(cur, "SELECT DISTINCT legal_weight FROM skat.chunks ORDER BY 1")
        ]
        per_section = max(4, size // max(len(section_types) * 4, 1))
        per_weight = max(4, size // max(len(legal_weights) * 6, 1))

        for low, high, _label in DECADE_BOUNDS:
            _add(
                selected,
                _fetch(
                    cur,
                    """
                    SELECT chunk_id, publication_year, section_type, legal_weight,
                           is_final_result, manual_source_check, token_count,
                           embedding_text_sha256
                    FROM skat.chunks
                    WHERE publication_year BETWEEN %s AND %s
                    ORDER BY chunk_id
                    LIMIT %s
                    """,
                    (low, high, 80),
                ),
            )
        for section_type in section_types:
            _add(
                selected,
                _fetch(
                    cur,
                    """
                    SELECT chunk_id, publication_year, section_type, legal_weight,
                           is_final_result, manual_source_check, token_count,
                           embedding_text_sha256
                    FROM skat.chunks
                    WHERE section_type = %s
                    ORDER BY chunk_id
                    LIMIT %s
                    """,
                    (section_type, per_section),
                ),
            )
        for legal_weight in legal_weights:
            _add(
                selected,
                _fetch(
                    cur,
                    """
                    SELECT chunk_id, publication_year, section_type, legal_weight,
                           is_final_result, manual_source_check, token_count,
                           embedding_text_sha256
                    FROM skat.chunks
                    WHERE legal_weight = %s
                    ORDER BY chunk_id
                    LIMIT %s
                    """,
                    (legal_weight, per_weight),
                ),
            )
        for sql, params in (
            (
                """
                SELECT chunk_id, publication_year, section_type, legal_weight,
                       is_final_result, manual_source_check, token_count,
                       embedding_text_sha256
                FROM skat.chunks
                WHERE is_final_result = true
                ORDER BY chunk_id
                LIMIT %s
                """,
                (60,),
            ),
            (
                """
                SELECT chunk_id, publication_year, section_type, legal_weight,
                       is_final_result, manual_source_check, token_count,
                       embedding_text_sha256
                FROM skat.chunks
                WHERE legal_weight = 'authoritative_reasoning'
                ORDER BY chunk_id
                LIMIT %s
                """,
                (60,),
            ),
            (
                """
                SELECT chunk_id, publication_year, section_type, legal_weight,
                       is_final_result, manual_source_check, token_count,
                       embedding_text_sha256
                FROM skat.chunks
                WHERE section_type = 'summary'
                ORDER BY chunk_id
                LIMIT %s
                """,
                (60,),
            ),
            (
                """
                SELECT chunk_id, publication_year, section_type, legal_weight,
                       is_final_result, manual_source_check, token_count,
                       embedding_text_sha256
                FROM skat.chunks
                WHERE manual_source_check = true
                ORDER BY chunk_id
                LIMIT %s
                """,
                (40,),
            ),
        ):
            _add(selected, _fetch(cur, sql, params))

        if len(selected) < size:
            needed = size - len(selected)
            already = list(selected)
            _add(
                selected,
                _fetch(
                    cur,
                    """
                    SELECT chunk_id, publication_year, section_type, legal_weight,
                           is_final_result, manual_source_check, token_count,
                           embedding_text_sha256
                    FROM skat.chunks
                    WHERE NOT (chunk_id = ANY(%s))
                    ORDER BY md5(chunk_id || %s), chunk_id
                    LIMIT %s
                    """,
                    (already or [""], PILOT_SELECTION_KEY, needed),
                ),
            )

    rows = list(selected.values())
    rows.sort(key=lambda row: row["chunk_id"])
    if len(rows) < size:
        raise RuntimeError(f"kunne kun udvælge {len(rows)} chunks til pilot; forventet {size}")
    if len(rows) > size:
        rows = rows[:size]
    return [
        SelectedChunk(
            chunk_id=row["chunk_id"],
            publication_year=int(row["publication_year"]),
            section_type=row["section_type"],
            legal_weight=row["legal_weight"],
            is_final_result=bool(row["is_final_result"]),
            manual_source_check=bool(row["manual_source_check"]),
            token_count=int(row["token_count"]),
            embedding_text_sha256=row["embedding_text_sha256"],
        )
        for row in rows
    ]


def coverage_report(chunks: list[SelectedChunk], conn) -> dict[str, object]:
    decades = {label: 0 for _low, _high, label in DECADE_BOUNDS}
    for chunk in chunks:
        for low, high, label in DECADE_BOUNDS:
            if low <= chunk.publication_year <= high:
                decades[label] += 1
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT section_type FROM skat.chunks ORDER BY 1")
        all_sections = {row[0] for row in cur.fetchall()}
        cur.execute("SELECT DISTINCT legal_weight FROM skat.chunks ORDER BY 1")
        all_weights = {row[0] for row in cur.fetchall()}
    got_sections = {chunk.section_type for chunk in chunks}
    got_weights = {chunk.legal_weight for chunk in chunks}
    return {
        "n": len(chunks),
        "decades": decades,
        "section_types": sorted(got_sections),
        "missing_section_types": sorted(all_sections - got_sections),
        "legal_weights": sorted(got_weights),
        "missing_legal_weights": sorted(all_weights - got_weights),
        "final_result": sum(1 for chunk in chunks if chunk.is_final_result),
        "authoritative_reasoning": sum(
            1 for chunk in chunks if chunk.legal_weight == "authoritative_reasoning"
        ),
        "summary": sum(1 for chunk in chunks if chunk.section_type == "summary"),
        "manual_source_check": sum(1 for chunk in chunks if chunk.manual_source_check),
    }
