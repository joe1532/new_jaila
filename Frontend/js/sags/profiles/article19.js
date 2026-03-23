export function createArticle19Profile() {
  return {
    profile_id: "employment_article_19",
    requires_day_allocation: false,
    requires_employer_assessment: true,
    legal_sources: [
      { label: "KSL § 1, stk. 1, nr. 1", reason: "Mulig fuld dansk skattepligt" },
      { label: "SSL § 4", reason: "Globalindkomstprincip ved fuld skattepligt" },
      { label: "DBO artikel 19", reason: "Valgt artikel for offentligt hverv/ydelse" },
    ],
    apply({ context }) {
      const praemisser = [
        "Det lægges til grund, at vurderingen sker efter DBO artikel 19.",
        "Arbejdsgivers offentlige/private karakter anses for central i vurderingen.",
      ];
      const uafklarede_sporgsmaal = [];
      const employerType = String(context.employerType || "").trim();
      if (!employerType || employerType === "private_foreign") {
        uafklarede_sporgsmaal.push(
          "For artikel 19 bør det afklares, om arbejdsgiver er offentlig myndighed/offentligt organ.",
        );
      }
      return {
        praemisser,
        uafklarede_sporgsmaal,
        vurderingstrin: [],
        advarsler: [],
        conclusion: {
          text: "Foreløbig vurdering efter artikel 19 kræver afklaring af arbejdsgivers offentlige status.",
          status: "foreløbig",
        },
      };
    },
  };
}
