"""Verifikation af embeddings. Ingen HNSW. Ingen dokumenttekst."""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.db.skat_embed.constants import (
    CORPUS_SELECTION_KEY,
    DIMENSIONS,
    MODEL_NAME,
    PILOT_SELECTION_KEY,
    PROVIDER,
)
from backend.db.skat_embed.errors import SkatEmbedError
from backend.db.skat_embed.select import select_pilot_chunks
from backend.db.skat_import.constants import (
    EXPECTED_CHUNK_COUNT,
    EXPECTED_DOCUMENT_COUNT,
    EXPECTED_REFERENCE_COUNT,
)


@dataclass
class VerifyReport:
    checks: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def ok(self) -> bool:
        return not self.errors


def _expect(report: VerifyReport, label: str, actual, expected) -> None:
    if actual != expected:
        report.errors.append(f"{label}: {actual}, forventet {expected}")
    else:
        report.checks.append(f"{label}: {actual}")


def hnsw_index_count(conn) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
            FROM pg_indexes
            WHERE schemaname = 'skat'
              AND indexdef ILIKE %s
            """,
            ("%hnsw%",),
        )
        return int(cur.fetchone()[0])


def verify_pilot(conn) -> VerifyReport:
    report = VerifyReport()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT embedding_model_id, provider, model_name, dimensions,
                   distance_metric, configuration, created_at
            FROM skat.embedding_models
            WHERE provider = %s AND model_name = %s AND dimensions = %s
            """,
            (PROVIDER, MODEL_NAME, DIMENSIONS),
        )
        models = cur.fetchall()
    if len(models) != 1:
        report.errors.append(f"forventede 1 embedding_models-række, fik {len(models)}")
        return report
    model_id, provider, model_name, dimensions, metric, configuration, created_at = models[0]
    _expect(report, "provider", provider, PROVIDER)
    _expect(report, "model_name", model_name, MODEL_NAME)
    _expect(report, "dimensions", int(dimensions), DIMENSIONS)
    _expect(report, "distance_metric", metric, "inner_product")
    if created_at is None:
        report.errors.append("embedding_models.created_at mangler")
    else:
        report.checks.append(f"created_at: {created_at.isoformat()}")
    if not isinstance(configuration, dict):
        report.errors.append("configuration er ikke jsonb-objekt")
    else:
        report.checks.append("configuration gemt")

    chunk_ids: list[str] | None = None
    if selection_key == PILOT_SELECTION_KEY:
        selected = select_pilot_chunks(conn)
        chunk_ids = [item.chunk_id for item in selected]
        _expect(report, "pilot_size", len(chunk_ids), 1000)

    with conn.cursor() as cur:
        if chunk_ids is not None:
            cur.execute(
                """
                SELECT count(*)
                FROM skat.chunk_embeddings
                WHERE embedding_model_id = %s
                  AND chunk_id = ANY(%s)
                """,
                (model_id, chunk_ids),
            )
            _expect(report, "pilot embeddings", int(cur.fetchone()[0]), len(chunk_ids))
            cur.execute(
                """
                SELECT count(*)
                FROM skat.chunks AS c
                JOIN skat.chunk_embeddings AS e
                  ON e.chunk_id = c.chunk_id
                 AND e.embedding_model_id = %s
                WHERE c.chunk_id = ANY(%s)
                  AND e.embedding_text_sha256 <> c.embedding_text_sha256
                """,
                (model_id, chunk_ids),
            )
            _expect(report, "hash-afvigelser", int(cur.fetchone()[0]), 0)
        cur.execute(
            """
            SELECT count(*)
            FROM skat.chunk_embeddings
            WHERE vector_dims(embedding) <> %s
            """,
            (DIMENSIONS,),
        )
        _expect(report, "forkerte dimensioner", int(cur.fetchone()[0]), 0)
        zero = "[" + ",".join(["0"] * DIMENSIONS) + "]"
        cur.execute(
            """
            SELECT count(*)
            FROM skat.chunk_embeddings
            WHERE embedding <-> %s::vector = 0
            """,
            (zero,),
        )
        _expect(report, "nul-vektorer", int(cur.fetchone()[0]), 0)
        cur.execute("SELECT count(*) FROM skat.chunk_embeddings")
        report.checks.append(f"chunk_embeddings i alt: {int(cur.fetchone()[0])}")
        cur.execute("SELECT count(*) FROM skat.query_embeddings")
        report.checks.append(f"query_embeddings: {int(cur.fetchone()[0])}")

    hnsw = hnsw_index_count(conn)
    _expect(report, "HNSW-indekser", hnsw, 0)
    if report.errors:
        raise SkatEmbedError("verify fejlede:\n- " + "\n- ".join(report.errors))
    return report


EXPECTED_SPANS = 1_941_364


def verify_corpus(conn, *, require_hnsw: bool = False) -> VerifyReport:
    """Slutverifikation af hele korpusset. require_hnsw=False før indeksbygning."""
    report = VerifyReport()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM skat.chunks")
        chunks = int(cur.fetchone()[0])
        cur.execute("SELECT count(*) FROM skat.legal_documents")
        docs = int(cur.fetchone()[0])
        cur.execute("SELECT count(*) FROM skat.chunk_source_spans")
        spans = int(cur.fetchone()[0])
        cur.execute("SELECT count(*) FROM skat.document_references")
        refs = int(cur.fetchone()[0])
        cur.execute(
            """
            SELECT embedding_model_id, provider, model_name, dimensions, distance_metric
            FROM skat.embedding_models
            """
        )
        models = cur.fetchall()
        cur.execute("SELECT count(*) FROM skat.chunk_embeddings")
        embeddings = int(cur.fetchone()[0])
        cur.execute("SELECT count(DISTINCT chunk_id) FROM skat.chunk_embeddings")
        distinct_chunks = int(cur.fetchone()[0])
        cur.execute(
            """
            SELECT count(*)
            FROM skat.chunks AS c
            WHERE NOT EXISTS (
                SELECT 1 FROM skat.chunk_embeddings AS e WHERE e.chunk_id = c.chunk_id
            )
            """
        )
        missing = int(cur.fetchone()[0])
        cur.execute(
            """
            SELECT count(*)
            FROM skat.chunk_embeddings AS e
            WHERE NOT EXISTS (
                SELECT 1 FROM skat.chunks AS c WHERE c.chunk_id = e.chunk_id
            )
            """
        )
        extra = int(cur.fetchone()[0])

    _expect(report, "chunks", chunks, EXPECTED_CHUNK_COUNT)
    _expect(report, "dokumenter", docs, EXPECTED_DOCUMENT_COUNT)
    _expect(report, "source spans", spans, EXPECTED_SPANS)
    _expect(report, "referencer", refs, EXPECTED_REFERENCE_COUNT)
    _expect(report, "chunk_embeddings", embeddings, EXPECTED_CHUNK_COUNT)
    _expect(report, "manglende embeddings", missing, 0)
    _expect(report, "ekstra embeddings", extra, 0)
    _expect(report, "dubletter", embeddings - distinct_chunks, 0)
    if len(models) != 1:
        report.errors.append(f"model mismatch: {len(models)} embedding_models-rækker")
        if report.errors:
            raise SkatEmbedError("verify fejlede:\n- " + "\n- ".join(report.errors))
        return report
    model_id, provider, model_name, dimensions, metric = models[0]
    _expect(report, "provider", provider, PROVIDER)
    _expect(report, "model_name", model_name, MODEL_NAME)
    _expect(report, "dimensions", int(dimensions), DIMENSIONS)
    _expect(report, "distance_metric", metric, "inner_product")

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
            FROM skat.chunk_embeddings
            WHERE embedding_model_id <> %s
            """,
            (model_id,),
        )
        _expect(report, "model mismatch", int(cur.fetchone()[0]), 0)
        cur.execute(
            """
            SELECT count(*)
            FROM skat.chunk_embeddings
            WHERE vector_dims(embedding) <> %s
            """,
            (DIMENSIONS,),
        )
        _expect(report, "forkerte dimensioner", int(cur.fetchone()[0]), 0)
        cur.execute(
            """
            SELECT count(*)
            FROM skat.chunks AS c
            JOIN skat.chunk_embeddings AS e ON e.chunk_id = c.chunk_id
            WHERE e.embedding_text_sha256 <> c.embedding_text_sha256
            """
        )
        _expect(report, "hash-afvigelser", int(cur.fetchone()[0]), 0)
        zero = "[" + ",".join(["0"] * DIMENSIONS) + "]"
        cur.execute(
            """
            SELECT count(*)
            FROM skat.chunk_embeddings
            WHERE embedding <-> %s::vector = 0
            """,
            (zero,),
        )
        _expect(report, "nul-vektorer", int(cur.fetchone()[0]), 0)
        cur.execute(
            """
            SELECT count(*)
            FROM skat.chunk_embeddings
            WHERE NOT ((embedding <#> embedding) = (embedding <#> embedding))
            """
        )
        _expect(report, "ikke-finite værdier", int(cur.fetchone()[0]), 0)

    hnsw = hnsw_index_count(conn)
    if require_hnsw:
        if hnsw < 1:
            report.errors.append("HNSW-indeks mangler")
        else:
            report.checks.append(f"HNSW-indekser: {hnsw}")
    else:
        _expect(report, "HNSW-indekser", hnsw, 0)
    report.checks.append("chunk- og dokumenttabeller: tællinger matcher korpusforventningerne")
    if report.errors:
        raise SkatEmbedError("verify fejlede:\n- " + "\n- ".join(report.errors))
    return report


def verify_selection(conn, *, selection_key: str = PILOT_SELECTION_KEY) -> VerifyReport:
    if selection_key in {CORPUS_SELECTION_KEY, "corpus"}:
        return verify_corpus(conn, require_hnsw=False)
    return verify_pilot(conn)
