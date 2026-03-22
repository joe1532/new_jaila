import { buildDecisionPackageFromSagsInput } from "./decisionPackageContract.js";

const SKATTEPLIGT_FACTOR_TITLES = {
  self_employed_business: "Selvstændig erhvervsvirksomhed",
  foreign_income: "Indkomst fra udlandet",
  foreign_real_estate: "Fast ejendom i udlandet",
  work_abroad_with_relief: "Lønindkomst for arbejde udført i udlandet med lempelse",
  special_tax_liability_conditions: "Særlige skattepligtsforhold",
  major_shareholder_status: "Hovedaktionærstatus",
  foreign_assets_liabilities_significant:
    "Aktiver eller passiver i udlandet af betydning for skatteansættelsen",
  cross_border_commuter_taxation: "Grænsegængerbeskatning",
};

const SELF_EMPLOYED_MODE_TITLES = {
  oplysningsskema: "Ikke omfattet af undtagelsen i § 2",
  undtagelse: "Selvstændig erhvervsvirksomhed med årsopgørelse efter undtagelsesreglen",
};

const FOREIGN_INCOME_TYPE_TITLES = {
  salary: "lønindkomst",
  pension: "pension",
  capital_income: "kapitalindkomst",
};

const FOREIGN_ASSETS_TYPE_TITLES = {
  bankkonti: "Bankkonti",
  værdipapirer: "Værdipapirer",
  gæld: "Gæld",
};

const FOREIGN_ASSETS_TYPE_DETAILS = {
  bankkonti: "bankkonti",
  værdipapirer: "værdipapirer",
  gæld: "gæld",
};

const SPECIAL_TAX_LIABILITY_MODE_TITLES = {
  shift_full_limited: "Skift mellem fuld og begrænset skattepligt",
  tax_resident_abroad: "Skattemæssigt hjemmehørende i udlandet",
  offset_income_year: "Forskudt indkomstår",
  duty_under_section_8_2: "Oplysningspligt efter skattekontrollovens § 8, stk. 2",
  request_information_schema: "Anmodning om oplysningsskema",
};

const SPECIAL_TAX_LIABILITY_MODE_DETAILS = {
  shift_full_limited: "skift mellem fuld og begrænset skattepligt",
  tax_resident_abroad: "skattemæssigt hjemmehørende i udlandet",
  offset_income_year: "forskudt indkomstår",
  duty_under_section_8_2: "oplysningspligt efter skattekontrollovens § 8, stk. 2",
  request_information_schema: "anmodning om oplysningsskema",
};

function normalizeIncomeYearsInput(rawValue) {
  const text = String(rawValue || "").trim();
  if (!text) {
    return "";
  }
  const normalizedSeparators = text
    .replace(/\bog\b/gi, ",")
    .replace(/[;/]+/g, ",")
    .replace(/\s+/g, " ");
  const yearMatches = normalizedSeparators.match(/\b(?:19|20)\d{2}\b/g) || [];
  if (!yearMatches.length) {
    return text;
  }
  const uniqueSortedYears = Array.from(new Set(yearMatches)).sort((a, b) => Number(a) - Number(b));
  return uniqueSortedYears.join(", ");
}

function formatDanishList(values) {
  const cleaned = (Array.isArray(values) ? values : [])
    .map((value) => String(value || "").trim())
    .filter((value) => value.length > 0);
  if (!cleaned.length) {
    return "";
  }
  if (cleaned.length === 1) {
    return cleaned[0];
  }
  if (cleaned.length === 2) {
    return `${cleaned[0]} og ${cleaned[1]}`;
  }
  return `${cleaned.slice(0, -1).join(", ")} og ${cleaned[cleaned.length - 1]}`;
}

function buildWorkCountriesFromFacts(facts) {
  const modes = Array.isArray(facts.workCountryModes)
    ? facts.workCountryModes.map((value) => String(value || "").trim()).filter((value) => value)
    : String(facts.workCountryMode || "").trim()
      ? [String(facts.workCountryMode || "").trim()]
      : [];
  const selectedModes = new Set(modes);
  const countries = [];
  if (selectedModes.has("danmark")) {
    countries.push("Danmark");
  }
  const customCountries = Array.isArray(facts.workCountryDenmarkFields)
    ? facts.workCountryDenmarkFields
    : [];
  const customChecked = Array.isArray(facts.workCountryCustomChecked)
    ? facts.workCountryCustomChecked
    : [];
  customCountries.forEach((value, idx) => {
    if (!Boolean(customChecked[idx])) return;
    const text = String(value || "").trim();
    if (!text) return;
    countries.push(text);
  });
  const seen = new Set();
  const deduped = [];
  countries.forEach((country) => {
    const key = country.toLowerCase();
    if (!key || seen.has(key)) return;
    seen.add(key);
    deduped.push(country);
  });
  return deduped;
}

function parseWorkDaysInteger(value) {
  const text = String(value || "").trim();
  if (!text || text.startsWith("-")) {
    return null;
  }
  const beforeDecimal = text.split(/[.,]/)[0] || "";
  const leadingDigitsMatch = beforeDecimal.match(/^\d+/);
  if (!leadingDigitsMatch) {
    return null;
  }
  const numeric = Number.parseInt(leadingDigitsMatch[0], 10);
  return Number.isFinite(numeric) ? numeric : null;
}

function formatWorkDaysPercent(days, totalDays) {
  if (!Number.isFinite(totalDays) || totalDays <= 0) {
    return "—";
  }
  const pct = (days / totalDays) * 100;
  return Number.isInteger(pct) ? `${pct} %` : `${pct.toFixed(1).replace(".", ",")} %`;
}

function getBeskatningsretResidenceCountryText(facts) {
  const mode = String(facts.residenceCountryMode || "").trim();
  if (mode === "danmark") return "Danmark";
  if (mode === "other") {
    const otherCountry = String(facts.residenceCountryOther || "").trim();
    return otherCountry ? otherCountry : "Andet (ikke angivet)";
  }
  return "";
}

function getBeskatningsretEmployerResidenceText(facts) {
  const mode = String(facts.employerResidenceMode || "").trim();
  if (mode === "danmark") return "Danmark";
  if (mode === "private_foreign") return "Privat udenlandsk arbejdsgiver";
  if (mode === "public_foreign") return "Offentlig udenlandsk arbejdsgiver";
  return "";
}

function buildBeskatningsretWorkdaysSummary(facts) {
  const countries = buildWorkCountriesFromFacts(facts);
  const daysMap = facts.workCountryDaysByCountry && typeof facts.workCountryDaysByCountry === "object"
    ? facts.workCountryDaysByCountry
    : {};
  const totalDays = countries.reduce((sum, country) => {
    const numeric = parseWorkDaysInteger(daysMap[country]);
    return Number.isFinite(numeric) ? sum + numeric : sum;
  }, 0);
  const lines = countries
    .map((country) => {
      const numeric = parseWorkDaysInteger(daysMap[country]);
      if (!Number.isFinite(numeric)) return "";
      return `${country}: ${numeric} (${formatWorkDaysPercent(numeric, totalDays)})`;
    })
    .filter((line) => line);
  return {
    countries,
    totalDays,
    summary: lines.join(" | "),
  };
}

function buildBeskatningsretFactsLines(facts) {
  const employerCountMode = String(facts.employerCountMode || "one").trim() || "one";
  const workdaySummary = buildBeskatningsretWorkdaysSummary(facts);
  return [
    ["Bopælsland", getBeskatningsretResidenceCountryText(facts)],
    ["Bopæl til rådighed i arbejdsland", facts.residenceAvailableInWorkCountry ? "Ja" : "Nej"],
    ["Skattemæssigt hjemsted/Danmark", facts.taxResidenceDenmarkFact],
    [
      "Har vi modtaget ansættelseskontrakt?",
      String(facts.employmentContractReceived || "").trim() === "ja"
        ? "Ja"
        : String(facts.employmentContractReceived || "").trim() === "nej"
          ? "Nej"
          : "",
    ],
    ["Kommentarer til ansættelseskontrakt", facts.foreignAssetsLiabilities],
    ["Arbejdsgiver hjemmehørende i", getBeskatningsretEmployerResidenceText(facts)],
    ["Antal arbejdsgivere", employerCountMode === "two" ? "To" : "En"],
    ["Navn på arbejdsgiver", facts.employerName],
    ["Navn på arbejdsgiver (nr. 2)", employerCountMode === "two" ? facts.employerName2 : ""],
    ["Land, hvor arbejdsgiver er hjemmehørende", facts.employerCountry],
    ["DBO-artikel for indkomsten", facts.incomeDboArticle],
    ["Lande, hvor der er udført arbejde", workdaySummary.countries.join(", ")],
    ["Arbejdsdage pr. land", workdaySummary.summary],
    ["Arbejdsdage i alt", workdaySummary.totalDays > 0 ? String(workdaySummary.totalDays) : ""],
    ["Indkomst/faktum", facts.foreignIncome],
    ["Tilføj kontekst til fakta", facts.notes],
  ]
    .map(([label, value]) => [label, String(value || "").trim()])
    .filter(([, value]) => value);
}

function buildSagsCaseFactsPayload(facts) {
  const safeFacts = facts && typeof facts === "object" ? facts : {};
  const incomeYears = normalizeIncomeYearsInput(safeFacts.incomeYears || "");
  const selectedFactors = Array.isArray(safeFacts.selectedFactors) ? safeFacts.selectedFactors : [];
  const factorDetails =
    safeFacts.factorDetails && typeof safeFacts.factorDetails === "object" ? safeFacts.factorDetails : {};
  const selectedTriggerId = selectedFactors.length ? String(selectedFactors[0]) : "";
  const foreignIncomeTypes = Array.isArray(safeFacts.foreignIncomeTypes) ? safeFacts.foreignIncomeTypes : [];
  const foreignIncomeDetail = formatDanishList(
    foreignIncomeTypes.map((typeId) => FOREIGN_INCOME_TYPE_TITLES[typeId] || ""),
  );
  const specialTaxLiabilityMode = String(safeFacts.specialTaxLiabilityMode || "").trim();
  const specialTaxLiabilityDetail = SPECIAL_TAX_LIABILITY_MODE_DETAILS[specialTaxLiabilityMode] || "";
  const foreignAssetsLiabilitiesType = String(safeFacts.foreignAssetsLiabilitiesType || "").trim();
  const foreignAssetsDetail = FOREIGN_ASSETS_TYPE_DETAILS[foreignAssetsLiabilitiesType] || "";
  const selectedTriggerDetail = selectedTriggerId
    ? selectedTriggerId === "foreign_income"
      ? foreignIncomeDetail
      : selectedTriggerId === "special_tax_liability_conditions"
        ? specialTaxLiabilityDetail
        : selectedTriggerId === "foreign_assets_liabilities_significant"
          ? foreignAssetsDetail
          : String(factorDetails[selectedTriggerId] || "").trim()
    : "";
  const selectedFactorTitles = selectedFactors
    .map((factorId) => {
      const baseTitle = SKATTEPLIGT_FACTOR_TITLES[factorId] || factorId;
      const detailText = factorId === "foreign_income"
        ? foreignIncomeDetail
        : factorId === "special_tax_liability_conditions"
          ? specialTaxLiabilityDetail
          : factorId === "foreign_assets_liabilities_significant"
            ? foreignAssetsDetail
            : String(factorDetails[factorId] || "").trim();
      return detailText ? `${baseTitle}: ${detailText}` : baseTitle;
    })
    .filter((value) => String(value || "").trim().length > 0);
  const residenceMode = String(safeFacts.residenceMode || "").trim();
  const residenceSinceYear = String(safeFacts.residenceSinceYear || "").trim();
  const residenceFact = (() => {
    if (residenceMode === "always") return "Da du altid har haft bopæl i Danmark";
    if (residenceMode === "since_year") {
      return residenceSinceYear ? `Da du har haft bopæl i Danmark siden ${residenceSinceYear}` : "";
    }
    return String(safeFacts.residenceFact || "").trim();
  })();
  return {
    income_years: incomeYears,
    foreign_income: selectedFactorTitles.join("; "),
    foreign_assets_liabilities: "",
    residence_fact: residenceFact,
    residence_mode: residenceMode,
    residence_since_year: residenceSinceYear,
    selected_factors: selectedFactors,
    selected_trigger: selectedTriggerId,
    selected_trigger_detail: selectedTriggerDetail,
    foreign_income_types: foreignIncomeTypes,
    foreign_assets_liabilities_type: foreignAssetsLiabilitiesType,
    special_tax_liability_mode: specialTaxLiabilityMode,
    self_employed_business_mode: String(safeFacts.selfEmployedMode || "").trim(),
    self_employed_business_detail: String(factorDetails.self_employed_business || "").trim(),
    foreign_income_detail: foreignIncomeDetail,
    major_shareholder_status_detail: String(factorDetails.major_shareholder_status || "").trim(),
    special_tax_liability_conditions_detail: specialTaxLiabilityDetail,
    foreign_assets_liabilities_detail: foreignAssetsDetail,
  };
}

function validateSkattepligtCaseFacts(caseFacts) {
  const missingRequiredFacts = [];
  if (!String(caseFacts.income_years || "").trim()) {
    missingRequiredFacts.push("Indkomstår");
  }
  if (!Array.isArray(caseFacts.selected_factors) || caseFacts.selected_factors.length !== 1) {
    missingRequiredFacts.push("Vælg præcis én trigger");
  }
  if (
    Array.isArray(caseFacts.selected_factors)
    && caseFacts.selected_factors.includes("self_employed_business")
    && !String(caseFacts.self_employed_business_mode || "").trim()
  ) {
    missingRequiredFacts.push("Vælg underkategori for selvstændig erhvervsvirksomhed");
  }
  if (
    Array.isArray(caseFacts.selected_factors)
    && caseFacts.selected_factors.includes("foreign_income")
    && (!Array.isArray(caseFacts.foreign_income_types) || caseFacts.foreign_income_types.length === 0)
  ) {
    missingRequiredFacts.push("Vælg mindst én type under indkomst fra udlandet");
  }
  if (
    Array.isArray(caseFacts.selected_factors)
    && caseFacts.selected_factors.includes("major_shareholder_status")
    && !String(caseFacts.major_shareholder_status_detail || "").trim()
  ) {
    missingRequiredFacts.push("Skriv navnet på selskabet");
  }
  if (
    Array.isArray(caseFacts.selected_factors)
    && caseFacts.selected_factors.includes("special_tax_liability_conditions")
    && !String(caseFacts.special_tax_liability_mode || "").trim()
  ) {
    missingRequiredFacts.push("Vælg underpunkt for særlige skattepligtsforhold");
  }
  if (
    Array.isArray(caseFacts.selected_factors)
    && caseFacts.selected_factors.includes("foreign_assets_liabilities_significant")
    && !String(caseFacts.foreign_assets_liabilities_type || "").trim()
  ) {
    missingRequiredFacts.push("Vælg formueforhold under aktiver/passiver i udlandet");
  }
  const isGrensegaenger = Array.isArray(caseFacts.selected_factors)
    && caseFacts.selected_factors.includes("cross_border_commuter_taxation");
  if (!isGrensegaenger) {
    const residenceMode = String(caseFacts.residence_mode || "").trim();
    if (!residenceMode) {
      missingRequiredFacts.push("Vælg bopælsfaktum");
    } else if (residenceMode === "since_year") {
      if (!/\b(?:19|20)\d{2}\b/.test(String(caseFacts.residence_since_year || "").trim())) {
        missingRequiredFacts.push("Angiv gyldigt årstal for bopæl i Danmark siden");
      }
    }
    if (!String(caseFacts.residence_fact || "").trim()) {
      missingRequiredFacts.push("Bopælsfaktum");
    }
  }
  return missingRequiredFacts;
}

export function buildSagsQuestionPayload({ activeSubtab, freeText, factsBySubtab, subtabLabels }) {
  const safeSubtab = String(activeSubtab || "").trim();
  const safeFactsBySubtab = factsBySubtab && typeof factsBySubtab === "object" ? factsBySubtab : {};
  const safeFreeText = String(freeText || "").trim();
  const labels = subtabLabels && typeof subtabLabels === "object" ? subtabLabels : {};
  const decisionPackage = buildDecisionPackageFromSagsInput({
    activeSubtab: safeSubtab,
    factsBySubtab: safeFactsBySubtab,
  });

  if (safeSubtab === "skattepligt_ligningsfrist") {
    const caseFacts = buildSagsCaseFactsPayload(safeFactsBySubtab[safeSubtab] || {});
    const missing = validateSkattepligtCaseFacts(caseFacts);
    if (missing.length) {
      return {
        ok: false,
        errorMessage: "Udfyld obligatoriske felter: " + missing.join(", "),
      };
    }
    const selectedFactors = Array.isArray(caseFacts.selected_factors) ? caseFacts.selected_factors : [];
    const selectedFactorId = selectedFactors.length === 1 ? String(selectedFactors[0] || "") : "";
    const selectedFactorText = (() => {
      if (selectedFactorId === "self_employed_business") {
        const modeId = String(caseFacts.self_employed_business_mode || "").trim();
        return SELF_EMPLOYED_MODE_TITLES[modeId] || "Selvstændig erhvervsvirksomhed";
      }
      if (selectedFactorId === "special_tax_liability_conditions") {
        const modeId = String(caseFacts.special_tax_liability_mode || "").trim();
        return SPECIAL_TAX_LIABILITY_MODE_TITLES[modeId] || "Særlige skattepligtsforhold";
      }
      if (selectedFactorId === "foreign_assets_liabilities_significant") {
        const typeId = String(caseFacts.foreign_assets_liabilities_type || "").trim();
        return FOREIGN_ASSETS_TYPE_TITLES[typeId] || "Aktiver eller passiver i udlandet";
      }
      return SKATTEPLIGT_FACTOR_TITLES[selectedFactorId] || String(caseFacts.foreign_income || "");
    })();
    const isGrensegaenger = Array.isArray(caseFacts.selected_factors)
      && caseFacts.selected_factors.includes("cross_border_commuter_taxation");
    const residenceLine = isGrensegaenger
      ? ""
      : "\n- Bopælsfaktum: " + String(caseFacts.residence_fact || "");
    return {
      ok: true,
      caseFacts,
      decisionPackage,
      generatedQuestion: "Foretag en samlet juridisk vurdering af, om borgeren er omfattet af kort eller ordinær ligningsfrist på baggrund af de oplyste fakta.",
      userMessage:
        "Fakta sendt til vurdering:\n- Indkomstår: "
        + String(caseFacts.income_years || "")
        + "\n- Valgt underpunkt: "
        + selectedFactorText
        + residenceLine,
    };
  }

  if (
    safeSubtab === "opgoerelse_indkomst"
    || safeSubtab === "beskatningsret_indkomst"
    || safeSubtab === "lempelse"
    || safeSubtab === "andet"
  ) {
    const facts = safeFactsBySubtab[safeSubtab] || {};
    const factsLines = safeSubtab === "beskatningsret_indkomst"
      ? buildBeskatningsretFactsLines(facts)
      : [
        ["Indkomstår", facts.incomeYears],
        ["Indkomst/faktum", facts.foreignIncome],
        ["Aktiver/passiver", facts.foreignAssetsLiabilities],
        ["Bopælsfaktum", facts.residenceFact],
        ["Noter", facts.notes],
      ]
        .map(([label, value]) => [label, String(value || "").trim()])
        .filter(([, value]) => value);
    if (!safeFreeText && !factsLines.length) {
      return {
        ok: false,
        errorMessage: "Skriv sagsbeskrivelse eller udfyld fakta før afsendelse.",
      };
    }
    return {
      ok: true,
      caseFacts: null,
      decisionPackage,
      generatedQuestion:
        `Undertab: ${labels[safeSubtab] || safeSubtab}\n`
        + `Sagsbeskrivelse: ${safeFreeText || "(ingen fritekst angivet)"}\n`
        + (factsLines.length
          ? `\nFakta:\n${factsLines.map(([label, value]) => `- ${label}: ${value}`).join("\n")}`
          : "")
        + "\n\nLav en juridisk vurdering med tydelig struktur og anvendte kilder/love.",
      userMessage: "Sagsspørgsmål sendt til vurdering" + (safeFreeText ? `:\n${safeFreeText}` : "."),
    };
  }

  return {
    ok: false,
    errorMessage: "Undertab er ikke aktiveret endnu.",
    systemMessage: "Denne undertab er ikke aktiveret endnu.",
  };
}
