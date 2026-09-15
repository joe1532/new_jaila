"""CLI for SKAT JSONL-import. Ingen embeddings. Ingen credentials i argumenter."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from backend.db.skat_import.constants import (
    DEFAULT_BATCH_SIZE,
    PRODUCTION_EXPECTATIONS,
    SMOKE_2026,
    YEAR_2026,
)
from backend.db.skat_import.errors import PreflightError, SkatImportError, VerifyError
from backend.db.skat_import.io import redact_dsn
from backend.db.skat_import.preflight import run_preflight
from backend.db.skat_import.year_expect import APPROVED_PILOT_YEAR, descending_years


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deterministisk import af SKAT-afgørelser til Postgres"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(subparser) -> None:
        subparser.add_argument("--input-root", required=True, help="Rod til skat_info_personskat_chunks/v1")
        subparser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)

    pre = sub.add_parser("preflight", help="Valider korpus uden databaseændring")
    add_common(pre)
    dry = sub.add_parser("dry-run", help="Preflight plus forventede ændringer, ingen writes")
    add_common(dry)
    dry.add_argument("--year", type=int, default=None)
    dry.add_argument("--start-year", type=int, default=None)
    dry.add_argument("--end-year", type=int, default=None)
    docs = sub.add_parser("import-documents", help="Indlæs legal_documents for hele korpusset")
    add_common(docs)
    year_p = sub.add_parser("import-year", help="Indlæs chunks og referencer for ét år")
    add_common(year_p)
    year_p.add_argument("--year", type=int, required=True)
    corpus_p = sub.add_parser("import-corpus", help="Resumérbar import af et årsinterval")
    add_common(corpus_p)
    corpus_p.add_argument("--start-year", type=int, required=True)
    corpus_p.add_argument("--end-year", type=int, required=True)
    corpus_p.add_argument("--verify-each-year", action="store_true", default=True)
    corpus_p.add_argument("--no-verify-each-year", action="store_false", dest="verify_each_year")
    verify_p = sub.add_parser("verify", help="Kontrollér ét år mod JSONL")
    add_common(verify_p)
    verify_p.add_argument("--year", type=int, required=True)
    verify_c = sub.add_parser("verify-corpus", help="Samlet korpusverifikation")
    add_common(verify_c)
    retrieval = sub.add_parser("retrieval-check", help="Eksakte opslag på tværs af år")
    add_common(retrieval)
    args = parser.parse_args(argv)
    input_root = Path(args.input_root)

    try:
        if args.command == "preflight":
            result = run_preflight(input_root)
            print(
                f"preflight OK: {len(result.years)} år, "
                f"{result.expected.document_count} dokumenter, "
                f"{result.expected.chunk_count} chunks, "
                f"{result.expected.reference_count} referencer",
                flush=True,
            )
            return 0
        if args.command == "dry-run":
            return _dry_run(input_root, args.year, args.start_year, args.end_year)
        if args.command == "import-documents":
            return _import_documents(input_root, args.batch_size)
        if args.command == "import-year":
            return _import_year(input_root, args.year, args.batch_size)
        if args.command == "import-corpus":
            return _import_corpus(
                input_root,
                args.start_year,
                args.end_year,
                args.batch_size,
                args.verify_each_year,
            )
        if args.command == "verify":
            return _verify(input_root, args.year)
        if args.command == "verify-corpus":
            return _verify_corpus(input_root)
        if args.command == "retrieval-check":
            return _retrieval_check(input_root)
        raise SkatImportError(f"ukendt kommando {args.command}")
    except PreflightError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (SkatImportError, VerifyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


def _dry_run(input_root: Path, year: int | None, start_year: int | None, end_year: int | None) -> int:
    result = run_preflight(input_root)
    if start_year is not None or end_year is not None:
        if start_year is None or end_year is None:
            raise SkatImportError("dry-run kræver både --start-year og --end-year")
        years = descending_years(start_year, end_year)
    elif year is not None:
        years = [year]
    else:
        years = [YEAR_2026.year]
    by_year = {item.year: item for item in result.year_checks}
    print("dry-run: preflight OK, ingen databasewrites", flush=True)
    print(
        f"  korpus: {result.expected.document_count} dokumenter, "
        f"{result.expected.chunk_count} chunks, "
        f"{result.expected.reference_count} referencer",
        flush=True,
    )
    total_docs = total_chunks = total_refs = 0
    for current in years:
        check = by_year.get(current)
        if check is None:
            raise SkatImportError(f"år {current} findes ikke i preflight")
        marker = " (godkendt 2026, importeres ikke)" if current == APPROVED_PILOT_YEAR else ""
        print(
            f"  {current}: dokumenter={check.document_count} "
            f"chunks={check.chunk_count} referencer={check.reference_count}{marker}",
            flush=True,
        )
        if current != APPROVED_PILOT_YEAR:
            total_docs += check.document_count
            total_chunks += check.chunk_count
            total_refs += check.reference_count
    print(
        f"  interval uden {APPROVED_PILOT_YEAR}: "
        f"dokumenter={total_docs} chunks={total_chunks} referencer={total_refs}",
        flush=True,
    )
    existing = _existing_counts_readonly()
    if existing is not None:
        print(
            f"  database nu: dokumenter={existing[0]} chunks={existing[1]} "
            f"referencer={existing[2]}",
            flush=True,
        )
    else:
        print("  database ikke tilsluttet (JAILA_SKAT_DATABASE_URL mangler eller fejlede)", flush=True)
    return 0


def _existing_counts_readonly() -> tuple[int, int, int] | None:
    try:
        from backend.db.skat_import.connect import connect, dsn

        url = dsn()
        print(f"  forbindelse {redact_dsn(url)} (kun SELECT)", flush=True)
        conn = connect(url, autocommit=True)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM skat.legal_documents")
                docs = int(cur.fetchone()[0])
                cur.execute("SELECT count(*) FROM skat.chunks")
                chunks = int(cur.fetchone()[0])
                cur.execute("SELECT count(*) FROM skat.document_references")
                refs = int(cur.fetchone()[0])
            return docs, chunks, refs
        finally:
            conn.close()
    except Exception:
        return None


def _open_conns():
    from backend.db.skat_import.connect import connect, dsn

    url = dsn()
    print(f"forbindelse {redact_dsn(url)}", flush=True)
    work = connect(url, autocommit=False)
    audit_conn = connect(url, autocommit=True)
    return work, audit_conn


def _import_documents(input_root: Path, batch_size: int) -> int:
    from backend.db.skat_import.documents import import_documents

    preflight = run_preflight(input_root)
    work, audit_conn = _open_conns()
    try:
        progress = import_documents(
            input_root,
            work,
            audit_conn,
            expected=PRODUCTION_EXPECTATIONS,
            batch_size=batch_size,
            preflight=preflight,
        )
        print(
            f"dokumentimport færdig: læst={progress.read} "
            f"indsat={progress.inserted} sprunget_over={progress.skipped}",
            flush=True,
        )
        return 0
    finally:
        work.close()
        audit_conn.close()


def _import_year(input_root: Path, year: int, batch_size: int) -> int:
    from backend.db.skat_import.year import import_year
    from backend.db.skat_import.year_expect import expectations_from_year_files

    run_preflight(input_root)
    if year < 2001 or year > 2026:
        raise SkatImportError(f"år {year} ligger uden for 2001–2026")
    work, audit_conn = _open_conns()
    try:
        import_year(
            input_root,
            year,
            work,
            audit_conn,
            expectations=expectations_from_year_files(input_root, year),
            batch_size=batch_size,
        )
        return 0
    finally:
        work.close()
        audit_conn.close()


def _import_corpus(
    input_root: Path,
    start_year: int,
    end_year: int,
    batch_size: int,
    verify_each_year: bool,
) -> int:
    from backend.db.skat_import.corpus import import_corpus

    preflight = run_preflight(input_root)
    work, audit_conn = _open_conns()
    try:
        result = import_corpus(
            input_root,
            start_year,
            end_year,
            work,
            audit_conn,
            expected=PRODUCTION_EXPECTATIONS,
            batch_size=batch_size,
            skip_years={APPROVED_PILOT_YEAR},
            verify_each_year=verify_each_year,
            preflight=preflight,
        )
        print(
            f"import-corpus færdig: importeret={result.imported} sprunget_over={result.skipped}",
            flush=True,
        )
        return 0
    finally:
        work.close()
        audit_conn.close()


def _verify(input_root: Path, year: int) -> int:
    from backend.db.skat_import.connect import connect, dsn
    from backend.db.skat_import.verify import verify_year

    url = dsn()
    print(f"forbindelse {redact_dsn(url)}", flush=True)
    conn = connect(url, autocommit=True)
    try:
        smoke = SMOKE_2026 if year == YEAR_2026.year else None
        result = verify_year(input_root, year, conn, smoke=smoke)
        for line in result.checks:
            print(f"OK {line}", flush=True)
        print("verify OK", flush=True)
        return 0
    finally:
        conn.close()


def _verify_corpus(input_root: Path) -> int:
    from backend.db.skat_import.connect import connect, dsn
    from backend.db.skat_import.corpus import verify_corpus

    url = dsn()
    print(f"forbindelse {redact_dsn(url)}", flush=True)
    conn = connect(url, autocommit=True)
    try:
        result = verify_corpus(input_root, conn)
        for line in result.checks:
            print(f"OK {line}", flush=True)
        print("verify-corpus OK", flush=True)
        return 0
    finally:
        conn.close()


def _retrieval_check(input_root: Path) -> int:
    from backend.db.skat_import.connect import connect, dsn
    from backend.db.skat_import.corpus import retrieval_check

    run_preflight(input_root)
    url = dsn()
    print(f"forbindelse {redact_dsn(url)}", flush=True)
    conn = connect(url, autocommit=True)
    try:
        for line in retrieval_check(conn):
            print(f"OK {line}", flush=True)
        print("retrieval-check OK", flush=True)
        return 0
    finally:
        conn.close()
