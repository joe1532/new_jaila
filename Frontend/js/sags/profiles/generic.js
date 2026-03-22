export function createGenericProfile(article, section) {
  const articleLabel = Number.isFinite(Number(article))
    ? `DBO artikel ${Number(article)}${Number.isFinite(Number(section)) ? `, stk. ${Number(section)}` : ""}`
    : "DBO (ikke præciseret)";
  const reason = Number.isFinite(Number(article))
    ? "Valgt artikel til foreløbig subsumption"
    : "Artikel skal afklares for sikker subsumption";
  return {
    profile_id: "employment_generic",
    requires_day_allocation: false,
    requires_employer_assessment: true,
    legal_sources: [
      { label: "KSL § 1, stk. 1, nr. 1", reason: "Mulig fuld dansk skattepligt" },
      { label: "SSL § 4", reason: "Globalindkomstprincip ved fuld skattepligt" },
      { label: articleLabel, reason },
    ],
    apply() {
      // Bevidst tom: generic-profil tilføjer kun basisreetskilder.
    },
  };
}
