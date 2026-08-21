import unittest

from backend.services.openai_service import (
    attach_named_law_citations,
    _filename_is_named_statute,
)


class NamedLawCitationTests(unittest.TestCase):
    def test_statute_filename_matches_stem_at_start(self):
        stems = {"ligningslov"}
        self.assertTrue(
            _filename_is_named_statute(
                "Ligningsloven (2025-11-24 nr. 1500).pdf",
                stems,
            )
        )

    def test_circular_about_the_law_is_not_the_statute(self):
        stems = {"ligningslov"}
        self.assertFalse(
            _filename_is_named_statute(
                "Cirkulære 1996-04-17 nr. 72 om ligningsloven.pdf",
                stems,
            )
        )

    def test_attaches_retrieved_statute_the_answer_names(self):
        parsed = attach_named_law_citations(
            {
                "output_text": (
                    "Efter ligningslovens § 33, stk. 1, kan udenlandsk skat fradrages.\n\n"
                    "Anvendte kilder/love\n"
                    "Ligningsloven § 33\n"
                    "Den juridiske vejledning 2026-1, afsnit C.F"
                ),
                "citations": [
                    {
                        "file_id": "file-djv",
                        "filename": "DJV C.F Subjektiv skattepligt og dobbeltbeskatning (2026-1).pdf",
                    }
                ],
                "retrieved_sources": [
                    {
                        "file_id": "file-djv",
                        "filename": "DJV C.F Subjektiv skattepligt og dobbeltbeskatning (2026-1).pdf",
                    },
                    {
                        "file_id": "file-ll",
                        "filename": "Ligningsloven (2025-11-24 nr. 1500).pdf",
                    },
                    {
                        "file_id": "file-cirk",
                        "filename": "Cirkulære 1996-04-17 nr. 72 om ligningsloven.pdf",
                    },
                ],
            }
        )
        citations = parsed["citations"]
        self.assertEqual(citations[0]["file_id"], "file-ll")
        self.assertEqual(
            citations[0]["filename"],
            "Ligningsloven (2025-11-24 nr. 1500).pdf",
        )
        self.assertEqual(citations[1]["file_id"], "file-djv")
        self.assertEqual([item["file_id"] for item in citations], ["file-ll", "file-djv"])

    def test_does_not_duplicate_an_already_cited_statute(self):
        parsed = attach_named_law_citations(
            {
                "output_text": "Efter ligningslovens § 33.",
                "citations": [
                    {
                        "file_id": "file-ll",
                        "filename": "Ligningsloven (2025-11-24 nr. 1500).pdf",
                    }
                ],
                "retrieved_sources": [
                    {
                        "file_id": "file-ll",
                        "filename": "Ligningsloven (2025-11-24 nr. 1500).pdf",
                    }
                ],
            }
        )
        self.assertEqual(len(parsed["citations"]), 1)

    def test_leaves_citations_when_answer_does_not_name_a_law(self):
        parsed = attach_named_law_citations(
            {
                "output_text": "Dette fremgår ikke af de tilgængelige kilder.",
                "citations": [{"file_id": "file-djv", "filename": "DJV C.F.pdf"}],
                "retrieved_sources": [
                    {
                        "file_id": "file-ll",
                        "filename": "Ligningsloven (2025-11-24 nr. 1500).pdf",
                    }
                ],
            }
        )
        self.assertEqual(parsed["citations"], [{"file_id": "file-djv", "filename": "DJV C.F.pdf"}])


if __name__ == "__main__":
    unittest.main()
