"""Tests af embedding-worker. Kalder ikke OpenAI. Bruger jaila_skat_test."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from uuid import uuid4

from backend.db.skat_embed.client import (
    BatchItem,
    EmbedResponse,
    backoff_seconds,
    embed_texts,
    is_retryable,
    order_embeddings,
    split_batches,
)
from backend.db.skat_embed.constants import DIMENSIONS, MODEL_NAME, QUERY_PREFIX
from backend.db.skat_embed.errors import FullCorpusNotApprovedError, IntegrityError, VectorValidationError
from backend.db.skat_embed.vectors import validate_embedding

ROOT = Path(__file__).resolve().parents[1]
MIGRATE = ROOT / "backend" / "db" / "migrate.py"
SHA = "a" * 64
SHA_B = "b" * 64
TEST_DB_NAME = "jaila_skat_test"


def _load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        if key.strip() and key.strip() not in os.environ:
            os.environ[key.strip()] = value.strip().strip('"').strip("'")


def _dsn() -> str:
    _load_env()
    return (os.getenv("JAILA_SKAT_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()


def _isolated_dsn(prod_dsn: str) -> str:
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(prod_dsn)
    test_dsn = urlunparse(parsed._replace(path=f"/{TEST_DB_NAME}"))
    import psycopg

    conn = psycopg.connect(prod_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB_NAME,))
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
    finally:
        conn.close()
    return test_dsn


def _sql_value(value):
    if isinstance(value, dict):
        from psycopg.types.json import Jsonb

        return Jsonb(value)
    return value


def _nonzero_vector(seed: float = 1.0) -> list[float]:
    values = [0.0] * DIMENSIONS
    values[0] = seed
    values[1] = -seed / 2
    return values


class FakeAPI:
    def __init__(self, fail_times: int = 0, status: int = 429) -> None:
        self.fail_times = fail_times
        self.status = status
        self.calls: list[list[str]] = []

    def embeddings_create(self, *, model, dimensions, input, encoding_format):
        if self.fail_times > 0:
            self.fail_times -= 1
            error = RuntimeError("temporary")
            error.status_code = self.status
            raise error
        self.calls.append(list(input))
        vectors = []
        for index, text in enumerate(input):
            values = _nonzero_vector(float(index + 1))
            values[3] = float(len(text))
            vectors.append(values)
        return EmbedResponse(
            embeddings=vectors,
            model=model,
            prompt_tokens=len(input) * 4,
            total_tokens=len(input) * 4,
            request_id="test-req",
            http_status=200,
        )


class VectorTests(unittest.TestCase):
    def test_rejects_wrong_dimension_nan_and_zero(self):
        with self.assertRaises(VectorValidationError):
            validate_embedding([0.1, 0.2])
        bad = _nonzero_vector()
        bad[10] = float("nan")
        with self.assertRaises(VectorValidationError):
            validate_embedding(bad)
        with self.assertRaises(VectorValidationError):
            validate_embedding([0.0] * DIMENSIONS)

    def test_index_order_is_preserved(self):
        items = [
            {"index": 2, "embedding": _nonzero_vector(3)},
            {"index": 0, "embedding": _nonzero_vector(1)},
            {"index": 1, "embedding": _nonzero_vector(2)},
        ]
        ordered = order_embeddings(items, 3)
        self.assertEqual(ordered[0][0], 1.0)
        self.assertEqual(ordered[2][0], 3.0)

    def test_batches_respect_input_and_token_budget(self):
        items = [
            BatchItem("a", "x", 80),
            BatchItem("b", "y", 80),
            BatchItem("c", "z", 80),
        ]
        by_count = split_batches(items, max_inputs=2, max_tokens=10000)
        self.assertEqual([[item.item_id for item in batch] for batch in by_count], [["a", "b"], ["c"]])
        by_tokens = split_batches(items, max_inputs=10, max_tokens=150)
        self.assertEqual([[item.item_id for item in batch] for batch in by_tokens], [["a"], ["b"], ["c"]])

    def test_retry_on_429(self):
        api = FakeAPI(fail_times=2, status=429)
        result = embed_texts(["abc"], client=api, sleep=lambda _delay: None)
        self.assertEqual(len(result.embeddings[0]), DIMENSIONS)
        self.assertEqual(1, len(api.calls))

    def test_query_prefix_and_no_secret_in_error(self):
        os.environ["OPENAI_API_KEY"] = "sk-secret-test-key"
        from backend.db.skat_embed.keys import redact_secrets
        from backend.db.skat_embed.queries import query_input_text

        self.assertTrue(query_input_text("moms").startswith(QUERY_PREFIX))
        self.assertNotIn("sk-secret-test-key", redact_secrets("fejl sk-secret-test-key her"))
        self.assertTrue(is_retryable(type("E", (), {"status_code": 503})()))
        self.assertGreater(backoff_seconds(3, rng=__import__("random").Random(0)), 0)


class SkatEmbedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        dsn = _dsn()
        if not dsn:
            raise unittest.SkipTest("Sæt JAILA_SKAT_DATABASE_URL")
        try:
            import psycopg
        except ImportError as exc:
            raise unittest.SkipTest("psycopg mangler") from exc
        try:
            test_dsn = _isolated_dsn(dsn)
        except Exception as exc:
            raise unittest.SkipTest(f"kunne ikke oprette testdatabase: {exc}") from exc
        if test_dsn.rsplit("/", 1)[-1] != TEST_DB_NAME:
            raise unittest.SkipTest("testdatabase er ikke jaila_skat_test")
        cls.dsn = test_dsn
        os.environ["JAILA_SKAT_DATABASE_URL"] = test_dsn
        cls.conn = psycopg.connect(test_dsn)
        cls.conn.autocommit = True
        with cls.conn.cursor() as cur:
            cur.execute("DROP SCHEMA IF EXISTS skat CASCADE")
        env = os.environ.copy()
        env["JAILA_SKAT_DATABASE_URL"] = cls.dsn
        subprocess.check_call([sys.executable, str(MIGRATE)], cwd=str(ROOT), env=env)

    @classmethod
    def tearDownClass(cls) -> None:
        if getattr(cls, "conn", None) is not None:
            cls.conn.close()

    def setUp(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                TRUNCATE skat.legal_documents, skat.chunk_runs, skat.embedding_models
                RESTART IDENTITY CASCADE
                """
            )

    def _insert_document(self, **overrides):
        row = {
            "document_id": "skat-info:oid:100",
            "schema_version": "jaila.skat.document.v1",
            "corpus": "skat_info_skm",
            "source_oid": "100",
            "skm_number": "SKM2026.1.LSR",
            "title": "Test",
            "document_type": "Dom",
            "authority": "Landsskatteretten",
            "responsible_agency": "Skattestyrelsen",
            "case_number": "1",
            "publication_date": "2026-01-23",
            "decision_date": "2025-11-17",
            "publication_year": 2026,
            "main_topic": "Skat",
            "subtopic": None,
            "subject_terms": ["test"],
            "summary": "Resumé",
            "source_url": "https://info.skat.dk/data.aspx?oid=100",
            "document_status": "active",
            "replaced_by": None,
            "has_body": True,
            "has_assets": False,
            "has_ocr": False,
            "manual_source_check": False,
            "image_text_authority": "not_applicable",
            "content_sha256": SHA,
            "canonical_text_sha256": {"summary": SHA, "body": SHA_B, "references": SHA},
            "canonical_text_length": {"summary": 1, "body": 1, "references": 1},
            "raw_record": {},
        }
        row.update(overrides)
        cols = list(row.keys())
        sql = f"INSERT INTO skat.legal_documents ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})"
        with self.conn.cursor() as cur:
            cur.execute(sql, [_sql_value(row[c]) for c in cols])
        return row

    def _insert_run(self) -> str:
        run_id = str(uuid4())
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO skat.chunk_runs (
                    chunk_run_id, chunker_name, chunker_version, chunk_config_sha256,
                    schema_version, source_manifest_sha256, tokenizer_model,
                    tokenizer_encoding, target_tokens, hard_max_tokens,
                    overlap_tokens, config
                ) VALUES (
                    %s, 'skat-skm-structural', '1.0.1', %s,
                    'jaila.skat.chunk.v1', %s, 'text-embedding-3-large',
                    'cl100k_base', 800, 1000, 100, '{}'::jsonb
                )
                """,
                (run_id, SHA, SHA_B),
            )
        return run_id

    def _insert_chunk(self, document_id: str, run_id: str, **overrides):
        text = overrides.pop("embedding_text", "embeddingtekst om moms")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        values = {
            "chunk_id": overrides.pop("chunk_id", "skat-skm-chunk:" + uuid4().hex),
            "document_id": document_id,
            "chunk_run_id": run_id,
            "schema_version": "jaila.skat.chunk.v1",
            "source_oid": "100",
            "skm_number": "SKM2026.1.LSR",
            "chunker_version": "1.0.1",
            "chunk_config_sha256": SHA,
            "chunk_index": 0,
            "publication_date": "2026-01-23",
            "decision_date": "2025-11-17",
            "publication_year": 2026,
            "document_type": "Dom",
            "authority": "Landsskatteretten",
            "case_number": "1",
            "subject_terms": ["test"],
            "source_url": "https://info.skat.dk/data.aspx?oid=100",
            "section_type": "summary",
            "legal_weight": "editorial",
            "section_heading_original": None,
            "section_heading_normalized": None,
            "section_path_original": [],
            "section_path_normalized": [],
            "classification_method": "section_attribute",
            "question_number": None,
            "is_final_result": False,
            "chunk_kind": "text",
            "chunk_text": "synlig tekst",
            "decision_context": "",
            "embedding_text": text,
            "contains_table": False,
            "contains_image": False,
            "contains_ocr": False,
            "previous_chunk_id": None,
            "next_chunk_id": None,
            "manual_source_check": False,
            "token_count": 12,
            "text_sha256": digest,
            "embedding_text_sha256": digest,
            "raw_record": {},
        }
        values.update(overrides)
        cols = list(values.keys())
        sql = f"INSERT INTO skat.chunks ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})"
        with self.conn.cursor() as cur:
            cur.execute(sql, [_sql_value(values[c]) for c in cols])
        return values

    def test_dry_run_does_not_insert(self):
        from backend.db.skat_embed.worker import embed_chunk_ids

        self._insert_document()
        run_id = self._insert_run()
        chunk = self._insert_chunk("skat-info:oid:100", run_id)
        stats = embed_chunk_ids(
            self.conn,
            [chunk["chunk_id"]],
            phase="pilot",
            selection_key="test",
            dry_run=True,
            client=FakeAPI(),
        )
        with self.conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM skat.chunk_embeddings")
            self.assertEqual(0, cur.fetchone()[0])
            cur.execute("SELECT count(*) FROM skat.embedding_models")
            self.assertEqual(0, cur.fetchone()[0])
        self.assertEqual(1, stats.pending)

    def test_insert_skip_and_integrity(self):
        from backend.db.skat_embed.worker import embed_chunk_ids

        self._insert_document()
        run_id = self._insert_run()
        first = self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_index=0,
            embedding_text="første embeddingtekst",
        )
        second = self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_index=1,
            embedding_text="anden embeddingtekst",
        )
        api = FakeAPI()
        stats = embed_chunk_ids(
            self.conn,
            [first["chunk_id"], second["chunk_id"]],
            phase="pilot",
            selection_key="test",
            client=api,
        )
        self.assertEqual(2, stats.inserted)
        self.assertEqual(first["embedding_text"], api.calls[0][0])
        self.assertNotEqual("synlig tekst", api.calls[0][0])
        resume = embed_chunk_ids(
            self.conn,
            [first["chunk_id"], second["chunk_id"]],
            phase="pilot",
            selection_key="test",
            client=FakeAPI(),
        )
        self.assertEqual(0, resume.inserted)
        self.assertEqual(2, resume.skipped)
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE skat.chunk_embeddings
                SET embedding_text_sha256 = %s
                WHERE chunk_id = %s
                """,
                ("c" * 64, first["chunk_id"]),
            )
        with self.assertRaises(IntegrityError):
            embed_chunk_ids(
                self.conn,
                [first["chunk_id"]],
                phase="pilot",
                selection_key="test",
                client=FakeAPI(),
            )

    def test_query_embedding_same_dimensions(self):
        from backend.db.skat_embed.queries import embed_query_text

        result = embed_query_text("fradrag for moms", client=FakeAPI())
        self.assertEqual(DIMENSIONS, len(result.vector))
        self.assertTrue(any(value != 0 for value in result.vector))

    def test_corpus_requires_approval(self):
        from backend.db.skat_embed.worker import run_corpus

        with self.assertRaises(FullCorpusNotApprovedError):
            run_corpus(self.conn, approved=False)

    def test_no_hnsw_and_model_metadata(self):
        from backend.db.skat_embed.verify import hnsw_index_count
        from backend.db.skat_embed.worker import embed_chunk_ids

        self._insert_document()
        run_id = self._insert_run()
        chunk = self._insert_chunk("skat-info:oid:100", run_id)
        embed_chunk_ids(
            self.conn,
            [chunk["chunk_id"]],
            phase="pilot",
            selection_key="test",
            client=FakeAPI(),
        )
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT provider, model_name, dimensions, created_at, configuration
                FROM skat.embedding_models
                """
            )
            provider, model_name, dimensions, created_at, configuration = cur.fetchone()
            cur.execute(
                "SELECT vector_dims(embedding), embedding_text_sha256 FROM skat.chunk_embeddings"
            )
            dims, stored_sha = cur.fetchone()
        self.assertEqual("openai", provider)
        self.assertEqual(MODEL_NAME, model_name)
        self.assertEqual(1536, dimensions)
        self.assertIsNotNone(created_at)
        self.assertEqual(1536, dims)
        self.assertEqual(chunk["embedding_text_sha256"], stored_sha)
        self.assertEqual(0, hnsw_index_count(self.conn))
        dumped = json.dumps(configuration)
        self.assertNotIn("sk-", dumped)


if __name__ == "__main__":
    unittest.main()
