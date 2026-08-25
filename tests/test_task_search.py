import unittest

from backend.services.task_search import (
    _fact_excerpt,
    _open_doors,
    _pack_chunks,
    _section_is_node,
    build_search_plan,
    compose_write_input,
    extract_anchors,
    extract_regulations,
    filename_looks_like_statute,
    format_retrieved_context,
    format_flat_retrieved_context,
    lookup_pack_for_chat,
    prefetch_chat_retrieval,
    run_layered_search,
)


class TaskSearchTests(unittest.TestCase):
    def test_extract_anchors_expands_abbreviations(self):
        anchors = extract_anchors("LL § 33 A og KSL § 1, stk. 1, nr. 1. DBO art. 15.")
        labels = [item["label"] for item in anchors]
        self.assertIn("ligningsloven § 33 A", labels)
        self.assertIn("kildeskatteloven § 1", labels)
        self.assertIn("dobbeltbeskatningsoverenskomst artikel 15", labels)

    def test_plan_splits_norm_and_issue_specific_interpretation(self):
        plan = build_search_plan(
            issues=[
                {
                    "id": "I1",
                    "question": "Er betingelserne i LL § 33 A opfyldt?",
                },
                {
                    "id": "I2",
                    "question": "Er der fuld skattepligt efter KSL § 1?",
                },
            ],
            legal_locus="LL § 33 A",
            message="Tim arbejder i Tyskland.",
        )
        norm_queries = [item["query"] for item in plan["norm_queries"]]
        self.assertTrue(any("ligningsloven § 33 A" in query for query in norm_queries))
        self.assertTrue(any("kildeskatteloven § 1" in query for query in norm_queries))
        self.assertTrue(all("lovtekst" in query for query in norm_queries))
        self.assertEqual(3, len(plan["interpretive_queries"]))
        self.assertEqual("scope", plan["interpretive_queries"][0]["issue_id"])
        self.assertIn("personkreds", plan["interpretive_queries"][0]["query"])
        self.assertIn("I1", plan["interpretive_queries"][1]["issue_id"])
        self.assertIn("praksis", plan["interpretive_queries"][1]["query"])
        self.assertIn("Er betingelserne i LL § 33 A opfyldt?", plan["interpretive_queries"][1]["query"])
        self.assertIn("Tim arbejder i Tyskland.", plan["interpretive_queries"][1]["query"])

    def test_gap_search_follows_citation_in_retrieved_statute(self):
        calls: list[str] = []

        def fake_search(query: str):
            calls.append(query)
            if "praksis" in query or "personkreds" in query:
                return [
                    {
                        "file_id": "djv",
                        "filename": "Den juridiske vejledning 2025-1.pdf",
                        "score": 0.5,
                        "text": "C.F.7.2.1 om ligningslovens § 33 A.",
                    }
                ]
            if "kildeskatteloven § 1" in query:
                return [
                    {
                        "file_id": "ksl",
                        "filename": "Kildeskatteloven (2024-01-01 nr. 12).pdf",
                        "score": 0.8,
                        "text": "§ 1. Personer, der har bopæl her i landet.",
                    }
                ]
            if "ligningsloven § 33 A" in query:
                return [
                    {
                        "file_id": "ll",
                        "filename": "Ligningsloven (2025-11-24 nr. 1500).pdf",
                        "score": 0.9,
                        "text": (
                            "§ 33 A. Lempelse forudsætter, at personen er skattepligtig "
                            "efter kildeskattelovens § 1."
                        ),
                    }
                ]
            return []

        pack = run_layered_search(
            client=None,  # type: ignore[arg-type]
            message="Tim bor i Tyskland.",
            legal_locus="LL § 33 A",
            issues=[{"id": "I1", "question": "Gælder LL § 33 A?"}],
            search_fn=fake_search,
        )
        file_ids = [item["file_id"] for item in pack["retrieved_chunks"]]
        self.assertTrue(any(item.startswith("opslag:ll:33a:") for item in file_ids))
        self.assertIn("ksl", file_ids)
        self.assertIn("djv", file_ids)
        self.assertTrue(any("kildeskatteloven § 1" in query for query in calls))
        self.assertFalse(any("ligningsloven § 33 A" in query and "lovtekst" in query for query in calls))
        self.assertTrue(any(item.get("source") == "opslag" for item in pack["searches"]))
        self.assertTrue(any(item["layer"] == "gap" for item in pack["searches"]))
        self.assertIn("Lag A — normgrundlag", pack["context_text"])
        self.assertIn("Lag B — fortolkningsgrundlag", pack["context_text"])
        self.assertIn("Opslag (ikke søgning)", pack["context_text"])
        first_ll = next(item for item in pack["retrieved_chunks"] if item.get("from_lookup"))
        self.assertTrue(first_ll["text"].startswith("§ 33 A."))
        self.assertGreater(len(first_ll["text"]), 2000)
        self.assertTrue(
            any(item.startswith("opslag:djv:C.F.4.2.1:") for item in file_ids)
        )
        self.assertTrue(
            any(
                "DJV-opslag" in query
                for item in pack["searches"]
                for query in item.get("queries") or []
            )
        )

    def test_filename_detects_statute_not_djv(self):
        self.assertTrue(filename_looks_like_statute("Ligningsloven (2025-11-24 nr. 1500).pdf"))
        self.assertFalse(filename_looks_like_statute("Den juridiske vejledning 2025-1.pdf"))

    def test_compose_write_input_keeps_facts_before_sources(self):
        text = compose_write_input(
            message="Faktum: Tim arbejder i Tyskland.",
            prefetch_context="[Hentede retskilder]\nlovtekst",
            uploaded_context="kontrakt",
        )
        self.assertTrue(text.startswith("Faktum:"))
        self.assertIn("Materiale lagt op af brugeren", text)
        self.assertIn("Hentede retskilder", text)

    def test_empty_retrieval_formats_blank_context(self):
        self.assertEqual("", format_retrieved_context([]))

    def test_scope_query_exists_without_status_word_in_facts(self):
        plan = build_search_plan(
            issues=[{"id": "I1", "question": "Gælder LL § 33 A?"}],
            legal_locus="LL § 33 A",
            message="Personen bor i udlandet og arbejder for en dansk arbejdsgiver.",
        )
        scope = plan["interpretive_queries"][0]["query"]
        self.assertIn("personkreds", scope)
        self.assertIn("hvem kan anvende", scope)
        joined = " ".join(item["query"] for item in plan["interpretive_queries"])
        self.assertIn("dansk arbejdsgiver", joined)

    def test_wrong_paragraph_in_statute_file_is_a_gap(self):
        calls: list[str] = []

        def fake_search(query: str):
            calls.append(query)
            if "kildeskatteloven § 5" in query:
                return [
                    {
                        "file_id": "ksl",
                        "filename": "Kildeskatteloven (2024-05-03 nr. 460).pdf",
                        "score": 0.7,
                        "text": "§ 62 A. Henstand. L 2010 723 ophævede § 5 B, stk. 3.",
                    }
                ]
            return []

        pack = run_layered_search(
            client=None,  # type: ignore[arg-type]
            message="Personen er omfattet af KSL § 5 A.",
            legal_locus="KSL § 5 A",
            issues=[{"id": "I1", "question": "Gælder KSL § 5 A?"}],
            search_fn=fake_search,
        )
        self.assertTrue(any(item["layer"] == "gap" for item in pack["searches"]))
        self.assertGreaterEqual(sum(1 for query in calls if "kildeskatteloven § 5 A" in query), 2)

    def test_pack_caps_chunks_per_file(self):
        from backend.services.task_search import _pack_chunks

        hits = [
            {
                "file_id": "skr",
                "filename": "styresignal.pdf",
                "text": f"uddrag {index}",
                "score": "0.9",
                "layer": "B",
            }
            for index in range(5)
        ]
        packed = _pack_chunks([], hits)
        self.assertEqual(2, len(packed))

    def test_cross_reference_is_not_the_section_node(self):
        anchor = extract_anchors("LL § 9 A")[0]
        mention = (
            "rejsefradrag i § 9 A.\n"
            "Copyright © Karnov Group Denmark A/S side 99\n"
            "DIS-ordningen i sømandsbeskatningslovens §§ 5-8."
        )
        node = (
            "§ 9 A. Skattefri rejsegodtgørelse kan udbetales, når lønmodtageren "
            "på grund af afstanden mellem bopæl og midlertidigt arbejdssted "
            "ikke har mulighed for at overnatte på sin sædvanlige bopæl."
        )
        self.assertFalse(_section_is_node(anchor, mention))
        self.assertTrue(_section_is_node(anchor, node))

    def test_mention_of_9a_looks_up_the_full_node_without_vector(self):
        calls: list[str] = []

        def fake_search(query: str):
            calls.append(query)
            if "praksis" in query or "personkreds" in query:
                return [
                    {
                        "file_id": "djv",
                        "filename": "Den juridiske vejledning 2025-1.pdf",
                        "score": 0.5,
                        "text": "C.A.7 om ligningslovens § 9 A.",
                    }
                ]
            return []

        pack = run_layered_search(
            client=None,  # type: ignore[arg-type]
            message="Kan Mette få rejsegodtgørelse efter ligningslovens § 9 A?",
            legal_locus="LL § 9 A",
            issues=[{"id": "I1", "question": "Er Mette på rejse efter LL § 9 A?"}],
            search_fn=fake_search,
        )
        first = pack["retrieved_chunks"][0]
        self.assertTrue(first.get("from_lookup"))
        self.assertTrue(first["text"].startswith("§ 9 A."))
        self.assertIn("Stk. 3.", first["text"])
        self.assertGreater(len(first["text"]), 3000)
        self.assertFalse(any("ligningsloven § 9 A" in query and "lovtekst" in query for query in calls))
        self.assertNotIn("§ 9 H.", first["text"][:80])
        self.assertTrue(any(item["file_id"] == "djv" for item in pack["retrieved_chunks"]))
        self.assertTrue(
            any(
                str(item["file_id"]).startswith("opslag:djv:C.A.7.3.2:")
                for item in pack["retrieved_chunks"]
            )
        )
        self.assertFalse(
            any(
                str(item["file_id"]).startswith("opslag:djv:C.F.")
                for item in pack["retrieved_chunks"]
            )
        )

    def test_layer_b_keeps_practice_on_anchor_and_drops_9h_neighbor(self):
        dagpleje = (
            "Bestemmelsen tilsigter skattemæssig ligestilling mellem dagpleje og "
            "døgnpleje, jf. § 9, stk. 6. Dokumenterede udgifter kan fradrages "
            "ved siden af standardfradraget efter § 9 H."
        )
        pensions = (
            "Pensionskasseordninger oprettet den 18. februar 1992 eller senere "
            "er omfattet af PBL § 53 A."
        )
        rejse = "C.A.7.1. Rejsegodtgørelse efter ligningslovens § 9 A, stk. 1."
        lsr = (
            "Af ligningslovens § 9 A, stk. 2 fremgår det, at den skattefrie "
            "godtgørelse maksimalt kan udgøre 487 kr. pr. dag."
        )

        def fake_search(query: str):
            if "praksis" in query or "personkreds" in query:
                return [
                    {
                        "file_id": "ll-pdf",
                        "filename": "Ligningsloven (2025-11-24 nr. 1500).pdf",
                        "score": 0.89,
                        "text": dagpleje,
                    },
                    {
                        "file_id": "djv-pension",
                        "filename": "DJV C.A Personbeskatning (2026-1).pdf",
                        "score": 0.75,
                        "text": pensions,
                    },
                    {
                        "file_id": "djv-rejse",
                        "filename": "DJV C.A Personbeskatning (2026-1).pdf",
                        "score": 0.70,
                        "text": rejse,
                    },
                    {
                        "file_id": "lsr",
                        "filename": "LSR2020.19.0079779.pdf",
                        "score": 0.82,
                        "text": lsr,
                    },
                ]
            return []

        pack = run_layered_search(
            client=None,  # type: ignore[arg-type]
            message="Kan Entreprise A/S udbetale skattefri rejsegodtgørelse efter LL § 9 A?",
            legal_locus="LL § 9 A",
            issues=[{"id": "I1", "question": "Gælder LL § 9 A?"}],
            search_fn=fake_search,
        )
        file_ids = [item["file_id"] for item in pack["retrieved_chunks"]]
        self.assertTrue(any(item.startswith("opslag:ll:9a:") for item in file_ids))
        self.assertIn("djv-rejse", file_ids)
        self.assertIn("lsr", file_ids)
        self.assertNotIn("ll-pdf", file_ids)
        self.assertNotIn("djv-pension", file_ids)
        self.assertNotIn(dagpleje, pack["context_text"])
        self.assertIn("ligningslovens § 9 A", pack["context_text"])

    def test_pack_prefers_section_node_over_neighbor(self):
        anchor = extract_anchors("LL § 9 A")[0]
        packed = _pack_chunks(
            [
                {
                    "file_id": "ll",
                    "filename": "Ligningsloven (2025-11-24 nr. 1500).pdf",
                    "score": 0.95,
                    "text": "rejsefradrag i § 9 A.\nside 99",
                    "anchor": "ligningsloven § 9 A",
                },
                {
                    "file_id": "ll",
                    "filename": "Ligningsloven (2025-11-24 nr. 1500).pdf",
                    "score": 0.70,
                    "text": "§ 9 A. Skattefri rejsegodtgørelse kan udbetales.",
                    "anchor": "ligningsloven § 9 A",
                },
            ],
            [],
            anchors=[anchor],
        )
        self.assertTrue(packed[0]["text"].startswith("§ 9 A."))

    def test_fact_excerpt_puts_supplements_first(self):
        message = (
            "Faktum:\nAnders har været i Danmark omkring 40 dage.\n\n"
            "Supplerende oplysninger\n\n"
            "Hvad var de præcise datoer?\n"
            "13.-16. marts: 4 dage. 24.-28. april: 5 dage."
        )
        excerpt = _fact_excerpt(message, max_chars=80)
        self.assertIn("13.-16. marts", excerpt)
        self.assertFalse(excerpt.startswith("Anders har været"))

    def test_flat_context_does_not_claim_two_layers(self):
        text = format_flat_retrieved_context(
            [
                {
                    "filename": "Ligningsloven.pdf",
                    "text": "§ 33 A. ...",
                }
            ]
        )
        self.assertIn("[Hentede retskilder]", text)
        self.assertIn("Ligningsloven.pdf", text)
        self.assertNotIn("Lag A", text)

    def test_prefetch_chat_retrieval_empty_query(self):
        pack = prefetch_chat_retrieval(client=None, query="  ")
        self.assertEqual(pack["retrieved_chunks"], [])
        self.assertEqual(pack["context_text"], "")

    def test_context_puts_bound_b_before_gap_so_djv_fits(self):
        lookup = {
            "from_lookup": True,
            "layer": "A",
            "filename": "Ligningsloven (LBKG nr. 1500) § 9 A",
            "text": "§ 9 A. " + ("n" * 7000),
        }
        gap = {
            "layer": "gap",
            "filename": "Kildeskatteloven (2024-05-03 nr. 460).pdf",
            "text": "§ 43. A-skat. " + ("k" * 18000),
        }
        djv = {
            "layer": "B",
            "filename": "DJV C.A Personbeskatning (2026-1).pdf",
            "text": "C.A.7 om ligningslovens § 9 A og rejsegodtgørelse.",
        }
        text = format_retrieved_context([lookup, gap, djv])
        self.assertIn("C.A.7 om ligningslovens § 9 A", text)
        self.assertLess(text.find("C.A.7"), text.find("A-skat") if "A-skat" in text else len(text))

    def test_gap_keeps_cited_ksl_node_and_drops_neighbor_pages(self):
        def fake_search(query: str):
            if "praksis" in query or "personkreds" in query:
                return [
                    {
                        "file_id": "djv-rejse",
                        "filename": "DJV C.A Personbeskatning (2026-1).pdf",
                        "score": 0.91,
                        "text": "C.A.7.2.5 om ligningslovens § 9 A og standardsatser.",
                    }
                ]
            if "kildeskatteloven § 43" in query:
                return [
                    {
                        "file_id": "ksl-wrong",
                        "filename": "Kildeskatteloven (2024-05-03 nr. 460).pdf",
                        "score": 0.85,
                        "text": "§ 48 E. Personer, som bliver skattepligtige efter § 1.",
                    },
                    {
                        "file_id": "ksl-node",
                        "filename": "Kildeskatteloven (2024-05-03 nr. 460).pdf",
                        "score": 0.80,
                        "text": "§ 43. Til A-indkomst henregnes enhver form for vederlag.",
                    },
                ]
            return []

        pack = run_layered_search(
            client=None,  # type: ignore[arg-type]
            message="Kan Entreprise A/S udbetale skattefri rejsegodtgørelse efter LL § 9 A?",
            legal_locus="LL § 9 A",
            issues=[{"id": "I1", "question": "Gælder LL § 9 A?"}],
            search_fn=fake_search,
        )
        self.assertIn("C.A.7.2.5 om ligningslovens § 9 A", pack["context_text"])
        file_ids = [item["file_id"] for item in pack["retrieved_chunks"]]
        self.assertIn("djv-rejse", file_ids)
        self.assertNotIn("ksl-wrong", file_ids)
        if "ksl-node" in file_ids:
            self.assertLess(
                pack["context_text"].find("C.A.7.2.5"),
                pack["context_text"].find("§ 43. Til A-indkomst"),
            )

    def test_extract_regulations_reads_bekendtgorelse_nummer(self):
        found = extract_regulations(
            "Arbejdsgiveren skal føre kontrol efter bekendtgørelse nr. 173 af 13. marts 2000."
        )
        self.assertEqual(["bekendtgørelse nr. 173"], [item["label"] for item in found])
        self.assertEqual("regulation", found[0]["kind"])

    def test_open_doors_9a_travel_skips_board_and_double_household(self):
        from backend.services.opslagsvaerk import lookup_hit_for_anchor

        hit = lookup_hit_for_anchor(extract_anchors("LL § 9 A")[0])
        self.assertIsNotNone(hit)
        assert hit is not None
        doors = _open_doors(
            [hit],
            message=(
                "Kan Entreprise A/S udbetale skattefri rejsegodtgørelse efter LL § 9 A? "
                "Elektriker, Odense til Aalborg hospital, 185 km, 2 timer 15 min, "
                "værelse mandag-fredag, standardsatser og kontrol, 24 timer."
            ),
            issues=[{"id": "I1", "question": "Gælder LL § 9 A?"}],
        )
        labels = [door["label"] for door in doors]
        self.assertTrue(labels[0].startswith("Stk. 1"))
        self.assertNotIn("Stk. 7.", labels)
        self.assertNotIn("Stk. 9.", labels)
        joined = " ".join(door["text"] for door in doors)
        self.assertNotIn("kildeskattelovens § 43", joined)
        self.assertNotIn("statsskattelovens § 6", joined)

    def test_layer_b_keeps_djv_without_paragraph_number_via_door_language(self):
        begreb = (
            "C.A.7.1. Rejsebegrebet. Et arbejdssted er midlertidigt, når "
            "lønmodtageren ikke kan overnatte på den sædvanlige bopæl på grund "
            "af afstanden."
        )

        def fake_search(query: str):
            if "praksis" in query or "personkreds" in query:
                return [
                    {
                        "file_id": "djv-begreb",
                        "filename": "DJV C.A Personbeskatning (2026-1).pdf",
                        "score": 0.72,
                        "text": begreb,
                    },
                    {
                        "file_id": "djv-pension",
                        "filename": "DJV C.A Personbeskatning (2026-1).pdf",
                        "score": 0.80,
                        "text": (
                            "Pensionskasseordninger oprettet den 18. februar 1992 "
                            "eller senere er omfattet af PBL § 53 A."
                        ),
                    },
                ]
            return []

        pack = run_layered_search(
            client=None,  # type: ignore[arg-type]
            message=(
                "Kan Entreprise A/S udbetale skattefri rejsegodtgørelse efter LL § 9 A? "
                "Elektriker med værelse i Aalborg og 24 timer væk fra bopælen."
            ),
            legal_locus="LL § 9 A",
            issues=[{"id": "I1", "question": "Gælder LL § 9 A?"}],
            search_fn=fake_search,
        )
        file_ids = [item["file_id"] for item in pack["retrieved_chunks"]]
        self.assertIn("djv-begreb", file_ids)
        self.assertNotIn("djv-pension", file_ids)
        self.assertIn("Rejsebegrebet", pack["context_text"])
        self.assertIn("åbnet disse stykker", pack["context_text"])

    def test_gap_skips_incidental_cites_and_follows_bek_in_layer_b(self):
        calls: list[str] = []

        def fake_search(query: str):
            calls.append(query)
            if "praksis" in query or "personkreds" in query:
                return [
                    {
                        "file_id": "djv-kontrol",
                        "filename": "DJV C.A Personbeskatning (2026-1).pdf",
                        "score": 0.88,
                        "text": (
                            "C.A.7.2 om ligningslovens § 9 A. Arbejdsgiveren skal "
                            "føre kontrol efter bekendtgørelse nr. 173."
                        ),
                    }
                ]
            if "bekendtgørelse nr. 173" in query:
                return [
                    {
                        "file_id": "bek173",
                        "filename": "Bekendtgørelse nr. 173 af 13. marts 2000.pdf",
                        "score": 0.7,
                        "text": "§ 2. Arbejdsgiveren skal føre kontrol med udbetalingen.",
                    }
                ]
            return []

        pack = run_layered_search(
            client=None,  # type: ignore[arg-type]
            message=(
                "Kan Entreprise A/S udbetale skattefri rejsegodtgørelse efter LL § 9 A? "
                "Elektriker, Aalborg, standardsatser, kontrol, 24 timer."
            ),
            legal_locus="LL § 9 A",
            issues=[{"id": "I1", "question": "Gælder LL § 9 A?"}],
            search_fn=fake_search,
        )
        joined = " ".join(calls)
        self.assertNotIn("kildeskatteloven § 43", joined)
        self.assertNotIn("statsskatteloven § 6", joined)
        self.assertTrue(any("bekendtgørelse nr. 173" in query for query in calls))
        file_ids = [item["file_id"] for item in pack["retrieved_chunks"]]
        self.assertIn("bek173", file_ids)
        self.assertIn("djv-kontrol", file_ids)
        door_lines = [
            query
            for item in pack["searches"]
            for query in item.get("queries") or []
            if str(query).startswith("Døre:")
        ]
        self.assertTrue(door_lines)
        self.assertNotIn("Stk. 9.", door_lines[0])

    def test_chat_lookup_pack_gives_full_9a_node_and_keeps_file_search(self):
        pack = lookup_pack_for_chat(
            "Kan Entreprise A/S udbetale skattefri rejsegodtgørelse efter LL § 9 A?"
        )
        self.assertTrue(pack["keep_file_search"])
        first = pack["retrieved_chunks"][0]
        self.assertTrue(first.get("from_lookup"))
        self.assertTrue(first["text"].startswith("§ 9 A."))
        self.assertIn("Stk. 3.", first["text"])
        self.assertGreater(len(first["text"]), 3000)
        file_ids = [item["file_id"] for item in pack["retrieved_chunks"]]
        self.assertTrue(any(item.startswith("opslag:djv:C.A.") for item in file_ids))
        self.assertFalse(any(item.startswith("opslag:djv:C.F.") for item in file_ids))
        self.assertIn("paragrafnode", pack["context_text"])
        self.assertIn("også slå praksis", pack["context_text"])
        self.assertIn("DJV 2026-2", pack["context_text"])

    def test_prefetch_chat_keeps_lookup_and_drops_replaced_statute_pdf(self):
        dagpleje = "rejsefradrag i § 9 A, men teksten er § 9 H om dagpleje."

        def fake_search(query: str):
            return [
                {
                    "file_id": "ll-pdf",
                    "filename": "Ligningsloven (2025-11-24 nr. 1500).pdf",
                    "score": 0.9,
                    "text": dagpleje,
                },
                {
                    "file_id": "djv",
                    "filename": "Den juridiske vejledning 2026-1.pdf",
                    "score": 0.5,
                    "text": "C.A.7 om ligningslovens § 9 A.",
                },
            ]

        pack = prefetch_chat_retrieval(
            client=None,  # type: ignore[arg-type]
            query="Kan Mette få rejsegodtgørelse efter ligningslovens § 9 A?",
            search_fn=fake_search,
        )
        file_ids = [item["file_id"] for item in pack["retrieved_chunks"]]
        self.assertTrue(any(item.startswith("opslag:ll:9a:") for item in file_ids))
        self.assertIn("djv", file_ids)
        self.assertNotIn("ll-pdf", file_ids)
        self.assertTrue(pack["retrieved_chunks"][0]["text"].startswith("§ 9 A."))

    def test_33a_looks_up_djv_node_and_drops_same_family_pdf(self):
        def fake_search(query: str):
            if "praksis" in query or "personkreds" in query:
                return [
                    {
                        "file_id": "djv-cf4-pdf",
                        "filename": "Den juridiske vejledning 2025-1.pdf",
                        "score": 0.7,
                        "text": "C.F.4.2.1 uddrag fra PDF om ligningslovens § 33 A.",
                    },
                    {
                        "file_id": "djv",
                        "filename": "Den juridiske vejledning 2025-1.pdf",
                        "score": 0.5,
                        "text": "C.F.7.2.1 om ligningslovens § 33 A.",
                    },
                ]
            return []

        pack = run_layered_search(
            client=None,  # type: ignore[arg-type]
            message=(
                "Tim bor i Tyskland. Dobbeltbeskatningsoverenskomsten "
                "tillægger Danmark beskatningsretten."
            ),
            legal_locus="LL § 33 A",
            issues=[{"id": "I1", "question": "Gælder LL § 33 A?"}],
            search_fn=fake_search,
        )
        file_ids = [item["file_id"] for item in pack["retrieved_chunks"]]
        self.assertTrue(any(item.startswith("opslag:djv:C.F.4.2.1:") for item in file_ids))
        self.assertTrue(any(item.startswith("opslag:djv:C.F.4.2.3:") for item in file_ids))
        self.assertIn("djv", file_ids)
        self.assertNotIn("djv-cf4-pdf", file_ids)
        self.assertIn("C.F.4.2.1", pack["context_text"])
        self.assertIn("slået op som node, ikke søgt", pack["context_text"])


if __name__ == "__main__":
    unittest.main()
