"""Read-only preflight før fuld korpus-embedding. Ingen API-kald. Ingen dokumenttekst."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from backend.db.skat_embed.client import BatchItem, split_batches
from backend.db.skat_embed.constants import (
    CORPUS_SELECTION_KEY,
    DEFAULT_BATCH_INPUTS,
    DEFAULT_BATCH_TOKENS,
    DIMENSIONS,
    DISTANCE_METRIC,
    MODEL_NAME,
    PROVIDER,
)
from backend.db.skat_embed.errors import SkatEmbedError
from backend.db.skat_embed.keys import openai_api_key
from backend.db.skat_import.constants import (
    EXPECTED_CHUNK_COUNT,
    EXPECTED_DOCUMENT_COUNT,
    EXPECTED_REFERENCE_COUNT,
)
from backend.db.skat_import.io import redact_dsn

EXPECTED_EMBEDDINGS_BEFORE = 1000
EXPECTED_PENDING = EXPECTED_CHUNK_COUNT - EXPECTED_EMBEDDINGS_BEFORE
EXPECTED_SPANS = 1_941_364
BACKUP_DIR = Path(__file__).resolve().parents[1] / "backups"


@dataclass
class PreflightReport:
    checks: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    chunk_count: int = 0
    embedding_count: int = 0
    pending_count: int = 0
    pending_tokens: int = 0
    batch_count: int = 0
    model_id: str | None = None
    backup_path: str | None = None
    backup_bytes: int = 0
    document_count: int = 0
    span_count: int = 0
    reference_count: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict:
        return {
            "ok": not self.errors,
            "checks": self.checks,
            "errors": self.errors,
            "chunk_count": self.chunk_count,
            "existing_embeddings": self.embedding_count,
            "pending_embeddings": self.pending_count,
            "pending_tokens": self.pending_tokens,
            "expected_batches": self.batch_count,
            "max_tokens_per_request": DEFAULT_BATCH_TOKENS,
            "model_id": self.model_id,
            "backup_path": self.backup_path,
            "backup_bytes": self.backup_bytes,
            "document_count": self.document_count,
            "span_count": self.span_count,
            "reference_count": self.reference_count,
            "selection_key": CORPUS_SELECTION_KEY,
        }


def _expect(report: PreflightReport, label: str, actual, expected) -> None:
    if actual != expected:
        report.errors.append(f"{label}: {actual}, forventet {expected}")
    else:
        report.checks.append(f"{label}: {actual}")


def latest_backup() -> Path | None:
    if not BACKUP_DIR.is_dir():
        return None
    dumps = sorted(BACKUP_DIR.glob("*.dump"), key=lambda path: path.stat().st_mtime)
    return dumps[-1] if dumps else None


def run_preflight(conn, dsn: str) -> PreflightReport:
    report = PreflightReport()
    parsed = urlparse(dsn)
    host = parsed.hostname
    port = parsed.port or 5432
    dbname = (parsed.path or "").lstrip("/")
    _expect(report, "databasehost", f"{host}:{port}", "127.0.0.1:5433")
    _expect(report, "databasenavn", dbname, "jaila_skat")
    report.checks.append(f"dsn {redact_dsn(dsn)}")

    key_ok = False
    try:
        openai_api_key()
        key_ok = True
    except Exception:
        key_ok = False
    if key_ok:
        report.checks.append("OPENAI_API_KEY er sat")
    else:
        report.errors.append("OPENAI_API_KEY mangler")

    backup = latest_backup()
    if backup is None or backup.stat().st_size <= 0:
        report.errors.append("backupfil mangler eller er tom")
    else:
        report.backup_path = str(backup)
        report.backup_bytes = int(backup.stat().st_size)
        report.checks.append(f"backup {backup.name} bytes={report.backup_bytes}")

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM skat.chunks")
        report.chunk_count = int(cur.fetchone()[0])
        cur.execute("SELECT count(*) FROM skat.legal_documents")
        report.document_count = int(cur.fetchone()[0])
        cur.execute("SELECT count(*) FROM skat.chunk_source_spans")
        report.span_count = int(cur.fetchone()[0])
        cur.execute("SELECT count(*) FROM skat.document_references")
        report.reference_count = int(cur.fetchone()[0])
        cur.execute(
            """
            SELECT embedding_model_id, provider, model_name, dimensions, distance_metric
            FROM skat.embedding_models
            """
        )
        models = cur.fetchall()
        cur.execute("SELECT count(*) FROM skat.chunk_embeddings")
        report.embedding_count = int(cur.fetchone()[0])
        cur.execute(
            """
            SELECT count(*)
            FROM pg_indexes
            WHERE schemaname = 'skat' AND indexdef ILIKE %s
            """,
            ("%hnsw%",),
        )
        hnsw = int(cur.fetchone()[0])

    _expect(report, "chunks", report.chunk_count, EXPECTED_CHUNK_COUNT)
    _expect(report, "dokumenter", report.document_count, EXPECTED_DOCUMENT_COUNT)
    _expect(report, "source spans", report.span_count, EXPECTED_SPANS)
    _expect(report, "referencer", report.reference_count, EXPECTED_REFERENCE_COUNT)
    _expect(report, "eksisterende embeddings", report.embedding_count, EXPECTED_EMBEDDINGS_BEFORE)
    _expect(report, "HNSW før fuld embedding", hnsw, 0)

    if len(models) != 1:
        report.errors.append(f"forventede præcis 1 embedding_models-række, fik {len(models)}")
        return report
    model_id, provider, model_name, dimensions, metric = models[0]
    report.model_id = str(model_id)
    _expect(report, "provider", provider, PROVIDER)
    _expect(report, "model_name", model_name, MODEL_NAME)
    _expect(report, "dimensions", int(dimensions), DIMENSIONS)
    _expect(report, "distance_metric", metric, DISTANCE_METRIC)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
            FROM skat.chunks AS c
            JOIN skat.chunk_embeddings AS e
              ON e.chunk_id = c.chunk_id
             AND e.embedding_model_id = %s
            WHERE e.embedding_text_sha256 <> c.embedding_text_sha256
            """,
            (model_id,),
        )
        conflicts = int(cur.fetchone()[0])
        cur.execute(
            """
            SELECT count(*) AS pending, coalesce(sum(c.token_count), 0) AS tokens
            FROM skat.chunks AS c
            WHERE NOT EXISTS (
                SELECT 1
                FROM skat.chunk_embeddings AS e
                WHERE e.chunk_id = c.chunk_id
                  AND e.embedding_model_id = %s
            )
            """,
            (model_id,),
        )
        pending, tokens = cur.fetchone()
        cur.execute(
            """
            SELECT token_count
            FROM skat.chunks AS c
            WHERE NOT EXISTS (
                SELECT 1
                FROM skat.chunk_embeddings AS e
                WHERE e.chunk_id = c.chunk_id
                  AND e.embedding_model_id = %s
            )
            ORDER BY c.chunk_id
            """,
            (model_id,),
        )
        token_rows = [int(row[0]) for row in cur.fetchall()]

    _expect(report, "hashkonflikter", conflicts, 0)
    report.pending_count = int(pending)
    report.pending_tokens = int(tokens)
    _expect(report, "manglende embeddings", report.pending_count, EXPECTED_PENDING)
    items = [BatchItem(str(index), "", token_count) for index, token_count in enumerate(token_rows)]
    report.batch_count = len(
        split_batches(items, max_inputs=DEFAULT_BATCH_INPUTS, max_tokens=DEFAULT_BATCH_TOKENS)
    )
    report.checks.append(f"forventet tokenforbrug (pending token_count): {report.pending_tokens}")
    report.checks.append(
        f"forventet batches: {report.batch_count} "
        f"(max {DEFAULT_BATCH_INPUTS} inputs / {DEFAULT_BATCH_TOKENS} tokens)"
    )
    if report.errors:
        raise SkatEmbedError("preflight fejlede:\n- " + "\n- ".join(report.errors))
    return report
