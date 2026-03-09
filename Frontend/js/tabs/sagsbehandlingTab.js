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
    enabled: false,
  },
  beskatningsret_indkomst: {
    title: "Sagsbehandling - Beskatningsret til indkomst",
    placeholder: "Beskriv spørgsmålet om beskatningsret (dummy)...",
    functions: [
      "Fordel beskatningsret (dummy)",
      "Vurder DBO-relevans (dummy)",
      "Opsummer hjemmel (dummy)",
    ],
    enabled: false,
  },
  lempelse: {
    title: "Sagsbehandling - Lempelse",
    placeholder: "Beskriv spørgsmålet om lempelse (dummy)...",
    functions: [
      "Vælg lempelsesmetode (dummy)",
      "Beregn credit/exemption (dummy)",
      "Dokumentationscheck (dummy)",
    ],
    enabled: false,
  },
  andet: {
    title: "Sagsbehandling - Andet",
    placeholder: "Beskriv anden sagsbehandling (dummy)...",
    functions: [
      "Generel juridisk vurdering (dummy)",
      "Klassificer problemstilling (dummy)",
      "Lav handlingsplan (dummy)",
    ],
    enabled: false,
  },
};

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
    incomeYearsLabel: "Indkomstår",
    incomeYearsPlaceholder: "Fx 2023",
    foreignIncomeLabel: "Land(e) og indkomstkilde",
    foreignIncomePlaceholder: "Fx Danmark/Tyskland, lønindkomst",
    foreignAssetsLiabilitiesLabel: "Arbejdssted / ophold",
    foreignAssetsLiabilitiesPlaceholder: "Fx antal dage, arbejdssted, arbejdsgiver",
    residenceLabel: "Skattemæssigt hjemsted (faktum)",
    residencePlaceholder: "Fx bopæl, familie, opholdsmønster",
    notesLabel: "Supplerende DBO-fakta",
    notesPlaceholder: "Fx artikelhenvisning, kildebeskatning, credit",
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

export function renderSagsbehandling(elements, state) {
  const activeSubtab = state.sagsbehandling.activeSubtab || "skattepligt_ligningsfrist";
  const cfg = SUBTAB_CONFIG[activeSubtab] || SUBTAB_CONFIG.skattepligt_ligningsfrist;
  const factsUiCfg =
    FACTS_UI_CONFIG[activeSubtab] || FACTS_UI_CONFIG.skattepligt_ligningsfrist;
  const requiredFields = new Set(factsUiCfg.requiredFields || []);
  const factsBySubtab = state.sagsbehandling.factsBySubtab || {};
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
    ...(factsBySubtab[activeSubtab] || {}),
  };

  if (elements.sagsbehandlingTitle) {
    elements.sagsbehandlingTitle.textContent = cfg.title;
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
    elements.sagsbehandlingSendBtn.disabled = !cfg.enabled || !requiredFactsComplete;
    elements.sagsbehandlingSendBtn.textContent = cfg.enabled ? "Send" : "Send (kommer snart)";
  }

  if (elements.sagsbehandlingConversation) {
    const messages = state.sagsbehandling.messages || [];
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
      messages.forEach((entry) => {
        const msg = document.createElement("div");
        msg.classList.add("msg");
        if (entry.role === "user") {
          msg.classList.add("msg-user");
          msg.textContent = "Du: " + (entry.text || "");
        } else if (entry.role === "assistant") {
          msg.classList.add("msg-assistant");
          msg.textContent = "JAILA:\n\n" + (entry.text || "");
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

  if (elements.sagsFactsPanelTitle) {
    elements.sagsFactsPanelTitle.textContent = factsUiCfg.panelTitle;
  }
  if (elements.sagsFactsIncomeYearsLabel) {
    elements.sagsFactsIncomeYearsLabel.textContent = withRequiredMarker(
      factsUiCfg.incomeYearsLabel,
      requiredFields.has("incomeYears"),
    );
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
  if (
    elements.sagsFactsForeignAssetsLiabilities &&
    elements.sagsFactsForeignAssetsLiabilities.value !== (facts.foreignAssetsLiabilities ?? "")
  ) {
    elements.sagsFactsForeignAssetsLiabilities.value = facts.foreignAssetsLiabilities ?? "";
  }
  if (elements.sagsFactsForeignAssetsLiabilities) {
    elements.sagsFactsForeignAssetsLiabilities.placeholder =
      factsUiCfg.foreignAssetsLiabilitiesPlaceholder || "";
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
    elements.sagsFactsForeignIncome.classList.toggle("hidden", hideLegacyFields);
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
    elements.sagsFactsResidence.classList.toggle("hidden", activeSubtab === "skattepligt_ligningsfrist");
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
}
