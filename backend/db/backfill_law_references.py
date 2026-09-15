"""Backfill strukturerede lovhenvisninger uden at ændre original reference-tekst."""

from __future__ import annotations

import argparse

from backend.db.migrate import connect, dsn
from backend.db.skat_retrieval.law_refs import normalized_reference_columns


UPDATE_SQL = """
UPDATE skat.document_references
SET cited_law_key = %s,
    cited_section_number = %s,
    cited_section_suffix = %s,
    cited_section_end_number = %s,
    cited_section_end_suffix = %s,
    cited_subsection = %s,
    cited_item_number = %s,
    cited_letter = %s
WHERE reference_id = %s
"""


def backfill(conn, *, batch_size: int = 2000, dry_run: bool = False) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT reference_id, cited_identifier, exact_reference_text
            FROM skat.document_references
            WHERE reference_type = 'law_section'
            ORDER BY reference_id
            """
        )
        rows = cur.fetchall()
    parsed = 0
    unparsed = 0
    pending: list[tuple[object, ...]] = []
    for reference_id, cited_identifier, exact_reference_text in rows:
        values = normalized_reference_columns(cited_identifier or exact_reference_text or "")
        if values[0] is None:
            unparsed += 1
        else:
            parsed += 1
        pending.append(values + (reference_id,))
        if len(pending) >= batch_size:
            if not dry_run:
                with conn.cursor() as cur:
                    cur.executemany(UPDATE_SQL, pending)
                conn.commit()
            pending.clear()
    if pending and not dry_run:
        with conn.cursor() as cur:
            cur.executemany(UPDATE_SQL, pending)
        conn.commit()
    if dry_run:
        conn.rollback()
    return {"total": len(rows), "parsed": parsed, "unparsed": unparsed}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=2000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    conn = connect(dsn())
    try:
        result = backfill(conn, batch_size=max(1, args.batch_size), dry_run=args.dry_run)
    finally:
        conn.close()
    print(
        f"lovhenvisninger total={result['total']} parsed={result['parsed']} "
        f"unparsed={result['unparsed']} dry_run={args.dry_run}"
    )


if __name__ == "__main__":
    main()
