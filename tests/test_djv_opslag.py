import unittest

from backend.services.djv_opslag import (
    djv_edition,
    lookup_djv_address,
    lookup_djv_hits,
    split_practice,
)
from backend.tools.import_djv import (
    bindings_from_heading,
    bindings_from_node,
    flatten_tree,
)


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

    def test_regel_binds_paragraph_from_markdown_not_stk(self):
        found = bindings_from_node(
            "C.A.7.1.4 Betingelse om midlertidigt arbejdssted",
            (
                "# Regel\n\n"
                "Hverken [LL § 9 A](https://example.invalid/P9A) eller "
                "forarbejderne definerer midlertidigt arbejdssted.\n\n"
                "### Bemærk\n\n"
                "Fri kost kan stilles til rådighed efter LL § 16, stk. 11.\n"
            ),
        )
        self.assertEqual([{"law": "ligningsloven", "key": "9a"}], found)

    def test_regel_does_not_bind_stk_from_body(self):
        found = bindings_from_node(
            "C.A.7.1.1 Hvad vil det sige at være på rejse",
            "# Regel\n\nEfter LL § 9 A, stk. 1, er lønmodtageren på rejse.\n",
        )
        self.assertEqual([{"law": "ligningsloven", "key": "9a"}], found)
        self.assertNotIn("stk", found[0])

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

    def test_example_does_not_bind_other_paragraph(self):
        found = bindings_from_node(
            "C.A.5.14.1.2 Personer omfattet af reglen",
            (
                "# Ansættelsesforhold mv.\n\n"
                "Reglerne gælder for ansatte. Se LL § 16, stk. 4.\n\n"
                "### Eksempel på en situation, der ikke var omfattet\n\n"
                "Der var ikke hjemmel efter LL § 9 C, stk. 1.\n"
            ),
        )
        self.assertEqual([{"law": "ligningsloven", "key": "16"}], found)

    def test_unbound_sibling_inherits_majority_paragraph(self):
        nodes = flatten_tree(
            {
                "Overskrift": "C.A.5.14.1 Firmabil",
                "Tekst": "# Indhold\n\nFirmabil.",
                "children": [
                    {
                        "Overskrift": "C.A.5.14.1.1 Regel",
                        "Tekst": "# Regel\n\nSe LL § 16, stk. 4.\n",
                    },
                    {
                        "Overskrift": "C.A.5.14.1.4 Rådighedsbeskatning",
                        "Tekst": "# Regel\n\nDet er rådigheden. Se LL § 16.\n",
                    },
                    {
                        "Overskrift": "C.A.5.14.1.11 Vurderingen af rådighed",
                        "Tekst": (
                            "# Regel\n\n"
                            "Der sker kun beskatning, hvis bilen er til "
                            "rådighed for privat brug.\n"
                        ),
                    },
                ],
            }
        )
        by_address = {item["address"]: item for item in nodes}
        self.assertEqual(
            [{"law": "ligningsloven", "key": "16"}],
            by_address["C.A.5.14.1.11"]["bindings"],
        )
        self.assertEqual([], by_address["C.A.5.14.1"]["bindings"])


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
            [
                {
                    "label": "Stk. 1.",
                    "text": (
                        "skattefri rejsegodtgørelse når lønmodtageren på grund "
                        "af afstanden mellem bopæl og midlertidigt arbejdssted "
                        "ikke kan overnatte på den sædvanlige bopæl"
                    ),
                }
            ],
            facts=(
                "Kan Mette få skattefri rejsegodtgørelse efter ligningslovens "
                "§ 9 A? Elektriker, Aalborg hospital, 185 km, 24 timer."
            ),
        )
        addresses = {hit["lookup_address"] for hit in hits}
        self.assertIn("C.A.7.1.4", addresses)
        self.assertLessEqual(len(addresses), 4)
        self.assertFalse(any(item.startswith("C.F.") for item in addresses))
        self.assertTrue(all(hit.get("lookup_edition") == "2026-2" for hit in hits))
        practice = next(
            hit
            for hit in hits
            if hit["lookup_address"] == "C.A.7.1.4" and hit["file_id"].endswith(":praksis")
        )
        self.assertIn("SKM2025.692.LSR", practice["text"])

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
        self.assertIn("C.H.3.4.1.1.1", addresses)
        self.assertTrue(all(item.startswith("C.H.") for item in addresses))
        self.assertLessEqual(len(addresses), 4)

    def test_firmabil_opens_ca514_not_telefon_or_befordring(self):
        from backend.services.djv_opslag import _is_toc_node, lookup_djv_address
        from backend.services.opslagsvaerk import lookup_hit_for_anchor
        from backend.services.task_search import _open_doors, extract_anchors

        parent = lookup_djv_address("C.A.5.14.1")
        regel = lookup_djv_address("C.A.5.14.1.1")
        raadighed = lookup_djv_address("C.A.5.14.1.4")
        self.assertIsNotNone(parent)
        self.assertIsNotNone(regel)
        self.assertIsNotNone(raadighed)
        facts = (
            "Henrik er direktør i Alfa A/S. Alfa A/S stiller en personbil til en "
            "værdi af 650.000 kr. til rådighed for Henrik. Ifølge hans "
            "ansættelseskontrakt må bilen anvendes både erhvervsmæssigt og privat. "
            "Bilen holder normalt ved Henriks bopæl om natten, og Henrik har selv "
            "bilens nøgler. Henrik ejer også privat en anden bil. Henrik oplyser, "
            "at han i hele 2026 ikke har kørt én eneste privat kilometer i "
            "firmabilen. Skal Henrik beskattes af fri bil?"
        )
        fact_tokens = {"rådighed", "firmabilen", "privat"}
        self.assertTrue(_is_toc_node(parent, fact_tokens))
        self.assertFalse(_is_toc_node(regel, fact_tokens))
        self.assertFalse(_is_toc_node(raadighed, fact_tokens))

        hit = lookup_hit_for_anchor(extract_anchors("LL § 16")[0])
        self.assertIsNotNone(hit)
        doors = _open_doors([hit], facts, None)
        found = lookup_djv_hits(
            [
                {
                    "law": "ligningsloven",
                    "section": "§ 16",
                    "kind": "statute",
                    "label": "ligningsloven § 16",
                }
            ],
            doors,
            facts=facts,
        )
        addresses = {item["lookup_address"] for item in found}
        self.assertIn("C.A.5.14.1.1", addresses)
        self.assertIn("C.A.5.14.1.4", addresses)
        self.assertIn("C.A.5.14.1.11", addresses)
        self.assertNotIn("C.A.5.14.1.12", addresses)
        self.assertTrue(all(item.startswith("C.A.5.14.1") for item in addresses))
        self.assertFalse(any(item.startswith("C.A.5.2") for item in addresses))
        self.assertFalse(any(item.startswith("C.A.5.14.4") for item in addresses))
        self.assertFalse(any(item.startswith("C.A.4") for item in addresses))

    def test_short_9a_question_opens_travel_not_small_expenses(self):
        hits = lookup_djv_hits(
            [
                {
                    "law": "ligningsloven",
                    "section": "§ 9 A",
                    "kind": "statute",
                    "label": "ligningsloven § 9 A",
                }
            ],
            [
                {
                    "label": "Stk. 1.",
                    "text": (
                        "skattefri rejsegodtgørelse når lønmodtageren på grund "
                        "af afstanden mellem bopæl og midlertidigt arbejdssted "
                        "ikke kan overnatte på den sædvanlige bopæl"
                    ),
                },
                {
                    "label": "Stk. 3.",
                    "text": "godtgørelsen overstiger de i stk. 2 nævnte satser",
                },
            ],
            facts="Kan Mette få rejsegodtgørelse efter ligningslovens § 9 A?",
        )
        addresses = {item["lookup_address"] for item in hits}
        self.assertIn("C.A.7.1.4", addresses)
        self.assertNotIn("C.A.2.5.2.30", addresses)

    def test_firmabil_assessment_leaf_binds_16_not_commute_example(self):
        eleven = lookup_djv_address("C.A.5.14.1.11")
        persons = lookup_djv_address("C.A.5.14.1.2")
        self.assertIsNotNone(eleven)
        self.assertIsNotNone(persons)
        assert eleven is not None
        assert persons is not None
        eleven_keys = {item["key"] for item in eleven["bindings"]}
        person_keys = {item["key"] for item in persons["bindings"]}
        self.assertIn("16", eleven_keys)
        self.assertNotIn("9c", eleven_keys)
        self.assertIn("16", person_keys)
        self.assertNotIn("9c", person_keys)


if __name__ == "__main__":
    unittest.main()
