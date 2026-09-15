"""Tests af SKAT-retrieval. Bruger jaila_skat_test, ikke produktionskorpusset."""

from __future__ import annotations

import ast
import io
import json
import os
import re
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
MIGRATE = ROOT / "backend" / "db" / "migrate.py"
RETRIEVAL_DIR = ROOT / "backend" / "db" / "skat_retrieval"
SHA = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
TEST_DB_NAME = "jaila_skat_test"
_TEST_DB: dict[str, object] = {}


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


def _doc_row(document_id: str, source_oid: str, skm_number: str | None, summary: str) -> dict:
    return {
        "document_id": document_id,
        "schema_version": "jaila.skat.document.v1",
        "corpus": "skat_info_skm",
        "source_oid": source_oid,
        "skm_number": skm_number,
        "title": "Testafgørelse om momsfradrag",
        "document_type": "Dom",
        "authority": "Landsskatteretten",
        "responsible_agency": "Skattestyrelsen",
        "case_number": "1-2",
        "publication_date": "2026-01-23",
        "decision_date": "2025-11-17",
        "publication_year": 2026,
        "main_topic": "Skat",
        "subtopic": None,
        "subject_terms": ["moms", "fradrag"],
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


class RoutingTests(unittest.TestCase):
    def test_exact_skm_and_oid_routing(self):
        from backend.db.skat_retrieval.routing import (
            INTENT_EXACT,
            extract_identifier,
            route_query,
        )

        skm = route_query("SKM2026.46.BR")
        self.assertEqual(INTENT_EXACT, skm.intent)
        self.assertEqual("SKM2026.46.BR", skm.identifier)

        oid = route_query("skat-info:oid:2459841")
        self.assertEqual(INTENT_EXACT, oid.intent)

        for query in ("skm2026.46.br", " SKM 2026 . 46 . br ", "SKM2026.46.BR"):
            normalized = route_query(query)
            self.assertEqual(INTENT_EXACT, normalized.intent)
            self.assertEqual("SKM2026.46.BR", normalized.identifier)

        for malformed in ("notSKM2026.46.BR", "1234abc", "oid:abc"):
            self.assertIsNone(extract_identifier(malformed))
        self.assertEqual("skat-info:oid:2459841", oid.identifier)

        bare = route_query("2459841")
        self.assertEqual(INTENT_EXACT, bare.intent)
        self.assertEqual("2459841", bare.identifier)

    def test_command_routing_requires_identifier(self):
        from backend.db.skat_retrieval.routing import (
            INTENT_QUESTIONS,
            INTENT_REASONING,
            INTENT_REFERENCES,
            INTENT_RESULT,
            INTENT_SUMMARY,
            INTENT_TOPICAL,
            route_query,
        )

        self.assertEqual(INTENT_SUMMARY, route_query("Resumé af SKM2026.46.BR").intent)
        self.assertEqual(INTENT_RESULT, route_query("Hvad blev resultatet i SKM2026.46.BR?").intent)
        self.assertEqual(INTENT_REASONING, route_query("Giv præmisserne for SKM2026.46.BR").intent)
        self.assertEqual(INTENT_REFERENCES, route_query("Hvilke henvisninger har SKM2026.46.BR?").intent)
        self.assertEqual(INTENT_QUESTIONS, route_query("Hvilke spørgsmål stilles i SKM2026.46.BR?").intent)
        topical = route_query("Find sager om moms")
        self.assertEqual(INTENT_TOPICAL, topical.intent)
        self.assertIsNone(topical.identifier)

    def test_law_reference_variants_are_generic_and_scoped(self):
        from backend.db.skat_retrieval.law_refs import (
            extract_law_references,
            is_bare_law_reference,
            law_reference_variants,
            structured_reference_payload,
        )

        cases = (
            ("LL § 33 A", "Ligningslovens § 33A"),
            ("KSL 1", "Kildeskattelovens § 1"),
            ("ASKL § 12", "Aktiesparekontolovens § 12"),
            ("FORÆL § 3", "Forældelseslovens § 3"),
            ("KSLBek § 1", "Kildeskattebekendtgørelsens § 1"),
            ("eksempellovens § 7 b", "Eksempellovens § 7B"),
        )
        for query, expected in cases:
            variants = law_reference_variants(query)
            self.assertIn(expected, variants)
            self.assertTrue(is_bare_law_reference(query))
            self.assertTrue(all(not value.startswith("§") for value in variants))
        self.assertFalse(is_bare_law_reference("Find principielle sager om LL § 33 A"))
        self.assertEqual((), law_reference_variants("§ 33 A"))
        self.assertEqual((), law_reference_variants("Find sager om moms"))

        # MBL og ML er forskellige love; testen kræver ingen korpusforekomster.
        self.assertIn("Minimumsbeskatningslovens § 15", law_reference_variants("MBL § 15"))
        self.assertNotIn("Momslovens § 15", law_reference_variants("MBL § 15"))
        self.assertIn("Momslovens § 37", law_reference_variants("ML § 37"))

        specific = extract_law_references("KSL § 1, stk. 1, nr. 1")[0]
        self.assertEqual((1, "1", "1"), (specific.section_number, specific.subsection, specific.item_number))
        interval = extract_law_references("SFL §§ 26-27")[0]
        self.assertEqual((26, 27), (interval.section_number, interval.section_end_number))
        multiple = extract_law_references("LL § 16 og KSL § 1")
        self.assertEqual(["ll", "ksl"], [item.law_key for item in multiple])
        self.assertEqual(2, structured_reference_payload("LL § 16 og KSL § 1")[1])
        self.assertEqual(1, structured_reference_payload("LL § 16 eller KSL § 1")[1])
        self.assertEqual("kal", extract_law_references("lov om kreditaftaler § 3")[0].law_key)
        self.assertEqual("1908-lov", extract_law_references("1908-LOV § 1")[0].law_key)
        for non_law in ("§ 1", "HR § 1", "ApS § 1", "tekstKSL § 1"):
            self.assertEqual((), extract_law_references(non_law))

    def test_locked_architecture_uses_transaction_local_ef_search(self):
        from inspect import signature

        from backend.db.skat_retrieval.engine import retrieve
        from backend.db.skat_retrieval.settings import DEFAULT_CLI_SEARCH_MODE, DEFAULT_RETRIEVE_MODE, HNSW_EF_SEARCH
        from backend.db.skat_retrieval import tx, vector

        self.assertEqual("hybrid", DEFAULT_RETRIEVE_MODE)
        self.assertEqual("auto", DEFAULT_CLI_SEARCH_MODE)
        self.assertEqual(800, HNSW_EF_SEARCH)
        self.assertEqual("hybrid", signature(retrieve).parameters["mode"].default)
        vector_src = Path(vector.__file__).read_text(encoding="utf-8")
        tx_src = Path(tx.__file__).read_text(encoding="utf-8")
        self.assertIn("SET LOCAL hnsw.ef_search", vector_src)
        self.assertIn("execute_with_local_settings", vector_src)
        self.assertIn("SET LOCAL enable_indexscan = off", vector_src)
        self.assertIn("SET LOCAL enable_indexscan TO DEFAULT", vector_src)
        self.assertIn("SET LOCAL", tx_src)
        self.assertNotIn("SET hnsw.ef_search =", vector_src)

    def test_package_has_no_openai_or_vector_search(self):
        forbidden = {"openai", "OpenAI"}
        for path in RETRIEVAL_DIR.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("FROM skat.hybrid_search_chunks", source)
            self.assertNotIn("skat.hybrid_search_chunks(", source)
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn(alias.name.split(".")[0], forbidden)
                if isinstance(node, ast.ImportFrom) and node.module:
                    self.assertNotIn(node.module.split(".")[0], forbidden)
                    self.assertNotIn("openai", node.module)


    def test_cli_source_is_read_only(self):
        write_pattern = re.compile(
            r"\b(INSERT INTO|UPDATE\s+\w|DELETE FROM|DROP TABLE|DROP INDEX|DROP SCHEMA|ALTER TABLE|TRUNCATE |CREATE TABLE|CREATE INDEX)\b",
            re.IGNORECASE,
        )
        for path in RETRIEVAL_DIR.glob("*.py"):
            if path.name == "build_eval.py":
                continue
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("migrate.py", source)
            self.assertNotIn("--with-hnsw", source)
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if write_pattern.search(node.value):
                        self.fail(f"skrivende SQL i {path.name}")

    def test_missing_database_url_leaks_no_credentials(self):
        from backend.db.skat_retrieval.cli import main

        removed = os.environ.pop("JAILA_SKAT_DATABASE_URL", None)
        stdout = io.StringIO()
        stderr = io.StringIO()
        try:
            with patch("backend.db.skat_retrieval.db.load_env"):
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = main(
                        ["summary", "--identifier", "SKM2026.46.BR", "--format", "json"]
                    )
        finally:
            if removed is not None:
                os.environ["JAILA_SKAT_DATABASE_URL"] = removed
        self.assertEqual(4, code)
        out = stdout.getvalue()
        err = stderr.getvalue()
        combined = out + err
        self.assertEqual("", out.strip())
        self.assertNotIn("://", combined)
        self.assertNotIn("password", combined.lower())
        self.assertNotRegex(combined, r":[^:@\s/]+@")
        payload = json.loads(err)
        self.assertEqual("1.0", payload["schema_version"])
        self.assertEqual("database_error", payload["error"]["code"])
        self.assertIn("JAILA_SKAT_DATABASE_URL", payload["error"]["message"])


class SkatRetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cached = _TEST_DB.get("conn")
        if cached is not None:
            cls.psycopg = _TEST_DB["psycopg"]
            cls.dsn = _TEST_DB["dsn"]
            cls.conn = cached
            os.environ["JAILA_SKAT_DATABASE_URL"] = str(cls.dsn)
            return
        dsn = _dsn()
        if not dsn:
            raise unittest.SkipTest(
                "Sæt JAILA_SKAT_DATABASE_URL. Start fx: docker compose -f backend/db/docker-compose.yml up -d"
            )
        try:
            import psycopg
        except ImportError as exc:
            raise unittest.SkipTest(
                "psycopg mangler. pip install -r backend/db/requirements.txt"
            ) from exc
        try:
            test_dsn = _isolated_dsn(dsn)
        except Exception as exc:
            raise unittest.SkipTest(f"kunne ikke oprette testdatabase: {exc}") from exc
        parsed_name = test_dsn.rsplit("/", 1)[-1]
        if parsed_name != TEST_DB_NAME:
            raise unittest.SkipTest("testdatabase er ikke jaila_skat_test")
        cls.psycopg = psycopg
        cls.dsn = test_dsn
        os.environ["JAILA_SKAT_DATABASE_URL"] = test_dsn
        cls.conn = psycopg.connect(test_dsn)
        cls.conn.autocommit = True
        with cls.conn.cursor() as cur:
            cur.execute("DROP SCHEMA IF EXISTS skat CASCADE")
        env = os.environ.copy()
        env["JAILA_SKAT_DATABASE_URL"] = cls.dsn
        subprocess.check_call([sys.executable, str(MIGRATE)], cwd=str(ROOT), env=env)
        _TEST_DB.update(psycopg=psycopg, dsn=test_dsn, conn=cls.conn)

    @classmethod
    def tearDownClass(cls) -> None:
        conn = _TEST_DB.pop("conn", None)
        if conn is not None:
            conn.close()

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
        values = {
            "chunk_id": overrides.pop("chunk_id", "skat-skm-chunk:" + uuid4().hex),
            "document_id": document_id,
            "chunk_run_id": run_id,
            "schema_version": "jaila.skat.chunk.v1",
            "source_oid": overrides.pop("source_oid", "100"),
            "skm_number": overrides.pop("skm_number", "SKM2026.1.LSR"),
            "chunker_version": "1.0.1",
            "chunk_config_sha256": SHA,
            "chunk_index": 0,
            "publication_date": "2026-01-23",
            "decision_date": "2025-11-17",
            "publication_year": 2026,
            "document_type": "Dom",
            "authority": "Landsskatteretten",
            "case_number": "1-2",
            "subject_terms": ["moms", "fradrag"],
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

    def _run_cli(self, argv: list[str]) -> tuple[int, str, str]:
        from backend.db.skat_retrieval.cli import main

        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def _insert_reference(
        self,
        *,
        source_document_id: str,
        source_chunk_id: str | None,
        target_document_id: str | None,
        cited: str,
        occurrence_index: int,
        canonical: str,
        original_target: str | None = None,
        target_url: str | None = None,
        reference_type: str = "skm",
    ) -> None:
        from backend.db.skat_retrieval.law_refs import normalized_reference_columns

        normalized = (
            normalized_reference_columns(cited)
            if reference_type == "law_section"
            else (None,) * 8
        )
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO skat.document_references (
                    reference_id, reference_key, source_document_id, source_chunk_id,
                    reference_type, cited_identifier, exact_reference_text,
                    target_document_id, target_url, resolution_status,
                    canonical_reference_sha256, occurrence_index,
                    original_target_document_id, raw_record,
                    cited_law_key, cited_section_number, cited_section_suffix,
                    cited_section_end_number, cited_section_end_suffix,
                    cited_subsection, cited_item_number, cited_letter
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, '{}'::jsonb,
                    %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    str(uuid4()),
                    f"{canonical}:{occurrence_index}",
                    source_document_id,
                    source_chunk_id,
                    reference_type,
                    cited,
                    cited,
                    target_document_id,
                    target_url or "https://info.skat.dk/data.aspx?oid=200",
                    "resolved" if target_document_id else "unresolved",
                    canonical,
                    occurrence_index,
                    original_target,
                    *normalized,
                ),
            )

    def _pgvector(self, first: float) -> str:
        values = [0.0] * 1536
        values[0] = first
        return "[" + ",".join(str(v) for v in values) + "]"

    def _insert_query_embedding(self, query: str, first: float, model_id) -> None:
        from backend.db.skat_retrieval.vector import query_text_sha256

        digest = query_text_sha256(query)
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO skat.query_embeddings (
                    query_key, embedding_model_id, query_text_sha256,
                    embedding, purpose
                ) VALUES (%s, %s, %s, %s::vector, 'adhoc')
                """,
                (digest, model_id, digest, self._pgvector(first)),
            )

    def _insert_embedding_model(self):
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO skat.embedding_models (
                    provider, model_name, dimensions, distance_metric, model_revision
                ) VALUES ('openai', 'text-embedding-3-large', 1536, 'inner_product', 'test')
                RETURNING embedding_model_id
                """
            )
            return cur.fetchone()[0]

    def test_exact_skm_and_oid_lookup(self):
        from backend.db.skat_retrieval.engine import retrieve

        full = "Hele resuméet står her og må ikke afkortes."
        self._insert_document(
            summary=full,
            document_id="skat-info:oid:10001",
            source_oid="10001",
        )
        for query in ("SKM2026.1.LSR", "skat-info:oid:10001", "10001"):
            response = retrieve(self.conn, query)
            self.assertIsNotNone(response.document)
            self.assertEqual("skat-info:oid:10001", response.document.document_id)
            self.assertEqual(full, response.summary)
            self.assertIsNone(response.hits)

    def test_exact_skm_lookup_is_normalized_and_does_not_confuse_nearby_identifiers(self):
        from backend.db.skat_retrieval.engine import retrieve

        first = self._insert_document(
            document_id="skat-info:oid:181",
            source_oid="181",
            skm_number="SKM2026.18.ØLR",
            title="Den ønskede landsretsdom",
        )
        self._insert_document(
            document_id="skat-info:oid:182",
            source_oid="182",
            skm_number="SKM2026.180.ØLR",
            title="Næsten samme nummer",
            content_sha256=SHA_B,
        )
        self._insert_document(
            document_id="skat-info:oid:183",
            source_oid="183",
            skm_number="SKM2026.18.SR",
            title="Samme løbenummer, anden myndighed",
            content_sha256=SHA_C,
        )

        for query in ("SKM2026.18.ØLR", "skm2026.18.ølr", "SKM 2026 . 18 . ØLR"):
            response = retrieve(self.conn, query)
            self.assertEqual(first["document_id"], response.document.document_id)
            self.assertEqual("Den ønskede landsretsdom", response.document.title)

    def test_oid_lookup_supports_document_without_skm_number(self):
        from backend.db.skat_retrieval.engine import retrieve

        document = self._insert_document(
            document_id="skat-info:oid:91919",
            source_oid="91919",
            skm_number=None,
            title="Dokument uden SKM-nummer",
        )
        for query in ("91919", "oid:91919", "skat-info:oid:91919"):
            self.assertEqual(document["document_id"], retrieve(self.conn, query).document.document_id)

    def test_identifier_lookup_is_parameterized(self):
        from backend.db.skat_retrieval.errors import IdentifierNotFoundError
        from backend.db.skat_retrieval.lookup import get_document

        self._insert_document()
        with self.assertRaises(IdentifierNotFoundError):
            get_document(self.conn, "SKM2026.1.LSR' OR '1'='1")
        with self.conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM skat.legal_documents")
            self.assertEqual(1, cur.fetchone()[0])

    def test_summary_is_full_and_unbroken(self):
        from backend.db.skat_retrieval.engine import retrieve
        from backend.db.skat_retrieval.lookup import get_summary

        full = "A" * 400 + " mellemled " + "B" * 400
        self._insert_document(summary=full)
        run_id = self._insert_run()
        self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_text="Afkortet resuméchunk.",
            section_type="summary",
        )
        response = retrieve(self.conn, "Giv mig resuméet af SKM2026.1.LSR")
        self.assertEqual(full, response.summary)
        self.assertEqual(full, get_summary(self.conn, "SKM2026.1.LSR"))
        self.assertNotIn("Afkortet", response.summary)
        self.assertIn("aldrig rekonstrueret fra embeddings", response.note)

    def test_final_result_chunks_keep_chunk_index_order(self):
        from backend.db.skat_retrieval.engine import retrieve

        self._insert_document()
        run_id = self._insert_run()
        second = self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_index=2,
            section_type="court_result",
            legal_weight="authoritative_result",
            is_final_result=True,
            chunk_kind="decision",
            chunk_text="Anden resultatchunk.",
        )
        first = self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_index=1,
            section_type="court_result",
            legal_weight="authoritative_result",
            is_final_result=True,
            chunk_kind="decision",
            chunk_text="Første resultatchunk.",
        )
        self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_index=0,
            section_type="summary",
            legal_weight="editorial",
            is_final_result=False,
            chunk_text="Ikke resultat.",
        )
        response = retrieve(self.conn, "Hvad blev resultatet i SKM2026.1.LSR?")
        ids = [chunk.chunk_id for chunk in response.chunks]
        self.assertEqual([first["chunk_id"], second["chunk_id"]], ids)
        indexes = [chunk.chunk_index for chunk in response.chunks]
        self.assertEqual(indexes, sorted(indexes))
        self.assertTrue(all(chunk.is_final_result for chunk in response.chunks))

    def test_reasoning_excludes_prior_instance(self):
        from backend.db.skat_retrieval.engine import retrieve

        self._insert_document()
        run_id = self._insert_run()
        kept = self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_index=0,
            section_type="court_reasoning",
            legal_weight="authoritative_reasoning",
            chunk_text="Rettens aktuelle begrundelse.",
        )
        self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_index=1,
            section_type="prior_instance_reasoning",
            legal_weight="prior_instance",
            chunk_text="Tidligere instans må ikke medtages.",
        )
        response = retrieve(self.conn, "Hvad er begrundelsen i SKM2026.1.LSR?")
        weights = {chunk.legal_weight for chunk in response.chunks}
        self.assertEqual({"authoritative_reasoning"}, weights)
        self.assertEqual([kept["chunk_id"]], [chunk.chunk_id for chunk in response.chunks])

    def test_incoming_and_outgoing_references(self):
        from backend.db.skat_retrieval.engine import retrieve

        source = self._insert_document()
        target = self._insert_document(
            document_id="skat-info:oid:200",
            source_oid="200",
            skm_number="SKM2022.129.OLR",
            content_sha256=SHA_B,
            title="Ældre landsretsdom",
        )
        run_id = self._insert_run()
        chunk = self._insert_chunk(source["document_id"], run_id)
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO skat.document_references (
                    reference_id, reference_key, source_document_id, source_chunk_id,
                    reference_type, cited_identifier, exact_reference_text,
                    target_document_id, target_url, resolution_status,
                    canonical_reference_sha256, occurrence_index, raw_record
                ) VALUES (
                    %s, 'skm:SKM2022.129.OLR', %s, %s,
                    'skm', 'SKM2022.129.OLR', 'SKM2022.129.OLR',
                    %s, 'https://info.skat.dk/data.aspx?oid=200', 'resolved',
                    %s, 0, '{}'::jsonb
                )
                """,
                (str(uuid4()), source["document_id"], chunk["chunk_id"], target["document_id"], SHA_C),
            )
        outgoing = retrieve(self.conn, "Vis referencerne for SKM2026.1.LSR")
        self.assertEqual({"outgoing"}, {row.direction for row in outgoing.references})
        self.assertEqual("SKM2022.129.OLR", outgoing.references[0].cited_identifier)
        incoming = retrieve(self.conn, "Hvilke henvisninger har SKM2022.129.OLR?")
        self.assertEqual({"incoming"}, {row.direction for row in incoming.references})

    def test_metadata_filters_year_authority_and_type(self):
        from backend.db.skat_retrieval.search import lexical_search

        self._insert_document()
        other = self._insert_document(
            document_id="skat-info:oid:200",
            source_oid="200",
            skm_number="SKM2015.9.SR",
            publication_year=2015,
            publication_date="2015-03-01",
            document_type="Bindende svar",
            authority="Skatterådet",
            content_sha256=SHA_B,
            title="Bindende svar om udbytte",
        )
        run_id = self._insert_run()
        self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_text="Fradrag for moms i udlejningsejendom ved Landsskatteretten.",
            publication_year=2026,
        )
        self._insert_chunk(
            other["document_id"],
            run_id,
            source_oid="200",
            skm_number="SKM2015.9.SR",
            chunk_text="Udbytte og fradrag i bindende svar fra Skatterådet.",
            publication_year=2015,
            document_type="Bindende svar",
            authority="Skatterådet",
            source_url="https://info.skat.dk/data.aspx?oid=200",
        )
        hits = lexical_search(
            self.conn,
            "fradrag",
            filters={"year": 2015, "authority": "Skatterådet", "document_type": "Bindende svar"},
        )
        self.assertTrue(hits)
        self.assertEqual({"skat-info:oid:200"}, {hit.document_id for hit in hits})

    def test_danish_full_text_search(self):
        from backend.db.skat_retrieval.search import lexical_search

        self._insert_document()
        run_id = self._insert_run()
        self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_text="Skatteyderen fik fradrag for moms ved udlejning af fast ejendom.",
            section_heading_normalized="Fradrag for moms",
        )
        hits = lexical_search(self.conn, "fradrag moms")
        self.assertTrue(hits)
        self.assertIn("dansk full-text", hits[0].signals)
        self.assertEqual("skat-info:oid:100", hits[0].document_id)

    def test_law_reference_search_uses_structured_references(self):
        from backend.db.skat_retrieval.engine import retrieve
        from backend.db.skat_retrieval.search import lexical_search

        document = self._insert_document(
            skm_number="SKM2024.77.BR",
            title="Syntetisk sag om en generisk lovhenvisning",
            publication_year=2023,
        )
        run_id = self._insert_run()
        chunk = self._insert_chunk(
            document["document_id"],
            run_id,
            skm_number="SKM2024.77.BR",
            publication_year=2023,
            chunk_text="Landsrettens principielle begrundelse om pilotens udlandsophold.",
            legal_weight="authoritative_reasoning",
        )
        self._insert_reference(
            source_document_id=document["document_id"],
            source_chunk_id=chunk["chunk_id"],
            target_document_id=None,
            cited="Eksempellovens § 7B",
            occurrence_index=0,
            canonical=SHA,
            reference_type="law_section",
        )

        hits = lexical_search(self.conn, "eksempelloven § 7 B")

        self.assertTrue(hits)
        self.assertEqual("SKM2024.77.BR", hits[0].skm_number)
        self.assertIn("struktureret lovhenvisning", hits[0].signals)
        with patch(
            "backend.db.skat_retrieval.engine.resolve_query_vector",
            side_effect=AssertionError("ren lovhenvisning i auto må ikke kalde embedding-API"),
        ):
            response = retrieve(self.conn, "eksempelloven § 7 B", mode="auto")
        self.assertEqual("lexical", response.effective_mode)
        self.assertIsNone(response.embedding_usage)
        self.assertEqual("SKM2024.77.BR", response.hits[0].skm_number)

    def test_structured_references_handle_specificity_ranges_and_boolean_combinations(self):
        from backend.db.skat_retrieval.search import lexical_search

        run_id = self._insert_run()

        def add_case(number: int, references: tuple[str, ...]) -> str:
            document_id = f"skat-info:oid:{number}"
            skm = f"SKM2026.{number}.BR"
            self._insert_document(
                document_id=document_id,
                source_oid=str(number),
                skm_number=skm,
                title=f"Syntetisk referencesag {number}",
            )
            chunk = self._insert_chunk(
                document_id,
                run_id,
                source_oid=str(number),
                skm_number=skm,
                chunk_text="Neutral tekst uden lovnavne.",
            )
            for occurrence, cited in enumerate(references):
                self._insert_reference(
                    source_document_id=document_id,
                    source_chunk_id=chunk["chunk_id"],
                    target_document_id=None,
                    cited=cited,
                    occurrence_index=occurrence,
                    canonical=f"{number * 10 + occurrence:064x}",
                    reference_type="law_section",
                )
            return document_id

        exact = add_case(101, ("Kildeskattelovens § 1, stk. 1, nr. 1",))
        other_subsection = add_case(102, ("Kildeskattelovens § 1, stk. 2",))
        wrong_law = add_case(103, ("Selskabsskattelovens § 1",))
        section_26 = add_case(104, ("Skatteforvaltningslovens § 26",))
        section_27 = add_case(105, ("Skatteforvaltningslovens § 27",))
        both = add_case(106, ("Ligningslovens § 16", "Kildeskattelovens § 1"))
        ll_only = add_case(107, ("Ligningslovens § 16",))

        specific = lexical_search(self.conn, "KSL § 1, stk. 1, nr. 1")
        self.assertEqual(exact, specific[0].document_id)
        structured_ids = {
            hit.document_id
            for hit in specific
            if "struktureret lovhenvisning" in hit.signals
        }
        self.assertIn(other_subsection, structured_ids)
        self.assertNotIn(wrong_law, structured_ids)

        interval_ids = {
            hit.document_id
            for hit in lexical_search(self.conn, "SFL §§ 26-27")
            if "struktureret lovhenvisning" in hit.signals
        }
        self.assertTrue({section_26, section_27}.issubset(interval_ids))

        and_ids = {
            hit.document_id
            for hit in lexical_search(self.conn, "LL § 16 og KSL § 1")
            if "struktureret lovhenvisning" in hit.signals
        }
        self.assertEqual({both}, and_ids)
        or_ids = {
            hit.document_id
            for hit in lexical_search(self.conn, "LL § 16 eller KSL § 1")
            if "struktureret lovhenvisning" in hit.signals
        }
        self.assertTrue({exact, other_subsection, both, ll_only}.issubset(or_ids))

    def test_hybrid_scopes_semantics_to_structured_reference_documents(self):
        from backend.db.skat_retrieval.vector import hybrid_search

        document = self._insert_document(
            document_id="skat-info:oid:808",
            source_oid="808",
            skm_number="SKM2026.808.BR",
        )
        run_id = self._insert_run()
        chunk = self._insert_chunk(
            document["document_id"],
            run_id,
            source_oid="808",
            skm_number="SKM2026.808.BR",
            chunk_text="Neutral tekst.",
        )
        self._insert_reference(
            source_document_id=document["document_id"],
            source_chunk_id=chunk["chunk_id"],
            target_document_id=None,
            cited="Eksempellovens § 7 B",
            occurrence_index=0,
            canonical="8" * 64,
            reference_type="law_section",
        )

        with patch("backend.db.skat_retrieval.vector.vector_search", return_value=[]) as vector:
            hits = hybrid_search(
                self.conn,
                "et semantisk emne efter eksempellovens § 7 B",
                query_vector="[0]",
            )
        self.assertTrue(hits)
        self.assertEqual(
            [document["document_id"]],
            vector.call_args.kwargs["candidate_document_ids"],
        )

    def test_hybrid_uses_global_semantics_when_reference_has_no_structured_candidates(self):
        from backend.db.skat_retrieval.vector import hybrid_search

        self._insert_document()
        run_id = self._insert_run()
        self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_text="Et semantisk emne uden den efterspurgte lovhenvisning.",
        )
        with patch("backend.db.skat_retrieval.vector.vector_search", return_value=[]) as vector:
            hybrid_search(
                self.conn,
                "et semantisk emne efter eksempellovens § 999",
                query_vector="[0]",
            )
        self.assertIsNone(vector.call_args.kwargs["candidate_document_ids"])

    def test_law_reference_backfill_is_idempotent_and_preserves_original_text(self):
        from backend.db.backfill_law_references import backfill

        document = self._insert_document()
        run_id = self._insert_run()
        chunk = self._insert_chunk(document["document_id"], run_id)
        original = "Kildeskattelovens § 1, stk. 1, nr. 1"
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO skat.document_references (
                    reference_id, reference_key, source_document_id, source_chunk_id,
                    reference_type, cited_identifier, exact_reference_text,
                    resolution_status, canonical_reference_sha256, occurrence_index,
                    raw_record
                ) VALUES (%s, %s, %s, %s, 'law_section', %s, %s,
                          'unresolved', %s, 0, '{}'::jsonb)
                """,
                (str(uuid4()), "backfill:test", document["document_id"], chunk["chunk_id"], original, original, SHA),
            )

        dry = backfill(self.conn, dry_run=True)
        self.assertEqual(1, dry["parsed"])
        with self.conn.cursor() as cur:
            cur.execute("SELECT cited_law_key FROM skat.document_references")
            self.assertIsNone(cur.fetchone()[0])

        first = backfill(self.conn)
        second = backfill(self.conn)
        self.assertEqual(first, second)
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT cited_identifier, exact_reference_text, cited_law_key,
                       cited_section_number, cited_subsection, cited_item_number
                FROM skat.document_references
                """
            )
            self.assertEqual((original, original, "ksl", 1, "1", "1"), cur.fetchone())

    def test_ranking_is_deterministic(self):
        from backend.db.skat_retrieval.search import lexical_search

        self._insert_document()
        run_id = self._insert_run()
        other = self._insert_document(
            document_id="skat-info:oid:200",
            source_oid="200",
            skm_number="SKM2026.2.LSR",
            content_sha256=SHA_B,
            title="Anden sag om fradrag",
        )
        for index, heading in enumerate(("Momsfradrag", "Udlejning", "Bevisbyrde")):
            self._insert_chunk(
                "skat-info:oid:100",
                run_id,
                chunk_index=index,
                chunk_text=f"Tekst om {heading.lower()} og fradrag i sagen.",
                section_heading_normalized=heading,
            )
        self._insert_chunk(
            other["document_id"],
            run_id,
            source_oid="200",
            skm_number="SKM2026.2.LSR",
            chunk_text="Anden tekst om fradrag.",
            source_url="https://info.skat.dk/data.aspx?oid=200",
        )
        first = [(hit.chunk_id, hit.rank_score, hit.signals) for hit in lexical_search(self.conn, "fradrag")]
        second = [(hit.chunk_id, hit.rank_score, hit.signals) for hit in lexical_search(self.conn, "fradrag")]
        self.assertEqual(first, second)
        self.assertGreater(len(first), 1)

    def test_manual_source_check_follows_hit(self):
        from backend.db.skat_retrieval.engine import retrieve
        from backend.db.skat_retrieval.search import lexical_search

        self._insert_document(manual_source_check=True)
        run_id = self._insert_run()
        self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_text="Kontrolleret kildetekst om fradrag.",
            manual_source_check=True,
        )
        response = retrieve(self.conn, "SKM2026.1.LSR")
        self.assertTrue(response.document.manual_source_check)
        hits = lexical_search(self.conn, "fradrag")
        self.assertTrue(hits)
        self.assertTrue(hits[0].manual_source_check)

    def test_search_sql_has_no_vector_dependency(self):
        from backend.db.skat_retrieval import search

        source = Path(search.__file__).read_text(encoding="utf-8")
        self.assertNotIn("chunk_embeddings", source)
        self.assertNotIn("FROM skat.hybrid_search_chunks", source)
        self.assertNotIn("skat.hybrid_search_chunks(", source)
        self.assertNotIn("import openai", source.lower())
        with self.conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM skat.chunk_embeddings")
            self.assertEqual(0, cur.fetchone()[0])
            cur.execute(
                """
                SELECT indexname FROM pg_indexes
                WHERE schemaname = 'skat' AND indexdef ILIKE '%hnsw%'
                """
            )
            self.assertEqual([], cur.fetchall())


    def test_one_best_chunk_per_document(self):
        from backend.db.skat_retrieval.search import lexical_search

        self._insert_document()
        run_id = self._insert_run()
        best = self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_index=0,
            chunk_text="Fradrag for moms i den bedst matchende chunk.",
            section_heading_normalized="Fradrag for moms",
        )
        self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_index=1,
            chunk_text="En svagere chunk der også nævner fradrag.",
        )
        hits = lexical_search(self.conn, "fradrag moms")
        self.assertEqual(1, len(hits))
        self.assertEqual(best["chunk_id"], hits[0].chunk_id)

    def test_section_type_and_year_and_document_type_filters(self):
        from backend.db.skat_retrieval.search import lexical_search

        self._insert_document()
        other = self._insert_document(
            document_id="skat-info:oid:200",
            source_oid="200",
            skm_number="SKM2015.9.SR",
            publication_year=2015,
            publication_date="2015-03-01",
            document_type="Bindende svar",
            content_sha256=SHA_B,
            title="Bindende svar om fradrag",
        )
        run_id = self._insert_run()
        self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_text="Fradrag i rettens begrundelse.",
            section_type="court_reasoning",
            legal_weight="authoritative_reasoning",
            publication_year=2026,
        )
        self._insert_chunk(
            other["document_id"],
            run_id,
            source_oid="200",
            skm_number="SKM2015.9.SR",
            chunk_text="Fradrag i bindende svar.",
            publication_year=2015,
            document_type="Bindende svar",
            section_type="summary",
            source_url="https://info.skat.dk/data.aspx?oid=200",
        )
        hits = lexical_search(
            self.conn,
            "fradrag",
            filters={"year_from": 2015, "year_to": 2015, "document_type": "Bindende svar"},
        )
        self.assertEqual({"skat-info:oid:200"}, {hit.document_id for hit in hits})
        reasoning = lexical_search(
            self.conn,
            "fradrag",
            filters={"section_type": "court_reasoning"},
        )
        self.assertEqual({"skat-info:oid:100"}, {hit.document_id for hit in reasoning})
        self.assertTrue(all(hit.section_type == "court_reasoning" for hit in reasoning))

    def test_duplicate_reference_occurrences_are_kept(self):
        from backend.db.skat_retrieval.lookup import get_references

        source = self._insert_document()
        target = self._insert_document(
            document_id="skat-info:oid:200",
            source_oid="200",
            skm_number="SKM2022.129.OLR",
            content_sha256=SHA_B,
            title="Ældre landsretsdom",
        )
        run_id = self._insert_run()
        chunk = self._insert_chunk(source["document_id"], run_id)
        self._insert_reference(
            source_document_id=source["document_id"],
            source_chunk_id=chunk["chunk_id"],
            target_document_id=target["document_id"],
            cited="SKM2022.129.OLR",
            occurrence_index=0,
            canonical=SHA,
        )
        self._insert_reference(
            source_document_id=source["document_id"],
            source_chunk_id=chunk["chunk_id"],
            target_document_id=target["document_id"],
            cited="SKM2022.129.OLR",
            occurrence_index=1,
            canonical=SHA,
        )
        rows = get_references(self.conn, "SKM2026.1.LSR")
        outgoing = [row for row in rows if row.direction == "outgoing"]
        self.assertEqual(2, len(outgoing))
        self.assertEqual({0, 1}, {row.occurrence_index for row in outgoing})

    def test_lookup_routes_never_call_embeddings(self):
        from backend.db.skat_retrieval.engine import retrieve
        from backend.db.skat_retrieval import vector

        full = "Hele resuméet står her og må ikke afkortes."
        self._insert_document(summary=full)
        with patch.object(
            vector, "vector_search", side_effect=AssertionError("A–E må ikke bruge embeddings")
        ), patch.object(
            vector, "hybrid_search", side_effect=AssertionError("A–E må ikke bruge embeddings")
        ), patch(
            "backend.db.skat_retrieval.engine.resolve_query_vector",
            side_effect=AssertionError("A–E må aldrig kalde embedding-API"),
        ):
            response = retrieve(self.conn, "Giv mig resuméet af SKM2026.1.LSR", mode="vector")
        self.assertEqual("lookup", response.effective_mode)
        self.assertEqual("B", response.resolved_route)
        self.assertEqual(full, response.summary)

    def test_missing_query_embedding_falls_back_to_lexical(self):
        from backend.db.skat_retrieval.engine import retrieve

        self._insert_document()
        run_id = self._insert_run()
        self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_text="Fradrag for moms ved udlejning.",
        )
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            response = retrieve(self.conn, "fradrag for moms", mode="hybrid")
        self.assertEqual("hybrid", response.requested_mode)
        self.assertEqual("lexical", response.effective_mode)
        self.assertEqual("missing_openai_api_key", response.fallback_reason)
        self.assertEqual("F", response.resolved_route)
        self.assertTrue(response.hits)
        self.assertIsNone(response.embedding_usage)

    def test_exact_and_high_risk_flags_use_same_scan(self):
        from backend.db.skat_retrieval.engine import _ranked_mode

        self.assertEqual(("vector", True, "exact"), _ranked_mode("exact", False))
        self.assertEqual(("hybrid", True, "exact"), _ranked_mode("hybrid", True))
        self.assertEqual(("hybrid", False, "hybrid"), _ranked_mode("auto", False))
        self.assertEqual(("hybrid", True, "exact"), _ranked_mode("auto", True))

    def test_hnsw_ef_search_is_transaction_local(self):
        from backend.db.skat_retrieval.vector import vector_search

        self._insert_document()
        run_id = self._insert_run()
        chunk = self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_text="Fradrag for moms.",
        )
        model_id = self._insert_embedding_model()
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO skat.chunk_embeddings (
                    chunk_id, embedding_model_id, embedding, embedding_text_sha256
                ) VALUES (%s, %s, %s::vector, %s)
                """,
                (chunk["chunk_id"], model_id, self._pgvector(1.0), SHA),
            )
        self._insert_query_embedding("fradrag for moms", 1.0, model_id)
        captured: list[tuple[str, ...]] = []
        orig = None
        from backend.db.skat_retrieval import vector as vector_mod

        orig = vector_mod.execute_with_local_settings

        def spy(conn, settings, sql, params):
            captured.append(tuple(settings))
            return orig(conn, settings, sql, params)

        with patch.object(vector_mod, "execute_with_local_settings", spy):
            hits = vector_search(self.conn, "fradrag for moms", limit=5)
        self.assertTrue(hits)
        self.assertEqual(("SET LOCAL hnsw.ef_search = 800",), captured[0])
        exact_hits = vector_search(
            self.conn, "fradrag for moms", limit=5, exact_vector=True
        )
        self.assertTrue(exact_hits)
        src = Path(vector_mod.__file__).read_text(encoding="utf-8")
        self.assertIn("SET LOCAL enable_indexscan = off", src)
        self.assertIn("SET LOCAL enable_indexscan TO DEFAULT", src)

    def test_cli_json_contracts_for_all_commands(self):
        full = "Hele resuméet med æøå står her og må ikke afkortes."
        self._insert_document(summary=full)
        run_id = self._insert_run()
        first = self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_index=1,
            section_type="court_result",
            legal_weight="authoritative_result",
            is_final_result=True,
            chunk_kind="decision",
            chunk_text="Første resultat.",
        )
        second = self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_index=2,
            section_type="court_result",
            legal_weight="authoritative_result",
            is_final_result=True,
            chunk_kind="decision",
            chunk_text="Andet resultat.",
        )
        self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_index=3,
            section_type="court_reasoning",
            legal_weight="authoritative_reasoning",
            chunk_text="Rettens aktuelle begrundelse.",
        )
        self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_index=4,
            section_type="prior_instance_reasoning",
            legal_weight="prior_instance",
            chunk_text="Tidligere instans.",
        )
        target = self._insert_document(
            document_id="skat-info:oid:200",
            source_oid="200",
            skm_number="SKM2022.129.OLR",
            content_sha256=SHA_B,
            title="Ældre landsretsdom",
        )
        self._insert_reference(
            source_document_id="skat-info:oid:100",
            source_chunk_id=first["chunk_id"],
            target_document_id=target["document_id"],
            cited="SKM2022.129.OLR",
            occurrence_index=0,
            canonical=SHA,
        )

        commands = [
            ["search", "--query", "fradrag", "--mode", "lexical", "--format", "json"],
            ["summary", "--identifier", "SKM2026.1.LSR", "--format", "json"],
            ["result", "--identifier", "SKM2026.1.LSR", "--format", "json"],
            ["reasoning", "--identifier", "SKM2026.1.LSR", "--format", "json"],
            ["references", "--identifier", "SKM2026.1.LSR", "--format", "json"],
        ]
        for argv in commands:
            code, out, err = self._run_cli(argv)
            self.assertEqual(0, code, err)
            self.assertNotIn("forbindelse", out)
            payload = json.loads(out)
            self.assertEqual("1.0", payload["schema_version"])
            self.assertIn("requested_mode", payload)
            self.assertIn("effective_mode", payload)
            self.assertIn("fallback_reason", payload)

        _, summary_out, _ = self._run_cli(
            ["summary", "--identifier", "SKM2026.1.LSR", "--format", "json"]
        )
        summary = json.loads(summary_out)
        self.assertEqual(full, summary["summary"])
        self.assertIn("æøå", summary["summary"])
        self.assertEqual("B", summary["resolved_route"])

        _, result_out, _ = self._run_cli(
            ["result", "--identifier", "SKM2026.1.LSR", "--format", "json"]
        )
        result = json.loads(result_out)
        self.assertEqual(
            [first["chunk_id"], second["chunk_id"]],
            [row["chunk_id"] for row in result["chunks"]],
        )
        self.assertEqual(
            [1, 2],
            [row["chunk_index"] for row in result["chunks"]],
        )
        self.assertIn("Første resultat.", result["combined_text"])
        self.assertIn("Andet resultat.", result["combined_text"])

        _, reasoning_out, _ = self._run_cli(
            ["reasoning", "--identifier", "SKM2026.1.LSR", "--format", "json"]
        )
        reasoning = json.loads(reasoning_out)
        self.assertTrue(reasoning["prior_instance_omitted"])
        self.assertEqual(1, reasoning["prior_instance_chunk_count"])
        self.assertEqual(
            {"authoritative_reasoning"},
            {row["legal_weight"] for row in reasoning["chunks"]},
        )
        self.assertNotIn("Tidligere instans", reasoning["combined_text"])

        _, refs_out, _ = self._run_cli(
            ["references", "--identifier", "SKM2026.1.LSR", "--format", "json"]
        )
        refs = json.loads(refs_out)
        self.assertGreaterEqual(refs["outgoing_count"], 1)
        self.assertEqual("SKM2022.129.OLR", refs["references"][0]["cited_identifier"])
        self.assertIn("occurrence_index", refs["references"][0])

    def test_cli_jsonl_one_json_value_per_line(self):
        self._insert_document()
        run_id = self._insert_run()
        self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_text="Fradrag for moms ved udlejning.",
        )
        code, out, err = self._run_cli(
            ["search", "--query", "fradrag", "--mode", "lexical", "--format", "jsonl"]
        )
        self.assertEqual(0, code, err)
        lines = [line for line in out.splitlines() if line.strip()]
        self.assertGreaterEqual(len(lines), 2)
        parsed = [json.loads(line) for line in lines]
        self.assertEqual("query_metadata", parsed[0]["record_type"])
        self.assertEqual("result", parsed[1]["record_type"])
        self.assertNotIn("results", parsed[0])

    def test_cli_json_has_no_logs_on_stdout(self):
        self._insert_document()
        code, out, err = self._run_cli(
            ["summary", "--identifier", "SKM2026.1.LSR", "--format", "json"]
        )
        self.assertEqual(0, code, err)
        self.assertTrue(out.lstrip().startswith("{"))
        json.loads(out)
        self.assertEqual(1, len([line for line in out.splitlines() if line.strip()]))
        self.assertNotIn("forbindelse", out)
        self.assertNotIn("ADVARSEL", out)

    def test_unknown_identifier_json_exit_3(self):
        code, out, err = self._run_cli(
            ["summary", "--identifier", "SKM2099.1.X", "--format", "json"]
        )
        self.assertEqual(3, code)
        self.assertEqual("", out.strip())
        payload = json.loads(err)
        self.assertEqual("identifier_not_found", payload["error"]["code"])
        self.assertEqual("SKM2099.1.X", payload["error"]["identifier"])
        self.assertEqual("Dokumentet blev ikke fundet", payload["error"]["message"])

    def test_invalid_arguments_json_exit_2(self):
        code, out, err = self._run_cli(["search", "--format", "json"])
        self.assertEqual(2, code)
        self.assertEqual("", out.strip())
        payload = json.loads(err)
        self.assertEqual("invalid_argument", payload["error"]["code"])

    def test_text_output_remains_backward_compatible(self):
        full = "Hele resuméet står her og må ikke afkortes."
        self._insert_document(summary=full)
        run_id = self._insert_run()
        self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_text="Fradrag for moms ved udlejning.",
        )
        code, out, err = self._run_cli(["summary", "--identifier", "SKM2026.1.LSR"])
        self.assertEqual(0, code, err)
        self.assertIn("forbindelse ", out)
        self.assertIn("***", out)
        self.assertIn("summary_tegn=", out)
        self.assertIn(full, out)
        search_code, search_out, search_err = self._run_cli(
            ["search", "--query", "fradrag", "--mode", "lexical"]
        )
        self.assertEqual(0, search_code, search_err)
        self.assertIn("intent=", search_out)
        self.assertIn("fradrag", search_out.lower())

    def test_ranking_tie_break_is_deterministic(self):
        from backend.db.skat_retrieval.search import lexical_search

        self._insert_document()
        other = self._insert_document(
            document_id="skat-info:oid:200",
            source_oid="200",
            skm_number="SKM2026.2.LSR",
            content_sha256=SHA_B,
            title="Anden sag om fradrag",
        )
        run_id = self._insert_run()
        self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_text="Tekst om fradrag.",
        )
        self._insert_chunk(
            other["document_id"],
            run_id,
            source_oid="200",
            skm_number="SKM2026.2.LSR",
            chunk_text="Tekst om fradrag.",
            source_url="https://info.skat.dk/data.aspx?oid=200",
        )
        first = [(hit.document_id, hit.chunk_id, hit.rank_score) for hit in lexical_search(self.conn, "fradrag")]
        second = [(hit.document_id, hit.chunk_id, hit.rank_score) for hit in lexical_search(self.conn, "fradrag")]
        self.assertEqual(first, second)
        self.assertEqual(first, sorted(first, key=lambda item: (-item[2], item[0], item[1])))


def _unit_vector(first: float, *, size: int = 1536, nan: bool = False, inf: bool = False) -> list[float]:
    values = [0.0] * size
    if size:
        values[0] = first
    if nan:
        values[1] = float("nan")
    if inf:
        values[1] = float("inf")
    return values


class _RecordingEmbedClient:
    def __init__(self, vector, prompt_tokens: int = 8) -> None:
        self.vector = vector
        self.prompt_tokens = prompt_tokens
        self.calls: list[dict] = []

    def embeddings_create(self, *, model, dimensions, input, encoding_format):
        from backend.db.skat_embed.client import EmbedResponse

        self.calls.append(
            {
                "model": model,
                "dimensions": dimensions,
                "input": input,
                "encoding_format": encoding_format,
            }
        )
        return EmbedResponse(
            embeddings=[list(self.vector)],
            model=model,
            prompt_tokens=self.prompt_tokens,
            total_tokens=self.prompt_tokens,
            request_id=None,
            http_status=200,
        )


class QueryEmbedUnitTests(unittest.TestCase):
    def test_on_demand_embedding_uses_official_contract(self):
        from backend.db.skat_embed.constants import DIMENSIONS, ENCODING_FORMAT, MODEL_NAME
        from backend.db.skat_retrieval.query_embed import embed_query_on_demand

        client = _RecordingEmbedClient(_unit_vector(0.25), prompt_tokens=8)
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-not-for-stdout"}):
            resolved = embed_query_on_demand("beskatning", client=client)
        self.assertEqual(1, len(client.calls))
        call = client.calls[0]
        self.assertEqual(MODEL_NAME, call["model"])
        self.assertEqual(DIMENSIONS, call["dimensions"])
        self.assertEqual(ENCODING_FORMAT, call["encoding_format"])
        self.assertEqual(["Forespørgsel:\nbeskatning"], call["input"])
        usage = resolved.usage_payload()
        self.assertEqual("on_demand", usage["source"])
        self.assertEqual(8, usage["input_tokens"])
        self.assertEqual(1536, usage["dimensions"])

    def test_wrong_dimension_is_rejected(self):
        from backend.db.skat_retrieval.errors import QueryEmbeddingUnavailableError
        from backend.db.skat_retrieval.query_embed import embed_query_on_demand

        client = _RecordingEmbedClient(_unit_vector(0.2, size=8))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-not-for-stdout"}):
            with self.assertRaises(QueryEmbeddingUnavailableError) as raised:
                embed_query_on_demand("beskatning", client=client)
        self.assertEqual("invalid_query_embedding", raised.exception.reason)

    def test_nan_inf_and_zero_vector_are_rejected(self):
        from backend.db.skat_retrieval.errors import QueryEmbeddingUnavailableError
        from backend.db.skat_retrieval.query_embed import embed_query_on_demand

        cases = [
            _unit_vector(0.2, nan=True),
            _unit_vector(0.2, inf=True),
            _unit_vector(0.0),
        ]
        for vector in cases:
            client = _RecordingEmbedClient(vector)
            with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-not-for-stdout"}):
                with self.assertRaises(QueryEmbeddingUnavailableError) as raised:
                    embed_query_on_demand("beskatning", client=client)
            self.assertEqual("invalid_query_embedding", raised.exception.reason)


class QueryEmbedRetrievalTests(unittest.TestCase):
    """On-demand embedding, exact-plan og hybrid uden at gentage fixture-tests."""

    @classmethod
    def setUpClass(cls) -> None:
        SkatRetrievalTests.setUpClass()
        cls.conn = SkatRetrievalTests.conn
        cls.dsn = SkatRetrievalTests.dsn
        cls.psycopg = SkatRetrievalTests.psycopg

    @classmethod
    def tearDownClass(cls) -> None:
        return

    setUp = SkatRetrievalTests.setUp
    _insert_document = SkatRetrievalTests._insert_document
    _insert_run = SkatRetrievalTests._insert_run
    _insert_chunk = SkatRetrievalTests._insert_chunk
    _run_cli = SkatRetrievalTests._run_cli
    _insert_reference = SkatRetrievalTests._insert_reference
    _pgvector = SkatRetrievalTests._pgvector
    _insert_query_embedding = SkatRetrievalTests._insert_query_embedding
    _insert_embedding_model = SkatRetrievalTests._insert_embedding_model
    def test_valid_on_demand_embedding_is_not_written(self):
        from backend.db.skat_retrieval.engine import retrieve

        self._insert_document()
        run_id = self._insert_run()
        chunk = self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_text="Beskatning af udenlandsk indkomst.",
        )
        model_id = self._insert_embedding_model()
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO skat.chunk_embeddings (
                    chunk_id, embedding_model_id, embedding, embedding_text_sha256
                ) VALUES (%s, %s, %s::vector, %s)
                """,
                (chunk["chunk_id"], model_id, self._pgvector(0.4), SHA),
            )
            cur.execute("SELECT count(*) FROM skat.query_embeddings")
            before = cur.fetchone()[0]
        client = _RecordingEmbedClient(_unit_vector(0.4))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-not-for-stdout"}):
            response = retrieve(
                self.conn,
                "beskatning af udenlandsk indkomst",
                mode="hybrid",
                embed_client=client,
            )
        self.assertEqual("hybrid", response.effective_mode)
        self.assertIsNone(response.fallback_reason)
        self.assertEqual("on_demand", response.embedding_usage["source"])
        self.assertTrue(client.calls)
        with self.conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM skat.query_embeddings")
            after = cur.fetchone()[0]
        self.assertEqual(before, after)

    def test_lexical_never_calls_embedding_api(self):
        from backend.db.skat_retrieval.engine import retrieve

        self._insert_document()
        run_id = self._insert_run()
        self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_text="Fradrag for moms ved udlejning.",
        )
        client = _RecordingEmbedClient(_unit_vector(0.3))
        with patch(
            "backend.db.skat_retrieval.query_embed.embed_query_on_demand",
            side_effect=AssertionError("lexical må aldrig kalde embedding-API"),
        ):
            response = retrieve(
                self.conn,
                "fradrag for moms",
                mode="lexical",
                embed_client=client,
            )
        self.assertEqual("lexical", response.effective_mode)
        self.assertIsNone(response.embedding_usage)
        self.assertFalse(client.calls)

    def test_auto_falls_back_without_api_key(self):
        from backend.db.skat_retrieval.engine import retrieve

        self._insert_document()
        run_id = self._insert_run()
        self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_text="Fradrag for moms ved udlejning.",
        )
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            response = retrieve(self.conn, "fradrag for moms", mode="auto")
        self.assertEqual("auto", response.requested_mode)
        self.assertEqual("lexical", response.effective_mode)
        self.assertEqual("missing_openai_api_key", response.fallback_reason)

    def test_vector_and_exact_exit_4_without_embedding(self):
        self._insert_document()
        run_id = self._insert_run()
        self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_text="Fradrag for moms ved udlejning.",
        )
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            for argv in (
                ["search", "--query", "fradrag for moms", "--mode", "vector", "--format", "json"],
                ["search", "--query", "fradrag for moms", "--mode", "exact", "--format", "json"],
                [
                    "search",
                    "--query",
                    "fradrag for moms",
                    "--mode",
                    "hybrid",
                    "--exact-vector",
                    "--format",
                    "json",
                ],
            ):
                code, out, err = self._run_cli(argv)
                self.assertEqual(4, code, err)
                self.assertEqual("", out.strip())
                payload = json.loads(err)
                self.assertEqual("query_embedding_unavailable", payload["error"]["code"])
                combined = out + err
                self.assertNotIn("sk-", combined)
                self.assertNotIn("[0.", combined)

    def test_api_key_and_query_vector_stay_off_stdout_stderr(self):
        from backend.db.skat_retrieval.engine import retrieve
        from backend.db.skat_retrieval.output import dumps, search_payload

        self._insert_document()
        run_id = self._insert_run()
        chunk = self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_text="Beskatning af udenlandsk indkomst.",
        )
        model_id = self._insert_embedding_model()
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO skat.chunk_embeddings (
                    chunk_id, embedding_model_id, embedding, embedding_text_sha256
                ) VALUES (%s, %s, %s::vector, %s)
                """,
                (chunk["chunk_id"], model_id, self._pgvector(0.7), SHA),
            )
        secret = "sk-test-secret-key-SHOULD-NOT-LEAK"
        client = _RecordingEmbedClient(_unit_vector(0.7))
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch.dict(os.environ, {"OPENAI_API_KEY": secret}):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                response = retrieve(
                    self.conn,
                    "beskatning af udenlandsk indkomst",
                    mode="vector",
                    embed_client=client,
                )
                payload = search_payload(
                    response,
                    query="beskatning af udenlandsk indkomst",
                    limit=10,
                    filters={},
                    elapsed_ms=1.0,
                    include_references=False,
                )
                print(dumps(payload))
        combined = stdout.getvalue() + stderr.getvalue()
        self.assertNotIn(secret, combined)
        self.assertNotIn("[0.7,0.0,", combined)
        self.assertIn("timings_ms", combined)
        self.assertIn("embedding_usage", combined)

    def test_exact_candidate_plan_does_not_use_hnsw(self):
        from backend.db.skat_retrieval.vector import EXACT_CANDIDATE_SQL, _model_id

        self._insert_document()
        run_id = self._insert_run()
        chunk = self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_text="Fri bil til hovedaktionær.",
        )
        model_id = self._insert_embedding_model()
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO skat.chunk_embeddings (
                    chunk_id, embedding_model_id, embedding, embedding_text_sha256
                ) VALUES (%s, %s, %s::vector, %s)
                """,
                (chunk["chunk_id"], model_id, self._pgvector(0.9), SHA),
            )
        qvec = self._pgvector(1.0)
        with self.conn.cursor() as cur:
            cur.execute("BEGIN")
            cur.execute("SET LOCAL enable_indexscan = off")
            cur.execute("SET LOCAL enable_bitmapscan = off")
            cur.execute("SET LOCAL enable_seqscan = on")
            cur.execute(
                "EXPLAIN (ANALYZE, BUFFERS, SETTINGS, FORMAT TEXT) " + EXACT_CANDIDATE_SQL,
                (qvec, _model_id(self.conn), qvec, 200),
            )
            plan = "\n".join(row[0] for row in cur.fetchall())
            cur.execute("ROLLBACK")
        redacted = re.sub(r"\[[-\d.eE+,]+\]", "[vector]", plan)
        self.assertNotIn("hnsw", redacted.lower())
        self.assertNotIn("chunk_embeddings_hnsw", redacted.lower())
        self.assertTrue("Seq Scan" in redacted or "Parallel Seq Scan" in redacted)
        self.assertNotIn("HNSW", plan)

    def test_hydration_after_exact_restores_indexscan(self):
        from backend.db.skat_retrieval.search import HYDRATE_SQL
        from backend.db.skat_retrieval.vector import EXACT_RESTORE_SETTINGS, _run_exact_candidates

        self._insert_document()
        run_id = self._insert_run()
        chunk = self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_text="Fri bil til hovedaktionær.",
        )
        model_id = self._insert_embedding_model()
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO skat.chunk_embeddings (
                    chunk_id, embedding_model_id, embedding, embedding_text_sha256
                ) VALUES (%s, %s, %s::vector, %s)
                """,
                (chunk["chunk_id"], model_id, self._pgvector(0.9), SHA),
            )
        qvec = self._pgvector(1.0)
        rows = _run_exact_candidates(self.conn, qvec, model_id, 200)
        self.assertTrue(rows)
        with self.conn.cursor() as cur:
            cur.execute("SHOW enable_indexscan")
            self.assertEqual("on", cur.fetchone()[0])
            cur.execute("EXPLAIN (FORMAT TEXT) " + HYDRATE_SQL, ([chunk["chunk_id"]],))
            plan = "\n".join(row[0] for row in cur.fetchall())
        self.assertTrue(
            any(token in plan for token in ("Index Scan", "Index Only Scan", "Bitmap Heap Scan", "Seq Scan"))
        )
        src = Path(
            Path(__file__).resolve().parents[1]
            / "backend"
            / "db"
            / "skat_retrieval"
            / "vector.py"
        ).read_text(encoding="utf-8")
        for statement in EXACT_RESTORE_SETTINGS:
            self.assertIn(statement, src)
        self.assertIn("chunk_id = ANY(%s)", HYDRATE_SQL)

    def test_exact_top10_matches_full_inner_product_order(self):
        from backend.db.skat_retrieval.vector import vector_search

        run_id = self._insert_run()
        model_id = self._insert_embedding_model()
        expected = []
        for index in range(12):
            document_id = f"skat-info:oid:{100 + index}"
            self._insert_document(
                document_id=document_id,
                source_oid=str(100 + index),
                skm_number=f"SKM2026.{index + 1}.LSR",
                content_sha256=SHA if index == 0 else SHA_B,
                title=f"Sag {index} om fri bil",
            )
            chunk = self._insert_chunk(
                document_id,
                run_id,
                source_oid=str(100 + index),
                skm_number=f"SKM2026.{index + 1}.LSR",
                chunk_text=f"Fri bil hovedaktionær {index}.",
                source_url=f"https://info.skat.dk/data.aspx?oid={100 + index}",
            )
            weight = 1.0 - (index * 0.05)
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO skat.chunk_embeddings (
                        chunk_id, embedding_model_id, embedding, embedding_text_sha256
                    ) VALUES (%s, %s, %s::vector, %s)
                    """,
                    (chunk["chunk_id"], model_id, self._pgvector(weight), SHA),
                )
            expected.append(document_id)
        self._insert_query_embedding("fri bil hovedaktionær", 1.0, model_id)
        hits = vector_search(self.conn, "fri bil hovedaktionær", limit=10, exact_vector=True)
        self.assertEqual(expected[:10], [hit.document_id for hit in hits])

    def test_hybrid_uses_hnsw_v2_and_ef_search_800(self):
        from backend.db.skat_retrieval import vector as vector_mod
        from backend.db.skat_retrieval.settings import HNSW_EF_SEARCH, HNSW_INDEX_NAME
        from backend.db.skat_retrieval.vector import hybrid_search

        self._insert_document()
        run_id = self._insert_run()
        chunk = self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_text="Find sager om momsfradrag.",
        )
        model_id = self._insert_embedding_model()
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO skat.chunk_embeddings (
                    chunk_id, embedding_model_id, embedding, embedding_text_sha256
                ) VALUES (%s, %s, %s::vector, %s)
                """,
                (chunk["chunk_id"], model_id, self._pgvector(0.5), SHA),
            )
        self._insert_query_embedding("Find sager om moms", 0.5, model_id)
        captured_sql: list[str] = []
        orig = vector_mod.execute_with_local_settings

        def spy(conn, settings, sql, params):
            captured_sql.append(sql)
            self.assertEqual((f"SET LOCAL hnsw.ef_search = {HNSW_EF_SEARCH}",), tuple(settings))
            return orig(conn, settings, sql, params)

        with patch.object(vector_mod, "execute_with_local_settings", spy):
            hits = hybrid_search(self.conn, "Find sager om moms", limit=5)
        self.assertTrue(hits)
        self.assertTrue(captured_sql)
        self.assertIn(vector_mod.HNSW_CANDIDATE_SQL.strip(), captured_sql[0].strip())
        self.assertIn(HNSW_INDEX_NAME, vector_mod.HNSW_CANDIDATE_SQL + "\n" + Path(vector_mod.__file__).read_text(encoding="utf-8"))

    def test_json_and_jsonl_include_timings_compatibly(self):
        self._insert_document()
        run_id = self._insert_run()
        self._insert_chunk(
            "skat-info:oid:100",
            run_id,
            chunk_text="Fradrag for moms ved udlejning.",
        )
        code, out, err = self._run_cli(
            ["search", "--query", "fradrag", "--mode", "lexical", "--format", "json"]
        )
        self.assertEqual(0, code, err)
        payload = json.loads(out)
        self.assertEqual("1.0", payload["schema_version"])
        self.assertEqual("lexical", payload["requested_mode"])
        self.assertEqual("lexical", payload["effective_mode"])
        self.assertIsNone(payload["fallback_reason"])
        self.assertIn("timings_ms", payload)
        self.assertIsNone(payload["embedding_usage"])
        self.assertIn("lexical", payload["timings_ms"])
        code, out, err = self._run_cli(
            ["search", "--query", "fradrag", "--mode", "lexical", "--format", "jsonl"]
        )
        self.assertEqual(0, code, err)
        lines = [json.loads(line) for line in out.splitlines() if line.strip()]
        self.assertEqual("query_metadata", lines[0]["record_type"])
        self.assertIn("timings_ms", lines[0])
        self.assertEqual("result", lines[1]["record_type"])
        self.assertNotIn("results", lines[0])


if __name__ == "__main__":
    unittest.main()
