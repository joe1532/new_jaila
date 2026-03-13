import { analyzeQuestion, analyzeQuestionStream } from "./api/analyzeApi.js";
import {
  deleteAnalyseLog,
  getAnalyseLog,
  listAnalyseLogs,
  saveAnalyseLog,
} from "./api/analyseLogsApi.js";
import { deleteChatLog, getChatLog, listChatLogs, saveChatLog } from "./api/chatLogsApi.js";
import { createCase, deleteCase, getCase, listCases, updateCase } from "./api/casesApi.js";
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
  setChatSessionId,
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

const SAGS_CONTEXT_TARGET_SUBTABS = [
  { id: "opgoerelse_indkomst", label: "Opgørelse af indkomst" },
  { id: "beskatningsret_indkomst", label: "Beskatningsret til indkomst" },
  { id: "lempelse", label: "Lempelse" },
  { id: "andet", label: "Andet" },
];
const BESKATNINGSRET_AUTO_CONTEXT_SOURCES = [
  "skattepligt_ligningsfrist",
  "opgoerelse_indkomst",
];
const SAGS_SUBTAB_LABELS = {
  skattepligt_ligningsfrist: "Skattepligt og ligningsfrist",
  opgoerelse_indkomst: "Opgørelse af indkomst",
  beskatningsret_indkomst: "Beskatningsret til indkomst",
  lempelse: "Lempelse",
  andet: "Andet",
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
  sagsbehandlingCopyAnswerBtn: document.getElementById("sagsbehandlingCopyAnswerBtn"),
  sagsbehandlingLockBtn: document.getElementById("sagsbehandlingLockBtn"),
  sagsbehandlingClearBtn: document.getElementById("sagsbehandlingClearBtn"),
  sagsStartCaseBtn: document.getElementById("sagsStartCaseBtn"),
  sagsRenameCaseBtn: document.getElementById("sagsRenameCaseBtn"),
  sagsDeleteCaseBtn: document.getElementById("sagsDeleteCaseBtn"),
  sagsCaseSelect: document.getElementById("sagsCaseSelect"),
  sagsContextPanel: document.getElementById("sagsContextPanel"),
  sagsContextTitle: document.getElementById("sagsContextTitle"),
  sagsContextList: document.getElementById("sagsContextList"),
  sagsContextClearBtn: document.getElementById("sagsContextClearBtn"),
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
  sagsFactsBeskatningsretCountryBlock: document.getElementById("sagsFactsBeskatningsretCountryBlock"),
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
  chatLogContent: document.getElementById("chatLogContent"),
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
let sagsCaseSaveChain = Promise.resolve();
let sagsCaseSaveDebounceTimer = null;
const SAGS_CASE_SAVE_DEBOUNCE_MS = 400;

function generateLocalSessionId(prefix) {
  const safePrefix = String(prefix || "session");
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `${safePrefix}_${crypto.randomUUID()}`;
  }
  return `${safePrefix}_${Date.now()}_${Math.floor(Math.random() * 1_000_000)}`;
}

function getOrCreateAnalyseSessionId() {
  const current = String((getState().analyse || {}).sessionId || "").trim();
  if (current) {
    return current;
  }
  const created = generateLocalSessionId("analyse");
  setState({
    analyse: {
      sessionId: created,
    },
  });
  return created;
}

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
  if (elements.sagsbehandlingCopyAnswerBtn && isLoading) {
    elements.sagsbehandlingCopyAnswerBtn.disabled = true;
  }
  if (elements.sagsbehandlingLockBtn && isLoading) {
    elements.sagsbehandlingLockBtn.disabled = true;
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
  updateSagsCaseSelector();
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
  } else if (tabId === "chat") {
    loadChatSavedLogs();
  } else if (tabId === "sagsbehandling") {
    refreshSagsCases();
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
  refreshSagsCases();
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
      sessionId: generateLocalSessionId("analyse"),
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

async function onDeleteAnalyseLog(entryId) {
  const user = getActiveUser();
  if (!user || !entryId) return;
  if (!window.confirm("Vil du slette denne gemte analyse?")) {
    return;
  }
  try {
    const res = await deleteAnalyseLog(user, entryId);
    const prev = getState().analyse || {};
    setState({
      analyse: {
        ...prev,
        savedLogs: res.entries || [],
        selectedLogId: null,
        selectedLogContent: null,
      },
    });
    renderAnalyse(elements, getState());
    setStatus("Gemt analyse er slettet.", "ok");
  } catch (err) {
    setStatus("Kunne ikke slette analyse-log: " + (err.message || "Fejl"), "error");
  }
}

async function loadChatSavedLogs() {
  const user = (getActiveUser() || "").trim();
  if (!user) return;
  try {
    const res = await listChatLogs(user);
    const prev = getState().chat || {};
    setState({ chat: { ...prev, savedLogs: res.entries || [] } });
    renderChat(elements, getState());
  } catch (err) {
    setStatus("Kunne ikke hente gemte chats: " + (err.message || "Fejl"), "error");
  }
}

async function onChatLogEntryClick(entryId) {
  const user = getActiveUser();
  if (!user) return;
  try {
    const entry = await getChatLog(user, entryId);
    setState({
      chat: {
        selectedLogId: entryId,
        selectedLogContent: entry,
      },
    });
    renderChat(elements, getState());
  } catch (err) {
    setStatus("Kunne ikke hente chat-log: " + (err.message || "Fejl"), "error");
  }
}

function onChatLogBackClick() {
  setState({
    chat: {
      selectedLogId: null,
      selectedLogContent: null,
    },
  });
  renderChat(elements, getState());
}

async function onDeleteChatLog(entryId) {
  const user = getActiveUser();
  if (!user || !entryId) return;
  if (!window.confirm("Vil du slette denne gemte chat?")) {
    return;
  }
  try {
    const res = await deleteChatLog(user, entryId);
    const prev = getState().chat || {};
    setState({
      chat: {
        ...prev,
        savedLogs: res.entries || [],
        selectedLogId: null,
        selectedLogContent: null,
      },
    });
    renderChat(elements, getState());
    setStatus("Gemt chat er slettet.", "ok");
  } catch (err) {
    setStatus("Kunne ikke slette chat-log: " + (err.message || "Fejl"), "error");
  }
}

function loadAnalyseFromLogEntry(entry) {
  const messages = Array.isArray(entry?.messages) && entry.messages.length
    ? entry.messages
        .map((msg) => ({
          role: String(msg.role || "").trim(),
          text: String(msg.text || "").trim(),
        }))
        .filter((msg) => msg.text)
    : [
        { role: "user", text: String(entry?.question || "").trim() },
        { role: "assistant", text: String(entry?.answer || "").trim() },
      ].filter((msg) => msg.text);
  const sessionId = String(entry?.session_id || "").trim() || generateLocalSessionId("analyse");
  setState({
    analyse: {
      messages,
      previousResponseId: entry?.last_response_id || null,
      usedModel: entry?.used_model || null,
      answer: String(entry?.answer || "").trim() || "Intet svar endnu.",
      citations: Array.isArray(entry?.citations) ? entry.citations : [],
      retrievalResults: Array.isArray(entry?.retrieval_results) ? entry.retrieval_results : [],
      logPdfUrl: entry?.log_pdf_url || "",
      logPdfLabel: entry?.log_pdf_filename || "Åbn PDF-log",
      selectedLogId: null,
      selectedLogContent: null,
      question: "",
      sessionId,
    },
  });
  switchTab("analyse");
  renderAnalyse(elements, getState());
  setStatus("Analyse indlæst fra historik.", "ok");
}

function loadChatFromLogEntry(entry) {
  const messages = Array.isArray(entry?.messages)
    ? entry.messages
        .map((msg) => ({
          role: String(msg.role || "").trim(),
          text: String(msg.text || "").trim(),
        }))
        .filter((msg) => msg.text)
    : [];
  setState({
    chat: {
      messages,
      previousResponseId: entry?.last_response_id || null,
      usedModel: entry?.used_model || null,
      selectedLogId: null,
      selectedLogContent: null,
      inputText: "",
    },
  });
  if (entry?.session_id) {
    setChatSessionId(entry.session_id);
  }
  switchTab("chat");
  renderChat(elements, getState());
  setStatus("Chat indlæst fra historik.", "ok");
}

function buildSagsContextPreviewFromLog(entry) {
  if (!entry) return "";
  const lines = [];
  lines.push("Tidligere analyse-kontekst (gennemgået af bruger)");
  lines.push(`Titel: ${entry.title || "Uden titel"}`);
  lines.push(`Tidspunkt: ${entry.created_at || ""}`);
  lines.push(`Spørgsmål: ${entry.question || ""}`);
  lines.push("");
  lines.push("Tidligere analyse/svar:");
  lines.push(entry.answer || "(Tomt svar)");
  return lines.join("\n");
}

function buildSagsContextPreviewFromChatLog(entry) {
  if (!entry) return "";
  const lines = [];
  lines.push("Tidligere chat-kontekst (gennemgået af bruger)");
  lines.push(`Titel: ${entry.title || "Chat uden titel"}`);
  lines.push(`Tidspunkt: ${entry.updated_at || entry.created_at || ""}`);
  lines.push("");
  lines.push("Samtaleuddrag:");
  (entry.messages || []).forEach((msg) => {
    const role = String(msg.role || "").toLowerCase();
    if (role === "user") {
      lines.push("Du:");
    } else if (role === "assistant") {
      lines.push("JAILA:");
    } else {
      lines.push("System:");
    }
    lines.push(String(msg.text || ""));
    lines.push("");
  });
  return lines.join("\n");
}

function chooseSagsContextTargetSubtab(defaultSubtab, options = SAGS_CONTEXT_TARGET_SUBTABS) {
  const availableOptions = Array.isArray(options) && options.length ? options : SAGS_CONTEXT_TARGET_SUBTABS;
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "welcome-overlay";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");

    const optionsHtml = availableOptions
      .map((option) => {
        const checked = option.id === defaultSubtab ? "checked" : "";
        return `
          <label class="sags-context-picker-option">
            <input type="radio" name="sagsContextTargetSubtab" value="${option.id}" ${checked} />
            <span>${option.label}</span>
          </label>
        `;
      })
      .join("");

    overlay.innerHTML = `
      <div class="welcome-overlay-backdrop"></div>
      <div class="welcome-overlay-box sags-context-picker-box">
        <h2 class="welcome-overlay-title">Vælg undertab</h2>
        <p class="welcome-overlay-message">Hvor skal analyse-konteksten bruges?</p>
        <div class="sags-context-picker-options">${optionsHtml}</div>
        <div class="actions">
          <button type="button" class="button-secondary" data-action="cancel">Annuller</button>
          <button type="button" data-action="confirm">Vælg</button>
        </div>
      </div>
    `;

    const close = (value) => {
      overlay.remove();
      resolve(value);
    };
    const onCancel = () => close(null);
    const onConfirm = () => {
      const selected = overlay.querySelector(
        "input[name='sagsContextTargetSubtab']:checked",
      );
      const value = selected instanceof HTMLInputElement ? selected.value : "";
      close(value || "");
    };

    overlay.querySelector("[data-action='cancel']")?.addEventListener("click", onCancel);
    overlay.querySelector("[data-action='confirm']")?.addEventListener("click", onConfirm);
    overlay.querySelector(".welcome-overlay-backdrop")?.addEventListener("click", onCancel);
    document.body.appendChild(overlay);
  });
}

async function onUseAnalyseLogAsSagsContext(entryId) {
  const user = getActiveUser();
  if (!user) return;
  const currentSubtab = getState().sagsbehandling.activeSubtab || "";
  const defaultSubtab = SAGS_CONTEXT_TARGET_SUBTABS.some((option) => option.id === currentSubtab)
    ? currentSubtab
    : "lempelse";
  const selectedSubtab = await chooseSagsContextTargetSubtab(defaultSubtab);
  if (selectedSubtab === null) {
    setStatus("Valg af undertab blev annulleret.", "ok");
    return;
  }
  if (!selectedSubtab) {
    setStatus("Ugyldigt valg af undertab. Prøv igen.", "error");
    return;
  }
  try {
    const entry = await getAnalyseLog(user, entryId);
    const previewText = buildSagsContextPreviewFromLog(entry);
    const existing = getState().sagsbehandling.contextBySubtab || {};
    const currentList = Array.isArray(existing[selectedSubtab])
      ? existing[selectedSubtab]
      : existing[selectedSubtab]
        ? [existing[selectedSubtab]]
        : [];
    const newItem = {
      logId: entry.id || entryId,
      sourceType: "analyse",
      title: entry.title || "Uden titel",
      createdAt: entry.created_at || "",
      previewText,
      approved: false,
    };
    if (currentList.some((c) => (c.logId || "") === (newItem.logId || ""))) {
      setStatus("Konteksten er allerede tilføjet til denne undertab.", "ok");
      return;
    }
    setState({
      sagsbehandling: {
        activeSubtab: selectedSubtab,
        contextBySubtab: {
          ...existing,
          [selectedSubtab]: [...currentList, newItem],
        },
      },
    });
    switchTab("sagsbehandling");
    renderSagsbehandling(elements, getState());
    saveCurrentSagsCaseSnapshot();
    const selectedLabel = (
      SAGS_CONTEXT_TARGET_SUBTABS.find((option) => option.id === selectedSubtab)?.label
      || selectedSubtab
    );
    setStatus(
      `Analyse-kontekst er valgt til "${selectedLabel}". Gennemgå og godkend den i sagsbehandling.`,
      "ok",
    );
  } catch (err) {
    setStatus("Kunne ikke sætte analyse som kontekst: " + (err.message || "Fejl"), "error");
  }
}

async function onUseChatLogAsSagsContext(entryId) {
  const user = getActiveUser();
  if (!user) return;
  const allowedSubtabs = SAGS_CONTEXT_TARGET_SUBTABS.filter(
    (option) => option.id !== "skattepligt_ligningsfrist",
  );
  if (!allowedSubtabs.length) {
    setStatus("Ingen undertabs er tilgængelige for chat-kontekst.", "error");
    return;
  }
  const currentSubtab = getState().sagsbehandling.activeSubtab || "";
  const defaultSubtab = allowedSubtabs.some((option) => option.id === currentSubtab)
    ? currentSubtab
    : "lempelse";
  const selectedSubtab = await chooseSagsContextTargetSubtab(defaultSubtab, allowedSubtabs);
  if (selectedSubtab === null) {
    setStatus("Valg af undertab blev annulleret.", "ok");
    return;
  }
  if (!selectedSubtab) {
    setStatus("Ugyldigt valg af undertab. Prøv igen.", "error");
    return;
  }
  if (selectedSubtab === "skattepligt_ligningsfrist") {
    setStatus("Chat-kontekst kan ikke bruges i Skattepligt og ligningsfrist.", "error");
    return;
  }
  try {
    const entry = await getChatLog(user, entryId);
    const previewText = buildSagsContextPreviewFromChatLog(entry);
    const existing = getState().sagsbehandling.contextBySubtab || {};
    const currentList = Array.isArray(existing[selectedSubtab])
      ? existing[selectedSubtab]
      : existing[selectedSubtab]
        ? [existing[selectedSubtab]]
        : [];
    const newItem = {
      logId: `chat_${entry.id || entryId}`,
      sourceType: "chat",
      sourceEntryId: entry.id || entryId,
      title: entry.title || "Chat uden titel",
      createdAt: entry.updated_at || entry.created_at || "",
      previewText,
      approved: false,
    };
    if (currentList.some((c) => (c.logId || "") === (newItem.logId || ""))) {
      setStatus("Konteksten er allerede tilføjet til denne undertab.", "ok");
      return;
    }
    setState({
      sagsbehandling: {
        activeSubtab: selectedSubtab,
        contextBySubtab: {
          ...existing,
          [selectedSubtab]: [...currentList, newItem],
        },
      },
    });
    switchTab("sagsbehandling");
    renderSagsbehandling(elements, getState());
    saveCurrentSagsCaseSnapshot();
    const selectedLabel = (
      SAGS_CONTEXT_TARGET_SUBTABS.find((option) => option.id === selectedSubtab)?.label
      || selectedSubtab
    );
    setStatus(
      `Chat-kontekst er valgt til "${selectedLabel}". Gennemgå og godkend den i sagsbehandling.`,
      "ok",
    );
  } catch (err) {
    setStatus("Kunne ikke sætte chat som kontekst: " + (err.message || "Fejl"), "error");
  }
}

function resetChat() {
  const prev = getState().chat || {};
  const currentContextFiles = getState().chat.contextFiles || [];
  const initialChat = getInitialChatState();
  initialChat.contextFiles = currentContextFiles;
  initialChat.savedLogs = prev.savedLogs || [];
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
  const sags = getState().sagsbehandling || {};
  const activeSubtab = sags.activeSubtab || "skattepligt_ligningsfrist";
  const currentMessages = sags.messages || [];
  const messagesBySubtab = sags.messagesBySubtab || {};
  const updatedMessages = currentMessages.concat([{ role: role, text: text || "" }]);
  setState({
    sagsbehandling: {
      messages: updatedMessages,
      messagesBySubtab: {
        ...messagesBySubtab,
        [activeSubtab]: updatedMessages,
      },
    },
  });
  renderSagsbehandling(elements, getState());
}

function getLatestSagsbehandlingAssistantAnswer() {
  const messages = getState().sagsbehandling.messages || [];
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i].role === "assistant") {
      return String(messages[i].text || "").replace(/^JAILA:\s*/i, "").trim();
    }
  }
  return "";
}

function normalizeSagsAssistantText(text) {
  return String(text || "").trim();
}

function saveSagsbehandlingEditedOutput(subtab, text, options = {}) {
  const { persist = true, rerender = true } = options;
  const normalizedText = normalizeSagsAssistantText(text);
  const sags = getState().sagsbehandling || {};
  const messagesBySubtab = sags.messagesBySubtab || {};
  const messages = messagesBySubtab[subtab] || [];
  let lastAssistantIdx = -1;
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i].role === "assistant") {
      lastAssistantIdx = i;
      break;
    }
  }
  if (lastAssistantIdx < 0) return;
  const previousText = String(messages[lastAssistantIdx]?.text || "").trim();
  if (previousText === normalizedText) return;
  const updated = [...messages];
  updated[lastAssistantIdx] = { ...updated[lastAssistantIdx], text: normalizedText };
  const subtabOutputs = sags.subtabOutputs || {};
  const currentOutput = subtabOutputs[subtab] || {};
  setState({
    sagsbehandling: {
      messagesBySubtab: {
        ...messagesBySubtab,
        [subtab]: updated,
      },
      messages: sags.activeSubtab === subtab ? updated : sags.messages,
      subtabOutputs: {
        ...subtabOutputs,
        [subtab]: {
          ...currentOutput,
          answer: normalizedText,
        },
      },
    },
  });
  if (persist) {
    scheduleSagsCaseSnapshotSave();
  }
  if (rerender) {
    renderSagsbehandling(elements, getState());
  }
}

async function onSagsbehandlingLockToggle() {
  const ui = getState().ui || {};
  if (ui.loading) return;
  const sags = getState().sagsbehandling || {};
  const activeSubtab = sags.activeSubtab || "skattepligt_ligningsfrist";
  const isLocked = Boolean((sags.subtabOutputLocked || {})[activeSubtab]);
  const editable = elements.sagsbehandlingConversation?.querySelector(".sags-output-editable");
  if (editable instanceof HTMLTextAreaElement && !isLocked) {
    const text = normalizeSagsAssistantText(editable.value);
    saveSagsbehandlingEditedOutput(activeSubtab, text, { persist: false, rerender: false });
  }
  setState({
    sagsbehandling: {
      subtabOutputLocked: {
        ...(sags.subtabOutputLocked || {}),
        [activeSubtab]: !isLocked,
      },
    },
  });
  await saveCurrentSagsCaseSnapshot();
  renderSagsbehandling(elements, getState());
  setStatus(isLocked ? "Tekst låst op – du kan nu redigere." : "Tekst låst – beskyttet mod ændringer.", "ok");
}

async function copySagsbehandlingAnswer() {
  const answerText = getLatestSagsbehandlingAssistantAnswer();
  if (!answerText) {
    setStatus("Der er intet svar at kopiere endnu.", "error");
    return;
  }
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(answerText);
    } else {
      const temp = document.createElement("textarea");
      temp.value = answerText;
      temp.setAttribute("readonly", "");
      temp.style.position = "absolute";
      temp.style.left = "-9999px";
      document.body.appendChild(temp);
      temp.select();
      document.execCommand("copy");
      temp.remove();
    }
    setStatus("Svar kopieret til udklipsholder.", "ok");
  } catch (_err) {
    setStatus("Kunne ikke kopiere svar til udklipsholder.", "error");
  }
}

function updateSagsFactsForActiveSubtab(patch) {
  const state = getState();
  const subtab = state.sagsbehandling.activeSubtab || "skattepligt_ligningsfrist";
  const factsLockedBySubtab = state.sagsbehandling.factsLockedBySubtab || {};
  if (factsLockedBySubtab[subtab]) {
    return;
  }
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
  customCountries
    .forEach((value, idx) => {
      if (!Boolean(customChecked[idx])) {
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
    if (!key || seen.has(key)) {
      return;
    }
    seen.add(key);
    deduped.push(country);
  });
  return deduped;
}

function pruneWorkCountryDays(facts) {
  const countries = buildWorkCountriesFromFacts(facts);
  const currentMap = facts.workCountryDaysByCountry && typeof facts.workCountryDaysByCountry === "object"
    ? facts.workCountryDaysByCountry
    : {};
  const nextMap = {};
  countries.forEach((country) => {
    if (Object.prototype.hasOwnProperty.call(currentMap, country)) {
      nextMap[country] = currentMap[country];
    }
  });
  return nextMap;
}

function sanitizeWorkDaysInput(value) {
  const text = String(value || "").trim();
  if (!text || text.startsWith("-")) {
    return "";
  }
  const beforeDecimal = text.split(/[.,]/)[0] || "";
  const leadingDigitsMatch = beforeDecimal.match(/^\d+/);
  return leadingDigitsMatch ? leadingDigitsMatch[0] : "";
}

function parseWorkDaysInteger(value) {
  const sanitized = sanitizeWorkDaysInput(value);
  if (!sanitized) {
    return null;
  }
  const numeric = Number.parseInt(sanitized, 10);
  return Number.isFinite(numeric) ? numeric : null;
}

function formatWorkDaysTotal(daysMap, countries) {
  const totalDays = (Array.isArray(countries) ? countries : []).reduce((sum, country) => {
    const numeric = parseWorkDaysInteger(daysMap && daysMap[country]);
    return Number.isFinite(numeric) ? sum + numeric : sum;
  }, 0);
  return String(totalDays);
}

function formatWorkDaysPercent(days, totalDays) {
  if (!Number.isFinite(totalDays) || totalDays <= 0) {
    return "—";
  }
  const pct = (days / totalDays) * 100;
  return Number.isInteger(pct) ? `${pct} %` : `${pct.toFixed(1).replace(".", ",")} %`;
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

function normalizeMessagesForSave(messages) {
  return (Array.isArray(messages) ? messages : [])
    .map((msg) => ({
      role: String(msg?.role || "").trim(),
      text: String(msg?.text || "").trim(),
    }))
    .filter((msg) => msg.text);
}

function getSagsbehandlingCasePatchFromState() {
  const sags = getState().sagsbehandling || {};
  return {
    active_subtab: sags.activeSubtab || "skattepligt_ligningsfrist",
    shared_facts: sags.sharedFacts || {},
    subtab_outputs: sags.subtabOutputs || {},
    locked_by_subtab: sags.subtabOutputLocked || {},
    facts_locked_by_subtab: sags.factsLockedBySubtab || {},
    facts_by_subtab: sags.factsBySubtab || {},
    context_by_subtab: sags.contextBySubtab || {},
    messages_by_subtab: Object.fromEntries(
      Object.entries(sags.messagesBySubtab || {}).map(([subtab, messages]) => [
        subtab,
        normalizeMessagesForSave(messages),
      ]),
    ),
    previous_response_id_by_subtab: sags.previousResponseIdBySubtab || {},
    used_model_by_subtab: sags.usedModelBySubtab || {},
  };
}

function updateSagsCaseSelector() {
  if (!elements.sagsCaseSelect) return;
  const sags = getState().sagsbehandling || {};
  const cases = Array.isArray(sags.cases) ? sags.cases : [];
  const activeCaseId = String(sags.activeCaseId || "");
  elements.sagsCaseSelect.innerHTML = "";
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = cases.length ? "Vælg sag..." : "Ingen sag valgt";
  elements.sagsCaseSelect.appendChild(placeholder);
  cases.forEach((entry) => {
    const option = document.createElement("option");
    option.value = entry.id || "";
    option.textContent = `${entry.title || "Ny sag"} (${entry.updated_at || entry.created_at || ""})`;
    if (option.value && option.value === activeCaseId) {
      option.selected = true;
    }
    elements.sagsCaseSelect.appendChild(option);
  });
  updateSagsCaseActionsState();
}

function updateSagsCaseActionsState() {
  if (!elements.sagsRenameCaseBtn && !elements.sagsDeleteCaseBtn) return;
  const sags = getState().sagsbehandling || {};
  const activeCaseId = String(sags.activeCaseId || "").trim();
  if (elements.sagsRenameCaseBtn) {
    elements.sagsRenameCaseBtn.disabled = !activeCaseId;
  }
  if (elements.sagsDeleteCaseBtn) {
    elements.sagsDeleteCaseBtn.disabled = !activeCaseId;
  }
}

function applyCaseToSagsbehandlingState(caseEntry) {
  const activeSubtab = String(caseEntry?.active_subtab || "skattepligt_ligningsfrist");
  const messagesBySubtab = caseEntry?.messages_by_subtab && typeof caseEntry.messages_by_subtab === "object"
    ? caseEntry.messages_by_subtab
    : {};
  const previousBySubtab = caseEntry?.previous_response_id_by_subtab && typeof caseEntry.previous_response_id_by_subtab === "object"
    ? caseEntry.previous_response_id_by_subtab
    : {};
  const usedModelBySubtab = caseEntry?.used_model_by_subtab && typeof caseEntry.used_model_by_subtab === "object"
    ? caseEntry.used_model_by_subtab
    : {};
  setState({
    sagsbehandling: {
      activeCaseId: caseEntry?.id || null,
      activeSubtab,
      activeFunction: "",
      inputText: "",
      messagesBySubtab,
      messages: messagesBySubtab[activeSubtab] || [],
      previousResponseIdBySubtab: previousBySubtab,
      previousResponseId: previousBySubtab[activeSubtab] || null,
      usedModelBySubtab: usedModelBySubtab,
      usedModel: usedModelBySubtab[activeSubtab] || null,
      sharedFacts: caseEntry?.shared_facts || {},
      subtabOutputs: caseEntry?.subtab_outputs || {},
      subtabOutputLocked: caseEntry?.locked_by_subtab || {},
      factsLockedBySubtab: caseEntry?.facts_locked_by_subtab || {},
      factsBySubtab: caseEntry?.facts_by_subtab || {},
      contextBySubtab: caseEntry?.context_by_subtab || {},
      factsPanelOpen: false,
    },
  });
}

async function refreshSagsCases() {
  const user = (getActiveUser() || "").trim();
  if (!user) return;
  try {
    const res = await listCases(user);
    setState({
      sagsbehandling: {
        cases: res.entries || [],
      },
    });
    updateSagsCaseSelector();
  } catch (err) {
    setStatus("Kunne ikke hente sager: " + (err.message || "Fejl"), "error");
  }
}

async function saveCurrentSagsCaseSnapshot() {
  const user = (getActiveUser() || "").trim();
  const sags = getState().sagsbehandling || {};
  const activeCaseId = String(sags.activeCaseId || "").trim();
  if (!user || !activeCaseId) return;
  const payload = {
    user,
    ...getSagsbehandlingCasePatchFromState(),
  };
  try {
    sagsCaseSaveChain = sagsCaseSaveChain.then(async () => {
      await updateCase(activeCaseId, payload);
    });
    await sagsCaseSaveChain;
  } catch (_err) {
    // Gemmefejl skal ikke stoppe brugerflow; status vises kun ved direkte case-handlinger.
  }
}

function scheduleSagsCaseSnapshotSave() {
  if (sagsCaseSaveDebounceTimer) {
    clearTimeout(sagsCaseSaveDebounceTimer);
  }
  sagsCaseSaveDebounceTimer = setTimeout(() => {
    saveCurrentSagsCaseSnapshot();
  }, SAGS_CASE_SAVE_DEBOUNCE_MS);
}

async function loadSagsCase(caseId) {
  const user = (getActiveUser() || "").trim();
  const safeCaseId = String(caseId || "").trim();
  if (!user || !safeCaseId) {
    return;
  }
  try {
    const entry = await getCase(user, safeCaseId);
    applyCaseToSagsbehandlingState(entry);
    renderSagsbehandling(elements, getState());
    updateSagsCaseSelector();
    loadLegalBasisForSubtab(getState().sagsbehandling.activeSubtab || "skattepligt_ligningsfrist");
    setStatus("Sag indlæst.", "ok");
  } catch (err) {
    setStatus("Kunne ikke indlæse sag: " + (err.message || "Fejl"), "error");
  }
}

async function startNewSagsCase() {
  const user = (getActiveUser() || "").trim();
  if (!user) {
    setStatus("Du skal være logget ind for at starte en sag.", "error");
    return;
  }
  try {
    const entry = await createCase(user, null);
    applyCaseToSagsbehandlingState(entry);
    renderSagsbehandling(elements, getState());
    await refreshSagsCases();
    updateSagsCaseSelector();
    loadLegalBasisForSubtab(getState().sagsbehandling.activeSubtab || "skattepligt_ligningsfrist");
    setStatus("Ny sag startet.", "ok");
  } catch (err) {
    setStatus("Kunne ikke starte ny sag: " + (err.message || "Fejl"), "error");
  }
}

async function renameActiveSagsCase() {
  const user = (getActiveUser() || "").trim();
  const sags = getState().sagsbehandling || {};
  const activeCaseId = String(sags.activeCaseId || "").trim();
  if (!user || !activeCaseId) {
    setStatus("Vælg først en sag, før du omdøber.", "error");
    return;
  }
  const cases = Array.isArray(sags.cases) ? sags.cases : [];
  const activeCase = cases.find((entry) => String(entry?.id || "").trim() === activeCaseId);
  const currentTitle = String(activeCase?.title || "Ny sag").trim();
  const nextTitleRaw = window.prompt("Nyt navn til sag:", currentTitle);
  if (nextTitleRaw == null) {
    return;
  }
  const nextTitle = String(nextTitleRaw || "").trim();
  if (!nextTitle) {
    setStatus("Sagsnavn må ikke være tomt.", "error");
    return;
  }
  if (nextTitle === currentTitle) {
    return;
  }
  try {
    const updated = await updateCase(activeCaseId, {
      user,
      title: nextTitle,
    });
    const updatedCases = cases.map((entry) =>
      String(entry?.id || "").trim() === activeCaseId
        ? {
          ...entry,
          title: updated?.title || nextTitle,
          updated_at: updated?.updated_at || entry.updated_at || entry.created_at || "",
        }
        : entry,
    );
    setState({
      sagsbehandling: {
        cases: updatedCases,
      },
    });
    renderSagsbehandling(elements, getState());
    updateSagsCaseSelector();
    setStatus("Sag omdøbt.", "ok");
  } catch (err) {
    setStatus("Kunne ikke omdøbe sag: " + (err.message || "Fejl"), "error");
  }
}

async function deleteActiveSagsCase() {
  const user = (getActiveUser() || "").trim();
  const sags = getState().sagsbehandling || {};
  const activeCaseId = String(sags.activeCaseId || "").trim();
  if (!user || !activeCaseId) {
    setStatus("Vælg først en sag, før du sletter.", "error");
    return;
  }
  const cases = Array.isArray(sags.cases) ? sags.cases : [];
  const activeCase = cases.find((entry) => String(entry?.id || "").trim() === activeCaseId);
  const caseTitle = String(activeCase?.title || "Ny sag").trim();
  const confirmed = window.confirm(`Slet sag "${caseTitle}"? Denne handling kan ikke fortrydes.`);
  if (!confirmed) {
    return;
  }
  try {
    const result = await deleteCase(user, activeCaseId);
    const remainingCases = Array.isArray(result?.entries) ? result.entries : [];
    setState({
      sagsbehandling: {
        activeCaseId: null,
        cases: remainingCases,
        inputText: "",
        messages: [],
        messagesBySubtab: {},
        previousResponseId: null,
        previousResponseIdBySubtab: {},
        usedModel: null,
        usedModelBySubtab: {},
        sharedFacts: {},
        subtabOutputs: {},
        subtabOutputLocked: {},
        factsLockedBySubtab: {},
        factsPanelOpen: false,
        factsBySubtab: {},
        contextBySubtab: {},
      },
    });
    renderSagsbehandling(elements, getState());
    updateSagsCaseSelector();
    if (remainingCases.length > 0 && remainingCases[0]?.id) {
      await loadSagsCase(remainingCases[0].id);
      setStatus("Sag slettet. Næste sag er indlæst.", "ok");
      return;
    }
    setStatus("Sag slettet.", "ok");
  } catch (err) {
    setStatus("Kunne ikke slette sag: " + (err.message || "Fejl"), "error");
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
    setState({
      sagsbehandling: {
        activeCaseId: null,
        cases: [],
        activeSubtab: "skattepligt_ligningsfrist",
        activeFunction: "",
        inputText: "",
        messages: [],
        messagesBySubtab: {},
        previousResponseId: null,
        previousResponseIdBySubtab: {},
        usedModel: null,
        usedModelBySubtab: {},
        sharedFacts: {},
        subtabOutputs: {},
        subtabOutputLocked: {},
        factsLockedBySubtab: {},
        factsPanelOpen: false,
        factsBySubtab: {},
        contextBySubtab: {},
        legalBasisBySubtab: {},
        legalBasisLoadingBySubtab: {},
        autoLegalBasisTextBySubtab: {},
      },
    });
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
    const analyseSessionId = getOrCreateAnalyseSessionId();
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
            const snapshotMessages = getState().analyse.messages || [];
            saveAnalyseLog(user, {
              session_id: analyseSessionId,
              question,
              answer,
              citations: evt.citations || [],
              retrieval_results: evt.retrieval_results || [],
              used_model: evt.used_model || "",
              used_vector_store_ids: evt.used_vector_store_ids || null,
              log_pdf_filename: evt.log_pdf_filename || null,
              log_pdf_url: evt.log_pdf_url || null,
              messages: snapshotMessages,
              last_response_id: evt.response_id || null,
            })
              .then((saved) => {
                const prev = getState().analyse || {};
                const existing = Array.isArray(prev.savedLogs) ? prev.savedLogs : [];
                const filtered = existing.filter((entry) => entry.id !== saved.id);
                const logs = [
                  {
                    id: saved.id,
                    created_at: saved.created_at,
                    title: saved.title,
                    log_pdf_filename: saved.log_pdf_filename || null,
                    log_pdf_url: saved.log_pdf_url || null,
                  },
                  ...filtered,
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
        const snapshotMessages = getState().analyse.messages || [];
        saveAnalyseLog(user, {
          session_id: analyseSessionId,
          question,
          answer: data.answer || "",
          citations: data.citations || [],
          retrieval_results: data.retrieval_results || [],
          used_model: data.used_model || "",
          used_vector_store_ids: null,
          log_pdf_filename: data.log_pdf_filename || null,
          log_pdf_url: data.log_pdf_url || null,
          messages: snapshotMessages,
          last_response_id: data.response_id || null,
        })
          .then((saved) => {
            const prev = getState().analyse || {};
            const existing = Array.isArray(prev.savedLogs) ? prev.savedLogs : [];
            const filtered = existing.filter((entry) => entry.id !== saved.id);
            const logs = [
              {
                id: saved.id,
                created_at: saved.created_at,
                title: saved.title,
                log_pdf_filename: saved.log_pdf_filename || null,
                log_pdf_url: saved.log_pdf_url || null,
              },
              ...filtered,
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

function getContextListForSubtab(subtab) {
  const contextBySubtab = getState().sagsbehandling.contextBySubtab || {};
  const raw = contextBySubtab[subtab];
  return Array.isArray(raw) ? raw : raw ? [raw] : [];
}

function removeSagsContext(logId) {
  const activeSubtab = getState().sagsbehandling.activeSubtab || "";
  const contextBySubtab = getState().sagsbehandling.contextBySubtab || {};
  const list = getContextListForSubtab(activeSubtab);
  const updated = list.filter((c) => (c.logId || "") !== logId);
  setState({
    sagsbehandling: {
      contextBySubtab: { ...contextBySubtab, [activeSubtab]: updated },
    },
  });
  renderSagsbehandling(elements, getState());
  setStatus("Analyse-kontekst er fjernet.", "ok");
  saveCurrentSagsCaseSnapshot();
}

async function runSagsbehandling() {
  const activeCaseId = String((getState().sagsbehandling || {}).activeCaseId || "").trim();
  if (!activeCaseId) {
    setStatus("Start eller vælg en sag før du sender i Sagsbehandling.", "error");
    return;
  }
  const activeSubtab = (getState().sagsbehandling.activeSubtab || "").trim();
  const contextList = getContextListForSubtab(activeSubtab);
  const hasContext = contextList.length > 0;
  const allApproved = !hasContext || contextList.every((c) => Boolean(c.approved));
  if (hasContext && !allApproved) {
    setStatus("Gennemgå og godkend alle analyse-kontekster før du sender.", "error");
    return;
  }
  const approvedContexts = hasContext
    ? contextList.filter((c) => c.approved)
    : [];
  const approvedAnalyseLogIds = approvedContexts
    .filter((c) => !c.sourceType || c.sourceType === "analyse")
    .map((c) => c.logId)
    .filter(Boolean);
  const approvedContextBlocks = approvedContexts
    .map((c) => String(c.previewText || "").trim())
    .filter((text) => text.length > 0);
  const isSkattepligtFlow = activeSubtab === "skattepligt_ligningsfrist";
  let caseFacts = null;
  let generatedQuestion = "";
  const sharedFacts = getState().sagsbehandling.sharedFacts || {};
  const subtabOutputs = getState().sagsbehandling.subtabOutputs || {};
  const subtabOutputLocked = getState().sagsbehandling.subtabOutputLocked || {};

  if (isSkattepligtFlow) {
    caseFacts = buildSagsCaseFactsPayload(activeSubtab) || {};
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

    generatedQuestion =
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
  } else if (
    activeSubtab === "opgoerelse_indkomst"
    || activeSubtab === "beskatningsret_indkomst"
    || activeSubtab === "lempelse"
    || activeSubtab === "andet"
  ) {
    const freeText = (elements.sagsbehandlingInput ? elements.sagsbehandlingInput.value : "").trim();
    const factsBySubtab = getState().sagsbehandling.factsBySubtab || {};
    const facts = factsBySubtab[activeSubtab] || {};
    const beskatningsretCountryLine = activeSubtab === "beskatningsret_indkomst"
      ? (() => {
        const mode = String(facts.residenceCountryMode || "").trim();
        if (mode === "danmark") {
          return "Danmark";
        }
        if (mode === "other") {
          const otherCountry = String(facts.residenceCountryOther || "").trim();
          return otherCountry ? otherCountry : "Andet (ikke angivet)";
        }
        return "";
      })()
      : "";
    const beskatningsretEmployerLine = activeSubtab === "beskatningsret_indkomst"
      ? (() => {
        const mode = String(facts.employerResidenceMode || "").trim();
        if (mode === "danmark") return "Danmark";
        if (mode === "private_foreign") return "Privat udenlandsk arbejdsgiver";
        if (mode === "public_foreign") return "Offentlig udenlandsk arbejdsgiver";
        return "";
      })()
      : "";
    const factsLines = [
      ...(activeSubtab === "beskatningsret_indkomst" ? [] : [["Indkomstår", facts.incomeYears]]),
      ...(activeSubtab === "beskatningsret_indkomst" ? [["Bopælsland", beskatningsretCountryLine]] : []),
      ...(activeSubtab === "beskatningsret_indkomst"
        ? [[
          "Bopæl til rådighed i arbejdsland",
          facts.residenceAvailableInWorkCountry ? "Ja" : "Nej",
        ]]
        : []),
      ...(activeSubtab === "beskatningsret_indkomst"
        ? [["Skattemæssigt hjemsted/Danmark", facts.taxResidenceDenmarkFact]]
        : []),
      ...(activeSubtab === "beskatningsret_indkomst" ? [["Arbejdsgiver hjemmehørende i", beskatningsretEmployerLine]] : []),
      ...(activeSubtab === "beskatningsret_indkomst" ? [["Navn på arbejdsgiver", facts.employerName]] : []),
      ...(activeSubtab === "beskatningsret_indkomst" ? [["Navn på arbejdsgiver (nr. 2)", facts.employerName2]] : []),
      ...(activeSubtab === "beskatningsret_indkomst" ? [["Land, hvor arbejdsgiver er hjemmehørende", facts.employerCountry]] : []),
      ...(activeSubtab === "beskatningsret_indkomst"
        ? [[
          "Lande, hvor der er udført arbejde",
          buildWorkCountriesFromFacts(facts).join(", "),
        ]]
        : []),
      ...(activeSubtab === "beskatningsret_indkomst"
        ? [[
          "Arbejdsdage pr. land",
          (() => {
            const countries = buildWorkCountriesFromFacts(facts);
            const daysMap = facts.workCountryDaysByCountry && typeof facts.workCountryDaysByCountry === "object"
              ? facts.workCountryDaysByCountry
              : {};
            return countries
              .map((country) => {
                const days = String(daysMap[country] || "").trim();
                return days ? `${country}: ${days}` : "";
              })
              .filter((line) => line)
              .join(" | ");
          })(),
        ]]
        : []),
      ["Indkomst/faktum", facts.foreignIncome],
      ["Aktiver/passiver", facts.foreignAssetsLiabilities],
      ["Bopælsfaktum", facts.residenceFact],
      ["Noter", facts.notes],
    ]
      .map(([label, value]) => [label, String(value || "").trim()])
      .filter(([, value]) => value);

    if (!freeText && !factsLines.length) {
      setStatus("Skriv sagsbeskrivelse eller udfyld fakta før afsendelse.", "error");
      return;
    }

    generatedQuestion =
      `Undertab: ${SAGS_SUBTAB_LABELS[activeSubtab] || activeSubtab}\n`
      + `Sagsbeskrivelse: ${freeText || "(ingen fritekst angivet)"}\n`
      + (factsLines.length
        ? `\nFakta:\n${factsLines.map(([label, value]) => `- ${label}: ${value}`).join("\n")}`
        : "")
      + "\n\nLav en juridisk vurdering med tydelig struktur og anvendte kilder/love.";
    addSagsbehandlingMessage(
      "user",
      "Sagsspørgsmål sendt til vurdering"
      + (freeText ? `:\n${freeText}` : "."),
    );
  } else {
    addSagsbehandlingMessage(
      "system",
      "Denne undertab er ikke aktiveret endnu.",
    );
    setStatus("Undertab er ikke aktiveret endnu.", "error");
    return;
  }
  if (approvedContextBlocks.length) {
    generatedQuestion +=
      "\n\nTidligere godkendt kontekst:\n"
      + approvedContextBlocks.map((block, idx) => `--- Kontekst ${idx + 1} ---\n${block}`).join("\n\n")
      + "\n\nBrug konteksten som baggrund. Hvis den strider mod file_search-kilder, følg file_search-kilderne.";
  }
  const sharedFactLines = Object.entries(sharedFacts || {})
    .map(([key, value]) => [String(key || "").trim(), String(value ?? "").trim()])
    .filter(([key, value]) => key && value)
    .map(([key, value]) => `- ${key}: ${value}`);
  if (sharedFactLines.length) {
    generatedQuestion += `\n\nFælles sagsfakta fra tidligere undertabs:\n${sharedFactLines.join("\n")}`;
  }
  const autoBeskatningsretContextLines = activeSubtab === "beskatningsret_indkomst"
    ? BESKATNINGSRET_AUTO_CONTEXT_SOURCES
      .map((subtabKey) => {
        if (!Boolean(subtabOutputLocked[subtabKey])) {
          return "";
        }
        const answer = String((subtabOutputs[subtabKey] && subtabOutputs[subtabKey].answer) || "").trim();
        if (!answer) {
          return "";
        }
        const subtabLabel = SAGS_SUBTAB_LABELS[subtabKey] || subtabKey;
        return `${subtabLabel} (låst):\n${answer}`;
      })
      .filter((block) => block)
    : [];
  if (autoBeskatningsretContextLines.length) {
    generatedQuestion +=
      `\n\nAutomatisk kontekst fra låste undertabs:\n${autoBeskatningsretContextLines.join("\n\n")}`;
  }
  const excludedSubtabs = new Set([activeSubtab]);
  if (activeSubtab === "beskatningsret_indkomst") {
    BESKATNINGSRET_AUTO_CONTEXT_SOURCES.forEach((subtabKey) => excludedSubtabs.add(subtabKey));
  }
  const priorOutputLines = Object.entries(subtabOutputs || {})
    .filter(([subtabKey]) => {
      const safeSubtabKey = String(subtabKey || "").trim();
      return safeSubtabKey && !excludedSubtabs.has(safeSubtabKey);
    })
    .map(([subtabKey, output]) => {
      const answer = String((output && output.answer) || "").trim();
      if (!answer) return "";
      return `Undertab ${SAGS_SUBTAB_LABELS[subtabKey] || subtabKey}:\n${answer}`;
    })
    .filter((block) => block);
  if (priorOutputLines.length) {
    generatedQuestion += `\n\nTidligere delresultater i samme sag:\n${priorOutputLines.join("\n\n")}`;
  }
  renderSagsbehandling(elements, getState());

  setLoading(true);
  setStatus("Sender forespørgsel til backend...", "ok");
  try {
    const previousResponseId = getState().sagsbehandling.previousResponseId || null;
    const activeUser = getActiveUser();
    const data = await analyzeQuestion(generatedQuestion, previousResponseId, {
      sourceTab: "sagsbehandling",
      subtab: activeSubtab,
      caseId: activeCaseId,
      caseUser: activeUser,
      caseFacts: caseFacts,
      contextLogIds: approvedAnalyseLogIds,
      contextUser: approvedAnalyseLogIds.length ? activeUser : null,
      contextApproved: approvedAnalyseLogIds.length > 0,
    });
    const currentSags = getState().sagsbehandling || {};
    const prevRespMap = currentSags.previousResponseIdBySubtab || {};
    const usedModelMap = currentSags.usedModelBySubtab || {};
    const nextSharedFacts = { ...(currentSags.sharedFacts || {}) };
    if (activeSubtab === "skattepligt_ligningsfrist" && caseFacts) {
      if (caseFacts.income_years) nextSharedFacts.income_years = String(caseFacts.income_years);
      if (caseFacts.selected_trigger) nextSharedFacts.selected_trigger = String(caseFacts.selected_trigger);
      if (caseFacts.residence_fact) nextSharedFacts.residence_fact = String(caseFacts.residence_fact);
    }
    const nextSubtabOutputs = {
      ...(currentSags.subtabOutputs || {}),
      [activeSubtab]: {
        answer: data.answer || "",
        used_model: data.used_model || "",
        response_id: data.response_id || null,
      },
    };
    setState({
      sagsbehandling: {
        previousResponseId: data.response_id || null,
        usedModel: data.used_model || null,
        previousResponseIdBySubtab: {
          ...prevRespMap,
          [activeSubtab]: data.response_id || null,
        },
        usedModelBySubtab: {
          ...usedModelMap,
          [activeSubtab]: data.used_model || null,
        },
        sharedFacts: nextSharedFacts,
        subtabOutputs: nextSubtabOutputs,
      },
    });
    addSagsbehandlingMessage("assistant", data.answer || "Intet svar returneret.");
    setStatus("Sagsbehandling svar modtaget. Model: " + (data.used_model || "ukendt"), "ok");
    await saveCurrentSagsCaseSnapshot();
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
  const contextBySubtab = state.sagsbehandling.contextBySubtab || {};
  const messagesBySubtab = state.sagsbehandling.messagesBySubtab || {};
  const previousBySubtab = state.sagsbehandling.previousResponseIdBySubtab || {};
  const usedModelBySubtab = state.sagsbehandling.usedModelBySubtab || {};
  const subtabOutputs = state.sagsbehandling.subtabOutputs || {};
  const subtabOutputLocked = state.sagsbehandling.subtabOutputLocked || {};

  setState({
    sagsbehandling: {
      messages: [],
      previousResponseId: null,
      usedModel: null,
      messagesBySubtab: {
        ...messagesBySubtab,
        [activeSubtab]: [],
      },
      previousResponseIdBySubtab: {
        ...previousBySubtab,
        [activeSubtab]: null,
      },
      usedModelBySubtab: {
        ...usedModelBySubtab,
        [activeSubtab]: null,
      },
      subtabOutputLocked: {
        ...subtabOutputLocked,
        [activeSubtab]: false,
      },
      subtabOutputs: {
        ...subtabOutputs,
        [activeSubtab]: {
          answer: "",
          used_model: "",
          response_id: null,
        },
      },
      factsBySubtab: {
        ...factsBySubtab,
        [activeSubtab]: {
          incomeYears: "",
          foreignIncome: "",
          foreignAssetsLiabilities: "",
          residenceFact: "",
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
        employmentContractReceived: "",
          workCountryModes: [],
          workCountryDenmarkFields: [],
          workCountryCustomChecked: [],
          workCountryDaysByCountry: {},
          notes: "",
          selectedFactors: [],
          factorDetails: {},
          foreignIncomeTypes: [],
          foreignAssetsLiabilitiesType: "",
          specialTaxLiabilityMode: "",
        },
      },
      contextBySubtab: {
        ...contextBySubtab,
        [activeSubtab]: [],
      },
    },
  });
  renderSagsbehandling(elements, getState());
  setStatus("Sagsbehandling ryddet for aktiv undertab.", "ok");
  saveCurrentSagsCaseSnapshot();
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
          const user = getActiveUser();
          if (user) {
            const snapshotMessages = getState().chat.messages || [];
            saveChatLog(
              user,
              sessionId,
              snapshotMessages,
              evt.used_model || "",
              evt.response_id || null,
            )
              .then((saved) => {
                const prev = getState().chat || {};
                const existing = Array.isArray(prev.savedLogs) ? prev.savedLogs : [];
                const filtered = existing.filter((entry) => entry.id !== saved.id);
                setState({
                  chat: {
                    savedLogs: [saved, ...filtered],
                  },
                });
                renderChat(elements, getState());
              })
              .catch(() => {});
          }
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
      const user = getActiveUser();
      if (user) {
        const snapshotMessages = getState().chat.messages || [];
        saveChatLog(
          user,
          sessionId,
          snapshotMessages,
          data.used_model || "",
          data.response_id || null,
        )
          .then((saved) => {
            const prev = getState().chat || {};
            const existing = Array.isArray(prev.savedLogs) ? prev.savedLogs : [];
            const filtered = existing.filter((entry) => entry.id !== saved.id);
            setState({
              chat: {
                savedLogs: [saved, ...filtered],
              },
            });
            renderChat(elements, getState());
          })
          .catch(() => {});
      }
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
    const onFileSelected = () => {
      if (fileInput.files && fileInput.files.length) {
        void uploadContextFromInput();
      }
    };
    fileInput.addEventListener("change", onFileSelected, { once: true });
    try {
      if (typeof fileInput.showPicker === "function") {
        fileInput.showPicker();
      } else {
        fileInput.click();
      }
    } catch (_err) {
      fileInput.click();
    }
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
  if (elements.sagsbehandlingCopyAnswerBtn) {
    elements.sagsbehandlingCopyAnswerBtn.addEventListener("click", copySagsbehandlingAnswer);
  }
  if (elements.sagsbehandlingLockBtn) {
    elements.sagsbehandlingLockBtn.addEventListener("click", onSagsbehandlingLockToggle);
  }
  if (elements.sagsbehandlingConversation) {
    elements.sagsbehandlingConversation.addEventListener("sags-output-edit", (event) => {
      const { subtab, text } = event.detail || {};
      if (!subtab) return;
      const sags = getState().sagsbehandling || {};
      const isLocked = Boolean((sags.subtabOutputLocked || {})[subtab]);
      if (isLocked) return;
      saveSagsbehandlingEditedOutput(subtab, text, { persist: false, rerender: false });
      scheduleSagsCaseSnapshotSave();
    });
  }
  if (elements.sagsStartCaseBtn) {
    elements.sagsStartCaseBtn.addEventListener("click", () => {
      startNewSagsCase();
    });
  }
  if (elements.sagsRenameCaseBtn) {
    elements.sagsRenameCaseBtn.addEventListener("click", () => {
      renameActiveSagsCase();
    });
  }
  if (elements.sagsDeleteCaseBtn) {
    elements.sagsDeleteCaseBtn.addEventListener("click", () => {
      deleteActiveSagsCase();
    });
  }
  if (elements.sagsCaseSelect) {
    elements.sagsCaseSelect.addEventListener("change", () => {
      const selected = String(elements.sagsCaseSelect.value || "").trim();
      if (!selected) {
        setState({
          sagsbehandling: {
            activeCaseId: null,
          },
        });
        renderSagsbehandling(elements, getState());
        updateSagsCaseActionsState();
        return;
      }
      loadSagsCase(selected);
    });
  }
  if (elements.sagsContextList) {
    elements.sagsContextList.addEventListener("change", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement) || target.type !== "checkbox") return;
      const logId = target.getAttribute("data-context-log-id");
      if (!logId) return;
      const activeSubtab = getState().sagsbehandling.activeSubtab || "";
      const contextBySubtab = getState().sagsbehandling.contextBySubtab || {};
      const list = getContextListForSubtab(activeSubtab);
      const updated = list.map((c) =>
        (c.logId || "") === logId ? { ...c, approved: Boolean(target.checked) } : c,
      );
      setState({
        sagsbehandling: {
          contextBySubtab: { ...contextBySubtab, [activeSubtab]: updated },
        },
      });
      renderSagsbehandling(elements, getState());
      saveCurrentSagsCaseSnapshot();
    });
    elements.sagsContextList.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      const removeBtn = target.closest("[data-action=remove-sags-context]");
      if (!removeBtn) return;
      const logId = removeBtn.getAttribute("data-context-log-id");
      if (!logId) return;
      event.preventDefault();
      removeSagsContext(logId);
      saveCurrentSagsCaseSnapshot();
    });
  }
  if (elements.sagsContextClearBtn) {
    elements.sagsContextClearBtn.addEventListener("click", () => {
      const activeSubtab = getState().sagsbehandling.activeSubtab || "skattepligt_ligningsfrist";
      const contextBySubtab = getState().sagsbehandling.contextBySubtab || {};
      setState({
        sagsbehandling: {
          contextBySubtab: { ...contextBySubtab, [activeSubtab]: [] },
        },
      });
      renderSagsbehandling(elements, getState());
      setStatus("Alle analyse-kontekster er fjernet for aktiv undertab.", "ok");
      saveCurrentSagsCaseSnapshot();
    });
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
      const useAsContextBtn = el.closest("[data-action=use-as-sags-context]");
      if (useAsContextBtn?.dataset?.entryId) {
        onUseAnalyseLogAsSagsContext(useAsContextBtn.dataset.entryId);
        return;
      }
      const loadBtn = el.closest("[data-action=analyse-log-load]");
      if (loadBtn?.dataset?.entryId) {
        const selected = getState().analyse.selectedLogContent;
        if (selected && (selected.id || "") === loadBtn.dataset.entryId) {
          loadAnalyseFromLogEntry(selected);
        }
        return;
      }
      const deleteBtn = el.closest("[data-action=analyse-log-delete]");
      if (deleteBtn?.dataset?.entryId) {
        onDeleteAnalyseLog(deleteBtn.dataset.entryId);
        return;
      }
      if (el.closest("[data-action=log-back]")) {
        onAnalyseLogBackClick();
      }
    });
  }

  if (elements.chatLogContent) {
    elements.chatLogContent.addEventListener("click", (event) => {
      const el = event.target.nodeType === Node.ELEMENT_NODE ? event.target : event.target.parentElement;
      if (!el) return;
      const entryBtn = el.closest(".analyse-log-entry");
      if (entryBtn?.dataset?.entryId) {
        onChatLogEntryClick(entryBtn.dataset.entryId);
        return;
      }
      const loadBtn = el.closest("[data-action=chat-log-load]");
      if (loadBtn?.dataset?.entryId) {
        const selected = getState().chat.selectedLogContent;
        if (selected && (selected.id || "") === loadBtn.dataset.entryId) {
          loadChatFromLogEntry(selected);
        }
        return;
      }
      const deleteBtn = el.closest("[data-action=chat-log-delete]");
      if (deleteBtn?.dataset?.entryId) {
        onDeleteChatLog(deleteBtn.dataset.entryId);
        return;
      }
      const useAsContextBtn = el.closest("[data-action=use-chat-as-sags-context]");
      if (useAsContextBtn?.dataset?.entryId) {
        onUseChatLogAsSagsContext(useAsContextBtn.dataset.entryId);
        return;
      }
      if (el.closest("[data-action=chat-log-back]")) {
        onChatLogBackClick();
      }
    });
  }

  if (elements.sagsSubtabButtons && elements.sagsSubtabButtons.length) {
    elements.sagsSubtabButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        const subtab = btn.dataset.sagsSubtab || "skattepligt_ligningsfrist";
        const sags = getState().sagsbehandling || {};
        const messagesBySubtab = sags.messagesBySubtab || {};
        const previousBySubtab = sags.previousResponseIdBySubtab || {};
        const usedModelBySubtab = sags.usedModelBySubtab || {};
        setState({
          sagsbehandling: {
            activeSubtab: subtab,
            activeFunction: "",
            inputText: "",
            messages: messagesBySubtab[subtab] || [],
            previousResponseId: previousBySubtab[subtab] || null,
            usedModel: usedModelBySubtab[subtab] || null,
            factsPanelOpen: false,
          },
        });
        renderSagsbehandling(elements, getState());
        saveCurrentSagsCaseSnapshot();
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
      const factsLockedBySubtab = getState().sagsbehandling.factsLockedBySubtab || {};
      const currentlyLocked = Boolean(factsLockedBySubtab[activeSubtab]);
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
      const nextLockedState = !currentlyLocked;
      setState({
        sagsbehandling: {
          factsLockedBySubtab: {
            ...factsLockedBySubtab,
            [activeSubtab]: nextLockedState,
          },
          factsPanelOpen: nextLockedState ? false : true,
        },
      });
      addSagsbehandlingMessage("system", nextLockedState
        ? "Fakta gemt og låst for undertab: " + activeSubtab + "."
        : "Fakta låst op for undertab: " + activeSubtab + ".");
      renderSagsbehandling(elements, getState());
      setStatus(nextLockedState ? "Fakta gemt og låst." : "Fakta er låst op og kan redigeres.", "ok");
      saveCurrentSagsCaseSnapshot();
    });
  }

  if (elements.sagsFactsClearBtn) {
    elements.sagsFactsClearBtn.addEventListener("click", () => {
      const activeSubtab = getState().sagsbehandling.activeSubtab || "skattepligt_ligningsfrist";
      const factsLockedBySubtab = getState().sagsbehandling.factsLockedBySubtab || {};
      if (Boolean(factsLockedBySubtab[activeSubtab])) {
        setStatus("Fakta er låst. Lås op før du rydder.", "error");
        return;
      }
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
        residenceCountryMode: "",
        residenceCountryOther: "",
        residenceAvailableInWorkCountry: false,
        taxResidenceDenmarkFact: "",
        employerResidenceMode: "",
        employerName: "",
        employerName2: "",
        employerCountMode: "one",
        employerCountry: "",
        employmentContractReceived: "",
        workCountryModes: [],
        workCountryDenmarkFields: [],
        workCountryCustomChecked: [],
        workCountryDaysByCountry: {},
      });
      renderSagsbehandling(elements, getState());
      setStatus("Fakta ryddet lokalt.", "ok");
      saveCurrentSagsCaseSnapshot();
    });
  }

  if (elements.sagsFactsPanel) {
    elements.sagsFactsPanel.addEventListener("change", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement)) {
        return;
      }
      const contractAnswer = String(target.dataset.sagsEmploymentContractReceived || "").trim();
      if (!contractAnswer) {
        return;
      }
      const activeSubtab = getState().sagsbehandling.activeSubtab || "";
      if (activeSubtab !== "beskatningsret_indkomst") {
        return;
      }
      updateSagsFactsForActiveSubtab({
        employmentContractReceived: contractAnswer,
      });
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
  if (elements.sagsFactsBeskatningsretCountryBlock) {
    elements.sagsFactsBeskatningsretCountryBlock.addEventListener("change", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement)) {
        return;
      }
      const activeSubtab = getState().sagsbehandling.activeSubtab || "";
      if (activeSubtab !== "beskatningsret_indkomst") {
        return;
      }
      const residenceMode = String(target.dataset.sagsResidenceCountryMode || "").trim();
      if (residenceMode && target.checked) {
        updateSagsFactsForActiveSubtab({
          residenceCountryMode: residenceMode,
          residenceCountryOther: residenceMode === "other"
            ? String(((getState().sagsbehandling.factsBySubtab || {})[activeSubtab] || {}).residenceCountryOther || "")
            : "",
        });
        renderSagsbehandling(elements, getState());
        return;
      }
      if (String(target.dataset.sagsResidenceAvailableInWorkCountry || "").trim() === "true") {
        updateSagsFactsForActiveSubtab({
          residenceAvailableInWorkCountry: Boolean(target.checked),
          taxResidenceDenmarkFact: target.checked
            ? String(((getState().sagsbehandling.factsBySubtab || {})[activeSubtab] || {}).taxResidenceDenmarkFact || "")
            : "",
        });
        renderSagsbehandling(elements, getState());
        return;
      }
      const employerMode = String(target.dataset.sagsEmployerResidenceMode || "").trim();
      if (employerMode && target.checked) {
        updateSagsFactsForActiveSubtab({
          employerResidenceMode: employerMode,
        });
        renderSagsbehandling(elements, getState());
        return;
      }
      const employerCountMode = String(target.dataset.sagsEmployerCountMode || "").trim();
      if (employerCountMode && target.checked) {
        const currentFacts = ((getState().sagsbehandling.factsBySubtab || {})[activeSubtab] || {});
        updateSagsFactsForActiveSubtab({
          employerCountMode,
          employerName2: employerCountMode === "two"
            ? String(currentFacts.employerName2 || "")
            : "",
        });
        renderSagsbehandling(elements, getState());
        return;
      }
      const workCountryMode = String(target.dataset.sagsWorkCountryMode || "").trim();
      if (workCountryMode) {
        const currentFacts = ((getState().sagsbehandling.factsBySubtab || {})[activeSubtab] || {});
        const currentModes = Array.isArray(currentFacts.workCountryModes)
          ? currentFacts.workCountryModes.map((value) => String(value || "").trim()).filter((value) => value)
          : String(currentFacts.workCountryMode || "").trim()
            ? [String(currentFacts.workCountryMode || "").trim()]
            : [];
        const nextModes = target.checked
          ? Array.from(new Set([...currentModes, workCountryMode]))
          : currentModes.filter((mode) => mode !== workCountryMode);
        const nextFacts = {
          ...currentFacts,
          workCountryModes: nextModes,
          workCountryMode: "",
          workCountryDenmarkFields: nextModes.includes("danmark")
            ? (Array.isArray(currentFacts.workCountryDenmarkFields)
              ? currentFacts.workCountryDenmarkFields
              : [])
            : [],
        };
        updateSagsFactsForActiveSubtab({
          workCountryModes: nextFacts.workCountryModes,
          workCountryMode: nextFacts.workCountryMode,
          workCountryDenmarkFields: nextFacts.workCountryDenmarkFields,
          workCountryDaysByCountry: pruneWorkCountryDays(nextFacts),
        });
        renderSagsbehandling(elements, getState());
        return;
      }
      const workCountryTextIndex = String(target.dataset.sagsWorkCountryDenmarkIndex || "").trim();
      if (workCountryTextIndex) {
        renderSagsbehandling(elements, getState());
        return;
      }
      const workCountryCustomCheckedIndex = String(target.dataset.sagsWorkCountryCustomCheckedIndex || "").trim();
      if (workCountryCustomCheckedIndex) {
        const idx = Number(workCountryCustomCheckedIndex);
        if (Number.isInteger(idx) && idx >= 0 && idx < 6) {
          const currentFacts = ((getState().sagsbehandling.factsBySubtab || {})[activeSubtab] || {});
          const nextChecked = Array.isArray(currentFacts.workCountryCustomChecked)
            ? [...currentFacts.workCountryCustomChecked]
            : [];
          nextChecked[idx] = Boolean(target.checked);
          const nextFacts = {
            ...currentFacts,
            workCountryCustomChecked: nextChecked,
          };
          updateSagsFactsForActiveSubtab({
            workCountryCustomChecked: nextChecked,
            workCountryDaysByCountry: pruneWorkCountryDays(nextFacts),
          });
          renderSagsbehandling(elements, getState());
        }
        return;
      }
    });
    elements.sagsFactsBeskatningsretCountryBlock.addEventListener("input", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement) && !(target instanceof HTMLTextAreaElement)) {
        return;
      }
      const activeSubtab = getState().sagsbehandling.activeSubtab || "";
      if (activeSubtab !== "beskatningsret_indkomst") {
        return;
      }
      if (String(target.dataset.sagsTaxResidenceDenmarkFact || "").trim() === "true") {
        updateSagsFactsForActiveSubtab({
          taxResidenceDenmarkFact: target.value,
        });
        return;
      }
      if (String(target.dataset.sagsResidenceCountryOther || "").trim() === "true") {
        updateSagsFactsForActiveSubtab({
          residenceCountryOther: target.value,
        });
        return;
      }
      if (String(target.dataset.sagsEmployerName || "").trim() === "true") {
        updateSagsFactsForActiveSubtab({
          employerName: target.value,
        });
        return;
      }
      if (String(target.dataset.sagsEmployerName2 || "").trim() === "true") {
        updateSagsFactsForActiveSubtab({
          employerName2: target.value,
        });
        return;
      }
      if (String(target.dataset.sagsEmployerCountry || "").trim() === "true") {
        updateSagsFactsForActiveSubtab({
          employerCountry: target.value,
        });
        return;
      }
      const workCountryIndexRaw = String(target.dataset.sagsWorkCountryDenmarkIndex || "").trim();
      if (workCountryIndexRaw) {
        const idx = Number(workCountryIndexRaw);
        if (Number.isInteger(idx) && idx >= 0 && idx < 6) {
          const currentFacts = ((getState().sagsbehandling.factsBySubtab || {})[activeSubtab] || {});
          const nextFields = Array.isArray(currentFacts.workCountryDenmarkFields)
            ? [...currentFacts.workCountryDenmarkFields]
            : [];
          nextFields[idx] = target.value;
          const nextFacts = {
            ...currentFacts,
            workCountryDenmarkFields: nextFields,
          };
          updateSagsFactsForActiveSubtab({
            workCountryDenmarkFields: nextFields,
            workCountryDaysByCountry: pruneWorkCountryDays(nextFacts),
          });
        }
        return;
      }
      const workCountryDaysCountry = String(target.dataset.sagsWorkCountryDaysCountry || "").trim();
      if (workCountryDaysCountry) {
        const sanitizedValue = sanitizeWorkDaysInput(target.value);
        if (target.value !== sanitizedValue) {
          target.value = sanitizedValue;
        }
        const currentFacts = ((getState().sagsbehandling.factsBySubtab || {})[activeSubtab] || {});
        const currentMap = currentFacts.workCountryDaysByCountry && typeof currentFacts.workCountryDaysByCountry === "object"
          ? currentFacts.workCountryDaysByCountry
          : {};
        const nextDaysMap = {
          ...currentMap,
          [workCountryDaysCountry]: sanitizedValue,
        };
        updateSagsFactsForActiveSubtab({
          workCountryDaysByCountry: {
            ...nextDaysMap,
          },
        });
        const totalInput = elements.sagsFactsBeskatningsretCountryBlock
          ? elements.sagsFactsBeskatningsretCountryBlock.querySelector("[data-sags-work-days-total='true']")
          : null;
        if (totalInput instanceof HTMLInputElement) {
          const currentFacts = ((getState().sagsbehandling.factsBySubtab || {})[activeSubtab] || {});
          const countries = buildWorkCountriesFromFacts(currentFacts);
          totalInput.value = formatWorkDaysTotal(nextDaysMap, countries);
          const totalDays = countries.reduce((sum, country) => {
            const numeric = parseWorkDaysInteger(nextDaysMap[country]);
            return Number.isFinite(numeric) ? sum + numeric : sum;
          }, 0);
          const pctCells = elements.sagsFactsBeskatningsretCountryBlock
            .querySelectorAll("[data-sags-work-country-pct-country]");
          pctCells.forEach((cell) => {
            if (!(cell instanceof HTMLElement)) {
              return;
            }
            const country = String(cell.dataset.sagsWorkCountryPctCountry || "").trim();
            if (!country) {
              return;
            }
            const days = parseWorkDaysInteger(nextDaysMap[country]) || 0;
            cell.textContent = formatWorkDaysPercent(days, totalDays);
          });
          const totalPctCell = elements.sagsFactsBeskatningsretCountryBlock
            .querySelector("[data-sags-work-days-pct-total='true']");
          if (totalPctCell instanceof HTMLElement) {
            totalPctCell.textContent = totalDays > 0 ? "100 %" : "—";
          }
        }
        return;
      }
    });
  }

  // Enforce uppercase text in input boxes when leaving the field.
  document.addEventListener("blur", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement)) {
      return;
    }
    if (target.type !== "text" || target.disabled || target.readOnly) {
      return;
    }
    const normalizedValue = String(target.value || "").toUpperCase();
    if (normalizedValue === target.value) {
      return;
    }
    target.value = normalizedValue;
    target.dispatchEvent(new Event("input", { bubbles: true }));
    target.dispatchEvent(new Event("change", { bubbles: true }));
  }, true);

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
