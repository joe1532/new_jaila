import unittest

from backend.services.djv_opslag import (
    djv_edition,
    lookup_djv_address,
    lookup_djv_hits,
    split_practice,
)
from backend.tools.import_djv import bindings_from_heading, flatten_tree


class DjvImportTests(unittest.TestCase):
    def test_heading_binds_ll_section_and_stk(self):
        found = bindings_from_heading(
            "C.F.4.2.1 Ligningslovens § 33 A, stk. 1 — lempelse"
        )
        self.assertEqual(
            [{"law": "ligningsloven", "key": "33a", "stk": 1}],
            found,
        )

    def test_heading_binds_paragraph_without_stk(self):
        found = bindings_from_heading(
            "C.A.7.3.2 Personer, som kan fratrække rejseudgifter efter LL § 9 A"
        )
        self.assertEqual([{"law": "ligningsloven", "key": "9a"}], found)

    def test_heading_skips_paragraph_nummer(self):
        found = bindings_from_heading(
            "C.A.2.5.2.1.1 LL § 7, nr. 1 - Indsamlede gaver"
        )
        self.assertEqual([], found)

    def test_flatten_keeps_one_node_per_address(self):
        nodes = flatten_tree(
            {
                "Overskrift": "C.F.4 Personer",
                "Tekst": "rod",
                "children": [
                    {
                        "Overskrift": "C.F.4.2.1 LL § 33 A, stk. 1",
                        "Tekst": "krop",
                    },
                    {
                        "Overskrift": "C.F.4.2.1 gentaget",
                        "Tekst": "må ikke overskrive",
                    },
                ],
            }
        )
        addresses = [item["address"] for item in nodes]
        self.assertEqual(["C.F.4", "C.F.4.2.1"], addresses)
        leaf = nodes[1]
        self.assertEqual("krop", leaf["text"])
        self.assertEqual("33a", leaf["bindings"][0]["key"])
        self.assertEqual(1, leaf["bindings"][0]["stk"])
        self.assertEqual("2026-2", leaf["edition"])


class DjvOpslagTests(unittest.TestCase):
    def test_cf421_is_33a_stk1_and_splits_practice(self):
        node = lookup_djv_address("C.F.4.2.1")
        self.assertIsNotNone(node)
        assert node is not None
        self.assertEqual(
            [{"law": "ligningsloven", "key": "33a", "stk": 1}],
            node["bindings"],
        )
        self.assertEqual("2026-2", node["edition"])
        self.assertEqual("2026-2", djv_edition())
        body, practice = split_practice(node["text"])
        self.assertGreater(len(body), 8000)
        self.assertTrue(practice.startswith("# Oversigt over domme"))
        self.assertNotIn("\n# Oversigt over domme", body)

    def test_open_stk1_looks_up_cf421_not_cf423(self):
        hits = lookup_djv_hits(
            [
                {
                    "law": "ligningsloven",
                    "section": "§ 33 A",
                    "kind": "statute",
                    "label": "ligningsloven § 33 A",
                }
            ],
            [{"label": "Stk. 1.", "text": "ophold uden for riget"}],
        )
        addresses = [hit["lookup_address"] for hit in hits]
        kinds = {hit["file_id"] for hit in hits}
        self.assertIn("C.F.4.2.1", addresses)
        self.assertNotIn("C.F.4.2.3", addresses)
        self.assertIn("opslag:djv:C.F.4.2.1:body", kinds)
        body = next(hit for hit in hits if hit["file_id"].endswith(":body"))
        self.assertFalse(body["lookup_clip"])
        self.assertGreater(len(body["text"]), 8000)

    def test_open_stk3_looks_up_half_relief_node(self):
        hits = lookup_djv_hits(
            [
                {
                    "law": "ligningsloven",
                    "section": "33a",
                    "kind": "statute",
                    "label": "ligningsloven § 33 A",
                }
            ],
            [
                {"label": "Stk. 1.", "text": "ophold"},
                {"label": "Stk. 3.", "text": "dobbeltbeskatningsoverenskomst"},
            ],
        )
        addresses = set(hit["lookup_address"] for hit in hits)
        self.assertEqual({"C.F.4.2.1", "C.F.4.2.3"}, addresses)

    def test_9a_opens_ca_not_cf(self):
        hits = lookup_djv_hits(
            [
                {
                    "law": "ligningsloven",
                    "section": "§ 9 A",
                    "kind": "statute",
                    "label": "ligningsloven § 9 A",
                }
            ],
            [{"label": "Stk. 1.", "text": "rejse"}],
        )
        addresses = {hit["lookup_address"] for hit in hits}
        self.assertIn("C.A.7.3.2", addresses)
        self.assertIn("C.A.7.3.3", addresses)
        self.assertFalse(any(item.startswith("C.F.") for item in addresses))
        self.assertTrue(all(hit.get("lookup_edition") == "2026-2" for hit in hits))

    def test_15p_opens_ch(self):
        hits = lookup_djv_hits(
            [
                {
                    "law": "ligningsloven",
                    "section": "§ 15 P",
                    "kind": "statute",
                    "label": "ligningsloven § 15 P",
                }
            ],
            [{"label": "Stk. 1.", "text": "ejendom"}],
        )
        addresses = {hit["lookup_address"] for hit in hits}
        self.assertEqual({"C.H.3.4.1.1.1"}, addresses)


if __name__ == "__main__":
    unittest.main()
