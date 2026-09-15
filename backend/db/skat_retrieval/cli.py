"""CLI for SKAT-retrieval. Read-only. Maskinlæsbart JSON/JSONL.

JSON-fejl skrives til stderr med non-zero exit code. stdout ved --format json
indeholder kun ét JSON-objekt. JSONL: første linje er record_type=query_metadata
(eller tilsvarende metadata), derefter én JSON-værdi pr. linje.
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

from backend.db.skat_import.io import redact_dsn
from backend.db.skat_retrieval.db import connect_readonly, retrieval_dsn
from backend.db.skat_retrieval.engine import retrieve
from backend.db.skat_retrieval.errors import (
    CliArgumentError,
    DatabaseUnavailableError,
    EXIT_DATABASE,
    EXIT_OK,
    EXIT_USAGE,
    SkatRetrievalError,
)
from backend.db.skat_retrieval.lookup import (
    count_prior_instance_chunks,
    get_document,
    get_final_result,
    get_reasoning,
    get_references,
    get_summary,
)
from backend.db.skat_retrieval.output import (
    dumps,
    emit_error,
    emit_json,
    emit_jsonl,
    reasoning_payload,
    reference_payload,
    references_payload,
    result_payload,
    search_payload,
    summary_payload,
)
from backend.db.skat_retrieval.settings import (
    CLI_SEARCH_MODES,
    DEFAULT_CLI_SEARCH_MODE,
    OUTPUT_FORMATS,
)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliArgumentError(message)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    debug = "--debug" in argv
    fmt = _peek_format(argv)
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except CliArgumentError as exc:
        if fmt in {"json", "jsonl"}:
            emit_error(error=exc, identifier=None, debug=False)
        else:
            parser.print_usage(sys.stderr)
            print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    except SystemExit as exc:
        code = int(exc.code or 0)
        return EXIT_OK if code == 0 else EXIT_USAGE
    try:
        if args.command == "search":
            return _search(args)
        if args.command == "summary":
            return _summary(args)
        if args.command == "result":
            return _result(args)
        if args.command == "reasoning":
            return _reasoning(args)
        if args.command == "references":
            return _references(args)
        if args.command == "evaluate":
            return _evaluate(args)
        if args.command == "build-eval":
            return _build_eval(args)
        raise CliArgumentError(f"ukendt kommando {args.command}")
    except SkatRetrievalError as exc:
        return _fail(
            exc,
            fmt=getattr(args, "format", fmt),
            debug=debug,
            identifier=_identifier_of(args),
        )
    except Exception:
        if debug:
            traceback.print_exc(file=sys.stderr)
        return _fail(
            DatabaseUnavailableError("databaseforbindelse eller query-fejl"),
            fmt=getattr(args, "format", fmt),
            debug=False,
            identifier=_identifier_of(args),
        )


def _peek_format(argv: list[str]) -> str:
    if "--format" in argv:
        idx = argv.index("--format")
        if idx + 1 < len(argv) and argv[idx + 1] in OUTPUT_FORMATS:
            return argv[idx + 1]
    return "text"


def _identifier_of(args) -> str | None:
    return getattr(args, "identifier", None)


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description="SKAT-retrieval: A–E direkte, topical hybrid")
    parser.add_argument("--debug", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(item, *, with_query: bool = False, with_identifier: bool = False) -> None:
        if with_query:
            item.add_argument("--query", required=True)
        if with_identifier:
            item.add_argument("--identifier", required=True)
        item.add_argument("--format", choices=OUTPUT_FORMATS, default="text")
        item.add_argument("--limit", type=int, default=10)
        item.add_argument("--include-references", action="store_true")
        item.add_argument("--year", type=int)
        item.add_argument("--year-from", type=int)
        item.add_argument("--year-to", type=int)
        item.add_argument("--document-type")
        item.add_argument("--topic")
        item.add_argument("--section-type")
        item.add_argument("--authority")
        item.add_argument("--legal-weight")

    search = sub.add_parser("search")
    add_common(search, with_query=True)
    search.add_argument("--mode", choices=CLI_SEARCH_MODES, default=DEFAULT_CLI_SEARCH_MODE)
    search.add_argument("--exact-vector", action="store_true")
    search.add_argument("--high-risk", action="store_true")

    for name in ("summary", "result", "reasoning", "references"):
        add_common(sub.add_parser(name), with_identifier=True)

    ev = sub.add_parser("evaluate")
    ev.add_argument("--dataset", required=True)
    ev.add_argument("--format", choices=OUTPUT_FORMATS, default="text")
    ev.add_argument("--limit", type=int, default=10)
    ev.add_argument("--mode", choices=("auto", "lexical", "vector", "hybrid", "exact"), default="hybrid")
    ev.add_argument("--exact-vector", action="store_true")

    build = sub.add_parser("build-eval")
    build.add_argument("--output", required=True)
    build.add_argument("--format", choices=OUTPUT_FORMATS, default="text")
    return parser


def _filters(args) -> dict[str, object]:
    return {
        key: value
        for key, value in {
            "year": getattr(args, "year", None),
            "year_from": getattr(args, "year_from", None),
            "year_to": getattr(args, "year_to", None),
            "authority": getattr(args, "authority", None),
            "document_type": getattr(args, "document_type", None),
            "section_type": getattr(args, "section_type", None),
            "legal_weight": getattr(args, "legal_weight", None),
            "topic": getattr(args, "topic", None),
        }.items()
        if value is not None
    }


def _open(fmt: str):
    url = retrieval_dsn()
    if fmt == "text":
        print(f"forbindelse {redact_dsn(url)}", flush=True)
    return connect_readonly(url)


def _close(conn) -> None:
    try:
        conn.commit()
    except Exception:
        conn.rollback()
    conn.close()


def _fail(exc: SkatRetrievalError, *, fmt: str, debug: bool, identifier: str | None) -> int:
    if fmt in {"json", "jsonl"}:
        emit_error(error=exc, identifier=identifier, debug=debug)
    else:
        print(str(exc), file=sys.stderr)
        if debug:
            traceback.print_exc(file=sys.stderr)
    return int(getattr(exc, "exit_code", EXIT_DATABASE))


def _search(args) -> int:
    filters = _filters(args)
    started = time.perf_counter()
    conn = _open(args.format)
    try:
        response = retrieve(
            conn,
            args.query,
            limit=args.limit,
            filters=filters,
            mode=args.mode,
            exact_vector=args.exact_vector,
            high_risk=args.high_risk,
        )
        extra_refs = None
        if args.include_references and response.hits:
            extra_refs = {}
            for hit in response.hits:
                extra_refs[hit.document_id] = [
                    reference_payload(row) for row in get_references(conn, hit.document_id)
                ]
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        payload = search_payload(
            response,
            query=args.query,
            limit=args.limit,
            filters=filters,
            elapsed_ms=elapsed_ms,
            include_references=args.include_references,
            extra_references=extra_refs,
        )
        if args.format == "json":
            emit_json(payload)
            return EXIT_OK
        if args.format == "jsonl":
            meta = dict(payload)
            results = meta.pop("results")
            meta["record_type"] = "query_metadata"
            rows = [meta]
            for item in results:
                row = dict(item)
                row["record_type"] = "result"
                rows.append(row)
            emit_jsonl(rows)
            return EXIT_OK
        print(f"intent={response.route.intent} identifier={response.route.identifier}")
        print(response.note)
        if response.document:
            doc = response.document
            print(
                f"dokument {doc.skm_number} {doc.document_id} "
                f"manual_source_check={doc.manual_source_check}"
            )
        if response.summary is not None:
            print(f"summary_tegn={len(response.summary)}")
            print(response.summary)
        if response.chunks:
            for chunk in response.chunks:
                print(
                    f"{chunk.chunk_index} {chunk.chunk_id} {chunk.section_type} "
                    f"{chunk.legal_weight} final={chunk.is_final_result}"
                )
        if response.hits:
            for hit in response.hits:
                snippet = hit.chunk_text.replace("\n", " ")[:160]
                print(
                    f"{hit.rank_score:.1f} {hit.skm_number} {hit.chunk_id} "
                    f"{hit.section_type} {hit.legal_weight} "
                    f"manual={hit.manual_source_check} signals={','.join(hit.signals)}"
                )
                print(f"  {snippet}")
        if response.hits is not None and not response.hits:
            print("ingen lexical træf")
        return EXIT_OK
    finally:
        _close(conn)


def _summary(args) -> int:
    conn = _open(args.format)
    try:
        document = get_document(conn, args.identifier)
        text = get_summary(conn, args.identifier)
        payload = summary_payload(document, text, identifier=args.identifier)
        if args.format == "json":
            emit_json(payload)
            return EXIT_OK
        if args.format == "jsonl":
            emit_jsonl([{"record_type": "summary", **payload}])
            return EXIT_OK
        print(f"summary_tegn={len(text)}")
        print(text)
        return EXIT_OK
    finally:
        _close(conn)


def _result(args) -> int:
    conn = _open(args.format)
    try:
        document = get_document(conn, args.identifier)
        chunks = get_final_result(conn, args.identifier)
        payload = result_payload(document, chunks, identifier=args.identifier)
        if args.format == "json":
            emit_json(payload)
            return EXIT_OK
        if args.format == "jsonl":
            rows = [{"record_type": "result_metadata", **{k: v for k, v in payload.items() if k != "chunks"}}]
            for chunk in payload["chunks"]:
                rows.append({"record_type": "chunk", **chunk})
            emit_jsonl(rows)
            return EXIT_OK
        for chunk in chunks:
            print(
                f"{chunk.chunk_index} {chunk.chunk_id} {chunk.section_type} "
                f"{chunk.legal_weight} tegn={len(chunk.chunk_text)}"
            )
        return EXIT_OK
    finally:
        _close(conn)


def _reasoning(args) -> int:
    conn = _open(args.format)
    try:
        document = get_document(conn, args.identifier)
        chunks = get_reasoning(conn, args.identifier)
        payload = reasoning_payload(conn, document, chunks, identifier=args.identifier)
        if args.format == "json":
            emit_json(payload)
            return EXIT_OK
        if args.format == "jsonl":
            rows = [{"record_type": "reasoning_metadata", **{k: v for k, v in payload.items() if k != "chunks"}}]
            for chunk in payload["chunks"]:
                rows.append({"record_type": "chunk", **chunk})
            emit_jsonl(rows)
            return EXIT_OK
        omitted = count_prior_instance_chunks(conn, args.identifier)
        if omitted:
            print(f"prior_instance_udeladt={omitted}")
        for chunk in chunks:
            print(
                f"{chunk.chunk_index} {chunk.chunk_id} {chunk.legal_weight} "
                f"tegn={len(chunk.chunk_text)}"
            )
        return EXIT_OK
    finally:
        _close(conn)


def _references(args) -> int:
    conn = _open(args.format)
    try:
        document = get_document(conn, args.identifier)
        rows = get_references(conn, args.identifier)
        payload = references_payload(document, rows, identifier=args.identifier)
        if args.format == "json":
            emit_json(payload)
            return EXIT_OK
        if args.format == "jsonl":
            meta = {k: v for k, v in payload.items() if k != "references"}
            meta["record_type"] = "references_metadata"
            out = [meta]
            for item in payload["references"]:
                row = dict(item)
                row["record_type"] = "reference"
                out.append(row)
            emit_jsonl(out)
            return EXIT_OK
        for row in rows:
            print(
                f"{row.direction} {row.cited_identifier} {row.resolution_status} "
                f"target={row.target_document_id}"
            )
        return EXIT_OK
    finally:
        _close(conn)


def _evaluate(args) -> int:
    from backend.db.skat_retrieval.evaluate import evaluate_dataset

    conn = _open(args.format)
    try:
        report = evaluate_dataset(
            conn,
            Path(args.dataset),
            search_limit=args.limit,
            mode=args.mode,
            exact_vector=args.exact_vector,
        )
        payload = report.as_dict()
        warning = "ADVARSEL: alle cases har gold_status=draft og er ikke fagligt valideret."
        if args.format == "json":
            emit_json(payload)
            print(warning, file=sys.stderr, flush=True)
        elif args.format == "jsonl":
            emit_jsonl([{"record_type": "eval_report", **payload}])
            print(warning, file=sys.stderr, flush=True)
        else:
            print(dumps(payload))
            print(warning, file=sys.stderr, flush=True)
        exact = payload.get("exact_lookup_accuracy")
        if exact is not None and exact < 1:
            print("exact lookup accuracy er under 100 %", file=sys.stderr)
            return 1
        return EXIT_OK
    finally:
        _close(conn)


def _build_eval(args) -> int:
    from backend.db.skat_retrieval.build_eval import write_eval_dataset

    conn = _open(args.format)
    try:
        path = write_eval_dataset(conn, Path(args.output))
        if args.format == "json":
            emit_json({"schema_version": "1.0", "path": str(path)})
        else:
            print(f"skrev {path}")
        return EXIT_OK
    finally:
        _close(conn)
