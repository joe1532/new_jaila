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
    apply({ pkg }) {
      pkg.afledte_praemisser.push(
        "Artikel 15-profil: vurderingen baseres på lønarbejde i tjenesteforhold med mulig geografisk fordeling.",
      );
    },
  };
}
