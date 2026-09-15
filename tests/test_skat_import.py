"""Tests af SKAT-importer. Importerer ikke produktionskorpusset."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
MIGRATE = ROOT / "backend" / "db" / "migrate.py"

SOURCE_SHA = "e87faff39b20a238bcdf28707e9713a58c77f4d9a7824f5db752f81f225d0329"
CONFIG_SHA = "853d300cbb5017e5233419f0c60544509fd7030f2df387b508a96b9ebd2e07b9"
CONTENT_A = "a" * 64
CONTENT_B = "b" * 64
CONTENT_C = "c" * 64
CONTENT_D = "d" * 64


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


TEST_DB_NAME = "jaila_skat_test"


def _dsn() -> str:
    _load_env()
    return (os.getenv("JAILA_SKAT_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()


def _isolated_dsn(prod_dsn: str) -> str:
    """Testdatabase, så DROP SCHEMA ikke rører jaila_skat med 11.707 dokumenter."""
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


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict]) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        for record in records
    ]
    data = "".join(lines).encode("utf-8")
    path.write_bytes(data)
    return {
        "count": len(records),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }


def _document(
    oid: str,
    year: int,
    *,
    skm: str,
    summary: str,
    sha: str,
    manual: bool = False,
    publication_year=Ellipsis,
) -> dict:
    jsonl_year = year if publication_year is Ellipsis else publication_year
    return {
        "schema_version": "jaila.skat.document.v1",
        "corpus": "skat_info_skm",
        "document_id": f"skat-info:oid:{oid}",
        "source_oid": oid,
        "skm_number": skm,
        "title": f"Titel {oid}",
        "document_type": "Dom",
        "authority": "Byret",
        "responsible_agency": "Skattestyrelsen",
        "case_number": "1",
        "publication_date": f"{year}-01-15",
        "decision_date": f"{year - 1}-11-01",
        "publication_year": jsonl_year,
        "main_topic": "Skat",
        "subtopic": None,
        "subject_terms": ["test"],
        "summary": summary,
        "source_url": f"https://info.skat.dk/data.aspx?oid={oid}",
        "document_status": "active",
        "replaced_by": None,
        "has_body": True,
        "has_assets": False,
        "has_ocr": False,
        "manual_source_check": manual,
        "image_text_authority": "not_applicable",
        "content_sha256": sha,
        "canonical_text_sha256": {"summary": sha, "body": CONTENT_B, "references": CONTENT_C},
        "canonical_text_length": {"summary": len(summary), "body": 10, "references": 1},
    }


def _chunk(document: dict, index: int, *, chunk_id: str, section: str, weight: str, final: bool, text: str, nxt=None, prev=None) -> dict:
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {
        "schema_version": "jaila.skat.chunk.v1",
        "chunk_id": chunk_id,
        "document_id": document["document_id"],
        "source_oid": document["source_oid"],
        "skm_number": document["skm_number"],
        "chunker_version": "1.0.1",
        "chunk_config_sha256": CONFIG_SHA,
        "chunk_index": index,
        "publication_date": document["publication_date"],
        "decision_date": document["decision_date"],
        "publication_year": document["publication_year"],
        "document_type": document["document_type"],
        "authority": document["authority"],
        "case_number": document["case_number"],
        "subject_terms": document["subject_terms"],
        "source_url": document["source_url"],
        "section_type": section,
        "legal_weight": weight,
        "section_heading_original": None,
        "section_heading_normalized": None,
        "section_path_original": [],
        "section_path_normalized": [],
        "classification_method": "section_attribute",
        "question_number": None,
        "is_final_result": final,
        "chunk_kind": "text",
        "chunk_text": text,
        "decision_context": "",
        "embedding_text": text,
        "source_spans": [{"source": "body", "start": 0, "end": max(len(text), 1), "role": "primary"}],
        "contains_table": False,
        "contains_image": False,
        "contains_ocr": False,
        "previous_chunk_id": prev,
        "next_chunk_id": nxt,
        "manual_source_check": document["manual_source_check"],
        "token_count": 12,
        "text_sha256": sha,
        "embedding_text_sha256": sha,
    }


def _manifest(year: int, docs_meta: dict, chunks_meta: dict, refs_meta: dict, *, docs: int, chunks: int, refs: int) -> dict:
    return {
        "manifest_version": "1.0",
        "schema_version": "jaila.skat.chunk.v1",
        "chunker_version": "1.0.1",
        "chunk_config": {
            "schema_version": "jaila.skat.chunk.v1",
            "chunker_name": "skat-skm-structural",
            "chunker_version": "1.0.1",
            "target_tokens": 800,
            "hard_max_tokens": 1000,
            "overlap_tokens": 100,
            "tokenizer_model": "text-embedding-3-large",
        },
        "chunk_config_sha256": CONFIG_SHA,
        "tokenizer_encoding": "cl100k_base",
        "source_manifest_sha256": SOURCE_SHA,
        "year": year,
        "document_count": docs,
        "chunk_count": chunks,
        "reference_count": refs,
        "jsonl": {"documents": docs_meta, "chunks": chunks_meta, "references": refs_meta},
    }


def _build_corpus(root: Path) -> tuple[dict, dict]:
    old = _document("100", 2022, skm="SKM2022.1.LSR", summary="Ældre resumé.", sha=CONTENT_A)
    current = _document(
        "200",
        2026,
        skm="SKM2026.1.LSR",
        summary="Hele resuméet står her og må ikke afkortes.",
        sha=CONTENT_B,
    )
    manual = _document(
        "300",
        2026,
        skm="SKM2026.2.SR",
        summary="Manuelt tjekket resumé.",
        sha=CONTENT_C,
        manual=True,
    )
    c0 = "skat-skm-chunk:" + uuid4().hex
    c1 = "skat-skm-chunk:" + uuid4().hex
    c2 = "skat-skm-chunk:" + uuid4().hex
    chunks = [
        _chunk(current, 0, chunk_id=c0, section="summary", weight="editorial", final=False, text="kort resuméchunk", nxt=c1),
        _chunk(current, 1, chunk_id=c1, section="court_reasoning", weight="authoritative_reasoning", final=False, text="Begrundelse.", prev=c0, nxt=c2),
        _chunk(current, 2, chunk_id=c2, section="court_result", weight="authoritative_result", final=True, text="Stadfæstelse.", prev=c1),
    ]
    ref = {
        "source_document_id": current["document_id"],
        "source_chunk_id": c1,
        "reference_type": "skm",
        "cited_identifier": "SKM2022.1.LSR",
        "exact_reference_text": "SKM2022.1.LSR",
        "target_document_id": old["document_id"],
        "target_url": old["source_url"],
        "resolution_status": "resolved",
    }
    old_meta = _write_jsonl(root / "2022" / "documents" / "2022.jsonl", [old])
    empty_chunks_2022 = _write_jsonl(root / "2022" / "chunks" / "2022.jsonl", [])
    empty_refs_2022 = _write_jsonl(root / "2022" / "references" / "2022.jsonl", [])
    docs_meta = _write_jsonl(root / "2026" / "documents" / "2026.jsonl", [current, manual])
    chunks_meta = _write_jsonl(root / "2026" / "chunks" / "2026.jsonl", chunks)
    refs_meta = _write_jsonl(root / "2026" / "references" / "2026.jsonl", [ref])
    _write_json(
        root / "2022" / "manifest.json",
        _manifest(2022, old_meta, empty_chunks_2022, empty_refs_2022, docs=1, chunks=0, refs=0),
    )
    _write_json(
        root / "2026" / "manifest.json",
        _manifest(2026, docs_meta, chunks_meta, refs_meta, docs=2, chunks=3, refs=1),
    )
    for year in (2022, 2026):
        _write_json(
            root / str(year) / "validation_report.json",
            {"status": "pass", "error_count": 0},
        )
    _write_json(
        root / "corpus_status.json",
        {
            "status": "complete",
            "completed_years": [2026, 2022],
            "source_manifest_sha256": SOURCE_SHA,
            "chunk_config_sha256": CONFIG_SHA,
            "totals": {"document_count": 3, "chunk_count": 3, "reference_count": 1},
        },
    )
    from backend.db.skat_import.constants import CorpusExpectations, SmokeSpec, YearExpectations

    expected = CorpusExpectations(
        year_count=2,
        document_count=3,
        chunk_count=3,
        reference_count=1,
        source_manifest_sha256=SOURCE_SHA,
        chunk_config_sha256=CONFIG_SHA,
    )
    year_expected = YearExpectations(
        year=2026,
        document_count=2,
        chunk_count=3,
        reference_count=1,
        summary_chunk_count=1,
        authoritative_reasoning_count=1,
        authoritative_result_count=1,
        final_result_count=1,
        token_max=1000,
    )
    smoke = SmokeSpec(
        skm_number="SKM2026.1.LSR",
        summary_min_length=20,
        older_citation="SKM2022.1.LSR",
        manual_skm_number="SKM2026.2.SR",
    )
    return {
        "expected": expected,
        "year_expected": year_expected,
        "smoke": smoke,
        "current": current,
        "chunks": chunks,
        "ref": ref,
    }, {"old": old, "current": current, "manual": manual}


class CanonicalIdentityTests(unittest.TestCase):
    def test_identical_references_get_distinct_occurrence_identity(self):
        from backend.db.skat_import.io import (
            ReferenceOccurrenceAssigner,
            canonical_reference_sha256,
            occurrence_reference_key,
            reference_id,
        )

        record = {
            "source_document_id": "skat-info:oid:1",
            "source_chunk_id": None,
            "reference_type": "skm",
            "cited_identifier": "SKM2022.129.ØLR",
            "exact_reference_text": "SKM2022.129.ØLR",
            "target_document_id": "skat-info:oid:2",
            "target_url": "https://info.skat.dk/data.aspx?oid=2",
            "resolution_status": "resolved",
        }
        shuffled = {k: record[k] for k in reversed(list(record))}
        first = ReferenceOccurrenceAssigner()
        second = ReferenceOccurrenceAssigner()
        c0, i0, k0 = first.assign(record)
        c1, i1, k1 = first.assign(record)
        d0, j0, m0 = second.assign(shuffled)
        d1, j1, m1 = second.assign(shuffled)
        self.assertEqual(canonical_reference_sha256(record), c0)
        self.assertEqual(c0, c1)
        self.assertEqual((0, 1), (i0, i1))
        self.assertNotEqual(k0, k1)
        self.assertNotEqual(reference_id(k0), reference_id(k1))
        self.assertEqual(k0, occurrence_reference_key(c0, 0))
        self.assertEqual(k1, occurrence_reference_key(c1, 1))
        self.assertEqual((c0, i0, k0, reference_id(k0)), (d0, j0, m0, reference_id(m0)))
        self.assertEqual((c1, i1, k1, reference_id(k1)), (d1, j1, m1, reference_id(m1)))

    def test_document_row_marks_missing_publication_year_inferred(self):
        try:
            import psycopg  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("psycopg mangler")
        from backend.db.skat_import.mapping import document_row

        record = _document("1", 2001, skm="SKM2001.1.LSR", summary="x", sha=CONTENT_A, publication_year=None)
        row = document_row(record, publication_year=2001)
        self.assertEqual(2001, row[12])
        self.assertIsNone(row[13])
        self.assertTrue(row[14])
        self.assertIsNone(record["publication_year"])

    def test_document_row_keeps_jsonl_publication_year(self):
        try:
            import psycopg  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("psycopg mangler")
        from backend.db.skat_import.mapping import document_row

        record = _document("1", 2026, skm="SKM2026.1.LSR", summary="x", sha=CONTENT_A)
        row = document_row(record, publication_year=2026)
        self.assertEqual(2026, row[12])
        self.assertEqual(2026, row[13])
        self.assertFalse(row[14])

    def test_unresolved_out_of_corpus_keeps_original_target(self):
        try:
            import psycopg  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("psycopg mangler")
        from backend.db.skat_import.io import ReferenceOccurrenceAssigner
        from backend.db.skat_import.mapping import reference_row

        record = {
            "source_document_id": "skat-info:oid:1",
            "source_chunk_id": None,
            "reference_type": "skm",
            "cited_identifier": "SKM1999.1.LSR",
            "exact_reference_text": "SKM1999.1.LSR",
            "target_document_id": "skat-info:oid:out",
            "target_url": None,
            "resolution_status": "unresolved",
        }
        canonical, index, key = ReferenceOccurrenceAssigner().assign(record)
        row = reference_row(
            record,
            canonical_sha=canonical,
            occurrence_index=index,
            reference_key=key,
            known_document_ids={"skat-info:oid:1"},
        )
        self.assertIsNone(row[7])
        self.assertEqual("unresolved", row[9])
        self.assertEqual("skat-info:oid:out", row[12])

    def test_resolved_missing_target_is_rejected(self):
        from backend.db.skat_import.errors import MissingResolvedTargetError
        from backend.db.skat_import.io import ReferenceOccurrenceAssigner
        from backend.db.skat_import.mapping import reference_row

        record = {
            "source_document_id": "skat-info:oid:1",
            "source_chunk_id": None,
            "reference_type": "skm",
            "cited_identifier": "SKM2022.1.LSR",
            "exact_reference_text": "SKM2022.1.LSR",
            "target_document_id": "skat-info:oid:missing",
            "target_url": "https://info.skat.dk/data.aspx?oid=missing",
            "resolution_status": "resolved",
        }
        canonical, index, key = ReferenceOccurrenceAssigner().assign(record)
        with self.assertRaises(MissingResolvedTargetError):
            reference_row(
                record,
                canonical_sha=canonical,
                occurrence_index=index,
                reference_key=key,
                known_document_ids={"skat-info:oid:1"},
            )

    def test_preflight_rejects_bad_status(self):
        from backend.db.skat_import.constants import CorpusExpectations
        from backend.db.skat_import.errors import PreflightError
        from backend.db.skat_import.preflight import run_preflight

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta, _docs = _build_corpus(root)
            status = json.loads((root / "corpus_status.json").read_text(encoding="utf-8"))
            status["status"] = "incomplete"
            _write_json(root / "corpus_status.json", status)
            with self.assertRaises(PreflightError):
                run_preflight(root, meta["expected"])

    def test_preflight_accepts_mini_corpus(self):
        from backend.db.skat_import.preflight import run_preflight

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta, _docs = _build_corpus(root)
            result = run_preflight(root, meta["expected"])
            self.assertEqual([2022, 2026], result.years)

    def test_descending_years_skips_approved_pilot(self):
        from backend.db.skat_import.year_expect import APPROVED_PILOT_YEAR, descending_years

        years = descending_years(2025, 2001, skip={APPROVED_PILOT_YEAR})
        self.assertEqual(2025, years[0])
        self.assertEqual(2001, years[-1])
        self.assertEqual(25, len(years))
        self.assertNotIn(2026, years)
        self.assertEqual(
            [2026, 2025, 2024],
            descending_years(2026, 2024, skip=None),
        )
        self.assertEqual([2025, 2024], descending_years(2026, 2024, skip={2026}))


class SkatImportIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        dsn = _dsn()
        if not dsn:
            raise unittest.SkipTest("Sæt JAILA_SKAT_DATABASE_URL")
        try:
            import psycopg  # noqa: F401
        except ImportError as exc:
            raise unittest.SkipTest("psycopg mangler") from exc
        try:
            test_dsn = _isolated_dsn(dsn)
        except Exception as exc:
            raise unittest.SkipTest(f"kunne ikke oprette testdatabase: {exc}") from exc
        cls.dsn = test_dsn
        os.environ["JAILA_SKAT_DATABASE_URL"] = test_dsn
        env = os.environ.copy()
        env["JAILA_SKAT_DATABASE_URL"] = test_dsn
        import psycopg

        cls.psycopg = psycopg
        cls.conn = psycopg.connect(test_dsn)
        cls.conn.autocommit = True
        with cls.conn.cursor() as cur:
            cur.execute("DROP SCHEMA IF EXISTS skat CASCADE")
        subprocess.check_call([sys.executable, str(MIGRATE)], cwd=str(ROOT), env=env)

    @classmethod
    def tearDownClass(cls) -> None:
        if getattr(cls, "conn", None) is not None:
            cls.conn.close()

    def setUp(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                TRUNCATE skat.legal_documents, skat.chunk_runs, skat.embedding_models,
                         skat.import_runs
                RESTART IDENTITY CASCADE
                """
            )

    def _conns(self):
        from backend.db.skat_import.connect import connect

        work = connect(self.dsn, autocommit=False)
        audit = connect(self.dsn, autocommit=True)
        return work, audit

    def test_document_import_is_idempotent_and_detects_hash_conflict(self):
        from backend.db.skat_import.documents import import_documents

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta, docs = _build_corpus(root)
            work, audit = self._conns()
            try:
                from backend.db.skat_import.preflight import run_preflight

                preflight = run_preflight(root, meta["expected"])
                first = import_documents(
                    root, work, audit, expected=meta["expected"], batch_size=10, preflight=preflight
                )
                second = import_documents(
                    root, work, audit, expected=meta["expected"], batch_size=10, preflight=preflight
                )
            finally:
                work.close()
                audit.close()
            self.assertEqual(3, first.inserted)
            self.assertEqual(0, first.skipped)
            self.assertEqual(0, second.inserted)
            self.assertEqual(3, second.skipped)

            changed = docs["current"].copy()
            changed["content_sha256"] = CONTENT_D
            path = root / "2026" / "documents" / "2026.jsonl"
            _write_jsonl(path, [changed, docs["manual"]])
            from backend.db.skat_import.errors import HashIntegrityError

            work, audit = self._conns()
            try:
                with self.assertRaises(HashIntegrityError):
                    import_documents(
                        root,
                        work,
                        audit,
                        expected=meta["expected"],
                        batch_size=10,
                        preflight=preflight,
                    )
            finally:
                work.close()
                audit.close()

    def test_year_import_verify_and_rollback(self):
        from backend.db.skat_import.documents import import_documents
        from backend.db.skat_import.errors import HashIntegrityError
        from backend.db.skat_import.verify import verify_year
        from backend.db.skat_import.year import import_year

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta, _docs = _build_corpus(root)
            work, audit = self._conns()
            try:
                import_documents(root, work, audit, expected=meta["expected"], batch_size=10)
                import_year(
                    root,
                    2026,
                    work,
                    audit,
                    expectations=meta["year_expected"],
                    batch_size=2,
                )
            finally:
                work.close()
                audit.close()

            result = verify_year(
                root,
                2026,
                self.conn,
                corpus=meta["expected"],
                year_expected=meta["year_expected"],
                smoke=meta["smoke"],
            )
            self.assertTrue(result.ok)

            work, audit = self._conns()
            try:
                again = import_year(
                    root,
                    2026,
                    work,
                    audit,
                    expectations=meta["year_expected"],
                    batch_size=2,
                )
            finally:
                work.close()
                audit.close()
            self.assertEqual(0, again.chunks_inserted)
            self.assertEqual(3, again.chunks_skipped)

            bad_root = Path(tmp) / "bad"
            meta_bad, _ = _build_corpus(bad_root)
            chunks_path = bad_root / "2026" / "chunks" / "2026.jsonl"
            records = [
                json.loads(line)
                for line in chunks_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            records[0]["token_count"] = 1001
            meta_chunks = _write_jsonl(chunks_path, records)
            manifest = json.loads((bad_root / "2026" / "manifest.json").read_text(encoding="utf-8"))
            manifest["jsonl"]["chunks"] = meta_chunks
            _write_json(bad_root / "2026" / "manifest.json", manifest)

            with self.conn.cursor() as cur:
                cur.execute("DELETE FROM skat.chunks")
                cur.execute("DELETE FROM skat.document_references")
                cur.execute("DELETE FROM skat.ingest_year_manifests")

            work, audit = self._conns()
            try:
                with self.assertRaises((HashIntegrityError, self.psycopg.errors.CheckViolation)):
                    import_year(
                        bad_root,
                        2026,
                        work,
                        audit,
                        expectations=meta_bad["year_expected"],
                        batch_size=10,
                    )
            finally:
                work.close()
                audit.close()
            with self.conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM skat.chunks")
                self.assertEqual(0, cur.fetchone()[0])

    def test_dry_run_does_not_write(self):
        from backend.db.skat_import.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta, _docs = _build_corpus(root)
            with self.conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM skat.import_runs")
                before = cur.fetchone()[0]
            # Mini-korpus matcher ikke produktionsforventninger; dry-run skal fejle preflight.
            code = main(["dry-run", "--input-root", str(root), "--year", "2026"])
            self.assertEqual(2, code)
            with self.conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM skat.import_runs")
                self.assertEqual(before, cur.fetchone()[0])
            from backend.db.skat_import.preflight import run_preflight

            run_preflight(root, meta["expected"])

    def test_identical_reference_lines_become_two_rows(self):
        from backend.db.skat_import.documents import import_documents
        from backend.db.skat_import.io import ReferenceOccurrenceAssigner
        from backend.db.skat_import.year import import_year

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta, _docs = _build_corpus(root)
            ref = meta["ref"]
            refs_meta = _write_jsonl(root / "2026" / "references" / "2026.jsonl", [ref, ref])
            manifest = json.loads((root / "2026" / "manifest.json").read_text(encoding="utf-8"))
            manifest["reference_count"] = 2
            manifest["jsonl"]["references"] = refs_meta
            _write_json(root / "2026" / "manifest.json", manifest)
            status = json.loads((root / "corpus_status.json").read_text(encoding="utf-8"))
            status["totals"]["reference_count"] = 2
            _write_json(root / "corpus_status.json", status)
            expected = replace(meta["expected"], reference_count=2)
            year_expected = replace(meta["year_expected"], reference_count=2)

            work, audit = self._conns()
            try:
                import_documents(root, work, audit, expected=expected, batch_size=10)
                first = import_year(
                    root, 2026, work, audit, expectations=year_expected, batch_size=1
                )
                second = import_year(
                    root, 2026, work, audit, expectations=year_expected, batch_size=1
                )
            finally:
                work.close()
                audit.close()

            self.assertEqual(2, first.references_inserted)
            self.assertEqual(0, first.references_skipped)
            self.assertEqual(0, second.references_inserted)
            self.assertEqual(2, second.references_skipped)

            assigner = ReferenceOccurrenceAssigner()
            expected_rows = [assigner.assign(ref) for _ in range(2)]
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT canonical_reference_sha256, occurrence_index,
                           reference_key, reference_id::text
                    FROM skat.document_references
                    ORDER BY occurrence_index
                    """
                )
                rows = cur.fetchall()
            self.assertEqual(2, len(rows))
            self.assertEqual(expected_rows[0][0], rows[0][0])
            self.assertEqual(expected_rows[1][0], rows[1][0])
            self.assertEqual(expected_rows[0][0], expected_rows[1][0])
            self.assertEqual((0, 1), (rows[0][1], rows[1][1]))
            self.assertEqual(expected_rows[0][2], rows[0][2])
            self.assertEqual(expected_rows[1][2], rows[1][2])
            self.assertNotEqual(rows[0][2], rows[1][2])
            self.assertNotEqual(rows[0][3], rows[1][3])

    def test_publication_year_provenance_and_out_of_corpus_target(self):
        from backend.db.skat_import.documents import import_documents
        from backend.db.skat_import.year import import_year

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta, docs = _build_corpus(root)
            inferred = docs["old"].copy()
            inferred["publication_year"] = None
            old_meta = _write_jsonl(root / "2022" / "documents" / "2022.jsonl", [inferred])
            manifest_2022 = json.loads((root / "2022" / "manifest.json").read_text(encoding="utf-8"))
            manifest_2022["jsonl"]["documents"] = old_meta
            _write_json(root / "2022" / "manifest.json", manifest_2022)

            extra_ref = {
                "source_document_id": meta["current"]["document_id"],
                "source_chunk_id": meta["chunks"][1]["chunk_id"],
                "reference_type": "skm",
                "cited_identifier": "SKM1999.1.LSR",
                "exact_reference_text": "SKM1999.1.LSR",
                "target_document_id": "skat-info:oid:outside-corpus",
                "target_url": None,
                "resolution_status": "unresolved",
            }
            refs_meta = _write_jsonl(
                root / "2026" / "references" / "2026.jsonl",
                [meta["ref"], extra_ref],
            )
            manifest = json.loads((root / "2026" / "manifest.json").read_text(encoding="utf-8"))
            manifest["reference_count"] = 2
            manifest["jsonl"]["references"] = refs_meta
            _write_json(root / "2026" / "manifest.json", manifest)
            status = json.loads((root / "corpus_status.json").read_text(encoding="utf-8"))
            status["totals"]["reference_count"] = 2
            _write_json(root / "corpus_status.json", status)
            expected = replace(meta["expected"], reference_count=2)
            year_expected = replace(meta["year_expected"], reference_count=2)

            work, audit = self._conns()
            try:
                import_documents(root, work, audit, expected=expected, batch_size=10)
                import_year(root, 2026, work, audit, expectations=year_expected, batch_size=10)
            finally:
                work.close()
                audit.close()

            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT publication_year, publication_year_original,
                           publication_year_inferred, raw_record -> 'publication_year'
                    FROM skat.legal_documents
                    WHERE document_id = %s
                    """,
                    (inferred["document_id"],),
                )
                year, original, flag, raw_year = cur.fetchone()
                self.assertEqual(2022, year)
                self.assertIsNone(original)
                self.assertTrue(flag)
                self.assertIsNone(raw_year)

                cur.execute(
                    """
                    SELECT publication_year, publication_year_original, publication_year_inferred
                    FROM skat.legal_documents
                    WHERE document_id = %s
                    """,
                    (meta["current"]["document_id"],),
                )
                year, original, flag = cur.fetchone()
                self.assertEqual(2026, year)
                self.assertEqual(2026, original)
                self.assertFalse(flag)

                cur.execute(
                    """
                    SELECT target_document_id, original_target_document_id, resolution_status,
                           raw_record ->> 'target_document_id'
                    FROM skat.document_references
                    WHERE cited_identifier = 'SKM1999.1.LSR'
                    """
                )
                target, original_target, status_value, raw_target = cur.fetchone()
            self.assertIsNone(target)
            self.assertEqual("skat-info:oid:outside-corpus", original_target)
            self.assertEqual("unresolved", status_value)
            self.assertEqual("skat-info:oid:outside-corpus", raw_target)

    def test_resolved_reference_without_existing_target_is_rejected(self):
        from backend.db.skat_import.documents import import_documents
        from backend.db.skat_import.errors import MissingResolvedTargetError
        from backend.db.skat_import.year import import_year

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta, _docs = _build_corpus(root)
            broken = dict(meta["ref"])
            broken["target_document_id"] = "skat-info:oid:does-not-exist"
            refs_meta = _write_jsonl(root / "2026" / "references" / "2026.jsonl", [broken])
            manifest = json.loads((root / "2026" / "manifest.json").read_text(encoding="utf-8"))
            manifest["jsonl"]["references"] = refs_meta
            _write_json(root / "2026" / "manifest.json", manifest)

            work, audit = self._conns()
            try:
                import_documents(root, work, audit, expected=meta["expected"], batch_size=10)
                with self.assertRaises(MissingResolvedTargetError):
                    import_year(
                        root,
                        2026,
                        work,
                        audit,
                        expectations=meta["year_expected"],
                        batch_size=10,
                    )
            finally:
                work.close()
                audit.close()

            with self.conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM skat.document_references")
                self.assertEqual(0, cur.fetchone()[0])
                cur.execute("SELECT count(*) FROM skat.chunks")
                self.assertEqual(0, cur.fetchone()[0])

    def test_import_corpus_is_resumable_on_test_database(self):
        from backend.db.skat_import.corpus import import_corpus
        from backend.db.skat_import.documents import import_documents

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta, _docs = _build_corpus(root)
            work, audit = self._conns()
            try:
                import_documents(root, work, audit, expected=meta["expected"], batch_size=10)
                first = import_corpus(
                    root,
                    2026,
                    2026,
                    work,
                    audit,
                    expected=meta["expected"],
                    batch_size=2,
                    skip_years=set(),
                    verify_each_year=True,
                )
                second = import_corpus(
                    root,
                    2022,
                    2022,
                    work,
                    audit,
                    expected=meta["expected"],
                    batch_size=2,
                    skip_years=set(),
                    verify_each_year=True,
                )
                again_2026 = import_corpus(
                    root,
                    2026,
                    2026,
                    work,
                    audit,
                    expected=meta["expected"],
                    batch_size=2,
                    skip_years=set(),
                    verify_each_year=True,
                )
                again_2022 = import_corpus(
                    root,
                    2022,
                    2022,
                    work,
                    audit,
                    expected=meta["expected"],
                    batch_size=2,
                    skip_years=set(),
                    verify_each_year=True,
                )
            finally:
                work.close()
                audit.close()

            self.assertEqual([2026], first.imported)
            self.assertEqual([2022], second.imported)
            self.assertEqual([], again_2026.imported)
            self.assertEqual([2026], again_2026.skipped)
            self.assertEqual([], again_2022.imported)
            self.assertEqual([2022], again_2022.skipped)
            self.assertEqual(0, again_2026.years[0].chunks_inserted)
            with self.conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM skat.chunks")
                self.assertEqual(3, cur.fetchone()[0])
                cur.execute(
                    """
                    SELECT publication_year, status
                    FROM skat.import_runs
                    WHERE phase = 'year' AND status = 'complete'
                    ORDER BY publication_year
                    """
                )
                complete = [(row[0], row[1]) for row in cur.fetchall()]
            self.assertIn((2022, "complete"), complete)
            self.assertIn((2026, "complete"), complete)


if __name__ == "__main__":
    unittest.main()
