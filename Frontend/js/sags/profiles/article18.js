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
    apply({ pkg, context }) {
      pkg.afledte_praemisser.push(
        "Artikel 18-profil: vurderingen fokuserer på pension/tilsvarende ydelser fremfor arbejdsdagsfordeling.",
      );
      if (Array.isArray(context.workdays) && context.workdays.length > 0) {
        pkg.advarsler.push(
          "Arbejdsdage er oplyst, men artikel 18-profil bruger normalt ikke dagsbaseret allokering.",
        );
      }
    },
  };
}
