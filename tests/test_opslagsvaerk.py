import unittest

from backend.services.opslagsvaerk import (
    lookup_paragraph,
    normalize_normative_text,
    paragraph_key,
    paragraph_stability,
)


class OpslagsvaerkTests(unittest.TestCase):
    def test_paragraph_key_folds_section_forms(self):
        self.assertEqual("9a", paragraph_key("§ 9 A"))
        self.assertEqual("9a", paragraph_key("9 A"))
        self.assertEqual("9a", paragraph_key("9a"))
        self.assertEqual("33a", paragraph_key("LL § 33 A"))
        self.assertEqual("", paragraph_key(""))

    def test_lookup_9a_returns_full_node_not_9h(self):
        found = lookup_paragraph("ligningsloven", "§ 9 A")
        self.assertIsNotNone(found)
        assert found is not None
        text = found["normativeText"]
        self.assertTrue(text.startswith("§ 9 A."))
        self.assertIn("Stk. 3.", text)
        self.assertGreaterEqual(len(found["subsections"]), 10)
        self.assertGreater(len(text), 3000)
        self.assertNotIn("§ 9 H.", text.split("Stk. 1.")[0])
        self.assertEqual("1500", found["edition"])
        other = lookup_paragraph("kildeskatteloven", "§ 1")
        self.assertIsNone(other)

    def test_lookup_33a_is_the_lempelse_node(self):
        found = lookup_paragraph("ligningsloven", "33a")
        self.assertIsNotNone(found)
        assert found is not None
        self.assertTrue(found["normativeText"].startswith("§ 33 A."))
        self.assertIn("kildeskattelovens § 1", found["normativeText"].lower())

    def test_hyphen_is_not_a_legal_change(self):
        self.assertEqual(
            normalize_normative_text("for\u2010bindelse"),
            normalize_normative_text("forbindelse"),
        )
        nine_a = paragraph_stability("9a")
        self.assertEqual("1735", nine_a["stable_since_edition"])
        self.assertEqual([], nine_a["changed_hops"])
        thirty_three = paragraph_stability("33a")
        self.assertEqual("1735", thirty_three["stable_since_edition"])
        nine_c = paragraph_stability("9c")
        self.assertIn("42-1500", nine_c["changed_hops"])
        self.assertEqual("1500", nine_c["stable_since_edition"])


if __name__ == "__main__":
    unittest.main()
