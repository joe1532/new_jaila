"""Tests af den lokale SKAT-søge-API. Ingen rigtig database."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.services.skat_search import (
    collapse_hits_to_summaries,
    find_raw_html_file,
    inject_info_skat_base,
    load_original_html,
    run_skat_search,
    search_status,
    sections_to_html,
    skat_search_api_enabled,
)


class FakeConn:
    def __init__(self) -> None:
        self.rolled_back = False
        self.closed = False

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


class SkatSearchApiTests(unittest.TestCase):
    def test_flag_is_off_by_default(self) -> None:
        with patch.dict(os.environ, {"JAILA_SKAT_SEARCH_API": ""}, clear=False):
            os.environ.pop("JAILA_SKAT_SEARCH_API", None)
            self.assertFalse(skat_search_api_enabled())

    def test_status_does_not_echo_dsn(self) -> None:
        with patch.dict(
            os.environ,
            {
                "JAILA_SKAT_SEARCH_API": "true",
                "JAILA_SKAT_DATABASE_URL": "postgresql://secret@127.0.0.1/jaila_skat",
            },
        ):
            payload = search_status()
        self.assertEqual(True, payload["enabled"])
        self.assertEqual(True, payload["database_configured"])
        self.assertIn("raw_html_configured", payload)
        self.assertNotIn("secret", str(payload))

    def test_empty_query_rejected(self) -> None:
        with self.assertRaises(ValueError):
            run_skat_search("   ")

    def test_unknown_mode_rejected(self) -> None:
        with self.assertRaises(ValueError):
            run_skat_search("moms", mode="semantic")

    def test_run_search_uses_retrieve_and_closes(self) -> None:
        conn = FakeConn()
        response = SimpleNamespace(
            hits=[],
            document=None,
            summary=None,
            chunks=None,
            references=None,
            requested_mode="lexical",
            effective_mode="lexical",
            fallback_reason=None,
            resolved_route="F",
            exact_vector=False,
            timings_ms={"total": 12.0},
            embedding_usage=None,
            note="test",
            route=SimpleNamespace(intent="topical", identifier=None),
        )
        with (
            patch("backend.db.skat_retrieval.db.connect_readonly", return_value=conn),
            patch("backend.db.skat_retrieval.engine.retrieve", return_value=response) as retrieve,
        ):
            payload = run_skat_search("Find sager om moms", mode="lexical", limit=5)

        self.assertEqual("Find sager om moms", payload["query"])
        self.assertEqual("lexical", payload["requested_mode"])
        self.assertEqual(0, payload["result_count"])
        self.assertIn("elapsed_ms", payload)
        retrieve.assert_called_once()
        self.assertEqual("Find sager om moms", retrieve.call_args.args[1])
        self.assertEqual("lexical", retrieve.call_args.kwargs["mode"])
        self.assertFalse(retrieve.call_args.kwargs["honor_route_lookup"])
        self.assertTrue(conn.rolled_back)
        self.assertTrue(conn.closed)

    def test_http_disabled_is_404(self) -> None:
        from fastapi.testclient import TestClient
        from backend.main import app

        with patch("backend.main.skat_search_api_enabled", return_value=False):
            response = TestClient(app).post(
                "/api/skat/search",
                json={"query": "SKM2023.18.ØLR", "mode": "auto"},
            )
        self.assertEqual(404, response.status_code)

    def test_http_search_returns_payload(self) -> None:
        from fastapi.testclient import TestClient
        from backend.main import app

        fake = {
            "query": "SKM2023.18.ØLR",
            "requested_mode": "auto",
            "effective_mode": "lookup",
            "result_count": 0,
            "elapsed_ms": 8.1,
            "results": [],
        }
        with (
            patch("backend.main.skat_search_api_enabled", return_value=True),
            patch("backend.main.run_skat_search", return_value=fake),
        ):
            response = TestClient(app).post(
                "/api/skat/search",
                json={"query": "SKM2023.18.ØLR", "mode": "auto"},
            )
        self.assertEqual(200, response.status_code)
        self.assertEqual("lookup", response.json()["effective_mode"])
        self.assertEqual(8.1, response.json()["elapsed_ms"])

    def test_http_status_endpoint(self) -> None:
        from fastapi.testclient import TestClient
        from backend.main import app

        with patch(
            "backend.main.search_status",
            return_value={"enabled": True, "database_configured": False},
        ):
            response = TestClient(app).get("/api/skat/search/status")
        self.assertEqual(200, response.status_code)
        self.assertEqual(True, response.json()["enabled"])
        self.assertEqual(False, response.json()["database_configured"])
        self.assertIn("raw_html_configured", response.json())

    def test_collapse_hits_prefers_summary_text(self) -> None:
        rows = collapse_hits_to_summaries(
            [
                {
                    "rank": 1,
                    "document_id": "doc-1",
                    "section_type": "claimant_arguments",
                    "text": "Klagerens opfattelse",
                },
                {
                    "rank": 2,
                    "document_id": "doc-1",
                    "section_type": "summary",
                    "text": "Andet chunk samme sag",
                },
            ],
            {"doc-1": "Landsskatteretten fandt, det var berettiget."},
        )
        self.assertEqual(1, len(rows))
        self.assertEqual("Landsskatteretten fandt, det var berettiget.", rows[0]["text"])
        self.assertEqual("summary", rows[0]["section_type"])
        self.assertEqual("claimant_arguments", rows[0]["matched_section_type"])
        self.assertEqual("Klagerens opfattelse", rows[0]["matched_section_label"])

    def test_document_html_escapes_markup(self) -> None:
        markup = sections_to_html(
            [{"section_type": "summary", "heading": "Resumé", "text": "<script>x</script>\n\nAfsnit"}]
        )
        self.assertIn("&lt;script&gt;", markup)
        self.assertNotIn("<script>x</script>", markup)
        self.assertIn("<h2>Resumé</h2>", markup)

    def test_http_document_disabled_is_404(self) -> None:
        from fastapi.testclient import TestClient
        from backend.main import app

        with patch("backend.main.skat_search_api_enabled", return_value=False):
            response = TestClient(app).get("/api/skat/document", params={"identifier": "SKM2021.486.LSR"})
        self.assertEqual(404, response.status_code)

    def test_injects_info_skat_base(self) -> None:
        markup = inject_info_skat_base("<html><head><title>x</title></head></html>")
        self.assertIn('<base href="https://info.skat.dk/">', markup)

    def test_finds_raw_html_by_oid_and_skm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "2021" / "raw_html"
            folder.mkdir(parents=True)
            path = folder / "SKM2021.486.LSR__oid-2338766.html"
            path.write_text("<html><head></head><body>original</body></html>", encoding="utf-8")
            found = find_raw_html_file(identifier="2338766", root=root)
            self.assertEqual(path.resolve(), found)
            found_skm = find_raw_html_file(identifier="SKM2021.486.LSR", root=root)
            self.assertEqual(path.resolve(), found_skm)

    def test_rejects_path_traversal_identifier(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "2021" / "raw_html").mkdir(parents=True)
            with self.assertRaises(ValueError):
                load_original_html("../secret", root=root)

    def test_http_original_html_returns_scraped_file(self) -> None:
        from fastapi.testclient import TestClient
        from backend.main import app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "2021" / "raw_html"
            folder.mkdir(parents=True)
            (folder / "SKM2021.486.LSR__oid-2338766.html").write_text(
                "<html><head><title>x</title></head><body>Landsskatteretten</body></html>",
                encoding="utf-8",
            )
            with (
                patch("backend.main.skat_search_api_enabled", return_value=True),
                patch("backend.services.skat_search.raw_html_root", return_value=root),
            ):
                response = TestClient(app).get(
                    "/api/skat/document/original",
                    params={"identifier": "SKM2021.486.LSR"},
                )
        self.assertEqual(200, response.status_code)
        self.assertIn("text/html", response.headers.get("content-type", ""))
        self.assertIn("Landsskatteretten", response.text)
        self.assertIn('<base href="https://info.skat.dk/">', response.text)

    def test_http_original_html_disabled_is_404(self) -> None:
        from fastapi.testclient import TestClient
        from backend.main import app

        with patch("backend.main.skat_search_api_enabled", return_value=False):
            response = TestClient(app).get(
                "/api/skat/document/original",
                params={"identifier": "SKM2021.486.LSR"},
            )
        self.assertEqual(404, response.status_code)


if __name__ == "__main__":
    unittest.main()
