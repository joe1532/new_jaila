import json
import unittest

from backend.services.task_solve import (
    apply_issue_additions,
    excerpt_is_grounded,
    parse_expansion_additions,
    parse_intake_payload,
    pin_legal_locus,
    should_ask_facts,
)


def _fact(**overrides):
    row = {
        "fact": "Opholdsdage i udlandet",
        "status": "UNKNOWN",
        "materiality": "DECISIVE",
        "question": "Hvor mange dage opholdt personen sig i udlandet?",
        "kind": "text",
    }
    row.update(overrides)
    return row


class TaskSolveTests(unittest.TestCase):
    def test_pin_legal_locus_prepends_search_anchor(self):
        pinned = pin_legal_locus("Bor i Tyskland, arbejder i DK.", "LL § 33 A")
        self.assertIn("Retligt udgangspunkt anvist af brugeren: LL § 33 A", pinned)
        self.assertTrue(pinned.endswith("Bor i Tyskland, arbejder i DK."))

    def test_pin_legal_locus_skips_empty(self):
        self.assertEqual(pin_legal_locus("  sag  ", "  "), "sag")

    def test_parse_ignores_model_can_proceed_and_caps_questions(self):
        facts = [
            _fact(fact=f"Faktum {i}", question=f"Spørgsmål {i}?") for i in range(8)
        ]
        raw = (
            "```json\n"
            + json.dumps(
                {
                    "can_proceed": True,
                    "issues": [
                        {
                            "issue_id": "I1",
                            "question": "Gælder LL § 33 A?",
                            "required_facts": facts,
                        }
                    ],
                }
            )
            + "\n```"
        )
        parsed = parse_intake_payload(raw)
        self.assertFalse(parsed["can_proceed"])
        self.assertFalse(parsed["sufficient"])
        self.assertEqual(len(parsed["questions"]), 5)
        self.assertEqual(parsed["questions"][0]["prompt"], "Spørgsmål 0?")

    def test_relevant_unknown_does_not_block(self):
        parsed = parse_intake_payload(
            {
                "can_proceed": False,
                "issues": [
                    {
                        "issue_id": "I1",
                        "question": "Skattepligt?",
                        "required_facts": [
                            _fact(materiality="RELEVANT", question="Har du dokumentation?")
                        ],
                    }
                ],
            }
        )
        self.assertTrue(parsed["can_proceed"])
        self.assertEqual(parsed["questions"], [])

    def test_irrelevant_unknown_is_ignored(self):
        parsed = parse_intake_payload(
            {
                "issues": [
                    {
                        "issue_id": "I1",
                        "question": "Skattepligt?",
                        "required_facts": [_fact(materiality="IRRELEVANT")],
                    }
                ],
            }
        )
        self.assertTrue(parsed["can_proceed"])
        self.assertEqual(parsed["questions"], [])

    def test_conceptual_empty_issues_proceeds(self):
        parsed = parse_intake_payload({"can_proceed": False, "issues": []})
        self.assertTrue(parsed["can_proceed"])
        self.assertEqual(parsed["questions"], [])

    def test_invalid_json_does_not_block(self):
        parsed = parse_intake_payload("ikke json")
        self.assertTrue(parsed["can_proceed"])
        self.assertEqual(parsed["questions"], [])

    def test_should_ask_only_when_blocked_and_has_questions(self):
        self.assertFalse(
            should_ask_facts({"can_proceed": False, "issues": [], "questions": []})
        )
        self.assertTrue(
            should_ask_facts(
                {
                    "can_proceed": False,
                    "questions": [{"id": "q1", "prompt": "Hvor bor personen?", "kind": "country"}],
                }
            )
        )
        self.assertFalse(
            should_ask_facts(
                {
                    "can_proceed": True,
                    "questions": [{"id": "q1", "prompt": "Hvor bor personen?", "kind": "country"}],
                }
            )
        )

    def test_day_count_is_number_not_amount(self):
        parsed = parse_intake_payload(
            {
                "issues": [
                    {
                        "issue_id": "I1",
                        "question": "Gælder LL § 33 A?",
                        "required_facts": [
                            _fact(
                                fact="Opholdsdage i Danmark",
                                question=(
                                    "Hvor mange dage opholder Tom sig i Danmark under "
                                    "hver afsluttet seksmånedersperiode af udlandsopholdet?"
                                ),
                                kind="amount",
                            )
                        ],
                    }
                ],
            }
        )
        self.assertEqual("number", parsed["questions"][0]["kind"])
        self.assertEqual("number", parsed["issues"][0]["required_facts"][0]["kind"])

    def test_money_stays_amount(self):
        parsed = parse_intake_payload(
            {
                "issues": [
                    {
                        "issue_id": "I1",
                        "question": "Hvad er indkomsten?",
                        "required_facts": [
                            _fact(
                                fact="Løn",
                                question="Hvad er den samlede løn i kr.?",
                                kind="amount",
                            )
                        ],
                    }
                ],
            }
        )
        self.assertEqual("amount", parsed["questions"][0]["kind"])


NOTE_833 = (
    "I SKM 2001 194 TSS fandt Told- og Skattestyrelsen, at grænsegængere i "
    "henhold til kildeskattelovens §§ 5 A-5 D kan få skattelempelse efter § 33 A "
    "uden at være fuldt skattepligtige efter kildeskattelovens § 1, hvis betingelserne "
    "i § 33 A ellers er opfyldt."
)
EMPLOYER = (
    "Når udlandsopholdet er begrundet i arbejdsgiverens forhold, betyder det, "
    "at der kan gives lempelse efter ligningslovens § 33 A, forudsat at "
    "betingelserne herfor i øvrigt er opfyldt."
)
RETRIEVED = f"[Hentede retskilder]\n{NOTE_833}\n{EMPLOYER}"


def _addition(**overrides):
    row = {
        "issue_id": "I1",
        "issue_question": "Gælder LL § 33 A?",
        "fact": "Omfattet af kildeskattelovens §§ 5 A-5 D",
        "status": "UNKNOWN",
        "materiality": "DECISIVE",
        "question": "Er personen omfattet af kildeskattelovens §§ 5 A-5 D?",
        "kind": "yes_no",
        "source_excerpt": NOTE_833[:80],
        "source_filename": "Ligningsloven.pdf",
    }
    row.update(overrides)
    return row


class TaskExpandTests(unittest.TestCase):
    def test_grounded_addition_blocks_and_asks_only_the_new_fact(self):
        base = [
            {
                "issue_id": "I1",
                "question": "Gælder LL § 33 A?",
                "required_facts": [
                    _fact(
                        fact="Skattepligtsstatus",
                        status="KNOWN",
                        question="Hvilken skattepligtsstatus har personen?",
                    )
                ],
            }
        ]
        parsed = apply_issue_additions(base, [_addition()], RETRIEVED)
        self.assertFalse(parsed["can_proceed"])
        self.assertEqual(1, len(parsed["questions"]))
        self.assertIn("5 A-5 D", parsed["questions"][0]["prompt"])
        self.assertEqual(2, len(parsed["issues"][0]["required_facts"]))

    def test_ungrounded_excerpt_is_dropped(self):
        parsed = apply_issue_additions(
            [],
            [_addition(source_excerpt="Dette citat står ikke i de hentede uddrag overhovedet.")],
            RETRIEVED,
        )
        self.assertTrue(parsed["can_proceed"])
        self.assertEqual([], parsed["questions"])

    def test_short_excerpt_is_not_grounded(self):
        self.assertFalse(excerpt_is_grounded("grænsegængere", NOTE_833))
        self.assertTrue(excerpt_is_grounded(NOTE_833[:80], NOTE_833))

    def test_duplicate_of_existing_fact_is_dropped(self):
        base = [
            {
                "issue_id": "I1",
                "question": "Gælder LL § 33 A?",
                "required_facts": [
                    _fact(
                        fact="Omfattet af kildeskattelovens §§ 5 A-5 D",
                        status="KNOWN",
                        question="Er personen omfattet af kildeskattelovens §§ 5 A-5 D?",
                    )
                ],
            }
        ]
        parsed = apply_issue_additions(base, [_addition()], RETRIEVED)
        self.assertTrue(parsed["can_proceed"])
        self.assertEqual(1, len(parsed["issues"][0]["required_facts"]))

    def test_does_not_reask_original_unknowns(self):
        base = [
            {
                "issue_id": "I1",
                "question": "Gælder LL § 33 A?",
                "required_facts": [
                    _fact(
                        fact="Opholdets varighed",
                        status="UNKNOWN",
                        question="Hvor længe varede opholdet?",
                    )
                ],
            }
        ]
        parsed = apply_issue_additions(base, [_addition()], RETRIEVED)
        prompts = [item["prompt"] for item in parsed["questions"]]
        self.assertEqual(["Er personen omfattet af kildeskattelovens §§ 5 A-5 D?"], prompts)

    def test_known_addition_does_not_block(self):
        parsed = apply_issue_additions(
            [],
            [_addition(status="KNOWN")],
            RETRIEVED,
        )
        self.assertTrue(parsed["can_proceed"])
        self.assertEqual([], parsed["questions"])
        self.assertEqual("KNOWN", parsed["issues"][0]["required_facts"][0]["status"])

    def test_new_issue_when_id_unknown(self):
        parsed = apply_issue_additions(
            [
                {
                    "issue_id": "I1",
                    "question": "Gælder LL § 33 A?",
                    "required_facts": [_fact(status="KNOWN")],
                }
            ],
            [
                _addition(
                    issue_id="I2",
                    issue_question="Sammenhæng med arbejdsgiverens forhold",
                    fact="Opholdet er begrundet i arbejdsgiverens forhold",
                    question="Er opholdet begrundet i arbejdsgiverens forhold?",
                    source_excerpt=EMPLOYER[:90],
                )
            ],
            RETRIEVED,
        )
        self.assertEqual(2, len(parsed["issues"]))
        self.assertEqual("I2", parsed["issues"][1]["issue_id"])
        self.assertFalse(parsed["can_proceed"])

    def test_caps_added_questions_at_three(self):
        extras = [
            _addition(
                fact=f"Betingelse {index}",
                question=f"Er betingelse {index} opfyldt?",
                source_excerpt=NOTE_833[:80],
            )
            for index in range(5)
        ]
        parsed = apply_issue_additions([], extras, RETRIEVED)
        self.assertEqual(3, len(parsed["questions"]))

    def test_invalid_expansion_json_is_empty(self):
        self.assertEqual([], parse_expansion_additions("ikke json"))

    def test_whitespace_in_excerpt_still_grounds(self):
        noisy = "  " + NOTE_833[:80].replace(" ", "  ") + "  "
        self.assertTrue(excerpt_is_grounded(noisy, NOTE_833))


if __name__ == "__main__":
    unittest.main()
