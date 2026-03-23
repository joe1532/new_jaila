/**
 * Beslutningspakke-kontrakt til LLM-styring.
 * Formål: adskille fakta, præmisser, metode og usikkerheder,
 * så LLM skriver ud fra struktureret grundlag fremfor rå UI-felter.
 */

/**
 * @typedef {"ui"|"kontrakt"|"lønseddel"|"årsopgørelse"|"systemberegning"|"manuel_vurdering"|"ukendt"} DecisionSource
 * @typedef {"oplyst"|"udledt"|"beregnet"|"valgt"} DecisionOrigin
 * @typedef {"høj"|"middel"|"lav"} DecisionCertainty
 * @typedef {"aktiv"|"konfliktende"|"uafklaret"} DecisionStatus
 */
import { resolveDecisionProfile } from "./profiles/resolver.js";

function clean(value) {
  return String(value || "").trim();
}

function normalizeCountry(value) {
  return clean(value).toLowerCase();
}

function parseDanishAmount(value) {
  const raw = clean(value);
  if (!raw) return null;
  const compact = raw
    .replace(/[^\d,.\-]/g, "")
    .replace(/\.(?=\d{3}(?:\D|$))/g, "")
    .replace(",", ".");
  if (!compact || compact === "-" || compact === ".") return null;
  const numeric = Number.parseFloat(compact);
  return Number.isFinite(numeric) ? numeric : null;
}

function parseInteger(value) {
  const numeric = parseDanishAmount(value);
  if (!Number.isFinite(numeric)) return null;
  return Math.trunc(numeric);
}

function formatPeriod(valueA, valueB = "") {
  const first = clean(valueA);
  if (first) return first;
  return clean(valueB);
}

function normalizeCountryKey(value) {
  return clean(value)
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "");
}

function extractCandidateArticles(text) {
  const normalized = clean(text).toLowerCase();
  if (!normalized) return [];
  const matches = normalized.match(/\b(?:artikel|art)\s*\.?\s*\d{1,2}(?:\s*,?\s*stk\.?\s*\d{1,2})?/g) || [];
  const bareArticle = normalized.match(/\b\d{1,2}\s*,?\s*stk\.?\s*\d{1,2}\b/g) || [];
  const all = [...matches, ...bareArticle].map((item) => item.replace(/\s+/g, " ").trim());
  return Array.from(new Set(all));
}

function inferIncomeType(value) {
  const normalized = clean(value).toLowerCase();
  if (!normalized) return "";
  if (normalized.includes("løn")) return "løn";
  if (normalized.includes("pension")) return "pension";
  if (normalized.includes("kapital")) return "kapital";
  return "";
}

function resolveGrossIncome(opgoerelseFacts) {
  const explicitCandidates = [
    opgoerelseFacts.bruttoindkomstTotal,
    opgoerelseFacts.bruttoindkomst_total,
    opgoerelseFacts.grossIncomeTotal,
    opgoerelseFacts.gross_income_total,
  ];
  for (const candidate of explicitCandidates) {
    if (candidate && typeof candidate === "object") {
      const amount = parseDanishAmount(candidate.amount);
      if (Number.isFinite(amount)) {
        return {
          amount,
          source: clean(candidate.source || "ui"),
          origin: "oplyst",
          certainty: "høj",
          status: "aktiv",
        };
      }
    }
    const amount = parseDanishAmount(candidate);
    if (Number.isFinite(amount)) {
      return {
        amount,
        source: "ui",
        origin: "oplyst",
        certainty: "høj",
        status: "aktiv",
      };
    }
  }
  return {
    amount: null,
    source: "ukendt",
    origin: "udledt",
    certainty: "lav",
    status: "uafklaret",
  };
}

function parseArticleFromText(text) {
  const normalized = clean(text).toLowerCase();
  const articleMatch = normalized.match(/\b(?:artikel|art)\s*\.?\s*(\d{1,2})\b/) || normalized.match(/\b(\d{1,2})\s*,?\s*stk\.?\s*\d{1,2}\b/);
  const sectionMatch = normalized.match(/\bstk\.?\s*(\d{1,2})\b/) || normalized.match(/\b\d{1,2}\s*[,/]\s*(\d{1,2})\b/);
  const candidates = extractCandidateArticles(text);
  return {
    article: articleMatch ? Number(articleMatch[1]) : null,
    section: sectionMatch ? Number(sectionMatch[1]) : null,
    candidates,
  };
}

function createFact({ factKey, value, source = "ui", origin = "oplyst", certainty = "middel", status = "aktiv", note = "" }) {
  return {
    fact_key: factKey,
    value,
    source,
    origin,
    certainty,
    status,
    note: clean(note),
  };
}

function createDecisionSignal({ key, type, status = "uafklaret", data = {} }) {
  return {
    key: clean(key),
    type: clean(type),
    status: clean(status),
    data: data && typeof data === "object" ? data : {},
  };
}

function appendDecisionItems(target, items) {
  if (!Array.isArray(target) || !Array.isArray(items)) return;
  items.forEach((item) => {
    if (item && typeof item === "object") {
      target.push(item);
      return;
    }
    const text = clean(item);
    if (text) {
      target.push(text);
    }
  });
}

function createEmptyProfileResult() {
  return {
    praemisser: [],
    vurderingstrin: [],
    uafklarede_sporgsmaal: [],
    advarsler: [],
    konflikter: [],
    foreloebig_beskatningsret: [],
    conclusion: null,
  };
}

function mergeProfileResult(pkg, result) {
  const safe = result && typeof result === "object" ? result : createEmptyProfileResult();
  if (Array.isArray(safe.praemisser)) {
    appendDecisionItems(pkg.afledte_praemisser, safe.praemisser);
  }
  if (Array.isArray(safe.vurderingstrin)) {
    safe.vurderingstrin.forEach((step) => {
      if (step && typeof step === "object") {
        pkg.vurderingstrin.push(step);
      }
    });
  }
  if (Array.isArray(safe.uafklarede_sporgsmaal)) {
    appendDecisionItems(pkg.uafklarede_sporgsmaal, safe.uafklarede_sporgsmaal);
  }
  if (Array.isArray(safe.advarsler)) {
    appendDecisionItems(pkg.advarsler, safe.advarsler);
  }
  if (Array.isArray(safe.konflikter)) {
    appendDecisionItems(pkg.konflikter, safe.konflikter);
  }
  if (Array.isArray(safe.foreloebig_beskatningsret)) {
    safe.foreloebig_beskatningsret.forEach((item) => {
      if (item && typeof item === "object") {
        pkg.foreloebig_beskatningsret.push(item);
      }
    });
  }
  if (safe.conclusion && typeof safe.conclusion === "object") {
    pkg.samlet_konklusion = {
      text: clean(safe.conclusion.text),
      status: clean(safe.conclusion.status || "foreløbig") || "foreløbig",
    };
  }
}

function buildWorkdayRows(facts, period) {
  const modes = Array.isArray(facts.workCountryModes)
    ? facts.workCountryModes.map((value) => clean(value)).filter((value) => value)
    : [];
  const selected = new Set(modes);
  const countries = [];
  if (selected.has("danmark")) {
    countries.push("Danmark");
  }
  const customCountries = Array.isArray(facts.workCountryDenmarkFields) ? facts.workCountryDenmarkFields : [];
  const customChecked = Array.isArray(facts.workCountryCustomChecked) ? facts.workCountryCustomChecked : [];
  customCountries.forEach((value, idx) => {
    if (!Boolean(customChecked[idx])) return;
    const country = clean(value);
    if (!country) return;
    countries.push(country);
  });
  const seen = new Set();
  const uniqueCountries = [];
  countries.forEach((country) => {
    const key = normalizeCountry(country);
    if (!key || seen.has(key)) return;
    seen.add(key);
    uniqueCountries.push(country);
  });

  const daysMap = facts.workCountryDaysByCountry && typeof facts.workCountryDaysByCountry === "object"
    ? facts.workCountryDaysByCountry
    : {};
  return uniqueCountries
    .map((country) => ({
      country,
      days: parseInteger(daysMap[country]),
      source: "ui",
      period,
      status: "oplyst",
    }))
    .filter((row) => Number.isFinite(row.days));
}

export function createEmptyDecisionPackage() {
  return {
    sagskontekst: {
      indkomsttype: "",
      valgt_artikel: {
        article: null,
        section: null,
        raw_text: "",
        source: "ui",
        origin: "valgt",
        certainty: "middel",
        status: "uafklaret",
        candidate_articles: [],
      },
      bopaelsland: "",
      arbejdsgivertype: "",
    },
    regelprofil: {
      profile_id: "",
      requires_day_allocation: false,
      requires_employer_assessment: false,
    },
    konstaterede_fakta: [],
    afledte_praemisser: [],
    relevante_retskilder: [],
    uafklarede_sporgsmaal: [],
    fordelingsmetode: {
      method_id: "",
      description: "",
      basis: "",
      period: "",
      begrundelse: "",
      begrænsninger: [],
      calculation: {},
      assumptions: [],
    },
    foreloebig_beskatningsret: [],
    vurderingstrin: [],
    samlet_konklusion: {
      text: "",
      status: "foreløbig",
    },
    konflikter: [],
    advarsler: [],
    qa: {
      mangler: [],
      konflikter: [],
      risici: [],
    },
    input_kvalitet: {
      niveau: "middel",
      begrundelse: [],
    },
  };
}

export function buildDecisionPackageFromSagsInput({ activeSubtab, factsBySubtab }) {
  const pkg = createEmptyDecisionPackage();
  const safeSubtab = clean(activeSubtab);
  const allFacts = factsBySubtab && typeof factsBySubtab === "object" ? factsBySubtab : {};
  const facts = allFacts[safeSubtab] || {};
  const opgoerelseFacts = allFacts.opgoerelse_indkomst || {};
  const period = formatPeriod(opgoerelseFacts.incomeYears, facts.incomeYears);

  pkg.sagskontekst.indkomsttype = inferIncomeType(facts.foreignIncome) || clean(facts.foreignIncome || "");
  pkg.sagskontekst.bopaelsland = clean(facts.residenceCountryMode || "");
  pkg.sagskontekst.arbejdsgivertype = clean(facts.employerResidenceMode || "");

  const parsedArticle = parseArticleFromText(facts.incomeDboArticle);
  pkg.sagskontekst.valgt_artikel = {
    article: parsedArticle.article,
    section: parsedArticle.section,
    raw_text: clean(facts.incomeDboArticle || ""),
    source: "ui",
    origin: "valgt",
    certainty: parsedArticle.article ? "middel" : "lav",
    status: parsedArticle.article ? "aktiv" : "uafklaret",
    candidate_articles: parsedArticle.candidates,
  };

  const profile = resolveDecisionProfile(parsedArticle);
  pkg.regelprofil.profile_id = safeSubtab === "beskatningsret_indkomst"
    ? profile.profile_id
    : "general_assessment";
  pkg.regelprofil.requires_day_allocation =
    safeSubtab === "beskatningsret_indkomst" && Boolean(profile.requires_day_allocation);
  pkg.regelprofil.requires_employer_assessment =
    safeSubtab === "beskatningsret_indkomst" && Boolean(profile.requires_employer_assessment);

  if (safeSubtab === "beskatningsret_indkomst") {
    const workdays = buildWorkdayRows(facts, period);
    const grossIncome = resolveGrossIncome(opgoerelseFacts);
    const employerCountry = clean(facts.employerCountry || "");
    const residenceCountry = clean(facts.residenceCountryMode || "");
    const residenceAvailableInWorkCountry = Boolean(facts.residenceAvailableInWorkCountry);
    const taxResidenceDenmarkFact = clean(facts.taxResidenceDenmarkFact || "");
    const contractNote = clean(facts.foreignAssetsLiabilities || "");
    const employmentContractReceived = clean(facts.employmentContractReceived || "").toLowerCase();
    const hasArticle15Allocation = Boolean(profile.requires_day_allocation);

    pkg.konstaterede_fakta.push(
      createFact({
        factKey: "residence_country",
        value: residenceCountry,
        source: "ui",
        origin: "oplyst",
        certainty: "middel",
        status: residenceCountry ? "aktiv" : "uafklaret",
      }),
      createFact({
        factKey: "employer_residence_country",
        value: employerCountry,
        source: "ui",
        origin: "oplyst",
        certainty: "middel",
        status: employerCountry ? "aktiv" : "uafklaret",
      }),
      createFact({
        factKey: "gross_income_total",
        value: {
          amount: Number.isFinite(grossIncome.amount) ? grossIncome.amount : null,
          currency: "DKK",
          period,
          source: grossIncome.source,
          status: grossIncome.status,
        },
        source: grossIncome.source,
        origin: grossIncome.origin,
        certainty: grossIncome.certainty,
        status: grossIncome.status,
      }),
      createFact({
        factKey: "employment_contract_note",
        value: contractNote,
        source: "kontrakt",
        origin: "oplyst",
        certainty: contractNote ? "middel" : "lav",
        status: contractNote ? "aktiv" : "uafklaret",
      }),
      createFact({
        factKey: "employment_contract_received",
        value: employmentContractReceived || null,
        source: "ui",
        origin: "oplyst",
        certainty: employmentContractReceived ? "høj" : "lav",
        status: employmentContractReceived ? "aktiv" : "uafklaret",
      }),
      createFact({
        factKey: "residence_available_in_work_country",
        value: residenceAvailableInWorkCountry,
        source: "ui",
        origin: "oplyst",
        certainty: "middel",
        status: "aktiv",
      }),
      createFact({
        factKey: "tax_residence_denmark_fact",
        value: taxResidenceDenmarkFact,
        source: "ui",
        origin: "oplyst",
        certainty: taxResidenceDenmarkFact ? "middel" : "lav",
        status: taxResidenceDenmarkFact ? "aktiv" : "uafklaret",
      }),
      createFact({
        factKey: "workdays_by_country",
        value: workdays,
        source: "ui",
        origin: "oplyst",
        certainty: workdays.length ? "middel" : "lav",
        status: workdays.length ? "aktiv" : "uafklaret",
      }),
      createFact({
        factKey: "selected_dbo_article",
        value: {
          article: parsedArticle.article,
          section: parsedArticle.section,
          raw_text: clean(facts.incomeDboArticle || ""),
        },
        source: "ui",
        origin: "valgt",
        certainty: parsedArticle.article ? "middel" : "lav",
        status: parsedArticle.article ? "aktiv" : "uafklaret",
      }),
    );

    if (hasArticle15Allocation) {
      pkg.fordelingsmetode = {
        method_id: "pro_rata_workdays",
        description: "Foreløbig pro rata-fordeling efter arbejdsdage pr. land.",
        basis: ["workdays_by_country", "gross_income_total"],
        period,
        begrundelse: "Mere præcis fordelingsnøgle foreligger ikke i input.",
        begrænsninger: [
          "Ferie, rejsetid og standby er ikke særskilt oplyst.",
        ],
        calculation: {
          total_days: null,
          country_days: {},
          ratio_by_country: {},
          allocated_amount_by_country: {},
        },
        assumptions: [
          "Mere præcis fordelingsnøgle foreligger ikke i input.",
        ],
      };
    }

    pkg.afledte_praemisser.push(
      createDecisionSignal({
        key: "selected_article_is_working_hypothesis",
        type: "assumption",
        status: "aktiv",
        data: {
          article: parsedArticle.article,
          section: parsedArticle.section,
        },
      }),
      createDecisionSignal({
        key: "allocation_method_selection",
        type: "assumption",
        status: hasArticle15Allocation ? "aktiv" : "uafklaret",
        data: {
          method_id: hasArticle15Allocation ? "pro_rata_workdays" : "",
        },
      }),
    );
    if (residenceCountry === "danmark") {
      pkg.afledte_praemisser.push(createDecisionSignal({
        key: "denmark_home_state_candidate",
        type: "assumption",
        status: "aktiv",
        data: {
          residence_country: residenceCountry,
        },
      }));
    }

    profile.legal_sources.forEach((source) => {
      pkg.relevante_retskilder.push(source);
    });

    if (typeof profile.apply === "function") {
      const profileResult = profile.apply({
        context: {
          facts,
          parsedArticle,
          workdays,
          employerType: clean(facts.employerResidenceMode || ""),
          employerCountry,
          residenceCountry,
          residenceAvailableInWorkCountry,
          taxResidenceDenmarkFact,
          employmentContractReceived,
          grossIncome,
          period,
        },
      });
      mergeProfileResult(pkg, profileResult);
    }

    if (!workdays.length && hasArticle15Allocation) {
      pkg.uafklarede_sporgsmaal.push(createDecisionSignal({
        key: "workdays_missing",
        type: "missing_data",
        status: "uafklaret",
        data: {
          field: "workdays_by_country",
        },
      }));
      pkg.advarsler.push(createDecisionSignal({
        key: "allocation_blocked_without_workdays",
        type: "risk",
        status: "uafklaret",
        data: {
          method_id: "pro_rata_workdays",
        },
      }));
    }
    if (!parsedArticle.article) {
      pkg.uafklarede_sporgsmaal.push(createDecisionSignal({
        key: "article_not_selected_unambiguously",
        type: "missing_data",
        status: "uafklaret",
        data: {
          raw_input: clean(facts.incomeDboArticle || ""),
        },
      }));
      if (parsedArticle.candidates.length > 1) {
        pkg.konflikter.push(createDecisionSignal({
          key: "multiple_article_candidates",
          type: "conflict",
          status: "konfliktende",
          data: {
            candidates: parsedArticle.candidates,
          },
        }));
      }
    }
    if (!clean(facts.employerCountry || "")) {
      pkg.uafklarede_sporgsmaal.push(createDecisionSignal({
        key: "employer_country_missing",
        type: "missing_data",
        status: "uafklaret",
        data: {
          field: "employer_residence_country",
        },
      }));
    }
    if (!Number.isFinite(grossIncome.amount) && hasArticle15Allocation) {
      pkg.uafklarede_sporgsmaal.push(createDecisionSignal({
        key: "gross_income_missing",
        type: "missing_data",
        status: "uafklaret",
        data: {
          field: "gross_income_total",
        },
      }));
      pkg.advarsler.push(createDecisionSignal({
        key: "allocation_blocked_without_gross_income",
        type: "risk",
        status: "uafklaret",
        data: {
          method_id: "pro_rata_workdays",
        },
      }));
    }

    if (residenceCountry === "danmark" && employerCountry && normalizeCountryKey(employerCountry) === "danmark") {
      pkg.konflikter.push(createDecisionSignal({
        key: "residence_and_employer_country_both_denmark",
        type: "conflict",
        status: "konfliktende",
        data: {
          residence_country: residenceCountry,
          employer_country: employerCountry,
          employer_type: clean(facts.employerResidenceMode || ""),
        },
      }));
    }
    if (contractNote && !clean(facts.employmentContractReceived || "")) {
      pkg.konflikter.push(createDecisionSignal({
        key: "contract_note_without_contract_received_status",
        type: "conflict",
        status: "konfliktende",
        data: {
          has_contract_note: true,
        },
      }));
    }
    if (!employmentContractReceived) {
      pkg.uafklarede_sporgsmaal.push(createDecisionSignal({
        key: "employment_contract_received_missing",
        type: "missing_data",
        status: "uafklaret",
        data: {
          field: "employment_contract_received",
        },
      }));
    }
    const contractEvidenceLevel = employmentContractReceived === "ja"
      ? (contractNote ? "høj" : "middel")
      : employmentContractReceived === "nej"
        ? "lav"
        : "lav";
    pkg.advarsler.push(createDecisionSignal({
      key: "employment_contract_evidence_level",
      type: "risk",
      status: contractEvidenceLevel === "høj" ? "aktiv" : "uafklaret",
      data: {
        evidence_level: contractEvidenceLevel,
        contract_received: employmentContractReceived || null,
        has_contract_note: Boolean(contractNote),
      },
    }));
    if (residenceCountry === "danmark" && !taxResidenceDenmarkFact) {
      pkg.advarsler.push(createDecisionSignal({
        key: "tax_residence_denmark_fact_missing",
        type: "risk",
        status: "uafklaret",
        data: {
          field: "tax_residence_denmark_fact",
        },
      }));
    }

    if (hasArticle15Allocation && Number.isFinite(grossIncome.amount) && workdays.length > 0) {
      const totalDays = workdays.reduce((sum, row) => sum + Number(row.days || 0), 0);
      const dkKey = normalizeCountryKey("danmark");
      const employerKey = normalizeCountryKey(employerCountry);
      if (totalDays > 0) {
        const countryDays = {};
        const ratioByCountry = {};
        const allocatedAmountByCountry = {};
        workdays.forEach((row) => {
          const share = Number(row.days) / totalDays;
          const allocated = Number(grossIncome.amount) * share;
          const countryKey = normalizeCountryKey(row.country);
          const isOtherCountry = countryKey !== dkKey && countryKey !== employerKey;
          countryDays[row.country] = Number(row.days);
          ratioByCountry[row.country] = Math.round(share * 100000) / 100000;
          allocatedAmountByCountry[row.country] = Math.round(allocated * 100) / 100;
          pkg.foreloebig_beskatningsret.push({
            label: `Foreløbig andel for ${row.country}`,
            country: isOtherCountry ? "danmark" : row.country,
            amount: Math.round(allocated * 100) / 100,
            currency: "DKK",
            share_ratio: Math.round(share * 100000) / 100000,
            basis: "pro_rata_workdays",
            juridisk_hjemmel: parsedArticle.section
              ? `DBO artikel 15, stk. ${parsedArticle.section}`
              : "DBO artikel 15",
            forudsætninger: [
              "Arbejdsdage anvendes som foreløbig fordelingsnøgle.",
              "Mere præcis fordelingsnøgle foreligger ikke i input.",
            ],
            kilde_trin: [
              "art15_arbejdsland",
              parsedArticle.section === 2 ? "art15_s2_arbejdsgiver" : "art15_arbejdsland",
              "allokering_af_indkomst",
            ],
            status: "aktiv",
            note: isOtherCountry
              ? "Arbejdsland er hverken Danmark eller arbejdsgiverland; andel allokeres foreløbigt til Danmark."
              : "",
          });
        });
        if (pkg.fordelingsmetode && typeof pkg.fordelingsmetode === "object") {
          pkg.fordelingsmetode.calculation = {
            total_days: totalDays,
            country_days: countryDays,
            ratio_by_country: ratioByCountry,
            allocated_amount_by_country: allocatedAmountByCountry,
          };
        }
      }
    }
  }

  if (!clean(pkg.samlet_konklusion.text) && pkg.foreloebig_beskatningsret.length > 0) {
    pkg.samlet_konklusion = {
      text: "Foreløbig konklusion: Beskatningsretten fordeles efter de beregnede andele i beslutningspakken.",
      status: "foreløbig",
    };
  }

  pkg.qa = {
    mangler: [...pkg.uafklarede_sporgsmaal],
    konflikter: [...pkg.konflikter],
    risici: [...pkg.advarsler],
  };

  pkg.input_kvalitet.niveau = pkg.uafklarede_sporgsmaal.length >= 3
    ? "lav"
    : pkg.uafklarede_sporgsmaal.length > 0
      ? "middel"
      : "høj";
  if (pkg.uafklarede_sporgsmaal.length) {
    pkg.input_kvalitet.begrundelse.push("Der er uafklarede spørgsmål i datagrundlaget.");
  }
  return pkg;
}
