const SUBTAB_CONFIG = {
  skattepligt_ligningsfrist: {
    title: "Sagsbehandling - Skattepligt og ligningsfrist",
    placeholder: "Beskriv sagen om skattepligt/ligningsfrist...",
    functions: [
      "Vurder skattepligt",
      "Vurder ligningsfrist",
      "Opsummer risikopunkter",
    ],
    enabled: true,
  },
  opgoerelse_indkomst: {
    title: "Sagsbehandling - Opgørelse af indkomst",
    placeholder: "Beskriv opgørelsen af indkomst (dummy)...",
    functions: [
      "Beregn skattepligtig indkomst (dummy)",
      "Vurder fradragsposter (dummy)",
      "Lav opgørelsesnotat (dummy)",
    ],
    enabled: true,
  },
  beskatningsret_indkomst: {
    title: "Sagsbehandling - Beskatningsret til indkomst",
    placeholder: "Beskriv spørgsmålet om beskatningsret (dummy)...",
    functions: [],
    enabled: true,
  },
  lempelse: {
    title: "Sagsbehandling - Lempelse",
    placeholder: "Beskriv spørgsmålet om lempelse (dummy)...",
    functions: [
      "Vælg lempelsesmetode (dummy)",
      "Beregn credit/exemption (dummy)",
      "Dokumentationscheck (dummy)",
    ],
    enabled: true,
  },
  andet: {
    title: "Sagsbehandling - Andet",
    placeholder: "Beskriv anden sagsbehandling (dummy)...",
    functions: [
      "Generel juridisk vurdering (dummy)",
      "Klassificer problemstilling (dummy)",
      "Lav handlingsplan (dummy)",
    ],
    enabled: true,
  },
};

const LEGAL_SOURCE_CATEGORIES = [
  { id: "lovbekendtgoerelser", title: "Lovbekendtgørelser" },
  { id: "juridisk_vejledning", title: "Den juridiske vejledning" },
  { id: "bekendtgoerelser_cirkulaerer", title: "Bekendtgørelser og cirkulærer" },
  { id: "dobbeltbeskatningsoverenskomster", title: "Dobbeltbeskatningsoverenskomster" },
  { id: "afgoerelser_domme", title: "Afgørelser og domme" },
];

const LEGAL_INSTRUMENT_SEARCH_HINTS = [
  {
    instrumentPrefix: "norden_dbo",
    terms: [
      "norden",
      "nordisk",
      "nordiske",
      "nordiske dbo",
      "nordisk dbo",
      "norge",
      "sverige",
      "finland",
      "island",
      "færøerne",
      "faeroeerne",
    ],
  },
  {
    instrumentPrefix: "tyskland_dbo",
    terms: ["tyskland", "dk-de", "danmark tyskland", "tysk dbo", "dbo tyskland"],
  },
];

function normalizeSearchValue(value) {
  return String(value || "")
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function extractArticleNumberFromQuery(normalizedQuery) {
  const explicitMatch = normalizedQuery.match(/\b(?:art|artikel)\s*(\d{1,2})\b/);
  if (explicitMatch) {
    return Number(explicitMatch[1]);
  }
  const numberTokens = normalizedQuery
    .split(" ")
    .filter((token) => /^\d{1,2}$/.test(token))
    .map((token) => Number(token));
  return numberTokens.length === 1 ? numberTokens[0] : null;
}

function extractCompactArticleNumberFromHint(normalizedQuery, matchedTerm) {
  const term = String(matchedTerm || "").trim();
  if (!term) {
    return null;
  }
  const escapedTerm = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const compactPattern = new RegExp(`${escapedTerm}\\s*(\\d{1,2})\\b`);
  const match = normalizedQuery.match(compactPattern);
  if (!match) {
    return null;
  }
  return Number(match[1]);
}

function detectInstrumentHint(normalizedQuery) {
  if (!normalizedQuery) {
    return { instrumentPrefix: "", matchedTerm: "" };
  }
  let bestMatch = { instrumentPrefix: "", matchedTerm: "" };
  LEGAL_INSTRUMENT_SEARCH_HINTS.forEach((candidate) => {
    (candidate.terms || []).forEach((term) => {
      if (normalizedQuery.includes(term) && term.length > bestMatch.matchedTerm.length) {
        bestMatch = {
          instrumentPrefix: candidate.instrumentPrefix,
          matchedTerm: term,
        };
      }
    });
  });
  return bestMatch;
}

function buildResidualSearchTokens(normalizedQuery, matchedInstrumentTerm, articleNumber) {
  let residual = String(normalizedQuery || "");
  if (matchedInstrumentTerm) {
    residual = residual.replace(matchedInstrumentTerm, " ");
  }
  residual = residual.replace(/\bdbo\b/g, " ");
  residual = residual.replace(/\b(?:art|artikel)\s*\d{1,2}\b/g, " ");
  if (articleNumber != null) {
    if (matchedInstrumentTerm) {
      const escapedTerm = String(matchedInstrumentTerm).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      residual = residual.replace(new RegExp(`${escapedTerm}\\s*${articleNumber}\\b`, "g"), " ");
    }
    residual = residual.replace(new RegExp(`\\b${articleNumber}\\b`, "g"), " ");
  }
  return residual
    .split(" ")
    .map((token) => token.trim())
    .filter((token) => token.length >= 2);
}

const SKATTEPLIGT_FACTORS = [
  {
    id: "self_employed_business",
    title: "Selvstændig erhvervsvirksomhed",
    text: "personen driver selvstændig erhvervsvirksomhed, herunder enkeltmandsvirksomhed eller deltagelse i personselskab. Også mindre selvstændig virksomhed, der ellers kan modtage årsopgørelse, anses for ikke at have enkle økonomiske forhold.",
    refs: [
      "bekendtgørelse nr. 1302 af 14. november 2018 § 1, stk. 2, nr. 1 sammenholdt med bekendtgørelse nr. 1305 af 14. november 2018 § 2, stk. 1, nr. 2 og/eller bekendtgørelse nr. 49 af 24. januar 2025 § 2, stk. 1, nr. 2",
    ],
  },
  {
    id: "foreign_income",
    title: "Indkomst fra udlandet",
    text: "Personen modtager indkomst fra udlandet",
    refs: [
      "bekendtgørelse nr. 1302 af 14. november 2018 § 1, stk. 2, nr. 2 sammenholdt med bekendtgørelse nr. 1305 af 14. november 2018 § 2, stk. 1, nr. 2 og/eller bekendtgørelse nr. 49 af 24. januar 2025 § 2, stk. 1, nr. 2",
    ],
  },
  {
    id: "foreign_real_estate",
    title: "Fast ejendom i udlandet",
    text: "personen ejer fast ejendom uden for Danmark. Også i tilfælde hvor ejendommen alene kunne håndteres via årsopgørelse, anses forholdet stadig ikke for enkelt.",
    refs: [
      "bekendtgørelse nr. 1302 af 14. november 2018 § 1, stk. 2, nr. 3 sammenholdt med bekendtgørelse nr. 1305 af 14. november 2018 § 2, stk. 1, nr. 2 og/eller bekendtgørelse nr. 49 af 24. januar 2025 § 2, stk. 1, nr. 2",
    ],
  },
  {
    id: "work_abroad_with_relief",
    title: "Lønindkomst for arbejde udført i udlandet med lempelse",
    text: "personen har lønindkomst for arbejde udført uden for Danmark, hvor der gives nedslag i dansk skat efter en dobbeltbeskatningsoverenskomst eller efter danske regler.",
    refs: [
      "bekendtgørelse nr. 1302 af 14. november 2018 § 1, stk. 2, nr. 5 sammenholdt med bekendtgørelse nr. 1305 af 14. november 2018 § 2, stk. 1, nr. 1 og/eller bekendtgørelse nr. 49 af 24. januar 2025 § 2, stk. 1, nr. 1",
    ],
  },
  {
    id: "special_tax_liability_conditions",
    title: "Særlige skattepligtsforhold",
    text: "Vælg relevant særligt skattepligtsforhold",
    refs: [
      "bekendtgørelse nr. 1302 af 14. november 2018 § 1, stk. 3 sammenholdt med bekendtgørelse nr. 1305 af 14. november 2018 § 2, stk. 1, nr. 1 og/eller bekendtgørelse nr. 49 af 24. januar 2025 § 2, stk. 1, nr. 1",
    ],
  },
  {
    id: "major_shareholder_status",
    title: "Hovedaktionærstatus",
    text: "personen har status som hovedaktionær efter aktieavancebeskatningsloven.",
    requiresDetail: true,
    detailLabel: "Skriv navnet på selskabet",
    detailPlaceholder: "Angiv selskabsnavn",
    refs: [
      "bekendtgørelse nr. 1305 af 14. november 2018 § 2, stk. 1, nr. 3 og/eller",
      "bekendtgørelse nr. 49 af 24. januar 2025 § 2, stk. 1, nr. 3",
    ],
  },
  {
    id: "foreign_assets_liabilities_significant",
    title: "Aktiver eller passiver i udlandet af betydning for skatteansættelsen",
    text: "Vælg formueforhold i udlandet",
    refs: [
      "bekendtgørelse nr. 1305 af 14. november 2018 § 2, stk. 1, nr. 4 og/eller",
      "bekendtgørelse nr. 49 af 24. januar 2025 § 2, stk. 1, nr. 4",
    ],
  },
  {
    id: "cross_border_commuter_taxation",
    title: "Grænsegængerbeskatning",
    text: "personen har valgt at blive beskattet efter grænsegængerreglerne.",
    refs: [
      "bekendtgørelse nr. 1305 af 14. november 2018 § 2, stk. 1, nr. 5 og",
      "bekendtgørelse nr. 49 af 24. januar 2025 § 2, stk. 1, nr. 5",
    ],
  },
];

const SELF_EMPLOYED_SUBOPTIONS = [
  {
    id: "oplysningsskema",
    label: "Selvstændig erhvervsvirksomhed med oplysningsskema (hovedregel)",
    helpText:
      "Personen driver selvstændig erhvervsvirksomhed, fx enkeltmandsvirksomhed eller deltagelse i interessentskab, og skal derfor indgive oplysningsskema i stedet for at modtage en automatisk årsopgørelse.\n\n"
      + "Vælg denne mulighed, når virksomheden indgår som et almindeligt forhold i skatteansættelsen, og der skal afgives oplysninger om resultatet af virksomheden.\n\n"
      + "(bekendtgørelse nr. 1302 af 14. november 2018 § 1, stk. 2, nr. 1 sammenholdt med → bekendtgørelse nr. 1305 af 14. november 2018 § 2, stk. 1, nr. 1 og/eller bekendtgørelse nr. 49 af 24. januar 2025 § 2, stk. 1, nr. 1)",
  },
  {
    id: "undtagelse",
    label: "Selvstændig erhvervsvirksomhed med årsopgørelse efter undtagelsesreglen",
    helpText:
      "Personen har selvstændig erhvervsvirksomhed, men kan alligevel modtage en årsopgørelse efter undtagelsesreglen i bekendtgørelse nr. 1302 § 2.\n\n"
      + "Det kan fx være tilfældet, hvis virksomheden har begrænset betydning for skatteansættelsen, eller hvis Skatteforvaltningen allerede har de nødvendige oplysninger til at opgøre indkomsten.\n\n"
      + "(bekendtgørelse nr. 1302 af 14. november 2018 § 2 sammenholdt med bekendtgørelse nr. 1305 af 14. november 2018 § 2, stk. 1, nr. 2 og/eller bekendtgørelse nr. 49 af 24. januar 2025 § 2, stk. 1, nr. 2)",
  },
];

const FOREIGN_INCOME_SUBOPTIONS = [
  { id: "salary", label: "Lønindkomst" },
  { id: "pension", label: "Pension" },
  { id: "capital_income", label: "Kapitalindkomst" },
];

const FOREIGN_ASSETS_SUBOPTIONS = [
  { id: "bankkonti", label: "Bankkonti" },
  { id: "værdipapirer", label: "Værdipapirer" },
  { id: "gæld", label: "Gæld" },
];

const SPECIAL_TAX_LIABILITY_SUBOPTIONS = [
  {
    id: "shift_full_limited",
    label: "Skift mellem fuld og begrænset skattepligt",
    helpText:
      "personen har i løbet af indkomståret været både fuldt skattepligtig til Danmark og begrænset skattepligtig til Danmark.\n\n"
      + "(bekendtgørelse nr. 1302 af 14. november 2018 § 1, stk. 3, nr. 1\n"
      + "sammenholdt med bekendtgørelse nr. 1305 af 14. november 2018 § 2, stk. 1, nr. 1 og/eller bekendtgørelse nr. 49 af 24. januar 2025 § 2, stk. 1, nr. 1)",
  },
  {
    id: "tax_resident_abroad",
    label: "Skattemæssigt hjemmehørende i udlandet",
    helpText:
      "personen er fuldt skattepligtig til Danmark, men anses samtidig for skattemæssigt hjemmehørende i et andet land efter en dobbeltbeskatningsoverenskomst.\n\n"
      + "(bekendtgørelse nr. 1302 af 14. november 2018 § 1, stk. 3, nr. 2\n"
      + "sammenholdt med bekendtgørelse nr. 1305 af 14. november 2018 § 2, stk. 1, nr. 1 og/eller bekendtgørelse nr. 49 af 24. januar 2025 § 2, stk. 1, nr. 1)",
  },
  {
    id: "offset_income_year",
    label: "Forskudt indkomstår",
    helpText:
      "personen anvender et indkomstår, der ikke følger kalenderåret.\n\n"
      + "(bekendtgørelse nr. 1302 af 14. november 2018 § 1, stk. 3, nr. 3\n"
      + "sammenholdt med bekendtgørelse nr. 1305 af 14. november 2018 § 2, stk. 1, nr. 1 og/eller bekendtgørelse nr. 49 af 24. januar 2025 § 2, stk. 1, nr. 1)",
  },
  {
    id: "duty_under_section_8_2",
    label: "Oplysningspligt efter skattekontrollovens § 8, stk. 2",
    helpText:
      "personen er omfattet af reglerne i skattekontrollovens § 8, stk. 2 og skal derfor indsende oplysningsskema til Skatteforvaltningen.\n\n"
      + "(bekendtgørelse nr. 1302 af 14. november 2018 § 1, stk. 3, nr. 4\n"
      + "sammenholdt med bekendtgørelse nr. 1305 af 14. november 2018 § 2, stk. 1, nr. 1 og/eller bekendtgørelse nr. 49 af 24. januar 2025 § 2, stk. 1, nr. 1)",
  },
  {
    id: "request_information_schema",
    label: "Anmodning om oplysningsskema",
    helpText:
      "personen har selv anmodet Skatteforvaltningen om at få tilsendt et oplysningsskema i stedet for en årsopgørelse.\n\n"
      + "(bekendtgørelse nr. 1302 af 14. november 2018 § 1, stk. 3, nr. 5\n"
      + "sammenholdt med bekendtgørelse nr. 1305 af 14. november 2018 § 2, stk. 1, nr. 1 og/eller bekendtgørelse nr. 49 af 24. januar 2025 § 2, stk. 1, nr. 1)",
  },
];

const RESIDENCE_SUBOPTIONS = [
  {
    id: "always",
    label: "Borgeren har altid haft bopæl i Danmark",
  },
  {
    id: "since_year",
    label: "Borgeren har haft bopæl i Danmark siden",
  },
];

const FACTS_UI_CONFIG = {
  skattepligt_ligningsfrist: {
    panelTitle: "Fakta - Skattepligt og ligningsfrist",
    incomeYearsLabel: "Indkomstår",
    incomeYearsPlaceholder: "Fx 2022, 2023",
    factorSelectionLabel: "Vælg trigger (ét forhold)",
    foreignIncomeLabel: "Forhold, der kan begrunde ordinær ligningsfrist",
    foreignIncomePlaceholder: "Beskriv de faktiske forhold",
    foreignAssetsLiabilitiesLabel: "Aktiver/passiver i udlandet",
    foreignAssetsLiabilitiesPlaceholder: "Fx ejendom, bankkonti, værdipapirer, pension, gæld",
    residenceLabel: "Bopælsfaktum",
    residencePlaceholder: "Skriv kun selve bopælsfaktummet (ikke en fuld sætning)",
    notesLabel: "Retsgrundlag",
    notesPlaceholder: "Skriv eller rediger retsgrundlag",
    requiredFields: ["incomeYears", "selectedFactors", "residenceFact"],
  },
  opgoerelse_indkomst: {
    panelTitle: "Fakta - Opgørelse af indkomst",
    incomeYearsLabel: "Indkomstår / periode",
    incomeYearsPlaceholder: "Fx indkomstår 2024",
    foreignIncomeLabel: "Indkomsttyper",
    foreignIncomePlaceholder: "Fx løn, honorar, kapitalindkomst",
    foreignAssetsLiabilitiesLabel: "Dokumentation og beløb",
    foreignAssetsLiabilitiesPlaceholder: "Fx bilag, kontoudtog, opgørelser",
    residenceLabel: "Særlige forhold",
    residencePlaceholder: "Fx periodisering, fradrag, private udgifter",
    notesLabel: "Supplerende notat",
    notesPlaceholder: "Kort faktuel uddybning af opgørelsen",
  },
  beskatningsret_indkomst: {
    panelTitle: "Fakta - Beskatningsret til indkomst",
    showIncomeYears: false,
    foreignIncomeLabel: "Land(e) og indkomstkilde",
    foreignIncomePlaceholder: "Fx Danmark/Tyskland, lønindkomst",
    foreignAssetsLiabilitiesLabel: "Har vi modtaget ansættelseskontrakt?",
    foreignAssetsLiabilitiesPlaceholder: "Skriv relevante fakta",
    residenceLabel: "Skattemæssigt hjemsted (faktum)",
    residencePlaceholder: "Fx bopæl, familie, opholdsmønster",
    notesLabel: "Tilføj kontekst til fakta",
    notesPlaceholder: "Tilføj eventuelle bemærkninger til hvordan fakta skal fortolkes  og hvilke pointer der skal fremhæves i afsnittet",
  },
  lempelse: {
    panelTitle: "Fakta - Lempelse",
    incomeYearsLabel: "Indkomstår",
    incomeYearsPlaceholder: "Fx 2021-2024",
    foreignIncomeLabel: "Udenlandsk skat betalt",
    foreignIncomePlaceholder: "Fx beløb og land",
    foreignAssetsLiabilitiesLabel: "Type af lempelse (faktum)",
    foreignAssetsLiabilitiesPlaceholder: "Fx credit/exemption, dokumentationsgrundlag",
    residenceLabel: "Dansk skattepligt (faktum)",
    residencePlaceholder: "Kort faktum om fuld/begrænset skattepligt",
    notesLabel: "Supplerende oplysninger",
    notesPlaceholder: "Fx afgørelser, frister, bilag",
  },
  andet: {
    panelTitle: "Fakta - Andet",
    incomeYearsLabel: "Periode",
    incomeYearsPlaceholder: "Fx relevant periode/sagsnummer",
    foreignIncomeLabel: "Hovedtema",
    foreignIncomePlaceholder: "Kort beskrivelse af problemstillingen",
    foreignAssetsLiabilitiesLabel: "Nøglefaktum 1",
    foreignAssetsLiabilitiesPlaceholder: "Skriv centrale fakta",
    residenceLabel: "Nøglefaktum 2",
    residencePlaceholder: "Skriv centrale fakta",
    notesLabel: "Supplerende fakta",
    notesPlaceholder: "Ekstra detaljer til sagen",
  },
};

function withRequiredMarker(label, isRequired) {
  return isRequired ? `${label} *` : label;
}

function buildBeskatningsretBindingPreviewText(facts, contextList = []) {
  const legalContextTitles = (Array.isArray(contextList) ? contextList : [])
    .map((entry) => String(entry && entry.title ? entry.title : "").trim())
    .filter((value) => value);
  const lines = [
    String(facts.residenceCountryMode || "").trim()
      ? `Bopælsland: ${String(facts.residenceCountryMode || "").trim()}`
      : "",
    String(facts.employerResidenceMode || "").trim()
      ? `Arbejdsgiver hjemmehørende i: ${String(facts.employerResidenceMode || "").trim()}`
      : "",
    String(facts.employerCountry || "").trim()
      ? `Land, hvor arbejdsgiver er hjemmehørende: ${String(facts.employerCountry || "").trim()}`
      : "",
    String(facts.incomeDboArticle || "").trim()
      ? `DBO-artikel for indkomsten: ${String(facts.incomeDboArticle || "").trim()}`
      : "",
    String(facts.foreignAssetsLiabilities || "").trim()
      ? `Kommentarer til ansættelseskontrakt: ${String(facts.foreignAssetsLiabilities || "").trim()}`
      : "",
    String(facts.notes || "").trim()
      ? `Retskildebemærkninger: ${String(facts.notes || "").trim()}`
      : "",
    legalContextTitles.length ? `Valgte retskilder: ${legalContextTitles.join(" | ")}` : "",
  ].filter((line) => line);
  return lines.join("\n");
}

export function renderSagsbehandling(elements, state) {
  const activeCaseId = String(state.sagsbehandling.activeCaseId || "").trim();
  const hasCase = Boolean(activeCaseId);
  const activeCaseTitle = (() => {
    const cases = Array.isArray(state.sagsbehandling.cases) ? state.sagsbehandling.cases : [];
    const found = cases.find((entry) => String(entry.id || "") === activeCaseId);
    return found ? String(found.title || "Ny sag") : "";
  })();
  const activeSubtab = state.sagsbehandling.activeSubtab || "skattepligt_ligningsfrist";
  const cfg = SUBTAB_CONFIG[activeSubtab] || SUBTAB_CONFIG.skattepligt_ligningsfrist;
  const factsUiCfg =
    FACTS_UI_CONFIG[activeSubtab] || FACTS_UI_CONFIG.skattepligt_ligningsfrist;
  const requiredFields = new Set(factsUiCfg.requiredFields || []);
  const factsBySubtab = state.sagsbehandling.factsBySubtab || {};
  const contextBySubtab = state.sagsbehandling.contextBySubtab || {};
  const contextList = Array.isArray(contextBySubtab[activeSubtab])
    ? contextBySubtab[activeSubtab]
    : contextBySubtab[activeSubtab]
      ? [contextBySubtab[activeSubtab]]
      : [];
  const facts = {
    incomeYears: "",
    foreignIncome: "",
    foreignAssetsLiabilities: "",
    residenceFact: "",
    notes: "",
    selectedFactors: [],
    factorDetails: {},
    selfEmployedMode: "",
    foreignIncomeTypes: [],
    foreignAssetsLiabilitiesType: "",
    specialTaxLiabilityMode: "",
    residenceMode: "",
    residenceSinceYear: "",
    residenceCountryMode: "",
    residenceCountryOther: "",
    residenceAvailableInWorkCountry: false,
    taxResidenceDenmarkFact: "",
    employerResidenceMode: "",
    employerName: "",
    employerName2: "",
    employerCountMode: "one",
    employerCountry: "",
    incomeDboArticle: "",
    employmentContractReceived: "",
    workCountryModes: [],
    workCountryDenmarkFields: [],
    workCountryCustomChecked: [],
    workCountryDaysByCountry: {},
    ...(factsBySubtab[activeSubtab] || {}),
  };
  const messages = state.sagsbehandling.messages || [];
  const subtabOutputLocked = state.sagsbehandling.subtabOutputLocked || {};
  const isOutputLocked = Boolean(subtabOutputLocked[activeSubtab]);
  const factsLockedBySubtab = state.sagsbehandling.factsLockedBySubtab || {};
  const isFactsLocked = Boolean(factsLockedBySubtab[activeSubtab]);

  if (elements.sagsbehandlingTitle) {
    const caseLabel = activeCaseId ? ` [Sag: ${activeCaseTitle || activeCaseId}]` : " [Ingen aktiv sag]";
    elements.sagsbehandlingTitle.textContent = `${cfg.title}${caseLabel}`;
  }

  if (elements.sagsbehandlingInput) {
    if (elements.sagsbehandlingInput.value !== state.sagsbehandling.inputText) {
      elements.sagsbehandlingInput.value = state.sagsbehandling.inputText || "";
    }
    elements.sagsbehandlingInput.placeholder = cfg.placeholder;
  }

  if (elements.sagsbehandlingSendBtn) {
    const selectedFactorCount = Array.isArray(facts.selectedFactors) ? facts.selectedFactors.length : 0;
    const selectedFactorId = selectedFactorCount === 1 ? String(facts.selectedFactors[0] || "") : "";
    const factorDetails =
      facts.factorDetails && typeof facts.factorDetails === "object" ? facts.factorDetails : {};
    const hasRequiredDetailForSelectedFactor = (() => {
      if (!selectedFactorId) {
        return false;
      }
      const selectedFactorCfg = SKATTEPLIGT_FACTORS.find((item) => item.id === selectedFactorId);
      if (!selectedFactorCfg) {
        return false;
      }
      if (!selectedFactorCfg.requiresDetail) {
        return true;
      }
      const detailValue = String(factorDetails[selectedFactorId] || "").trim();
      return detailValue.length > 0;
    })();
    const hasSelfEmployedSubcategory =
      selectedFactorId !== "self_employed_business" || String(facts.selfEmployedMode || "").trim().length > 0;
    const hasForeignIncomeSubtype =
      selectedFactorId !== "foreign_income"
      || (Array.isArray(facts.foreignIncomeTypes) && facts.foreignIncomeTypes.length > 0);
    const hasSpecialTaxLiabilitySubtype =
      selectedFactorId !== "special_tax_liability_conditions"
      || String(facts.specialTaxLiabilityMode || "").trim().length > 0;
    const hasForeignAssetsSubtype =
      selectedFactorId !== "foreign_assets_liabilities_significant"
      || String(facts.foreignAssetsLiabilitiesType || "").trim().length > 0;
    const hasValidResidenceFact = (() => {
      if (activeSubtab !== "skattepligt_ligningsfrist") {
        return (facts.residenceFact || "").trim().length > 0;
      }
      if (selectedFactorId === "cross_border_commuter_taxation") {
        return true;
      }
      const mode = String(facts.residenceMode || "").trim();
      if (mode === "always") {
        return true;
      }
      if (mode === "since_year") {
        const sinceYearRaw = String(facts.residenceSinceYear || "").trim();
        return /\b(?:19|20)\d{2}\b/.test(sinceYearRaw);
      }
      return false;
    })();
    const requiredFactsComplete =
      activeSubtab !== "skattepligt_ligningsfrist" ||
      (facts.incomeYears || "").trim().length > 0 &&
        selectedFactorCount === 1 &&
        hasSelfEmployedSubcategory &&
        hasForeignIncomeSubtype &&
        hasForeignAssetsSubtype &&
        hasSpecialTaxLiabilitySubtype &&
        hasRequiredDetailForSelectedFactor &&
        hasValidResidenceFact;
    const contextReady =
      contextList.length === 0 || contextList.every((c) => Boolean(c.approved));
    elements.sagsbehandlingSendBtn.disabled = !cfg.enabled || !requiredFactsComplete || !hasCase;
    if (elements.sagsbehandlingSendBtn.disabled === false && !contextReady) {
      elements.sagsbehandlingSendBtn.disabled = true;
    }
    elements.sagsbehandlingSendBtn.textContent = cfg.enabled ? "Send" : "Send (kommer snart)";
  }
  if (elements.sagsbehandlingCopyAnswerBtn) {
    const hasAssistantAnswer = messages.some(
      (entry) => entry.role === "assistant" && String(entry.text || "").trim().length > 0,
    );
    elements.sagsbehandlingCopyAnswerBtn.disabled = !hasAssistantAnswer;
  }

  if (elements.sagsbehandlingLockBtn) {
    const hasAssistantAnswer = messages.some(
      (entry) => entry.role === "assistant" && String(entry.text || "").trim().length > 0,
    );
    elements.sagsbehandlingLockBtn.disabled = !hasAssistantAnswer;
    elements.sagsbehandlingLockBtn.textContent = isOutputLocked ? "Lås op" : "Lås";
    elements.sagsbehandlingLockBtn.setAttribute("data-sags-lock-action", isOutputLocked ? "unlock" : "lock");
  }

  if (elements.sagsContextPanel && elements.sagsContextList) {
    const hasContext = contextList.length > 0;
    elements.sagsContextPanel.classList.toggle("hidden", !hasContext);
    if (hasContext) {
      elements.sagsContextList.innerHTML = "";
      contextList.forEach((ctx) => {
        const item = document.createElement("div");
        item.className = "sags-context-item";
        item.setAttribute("data-context-log-id", ctx.logId || "");
        const header = document.createElement("div");
        header.className = "sags-context-item-header";
        const title = document.createElement("strong");
        title.className = "sags-context-item-title";
        title.textContent = ctx.title || "Uden titel";
        header.appendChild(title);
        const meta = document.createElement("span");
        meta.className = "sags-context-item-meta";
        meta.textContent = `${ctx.createdAt || ""}`;
        header.appendChild(meta);
        const removeBtn = document.createElement("button");
        removeBtn.type = "button";
        removeBtn.className = "button-secondary sags-facts-mini";
        removeBtn.textContent = "Fjern";
        removeBtn.setAttribute("data-action", "remove-sags-context");
        removeBtn.setAttribute("data-context-log-id", ctx.logId || "");
        header.appendChild(removeBtn);
        item.appendChild(header);
        const previewWrap = document.createElement("details");
        previewWrap.className = "sags-context-item-preview-wrap";
        const summary = document.createElement("summary");
        summary.textContent = "Vis kontekst";
        previewWrap.appendChild(summary);
        const preview = document.createElement("textarea");
        preview.className = "input sags-context-preview";
        preview.rows = 4;
        preview.readOnly = true;
        preview.value = ctx.previewText || "";
        previewWrap.appendChild(preview);
        item.appendChild(previewWrap);
        const approveLabel = document.createElement("label");
        approveLabel.className = "sags-context-approve";
        const approveCheck = document.createElement("input");
        approveCheck.type = "checkbox";
        approveCheck.checked = Boolean(ctx.approved);
        approveCheck.setAttribute("data-context-log-id", ctx.logId || "");
        approveLabel.appendChild(approveCheck);
        approveLabel.appendChild(
          document.createTextNode(" Jeg har gennemgået konteksten og vil bruge den"),
        );
        item.appendChild(approveLabel);
        elements.sagsContextList.appendChild(item);
      });
    }
  }

  if (elements.sagsbehandlingConversation) {
    const container = elements.sagsbehandlingConversation;
    container.innerHTML = "";
    if (!messages.length) {
      const msg = document.createElement("div");
      msg.className = "msg msg-system";
      msg.textContent = cfg.enabled
        ? "Klar til sagsbehandling. Udfyld fakta i 'Tilføj fakta' og tryk Send."
        : "Denne undertab er ikke aktiveret endnu.";
      container.appendChild(msg);
    } else {
      const lastAssistantIdx = (() => {
        for (let i = messages.length - 1; i >= 0; i -= 1) {
          if (messages[i].role === "assistant") return i;
        }
        return -1;
      })();
      messages.forEach((entry, idx) => {
        const msg = document.createElement("div");
        msg.classList.add("msg");
        if (entry.role === "user") {
          msg.classList.add("msg-user");
          msg.textContent = "Du: " + (entry.text || "");
        } else if (entry.role === "assistant") {
          msg.classList.add("msg-assistant");
          const isLastAssistant = idx === lastAssistantIdx;
          const isEditable = isLastAssistant && !isOutputLocked;
          if (isEditable) {
            const label = document.createElement("div");
            label.className = "msg-assistant-label";
            label.textContent = "JAILA:";
            msg.appendChild(label);
            const textarea = document.createElement("textarea");
            textarea.className = "input sags-output-editable msg-assistant-text";
            textarea.rows = 12;
            textarea.placeholder = "Rediger JAILA-svar her...";
            textarea.dataset.sagsSubtab = activeSubtab;
            textarea.value = entry.text || "";
            textarea.addEventListener("blur", () => {
              const text = String(textarea.value || "").trim();
              container.dispatchEvent(new CustomEvent("sags-output-edit", {
                detail: { subtab: activeSubtab, text },
                bubbles: true,
              }));
            });
            msg.appendChild(textarea);
          } else {
            const label = document.createElement("div");
            label.className = "msg-assistant-label";
            label.textContent = "JAILA:";
            msg.appendChild(label);
            const pre = document.createElement("pre");
            pre.className = "msg-assistant-text";
            pre.textContent = entry.text || "";
            msg.appendChild(pre);
          }
        } else {
          msg.classList.add("msg-system");
          msg.textContent = entry.text || "";
        }
        container.appendChild(msg);
      });
    }
    container.scrollTop = container.scrollHeight;
  }

  if (elements.sagsSubtabButtons && elements.sagsSubtabButtons.length) {
    elements.sagsSubtabButtons.forEach((btn) => {
      const isActive = btn.dataset.sagsSubtab === activeSubtab;
      btn.classList.toggle("sags-subtab-button-active", isActive);
    });
  }

  if (elements.sagsFunctionList) {
    const activeFunction = state.sagsbehandling.activeFunction || "";
    elements.sagsFunctionList.innerHTML = "";
    const functions = cfg.functions || [];
    functions.forEach((label) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "button-secondary sags-function-button";
      if (label === activeFunction) {
        btn.classList.add("sags-function-button-active");
      }
      btn.dataset.sagsFunction = label;
      btn.textContent = label;
      elements.sagsFunctionList.appendChild(btn);
    });
  }

  if (elements.sagsFactsToggleBtn) {
    elements.sagsFactsToggleBtn.textContent = state.sagsbehandling.factsPanelOpen
      ? "Skjul fakta"
      : "Tilføj fakta";
  }

  if (elements.sagsFactsPanel) {
    elements.sagsFactsPanel.classList.toggle("hidden", !state.sagsbehandling.factsPanelOpen);
  }
  if (elements.sagsLegalLibraryToggleBtn) {
    const isBeskatningsretSubtab = activeSubtab === "beskatningsret_indkomst";
    elements.sagsLegalLibraryToggleBtn.classList.toggle("hidden", !isBeskatningsretSubtab);
    if (isBeskatningsretSubtab) {
      elements.sagsLegalLibraryToggleBtn.textContent = state.sagsbehandling.legalLibraryPanelOpen
        ? "Skjul retskilder"
        : "Tilføj retskilder";
      elements.sagsLegalLibraryToggleBtn.disabled = !hasCase;
      elements.sagsLegalLibraryToggleBtn.title = hasCase
        ? ""
        : "Vælg eller opret først en sag for at tilføje retskilder.";
    }
  }
  if (elements.sagsLegalLibraryPanel) {
    const showLibraryPanel =
      activeSubtab === "beskatningsret_indkomst"
      && hasCase
      && Boolean(state.sagsbehandling.legalLibraryPanelOpen);
    elements.sagsLegalLibraryPanel.classList.toggle("hidden", !showLibraryPanel);
  }
  if (elements.sagsLegalLibrarySearch) {
    const searchValue = String(state.sagsbehandling.legalLibrarySearchQuery || "");
    if (elements.sagsLegalLibrarySearch.value !== searchValue) {
      elements.sagsLegalLibrarySearch.value = searchValue;
    }
  }
  if (elements.sagsLegalLibraryCategories && elements.sagsLegalLibrarySources) {
    const legalCatalog = Array.isArray(state.sagsbehandling.legalLibraryCatalog)
      ? state.sagsbehandling.legalLibraryCatalog
      : [];
    const libraryCategories = LEGAL_SOURCE_CATEGORIES;
    const queryRaw = String(state.sagsbehandling.legalLibrarySearchQuery || "").trim();
    const normalizedQuery = normalizeSearchValue(queryRaw);
    const instrumentHint = detectInstrumentHint(normalizedQuery);
    const articleNumber = extractArticleNumberFromQuery(normalizedQuery)
      ?? extractCompactArticleNumberFromHint(normalizedQuery, instrumentHint.matchedTerm);
    const residualTokens = buildResidualSearchTokens(
      normalizedQuery,
      instrumentHint.matchedTerm,
      articleNumber,
    );
    const activeCategoryBySubtab = state.sagsbehandling.legalLibraryActiveCategoryBySubtab || {};
    const activeDocumentBySubtab = state.sagsbehandling.legalLibraryActiveDocumentBySubtab || {};
    const activeVersionBySubtab = state.sagsbehandling.legalLibraryActiveVersionBySubtab || {};
    const previewBySubtab = state.sagsbehandling.legalLibraryPreviewSectionBySubtab || {};
    const activeCategory = String(activeCategoryBySubtab[activeSubtab] || "").trim();
    const activeDocumentId = String(activeDocumentBySubtab[activeSubtab] || "").trim();
    const activeVersionId = String(activeVersionBySubtab[activeSubtab] || "").trim();
    const previewSectionId = String(previewBySubtab[activeSubtab] || "").trim();
    elements.sagsLegalLibraryCategories.innerHTML = "";
    elements.sagsLegalLibrarySources.innerHTML = "";

    const matchesQuery = (doc, version, section) => {
      if (!normalizedQuery) {
        return true;
      }
      const docId = normalizeSearchValue(String(doc.id || ""));
      if (instrumentHint.instrumentPrefix && !docId.startsWith(instrumentHint.instrumentPrefix)) {
        return false;
      }
      if (articleNumber != null) {
        const sectionNumber = Number(String(section.sectionNumber || section.number || "").trim());
        const titleText = normalizeSearchValue(`${section.title} ${section.text || ""}`);
        const hasArticleNumber = (
          (Number.isFinite(sectionNumber) && sectionNumber === articleNumber)
          || titleText.includes(`artikel ${articleNumber}`)
          || titleText.includes(`art ${articleNumber}`)
        );
        if (!hasArticleNumber) {
          return false;
        }
      }
      if (!residualTokens.length) {
        return true;
      }
      const searchable = normalizeSearchValue(
        `${doc.title} ${(doc.tags || []).join(" ")} ${version.label} ${version.id} ${section.title} ${section.text || ""}`,
      );
      return residualTokens.every((token) => searchable.includes(token));
    };

    libraryCategories.forEach((category) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "button-secondary sags-legal-category-button";
      button.dataset.sagsLegalCategoryToggleId = category.id;
      if (activeCategory === category.id) {
        button.classList.add("sags-legal-category-button-active");
      }
      button.textContent = category.title;
      elements.sagsLegalLibraryCategories.appendChild(button);
    });

    if (!legalCatalog.length) {
      const empty = document.createElement("div");
      empty.className = "sags-legal-library-empty";
      empty.textContent = "Ingen retskilder fundet fra server endnu.";
      elements.sagsLegalLibrarySources.appendChild(empty);
    } else if (!activeCategory) {
      const empty = document.createElement("div");
      empty.className = "sags-legal-library-empty";
      empty.textContent = "Vælg en kategori for at se dokumenter.";
      elements.sagsLegalLibrarySources.appendChild(empty);
    } else {
      const visibleDocs = legalCatalog
        .filter((doc) => doc.category === activeCategory)
        .filter((doc) =>
          (Array.isArray(doc.versions) ? doc.versions : []).some((version) =>
            (Array.isArray(version.sections) ? version.sections : []).some((section) =>
              matchesQuery(doc, version, section),
            ),
          ),
        );
      if (!visibleDocs.length) {
        const empty = document.createElement("div");
        empty.className = "sags-legal-library-empty";
        empty.textContent = "Ingen dokumenter matcher søgningen i den valgte kategori.";
        elements.sagsLegalLibrarySources.appendChild(empty);
      } else {
        visibleDocs.forEach((doc) => {
          const docButton = document.createElement("button");
          docButton.type = "button";
          docButton.className = "button-secondary sags-legal-source-button";
          docButton.dataset.sagsLegalDocumentId = doc.id;
          if (activeDocumentId === doc.id) {
            docButton.classList.add("sags-legal-source-button-active");
          }
          docButton.textContent = doc.title;
          elements.sagsLegalLibrarySources.appendChild(docButton);

          if (activeDocumentId !== doc.id) {
            return;
          }
          const versions = (Array.isArray(doc.versions) ? doc.versions : [])
            .filter((version) =>
              (Array.isArray(version.sections) ? version.sections : []).some((section) =>
                matchesQuery(doc, version, section),
              ),
            )
            .sort((a, b) => String(b.validFrom || "").localeCompare(String(a.validFrom || "")));
          const hasStoredActiveVersion = versions.some((version) => version.id === activeVersionId);
          const effectiveActiveVersionId = hasStoredActiveVersion
            ? activeVersionId
            : (versions[0] ? versions[0].id : "");
          versions.forEach((version) => {
            const versionButton = document.createElement("button");
            versionButton.type = "button";
            versionButton.className = "button-secondary sags-legal-source-button sags-legal-version-button";
            versionButton.dataset.sagsLegalVersionId = version.id;
            if (effectiveActiveVersionId === version.id) {
              versionButton.classList.add("sags-legal-source-button-active");
            }
            const validTo = String(version.validTo || "").trim();
            const rangeLabel = validTo
              ? `${version.validFrom || "ukendt"} - ${validTo}`
              : `${version.validFrom || "ukendt"} - `;
            versionButton.textContent = `${version.label} (gyldig: ${rangeLabel})`;
            elements.sagsLegalLibrarySources.appendChild(versionButton);

            if (effectiveActiveVersionId !== version.id) {
              return;
            }
            const sections = (Array.isArray(version.sections) ? version.sections : [])
              .filter((section) => matchesQuery(doc, version, section));
            sections.forEach((section) => {
              const sectionRow = document.createElement("div");
              sectionRow.className = "sags-legal-section-row";

              const sectionButton = document.createElement("button");
              sectionButton.type = "button";
              sectionButton.className = "button-secondary sags-legal-source-button sags-legal-section-button";
              sectionButton.dataset.sagsLegalSourceId = `${version.id}:${section.id}`;
              sectionButton.dataset.sagsLegalSourceRef = String(section.sourceId || "").trim();
              if (previewSectionId === `${version.id}:${section.id}`) {
                sectionButton.classList.add("sags-legal-source-button-active");
              }
              sectionButton.textContent = section.title;
              sectionRow.appendChild(sectionButton);

              const addButton = document.createElement("button");
              addButton.type = "button";
              addButton.className = "button-secondary sags-facts-mini";
              addButton.textContent = "Tilføj";
              addButton.dataset.sagsLegalAddSectionId = section.id;
              addButton.dataset.sagsLegalAddSourceId = version.id;
              addButton.dataset.sagsLegalAddTitle =
                `${doc.title} - ${version.label} - ${section.title}`;
              addButton.dataset.sagsLegalAddText = section.text || "";
              sectionRow.appendChild(addButton);

              elements.sagsLegalLibrarySources.appendChild(sectionRow);
            });
          });
        });
      }
    }

    if (elements.sagsLegalPreviewTitle && elements.sagsLegalPreviewText) {
      let selectedSection = null;
      let selectedDocTitle = "";
      let selectedVersionLabel = "";
      let selectedSourceId = "";
      const sectionTextCache = state.sagsbehandling.legalLibrarySectionTextBySourceId || {};
      const loadingSourceId = String(state.sagsbehandling.legalLibraryPreviewLoadingSourceId || "").trim();
      const previewPageBySourceId = state.sagsbehandling.legalLibraryPreviewPageBySourceId || {};
      const previewTotalPagesBySourceId = state.sagsbehandling.legalLibraryPreviewTotalPagesBySourceId || {};
      legalCatalog.forEach((doc) => {
        (Array.isArray(doc.versions) ? doc.versions : []).forEach((version) => {
          (Array.isArray(version.sections) ? version.sections : []).forEach((section) => {
            const sectionKey = `${version.id}:${section.id}`;
            if (sectionKey === previewSectionId) {
              selectedSection = section;
              selectedDocTitle = doc.title;
              selectedVersionLabel = version.label;
              selectedSourceId = String(section.sourceId || "").trim();
            }
          });
        });
      });
      if (selectedSection) {
        elements.sagsLegalPreviewTitle.textContent =
          `${selectedDocTitle} - ${selectedVersionLabel} - ${selectedSection.title}`;
        const currentPage = Math.max(1, Number(previewPageBySourceId[selectedSourceId] || 1) || 1);
        const cacheKey = `${selectedSourceId}::${currentPage}`;
        const totalPages = Math.max(1, Number(previewTotalPagesBySourceId[selectedSourceId] || 1) || 1);
        if (selectedSourceId && loadingSourceId === selectedSourceId) {
          elements.sagsLegalPreviewText.textContent = "Indlæser indhold fra kilde...";
        } else if (selectedSourceId && String(sectionTextCache[cacheKey] || "").trim()) {
          elements.sagsLegalPreviewText.textContent = String(sectionTextCache[cacheKey] || "");
        } else {
          elements.sagsLegalPreviewText.textContent = selectedSection.text || "Ingen tekst fundet.";
        }
        if (
          elements.sagsLegalPreviewPager
          && elements.sagsLegalPrevPageBtn
          && elements.sagsLegalNextPageBtn
          && elements.sagsLegalPreviewPageInfo
        ) {
          elements.sagsLegalPreviewPager.classList.remove("hidden");
          elements.sagsLegalPreviewPageInfo.textContent = `Side ${currentPage}/${totalPages}`;
          elements.sagsLegalPrevPageBtn.disabled = currentPage <= 1 || loadingSourceId === selectedSourceId;
          elements.sagsLegalNextPageBtn.disabled = currentPage >= totalPages || loadingSourceId === selectedSourceId;
          elements.sagsLegalPrevPageBtn.dataset.sagsLegalSourceId = selectedSourceId;
          elements.sagsLegalNextPageBtn.dataset.sagsLegalSourceId = selectedSourceId;
          elements.sagsLegalPrevPageBtn.dataset.sagsLegalCurrentPage = String(currentPage);
          elements.sagsLegalNextPageBtn.dataset.sagsLegalCurrentPage = String(currentPage);
          elements.sagsLegalNextPageBtn.dataset.sagsLegalTotalPages = String(totalPages);
        }
      } else {
        elements.sagsLegalPreviewTitle.textContent = "Vælg en paragraf";
        elements.sagsLegalPreviewText.textContent =
          "Vælg kategori, dokument, version og derefter paragraf i højre side.";
        if (
          elements.sagsLegalPreviewPager
          && elements.sagsLegalPrevPageBtn
          && elements.sagsLegalNextPageBtn
          && elements.sagsLegalPreviewPageInfo
        ) {
          elements.sagsLegalPreviewPager.classList.add("hidden");
          elements.sagsLegalPreviewPageInfo.textContent = "Side 1/1";
          elements.sagsLegalPrevPageBtn.dataset.sagsLegalSourceId = "";
          elements.sagsLegalNextPageBtn.dataset.sagsLegalSourceId = "";
          elements.sagsLegalPrevPageBtn.disabled = true;
          elements.sagsLegalNextPageBtn.disabled = true;
        }
      }
      if (elements.sagsLegalOpenSourceBtn) {
        const showOpenSource = Boolean(selectedSection && selectedSourceId);
        elements.sagsLegalOpenSourceBtn.classList.toggle("hidden", !showOpenSource);
        if (showOpenSource) {
          elements.sagsLegalOpenSourceBtn.dataset.sagsLegalSourceId = selectedSourceId;
        } else {
          elements.sagsLegalOpenSourceBtn.dataset.sagsLegalSourceId = "";
        }
      }
      if (elements.sagsLegalAddSelectionBtn) {
        const showAddSelection = Boolean(selectedSection && selectedSourceId);
        elements.sagsLegalAddSelectionBtn.classList.toggle("hidden", !showAddSelection);
        if (showAddSelection) {
          elements.sagsLegalAddSelectionBtn.dataset.sagsLegalSourceId = selectedSourceId;
          elements.sagsLegalAddSelectionBtn.dataset.sagsLegalSectionId = String(selectedSection.id || "").trim();
          elements.sagsLegalAddSelectionBtn.dataset.sagsLegalSectionTitle = String(selectedSection.title || "").trim();
          elements.sagsLegalAddSelectionBtn.dataset.sagsLegalContextTitle =
            `${selectedDocTitle} - ${selectedVersionLabel} - ${selectedSection.title}`;
        } else {
          elements.sagsLegalAddSelectionBtn.dataset.sagsLegalSourceId = "";
          elements.sagsLegalAddSelectionBtn.dataset.sagsLegalSectionId = "";
          elements.sagsLegalAddSelectionBtn.dataset.sagsLegalSectionTitle = "";
          elements.sagsLegalAddSelectionBtn.dataset.sagsLegalContextTitle = "";
        }
      }
    }
  }

  if (elements.sagsFactsPanelTitle) {
    elements.sagsFactsPanelTitle.textContent = factsUiCfg.panelTitle;
  }
  const showIncomeYears = factsUiCfg.showIncomeYears !== false;
  if (elements.sagsFactsIncomeYearsLabel) {
    elements.sagsFactsIncomeYearsLabel.textContent = withRequiredMarker(
      factsUiCfg.incomeYearsLabel || "Indkomstår",
      requiredFields.has("incomeYears"),
    );
    elements.sagsFactsIncomeYearsLabel.classList.toggle("hidden", !showIncomeYears);
  }
  if (elements.sagsFactsFactorSelectionLabel) {
    elements.sagsFactsFactorSelectionLabel.textContent = withRequiredMarker(
      factsUiCfg.factorSelectionLabel || "Relevante forhold",
      requiredFields.has("selectedFactors"),
    );
    elements.sagsFactsFactorSelectionLabel.classList.toggle(
      "hidden",
      activeSubtab !== "skattepligt_ligningsfrist",
    );
  }
  if (elements.sagsFactsForeignIncomeLabel) {
    elements.sagsFactsForeignIncomeLabel.textContent = withRequiredMarker(
      factsUiCfg.foreignIncomeLabel,
      requiredFields.has("foreignIncome"),
    );
  }
  if (elements.sagsFactsForeignAssetsLiabilitiesLabel) {
    elements.sagsFactsForeignAssetsLiabilitiesLabel.textContent =
      factsUiCfg.foreignAssetsLiabilitiesLabel;
  }
  if (elements.sagsFactsResidenceLabel) {
    elements.sagsFactsResidenceLabel.textContent = withRequiredMarker(
      factsUiCfg.residenceLabel,
      requiredFields.has("residenceFact"),
    );
  }
  if (elements.sagsFactsNotesLabel) {
    elements.sagsFactsNotesLabel.textContent = factsUiCfg.notesLabel;
  }

  if (
    elements.sagsFactsIncomeYears &&
    elements.sagsFactsIncomeYears.value !== (facts.incomeYears ?? "")
  ) {
    elements.sagsFactsIncomeYears.value = facts.incomeYears ?? "";
  }
  if (elements.sagsFactsIncomeYears) {
    elements.sagsFactsIncomeYears.placeholder = factsUiCfg.incomeYearsPlaceholder || "";
    elements.sagsFactsIncomeYears.classList.toggle("hidden", !showIncomeYears);
  }
  if (
    elements.sagsFactsForeignIncome &&
    elements.sagsFactsForeignIncome.value !== (facts.foreignIncome ?? "")
  ) {
    elements.sagsFactsForeignIncome.value = facts.foreignIncome ?? "";
  }
  if (elements.sagsFactsForeignIncome) {
    elements.sagsFactsForeignIncome.placeholder = factsUiCfg.foreignIncomePlaceholder || "";
  }
  if (elements.sagsFactsBeskatningsretCountryBlock) {
    const isBeskatningsretSubtab = activeSubtab === "beskatningsret_indkomst";
    elements.sagsFactsBeskatningsretCountryBlock.classList.toggle("hidden", !isBeskatningsretSubtab);
    if (isBeskatningsretSubtab) {
      const selectedResidenceCountryMode = String(facts.residenceCountryMode || "").trim();
      const residenceCountryOther = String(facts.residenceCountryOther || "").trim();
      const residenceAvailableInWorkCountry = Boolean(facts.residenceAvailableInWorkCountry);
      const taxResidenceDenmarkFact = String(facts.taxResidenceDenmarkFact || "").trim();
      const selectedEmployerResidenceMode = String(facts.employerResidenceMode || "").trim();
      const employerName = String(facts.employerName || "").trim();
      const employerName2 = String(facts.employerName2 || "").trim();
      const employerCountMode = String(facts.employerCountMode || "one").trim() || "one";
      const employerCountry = String(facts.employerCountry || "").trim();
      const incomeDboArticle = String(facts.incomeDboArticle || "").trim();
      const selectedWorkCountryModes = Array.isArray(facts.workCountryModes)
        ? facts.workCountryModes.map((value) => String(value || "").trim()).filter((value) => value)
        : String(facts.workCountryMode || "").trim()
          ? [String(facts.workCountryMode || "").trim()]
          : [];
      const selectedWorkCountrySet = new Set(selectedWorkCountryModes);
      const workCountryDenmarkFields = Array.isArray(facts.workCountryDenmarkFields)
        ? facts.workCountryDenmarkFields
        : [];
      const workCountryCustomChecked = Array.isArray(facts.workCountryCustomChecked)
        ? facts.workCountryCustomChecked
        : [];
      const workCountryDaysByCountry =
        facts.workCountryDaysByCountry && typeof facts.workCountryDaysByCountry === "object"
          ? facts.workCountryDaysByCountry
          : {};
      elements.sagsFactsBeskatningsretCountryBlock.innerHTML = "";

      const residenceLabel = document.createElement("div");
      residenceLabel.className = "sags-facts-factor-detail-label";
      residenceLabel.textContent = "Bopælsland";
      elements.sagsFactsBeskatningsretCountryBlock.appendChild(residenceLabel);

      const residenceWrap = document.createElement("div");
      residenceWrap.className = "sags-facts-suboptions sags-beskatningsret-country-row";

      const dkRow = document.createElement("label");
      dkRow.className = "sags-facts-suboption-item";
      const dkRadio = document.createElement("input");
      dkRadio.type = "radio";
      dkRadio.name = "sagsBeskatningsretResidenceCountryMode";
      dkRadio.className = "sags-facts-suboption-radio";
      dkRadio.dataset.sagsResidenceCountryMode = "danmark";
      dkRadio.checked = selectedResidenceCountryMode === "danmark";
      dkRow.appendChild(dkRadio);
      const dkText = document.createElement("span");
      dkText.textContent = "Danmark";
      dkRow.appendChild(dkText);
      residenceWrap.appendChild(dkRow);

      const otherRow = document.createElement("label");
      otherRow.className = "sags-facts-suboption-item";
      const otherRadio = document.createElement("input");
      otherRadio.type = "radio";
      otherRadio.name = "sagsBeskatningsretResidenceCountryMode";
      otherRadio.className = "sags-facts-suboption-radio";
      otherRadio.dataset.sagsResidenceCountryMode = "other";
      otherRadio.checked = selectedResidenceCountryMode === "other";
      otherRow.appendChild(otherRadio);
      const otherText = document.createElement("span");
      otherText.textContent = "Andet (angiv land)";
      otherRow.appendChild(otherText);
      residenceWrap.appendChild(otherRow);

      const availableRow = document.createElement("label");
      availableRow.className = "sags-facts-suboption-item";
      const availableCheckbox = document.createElement("input");
      availableCheckbox.type = "checkbox";
      availableCheckbox.className = "sags-facts-suboption-radio";
      availableCheckbox.dataset.sagsResidenceAvailableInWorkCountry = "true";
      availableCheckbox.checked = residenceAvailableInWorkCountry;
      availableCheckbox.disabled = isFactsLocked;
      availableRow.appendChild(availableCheckbox);
      const availableText = document.createElement("span");
      availableText.textContent = "Bopæl til rådighed i arbejdsland";
      availableRow.appendChild(availableText);
      residenceWrap.appendChild(availableRow);

      const residenceOtherInput = document.createElement("input");
      residenceOtherInput.type = "text";
      residenceOtherInput.className = "input sags-facts-residence-inline-input";
      residenceOtherInput.placeholder = "Angiv bopælsland";
      residenceOtherInput.dataset.sagsResidenceCountryOther = "true";
      residenceOtherInput.value = residenceCountryOther;
      residenceOtherInput.disabled = selectedResidenceCountryMode !== "other" || isFactsLocked;
      residenceWrap.appendChild(residenceOtherInput);
      elements.sagsFactsBeskatningsretCountryBlock.appendChild(residenceWrap);

      const showTaxResidenceFact =
        residenceAvailableInWorkCountry
        && (selectedResidenceCountryMode === "danmark" || selectedResidenceCountryMode === "other");
      const taxResidenceLabel = document.createElement("div");
      taxResidenceLabel.className = "sags-facts-factor-detail-label";
      taxResidenceLabel.textContent = "Skattemæssigt hjemsted/Danmark";
      taxResidenceLabel.classList.toggle("hidden", !showTaxResidenceFact);
      elements.sagsFactsBeskatningsretCountryBlock.appendChild(taxResidenceLabel);

      const taxResidenceInput = document.createElement("textarea");
      taxResidenceInput.className = "input sags-facts-factor-detail-input";
      taxResidenceInput.rows = 2;
      taxResidenceInput.placeholder =
        "Skriv fakta der afgør, at skattemæssigt hjemsted falder til Danmark";
      taxResidenceInput.dataset.sagsTaxResidenceDenmarkFact = "true";
      taxResidenceInput.value = taxResidenceDenmarkFact;
      taxResidenceInput.disabled = isFactsLocked || !showTaxResidenceFact;
      taxResidenceInput.classList.toggle("hidden", !showTaxResidenceFact);
      elements.sagsFactsBeskatningsretCountryBlock.appendChild(taxResidenceInput);

      const employerTitle = document.createElement("div");
      employerTitle.className = "sags-facts-factor-detail-label";
      employerTitle.textContent = "Arbejdsgiver";
      elements.sagsFactsBeskatningsretCountryBlock.appendChild(employerTitle);

      const employerWrap = document.createElement("div");
      employerWrap.className = "sags-facts-suboptions sags-beskatningsret-employer-row";
      const employerQuestion = document.createElement("span");
      employerQuestion.className = "sags-beskatningsret-employer-question";
      employerQuestion.textContent = "Er arbejdsgiver hjemmehørende i";
      employerWrap.appendChild(employerQuestion);

      [
        { id: "danmark", label: "Danmark" },
        { id: "private_foreign", label: "Privat udenlandsk arbejdsgiver" },
        { id: "public_foreign", label: "Offentlig udenlandsk arbejdsgiver" },
      ].forEach((option) => {
        const optionRow = document.createElement("label");
        optionRow.className = "sags-facts-suboption-item";
        const optionRadio = document.createElement("input");
        optionRadio.type = "radio";
        optionRadio.name = "sagsBeskatningsretEmployerResidenceMode";
        optionRadio.className = "sags-facts-suboption-radio";
        optionRadio.dataset.sagsEmployerResidenceMode = option.id;
        optionRadio.checked = selectedEmployerResidenceMode === option.id;
        optionRow.appendChild(optionRadio);
        const optionText = document.createElement("span");
        optionText.textContent = option.label;
        optionRow.appendChild(optionText);
        employerWrap.appendChild(optionRow);
      });
      elements.sagsFactsBeskatningsretCountryBlock.appendChild(employerWrap);

      const employerNameLabel = document.createElement("div");
      employerNameLabel.className = "sags-facts-factor-detail-label";
      employerNameLabel.textContent = "Navn på arbejdsgiver";
      elements.sagsFactsBeskatningsretCountryBlock.appendChild(employerNameLabel);

      const employerCountWrap = document.createElement("div");
      employerCountWrap.className = "sags-facts-suboptions sags-beskatningsret-employer-row";
      [
        { id: "one", label: "En arbejdsgiver" },
        { id: "two", label: "To arbejdsgivere" },
      ].forEach((option) => {
        const optionRow = document.createElement("label");
        optionRow.className = "sags-facts-suboption-item";
        const optionRadio = document.createElement("input");
        optionRadio.type = "radio";
        optionRadio.name = "sagsBeskatningsretEmployerCountMode";
        optionRadio.className = "sags-facts-suboption-radio";
        optionRadio.dataset.sagsEmployerCountMode = option.id;
        optionRadio.checked = employerCountMode === option.id;
        optionRadio.disabled = isFactsLocked;
        optionRow.appendChild(optionRadio);
        const optionText = document.createElement("span");
        optionText.textContent = option.label;
        optionRow.appendChild(optionText);
        employerCountWrap.appendChild(optionRow);
      });
      elements.sagsFactsBeskatningsretCountryBlock.appendChild(employerCountWrap);

      const employerNameInput = document.createElement("input");
      employerNameInput.type = "text";
      employerNameInput.className = "input sags-facts-input";
      employerNameInput.placeholder = "Angiv arbejdsgivers navn";
      employerNameInput.dataset.sagsEmployerName = "true";
      employerNameInput.value = employerName;
      employerNameInput.disabled = isFactsLocked;
      elements.sagsFactsBeskatningsretCountryBlock.appendChild(employerNameInput);

      const employerNameInput2 = document.createElement("input");
      employerNameInput2.type = "text";
      employerNameInput2.className = "input sags-facts-input";
      employerNameInput2.placeholder = "Angiv arbejdsgivers navn (nr. 2)";
      employerNameInput2.dataset.sagsEmployerName2 = "true";
      employerNameInput2.value = employerName2;
      employerNameInput2.disabled = isFactsLocked || employerCountMode !== "two";
      elements.sagsFactsBeskatningsretCountryBlock.appendChild(employerNameInput2);

      const employerCountryLabel = document.createElement("div");
      employerCountryLabel.className = "sags-facts-factor-detail-label";
      employerCountryLabel.textContent = "Land, hvor din arbejdsgiver er hjemmehørende";
      elements.sagsFactsBeskatningsretCountryBlock.appendChild(employerCountryLabel);

      const employerCountryInput = document.createElement("input");
      employerCountryInput.type = "text";
      employerCountryInput.className = "input sags-facts-input";
      employerCountryInput.placeholder = "Angiv arbejdsgiverland";
      employerCountryInput.dataset.sagsEmployerCountry = "true";
      employerCountryInput.value = employerCountry;
      employerCountryInput.disabled = isFactsLocked;
      elements.sagsFactsBeskatningsretCountryBlock.appendChild(employerCountryInput);

      const incomeDboArticleLabel = document.createElement("div");
      incomeDboArticleLabel.className = "sags-facts-factor-detail-label";
      incomeDboArticleLabel.textContent = "Hvilken artikel i DBO'en er indkomsten omfattet af";
      elements.sagsFactsBeskatningsretCountryBlock.appendChild(incomeDboArticleLabel);

      const incomeDboArticleInput = document.createElement("input");
      incomeDboArticleInput.type = "text";
      incomeDboArticleInput.className = "input sags-facts-input";
      incomeDboArticleInput.placeholder = "Fx artikel 15";
      incomeDboArticleInput.dataset.sagsIncomeDboArticle = "true";
      incomeDboArticleInput.value = incomeDboArticle;
      incomeDboArticleInput.disabled = isFactsLocked;
      elements.sagsFactsBeskatningsretCountryBlock.appendChild(incomeDboArticleInput);

      const workCountryTitle = document.createElement("div");
      workCountryTitle.className = "sags-facts-factor-detail-label";
      workCountryTitle.textContent = "Lande, hvor der er udført arbejde";
      elements.sagsFactsBeskatningsretCountryBlock.appendChild(workCountryTitle);

      const workCountryWrap = document.createElement("div");
      workCountryWrap.className = "sags-facts-suboptions sags-beskatningsret-work-row";

      const dkWorkRow = document.createElement("label");
      dkWorkRow.className = "sags-facts-suboption-item";
      const dkWorkCheckbox = document.createElement("input");
      dkWorkCheckbox.type = "checkbox";
      dkWorkCheckbox.className = "sags-facts-suboption-radio";
      dkWorkCheckbox.dataset.sagsWorkCountryMode = "danmark";
      dkWorkCheckbox.checked = selectedWorkCountrySet.has("danmark");
      dkWorkRow.appendChild(dkWorkCheckbox);
      const dkWorkText = document.createElement("span");
      dkWorkText.textContent = "Danmark";
      dkWorkRow.appendChild(dkWorkText);
      workCountryWrap.appendChild(dkWorkRow);

      for (let idx = 0; idx < 6; idx += 1) {
        const customCheck = document.createElement("input");
        customCheck.type = "checkbox";
        customCheck.className = "sags-facts-suboption-radio";
        customCheck.dataset.sagsWorkCountryCustomCheckedIndex = String(idx);
        customCheck.checked = Boolean(workCountryCustomChecked[idx]);
        customCheck.disabled = isFactsLocked;
        workCountryWrap.appendChild(customCheck);

        const box = document.createElement("input");
        box.type = "text";
        box.className = "input sags-beskatningsret-work-small-input";
        box.placeholder = `Felt ${idx + 1}`;
        box.dataset.sagsWorkCountryDenmarkIndex = String(idx);
        box.value = String(workCountryDenmarkFields[idx] || "");
        box.disabled = isFactsLocked;
        workCountryWrap.appendChild(box);
      }
      elements.sagsFactsBeskatningsretCountryBlock.appendChild(workCountryWrap);

      const workCountries = (() => {
        const countries = [];
        if (selectedWorkCountrySet.has("danmark")) {
          countries.push("Danmark");
        }
        workCountryDenmarkFields
          .forEach((value, idx) => {
            if (!Boolean(workCountryCustomChecked[idx])) {
              return;
            }
            const text = String(value || "").trim();
            if (!text) {
              return;
            }
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
      })();

      const workDaysLabel = document.createElement("div");
      workDaysLabel.className = "sags-facts-factor-detail-label";
      workDaysLabel.textContent = "Arbejdsdage";
      elements.sagsFactsBeskatningsretCountryBlock.appendChild(workDaysLabel);

      if (!workCountries.length) {
        const workDaysHint = document.createElement("div");
        workDaysHint.className = "sags-beskatningsret-workdays-empty";
        workDaysHint.textContent = "Vælg eller angiv lande ovenfor for at udfylde arbejdsdage.";
        elements.sagsFactsBeskatningsretCountryBlock.appendChild(workDaysHint);
      } else {
        const tableWrap = document.createElement("div");
        tableWrap.className = "sags-beskatningsret-workdays-table-wrap";
        const table = document.createElement("table");
        table.className = "sags-beskatningsret-workdays-table";
        const thead = document.createElement("thead");
        thead.innerHTML = "<tr><th>Land</th><th>Arbejdsdage</th><th>%</th></tr>";
        table.appendChild(thead);
        const parseWorkDaysInteger = (value) => {
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
        };
        const totalDays = workCountries.reduce((sum, country) => {
          const numeric = parseWorkDaysInteger(workCountryDaysByCountry[country]);
          return Number.isFinite(numeric) ? sum + numeric : sum;
        }, 0);
        const tbody = document.createElement("tbody");
        workCountries.forEach((country) => {
          const row = document.createElement("tr");
          const countryCell = document.createElement("td");
          countryCell.textContent = country;
          row.appendChild(countryCell);
          const daysCell = document.createElement("td");
          const daysInput = document.createElement("input");
          daysInput.type = "number";
          daysInput.min = "0";
          daysInput.step = "1";
          daysInput.inputMode = "numeric";
          daysInput.className = "input sags-beskatningsret-workdays-input";
          daysInput.placeholder = "Angiv antal dage";
          const days = parseWorkDaysInteger(workCountryDaysByCountry[country]);
          daysInput.value = Number.isFinite(days) ? String(days) : "";
          daysInput.dataset.sagsWorkCountryDaysCountry = country;
          daysInput.disabled = isFactsLocked;
          daysCell.appendChild(daysInput);
          row.appendChild(daysCell);
          const pctCell = document.createElement("td");
          const pct = totalDays > 0 && Number.isFinite(days) ? (days / totalDays) * 100 : 0;
          pctCell.textContent = totalDays > 0
            ? (Number.isInteger(pct) ? `${pct} %` : `${pct.toFixed(1).replace(".", ",")} %`)
            : "—";
          pctCell.className = "sags-beskatningsret-workdays-pct";
          pctCell.dataset.sagsWorkCountryPctCountry = country;
          row.appendChild(pctCell);
          tbody.appendChild(row);
        });
        const totalDisplay = Number.isInteger(totalDays)
          ? String(totalDays)
          : totalDays.toFixed(2).replace(/\.00$/, "").replace(/(\.\d)0$/, "$1");
        const totalRow = document.createElement("tr");
        totalRow.className = "sags-beskatningsret-workdays-total-row";
        const totalLabelCell = document.createElement("td");
        totalLabelCell.textContent = "I alt";
        totalRow.appendChild(totalLabelCell);
        const totalValueCell = document.createElement("td");
        const totalInput = document.createElement("input");
        totalInput.type = "text";
        totalInput.className = "input sags-beskatningsret-workdays-input";
        totalInput.value = totalDisplay;
        totalInput.dataset.sagsWorkDaysTotal = "true";
        totalInput.readOnly = true;
        totalInput.disabled = true;
        totalValueCell.appendChild(totalInput);
        totalRow.appendChild(totalValueCell);
        const totalPctCell = document.createElement("td");
        totalPctCell.textContent = totalDays > 0 ? "100 %" : "—";
        totalPctCell.className = "sags-beskatningsret-workdays-pct";
        totalPctCell.dataset.sagsWorkDaysPctTotal = "true";
        totalRow.appendChild(totalPctCell);
        tbody.appendChild(totalRow);
        table.appendChild(tbody);
        tableWrap.appendChild(table);
        elements.sagsFactsBeskatningsretCountryBlock.appendChild(tableWrap);
      }

      const bindingPreview = buildBeskatningsretBindingPreviewText(facts, contextList);
      if (bindingPreview) {
        const bindingLabel = document.createElement("div");
        bindingLabel.className = "sags-facts-factor-detail-label";
        bindingLabel.textContent = "Oversigt over valgte oplysninger";
        elements.sagsFactsBeskatningsretCountryBlock.appendChild(bindingLabel);

        const bindingPreviewNode = document.createElement("textarea");
        bindingPreviewNode.className = "input sags-facts-factor-detail-input";
        bindingPreviewNode.rows = 5;
        bindingPreviewNode.readOnly = true;
        bindingPreviewNode.value = bindingPreview;
        elements.sagsFactsBeskatningsretCountryBlock.appendChild(bindingPreviewNode);
      }
    } else {
      elements.sagsFactsBeskatningsretCountryBlock.innerHTML = "";
    }
  }
  if (
    elements.sagsFactsForeignAssetsLiabilities &&
    elements.sagsFactsForeignAssetsLiabilities.value !== (facts.foreignAssetsLiabilities ?? "")
  ) {
    elements.sagsFactsForeignAssetsLiabilities.value = facts.foreignAssetsLiabilities ?? "";
  }
  if (elements.sagsFactsForeignAssetsLiabilities) {
    elements.sagsFactsForeignAssetsLiabilities.placeholder =
      factsUiCfg.foreignAssetsLiabilitiesPlaceholder || "";
    elements.sagsFactsForeignAssetsLiabilities.disabled = isFactsLocked;
  }
  const contractOptionsNode = document.getElementById("sagsFactsEmploymentContractOptions");
  if (activeSubtab === "beskatningsret_indkomst" && elements.sagsFactsForeignAssetsLiabilities) {
    const selectedEmploymentContract = String(facts.employmentContractReceived || "").trim();
    const optionsWrap = contractOptionsNode instanceof HTMLElement
      ? contractOptionsNode
      : document.createElement("div");
    optionsWrap.id = "sagsFactsEmploymentContractOptions";
    optionsWrap.className = "sags-facts-suboptions sags-beskatningsret-employer-row";
    optionsWrap.innerHTML = "";
    [
      { id: "ja", label: "Ja" },
      { id: "nej", label: "Nej" },
    ].forEach((option) => {
      const optionRow = document.createElement("label");
      optionRow.className = "sags-facts-suboption-item";
      const optionRadio = document.createElement("input");
      optionRadio.type = "radio";
      optionRadio.name = "sagsEmploymentContractReceived";
      optionRadio.className = "sags-facts-suboption-radio";
      optionRadio.dataset.sagsEmploymentContractReceived = option.id;
      optionRadio.checked = selectedEmploymentContract === option.id;
      optionRadio.disabled = isFactsLocked;
      optionRow.appendChild(optionRadio);
      const optionText = document.createElement("span");
      optionText.textContent = option.label;
      optionRow.appendChild(optionText);
      optionsWrap.appendChild(optionRow);
    });
    const parentNode = elements.sagsFactsForeignAssetsLiabilities.parentElement;
    if (parentNode) {
      parentNode.insertBefore(optionsWrap, elements.sagsFactsForeignAssetsLiabilities);
    }
  } else if (contractOptionsNode instanceof HTMLElement) {
    contractOptionsNode.remove();
  }

  if (elements.sagsFactsFactorChecklist) {
    const isSkattepligtSubtab = activeSubtab === "skattepligt_ligningsfrist";
    elements.sagsFactsFactorChecklist.classList.toggle("hidden", !isSkattepligtSubtab);
    if (isSkattepligtSubtab) {
      const selectedSet = new Set(
        Array.isArray(facts.selectedFactors) ? facts.selectedFactors : [],
      );
      elements.sagsFactsFactorChecklist.innerHTML = "";
      SKATTEPLIGT_FACTORS.forEach((factor) => {
        const row = document.createElement("div");
        row.className = "sags-facts-factor-item";

        const checkbox = document.createElement("input");
        checkbox.type = "radio";
        checkbox.name = "sagsSkattepligtFactor";
        checkbox.className = "sags-facts-factor-checkbox";
        checkbox.dataset.sagsFactorId = factor.id;
        checkbox.id = `sagsFactor_${factor.id}`;
        checkbox.checked = selectedSet.has(factor.id);
        row.appendChild(checkbox);

        const content = document.createElement("div");
        content.className = "sags-facts-factor-content";

        const title = document.createElement("label");
        title.className = "sags-facts-factor-title";
        title.htmlFor = checkbox.id;
        title.textContent = factor.title;
        content.appendChild(title);

        const text = document.createElement("div");
        text.className = "sags-facts-factor-text";
        text.innerHTML = `<em>${factor.text}<br/>(${factor.refs.join("<br/>")})</em>`;
        content.appendChild(text);

        if (factor.id === "self_employed_business") {
          const suboptionsLabel = document.createElement("div");
          suboptionsLabel.className = "sags-facts-factor-detail-label";
          suboptionsLabel.textContent = "Vælg underkategori";
          content.appendChild(suboptionsLabel);

          const suboptionsWrap = document.createElement("div");
          suboptionsWrap.className = "sags-facts-suboptions";
          const rawSelectedMode = String(facts.selfEmployedMode || "").trim();
          const selectedMode =
            rawSelectedMode === "not_covered_by_section_2"
              ? "oplysningsskema"
              : rawSelectedMode === "with_annual_statement_exception_rule"
                ? "undtagelse"
                : rawSelectedMode;
          SELF_EMPLOYED_SUBOPTIONS.forEach((option) => {
            const optionRow = document.createElement("label");
            optionRow.className = "sags-facts-suboption-item";

            const optionRadio = document.createElement("input");
            optionRadio.type = "radio";
            optionRadio.name = "sagsSelfEmployedMode";
            optionRadio.className = "sags-facts-suboption-radio";
            optionRadio.dataset.sagsSelfEmployedMode = option.id;
            optionRadio.checked = selectedMode === option.id;
            optionRadio.disabled = !checkbox.checked;
            optionRow.appendChild(optionRadio);

            const optionText = document.createElement("span");
            optionText.textContent = option.label;
            optionRow.appendChild(optionText);

            if (option.helpText) {
              const helpIcon = document.createElement("span");
              helpIcon.className = "sags-help-icon";
              helpIcon.textContent = "?";
              helpIcon.dataset.tooltip = option.helpText;
              helpIcon.tabIndex = 0;
              helpIcon.setAttribute("role", "note");
              helpIcon.setAttribute("aria-label", option.helpText);
              optionRow.appendChild(helpIcon);
            }

            suboptionsWrap.appendChild(optionRow);
          });
          content.appendChild(suboptionsWrap);
        }

        if (factor.id === "foreign_income") {
          const suboptionsLabel = document.createElement("div");
          suboptionsLabel.className = "sags-facts-factor-detail-label";
          suboptionsLabel.textContent = "Vælg indkomsttype";
          content.appendChild(suboptionsLabel);

          const selectedTypeId = Array.isArray(facts.foreignIncomeTypes)
            ? String(facts.foreignIncomeTypes[0] || "")
            : "";
          const suboptionsWrap = document.createElement("div");
          suboptionsWrap.className = "sags-facts-suboptions";
          FOREIGN_INCOME_SUBOPTIONS.forEach((option) => {
            const optionRow = document.createElement("label");
            optionRow.className = "sags-facts-suboption-item";

            const optionRadio = document.createElement("input");
            optionRadio.type = "radio";
            optionRadio.name = "sagsForeignIncomeType";
            optionRadio.className = "sags-facts-suboption-radio";
            optionRadio.dataset.sagsForeignIncomeType = option.id;
            optionRadio.checked = selectedTypeId === option.id;
            optionRadio.disabled = !checkbox.checked;
            optionRow.appendChild(optionRadio);

            const optionText = document.createElement("span");
            optionText.textContent = option.label;
            optionRow.appendChild(optionText);

            suboptionsWrap.appendChild(optionRow);
          });
          content.appendChild(suboptionsWrap);
        }

        if (factor.id === "special_tax_liability_conditions") {
          const suboptionsLabel = document.createElement("div");
          suboptionsLabel.className = "sags-facts-factor-detail-label";
          suboptionsLabel.textContent = "Vælg underpunkt";
          content.appendChild(suboptionsLabel);

          const selectedMode = String(facts.specialTaxLiabilityMode || "").trim();
          const suboptionsWrap = document.createElement("div");
          suboptionsWrap.className = "sags-facts-suboptions";
          SPECIAL_TAX_LIABILITY_SUBOPTIONS.forEach((option) => {
            const optionRow = document.createElement("label");
            optionRow.className = "sags-facts-suboption-item";

            const optionRadio = document.createElement("input");
            optionRadio.type = "radio";
            optionRadio.name = "sagsSpecialTaxLiabilityMode";
            optionRadio.className = "sags-facts-suboption-radio";
            optionRadio.dataset.sagsSpecialTaxLiabilityMode = option.id;
            optionRadio.checked = selectedMode === option.id;
            optionRadio.disabled = !checkbox.checked;
            optionRow.appendChild(optionRadio);

            const optionText = document.createElement("span");
            optionText.textContent = option.label;
            optionRow.appendChild(optionText);

            if (option.helpText) {
              const helpIcon = document.createElement("span");
              helpIcon.className = "sags-help-icon";
              helpIcon.textContent = "?";
              helpIcon.dataset.tooltip = option.helpText;
              helpIcon.tabIndex = 0;
              helpIcon.setAttribute("role", "note");
              helpIcon.setAttribute("aria-label", option.helpText);
              optionRow.appendChild(helpIcon);
            }

            suboptionsWrap.appendChild(optionRow);
          });
          content.appendChild(suboptionsWrap);
        }

        if (factor.id === "foreign_assets_liabilities_significant") {
          const suboptionsLabel = document.createElement("div");
          suboptionsLabel.className = "sags-facts-factor-detail-label";
          suboptionsLabel.textContent = "Vælg formueforhold";
          content.appendChild(suboptionsLabel);

          const selectedTypeId = String(facts.foreignAssetsLiabilitiesType || "").trim();
          const suboptionsWrap = document.createElement("div");
          suboptionsWrap.className = "sags-facts-suboptions";
          FOREIGN_ASSETS_SUBOPTIONS.forEach((option) => {
            const optionRow = document.createElement("label");
            optionRow.className = "sags-facts-suboption-item";

            const optionRadio = document.createElement("input");
            optionRadio.type = "radio";
            optionRadio.name = "sagsForeignAssetsType";
            optionRadio.className = "sags-facts-suboption-radio";
            optionRadio.dataset.sagsForeignAssetsType = option.id;
            optionRadio.checked = selectedTypeId === option.id;
            optionRadio.disabled = !checkbox.checked;
            optionRow.appendChild(optionRadio);

            const optionText = document.createElement("span");
            optionText.textContent = option.label;
            optionRow.appendChild(optionText);

            suboptionsWrap.appendChild(optionRow);
          });
          content.appendChild(suboptionsWrap);
        }

        if (factor.requiresDetail) {
          const detailLabel = document.createElement("div");
          detailLabel.className = "sags-facts-factor-detail-label";
          detailLabel.textContent = `${factor.detailLabel || "Specificér forhold"} *`;
          content.appendChild(detailLabel);

          const factorDetails =
            facts.factorDetails && typeof facts.factorDetails === "object" ? facts.factorDetails : {};
          const detailValue = String(factorDetails[factor.id] || "");
          const detailInput = document.createElement("textarea");
          detailInput.className = "input sags-facts-factor-detail-input";
          detailInput.rows = 2;
          detailInput.placeholder = factor.detailPlaceholder || "";
          detailInput.dataset.sagsFactorDetailId = factor.id;
          detailInput.disabled = !checkbox.checked;
          detailInput.value = detailValue;
          content.appendChild(detailInput);
        }

        row.appendChild(content);
        elements.sagsFactsFactorChecklist.appendChild(row);
      });
    } else {
      elements.sagsFactsFactorChecklist.innerHTML = "";
    }
  }

  const hideLegacyFields = activeSubtab === "skattepligt_ligningsfrist";
  if (elements.sagsFactsForeignIncomeLabel) {
    elements.sagsFactsForeignIncomeLabel.classList.toggle("hidden", hideLegacyFields);
  }
  if (elements.sagsFactsForeignIncome) {
    const hideForeignIncomeInput =
      hideLegacyFields || activeSubtab === "beskatningsret_indkomst";
    elements.sagsFactsForeignIncome.classList.toggle("hidden", hideForeignIncomeInput);
  }
  if (elements.sagsFactsForeignAssetsLiabilitiesLabel) {
    elements.sagsFactsForeignAssetsLiabilitiesLabel.classList.toggle("hidden", hideLegacyFields);
  }
  if (elements.sagsFactsForeignAssetsLiabilities) {
    elements.sagsFactsForeignAssetsLiabilities.classList.toggle("hidden", hideLegacyFields);
  }
  if (elements.sagsFactsResidenceOptions) {
    const isSkattepligtSubtab = activeSubtab === "skattepligt_ligningsfrist";
    const selectedFactorId =
      Array.isArray(facts.selectedFactors) && facts.selectedFactors.length === 1
        ? String(facts.selectedFactors[0] || "")
        : "";
    const isGrensegaenger = selectedFactorId === "cross_border_commuter_taxation";
    elements.sagsFactsResidenceOptions.classList.toggle("hidden", !isSkattepligtSubtab);
    elements.sagsFactsResidenceOptions.classList.toggle("sags-facts-residence-disabled", isGrensegaenger);
    if (isSkattepligtSubtab) {
      elements.sagsFactsResidenceOptions.innerHTML = "";
      const selectedResidenceMode = String(facts.residenceMode || "").trim();
      RESIDENCE_SUBOPTIONS.forEach((option) => {
        const optionRow = document.createElement("label");
        optionRow.className = "sags-facts-suboption-item sags-facts-residence-suboption";

        const optionRadio = document.createElement("input");
        optionRadio.type = "radio";
        optionRadio.name = "sagsResidenceMode";
        optionRadio.className = "sags-facts-suboption-radio";
        optionRadio.dataset.sagsResidenceMode = option.id;
        optionRadio.checked = selectedResidenceMode === option.id;
        optionRadio.disabled = isGrensegaenger;
        optionRow.appendChild(optionRadio);

        const optionText = document.createElement("span");
        optionText.textContent = option.label;
        optionRow.appendChild(optionText);

        if (option.id === "since_year") {
          const inlineSinceYearInput = document.createElement("input");
          inlineSinceYearInput.type = "text";
          inlineSinceYearInput.className = "input sags-facts-residence-inline-input";
          inlineSinceYearInput.placeholder = "fx 2021";
          inlineSinceYearInput.dataset.sagsResidenceSinceYear = "true";
          inlineSinceYearInput.value = String(facts.residenceSinceYear ?? "");
          inlineSinceYearInput.disabled = isGrensegaenger || selectedResidenceMode !== "since_year";
          optionRow.appendChild(inlineSinceYearInput);
        }

        elements.sagsFactsResidenceOptions.appendChild(optionRow);
      });
    } else {
      elements.sagsFactsResidenceOptions.innerHTML = "";
    }
  }
  if (elements.sagsFactsResidenceSinceYear) {
    // Legacy static input kept hidden; inline input is rendered in residence option row.
    elements.sagsFactsResidenceSinceYear.classList.add("hidden");
    if (elements.sagsFactsResidenceSinceYear.value !== (facts.residenceSinceYear ?? "")) {
      elements.sagsFactsResidenceSinceYear.value = facts.residenceSinceYear ?? "";
    }
  }
  if (
    elements.sagsFactsResidence &&
    elements.sagsFactsResidence.value !== (facts.residenceFact ?? "")
  ) {
    elements.sagsFactsResidence.value = facts.residenceFact ?? "";
  }
  if (elements.sagsFactsResidence) {
    elements.sagsFactsResidence.placeholder = factsUiCfg.residencePlaceholder || "";
    elements.sagsFactsResidence.classList.toggle(
      "hidden",
      activeSubtab === "skattepligt_ligningsfrist" || activeSubtab === "beskatningsret_indkomst",
    );
  }
  if (elements.sagsFactsResidenceLabel) {
    elements.sagsFactsResidenceLabel.classList.toggle("hidden", activeSubtab === "beskatningsret_indkomst");
  }
  if (elements.sagsFactsNotes && elements.sagsFactsNotes.value !== (facts.notes ?? "")) {
    elements.sagsFactsNotes.value = facts.notes ?? "";
  }
  if (elements.sagsFactsNotes) {
    elements.sagsFactsNotes.placeholder = factsUiCfg.notesPlaceholder || "";
    const isReadOnlyRetsgrundlag = activeSubtab === "skattepligt_ligningsfrist";
    elements.sagsFactsNotes.readOnly = isReadOnlyRetsgrundlag;
    elements.sagsFactsNotes.classList.toggle("input-readonly", isReadOnlyRetsgrundlag);
  }
  if (elements.sagsFactsSaveBtn) {
    elements.sagsFactsSaveBtn.textContent = isFactsLocked ? "Lås op fakta" : "Gem fakta";
  }
  if (elements.sagsFactsClearBtn) {
    elements.sagsFactsClearBtn.disabled = isFactsLocked;
  }
  if (elements.sagsFactsPanel) {
    const lockableControls = elements.sagsFactsPanel.querySelectorAll(
      "input, textarea, select",
    );
    lockableControls.forEach((control) => {
      const field = control;
      if (isFactsLocked) {
        field.disabled = true;
      }
    });
  }
}
