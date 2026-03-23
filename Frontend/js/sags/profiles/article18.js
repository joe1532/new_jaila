export function createArticle18Profile() {
  return {
    profile_id: "employment_article_18",
    requires_day_allocation: false,
    requires_employer_assessment: false,
    legal_sources: [
      { label: "KSL § 1, stk. 1, nr. 1", reason: "Mulig fuld dansk skattepligt" },
      { label: "SSL § 4", reason: "Globalindkomstprincip ved fuld skattepligt" },
      { label: "DBO artikel 18", reason: "Valgt artikel for pension/tilsvarende ydelser" },
    ],
    apply({ context }) {
      const praemisser = [
        "Det lægges til grund, at vurderingen sker efter DBO artikel 18.",
      ];
      const advarsler = [];
      if (Array.isArray(context.workdays) && context.workdays.length > 0) {
        advarsler.push(
          "Arbejdsdage er oplyst, men artikel 18-profil bruger normalt ikke dagsbaseret allokering.",
        );
      }
      return {
        praemisser,
        advarsler,
        vurderingstrin: [],
        uafklarede_sporgsmaal: [],
        conclusion: {
          text: "Foreløbig vurdering efter artikel 18 forudsætter yderligere afklaring af indkomsttype og kildedata.",
          status: "foreløbig",
        },
      };
    },
  };
}
