import unittest
from types import SimpleNamespace

from backend.services.legal_search import search_legal_sources


def result(file_id: str, filename: str, score: float, text: str):
    return SimpleNamespace(
        file_id=file_id,
        filename=filename,
        score=score,
        attributes={"category": "test"},
        content=[SimpleNamespace(type="text", text=text)],
    )


class FakeSearch:
    def __init__(self, pages):
        self.pages = pages

    def __call__(self, vector_store_id, **_kwargs):
        value = self.pages[vector_store_id]
        if isinstance(value, Exception):
            raise value
        return value


class LegalSearchTests(unittest.TestCase):
    def test_merges_sorts_deduplicates_and_limits_results(self):
        pages = {
            "vs_a": [
                result("file_1", "lov.pdf", 0.8, "A"),
                result("file_2", "dom.pdf", 0.6, "B"),
            ],
            "vs_b": [
                result("file_3", "note.pdf", 0.9, "C"),
                result("file_1", "lov.pdf", 0.8, "A"),
            ],
        }
        client = SimpleNamespace(
            vector_stores=SimpleNamespace(search=FakeSearch(pages))
        )

        found = search_legal_sources(
            client=client,
            query="ligningslovens § 33 A",
            max_results=2,
            vector_store_ids=["vs_a", "vs_b"],
        )

        self.assertEqual(["file_3", "file_1"], [item["file_id"] for item in found])
        self.assertEqual({"category": "test"}, found[0]["attributes"])

    def test_returns_results_when_one_store_fails(self):
        pages = {
            "vs_a": RuntimeError("provider error"),
            "vs_b": [result("file_1", "lov.pdf", 0.7, "tekst")],
        }
        client = SimpleNamespace(
            vector_stores=SimpleNamespace(search=FakeSearch(pages))
        )

        found = search_legal_sources(
            client=client,
            query="skat",
            vector_store_ids=["vs_a", "vs_b"],
        )

        self.assertEqual(1, len(found))

    def test_rejects_invalid_input(self):
        client = SimpleNamespace()
        with self.assertRaises(ValueError):
            search_legal_sources(client=client, query="")
        with self.assertRaises(ValueError):
            search_legal_sources(client=client, query="skat", max_results=0)


if __name__ == "__main__":
    unittest.main()
