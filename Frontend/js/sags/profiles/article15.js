export function createArticle15Profile(section) {
  const safeSection = Number(section) === 2 ? 2 : 1;
  return {
    profile_id: "employment_article_15_s1_s2",
    requires_day_allocation: true,
    requires_employer_assessment: true,
    legal_sources: [
      { label: "KSL § 1, stk. 1, nr. 1", reason: "Mulig fuld dansk skattepligt" },
      { label: "SSL § 4", reason: "Globalindkomstprincip ved fuld skattepligt" },
      { label: `DBO artikel 15, stk. ${safeSection}`, reason: "Valgt artikel til foreløbig subsumption" },
    ],
    apply({ context }) {
      const workdays = Array.isArray(context.workdays) ? context.workdays : [];
      const totalDays = workdays.reduce((sum, row) => sum + Number(row.days || 0), 0);
      const employerCountry = String(context.employerCountry || "").trim() || "(ikke angivet)";
      const hasGrossIncome = Number.isFinite(Number(context.grossIncome && context.grossIncome.amount));
      const firstForeignWorkday = workdays.find((row) => String(row.country || "").trim().toLowerCase() !== "danmark");
      const arbejdsland = firstForeignWorkday ? String(firstForeignWorkday.country || "").trim() : "";
      const arbejdsdage = firstForeignWorkday ? Number(firstForeignWorkday.days || 0) : 0;
      const parsedArticle = context.parsedArticle && typeof context.parsedArticle === "object"
        ? context.parsedArticle
        : { article: null, section: null };
      const article15ScopeOk = Number(parsedArticle.article) === 15 && [1, 2].includes(Number(parsedArticle.section || safeSection));
      const residenceAvailableInWorkCountry = Boolean(context.residenceAvailableInWorkCountry);
      const taxResidenceDenmarkFact = String(context.taxResidenceDenmarkFact || "").trim();
      const contractReceived = String(context.employmentContractReceived || "").trim().toLowerCase();
      const dayTestResolved = Boolean(arbejdsland && Number.isFinite(arbejdsdage));
      const dayTestPass = dayTestResolved ? arbejdsdage <= 183 : null;
      const employerTestResolved = Boolean(arbejdsland && employerCountry && employerCountry !== "(ikke angivet)");
      const employerTestPass = employerTestResolved
        ? employerCountry.toLowerCase() !== arbejdsland.toLowerCase()
        : null;

      const praemisser = [
        {
          key: "income_type_salary_under_article_15",
          type: "assumption",
          status: "aktiv",
          data: {
            article: 15,
            section: safeSection,
          },
        },
        {
          key: "denmark_home_state_applied",
          type: "assumption",
          status: taxResidenceDenmarkFact ? "aktiv" : "uafklaret",
          data: {
            residence_country: String(context.residenceCountry || "").trim(),
            residence_available_in_work_country: residenceAvailableInWorkCountry,
            tax_residence_fact_present: Boolean(taxResidenceDenmarkFact),
          },
        },
        {
          key: "employer_residence_applied",
          type: "assumption",
          status: employerCountry === "(ikke angivet)" ? "uafklaret" : "aktiv",
          data: {
            employer_country: employerCountry === "(ikke angivet)" ? null : employerCountry,
          },
        },
      ];

      /** @type {Array<Record<string, unknown>>} */
      const vurderingstrin = [
        {
          trin_id: "art15_scope_gate",
          juridisk_spoergsmaal: "Er den valgte bestemmelse artikel 15, stk. 1 eller stk. 2?",
          faktagrundlag: ["selected_dbo_article"],
          resultat: article15ScopeOk ? "opfyldt" : "ikke_opfyldt",
          status: article15ScopeOk ? "afklaret" : "konfliktende",
          tekstlinje: "",
        },
        {
          trin_id: "art15_hjemsted_vurdering",
          juridisk_spoergsmaal: "Kan Danmark behandles som hjemstat på foreliggende oplysninger?",
          faktagrundlag: ["residence_country", "tax_residence_denmark_fact", "residence_available_in_work_country"],
          resultat: taxResidenceDenmarkFact ? "opfyldt" : "uafklaret",
          status: taxResidenceDenmarkFact ? "afklaret" : "uafklaret",
          tekstlinje: "",
        },
        {
          trin_id: "art15_arbejdsland",
          juridisk_spoergsmaal: "I hvilke lande er arbejdet udført?",
          faktagrundlag: ["workdays_by_country"],
          resultat: {
            arbejdslande: workdays.map((row) => row.country),
            total_arbejdsdage: totalDays,
          },
          status: workdays.length ? "afklaret" : "uafklaret",
          tekstlinje: "",
        },
      ];

      if (safeSection === 2) {
        vurderingstrin.push(
          {
            trin_id: "art15_s2_dage",
            juridisk_spoergsmaal: "Overstiger arbejdet i den anden stat 183 dage?",
            faktagrundlag: ["workdays_by_country"],
            resultat: dayTestResolved ? (dayTestPass ? "opfyldt" : "ikke_opfyldt") : "uafklaret",
            status: dayTestResolved ? "afklaret" : "uafklaret",
            tekstlinje: "",
          },
          {
            trin_id: "art15_s2_arbejdsgiver",
            juridisk_spoergsmaal: "Er arbejdsgiveren hjemmehørende i arbejdslandet?",
            faktagrundlag: ["employer_residence_country", "workdays_by_country"],
            resultat: employerTestResolved ? (employerTestPass ? "opfyldt" : "ikke_opfyldt") : "uafklaret",
            status: employerTestResolved ? "afklaret" : "uafklaret",
            tekstlinje: "",
          },
          {
            trin_id: "art15_s2_fast_driftssted",
            juridisk_spoergsmaal: "Udredes lønnen af fast driftssted i arbejdslandet?",
            faktagrundlag: ["employment_contract_note", "employment_contract_received"],
            resultat: "uafklaret",
            status: "uafklaret",
            tekstlinje: "",
          },
        );
      }

      vurderingstrin.push({
        trin_id: "allokering_af_indkomst",
        juridisk_spoergsmaal: "Hvordan allokeres indkomsten foreløbigt mellem landene?",
        faktagrundlag: ["fordelingsmetode", "gross_income_total", "workdays_by_country"],
        resultat: {
          metode: "pro_rata_workdays",
        },
        status: hasGrossIncome && workdays.length ? "afklaret" : "uafklaret",
        tekstlinje: "",
      });

      const conclusion = {
        text: hasGrossIncome && workdays.length
          ? "Det er på det foreliggende grundlag den foreløbige vurdering, at beskatningsretten fordeles efter artikel 15 med arbejdsdagsbaseret allokering."
          : "Det er på det foreliggende grundlag kun muligt at foretage en foreløbig artikel 15-vurdering med væsentlige forbehold.",
        status: "foreløbig",
      };

      const uafklarede_sporgsmaal = [];
      if (!dayTestResolved && safeSection === 2) {
        uafklarede_sporgsmaal.push({
          key: "art15_s2_day_test_unresolved",
          type: "missing_data",
          status: "uafklaret",
          data: {
            required_field: "workdays_by_country",
          },
        });
      }
      const advarsler = [];
      if (!hasGrossIncome) {
        advarsler.push({
          key: "gross_income_missing_for_allocation",
          type: "risk",
          status: "uafklaret",
          data: {
            required_field: "gross_income_total",
          },
        });
      }
      if (!taxResidenceDenmarkFact) {
        advarsler.push({
          key: "home_state_assumption_weak_without_tax_residence_fact",
          type: "risk",
          status: "uafklaret",
          data: {
            required_field: "tax_residence_denmark_fact",
          },
        });
      }
      if (!contractReceived) {
        advarsler.push({
          key: "employment_contract_evidence_unresolved",
          type: "risk",
          status: "uafklaret",
          data: {
            required_field: "employment_contract_received",
          },
        });
      }

      return {
        praemisser,
        vurderingstrin,
        uafklarede_sporgsmaal,
        advarsler,
        conclusion,
      };
    },
  };
}
