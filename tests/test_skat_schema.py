"""Integrationstests af SKAT Postgres-skemaet.

Kræver en tom database og JAILA_SKAT_DATABASE_URL.
Importerer ikke korpusdata og kalder ikke OpenAI.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
MIGRATE = ROOT / "backend" / "db" / "migrate.py"


def _load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


TEST_DB_NAME = "jaila_skat_test"


def _dsn() -> str:
    _load_env()
    return (os.getenv("JAILA_SKAT_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()


def _isolated_dsn(prod_dsn: str) -> str:
    """Testdatabase, så DROP SCHEMA ikke rører jaila_skat med 11.707 dokumenter."""
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(prod_dsn)
    test_dsn = urlunparse(parsed._replace(path=f"/{TEST_DB_NAME}"))
    psycopg = _require_psycopg()
    conn = psycopg.connect(prod_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB_NAME,))
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
    finally:
        conn.close()
    return test_dsn


def _require_psycopg():
    try:
        import psycopg
    except ImportError as exc:
        raise unittest.SkipTest(
            "psycopg mangler. pip install -r backend/db/requirements.txt"
        ) from exc
    return psycopg


SHA = "a" * 64
SHA_B = "b" * 64


def _sql_value(value):
    if isinstance(value, dict):
        from psycopg.types.json import Jsonb

        return Jsonb(value)
    return value


def _doc_row(document_id: str, source_oid: str, skm_number: str | None, summary: str) -> dict:
    return {
        "document_id": document_id,
        "schema_version": "jaila.skat.document.v1",
        "corpus": "skat_info_skm",
        "source_oid": source_oid,
        "skm_number": skm_number,
        "title": "Testafgørelse",
        "document_type": "Dom",
        "authority": "Landsskatteretten",
        "responsible_agency": "Skattestyrelsen",
        "case_number": "1-2",
        "publication_date": "2026-01-23",
        "decision_date": "2025-11-17",
        "publication_year": 2026,
        "main_topic": "Skat",
        "subtopic": None,
        "subject_terms": ["test"],
        "summary": summary,
        "source_url": "https://info.skat.dk/data.aspx?oid=" + source_oid,
        "document_status": "active",
        "replaced_by": None,
        "has_body": True,
        "has_assets": False,
        "has_ocr": False,
        "manual_source_check": False,
        "image_text_authority": "not_applicable",
        "content_sha256": SHA,
        "canonical_text_sha256": {"summary": SHA, "body": SHA_B, "references": SHA},
        "canonical_text_length": {"summary": 12, "body": 20, "references": 1},
        "raw_record": {},
    }


class SkatSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        dsn = _dsn()
        if not dsn:
            raise unittest.SkipTest(
                "Sæt JAILA_SKAT_DATABASE_URL. Start fx: docker compose -f backend/db/docker-compose.yml up -d"
            )
        psycopg = _require_psycopg()
        try:
            test_dsn = _isolated_dsn(dsn)
        except Exception as exc:
            raise unittest.SkipTest(f"kunne ikke oprette testdatabase: {exc}") from exc
        cls.psycopg = psycopg
        cls.dsn = test_dsn
        os.environ["JAILA_SKAT_DATABASE_URL"] = test_dsn
        cls.conn = psycopg.connect(test_dsn)
        cls.conn.autocommit = True
        with cls.conn.cursor() as cur:
            cur.execute("DROP SCHEMA IF EXISTS skat CASCADE")
        cls._migrate()

    @classmethod
    def _migrate(cls) -> None:
        import subprocess
        import sys

        env = os.environ.copy()
        env["JAILA_SKAT_DATABASE_URL"] = cls.dsn
        subprocess.check_call([sys.executable, str(MIGRATE)], cwd=str(ROOT), env=env)

    @classmethod
    def tearDownClass(cls) -> None:
        if getattr(cls, "conn", None) is not None:
            cls.conn.close()

    def setUp(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute("SET search_path TO skat, public")
            cur.execute(
                """
                TRUNCATE skat.legal_documents, skat.chunk_runs, skat.embedding_models
                RESTART IDENTITY CASCADE
                """
            )

    def _insert_document(self, **overrides):
        row = _doc_row(
            overrides.pop("document_id", "skat-info:oid:100"),
            overrides.pop("source_oid", "100"),
            overrides.pop("skm_number", "SKM2026.1.LSR"),
            overrides.pop("summary", "Hele resuméet står her og må ikke afkortes."),
        )
        row.update(overrides)
        cols = list(row.keys())
        placeholders = ", ".join(["%s"] * len(cols))
        sql = f"INSERT INTO skat.legal_documents ({', '.join(cols)}) VALUES ({placeholders})"
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
        chunk_id = overrides.pop("chunk_id", "skat-skm-chunk:" + uuid4().hex)
        values = {
            "chunk_id": chunk_id,
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
            "case_number": "1-2",
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
            "chunk_text": "Resuméchunk, afkortet med vilje.",
            "decision_context": "",
            "embedding_text": "embed",
            "contains_table": False,
            "contains_image": False,
            "contains_ocr": False,
            "previous_chunk_id": None,
            "next_chunk_id": None,
            "manual_source_check": False,
            "token_count": 12,
            "text_sha256": SHA,
            "embedding_text_sha256": SHA_B,
            "raw_record": {},
        }
        values.update(overrides)
        cols = list(values.keys())
        sql = f"INSERT INTO skat.chunks ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})"
        with self.conn.cursor() as cur:
            cur.execute(sql, [_sql_value(values[c]) for c in cols])
        return values

    def test_migrations_create_schema_on_empty_database(self):
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT filename FROM skat.schema_migrations ORDER BY filename"
            )
            names = [row[0] for row in cur.fetchall()]
        self.assertEqual(
            [
                "001_extensions.sql",
                "002_skat_schema.sql",
                "004_import_audit.sql",
                "005_question_number_text.sql",
                "006_provenance_and_reference_occurrences.sql",
                "007_lexical_retrieval_indexes.sql",
                "008_embedding_audit.sql",
                "010_structured_law_references.sql",
            ],
            names,
        )
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT extname FROM pg_extension
                WHERE extname IN ('vector', 'pgcrypto', 'pg_trgm', 'unaccent')
                ORDER BY 1
                """
            )
            self.assertEqual(
                ["pg_trgm", "pgcrypto", "unaccent", "vector"],
                [row[0] for row in cur.fetchall()],
            )

    def test_duplicate_source_oid_is_rejected(self):
        self._insert_document()
        with self.assertRaises(self.psycopg.errors.UniqueViolation):
            self._insert_document(document_id="skat-info:oid:101", skm_number="SKM2026.2.LSR")

    def test_duplicate_normalized_skm_number_is_rejected(self):
        self._insert_document()
        with self.assertRaises(self.psycopg.errors.UniqueViolation):
            self._insert_document(
                document_id="skat-info:oid:101",
                source_oid="101",
                skm_number="skm2026.1.lsr",
            )

    def test_token_count_over_1000_is_rejected(self):
        self._insert_document()
        run_id = self._insert_run()
        with self.assertRaises(self.psycopg.errors.CheckViolation):
            self._insert_chunk("skat-info:oid:100", run_id, token_count=1001)

    def test_chunk_index_unique_per_document_and_config(self):
        self._insert_document()
        run_id = self._insert_run()
        self._insert_chunk("skat-info:oid:100", run_id, chunk_index=0)
        with self.assertRaises(self.psycopg.errors.UniqueViolation):
            self._insert_chunk("skat-info:oid:100", run_id, chunk_index=0)

    def test_source_span_invalid_offsets_are_rejected(self):
        self._insert_document()
        run_id = self._insert_run()
        chunk = self._insert_chunk("skat-info:oid:100", run_id)
        with self.conn.cursor() as cur:
            with self.assertRaises(self.psycopg.errors.CheckViolation):
                cur.execute(
                    """
                    INSERT INTO skat.chunk_source_spans
                        (chunk_id, span_index, source, start_offset, end_offset, role)
                    VALUES (%s, 0, 'body', 10, 10, 'primary')
                    """,
                    (chunk["chunk_id"],),
                )

    def test_exact_summary_lookup_returns_full_document_summary(self):
        full = "Hele resuméet står her og må ikke afkortes."
        self._insert_document(summary=full)
        run_id = self._insert_run()
        self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_text="kort",
            section_type="summary",
            legal_weight="editorial",
        )
        with self.conn.cursor() as cur:
            cur.execute("SELECT skat.get_document_summary(%s)", ("skm2026.1.lsr",))
            self.assertEqual(full, cur.fetchone()[0])
            cur.execute(
                "SELECT summary FROM skat.get_document_by_identifier(%s)",
                ("100",),
            )
            self.assertEqual(full, cur.fetchone()[0])

    def test_final_result_lookup_returns_only_flagged_chunks(self):
        self._insert_document()
        run_id = self._insert_run()
        self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_index=0,
            section_type="summary",
            legal_weight="editorial",
            is_final_result=False,
        )
        result = self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_index=1,
            section_type="court_result",
            legal_weight="authoritative_result",
            is_final_result=True,
            chunk_kind="decision",
            chunk_text="Landsskatteretten stadfæster.",
        )
        with self.conn.cursor() as cur:
            cur.execute("SELECT chunk_id FROM skat.get_document_final_result(%s)", ("SKM2026.1.LSR",))
            rows = [row[0] for row in cur.fetchall()]
        self.assertEqual([result["chunk_id"]], rows)

    def test_reasoning_lookup_excludes_prior_instance(self):
        self._insert_document()
        run_id = self._insert_run()
        kept = self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_index=0,
            section_type="court_reasoning",
            legal_weight="authoritative_reasoning",
            chunk_text="Rettens begrundelse.",
        )
        self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_index=1,
            section_type="prior_instance_reasoning",
            legal_weight="prior_instance",
            chunk_text="Tidligere instans.",
        )
        with self.conn.cursor() as cur:
            cur.execute("SELECT chunk_id, legal_weight FROM skat.get_document_reasoning(%s)", ("SKM2026.1.LSR",))
            rows = cur.fetchall()
        self.assertEqual([(kept["chunk_id"], "authoritative_reasoning")], rows)

    def test_reference_foreign_keys(self):
        source = self._insert_document()
        target = self._insert_document(
            document_id="skat-info:oid:200",
            source_oid="200",
            skm_number="SKM2026.2.LSR",
            content_sha256=SHA_B,
        )
        run_id = self._insert_run()
        chunk = self._insert_chunk(source["document_id"], run_id)
        ref_id = uuid4()
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO skat.document_references (
                    reference_id, reference_key, source_document_id, source_chunk_id,
                    reference_type, cited_identifier, exact_reference_text,
                    target_document_id, target_url, resolution_status,
                    canonical_reference_sha256, occurrence_index, raw_record
                ) VALUES (
                    %s, 'skm:SKM2026.2.LSR', %s, %s,
                    'skm', 'SKM2026.2.LSR', 'SKM2026.2.LSR',
                    %s, 'https://info.skat.dk/data.aspx?oid=200', 'resolved',
                    %s, 0, '{}'::jsonb
                )
                """,
                (str(ref_id), source["document_id"], chunk["chunk_id"], target["document_id"], SHA),
            )
            with self.assertRaises(self.psycopg.errors.ForeignKeyViolation):
                cur.execute(
                    """
                    INSERT INTO skat.document_references (
                        reference_id, reference_key, source_document_id,
                        reference_type, exact_reference_text, resolution_status,
                        canonical_reference_sha256, occurrence_index, raw_record
                    ) VALUES (
                        %s, 'missing-doc', 'skat-info:oid:missing',
                        'skm', 'x', 'unresolved', %s, 0, '{}'::jsonb
                    )
                    """,
                    (str(uuid4()), SHA_B),
                )
            cur.execute("SELECT direction FROM skat.get_document_references(%s)", ("SKM2026.1.LSR",))
            directions = {row[0] for row in cur.fetchall()}
        self.assertEqual({"outgoing"}, directions)

        with self.conn.cursor() as cur:
            cur.execute("SELECT direction FROM skat.get_document_references(%s)", ("SKM2026.2.LSR",))
            self.assertEqual({"incoming"}, {row[0] for row in cur.fetchall()})

    def test_reference_occurrence_constraints(self):
        source = self._insert_document()
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO skat.document_references (
                    reference_id, reference_key, source_document_id,
                    reference_type, exact_reference_text, resolution_status,
                    canonical_reference_sha256, occurrence_index, raw_record
                ) VALUES (
                    %s, 'occ-0', %s, 'skm', 'x', 'unresolved', %s, 0, '{}'::jsonb
                )
                """,
                (str(uuid4()), source["document_id"], SHA),
            )
            with self.assertRaises(self.psycopg.errors.UniqueViolation):
                cur.execute(
                    """
                    INSERT INTO skat.document_references (
                        reference_id, reference_key, source_document_id,
                        reference_type, exact_reference_text, resolution_status,
                        canonical_reference_sha256, occurrence_index, raw_record
                    ) VALUES (
                        %s, 'occ-dup', %s, 'skm', 'x', 'unresolved', %s, 0, '{}'::jsonb
                    )
                    """,
                    (str(uuid4()), source["document_id"], SHA),
                )
            with self.assertRaises(self.psycopg.errors.CheckViolation):
                cur.execute(
                    """
                    INSERT INTO skat.document_references (
                        reference_id, reference_key, source_document_id,
                        reference_type, exact_reference_text, resolution_status,
                        canonical_reference_sha256, occurrence_index, raw_record
                    ) VALUES (
                        %s, 'occ-neg', %s, 'skm', 'x', 'unresolved', %s, -1, '{}'::jsonb
                    )
                    """,
                    (str(uuid4()), source["document_id"], SHA),
                )
            with self.assertRaises(self.psycopg.errors.CheckViolation):
                cur.execute(
                    """
                    INSERT INTO skat.document_references (
                        reference_id, reference_key, source_document_id,
                        reference_type, exact_reference_text, resolution_status,
                        canonical_reference_sha256, occurrence_index, raw_record
                    ) VALUES (
                        %s, 'occ-hex', %s, 'skm', 'x', 'unresolved', 'not-a-hash', 1, '{}'::jsonb
                    )
                    """,
                    (str(uuid4()), source["document_id"]),
                )

    def test_embedding_dimension_is_exactly_1536(self):
        self._insert_document()
        run_id = self._insert_run()
        chunk = self._insert_chunk("skat-info:oid:100", run_id)
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO skat.embedding_models (
                    provider, model_name, dimensions, distance_metric, model_revision
                ) VALUES ('openai', 'text-embedding-3-large', 1536, 'inner_product', 'test')
                RETURNING embedding_model_id
                """
            )
            model_id = cur.fetchone()[0]
            with self.assertRaises(self.psycopg.errors.DataException):
                cur.execute(
                    """
                    INSERT INTO skat.chunk_embeddings (
                        chunk_id, embedding_model_id, embedding, embedding_text_sha256
                    ) VALUES (%s, %s, %s::vector, %s)
                    """,
                    (chunk["chunk_id"], model_id, "[" + ",".join(["0"] * 3) + "]", SHA),
                )
            vector = "[" + ",".join(["0"] * 1536) + "]"
            cur.execute(
                """
                INSERT INTO skat.chunk_embeddings (
                    chunk_id, embedding_model_id, embedding, embedding_text_sha256
                ) VALUES (%s, %s, %s::vector, %s)
                """,
                (chunk["chunk_id"], model_id, vector, SHA),
            )
            with self.assertRaises(self.psycopg.errors.CheckViolation):
                cur.execute(
                    """
                    INSERT INTO skat.embedding_models (
                        provider, model_name, dimensions, distance_metric, model_revision
                    ) VALUES ('openai', 'wrong', 768, 'inner_product', 'x')
                    """
                )

    def test_hybrid_search_is_stubbed(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT chunk_id FROM skat.hybrid_search_chunks(%s)", ("moms",))
            self.assertEqual([], cur.fetchall())

    def test_retrieval_overview_counts_chunks_and_references(self):
        self._insert_document()
        run_id = self._insert_run()
        self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_index=0,
            is_final_result=True,
            section_type="court_result",
            legal_weight="authoritative_result",
        )
        self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_index=1,
            section_type="court_reasoning",
            legal_weight="authoritative_reasoning",
        )
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT chunk_count, final_result_count, authoritative_reasoning_count
                FROM skat.document_retrieval_overview
                WHERE document_id = 'skat-info:oid:100'
                """
            )
            self.assertEqual((2, 1, 1), cur.fetchone())


if __name__ == "__main__":
    unittest.main()
