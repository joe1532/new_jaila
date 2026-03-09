import { analyzeQuestion, analyzeQuestionStream } from "./api/analyzeApi.js";
import { getAnalyseLog, listAnalyseLogs, saveAnalyseLog } from "./api/analyseLogsApi.js";
import { getSagsLegalBasis } from "./api/sagsbehandlingApi.js";
import { exportChatPdf, sendChat, sendChatStream } from "./api/chatApi.js";
import {
  clearChatContextFiles,
  deleteChatContextFile,
  getChatContextFiles,
  uploadChatContextFile,
} from "./api/contextApi.js";
import {
  clearActiveUser,
  getActiveTab,
  getActiveUser,
  getOrCreateChatSessionId,
  resetChatSessionId,
  setActiveTab,
  setActiveUser,
} from "./state/session.js";
import { getState, setState } from "./state/store.js";
import { getInitialAnalyseState, renderAnalyse } from "./tabs/analyseTab.js";
import { getInitialChatState, renderChat } from "./tabs/chatTab.js";
import { renderSagsbehandling } from "./tabs/sagsbehandlingTab.js";

const VALID_USERS = {
  jonas: "pepsimax",
  allan: "pepsimax",
};

const ALLAN_WELCOME_MESSAGES = [
  "Velkommen Allan. Systemet kører fint – lad os se hvor længe det varer.",
  "Allan er logget ind. Fejlprotokollen er allerede åbnet.",
  "Allan er logget ind. Stabiliteten falder nu statistisk set.",
  "Allan er online. Backup anbefales.",
  "Velkommen tilbage Allan. Lad os prøve at holde systemet i live i dag.",
  "Allan er online. Supportafdelingen har taget kaffe frem.",
  "Allan er logget ind. Systemet justerer automatisk forventningerne ned.",
  "Allan er logget ind. Fejlloggen var klar i forvejen.",
  "Allan er logget ind. Systemet trækker vejret dybt.",
  "Allan er logget ind. Tingene bliver interessante nu.",
  "Allan er logget ind. Stabilitet er nu en ambition.",
  "Allan er logget ind. Systemet forbereder sig på kreative løsninger.",
  "Allan er tilbage. Stabiliteten tager en pause.",
  "Allan er tilbage. Fejlmarginen stiger.",
  "Allan er tilbage. Systemet har set det før.",
  "Hej Allan. Lad os se hvad du bryder først i dag.",
  "Hej Allan. Prøv ikke at trykke på alt på én gang.",
  "Hej Allan. Hvis noget virker i dag, var det ikke planlagt.",
  "Hej Allan. Systemet er designet til at overleve dine beslutninger.",
  "Hej Allan. Prøv at være forsigtig i dag.",
  "Velkommen Allan. Dokumentationen venter stadig.",
  "Velkommen Allan. Vi antager, at du ikke har læst dokumentationen.",
  "Velkommen Allan. Vi har gemt de farlige knapper.",
  "Velkommen Allan. JAILA vil forsøge at forklare tingene igen.",
  "Velkommen Allan. Statistik viser, at tingene nu bliver interessante.",
  "Velkommen Allan. JAILA er klar til endnu en dag med kreativ fejlanvendelse.",
  "Velkommen Allan. JAILA vil gøre sit bedste for at oversætte dine spørgsmål til noget meningsfuldt.",
  "Velkommen Allan. Systemet har igen aktiveret \"forklar det langsomt\"-tilstand.",
  "Velkommen Allan. JAILA vil forsøge at holde tingene inden for fysikkens love.",
  "Allan er online. Risikoindikatoren blinker.",
  "Allan er online. Forventede komplikationer.",
  "Allan er online. Systemet forsøger at gætte hvad du egentlig mener.",
  "Allan er online. Den pædagogiske reservekapacitet er aktiveret.",
  "Allan er logget ind. JAILA justerer automatisk kompleksiteten ned.",
  "Allan er logget ind. Systemet har aktiveret pædagogisk tilstand.",
  "Allan er logget ind. Statistik viser øget spænding.",
  "Allan er logget ind. Systemet tager en dyb indånding.",
];

const DEFAULT_RETSGRUNDLAG_SKATTEPLIGT = [
  "Skatteforvaltningslovens § 26, stk. 1",
  "Bekendtgørelse 2018-11-14 nr. 1302 om fysiske personers modtagelse af en årsopgørelse i stedet for et oplysningsskema",
  "Bekendtgørelse 2018-11-14 nr. 1305 om en kort frist for skatteansættelse af personer med enkle økonomiske forhold",
  "Bekendtgørelse 2025-01-24 nr. 49 om en kort frist for skatteansættelse af personer med enkle økonomiske forhold",
].join("\n");

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

const elements = {
  loginSection: document.getElementById("loginSection"),
  appSection: document.getElementById("appSection"),
  username: document.getElementById("username"),
  password: document.getElementById("password"),
  loginBtn: document.getElementById("loginBtn"),
  logoutBtn: document.getElementById("logoutBtn"),
  resetBtn: document.getElementById("resetBtn"),
  sessionLabel: document.getElementById("sessionLabel"),
  statusTargets: Array.from(document.querySelectorAll("[data-connection-status]")),
  analyseConversation: document.getElementById("analyseConversation"),
  analyseLogContent: document.getElementById("analyseLogContent"),
  question: document.getElementById("question"),
  analyzeBtn: document.getElementById("analyzeBtn"),
  analyzeAbortBtn: document.getElementById("analyzeAbortBtn"),
  pdfLogLink: document.getElementById("pdfLogLink"),
  analyseExtraBtn: document.getElementById("analyseExtraBtn"),
  tabButtons: Array.from(document.querySelectorAll(".tab-button")),
  tabPaneAnalyse: document.getElementById("tabPaneAnalyse"),
  tabPaneSagsbehandling: document.getElementById("tabPaneSagsbehandling"),
  tabPaneChat: document.getElementById("tabPaneChat"),
  sagsbehandlingTitle: document.getElementById("sagsbehandlingTitle"),
  sagsbehandlingConversation: document.getElementById("sagsbehandlingConversation"),
  sagsbehandlingInput: document.getElementById("sagsbehandlingInput"),
  sagsbehandlingSendBtn: document.getElementById("sagsbehandlingSendBtn"),
  sagsbehandlingClearBtn: document.getElementById("sagsbehandlingClearBtn"),
  sagsFunctionList: document.getElementById("sagsFunctionList"),
  sagsSubtabButtons: Array.from(document.querySelectorAll(".sags-subtab-button")),
  sagsFactsToggleBtn: document.getElementById("sagsFactsToggleBtn"),
  sagsFactsPanel: document.getElementById("sagsFactsPanel"),
  sagsFactsPanelTitle: document.getElementById("sagsFactsPanelTitle"),
  sagsFactsIncomeYearsLabel: document.getElementById("sagsFactsIncomeYearsLabel"),
  sagsFactsFactorSelectionLabel: document.getElementById("sagsFactsFactorSelectionLabel"),
  sagsFactsFactorChecklist: document.getElementById("sagsFactsFactorChecklist"),
  sagsFactsForeignIncomeLabel: document.getElementById("sagsFactsForeignIncomeLabel"),
  sagsFactsForeignAssetsLiabilitiesLabel: document.getElementById(
    "sagsFactsForeignAssetsLiabilitiesLabel",
  ),
  sagsFactsResidenceLabel: document.getElementById("sagsFactsResidenceLabel"),
  sagsFactsNotesLabel: document.getElementById("sagsFactsNotesLabel"),
  sagsFactsIncomeYears: document.getElementById("sagsFactsIncomeYears"),
  sagsFactsForeignIncome: document.getElementById("sagsFactsForeignIncome"),
  sagsFactsForeignAssetsLiabilities: document.getElementById("sagsFactsForeignAssetsLiabilities"),
  sagsFactsResidence: document.getElementById("sagsFactsResidence"),
  sagsFactsResidenceOptions: document.getElementById("sagsFactsResidenceOptions"),
  sagsFactsResidenceSinceYear: document.getElementById("sagsFactsResidenceSinceYear"),
  sagsFactsNotes: document.getElementById("sagsFactsNotes"),
  sagsFactsSaveBtn: document.getElementById("sagsFactsSaveBtn"),
  sagsFactsClearBtn: document.getElementById("sagsFactsClearBtn"),
  sagsFactsCloseBtn: document.getElementById("sagsFactsCloseBtn"),
  chatConversation: document.getElementById("chatConversation"),
  chatInput: document.getElementById("chatInput"),
  chatSendBtn: document.getElementById("chatSendBtn"),
  chatAbortBtn: document.getElementById("chatAbortBtn"),
  chatResetBtn: document.getElementById("chatResetBtn"),
  chatSavePdfBtn: document.getElementById("chatSavePdfBtn"),
  chatContextFile: document.getElementById("chatContextFile"),
  chatContextUploadBtn: document.getElementById("chatContextUploadBtn"),
  chatContextList: document.getElementById("chatContextList"),
};

function renderStatus() {
  if (!elements.statusTargets || !elements.statusTargets.length) {
      return;
    }
  const state = getState();
  const fixedStatusText = "Forbindelse til database";
  elements.statusTargets.forEach((statusEl) => {
    statusEl.textContent = fixedStatusText;
    statusEl.classList.remove("ok", "error");
    if (state.ui.statusMode === "ok") {
      statusEl.classList.add("ok");
    } else if (state.ui.statusMode === "error") {
      statusEl.classList.add("error");
    }
  });
}

function setStatus(text, mode) {
  setState({
    ui: {
      statusMessage: text,
      statusMode: mode || "ok",
      error: mode === "error" ? text : null,
    },
  });
  renderStatus();
}

let analyseAbortController = null;
let chatAbortController = null;

function setLoading(isLoading) {
  setState({
    ui: {
      loading: isLoading,
    },
  });
  if (elements.analyzeBtn) {
    elements.analyzeBtn.disabled = isLoading;
    elements.analyzeBtn.textContent = isLoading ? "Arbejder..." : "Kør analyse";
  }
  if (elements.chatSendBtn) {
    elements.chatSendBtn.disabled = isLoading;
    elements.chatSendBtn.textContent = isLoading ? "Arbejder..." : "Send";
  }
  if (!isLoading) {
    if (elements.analyzeAbortBtn) elements.analyzeAbortBtn.disabled = true;
    if (elements.chatAbortBtn) elements.chatAbortBtn.disabled = true;
  }
  if (elements.chatResetBtn) {
    elements.chatResetBtn.disabled = isLoading;
  }
  if (elements.chatSavePdfBtn) {
    elements.chatSavePdfBtn.disabled = isLoading;
  }
  if (elements.sagsbehandlingSendBtn) {
    if (isLoading) {
      elements.sagsbehandlingSendBtn.disabled = true;
    } else {
      renderSagsbehandling(elements, getState());
    }
  }
  if (elements.sagsbehandlingClearBtn) {
    elements.sagsbehandlingClearBtn.disabled = isLoading;
  }
  if (elements.pdfLogLink) {
    const canDownload = Boolean(getState().analyse.logPdfUrl);
    elements.pdfLogLink.disabled = isLoading || !canDownload;
  }
}

function renderAllTabs() {
  const state = getState();
  renderAnalyse(elements, state);
  renderChat(elements, state);
  renderSagsbehandling(elements, state);
}

function switchTab(tabId) {
  setState({
    ui: {
      activeTab: tabId,
    },
  });
  setActiveTab(tabId);

  const state = getState();
  const paneMap = {
    analyse: elements.tabPaneAnalyse,
    sagsbehandling: elements.tabPaneSagsbehandling,
    chat: elements.tabPaneChat,
  };
  Object.keys(paneMap).forEach((key) => {
    const pane = paneMap[key];
    if (!pane) {
      return;
    }
    pane.classList.toggle("hidden", key !== state.ui.activeTab);
  });

  elements.tabButtons.forEach((btn) => {
    const isActive = btn.dataset.tab === state.ui.activeTab;
    btn.classList.toggle("tab-button-active", isActive);
  });

  if (tabId === "analyse") {
    loadAnalyseSavedLogs();
  }
}

function showWelcomeModalForAllan() {
  const msg = ALLAN_WELCOME_MESSAGES[Math.floor(Math.random() * ALLAN_WELCOME_MESSAGES.length)];
  const overlay = document.createElement("div");
  overlay.className = "welcome-overlay";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.innerHTML = `
    <div class="welcome-overlay-backdrop"></div>
    <div class="welcome-overlay-box">
      <button type="button" class="welcome-overlay-close" aria-label="Luk">&times;</button>
      <h2 class="welcome-overlay-title">Velkommen</h2>
      <p class="welcome-overlay-message"></p>
    </div>
  `;
  overlay.querySelector(".welcome-overlay-message").textContent = msg;
  const close = () => overlay.remove();
  overlay.querySelector(".welcome-overlay-close").addEventListener("click", close);
  overlay.querySelector(".welcome-overlay-backdrop").addEventListener("click", close);
  document.body.appendChild(overlay);
}

function showApp(user) {
  setState({
    auth: {
      user: user,
      isLoggedIn: true,
    },
  });
  elements.loginSection.classList.add("hidden");
  elements.appSection.classList.remove("hidden");
  elements.sessionLabel.textContent = "Logget ind som: " + user;
  switchTab(getState().ui.activeTab || "chat");
  renderAllTabs();
  loadLegalBasisForSubtab(getState().sagsbehandling.activeSubtab || "skattepligt_ligningsfrist");
  renderStatus();
  setStatus("Klar til analyse.", "ok");
  if (user === "allan") {
    setTimeout(showWelcomeModalForAllan, 50);
  }
}

function showLogin(message, mode) {
  setState({
    auth: {
      user: null,
      isLoggedIn: false,
    },
  });
  elements.loginSection.classList.remove("hidden");
  elements.appSection.classList.add("hidden");
  setStatus(message || "Log ind for at bruge systemet.", mode || "ok");
}

function resetAnalyse() {
  const prev = getState().analyse || {};
  setState({
    analyse: {
      ...getInitialAnalyseState(),
      savedLogs: prev.savedLogs || [],
    },
  });
  renderAnalyse(elements, getState());
  setStatus("Analyse nulstillet.", "ok");
}

async function loadAnalyseSavedLogs() {
  const user = (getActiveUser() || "").trim();
  if (!user) return;
  try {
    const res = await listAnalyseLogs(user);
    const prev = getState().analyse || {};
    setState({ analyse: { ...prev, savedLogs: res.entries || [] } });
    renderAnalyse(elements, getState());
  } catch (err) {
    setStatus("Kunne ikke hente gemte logs: " + (err.message || "Fejl"), "error");
  }
}

async function onAnalyseLogEntryClick(entryId) {
  const user = getActiveUser();
  if (!user) return;
  try {
    const entry = await getAnalyseLog(user, entryId);
    setState({
      analyse: {
        selectedLogId: entryId,
        selectedLogContent: entry,
      },
    });
    renderAnalyse(elements, getState());
  } catch (err) {
    setStatus("Kunne ikke hente log: " + (err.message || "Fejl"), "error");
  }
}

function onAnalyseLogBackClick() {
  setState({
    analyse: {
      selectedLogId: null,
      selectedLogContent: null,
    },
  });
  renderAnalyse(elements, getState());
}

function resetChat() {
  const currentContextFiles = getState().chat.contextFiles || [];
  const initialChat = getInitialChatState();
  initialChat.contextFiles = currentContextFiles;
  setState({ chat: initialChat });
  renderChat(elements, getState());
}

async function resetChatWithCleanup() {
  setLoading(true);
  setStatus("Nulstiller chat...", "ok");
  try {
    const sessionId = getOrCreateChatSessionId();
    await clearChatContextFiles(sessionId);
    resetChatSessionId();
    await refreshChatContextFiles();
    resetChat();
    setStatus("Ny chat startet.", "ok");
  } catch (err) {
    resetChat();
    setStatus("Chat nulstillet lokalt (oprydning fejlede): " + (err.message || "Ukendt fejl"), "error");
  } finally {
    setLoading(false);
  }
}

function addChatMessage(role, text) {
  const currentMessages = getState().chat.messages || [];
  setState({
    chat: {
      messages: currentMessages.concat([{ role: role, text: text || "" }]),
    },
  });
  renderChat(elements, getState());
}

function updateLastChatMessageText(text) {
  const currentMessages = getState().chat.messages || [];
  if (currentMessages.length === 0) return;
  const last = currentMessages[currentMessages.length - 1];
  if (last.role !== "assistant") return;
  const updated = currentMessages.slice(0, -1).concat([{ ...last, text: text || "" }]);
  setState({ chat: { messages: updated } });
}

function addAnalyseMessage(role, text) {
  const currentMessages = getState().analyse.messages || [];
  setState({
    analyse: {
      messages: currentMessages.concat([{ role: role, text: text || "" }]),
    },
  });
  renderAnalyse(elements, getState());
}

function updateLastAnalyseMessageText(text) {
  const currentMessages = getState().analyse.messages || [];
  if (currentMessages.length === 0) return;
  const last = currentMessages[currentMessages.length - 1];
  if (last.role !== "assistant") return;
  const updated = currentMessages.slice(0, -1).concat([{ ...last, text: text || "" }]);
  setState({ analyse: { messages: updated } });
}

function addSagsbehandlingMessage(role, text) {
  const currentMessages = getState().sagsbehandling.messages || [];
  setState({
    sagsbehandling: {
      messages: currentMessages.concat([{ role: role, text: text || "" }]),
    },
  });
  renderSagsbehandling(elements, getState());
}

function updateSagsFactsForActiveSubtab(patch) {
  const state = getState();
  const subtab = state.sagsbehandling.activeSubtab || "skattepligt_ligningsfrist";
  const currentFactsBySubtab = state.sagsbehandling.factsBySubtab || {};
  const currentFacts = currentFactsBySubtab[subtab] || {};
  setState({
    sagsbehandling: {
      factsBySubtab: {
        ...currentFactsBySubtab,
        [subtab]: {
          ...currentFacts,
          ...patch,
        },
      },
    },
  });
}

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

function buildSagsCaseFactsPayload(subtab) {
  const state = getState();
  const factsBySubtab = state.sagsbehandling.factsBySubtab || {};
  const facts = factsBySubtab[subtab] || {};
  if (subtab !== "skattepligt_ligningsfrist") {
    return null;
  }
  const incomeYears = normalizeIncomeYearsInput(facts.incomeYears || "");
  const selectedFactors = Array.isArray(facts.selectedFactors) ? facts.selectedFactors : [];
  const factorDetails =
    facts.factorDetails && typeof facts.factorDetails === "object" ? facts.factorDetails : {};
  const selectedTriggerId = selectedFactors.length ? String(selectedFactors[0]) : "";
  const foreignIncomeTypes = Array.isArray(facts.foreignIncomeTypes) ? facts.foreignIncomeTypes : [];
  const foreignIncomeDetail = formatDanishList(
    foreignIncomeTypes.map((typeId) => FOREIGN_INCOME_TYPE_TITLES[typeId] || ""),
  );
  const specialTaxLiabilityMode = String(facts.specialTaxLiabilityMode || "").trim();
  const specialTaxLiabilityDetail = SPECIAL_TAX_LIABILITY_MODE_DETAILS[specialTaxLiabilityMode] || "";
  const foreignAssetsLiabilitiesType = String(facts.foreignAssetsLiabilitiesType || "").trim();
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
      if (!detailText) {
        return baseTitle;
      }
      return `${baseTitle}: ${detailText}`;
    })
    .filter((value) => String(value || "").trim().length > 0);
  const residenceMode = String(facts.residenceMode || "").trim();
  const residenceSinceYear = String(facts.residenceSinceYear || "").trim();
  const residenceFact = (() => {
    if (residenceMode === "always") {
      return "Da du altid har haft bopæl i Danmark";
    }
    if (residenceMode === "since_year") {
      return residenceSinceYear
        ? `Da du har haft bopæl i Danmark siden ${residenceSinceYear}`
        : "";
    }
    return String(facts.residenceFact || "").trim();
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
    self_employed_business_mode: String(facts.selfEmployedMode || "").trim(),
    self_employed_business_detail: String(factorDetails.self_employed_business || "").trim(),
    foreign_income_detail: foreignIncomeDetail,
    major_shareholder_status_detail: String(factorDetails.major_shareholder_status || "").trim(),
    special_tax_liability_conditions_detail: specialTaxLiabilityDetail,
    foreign_assets_liabilities_detail: foreignAssetsDetail,
  };
}

function ensureDefaultRetsgrundlagForSkattepligt() {
  const state = getState();
  const factsBySubtab = state.sagsbehandling.factsBySubtab || {};
  const currentFacts = factsBySubtab.skattepligt_ligningsfrist || {};
  const currentNotes = String(currentFacts.notes || "").trim();
  if (!currentNotes) {
    setState({
      sagsbehandling: {
        factsBySubtab: {
          ...factsBySubtab,
          skattepligt_ligningsfrist: {
            ...currentFacts,
            notes: DEFAULT_RETSGRUNDLAG_SKATTEPLIGT,
          },
        },
      },
    });
    renderSagsbehandling(elements, getState());
  }
}

async function loadLegalBasisForSubtab(subtab) {
  const safeSubtab = String(subtab || "").trim();
  if (!safeSubtab) {
    return;
  }
  if (safeSubtab === "skattepligt_ligningsfrist") {
    ensureDefaultRetsgrundlagForSkattepligt();
    return;
  }
  const state = getState();
  const loadingMap = state.sagsbehandling.legalBasisLoadingBySubtab || {};
  if (loadingMap[safeSubtab]) {
    return;
  }

  setState({
    sagsbehandling: {
      legalBasisLoadingBySubtab: {
        ...loadingMap,
        [safeSubtab]: true,
      },
    },
  });

  try {
    const data = await getSagsLegalBasis(safeSubtab);
    const documents = Array.isArray(data.documents)
      ? data.documents
          .map((item) => String(item || "").trim())
          .filter((item) => item.length > 0)
      : [];
    const legalBasisText = documents.join("\n");

    const currentState = getState();
    const currentFactsBySubtab = currentState.sagsbehandling.factsBySubtab || {};
    const currentFacts = currentFactsBySubtab[safeSubtab] || {};
    const previousAutoText =
      (currentState.sagsbehandling.autoLegalBasisTextBySubtab || {})[safeSubtab] || "";
    const currentNotes = String(currentFacts.notes || "");
    const shouldPrefill = !currentNotes.trim() || currentNotes === previousAutoText;

    const nextFactsBySubtab = {
      ...currentFactsBySubtab,
      [safeSubtab]: shouldPrefill
        ? {
            ...currentFacts,
            notes: legalBasisText,
          }
        : currentFacts,
    };

    setState({
      sagsbehandling: {
        factsBySubtab: nextFactsBySubtab,
        legalBasisBySubtab: {
          ...(currentState.sagsbehandling.legalBasisBySubtab || {}),
          [safeSubtab]: documents,
        },
        autoLegalBasisTextBySubtab: {
          ...(currentState.sagsbehandling.autoLegalBasisTextBySubtab || {}),
          [safeSubtab]: legalBasisText,
        },
      },
    });
  } catch (err) {
    setStatus("Kunne ikke hente retsgrundlag fra vector store: " + (err.message || "Ukendt fejl"), "error");
  } finally {
    const stateAfter = getState();
    const loadingAfter = stateAfter.sagsbehandling.legalBasisLoadingBySubtab || {};
    setState({
      sagsbehandling: {
        legalBasisLoadingBySubtab: {
          ...loadingAfter,
          [safeSubtab]: false,
        },
      },
    });
    renderSagsbehandling(elements, getState());
  }
}

function tryLogin() {
  const username = (elements.username.value || "").trim().toLowerCase();
  const password = elements.password.value || "";
  const expectedPassword = VALID_USERS[username];

  if (!expectedPassword || password !== expectedPassword) {
    showLogin("Forkert brugernavn eller adgangskode.", "error");
    return;
  }

  setActiveUser(username);
  elements.password.value = "";
  showApp(username);
}

async function logout() {
  setLoading(true);
  try {
    const sessionId = getOrCreateChatSessionId();
    try {
      await clearChatContextFiles(sessionId);
    } catch (_err) {
      // Hvis cleanup fejler, må logout stadig gennemføres.
    }
    resetChatSessionId();
    clearActiveUser();
    resetAnalyse();
    resetChat();
    elements.password.value = "";
    showLogin("Du er logget ud.", "ok");
  } finally {
    setLoading(false);
  }
}

async function runAnalyse() {
  const question = (elements.question ? elements.question.value : "").trim();
  if (!question) {
    setStatus("Skriv et spørgsmål først.", "error");
    return;
  }

  setState({
    analyse: {
      question: question,
    },
  });
  addAnalyseMessage("user", question);
  setState({
    analyse: {
      question: "",
    },
  });
  renderAnalyse(elements, getState());

  setLoading(true);
  setStatus("Sender forespørgsel til backend...", "ok");
  if (analyseAbortController) analyseAbortController.abort();
  analyseAbortController = new AbortController();
  if (elements.analyzeAbortBtn) elements.analyzeAbortBtn.disabled = false;

  const useStream = true;
  try {
    const previousResponseId = getState().analyse.previousResponseId;
    const ctx = {
      sourceTab: "analyse",
      subtab: null,
      signal: analyseAbortController.signal,
    };
    if (useStream) {
      addAnalyseMessage("assistant", "");
      renderAnalyse(elements, getState());
      let accumulated = "";
      await analyzeQuestionStream(question, previousResponseId, ctx, (evt) => {
        if (evt.type === "delta" && evt.text) {
          accumulated += evt.text;
          updateLastAnalyseMessageText(accumulated);
          renderAnalyse(elements, getState());
        } else if (evt.type === "done") {
          const answer = evt.answer || accumulated || "Intet svar returneret.";
          const prev = getState().analyse || {};
          setState({
            analyse: {
              ...prev,
              answer,
              usedModel: evt.used_model || null,
              citations: evt.citations || [],
              retrievalResults: evt.retrieval_results || [],
              logPdfUrl: evt.log_pdf_url || "",
              logPdfLabel: evt.log_pdf_filename || "Åbn PDF-log",
              previousResponseId: evt.response_id || null,
            },
          });
          updateLastAnalyseMessageText(answer);
          renderAnalyse(elements, getState());
          setStatus("Analyse færdig. Model: " + (evt.used_model || "ukendt"), "ok");
          const user = getActiveUser();
          if (user) {
            saveAnalyseLog(user, {
              question,
              answer,
              citations: evt.citations || [],
              retrieval_results: evt.retrieval_results || [],
              used_model: evt.used_model || "",
              used_vector_store_ids: evt.used_vector_store_ids || null,
              log_pdf_filename: evt.log_pdf_filename || null,
              log_pdf_url: evt.log_pdf_url || null,
            })
              .then((saved) => {
                const prev = getState().analyse || {};
                const logs = [
                  {
                    id: saved.id,
                    created_at: saved.created_at,
                    title: saved.title,
                    log_pdf_filename: saved.log_pdf_filename || null,
                    log_pdf_url: saved.log_pdf_url || null,
                  },
                  ...(prev.savedLogs || []),
                ];
                setState({ analyse: { savedLogs: logs } });
                renderAnalyse(elements, getState());
              })
              .catch(() => {});
          }
        } else if (evt.type === "error") {
          throw new Error(evt.detail || "Streamfejl");
        }
      });
    } else {
      const data = await analyzeQuestion(question, previousResponseId, ctx);
      const prev = getState().analyse || {};
      setState({
        analyse: {
          ...prev,
          answer: data.answer || "Intet svar returneret.",
          usedModel: data.used_model || null,
          citations: data.citations || [],
          retrievalResults: data.retrieval_results || [],
          logPdfUrl: data.log_pdf_url || "",
          logPdfLabel: data.log_pdf_filename || "Åbn PDF-log",
          previousResponseId: data.response_id || null,
        },
      });
      addAnalyseMessage("assistant", data.answer || "Intet svar returneret.");
      renderAnalyse(elements, getState());
      setStatus("Analyse færdig. Model: " + (data.used_model || "ukendt"), "ok");
      const user = getActiveUser();
      if (user) {
        saveAnalyseLog(user, {
          question,
          answer: data.answer || "",
          citations: data.citations || [],
          retrieval_results: data.retrieval_results || [],
          used_model: data.used_model || "",
          used_vector_store_ids: null,
          log_pdf_filename: data.log_pdf_filename || null,
          log_pdf_url: data.log_pdf_url || null,
        })
          .then((saved) => {
            const prev = getState().analyse || {};
            const logs = [
              {
                id: saved.id,
                created_at: saved.created_at,
                title: saved.title,
                log_pdf_filename: saved.log_pdf_filename || null,
                log_pdf_url: saved.log_pdf_url || null,
              },
              ...(prev.savedLogs || []),
            ];
            setState({ analyse: { savedLogs: logs } });
            renderAnalyse(elements, getState());
          })
          .catch(() => {});
      }
    }
  } catch (err) {
    const isAborted = err && err.name === "AbortError";
    const errorText = isAborted ? "Afbrudt" : (err && err.message ? err.message : "Ukendt fejl");
    setState({
      analyse: {
        answer: "Kunne ikke hente svar: " + errorText,
        citations: [],
        logPdfUrl: "",
        logPdfLabel: "",
      },
    });
    addAnalyseMessage("system", isAborted ? "Afbrudt af bruger." : "Fejl: " + errorText);
    renderAnalyse(elements, getState());
    setStatus(isAborted ? "Afbrudt." : "Fejl: " + errorText, isAborted ? "ok" : "error");
  } finally {
    analyseAbortController = null;
    setLoading(false);
  }
}

async function runSagsbehandling() {
  const activeSubtab = (getState().sagsbehandling.activeSubtab || "").trim();
  if (activeSubtab !== "skattepligt_ligningsfrist") {
    addSagsbehandlingMessage(
      "system",
      "Denne undertab er ikke aktiveret endnu. Brug 'Skattepligt og ligningsfrist'.",
    );
    setStatus("Undertab er ikke aktiveret endnu.", "error");
    return;
  }

  const caseFacts = buildSagsCaseFactsPayload(activeSubtab) || {};
  const missingRequiredFacts = [];
  if (!String(caseFacts.income_years || "").trim()) {
    missingRequiredFacts.push("Indkomstår");
  }
  if (!Array.isArray(caseFacts.selected_factors) || caseFacts.selected_factors.length !== 1) {
    missingRequiredFacts.push("Vælg præcis én trigger");
  }
  if (
    Array.isArray(caseFacts.selected_factors) &&
    caseFacts.selected_factors.includes("self_employed_business") &&
    !String(caseFacts.self_employed_business_mode || "").trim()
  ) {
    missingRequiredFacts.push("Vælg underkategori for selvstændig erhvervsvirksomhed");
  }
  if (
    Array.isArray(caseFacts.selected_factors) &&
    caseFacts.selected_factors.includes("foreign_income") &&
    (!Array.isArray(caseFacts.foreign_income_types) || caseFacts.foreign_income_types.length === 0)
  ) {
    missingRequiredFacts.push("Vælg mindst én type under indkomst fra udlandet");
  }
  if (
    Array.isArray(caseFacts.selected_factors) &&
    caseFacts.selected_factors.includes("major_shareholder_status") &&
    !String(caseFacts.major_shareholder_status_detail || "").trim()
  ) {
    missingRequiredFacts.push("Skriv navnet på selskabet");
  }
  if (
    Array.isArray(caseFacts.selected_factors) &&
    caseFacts.selected_factors.includes("special_tax_liability_conditions") &&
    !String(caseFacts.special_tax_liability_mode || "").trim()
  ) {
    missingRequiredFacts.push("Vælg underpunkt for særlige skattepligtsforhold");
  }
  if (
    Array.isArray(caseFacts.selected_factors) &&
    caseFacts.selected_factors.includes("foreign_assets_liabilities_significant") &&
    !String(caseFacts.foreign_assets_liabilities_type || "").trim()
  ) {
    missingRequiredFacts.push("Vælg formueforhold under aktiver/passiver i udlandet");
  }
  const isGrensegaenger = Array.isArray(caseFacts.selected_factors) &&
    caseFacts.selected_factors.includes("cross_border_commuter_taxation");
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
  if (missingRequiredFacts.length) {
    setStatus("Udfyld obligatoriske felter: " + missingRequiredFacts.join(", "), "error");
    return;
  }

  const generatedQuestion =
    "Foretag en samlet juridisk vurdering af, om borgeren er omfattet af kort eller ordinær ligningsfrist på baggrund af de oplyste fakta.";
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
  const residenceLine = isGrensegaenger
    ? ""
    : "\n- Bopælsfaktum: " + String(caseFacts.residence_fact || "");
  addSagsbehandlingMessage(
    "user",
    "Fakta sendt til vurdering:\n- Indkomstår: "
      + String(caseFacts.income_years || "")
      + "\n- Valgt underpunkt: "
      + selectedFactorText
      + residenceLine,
  );
  renderSagsbehandling(elements, getState());

  setLoading(true);
  setStatus("Sender forespørgsel til backend...", "ok");
  try {
    const previousResponseId = getState().sagsbehandling.previousResponseId || null;
    const data = await analyzeQuestion(generatedQuestion, previousResponseId, {
      sourceTab: "sagsbehandling",
      subtab: "skattepligt_ligningsfrist",
      caseFacts: caseFacts,
    });
    setState({
      sagsbehandling: {
        previousResponseId: data.response_id || null,
        usedModel: data.used_model || null,
      },
    });
    addSagsbehandlingMessage("assistant", data.answer || "Intet svar returneret.");
    setStatus("Sagsbehandling svar modtaget. Model: " + (data.used_model || "ukendt"), "ok");
  } catch (err) {
    const errorText = err && err.message ? err.message : "Ukendt fejl";
    addSagsbehandlingMessage("system", "Fejl: " + errorText);
    setStatus("Fejl: " + errorText, "error");
  } finally {
    setLoading(false);
  }
}

function clearSagsbehandlingCurrentSubtab() {
  const state = getState();
  const activeSubtab = state.sagsbehandling.activeSubtab || "skattepligt_ligningsfrist";
  const factsBySubtab = state.sagsbehandling.factsBySubtab || {};

  setState({
    sagsbehandling: {
      messages: [],
      previousResponseId: null,
      usedModel: null,
      factsBySubtab: {
        ...factsBySubtab,
        [activeSubtab]: {
          incomeYears: "",
          foreignIncome: "",
          foreignAssetsLiabilities: "",
          residenceFact: "",
          residenceMode: "",
          residenceSinceYear: "",
          notes: "",
          selectedFactors: [],
          factorDetails: {},
          foreignIncomeTypes: [],
          foreignAssetsLiabilitiesType: "",
          specialTaxLiabilityMode: "",
        },
      },
    },
  });
  renderSagsbehandling(elements, getState());
  setStatus("Sagsbehandling ryddet for aktiv undertab.", "ok");
}

async function runChat() {
  const message = (elements.chatInput ? elements.chatInput.value : "").trim();
  if (!message) {
    setStatus("Skriv en chatbesked først.", "error");
    return;
  }

  addChatMessage("user", message);
  setState({
    chat: {
      inputText: "",
    },
  });
  renderChat(elements, getState());

  setLoading(true);
  setStatus("Sender chatbesked...", "ok");
  if (chatAbortController) chatAbortController.abort();
  chatAbortController = new AbortController();
  if (elements.chatAbortBtn) elements.chatAbortBtn.disabled = false;

  const useStream = true;
  try {
    const previousResponseId = getState().chat.previousResponseId;
    const sessionId = getOrCreateChatSessionId();
    const opts = { signal: chatAbortController.signal };
    if (useStream) {
      addChatMessage("assistant", "");
      renderChat(elements, getState());
      let accumulated = "";
      await sendChatStream(message, previousResponseId, sessionId, opts, (evt) => {
        if (evt.type === "delta" && evt.text) {
          accumulated += evt.text;
          updateLastChatMessageText(accumulated);
          renderChat(elements, getState());
        } else if (evt.type === "done") {
          setState({
            chat: {
              previousResponseId: evt.response_id || null,
              usedModel: evt.used_model || null,
            },
          });
          updateLastChatMessageText(evt.answer || accumulated || "Intet svar returneret.");
          renderChat(elements, getState());
          setStatus("Chat svar modtaget. Model: " + (evt.used_model || "ukendt"), "ok");
        } else if (evt.type === "error") {
          throw new Error(evt.detail || "Streamfejl");
        }
      });
    } else {
      const data = await sendChat(message, previousResponseId, sessionId, opts);
      setState({
        chat: {
          previousResponseId: data.response_id || null,
          usedModel: data.used_model || null,
        },
      });
      addChatMessage("assistant", data.answer || "Intet svar returneret.");
      setStatus("Chat svar modtaget. Model: " + (data.used_model || "ukendt"), "ok");
    }
  } catch (err) {
    const isAborted = err && err.name === "AbortError";
    const msg = isAborted ? "Afbrudt af bruger." : "Fejl: " + (err && err.message ? err.message : "Ukendt fejl");
    addChatMessage("system", msg);
    setStatus(isAborted ? "Afbrudt." : "Fejl: " + (err && err.message ? err.message : "Ukendt fejl"), isAborted ? "ok" : "error");
  } finally {
    chatAbortController = null;
    setLoading(false);
  }
}

async function refreshChatContextFiles() {
  try {
    const sessionId = getOrCreateChatSessionId();
    const files = await getChatContextFiles(sessionId);
    setState({
      chat: {
        contextFiles: files,
      },
    });
    renderChat(elements, getState());
  } catch (err) {
    setStatus("Fejl ved hentning af kontekstfiler: " + (err.message || "Ukendt fejl"), "error");
  }
}

async function uploadContextFromInput() {
  const fileInput = elements.chatContextFile;
  if (!fileInput || !fileInput.files || !fileInput.files.length) {
    setStatus("Vælg en fil først.", "error");
    return;
  }
  const file = fileInput.files[0];
  await uploadContextFile(file, "upload");
  fileInput.value = "";
}

async function uploadContextFile(file, sourceLabel) {
  if (!file) {
    setStatus("Ingen fil fundet.", "error");
    return;
  }

  const actionLabel = sourceLabel === "paste" ? "Indsætter kontekstfil fra clipboard..." : "Uploader kontekstfil...";
  setLoading(true);
  setStatus(actionLabel, "ok");
  try {
    const sessionId = getOrCreateChatSessionId();
    const files = await uploadChatContextFile(file, sessionId);
    setState({
      chat: {
        contextFiles: files,
      },
    });
    renderChat(elements, getState());
    setStatus("Kontekstfil uploadet og aktiv i Chat.", "ok");
  } catch (err) {
    setStatus("Fejl ved upload af kontekstfil: " + (err.message || "Ukendt fejl"), "error");
  } finally {
    setLoading(false);
  }
}

async function removeContextFile(contextId) {
  if (!contextId) {
    return;
  }
  setLoading(true);
  setStatus("Fjerner kontekstfil...", "ok");
  try {
    const sessionId = getOrCreateChatSessionId();
    const files = await deleteChatContextFile(contextId, sessionId);
    setState({
      chat: {
        contextFiles: files,
      },
    });
    if (elements.chatContextFile) {
      elements.chatContextFile.value = "";
    }
    renderChat(elements, getState());
    setStatus("Kontekstfil er fjernet.", "ok");
  } catch (err) {
    setStatus("Fejl ved fjernelse af kontekstfil: " + (err.message || "Ukendt fejl"), "error");
  } finally {
    setLoading(false);
  }
}

async function saveChatToPdf() {
  const messages = getState().chat.messages || [];
  if (!messages.length) {
    setStatus("Der er ingen chatbeskeder at gemme endnu.", "error");
    return;
  }

  setLoading(true);
  setStatus("Genererer chat-PDF...", "ok");
  try {
    const sessionId = getOrCreateChatSessionId();
    const data = await exportChatPdf(messages, sessionId);
    const link = document.createElement("a");
    link.href = data.log_pdf_url || "#";
    link.download = data.log_pdf_filename || "chat_log.pdf";
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    document.body.appendChild(link);
    link.click();
    link.remove();
    setStatus("Chat-PDF er klar til download.", "ok");
  } catch (err) {
    setStatus("Fejl ved PDF-eksport: " + (err.message || "Ukendt fejl"), "error");
  } finally {
    setLoading(false);
  }
}

function downloadAnalysePdf() {
  const url = getState().analyse.logPdfUrl || "";
  if (!url) {
    setStatus("Der er ingen analyse-PDF at hente endnu.", "error");
    return;
  }
  const link = document.createElement("a");
  link.href = url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  document.body.appendChild(link);
  link.click();
  link.remove();
}

function bindEvents() {
  elements.tabButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      switchTab(btn.dataset.tab || "analyse");
    });
  });

  if (elements.analyzeBtn) {
    elements.analyzeBtn.addEventListener("click", runAnalyse);
  }
  if (elements.analyzeAbortBtn) {
    elements.analyzeAbortBtn.addEventListener("click", () => {
      if (analyseAbortController) analyseAbortController.abort();
    });
  }
  if (elements.chatSendBtn) {
    elements.chatSendBtn.addEventListener("click", runChat);
  }
  if (elements.chatAbortBtn) {
    elements.chatAbortBtn.addEventListener("click", () => {
      if (chatAbortController) chatAbortController.abort();
    });
  }
  if (elements.sagsbehandlingSendBtn) {
    elements.sagsbehandlingSendBtn.addEventListener("click", runSagsbehandling);
  }
  if (elements.sagsbehandlingClearBtn) {
    elements.sagsbehandlingClearBtn.addEventListener("click", clearSagsbehandlingCurrentSubtab);
  }
  if (elements.chatResetBtn) {
    elements.chatResetBtn.addEventListener("click", resetChatWithCleanup);
  }
  if (elements.chatSavePdfBtn) {
    elements.chatSavePdfBtn.addEventListener("click", saveChatToPdf);
  }
  if (elements.chatContextUploadBtn) {
    elements.chatContextUploadBtn.addEventListener("click", uploadContextFromInput);
  }
  if (elements.loginBtn) {
    elements.loginBtn.addEventListener("click", tryLogin);
  }
  if (elements.logoutBtn) {
    elements.logoutBtn.addEventListener("click", logout);
  }
  if (elements.resetBtn) {
    elements.resetBtn.addEventListener("click", resetAnalyse);
  }
  if (elements.pdfLogLink) {
    elements.pdfLogLink.addEventListener("click", downloadAnalysePdf);
  }
  if (elements.chatContextList) {
    elements.chatContextList.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      const contextId = target.getAttribute("data-context-id");
      if (!contextId) {
        return;
      }
      removeContextFile(contextId);
    });
  }

  if (elements.analyseLogContent) {
    elements.analyseLogContent.addEventListener("click", (event) => {
      const el = event.target.nodeType === Node.ELEMENT_NODE ? event.target : event.target.parentElement;
      if (!el) return;
      const entryBtn = el.closest(".analyse-log-entry");
      if (entryBtn?.dataset?.entryId) {
        onAnalyseLogEntryClick(entryBtn.dataset.entryId);
        return;
      }
      if (el.closest("[data-action=log-back]")) {
        onAnalyseLogBackClick();
      }
    });
  }

  if (elements.sagsSubtabButtons && elements.sagsSubtabButtons.length) {
    elements.sagsSubtabButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        const subtab = btn.dataset.sagsSubtab || "skattepligt_ligningsfrist";
        setState({
          sagsbehandling: {
            activeSubtab: subtab,
            activeFunction: "",
            inputText: "",
            messages: [],
            previousResponseId: null,
            usedModel: null,
            factsPanelOpen: false,
          },
        });
        renderSagsbehandling(elements, getState());
        loadLegalBasisForSubtab(subtab);
      });
    });
  }

  if (elements.password) {
    elements.password.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        tryLogin();
      }
    });
  }

  if (elements.question) {
    elements.question.addEventListener("input", () => {
      setState({
        analyse: {
          question: elements.question.value,
        },
      });
    });

    elements.question.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        runAnalyse();
      }
    });
  }

  if (elements.chatInput) {
    elements.chatInput.addEventListener("input", () => {
      setState({
        chat: {
          inputText: elements.chatInput.value,
        },
      });
    });

    elements.chatInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        runChat();
      }
    });

    elements.chatInput.addEventListener("paste", (event) => {
      const clipboard = event.clipboardData;
      if (!clipboard) {
        return;
      }

      const candidateFiles = [];
      if (clipboard.files && clipboard.files.length) {
        for (const file of clipboard.files) {
          candidateFiles.push(file);
        }
      } else if (clipboard.items && clipboard.items.length) {
        for (const item of clipboard.items) {
          if (item.kind === "file") {
            const file = item.getAsFile();
            if (file) {
              candidateFiles.push(file);
            }
          }
        }
      }

      if (!candidateFiles.length) {
        return;
      }

      event.preventDefault();
      uploadContextFile(candidateFiles[0], "paste");
    });
  }

  if (elements.sagsFunctionList) {
    elements.sagsFunctionList.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      const button = target.closest("[data-sags-function]");
      if (!(button instanceof HTMLElement)) {
        return;
      }
      const functionLabel = button.dataset.sagsFunction || "";
      if (!functionLabel) {
        return;
      }
      setState({
        sagsbehandling: {
          activeFunction: functionLabel,
        },
      });
      renderSagsbehandling(elements, getState());
    });
  }

  if (elements.sagsFactsToggleBtn) {
    elements.sagsFactsToggleBtn.addEventListener("click", () => {
      const isOpen = Boolean(getState().sagsbehandling.factsPanelOpen);
      const activeSubtab = getState().sagsbehandling.activeSubtab || "skattepligt_ligningsfrist";
      setState({
        sagsbehandling: {
          factsPanelOpen: !isOpen,
        },
      });
      renderSagsbehandling(elements, getState());
      if (!isOpen) {
        loadLegalBasisForSubtab(activeSubtab);
      }
    });
  }

  if (elements.sagsFactsCloseBtn) {
    elements.sagsFactsCloseBtn.addEventListener("click", () => {
      setState({
        sagsbehandling: {
          factsPanelOpen: false,
        },
      });
      renderSagsbehandling(elements, getState());
    });
  }

  if (elements.sagsFactsSaveBtn) {
    elements.sagsFactsSaveBtn.addEventListener("click", () => {
      const activeSubtab = getState().sagsbehandling.activeSubtab || "skattepligt_ligningsfrist";
      if (activeSubtab === "skattepligt_ligningsfrist") {
        const currentFactsBySubtab = getState().sagsbehandling.factsBySubtab || {};
        const currentFacts = currentFactsBySubtab[activeSubtab] || {};
        const normalizedIncomeYears = normalizeIncomeYearsInput(currentFacts.incomeYears || "");
        if (normalizedIncomeYears !== (currentFacts.incomeYears || "")) {
          updateSagsFactsForActiveSubtab({
            incomeYears: normalizedIncomeYears,
          });
          renderSagsbehandling(elements, getState());
        }
      }
      addSagsbehandlingMessage(
        "system",
        "Fakta gemt for undertab: " + activeSubtab + ".",
      );
      setState({
        sagsbehandling: {
          factsPanelOpen: false,
        },
      });
      renderSagsbehandling(elements, getState());
      setStatus("Fakta gemt lokalt.", "ok");
    });
  }

  if (elements.sagsFactsClearBtn) {
    elements.sagsFactsClearBtn.addEventListener("click", () => {
      updateSagsFactsForActiveSubtab({
        incomeYears: "",
        foreignIncome: "",
        foreignAssetsLiabilities: "",
        residenceFact: "",
        residenceMode: "",
        residenceSinceYear: "",
        notes: "",
        selectedFactors: [],
        factorDetails: {},
        foreignIncomeTypes: [],
        foreignAssetsLiabilitiesType: "",
        specialTaxLiabilityMode: "",
        selfEmployedMode: "",
      });
      renderSagsbehandling(elements, getState());
      setStatus("Fakta ryddet lokalt.", "ok");
    });
  }

  if (elements.sagsFactsIncomeYears) {
    elements.sagsFactsIncomeYears.addEventListener("input", () => {
      updateSagsFactsForActiveSubtab({
        incomeYears: elements.sagsFactsIncomeYears.value,
      });
    });
    elements.sagsFactsIncomeYears.addEventListener("blur", () => {
      const activeSubtab = getState().sagsbehandling.activeSubtab || "";
      if (activeSubtab !== "skattepligt_ligningsfrist") {
        return;
      }
      const normalizedValue = normalizeIncomeYearsInput(elements.sagsFactsIncomeYears.value);
      updateSagsFactsForActiveSubtab({
        incomeYears: normalizedValue,
      });
      renderSagsbehandling(elements, getState());
    });
  }

  if (elements.sagsFactsForeignIncome) {
    elements.sagsFactsForeignIncome.addEventListener("input", () => {
      updateSagsFactsForActiveSubtab({
        foreignIncome: elements.sagsFactsForeignIncome.value,
      });
    });
  }

  if (elements.sagsFactsForeignAssetsLiabilities) {
    elements.sagsFactsForeignAssetsLiabilities.addEventListener("input", () => {
      updateSagsFactsForActiveSubtab({
        foreignAssetsLiabilities: elements.sagsFactsForeignAssetsLiabilities.value,
      });
    });
  }

  if (elements.sagsFactsResidence) {
    elements.sagsFactsResidence.addEventListener("input", () => {
      const activeSubtab = getState().sagsbehandling.activeSubtab || "";
      if (activeSubtab === "skattepligt_ligningsfrist") {
        return;
      }
      updateSagsFactsForActiveSubtab({
        residenceFact: elements.sagsFactsResidence.value,
      });
    });
  }

  if (elements.sagsFactsResidenceOptions) {
    elements.sagsFactsResidenceOptions.addEventListener("change", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement)) {
        return;
      }
      const residenceMode = String(target.dataset.sagsResidenceMode || "").trim();
      if (!residenceMode || !target.checked) {
        return;
      }
      const activeSubtab = getState().sagsbehandling.activeSubtab || "";
      if (activeSubtab !== "skattepligt_ligningsfrist") {
        return;
      }
      updateSagsFactsForActiveSubtab({
        residenceMode: residenceMode,
        residenceSinceYear: residenceMode === "since_year"
          ? String(((getState().sagsbehandling.factsBySubtab || {})[activeSubtab] || {}).residenceSinceYear || "")
          : "",
        residenceFact: "",
      });
      renderSagsbehandling(elements, getState());
    });

    elements.sagsFactsResidenceOptions.addEventListener("input", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement)) {
        return;
      }
      if (String(target.dataset.sagsResidenceSinceYear || "").trim() !== "true") {
        return;
      }
      const activeSubtab = getState().sagsbehandling.activeSubtab || "";
      if (activeSubtab !== "skattepligt_ligningsfrist") {
        return;
      }
      updateSagsFactsForActiveSubtab({
        residenceSinceYear: target.value,
      });
    });
  }

  if (elements.sagsFactsResidenceSinceYear) {
    elements.sagsFactsResidenceSinceYear.addEventListener("input", () => {
      const activeSubtab = getState().sagsbehandling.activeSubtab || "";
      if (activeSubtab !== "skattepligt_ligningsfrist") {
        return;
      }
      updateSagsFactsForActiveSubtab({
        residenceSinceYear: elements.sagsFactsResidenceSinceYear.value,
      });
    });
  }

  if (elements.sagsFactsNotes) {
    elements.sagsFactsNotes.addEventListener("input", () => {
      updateSagsFactsForActiveSubtab({
        notes: elements.sagsFactsNotes.value,
      });
    });
  }

  if (elements.sagsFactsFactorChecklist) {
    elements.sagsFactsFactorChecklist.addEventListener("change", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement)) {
        return;
      }
      const factorId = String(target.dataset.sagsFactorId || "").trim();
      if (!factorId) {
        return;
      }
      const activeSubtab = getState().sagsbehandling.activeSubtab || "";
      if (activeSubtab !== "skattepligt_ligningsfrist") {
        return;
      }
      const factsBySubtab = getState().sagsbehandling.factsBySubtab || {};
      const currentFacts = factsBySubtab[activeSubtab] || {};
      const nextSelfEmployedMode =
        factorId === "self_employed_business" && target.checked
          ? ""
          : "";
      const nextSpecialTaxLiabilityMode =
        factorId === "special_tax_liability_conditions" && target.checked
          ? ""
          : "";
      const nextForeignAssetsLiabilitiesType =
        factorId === "foreign_assets_liabilities_significant" && target.checked
          ? ""
          : "";
      updateSagsFactsForActiveSubtab({
        selectedFactors: target.checked ? [factorId] : [],
        selfEmployedMode: nextSelfEmployedMode,
        specialTaxLiabilityMode: nextSpecialTaxLiabilityMode,
        foreignAssetsLiabilitiesType: nextForeignAssetsLiabilitiesType,
      });
      renderSagsbehandling(elements, getState());
    });

    elements.sagsFactsFactorChecklist.addEventListener("change", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement)) {
        return;
      }
      const foreignIncomeTypeId = String(target.dataset.sagsForeignIncomeType || "").trim();
      if (foreignIncomeTypeId) {
        const activeSubtab = getState().sagsbehandling.activeSubtab || "";
        if (activeSubtab !== "skattepligt_ligningsfrist") {
          return;
        }
        const currentFacts = (getState().sagsbehandling.factsBySubtab || {})[activeSubtab] || {};
        const selectedFactors = Array.isArray(currentFacts.selectedFactors)
          ? currentFacts.selectedFactors
          : [];
        if (!selectedFactors.includes("foreign_income")) {
          return;
        }
        const nextTypes = target.checked ? [foreignIncomeTypeId] : [];
        updateSagsFactsForActiveSubtab({
          foreignIncomeTypes: nextTypes,
        });
        return;
      }
      const foreignAssetsTypeId = String(target.dataset.sagsForeignAssetsType || "").trim();
      if (foreignAssetsTypeId) {
        const activeSubtab = getState().sagsbehandling.activeSubtab || "";
        if (activeSubtab !== "skattepligt_ligningsfrist") {
          return;
        }
        const currentFacts = (getState().sagsbehandling.factsBySubtab || {})[activeSubtab] || {};
        const selectedFactors = Array.isArray(currentFacts.selectedFactors)
          ? currentFacts.selectedFactors
          : [];
        if (!selectedFactors.includes("foreign_assets_liabilities_significant")) {
          return;
        }
        const nextType = target.checked ? foreignAssetsTypeId : "";
        updateSagsFactsForActiveSubtab({
          foreignAssetsLiabilitiesType: nextType,
        });
        renderSagsbehandling(elements, getState());
        return;
      }
      const modeId = String(target.dataset.sagsSelfEmployedMode || "").trim();
      if (!modeId || !target.checked) {
        const specialModeId = String(target.dataset.sagsSpecialTaxLiabilityMode || "").trim();
        if (!specialModeId || !target.checked) {
          return;
        }
        const activeSubtab = getState().sagsbehandling.activeSubtab || "";
        if (activeSubtab !== "skattepligt_ligningsfrist") {
          return;
        }
        const currentFacts = (getState().sagsbehandling.factsBySubtab || {})[activeSubtab] || {};
        const selectedFactors = Array.isArray(currentFacts.selectedFactors)
          ? currentFacts.selectedFactors
          : [];
        if (!selectedFactors.includes("special_tax_liability_conditions")) {
          return;
        }
        updateSagsFactsForActiveSubtab({
          specialTaxLiabilityMode: specialModeId,
        });
        renderSagsbehandling(elements, getState());
        return;
      }
      const activeSubtab = getState().sagsbehandling.activeSubtab || "";
      if (activeSubtab !== "skattepligt_ligningsfrist") {
        return;
      }
      const currentFacts = (getState().sagsbehandling.factsBySubtab || {})[activeSubtab] || {};
      const selectedFactors = Array.isArray(currentFacts.selectedFactors)
        ? currentFacts.selectedFactors
        : [];
      if (!selectedFactors.includes("self_employed_business")) {
        return;
      }
      updateSagsFactsForActiveSubtab({
        selfEmployedMode: modeId,
      });
      renderSagsbehandling(elements, getState());
    });

    elements.sagsFactsFactorChecklist.addEventListener("input", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLTextAreaElement)) {
        return;
      }
      const factorId = String(target.dataset.sagsFactorDetailId || "").trim();
      if (!factorId) {
        return;
      }
      const activeSubtab = getState().sagsbehandling.activeSubtab || "";
      if (activeSubtab !== "skattepligt_ligningsfrist") {
        return;
      }
      const factsBySubtab = getState().sagsbehandling.factsBySubtab || {};
      const currentFacts = factsBySubtab[activeSubtab] || {};
      const currentFactorDetails =
        currentFacts.factorDetails && typeof currentFacts.factorDetails === "object"
          ? currentFacts.factorDetails
          : {};
      updateSagsFactsForActiveSubtab({
        factorDetails: {
          ...currentFactorDetails,
          [factorId]: target.value,
        },
      });
    });
  }
}

function init() {
  setState({
    ui: {
      activeTab: getActiveTab("chat"),
    },
  });
  bindEvents();
  const activeUser = getActiveUser();
  getOrCreateChatSessionId();
  refreshChatContextFiles();
  if (activeUser && Object.prototype.hasOwnProperty.call(VALID_USERS, activeUser)) {
    showApp(activeUser);
  } else {
    showLogin("Log ind for at bruge systemet.", "ok");
  }
}

init();
