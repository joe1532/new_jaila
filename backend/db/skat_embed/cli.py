"""CLI for SKAT-embedding-worker. Ingen API-nøgle i argumenter. Ingen HNSW."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.db.skat_embed.constants import PILOT_SELECTION_KEY, PILOT_SIZE
from backend.db.skat_embed.errors import FullCorpusNotApprovedError, SkatEmbedError
from backend.db.skat_import.io import redact_dsn


def main(argv: list[str] | None = None) -> int:
    if argv and any(item.startswith("--api-key") or item.startswith("--openai") for item in argv):
        print("API-nøgle må kun læses fra OPENAI_API_KEY", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(description="Genoptagelig OpenAI-embedding uden HNSW")
    sub = parser.add_subparsers(dest="command", required=True)

    dry = sub.add_parser("dry-run", help="Udvalg og tællinger uden API og uden inserts")
    dry.add_argument("--selection", choices=("pilot",), default="pilot")

    pilot = sub.add_parser("pilot", help="Embed 1000 stratificerede chunks")
    pilot.add_argument("--skip-queries", action="store_true")

    sub.add_parser("preflight", help="Read-only kontrol før fuld korpus-embedding")
    sub.add_parser("resume", help="Genoptag korpus (springer matching embeddings over)")

    verify = sub.add_parser("verify", help="Kontrollér embeddings, hashes og HNSW-status")
    verify.add_argument("--selection", default=PILOT_SELECTION_KEY)

    recall = sub.add_parser("hnsw-recall", help="Approximate Recall@10 mod exact vector search")
    recall.add_argument("--k", type=int, default=10)
    recall.add_argument("--ef", default="20,40,64,80,100,200,400,800,1600,4000")
    recall.add_argument("--skip-iterative", action="store_true")

    sub.add_parser("hnsw-plan", help="EXPLAIN exact seq-scan vs HNSW")

    query = sub.add_parser("query", help="Embed én forespørgsel med samme model")
    query.add_argument("--text", required=True)
    query.add_argument("--store", action="store_true")

    ev = sub.add_parser("embed-queries", help="Embed evalueringsforespørgsler")
    ev.add_argument("--dataset", default="backend/db/eval/skat_retrieval_eval_v1.jsonl")

    corpus = sub.add_parser("corpus", help="Fuld korpus-embedding; kræver særskilt godkendelse")
    corpus.add_argument("--i-approve-full-corpus", action="store_true")
    corpus.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "preflight":
            return _preflight()
        if args.command == "dry-run":
            return _dry_run()
        if args.command == "pilot":
            return _pilot(skip_queries=args.skip_queries)
        if args.command == "resume":
            return _resume()
        if args.command == "verify":
            return _verify(args.selection)
        if args.command == "hnsw-recall":
            return _hnsw_recall(
                k=args.k, ef_values=args.ef, skip_iterative=args.skip_iterative
            )
        if args.command == "hnsw-plan":
            return _hnsw_plan()
        if args.command == "query":
            return _query(args.text, store=args.store)
        if args.command == "embed-queries":
            return _embed_queries(Path(args.dataset))
        if args.command == "corpus":
            if not args.i_approve_full_corpus:
                raise FullCorpusNotApprovedError(
                    "Importér/embed ikke hele korpusset uden særskilt godkendelse"
                )
            return _corpus(dry_run=args.dry_run)
        raise SkatEmbedError(f"ukendt kommando {args.command}")
    except SkatEmbedError as exc:
        print(str(exc), file=sys.stderr)
        return 1


def _open(*, autocommit: bool = True):
    from backend.db.skat_import.connect import connect, dsn

    url = dsn()
    print(f"forbindelse {redact_dsn(url)}", flush=True)
    return connect(url, autocommit=autocommit)


def _write_pilot_manifest(conn) -> None:
    from backend.db.skat_embed.select import select_pilot_chunks

    selected = select_pilot_chunks(conn, size=PILOT_SIZE)
    path = Path("backend/db/eval/skat_embed_pilot_v1.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for item in selected:
            handle.write(
                json.dumps(
                    {
                        "chunk_id": item.chunk_id,
                        "publication_year": item.publication_year,
                        "section_type": item.section_type,
                        "legal_weight": item.legal_weight,
                        "is_final_result": item.is_final_result,
                        "manual_source_check": item.manual_source_check,
                        "token_count": item.token_count,
                        "embedding_text_sha256": item.embedding_text_sha256,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    print(f"skrev {path} ({len(selected)} chunks)", flush=True)


def _print_stats(stats) -> None:
    print(
        f"run_id={stats.run_id} valgt={stats.selected} pending={stats.pending} "
        f"indsat={stats.inserted} sprunget={stats.skipped} "
        f"prompt_tokens={stats.prompt_tokens} total_tokens={stats.total_tokens} "
        f"api_requests={stats.api_requests} retries={stats.retries} "
        f"duration_s={stats.duration_s:.1f}",
        flush=True,
    )
    if stats.coverage:
        print(json.dumps(stats.coverage, ensure_ascii=False), flush=True)


def _preflight() -> int:
    from backend.db.skat_embed.preflight import run_preflight
    from backend.db.skat_import.connect import dsn

    url = dsn()
    conn = _open()
    try:
        report = run_preflight(conn, url)
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2), flush=True)
        print("preflight OK", flush=True)
        return 0
    finally:
        conn.close()


def _hnsw_recall(*, k: int, ef_values: str, skip_iterative: bool = False) -> int:
    from backend.db.skat_embed.hnsw_recall import run_hnsw_recall

    values = [int(item.strip()) for item in ef_values.split(",") if item.strip()]
    conn = _open()
    try:
        report = run_hnsw_recall(
            conn, k=k, ef_values=values, skip_iterative=skip_iterative
        )
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        return 0
    finally:
        conn.close()


def _hnsw_plan() -> int:
    from backend.db.skat_embed.hnsw_plan import explain_exact_and_hnsw

    conn = _open()
    try:
        explain_exact_and_hnsw(conn)
        return 0
    finally:
        conn.close()


def _dry_run() -> int:
    from backend.db.skat_embed.worker import run_pilot

    conn = _open()
    try:
        stats = run_pilot(conn, dry_run=True)
        _write_pilot_manifest(conn)
        _print_stats(stats)
        return 0
    finally:
        conn.close()


def _pilot(skip_queries: bool) -> int:
    from backend.db.skat_embed.worker import run_pilot

    conn = _open()
    try:
        stats = run_pilot(conn, dry_run=False)
        _write_pilot_manifest(conn)
        _print_stats(stats)
        if not skip_queries:
            from backend.db.skat_embed.queries import embed_eval_queries

            dataset = Path("backend/db/eval/skat_retrieval_eval_v1.jsonl")
            n = embed_eval_queries(conn, dataset)
            print(f"query-embeddings indsat={n}", flush=True)
        return 0
    finally:
        conn.close()


def _resume() -> int:
    from backend.db.skat_embed.worker import run_resume_corpus

    conn = _open()
    try:
        stats = run_resume_corpus(conn)
        _print_stats(stats)
        return 0
    finally:
        conn.close()


def _verify(selection: str) -> int:
    from backend.db.skat_embed.verify import verify_selection

    conn = _open()
    try:
        report = verify_selection(conn, selection_key=selection)
        for line in report.checks:
            print(line, flush=True)
        print("verify OK", flush=True)
        return 0
    finally:
        conn.close()


def _query(text: str, *, store: bool) -> int:
    from backend.db.skat_embed.model import ensure_embedding_model
    from backend.db.skat_embed.queries import embed_query_text, store_query_embedding

    result = embed_query_text(text)
    print(
        f"query-embedding dim={len(result.vector)} sha256={result.sha256[:16]}…",
        flush=True,
    )
    if store:
        conn = _open()
        try:
            model_id = ensure_embedding_model(conn)
            store_query_embedding(conn, model_id, result)
            print("gemt i query_embeddings", flush=True)
        finally:
            conn.close()
    return 0


def _embed_queries(dataset: Path) -> int:
    from backend.db.skat_embed.queries import embed_eval_queries

    conn = _open()
    try:
        n = embed_eval_queries(conn, dataset)
        print(f"query-embeddings indsat={n}", flush=True)
        return 0
    finally:
        conn.close()


def _corpus(*, dry_run: bool) -> int:
    from backend.db.skat_embed.worker import run_corpus

    conn = _open()
    try:
        stats = run_corpus(conn, approved=True, dry_run=dry_run)
        _print_stats(stats)
        return 0
    finally:
        conn.close()
