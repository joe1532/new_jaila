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
    apply({ pkg, context }) {
      pkg.afledte_praemisser.push(
        "Artikel 19-profil: arbejdsgivers offentlige/private karakter er central for subsumptionen.",
      );
      const employerType = String(context.employerType || "").trim();
      if (!employerType || employerType === "private_foreign") {
        pkg.uafklarede_sporgsmaal.push(
          "For artikel 19 bør det afklares, om arbejdsgiver er offentlig myndighed/offentligt organ.",
        );
      }
    },
  };
}
