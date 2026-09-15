"""Udled draft-evalueringscases fra den importerede database. Ikke fagligt godkendt guld."""

from __future__ import annotations

import json
from pathlib import Path

GOLD_DRAFT = "draft"


def _case(
    eval_id: str,
    query: str,
    query_type: str,
    *,
    document_ids: list[str] | None = None,
    chunk_ids: list[str] | None = None,
    section_types: list[str] | None = None,
    legal_weights: list[str] | None = None,
    forbidden: list[str] | None = None,
    filters: dict | None = None,
    notes: str,
) -> dict:
    return {
        "eval_id": eval_id,
        "query": query,
        "query_type": query_type,
        "expected_document_ids": document_ids or [],
        "expected_chunk_ids": chunk_ids or [],
        "expected_section_types": section_types or [],
        "expected_legal_weights": legal_weights or [],
        "forbidden_legal_weights": forbidden or [],
        "filters": filters or {},
        "notes": notes,
        "gold_status": GOLD_DRAFT,
    }


def _fetch_docs(cur, sql: str, params: tuple = ()) -> list[dict]:
    cur.execute(sql, params)
    cols = [col.name for col in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def write_eval_dataset(conn, output: Path) -> Path:
    cases: list[dict] = []
    with conn.cursor() as cur:
        cases.extend(_exact_cases(cur))
        cases.extend(_summary_cases(cur))
        cases.extend(_result_cases(cur))
        cases.extend(_reasoning_cases(cur))
        cases.extend(_prior_cases(cur))
        cases.extend(_qa_cases(cur))
        cases.extend(_topical_cases(cur))
        cases.extend(_reference_cases(cur))
        cases.extend(_manual_cases(cur))
        cases.extend(_type_and_length_cases(cur))
        cases.extend(_filter_cases(cur))

    if len(cases) < 100:
        raise RuntimeError(f"kun {len(cases)} cases; forventet mindst 100")
    seen = set()
    unique = []
    for case in cases:
        if case["eval_id"] in seen:
            continue
        seen.add(case["eval_id"])
        unique.append(case)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for case in unique:
            handle.write(json.dumps(case, ensure_ascii=False) + "\n")
    return output


def _era_docs(cur, low: int, high: int, limit: int) -> list[dict]:
    return _fetch_docs(
        cur,
        """
        SELECT d.document_id, d.source_oid, d.skm_number, d.publication_year,
               d.document_type, d.authority, d.manual_source_check,
               length(coalesce(d.summary, '')) AS summary_len
        FROM skat.legal_documents AS d
        WHERE d.publication_year BETWEEN %s AND %s
          AND d.skm_number IS NOT NULL
          AND coalesce(d.summary, '') <> ''
        ORDER BY d.skm_number
        LIMIT %s
        """,
        (low, high, limit),
    )


def _exact_cases(cur) -> list[dict]:
    cases = []
    # Kendt pilot-dokument plus OID.
    cases.append(
        _case(
            "draft-exact-skm-2026-46",
            "SKM2026.46.BR",
            "exact_lookup",
            document_ids=["skat-info:oid:2459841"],
            notes="godkendt pilot-SKM; auto-udledt som draft i dette sæt",
        )
    )
    cases.append(
        _case(
            "draft-exact-oid-2459841",
            "skat-info:oid:2459841",
            "exact_lookup",
            document_ids=["skat-info:oid:2459841"],
            notes="OID-opslag for samme dokument",
        )
    )
    cases.append(
        _case(
            "draft-exact-oid-bare-2459841",
            "2459841",
            "exact_lookup",
            document_ids=["skat-info:oid:2459841"],
            notes="bar OID-tal",
        )
    )
    n = 1
    for low, high, tag in ((2001, 2009, "early"), (2010, 2019, "mid"), (2020, 2026, "late")):
        for doc in _era_docs(cur, low, high, 5):
            cases.append(
                _case(
                    f"draft-exact-skm-{tag}-{n:03d}",
                    doc["skm_number"],
                    "exact_lookup",
                    document_ids=[doc["document_id"]],
                    notes=f"eksakt SKM {doc['publication_year']} {doc['document_type']}",
                )
            )
            n += 1
            cases.append(
                _case(
                    f"draft-exact-oid-{tag}-{n:03d}",
                    doc["source_oid"],
                    "exact_lookup",
                    document_ids=[doc["document_id"]],
                    notes=f"eksakt OID {doc['publication_year']}",
                )
            )
            n += 1
    return cases


def _summary_cases(cur) -> list[dict]:
    cases = []
    cases.append(
        _case(
            "draft-summary-2026-46",
            "Giv mig resuméet af SKM2026.46.BR",
            "summary",
            document_ids=["skat-info:oid:2459841"],
            notes="hele legal_documents.summary, ikke chunk",
        )
    )
    n = 1
    for low, high in ((2001, 2009), (2010, 2019), (2020, 2026)):
        docs = _fetch_docs(
            cur,
            """
            SELECT document_id, skm_number, publication_year
            FROM skat.legal_documents
            WHERE publication_year BETWEEN %s AND %s
              AND skm_number IS NOT NULL
              AND length(coalesce(summary, '')) >= 200
            ORDER BY length(summary) DESC, skm_number
            LIMIT 4
            """,
            (low, high),
        )
        for doc in docs:
            cases.append(
                _case(
                    f"draft-summary-{n:03d}",
                    f"Hvad er resuméet af {doc['skm_number']}?",
                    "summary",
                    document_ids=[doc["document_id"]],
                    notes=f"summary {doc['publication_year']}",
                )
            )
            n += 1
    return cases


def _chunk_ids(cur, document_id: str, where_sql: str) -> list[str]:
    cur.execute(
        f"""
        SELECT chunk_id
        FROM skat.chunks
        WHERE document_id = %s AND {where_sql}
        ORDER BY chunk_index
        """,
        (document_id,),
    )
    return [row[0] for row in cur.fetchall()]


def _result_cases(cur) -> list[dict]:
    cases = []
    n = 1
    docs = _fetch_docs(
        cur,
        """
        SELECT d.document_id, d.skm_number, d.publication_year, d.document_type
        FROM skat.legal_documents AS d
        WHERE d.skm_number IS NOT NULL
          AND EXISTS (
                SELECT 1 FROM skat.chunks c
                WHERE c.document_id = d.document_id AND c.is_final_result
          )
        ORDER BY d.publication_year DESC, d.skm_number
        LIMIT 12
        """,
    )
    for doc in docs:
        chunk_ids = _chunk_ids(cur, doc["document_id"], "is_final_result = true")
        cases.append(
            _case(
                f"draft-result-{n:03d}",
                f"Hvad blev resultatet i {doc['skm_number']}?",
                "final_result",
                document_ids=[doc["document_id"]],
                chunk_ids=chunk_ids,
                notes=f"is_final_result {doc['document_type']} {doc['publication_year']}",
            )
        )
        n += 1
    return cases


def _reasoning_cases(cur) -> list[dict]:
    cases = []
    n = 1
    docs = _fetch_docs(
        cur,
        """
        SELECT d.document_id, d.skm_number, d.publication_year
        FROM skat.legal_documents AS d
        WHERE d.skm_number IS NOT NULL
          AND EXISTS (
                SELECT 1 FROM skat.chunks c
                WHERE c.document_id = d.document_id
                  AND c.legal_weight = 'authoritative_reasoning'
          )
        ORDER BY d.publication_year DESC, d.skm_number
        LIMIT 12
        """,
    )
    for doc in docs:
        chunk_ids = _chunk_ids(
            cur, doc["document_id"], "legal_weight = 'authoritative_reasoning'"
        )
        cases.append(
            _case(
                f"draft-reasoning-{n:03d}",
                f"Hvad er begrundelsen i {doc['skm_number']}?",
                "authoritative_reasoning",
                document_ids=[doc["document_id"]],
                chunk_ids=chunk_ids,
                legal_weights=["authoritative_reasoning"],
                forbidden=["prior_instance"],
                notes=f"authoritative_reasoning {doc['publication_year']}",
            )
        )
        n += 1
    return cases


def _prior_cases(cur) -> list[dict]:
    cases = []
    docs = _fetch_docs(
        cur,
        """
        SELECT d.document_id, d.skm_number, d.publication_year
        FROM skat.legal_documents AS d
        WHERE d.skm_number IS NOT NULL
          AND EXISTS (
                SELECT 1 FROM skat.chunks c
                WHERE c.document_id = d.document_id
                  AND c.legal_weight = 'authoritative_reasoning'
          )
          AND EXISTS (
                SELECT 1 FROM skat.chunks c
                WHERE c.document_id = d.document_id
                  AND c.legal_weight = 'prior_instance'
          )
        ORDER BY d.publication_year DESC, d.skm_number
        LIMIT 8
        """,
    )
    for index, doc in enumerate(docs, start=1):
        cases.append(
            _case(
                f"draft-prior-excl-{index:03d}",
                f"Giv præmisserne for {doc['skm_number']}",
                "prior_instance_exclusion",
                document_ids=[doc["document_id"]],
                legal_weights=["authoritative_reasoning"],
                forbidden=["prior_instance"],
                notes="prior_instance må ikke medtages som aktuel begrundelse",
            )
        )
    return cases


def _qa_cases(cur) -> list[dict]:
    cases = []
    docs = _fetch_docs(
        cur,
        """
        SELECT d.document_id, d.skm_number, d.publication_year
        FROM skat.legal_documents AS d
        WHERE d.skm_number IS NOT NULL
          AND EXISTS (
                SELECT 1 FROM skat.chunks c
                WHERE c.document_id = d.document_id AND c.section_type = 'questions'
          )
          AND EXISTS (
                SELECT 1 FROM skat.chunks c
                WHERE c.document_id = d.document_id AND c.section_type = 'answers'
          )
        ORDER BY d.publication_year DESC, d.skm_number
        LIMIT 8
        """,
    )
    for index, doc in enumerate(docs, start=1):
        cases.append(
            _case(
                f"draft-questions-{index:03d}",
                f"Hvilke spørgsmål stilles i {doc['skm_number']}?",
                "questions",
                document_ids=[doc["document_id"]],
                section_types=["questions"],
                notes="spørgsmål-sektion",
            )
        )
        cases.append(
            _case(
                f"draft-answers-{index:03d}",
                f"Hvad er svaret i {doc['skm_number']}?",
                "answers",
                document_ids=[doc["document_id"]],
                section_types=["answers"],
                notes="svar-sektion; 'svar' router til answers",
            )
        )
    return cases


def _topical_cases(cur) -> list[dict]:
    cases = []
    topics = [
        ("moms", 2020, 2026),
        ("fradrag", 2010, 2019),
        ("udbytte", 2001, 2009),
        ("fast ejendom", 2015, 2025),
        ("bevisbyrde", 2010, 2020),
        ("udlejning", 2008, 2018),
        ("genoptagelse", 2018, 2026),
        ("dokumentation", 2005, 2015),
    ]
    for index, (term, low, high) in enumerate(topics, start=1):
        docs = _fetch_docs(
            cur,
            """
            SELECT d.document_id, d.skm_number
            FROM skat.legal_documents AS d
            WHERE d.publication_year BETWEEN %s AND %s
              AND EXISTS (
                    SELECT 1 FROM unnest(d.subject_terms) AS t
                    WHERE lower(t) = lower(%s)
              )
              AND skat.immutable_unaccent(d.title) ILIKE '%%' || skat.immutable_unaccent(%s) || '%%'
            ORDER BY d.skm_number
            LIMIT 3
            """,
            (low, high, term, term),
        )
        if not docs:
            continue
        cases.append(
            _case(
                f"draft-topical-{index:03d}",
                f"Find sager om {term}",
                "topical",
                document_ids=[row["document_id"] for row in docs],
                filters={"year_from": low, "year_to": high},
                notes=f"emneord {term} {low}-{high}",
            )
        )
    return cases


def _reference_cases(cur) -> list[dict]:
    cases = []
    cases.append(
        _case(
            "draft-ref-2026-46",
            "Hvilke henvisninger har SKM2026.46.BR?",
            "references",
            document_ids=["skat-info:oid:2459841"],
            notes="cited:SKM2022.129.ØLR",
        )
    )
    rows = _fetch_docs(
        cur,
        """
        SELECT d.document_id, d.skm_number, d.publication_year,
               r.cited_identifier, t.document_id AS target_id, t.publication_year AS target_year
        FROM skat.document_references AS r
        JOIN skat.legal_documents AS d ON d.document_id = r.source_document_id
        JOIN skat.legal_documents AS t ON t.document_id = r.target_document_id
        WHERE r.resolution_status = 'resolved'
          AND d.skm_number IS NOT NULL
          AND r.cited_identifier IS NOT NULL
          AND d.publication_year <> t.publication_year
        ORDER BY d.publication_year DESC, d.skm_number
        LIMIT 8
        """,
    )
    for index, row in enumerate(rows, start=1):
        cases.append(
            _case(
                f"draft-ref-cross-{index:03d}",
                f"Vis referencerne for {row['skm_number']}",
                "references",
                document_ids=[row["document_id"], row["target_id"]],
        notes=f"cross-year {row['publication_year']}->{row['target_year']}; cited:{row['cited_identifier']}",
            )
        )
    return cases


def _manual_cases(cur) -> list[dict]:
    cases = []
    docs = _fetch_docs(
        cur,
        """
        SELECT document_id, skm_number, publication_year
        FROM skat.legal_documents
        WHERE manual_source_check = true AND skm_number IS NOT NULL
        ORDER BY publication_year DESC, skm_number
        LIMIT 8
        """,
    )
    for index, doc in enumerate(docs, start=1):
        cases.append(
            _case(
                f"draft-manual-{index:03d}",
                doc["skm_number"],
                "manual_source_check",
                document_ids=[doc["document_id"]],
                notes=f"manual_source_check {doc['publication_year']}",
            )
        )
    return cases


def _type_and_length_cases(cur) -> list[dict]:
    cases = []
    for index, (doc_type, intent_suffix) in enumerate(
        (
            ("Dom", "dom"),
            ("Kendelse", "kendelse"),
            ("Bindende svar", "bindende"),
            ("Afgørelse", "afgoerelse"),
        ),
        start=1,
    ):
        docs = _era_docs_of_type(cur, doc_type, 3)
        for offset, doc in enumerate(docs, start=1):
            cases.append(
                _case(
                    f"draft-type-{intent_suffix}-{offset:02d}",
                    doc["skm_number"],
                    "exact_lookup",
                    document_ids=[doc["document_id"]],
                    notes=f"document_type={doc_type} {doc['publication_year']}",
                )
            )
    short = _fetch_docs(
        cur,
        """
        SELECT d.document_id, d.skm_number, x.cnt
        FROM skat.legal_documents AS d
        JOIN (
            SELECT document_id, count(*) AS cnt FROM skat.chunks GROUP BY 1
        ) AS x ON x.document_id = d.document_id
        WHERE d.skm_number IS NOT NULL AND x.cnt <= 3
        ORDER BY x.cnt, d.skm_number
        LIMIT 4
        """,
    )
    long = _fetch_docs(
        cur,
        """
        SELECT d.document_id, d.skm_number, x.cnt
        FROM skat.legal_documents AS d
        JOIN (
            SELECT document_id, count(*) AS cnt FROM skat.chunks GROUP BY 1
        ) AS x ON x.document_id = d.document_id
        WHERE d.skm_number IS NOT NULL AND coalesce(d.summary, '') <> ''
        ORDER BY x.cnt DESC, d.skm_number
        LIMIT 4
        """,
    )
    for index, doc in enumerate(short, start=1):
        cases.append(
            _case(
                f"draft-short-{index:02d}",
                doc["skm_number"],
                "exact_lookup",
                document_ids=[doc["document_id"]],
                notes=f"kort dokument chunks={doc['cnt']}",
            )
        )
    for index, doc in enumerate(long, start=1):
        cases.append(
            _case(
                f"draft-long-{index:02d}",
                f"Resumé af {doc['skm_number']}",
                "summary",
                document_ids=[doc["document_id"]],
                notes=f"langt dokument chunks={doc['cnt']}",
            )
        )
    return cases


def _era_docs_of_type(cur, document_type: str, limit: int) -> list[dict]:
    return _fetch_docs(
        cur,
        """
        SELECT document_id, skm_number, publication_year
        FROM skat.legal_documents
        WHERE document_type = %s AND skm_number IS NOT NULL
        ORDER BY publication_year DESC, skm_number
        LIMIT %s
        """,
        (document_type, limit),
    )


def _filter_cases(cur) -> list[dict]:
    cases = []
    docs = _fetch_docs(
        cur,
        """
        SELECT document_id, skm_number, authority, document_type, publication_year
        FROM skat.legal_documents
        WHERE authority = 'Landsskatteretten'
          AND document_type = 'Afgørelse'
          AND publication_year BETWEEN 2020 AND 2026
          AND skm_number IS NOT NULL
          AND (
                EXISTS (
                    SELECT 1 FROM unnest(subject_terms) AS t
                    WHERE lower(t) = 'fradrag'
                )
                OR skat.immutable_unaccent(title) ILIKE '%%' || skat.immutable_unaccent('fradrag') || '%%'
          )
        ORDER BY skm_number
        LIMIT 4
        """,
    )
    if docs:
        cases.append(
            _case(
                "draft-filter-lsr-2020s",
                "afgørelse om fradrag",
                "topical",
                document_ids=[row["document_id"] for row in docs],
                filters={
                    "authority": "Landsskatteretten",
                    "document_type": "Afgørelse",
                    "year_from": 2020,
                    "year_to": 2026,
                },
                notes="metadatafilter authority+type+år",
            )
        )
    cases.append(
        _case(
            "draft-filter-section-legal-basis",
            "retsgrundlag moms",
            "section_role",
            section_types=["legal_basis"],
            filters={"section_type": "legal_basis", "year_from": 2020, "year_to": 2026},
            notes="section_type-filter legal_basis",
        )
    )
    cases.append(
        _case(
            "draft-filter-weight-reasoning",
            "begrundelse evidensbyrde",
            "section_role",
            legal_weights=["authoritative_reasoning"],
            forbidden=["prior_instance"],
            filters={"legal_weight": "authoritative_reasoning", "year": 2015},
            notes="legal_weight-filter",
        )
    )
    return cases
