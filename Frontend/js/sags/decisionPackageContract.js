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
      assumptions: [],
    },
    foreloebig_beskatningsret: [],
    konflikter: [],
    advarsler: [],
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
    const contractNote = clean(facts.foreignAssetsLiabilities || "");
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
        basis: "arbejdsdage_pr_land",
        period,
        assumptions: [
          "Mere præcis fordelingsnøgle foreligger ikke i input.",
        ],
      };
    }

    pkg.afledte_praemisser.push(
      "Det lægges i denne vurdering til grund, at den valgte DBO-artikel er et foreløbigt arbejdspunkt.",
      hasArticle15Allocation
        ? "Ved den foreløbige vurdering anvendes arbejdsdage som fordelingsnøgle."
        : "Der er ikke valgt en artikelprofil, der udløser arbejdsdagsfordeling.",
    );
    if (residenceCountry === "danmark") {
      pkg.afledte_praemisser.push("Systemet behandler foreløbigt Danmark som hjemstatskandidat.");
    }

    profile.legal_sources.forEach((source) => {
      pkg.relevante_retskilder.push(source);
    });

    if (typeof profile.apply === "function") {
      profile.apply({
        pkg,
        context: {
          facts,
          parsedArticle,
          workdays,
          employerType: clean(facts.employerResidenceMode || ""),
          employerCountry,
          residenceCountry,
          grossIncome,
          period,
        },
      });
    }

    if (!workdays.length && hasArticle15Allocation) {
      pkg.uafklarede_sporgsmaal.push("Arbejdsdage pr. land mangler.");
      pkg.advarsler.push("Fordelingsmetode kan ikke anvendes uden arbejdsdage.");
    }
    if (!parsedArticle.article) {
      pkg.uafklarede_sporgsmaal.push("DBO-artikel er ikke entydigt valgt.");
      if (parsedArticle.candidates.length > 1) {
        pkg.konflikter.push("Flere mulige artikelkandidater fundet i input; præcis artikelvalg er konfliktende.");
      }
    }
    if (!clean(facts.employerCountry || "")) {
      pkg.uafklarede_sporgsmaal.push("Arbejdsgiverland er ikke oplyst.");
    }
    if (!Number.isFinite(grossIncome.amount) && hasArticle15Allocation) {
      pkg.uafklarede_sporgsmaal.push("Samlet bruttoindkomst er ikke oplyst i struktureret felt.");
      pkg.advarsler.push("Foreløbig fordeling kan ikke beregnes uden bruttoindkomst_total.");
    }

    if (residenceCountry === "danmark" && employerCountry && normalizeCountryKey(employerCountry) === "danmark") {
      pkg.konflikter.push("Bopælsland og arbejdsgiverland er begge Danmark, men arbejdsgivertype kan være udenlandsk.");
    }
    if (contractNote && !clean(facts.employmentContractReceived || "")) {
      pkg.konflikter.push("Der er kontraktnote, men svar på modtaget ansættelseskontrakt (Ja/Nej) mangler.");
    }

    if (hasArticle15Allocation && Number.isFinite(grossIncome.amount) && workdays.length > 0) {
      const totalDays = workdays.reduce((sum, row) => sum + Number(row.days || 0), 0);
      const dkKey = normalizeCountryKey("danmark");
      const employerKey = normalizeCountryKey(employerCountry);
      if (totalDays > 0) {
        workdays.forEach((row) => {
          const share = Number(row.days) / totalDays;
          const allocated = Number(grossIncome.amount) * share;
          const countryKey = normalizeCountryKey(row.country);
          const isOtherCountry = countryKey !== dkKey && countryKey !== employerKey;
          pkg.foreloebig_beskatningsret.push({
            label: `Foreløbig andel for ${row.country}`,
            country: isOtherCountry ? "danmark" : row.country,
            amount: Math.round(allocated * 100) / 100,
            currency: "DKK",
            share_ratio: Math.round(share * 100000) / 100000,
            basis: "pro_rata_workdays",
            status: "aktiv",
            note: isOtherCountry
              ? "Arbejdsland er hverken Danmark eller arbejdsgiverland; andel allokeres foreløbigt til Danmark."
              : "",
          });
        });
      }
    }
  }

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
