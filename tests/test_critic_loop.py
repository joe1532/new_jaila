import unittest

from backend.services.critic_loop import (
    HENRIK_GOLD_ADDRESSES,
    build_pipeline_trace,
    build_retrieval_manifest,
    decide_critic_action,
    extract_cited_addresses,
    format_fail_closed,
    lookup_canonical_nodes,
    parse_critic_payload,
    recovery_address,
    recovery_addresses,
    unused_gold_in_manifest,
)


class CriticLoopTests(unittest.TestCase):
    def test_manifest_extracts_clear_djv_address(self):
        rows = build_retrieval_manifest(
            [
                {
                    "file_id": "file-1",
                    "filename": "JURV C.A.5.14.1.4 Rådighed.pdf",
                    "score": "0.9",
                    "text": "C.A.5.14.1.4 Rådighedsbeskatning af firmabil.",
                },
                {
                    "file_id": "file-2",
                    "filename": "JURV2026-2_C.A.pdf",
                    "score": "0.4",
                    "text": "Se også andre afsnit om personalegoder og kørsel.",
                },
            ]
        )
        self.assertEqual(rows[0]["address"], "C.A.5.14.1.4")
        self.assertEqual(rows[0]["complete"], "true")
        self.assertEqual(rows[1]["address"], "")
        self.assertEqual(rows[1]["complete"], "false")

    def test_extract_uses_draft_citations_not_see_also(self):
        draft = (
            "Konklusionen følger ligningsloven § 16, stk. 4 og C.A.5.14.1.4. "
            "Kilometer er ikke afgørende."
        )
        cited = extract_cited_addresses(draft)
        keys = {item["canonical"] for item in cited}
        self.assertTrue(any("16" in key and "stk. 4" in key for key in keys))
        self.assertIn("C.A.5.14.1.4", keys)
        self.assertFalse(any("9 C" in key or "9C" in key.replace(" ", "") for key in keys))

    def test_eval_splits_retrieval_miss_from_writer_miss(self):
        manifest = [
            {"address": "C.A.5.14.1.4"},
            {"address": "C.A.5.14.1.12"},
        ]
        cited = [{"canonical": "ligningsloven § 16, stk. 4"}]
        row = unused_gold_in_manifest(manifest, cited, HENRIK_GOLD_ADDRESSES)
        self.assertIn("c.a.5.14.1.4", row["gold_in_manifest"])
        self.assertIn("c.a.5.14.1.4", row["unused_in_draft"])
        self.assertTrue(any("16" in item and "4" in item for item in row["missing_from_retrieval"]))

    def test_eval_writer_used_gold_in_pose(self):
        manifest = [{"address": "C.A.5.14.1.4"}, {"address": "ligningsloven § 16, stk. 4"}]
        cited = [
            {"canonical": "C.A.5.14.1.4"},
            {"canonical": "ligningsloven § 16, stk. 4"},
        ]
        row = unused_gold_in_manifest(manifest, cited, HENRIK_GOLD_ADDRESSES)
        self.assertEqual(row["unused_in_draft"], [])
        self.assertEqual(row["missing_from_retrieval"], [])

    def test_underkend_with_address_recovers(self):
        self.assertEqual(
            decide_critic_action(
                {"status": "underkend", "mangler": ["C.A.5.14.1.4"], "fejl": ["km"]}
            ),
            "recover",
        )

    def test_underkend_without_address_fails_closed(self):
        self.assertEqual(
            decide_critic_action({"status": "underkend", "mangler": [], "fejl": ["km"]}),
            "fail_closed",
        )

    def test_godkend_does_not_recover(self):
        self.assertEqual(
            decide_critic_action({"status": "godkend", "mangler": ["C.A.5.14.1.4"]}),
            "godkend",
        )

    def test_does_not_recover_djv_already_looked_up(self):
        self.assertEqual(
            decide_critic_action(
                {"status": "mangler", "mangler": ["C.A.5.14.1.4"]},
                nodes=[{"kind": "djv", "address": "C.A.5.14.1.4", "status": "ok"}],
            ),
            "godkend",
        )

    def test_section_9_does_not_count_as_9a(self):
        self.assertEqual(
            decide_critic_action(
                {"status": "mangler", "mangler": ["ligningsloven § 9 A"]},
                nodes=[{"kind": "ll", "address": "ligningsloven § 9", "status": "ok"}],
            ),
            "recover",
        )

    def test_mangler_skm_does_not_recover_when_door_is_present(self):
        self.assertEqual(
            decide_critic_action(
                {
                    "status": "mangler",
                    "primaert_stk": 4,
                    "mangler": ["SKM2014.685.BR", "SKM2024.71.VLR"],
                    "fejl": ["Konklusionen bæres af ligningslovens § 16, stk. 4."],
                },
                nodes=[
                    {"kind": "ll", "address": "ligningsloven § 16, stk. 4", "status": "ok"},
                    {"kind": "djv", "address": "C.A.5.14.1.4", "status": "ok"},
                ],
            ),
            "godkend",
        )

    def test_recovery_skips_skm_and_takes_djv(self):
        self.assertEqual(
            recovery_address(
                {"mangler": ["SKM2024.71.VLR", "C.A.5.14.1.4"]}
            ),
            "C.A.5.14.1.4",
        )

    def test_underkend_with_only_skm_fails_closed(self):
        self.assertEqual(
            decide_critic_action(
                {"status": "underkend", "mangler": ["SKM2024.71.VLR"], "fejl": ["km"]}
            ),
            "fail_closed",
        )

    def test_underkend_with_nodes_revises(self):
        self.assertEqual(
            decide_critic_action(
                {
                    "status": "underkend",
                    "mangler": [],
                    "fejl": ["Udkastet bruger § 33 stk. 2, men noden er stk. 1."],
                },
                nodes=[{"kind": "ll", "address": "ligningsloven § 33", "status": "ok"}],
            ),
            "revise",
        )

    def test_mangler_fejl_revises_when_door_already_looked_up(self):
        self.assertEqual(
            decide_critic_action(
                {
                    "status": "mangler",
                    "mangler": ["ligningsloven § 9 A"],
                    "fejl": ["350.000 kr. er forkert."],
                },
                nodes=[{"kind": "ll", "address": "ligningsloven § 9 A", "status": "ok"}],
            ),
            "revise",
        )

    def test_recovery_addresses_returns_all_ll_doors(self):
        self.assertEqual(
            recovery_addresses(
                {
                    "mangler": [
                        "ligningsloven § 9 A",
                        "SKM2024.71.VLR",
                        "ligningsloven § 33 F",
                    ]
                }
            ),
            ["ligningsloven § 9 A", "ligningsloven § 33 F"],
        )

    def test_trace_revise_does_not_say_show_draft(self):
        trace = build_pipeline_trace(
            chunks=[],
            manifest=[],
            cited=[],
            nodes=[{"kind": "ll", "address": "ligningsloven § 33", "status": "ok"}],
            verdict={"status": "underkend", "mangler": [], "fejl": ["forkert stk."]},
            action="revise",
            outcome="rewrite",
        )
        detail = " ".join(step["detail"] for step in trace["steps"])
        self.assertIn("Skriv om ud fra slåede noder", detail)
        self.assertNotIn("Vis udkastet", detail)

    def test_parse_rejects_unknown_status(self):
        parsed = parse_critic_payload('{"status": "måske", "primaert_stk": 4, "mangler": [], "fejl": []}')
        self.assertEqual(parsed["status"], "underkend")
        self.assertEqual(parsed["primaert_stk"], 4)

    def test_fail_closed_text_is_not_a_fake_note(self):
        text = format_fail_closed({"fejl": ["Svaret afgjorde rådighed på kilometer."]})
        self.assertIn("ikke udsendt", text)
        self.assertIn("kilometer", text)

    def test_ll16_lookup_returns_stk_list(self):
        cited = extract_cited_addresses("Hjemlen er ligningsloven § 16, stk. 4.")
        nodes = lookup_canonical_nodes(cited)
        self.assertTrue(nodes)
        ll_nodes = [item for item in nodes if item.get("kind") == "ll"]
        self.assertTrue(ll_nodes)
        stks = {row["stk"] for row in ll_nodes[0]["subsections"]}
        self.assertIn("4", stks)
        self.assertGreaterEqual(len(stks), 4)

    def test_lookup_keeps_distinct_ll_sections(self):
        cited = extract_cited_addresses(
            "Hjemlen er ligningsloven § 33 A, ligningsloven § 9, "
            "ligningsloven § 33, ligningsloven § 33 F og ligningsloven § 9 A."
        )
        nodes = lookup_canonical_nodes(cited)
        labels = {
            str(item.get("address") or "")
            for item in nodes
            if item.get("kind") == "ll" and item.get("status") == "ok"
        }
        self.assertGreaterEqual(len(labels), 4)
        self.assertTrue(any("33 A" in label for label in labels))
        self.assertTrue(any("9 A" in label for label in labels))

    def test_pipeline_trace_records_critic_and_outcome(self):
        trace = build_pipeline_trace(
            chunks=[{"filename": "JURV C.A.5.14.1.4.pdf", "text": "C.A.5.14.1.4 Rådighed."}],
            manifest=[{"address": "C.A.5.14.1.4"}],
            cited=[{"canonical": "C.A.5.14.1.4"}],
            nodes=[{"kind": "djv", "address": "C.A.5.14.1.4", "status": "ok", "cited_stk": ""}],
            verdict={
                "status": "mangler",
                "primaert_stk": 4,
                "mangler": ["ligningsloven § 16, stk. 4"],
                "fejl": [],
            },
            action="recover",
            outcome="rewrite",
            recovery_address="ligningsloven § 16, stk. 4",
            recovery_source="node",
        )
        self.assertEqual(trace["pipeline"], "task_critic_v1")
        self.assertEqual(trace["outcome"], "rewrite")
        ids = [step["id"] for step in trace["steps"]]
        self.assertEqual(ids, ["file_search", "writer", "lookup", "critic", "action", "outcome"])
        critic = next(step for step in trace["steps"] if step["id"] == "critic")
        self.assertIn("mangler", critic["detail"])
        self.assertIn("stk. 4", critic["detail"])
        follow = next(step for step in trace["steps"] if step["id"] == "action")
        self.assertIn("ligningsloven § 16, stk. 4", follow["detail"])
        result = next(step for step in trace["steps"] if step["id"] == "outcome")
        self.assertIn("omskrivning", result["detail"])


if __name__ == "__main__":
    unittest.main()
