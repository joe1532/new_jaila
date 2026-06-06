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
import { getLegalSourceSection, getLegalSourcesCatalog } from "./api/legalSourcesApi.js";
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
import { buildSagsQuestionPayload } from "./sags/sagsQuestionBuilder.js";

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
const ENABLE_ANALYSE_TAB = false;

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
  analyseLegalContextPanel: document.getElementById("analyseLegalContextPanel"),
  analyseLegalContextList: document.getElementById("analyseLegalContextList"),
  analyseLegalContextClearBtn: document.getElementById("analyseLegalContextClearBtn"),
  analyseUseSemanticWithLegalContext: document.getElementById("analyseUseSemanticWithLegalContext"),
  analyseLegalLibraryPanel: document.getElementById("analyseLegalLibraryPanel"),
  analyseLegalLibraryCloseBtn: document.getElementById("analyseLegalLibraryCloseBtn"),
  analyseLegalLibrarySearch: document.getElementById("analyseLegalLibrarySearch"),
  analyseLegalLibraryLatency: document.getElementById("analyseLegalLibraryLatency"),
  analyseLegalLibraryCategories: document.getElementById("analyseLegalLibraryCategories"),
  analyseLegalLibrarySources: document.getElementById("analyseLegalLibrarySources"),
  analyseLegalPreviewTitle: document.getElementById("analyseLegalPreviewTitle"),
  analyseLegalPreviewText: document.getElementById("analyseLegalPreviewText"),
  analyseLegalOpenSourceBtn: document.getElementById("analyseLegalOpenSourceBtn"),
  analyseLegalAddSelectionBtn: document.getElementById("analyseLegalAddSelectionBtn"),
  analyseLegalPreviewPager: document.getElementById("analyseLegalPreviewPager"),
  analyseLegalPrevPageBtn: document.getElementById("analyseLegalPrevPageBtn"),
  analyseLegalNextPageBtn: document.getElementById("analyseLegalNextPageBtn"),
  analyseLegalPreviewPageInfo: document.getElementById("analyseLegalPreviewPageInfo"),
  tabButtons: Array.from(document.querySelectorAll(".tab-button")),
  tabAnalyse: document.getElementById("tabAnalyse"),
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
  sagsLegalLibraryToggleBtn: document.getElementById("sagsLegalLibraryToggleBtn"),
  sagsFactsPanel: document.getElementById("sagsFactsPanel"),
  sagsLegalLibraryPanel: document.getElementById("sagsLegalLibraryPanel"),
  sagsLegalLibraryCloseBtn: document.getElementById("sagsLegalLibraryCloseBtn"),
  sagsLegalLibrarySearch: document.getElementById("sagsLegalLibrarySearch"),
  sagsLegalLibraryLatency: document.getElementById("sagsLegalLibraryLatency"),
  sagsLegalLibraryCategories: document.getElementById("sagsLegalLibraryCategories"),
  sagsLegalLibrarySources: document.getElementById("sagsLegalLibrarySources"),
  sagsLegalPreviewTitle: document.getElementById("sagsLegalPreviewTitle"),
  sagsLegalPreviewText: document.getElementById("sagsLegalPreviewText"),
  sagsLegalOpenSourceBtn: document.getElementById("sagsLegalOpenSourceBtn"),
  sagsLegalAddSelectionBtn: document.getElementById("sagsLegalAddSelectionBtn"),
  sagsLegalPreviewPager: document.getElementById("sagsLegalPreviewPager"),
  sagsLegalPrevPageBtn: document.getElementById("sagsLegalPrevPageBtn"),
  sagsLegalNextPageBtn: document.getElementById("sagsLegalNextPageBtn"),
  sagsLegalPreviewPageInfo: document.getElementById("sagsLegalPreviewPageInfo"),
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
  chatUseVectorSearch: document.getElementById("chatUseVectorSearch"),
  chatContextList: document.getElementById("chatContextList"),
  chatLogContent: document.getElementById("chatLogContent"),
};

function normalizeTabId(tabId) {
  const normalized = String(tabId || "").trim();
  if (normalized === "analyse" && !ENABLE_ANALYSE_TAB) {
    return "chat";
  }
  if (normalized === "analyse" || normalized === "sagsbehandling" || normalized === "chat") {
    return normalized;
  }
  return "chat";
}

function applyTabAvailability() {
  if (!ENABLE_ANALYSE_TAB) {
    if (elements.tabAnalyse) {
      elements.tabAnalyse.classList.add("hidden");
      elements.tabAnalyse.setAttribute("aria-hidden", "true");
    }
    if (elements.tabPaneAnalyse) {
      elements.tabPaneAnalyse.classList.add("hidden");
      elements.tabPaneAnalyse.setAttribute("aria-hidden", "true");
    }
  }
}

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

function hasActiveSagsCaseSelected() {
  return Boolean(String((getState().sagsbehandling || {}).activeCaseId || "").trim());
}

function showMissingCasePopup() {
  const message = "Der er ikke valgt en sag endnu. Vælg eller opret først en sag.";
  setStatus(message, "error");
  window.alert(message);
}

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
  renderAnalyseLegalLibrary(elements, state);
  renderChat(elements, state);
  renderSagsbehandling(elements, state);
  updateSagsCaseSelector();
}

function switchTab(tabId) {
  const safeTabId = normalizeTabId(tabId);
  setState({
    ui: {
      activeTab: safeTabId,
    },
  });
  setActiveTab(safeTabId);

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
    if (key === "analyse" && !ENABLE_ANALYSE_TAB) {
      pane.classList.add("hidden");
      return;
    }
    pane.classList.toggle("hidden", key !== state.ui.activeTab);
  });

  elements.tabButtons.forEach((btn) => {
    const isActive = btn.dataset.tab === state.ui.activeTab;
    btn.classList.toggle("tab-button-active", isActive);
  });

  if (safeTabId === "analyse") {
    loadAnalyseSavedLogs();
  } else if (safeTabId === "chat") {
    loadChatSavedLogs();
  } else if (safeTabId === "sagsbehandling") {
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
  setStatus("Klar.", "ok");
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
      legalLibraryPanelOpen: false,
      legalLibrarySearchQuery: "",
      legalLibraryActiveCategory: "",
      legalLibraryActiveDocument: "",
      legalLibraryActiveVersion: "",
      legalLibraryPreviewSection: "",
      legalLibraryPreviewLoadingSourceId: "",
      legalLibrarySectionTextBySourceId: {},
      legalLibraryPreviewPageBySourceId: {},
      legalLibraryPreviewTotalPagesBySourceId: {},
      legalContexts: [],
      useSemanticWithLegalContext: false,
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
      citations: Array.isArray(entry?.citations) ? entry.citations : [],
      retrievalResults: Array.isArray(entry?.retrieval_results) ? entry.retrieval_results : [],
      usedRetrievalResults: Array.isArray(entry?.used_retrieval_results) ? entry.used_retrieval_results : [],
      usedVectorStoreIds: Array.isArray(entry?.used_vector_store_ids) ? entry.used_vector_store_ids : [],
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
  initialChat.useVectorSearch = prev.useVectorSearch !== false;
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

async function loadLegalSourcesCatalogIfNeeded(forceReload = false) {
  const sags = getState().sagsbehandling || {};
  const hasExistingCatalog =
    Array.isArray(sags.legalLibraryCatalog) && sags.legalLibraryCatalog.length > 0;
  if (!forceReload && sags.legalLibraryCatalogLoaded && hasExistingCatalog) {
    return;
  }
  try {
    const data = await getLegalSourcesCatalog();
    const categories = Array.isArray(data.categories) ? data.categories : [];
    const documents = Array.isArray(data.documents) ? data.documents : [];
    setState({
      sagsbehandling: {
        legalLibraryCategories: categories,
        legalLibraryCatalog: documents,
        legalLibraryCatalogLoaded: true,
      },
    });
    if (getState().analyse.legalLibraryPanelOpen && !String(getState().analyse.legalLibraryActiveCategory || "").trim()) {
      setState({
        analyse: {
          legalLibraryActiveCategory: String(categories[0]?.id || ""),
        },
      });
    }
    renderSagsbehandling(elements, getState());
    renderAnalyseLegalLibrary();
  } catch (err) {
    setStatus("Kunne ikke hente retskildekatalog fra server: " + (err.message || "Ukendt fejl"), "error");
  }
}

async function loadLegalSourceSectionTextIfNeeded(sourceId, page = 1) {
  const safeSourceId = String(sourceId || "").trim();
  if (!safeSourceId) {
    return;
  }
  const safePage = Math.max(1, Number(page) || 1);
  const cacheKey = `${safeSourceId}::${safePage}`;
  const sags = getState().sagsbehandling || {};
  const cache = sags.legalLibrarySectionTextBySourceId || {};
  if (cache[cacheKey]) {
    setState({
      sagsbehandling: {
        legalLibraryPreviewPageBySourceId: {
          ...(getState().sagsbehandling.legalLibraryPreviewPageBySourceId || {}),
          [safeSourceId]: safePage,
        },
      },
    });
    renderSagsbehandling(elements, getState());
    return;
  }
  setState({
    sagsbehandling: {
      legalLibraryPreviewLoadingSourceId: safeSourceId,
    },
  });
  renderSagsbehandling(elements, getState());
  try {
    const data = await getLegalSourceSection(safeSourceId, safePage);
    const previewText = String((data && data.text) || "").trim();
    const responsePage = Math.max(1, Number((data && data.page) || safePage) || safePage);
    const responseTotalPages = Math.max(1, Number((data && data.total_pages) || 1) || 1);
    const responseCacheKey = `${safeSourceId}::${responsePage}`;
    setState({
      sagsbehandling: {
        legalLibrarySectionTextBySourceId: {
          ...(getState().sagsbehandling.legalLibrarySectionTextBySourceId || {}),
          [responseCacheKey]: previewText || "Ingen tekst fundet.",
        },
        legalLibraryPreviewPageBySourceId: {
          ...(getState().sagsbehandling.legalLibraryPreviewPageBySourceId || {}),
          [safeSourceId]: responsePage,
        },
        legalLibraryPreviewTotalPagesBySourceId: {
          ...(getState().sagsbehandling.legalLibraryPreviewTotalPagesBySourceId || {}),
          [safeSourceId]: responseTotalPages,
        },
        legalLibraryPreviewLoadingSourceId: "",
      },
    });
    renderSagsbehandling(elements, getState());
  } catch (err) {
    setState({
      sagsbehandling: {
        legalLibraryPreviewLoadingSourceId: "",
      },
    });
    renderSagsbehandling(elements, getState());
    setStatus("Kunne ikke hente visning af retskilde: " + (err.message || "Ukendt fejl"), "error");
  }
}

function normalizeAnalyseLegalSearchValue(value) {
  return String(value || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function matchesAnalyseLegalQuery(doc, query) {
  if (!query) return true;
  const tokens = query.split(" ").filter(Boolean);
  if (!tokens.length) return true;
  const parts = [doc.title || "", ...(doc.tags || [])];
  (doc.versions || []).forEach((version) => {
    parts.push(version.label || "");
    (version.sections || []).forEach((section) => {
      parts.push(section.title || "");
      parts.push(section.text || "");
      parts.push(section.sourceId || "");
    });
  });
  const haystack = normalizeAnalyseLegalSearchValue(parts.join(" "));
  return tokens.every((token) => haystack.includes(token));
}

function getDefaultAnalyseLegalSelection(catalog, preferredCategoryId = "dobbeltbeskatningsoverenskomster") {
  const docs = Array.isArray(catalog) ? catalog : [];
  if (!docs.length) {
    return {
      categoryId: "",
      documentId: "",
      versionId: "",
      sectionId: "",
      sourceRefId: "",
    };
  }
  const preferredDoc = docs.find((doc) => String(doc?.category || "").trim() === preferredCategoryId);
  const selectedDoc = preferredDoc || docs[0];
  const versions = Array.isArray(selectedDoc?.versions) ? selectedDoc.versions : [];
  const selectedVersion = versions[0] || null;
  const sections = Array.isArray(selectedVersion?.sections) ? selectedVersion.sections : [];
  const selectedSection = sections[0] || null;
  return {
    categoryId: String(selectedDoc?.category || preferredCategoryId || "").trim(),
    documentId: String(selectedDoc?.id || "").trim(),
    versionId: String(selectedVersion?.id || "").trim(),
    sectionId: String(selectedSection?.id || "").trim(),
    sourceRefId: String(selectedSection?.sourceId || "").trim(),
  };
}

function renderAnalyseLegalLibrary() {
  const panel = elements.analyseLegalLibraryPanel;
  if (!panel) return;
  const state = getState();
  const analyse = state.analyse || {};
  const sags = state.sagsbehandling || {};
  const isOpen = Boolean(analyse.legalLibraryPanelOpen);
  panel.classList.toggle("hidden", !isOpen);
  if (!isOpen) {
    return;
  }

  const categories = Array.isArray(sags.legalLibraryCategories) ? sags.legalLibraryCategories : [];
  const catalog = Array.isArray(sags.legalLibraryCatalog) ? sags.legalLibraryCatalog : [];
  const searchQuery = String(analyse.legalLibrarySearchQuery || "");
  if (elements.analyseLegalLibrarySearch && elements.analyseLegalLibrarySearch.value !== searchQuery) {
    elements.analyseLegalLibrarySearch.value = searchQuery;
  }
  const normalizedQuery = normalizeAnalyseLegalSearchValue(searchQuery);
  const filteredCatalog = catalog.filter((doc) => matchesAnalyseLegalQuery(doc, normalizedQuery));
  const activeCategory = String(analyse.legalLibraryActiveCategory || "").trim();
  const activeDocument = String(analyse.legalLibraryActiveDocument || "").trim();
  const activeVersion = String(analyse.legalLibraryActiveVersion || "").trim();
  const activeSection = String(analyse.legalLibraryPreviewSection || "").trim();

  if (elements.analyseLegalLibraryCategories) {
    elements.analyseLegalLibraryCategories.innerHTML = "";
    categories.forEach((category) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "button-secondary sags-legal-category-button";
      btn.dataset.analyseLegalCategoryId = category.id || "";
      btn.textContent = category.title || category.id || "Kategori";
      if ((category.id || "") === activeCategory) {
        btn.classList.add("sags-legal-category-button-active");
      }
      elements.analyseLegalLibraryCategories.appendChild(btn);
    });
  }

  const categoryDocs = filteredCatalog.filter((doc) => {
    const docCategory = String(doc.category || "").trim();
    return !activeCategory || docCategory === activeCategory;
  });

  if (elements.analyseLegalLibrarySources) {
    elements.analyseLegalLibrarySources.innerHTML = "";
    if (!categoryDocs.length) {
      const empty = document.createElement("p");
      empty.className = "sags-legal-library-empty";
      empty.textContent = catalog.length
        ? "Ingen retskilder matcher søgningen."
        : "Ingen retskilder fundet fra server endnu.";
      elements.analyseLegalLibrarySources.appendChild(empty);
    } else {
      categoryDocs.forEach((doc) => {
        const docBtn = document.createElement("button");
        docBtn.type = "button";
        docBtn.className = "button-secondary sags-legal-source-button";
        docBtn.dataset.analyseLegalDocumentId = doc.id || "";
        docBtn.textContent = doc.title || doc.id || "Dokument";
        if ((doc.id || "") === activeDocument) {
          docBtn.classList.add("sags-legal-source-button-active");
        }
        elements.analyseLegalLibrarySources.appendChild(docBtn);

        if ((doc.id || "") !== activeDocument) {
          return;
        }
        const versions = Array.isArray(doc.versions) ? doc.versions : [];
        versions.forEach((version) => {
          const versionBtn = document.createElement("button");
          versionBtn.type = "button";
          versionBtn.className = "button-secondary sags-legal-version-button";
          versionBtn.dataset.analyseLegalVersionId = version.id || "";
          versionBtn.textContent = version.label || version.id || "Version";
          if ((version.id || "") === activeVersion) {
            versionBtn.classList.add("sags-legal-source-button-active");
          }
          elements.analyseLegalLibrarySources.appendChild(versionBtn);
          if ((version.id || "") !== activeVersion) {
            return;
          }
          const sections = Array.isArray(version.sections) ? version.sections : [];
          sections.forEach((section) => {
            const row = document.createElement("div");
            row.className = "sags-legal-section-row";
            const sectionBtn = document.createElement("button");
            sectionBtn.type = "button";
            sectionBtn.className = "button-secondary sags-legal-section-button";
            sectionBtn.dataset.analyseLegalSourceId = section.id || "";
            sectionBtn.dataset.analyseLegalSourceRef = section.sourceId || "";
            sectionBtn.dataset.analyseLegalSourceTitle = section.title || "";
            sectionBtn.textContent = section.title || section.id || "Afsnit";
            if ((section.id || "") === activeSection) {
              sectionBtn.classList.add("sags-legal-source-button-active");
            }
            row.appendChild(sectionBtn);
            elements.analyseLegalLibrarySources.appendChild(row);
          });
        });
      });
    }
  }

  const selectedDoc = categoryDocs.find((doc) => (doc.id || "") === activeDocument) || null;
  const selectedVersion = selectedDoc
    ? (selectedDoc.versions || []).find((version) => (version.id || "") === activeVersion) || null
    : null;
  const selectedSection = selectedVersion
    ? (selectedVersion.sections || []).find((section) => (section.id || "") === activeSection) || null
    : null;
  const sourceRefId = String(selectedSection?.sourceId || "").trim();
  const previewTitle = selectedSection?.title || "Vælg en retskilde";
  if (elements.analyseLegalPreviewTitle) {
    elements.analyseLegalPreviewTitle.textContent = previewTitle;
  }
  if (elements.analyseLegalPreviewText) {
    const loadingSourceId = String(analyse.legalLibraryPreviewLoadingSourceId || "").trim();
    const page = Math.max(
      1,
      Number((analyse.legalLibraryPreviewPageBySourceId || {})[sourceRefId] || 1) || 1,
    );
    const cacheKey = sourceRefId ? `${sourceRefId}::${page}` : "";
    const previewText = cacheKey
      ? String((analyse.legalLibrarySectionTextBySourceId || {})[cacheKey] || "").trim()
      : "";
    if (!sourceRefId) {
      elements.analyseLegalPreviewText.textContent =
        "Vælg først en kategori til højre, og derefter en retskilde for at se teksten her.";
    } else if (loadingSourceId === sourceRefId) {
      elements.analyseLegalPreviewText.textContent = "Indlæser...";
    } else {
      elements.analyseLegalPreviewText.textContent = previewText || "Ingen tekst fundet.";
    }
  }
  if (elements.analyseLegalOpenSourceBtn) {
    elements.analyseLegalOpenSourceBtn.classList.toggle("hidden", !sourceRefId);
    elements.analyseLegalOpenSourceBtn.dataset.analyseLegalSourceId = sourceRefId;
  }
  if (elements.analyseLegalAddSelectionBtn) {
    elements.analyseLegalAddSelectionBtn.classList.toggle("hidden", !sourceRefId);
    elements.analyseLegalAddSelectionBtn.dataset.analyseLegalSourceId = sourceRefId;
    elements.analyseLegalAddSelectionBtn.dataset.analyseLegalSectionId = String(selectedSection?.id || "");
    elements.analyseLegalAddSelectionBtn.dataset.analyseLegalContextTitle = previewTitle;
  }
  if (elements.analyseLegalPreviewPager) {
    const currentPage = Math.max(
      1,
      Number((analyse.legalLibraryPreviewPageBySourceId || {})[sourceRefId] || 1) || 1,
    );
    const totalPages = Math.max(
      1,
      Number((analyse.legalLibraryPreviewTotalPagesBySourceId || {})[sourceRefId] || 1) || 1,
    );
    const showPager = Boolean(sourceRefId && totalPages > 1);
    elements.analyseLegalPreviewPager.classList.toggle("hidden", !showPager);
    if (elements.analyseLegalPreviewPageInfo) {
      elements.analyseLegalPreviewPageInfo.textContent = `Side ${currentPage}/${totalPages}`;
    }
    if (elements.analyseLegalPrevPageBtn) {
      elements.analyseLegalPrevPageBtn.disabled = currentPage <= 1;
      elements.analyseLegalPrevPageBtn.dataset.analyseLegalSourceId = sourceRefId;
      elements.analyseLegalPrevPageBtn.dataset.analyseLegalCurrentPage = String(currentPage);
    }
    if (elements.analyseLegalNextPageBtn) {
      elements.analyseLegalNextPageBtn.disabled = currentPage >= totalPages;
      elements.analyseLegalNextPageBtn.dataset.analyseLegalSourceId = sourceRefId;
      elements.analyseLegalNextPageBtn.dataset.analyseLegalCurrentPage = String(currentPage);
      elements.analyseLegalNextPageBtn.dataset.analyseLegalTotalPages = String(totalPages);
    }
  }
}

async function loadAnalyseLegalSourceSectionTextIfNeeded(sourceId, page = 1) {
  const safeSourceId = String(sourceId || "").trim();
  if (!safeSourceId) return;
  const safePage = Math.max(1, Number(page) || 1);
  const cacheKey = `${safeSourceId}::${safePage}`;
  const analyse = getState().analyse || {};
  const cache = analyse.legalLibrarySectionTextBySourceId || {};
  if (cache[cacheKey]) {
    setState({
      analyse: {
        legalLibraryPreviewPageBySourceId: {
          ...(getState().analyse.legalLibraryPreviewPageBySourceId || {}),
          [safeSourceId]: safePage,
        },
      },
    });
    renderAnalyseLegalLibrary();
    return;
  }
  setState({
    analyse: {
      legalLibraryPreviewLoadingSourceId: safeSourceId,
    },
  });
  renderAnalyseLegalLibrary();
  try {
    const data = await getLegalSourceSection(safeSourceId, safePage);
    const previewText = String((data && data.text) || "").trim();
    const responsePage = Math.max(1, Number((data && data.page) || safePage) || safePage);
    const responseTotalPages = Math.max(1, Number((data && data.total_pages) || 1) || 1);
    const responseCacheKey = `${safeSourceId}::${responsePage}`;
    setState({
      analyse: {
        legalLibrarySectionTextBySourceId: {
          ...(getState().analyse.legalLibrarySectionTextBySourceId || {}),
          [responseCacheKey]: previewText || "Ingen tekst fundet.",
        },
        legalLibraryPreviewPageBySourceId: {
          ...(getState().analyse.legalLibraryPreviewPageBySourceId || {}),
          [safeSourceId]: responsePage,
        },
        legalLibraryPreviewTotalPagesBySourceId: {
          ...(getState().analyse.legalLibraryPreviewTotalPagesBySourceId || {}),
          [safeSourceId]: responseTotalPages,
        },
        legalLibraryPreviewLoadingSourceId: "",
      },
    });
    renderAnalyseLegalLibrary();
  } catch (err) {
    setState({
      analyse: {
        legalLibraryPreviewLoadingSourceId: "",
      },
    });
    renderAnalyseLegalLibrary();
    setStatus("Kunne ikke hente visning af retskilde: " + (err.message || "Ukendt fejl"), "error");
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
    selected_legal_sources_by_subtab: sags.selectedLegalSourcesBySubtab || {},
    legal_library_active_category_by_subtab: sags.legalLibraryActiveCategoryBySubtab || {},
    legal_library_preview_source_by_subtab: sags.legalLibraryPreviewSourceBySubtab || {},
    legal_library_active_document_by_subtab: sags.legalLibraryActiveDocumentBySubtab || {},
    legal_library_active_version_by_subtab: sags.legalLibraryActiveVersionBySubtab || {},
    legal_library_preview_section_by_subtab: sags.legalLibraryPreviewSectionBySubtab || {},
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
      legalLibraryPanelOpen: false,
      legalLibrarySearchQuery: "",
      selectedLegalSourcesBySubtab: caseEntry?.selected_legal_sources_by_subtab || {},
      legalLibraryActiveCategoryBySubtab: caseEntry?.legal_library_active_category_by_subtab || {},
      legalLibraryPreviewSourceBySubtab: caseEntry?.legal_library_preview_source_by_subtab || {},
      legalLibraryActiveDocumentBySubtab: caseEntry?.legal_library_active_document_by_subtab || {},
      legalLibraryActiveVersionBySubtab: caseEntry?.legal_library_active_version_by_subtab || {},
      legalLibraryPreviewSectionBySubtab: caseEntry?.legal_library_preview_section_by_subtab || {},
      legalLibraryCategories: [],
      legalLibraryCatalog: [],
      legalLibraryCatalogLoaded: false,
      legalLibrarySectionTextBySourceId: {},
      legalLibraryPreviewLoadingSourceId: "",
      legalLibraryPreviewPageBySourceId: {},
      legalLibraryPreviewTotalPagesBySourceId: {},
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
        legalLibraryPanelOpen: false,
        legalLibrarySearchQuery: "",
        selectedLegalSourcesBySubtab: {},
        legalLibraryActiveCategoryBySubtab: {},
        legalLibraryPreviewSourceBySubtab: {},
        legalLibraryActiveDocumentBySubtab: {},
        legalLibraryActiveVersionBySubtab: {},
        legalLibraryPreviewSectionBySubtab: {},
        legalLibraryCategories: [],
        legalLibraryCatalog: [],
        legalLibraryCatalogLoaded: false,
        legalLibrarySectionTextBySourceId: {},
        legalLibraryPreviewLoadingSourceId: "",
        legalLibraryPreviewPageBySourceId: {},
        legalLibraryPreviewTotalPagesBySourceId: {},
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
        legalLibraryPanelOpen: false,
        legalLibrarySearchQuery: "",
        selectedLegalSourcesBySubtab: {},
        legalLibraryActiveCategoryBySubtab: {},
        legalLibraryPreviewSourceBySubtab: {},
        legalLibraryActiveDocumentBySubtab: {},
        legalLibraryActiveVersionBySubtab: {},
        legalLibraryPreviewSectionBySubtab: {},
        legalLibraryCategories: [],
        legalLibraryCatalog: [],
        legalLibraryCatalogLoaded: false,
        legalLibrarySectionTextBySourceId: {},
        legalLibraryPreviewLoadingSourceId: "",
        legalLibraryPreviewPageBySourceId: {},
        legalLibraryPreviewTotalPagesBySourceId: {},
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
    const legalContexts = (getState().analyse.legalContexts || [])
      .map((entry) => String(entry?.previewText || "").trim())
      .filter(Boolean);
    const hasLegalContexts = legalContexts.length > 0;
    const ctx = {
      sourceTab: "analyse",
      subtab: null,
      signal: analyseAbortController.signal,
      legalContextBlocks: legalContexts,
      useSemanticSearchWithLegalContext: hasLegalContexts
        ? Boolean(getState().analyse.useSemanticWithLegalContext)
        : true,
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
  let caseFacts = null;
  let decisionPackage = null;
  let generatedQuestion = "";
  const sharedFacts = getState().sagsbehandling.sharedFacts || {};
  const subtabOutputs = getState().sagsbehandling.subtabOutputs || {};
  const subtabOutputLocked = getState().sagsbehandling.subtabOutputLocked || {};
  const freeText = (elements.sagsbehandlingInput ? elements.sagsbehandlingInput.value : "").trim();
  const questionPayload = buildSagsQuestionPayload({
    activeSubtab,
    freeText,
    factsBySubtab: getState().sagsbehandling.factsBySubtab || {},
    subtabLabels: SAGS_SUBTAB_LABELS,
  });
  if (!questionPayload.ok) {
    if (questionPayload.systemMessage) {
      addSagsbehandlingMessage("system", questionPayload.systemMessage);
    }
    setStatus(questionPayload.errorMessage || "Kunne ikke bygge spørgsmål.", "error");
    return;
  }
  caseFacts = questionPayload.caseFacts || null;
  decisionPackage = questionPayload.decisionPackage || null;
  generatedQuestion = String(questionPayload.generatedQuestion || "");
  addSagsbehandlingMessage("user", String(questionPayload.userMessage || "Sagsspørgsmål sendt til vurdering."));
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
      sagsDecisionPackage: decisionPackage,
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
          incomeDboArticle: "",
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
    const useVectorSearch = getState().chat.useVectorSearch !== false;
    const sessionId = getOrCreateChatSessionId();
    const opts = {
      signal: chatAbortController.signal,
      context: {
        useVectorSearch,
      },
    };
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
              usedVectorStoreIds: Array.isArray(evt.used_vector_store_ids) ? evt.used_vector_store_ids : [],
              vectorSearchEnabledLastResponse: Boolean(evt.vector_search_enabled),
              citations: Array.isArray(evt.citations) ? evt.citations : [],
              retrievalResults: Array.isArray(evt.retrieval_results) ? evt.retrieval_results : [],
              usedRetrievalResults: Array.isArray(evt.used_retrieval_results)
                ? evt.used_retrieval_results
                : (Array.isArray(evt.retrieval_results) ? evt.retrieval_results : []),
            },
          });
          updateLastChatMessageText(evt.answer || accumulated || "Intet svar returneret.");
          renderChat(elements, getState());
          const modeLabel = evt.vector_search_enabled ? "vector search: aktiv" : "vector search: inaktiv";
          setStatus("Chat svar modtaget. Model: " + (evt.used_model || "ukendt") + " (" + modeLabel + ")", "ok");
          const user = getActiveUser();
          if (user) {
            const snapshotMessages = getState().chat.messages || [];
            saveChatLog(
              user,
              sessionId,
              snapshotMessages,
              evt.used_model || "",
              evt.response_id || null,
              {
                citations: Array.isArray(evt.citations) ? evt.citations : [],
                retrievalResults: Array.isArray(evt.retrieval_results) ? evt.retrieval_results : [],
                usedRetrievalResults: Array.isArray(evt.used_retrieval_results)
                  ? evt.used_retrieval_results
                  : (Array.isArray(evt.retrieval_results) ? evt.retrieval_results : []),
                usedVectorStoreIds: Array.isArray(evt.used_vector_store_ids) ? evt.used_vector_store_ids : [],
              },
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
          usedVectorStoreIds: Array.isArray(data.used_vector_store_ids) ? data.used_vector_store_ids : [],
          vectorSearchEnabledLastResponse: Boolean(data.vector_search_enabled),
          citations: Array.isArray(data.citations) ? data.citations : [],
          retrievalResults: Array.isArray(data.retrieval_results) ? data.retrieval_results : [],
          usedRetrievalResults: Array.isArray(data.used_retrieval_results)
            ? data.used_retrieval_results
            : (Array.isArray(data.retrieval_results) ? data.retrieval_results : []),
        },
      });
      addChatMessage("assistant", data.answer || "Intet svar returneret.");
      const modeLabel = data.vector_search_enabled ? "vector search: aktiv" : "vector search: inaktiv";
      setStatus("Chat svar modtaget. Model: " + (data.used_model || "ukendt") + " (" + modeLabel + ")", "ok");
      const user = getActiveUser();
      if (user) {
        const snapshotMessages = getState().chat.messages || [];
        saveChatLog(
          user,
          sessionId,
          snapshotMessages,
          data.used_model || "",
          data.response_id || null,
          {
            citations: Array.isArray(data.citations) ? data.citations : [],
            retrievalResults: Array.isArray(data.retrieval_results) ? data.retrieval_results : [],
            usedRetrievalResults: Array.isArray(data.used_retrieval_results)
              ? data.used_retrieval_results
              : (Array.isArray(data.retrieval_results) ? data.retrieval_results : []),
            usedVectorStoreIds: Array.isArray(data.used_vector_store_ids) ? data.used_vector_store_ids : [],
          },
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
    const chatState = getState().chat || {};
    const data = await exportChatPdf(messages, sessionId, {
      citations: chatState.citations || [],
      retrievalResults: chatState.retrievalResults || [],
      usedRetrievalResults: chatState.usedRetrievalResults || [],
      usedVectorStoreIds: chatState.usedVectorStoreIds || [],
    });
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
  const legalLibraryLatencySamples = [];
  const analyseLegalLibraryLatencySamples = [];
  const showLegalLibraryLatency = (actionLabel, startMs) => {
    if (!elements.sagsLegalLibraryLatency) {
      return;
    }
    const elapsedMs = Math.max(0, Math.round(performance.now() - startMs));
    legalLibraryLatencySamples.push(elapsedMs);
    if (legalLibraryLatencySamples.length > 10) {
      legalLibraryLatencySamples.shift();
    }
    const avgMs = Math.round(
      legalLibraryLatencySamples.reduce((sum, value) => sum + value, 0)
      / Math.max(1, legalLibraryLatencySamples.length),
    );
    const label = String(actionLabel || "").trim();
    elements.sagsLegalLibraryLatency.textContent = label
      ? `${label}: ${elapsedMs} ms (snit ${legalLibraryLatencySamples.length}: ${avgMs} ms)`
      : `Latency: ${elapsedMs} ms (snit ${legalLibraryLatencySamples.length}: ${avgMs} ms)`;
  };
  const showAnalyseLegalLibraryLatency = (actionLabel, startMs) => {
    if (!elements.analyseLegalLibraryLatency) {
      return;
    }
    const elapsedMs = Math.max(0, Math.round(performance.now() - startMs));
    analyseLegalLibraryLatencySamples.push(elapsedMs);
    if (analyseLegalLibraryLatencySamples.length > 10) {
      analyseLegalLibraryLatencySamples.shift();
    }
    const avgMs = Math.round(
      analyseLegalLibraryLatencySamples.reduce((sum, value) => sum + value, 0)
      / Math.max(1, analyseLegalLibraryLatencySamples.length),
    );
    const label = String(actionLabel || "").trim();
    elements.analyseLegalLibraryLatency.textContent = label
      ? `${label}: ${elapsedMs} ms (snit ${analyseLegalLibraryLatencySamples.length}: ${avgMs} ms)`
      : `Latency: ${elapsedMs} ms (snit ${analyseLegalLibraryLatencySamples.length}: ${avgMs} ms)`;
  };

  elements.tabButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      switchTab(btn.dataset.tab || "chat");
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
  if (elements.analyseExtraBtn) {
    elements.analyseExtraBtn.addEventListener("click", () => {
      const startMs = performance.now();
      const analyse = getState().analyse || {};
      const isOpen = Boolean(analyse.legalLibraryPanelOpen);
      const catalog = Array.isArray((getState().sagsbehandling || {}).legalLibraryCatalog)
        ? (getState().sagsbehandling || {}).legalLibraryCatalog
        : [];
      const defaults = getDefaultAnalyseLegalSelection(catalog);
      setState({
        analyse: {
          legalLibraryPanelOpen: !isOpen,
          legalLibrarySearchQuery: "",
          legalLibraryActiveCategory: !isOpen ? defaults.categoryId : "",
          legalLibraryActiveDocument: !isOpen ? defaults.documentId : "",
          legalLibraryActiveVersion: !isOpen ? defaults.versionId : "",
          legalLibraryPreviewSection: !isOpen ? defaults.sectionId : "",
        },
      });
      renderAnalyse(elements, getState());
      renderAnalyseLegalLibrary();
      if (!isOpen) {
        loadLegalSourcesCatalogIfNeeded(true);
        if (defaults.sourceRefId) {
          loadAnalyseLegalSourceSectionTextIfNeeded(defaults.sourceRefId, 1);
        }
      }
      showAnalyseLegalLibraryLatency("Toggle panel", startMs);
    });
  }
  if (elements.analyseLegalLibraryCloseBtn) {
    elements.analyseLegalLibraryCloseBtn.addEventListener("click", () => {
      setState({
        analyse: {
          legalLibraryPanelOpen: false,
        },
      });
      renderAnalyse(elements, getState());
      renderAnalyseLegalLibrary();
    });
  }
  if (elements.analyseLegalLibrarySearch) {
    elements.analyseLegalLibrarySearch.addEventListener("input", () => {
      const startMs = performance.now();
      setState({
        analyse: {
          legalLibrarySearchQuery: elements.analyseLegalLibrarySearch.value,
        },
      });
      renderAnalyseLegalLibrary();
      showAnalyseLegalLibraryLatency("Søgning", startMs);
    });
  }
  if (elements.analyseLegalLibraryCategories) {
    elements.analyseLegalLibraryCategories.addEventListener("click", (event) => {
      const startMs = performance.now();
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      const button = target.closest("[data-analyse-legal-category-id]");
      if (!(button instanceof HTMLElement)) return;
      const categoryId = String(button.dataset.analyseLegalCategoryId || "").trim();
      if (!categoryId) return;
      const catalog = Array.isArray((getState().sagsbehandling || {}).legalLibraryCatalog)
        ? (getState().sagsbehandling || {}).legalLibraryCatalog
        : [];
      const categoryDocs = catalog.filter((doc) => String(doc?.category || "").trim() === categoryId);
      const defaults = getDefaultAnalyseLegalSelection(categoryDocs, categoryId);
      setState({
        analyse: {
          legalLibraryActiveCategory: categoryId,
          legalLibraryActiveDocument: defaults.documentId,
          legalLibraryActiveVersion: defaults.versionId,
          legalLibraryPreviewSection: defaults.sectionId,
        },
      });
      renderAnalyseLegalLibrary();
      if (defaults.sourceRefId) {
        loadAnalyseLegalSourceSectionTextIfNeeded(defaults.sourceRefId, 1);
      }
      showAnalyseLegalLibraryLatency("Kategori", startMs);
    });
  }
  if (elements.analyseLegalLibrarySources) {
    elements.analyseLegalLibrarySources.addEventListener("click", (event) => {
      const startMs = performance.now();
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      const docBtn = target.closest("[data-analyse-legal-document-id]");
      if (docBtn instanceof HTMLElement) {
        const documentId = String(docBtn.dataset.analyseLegalDocumentId || "").trim();
        if (!documentId) return;
        const catalog = Array.isArray((getState().sagsbehandling || {}).legalLibraryCatalog)
          ? (getState().sagsbehandling || {}).legalLibraryCatalog
          : [];
        const selectedDoc = catalog.find((doc) => String(doc.id || "").trim() === documentId);
        const firstVersionId = String(selectedDoc?.versions?.[0]?.id || "");
        const firstSectionId = String(selectedDoc?.versions?.[0]?.sections?.[0]?.id || "");
        const firstSourceRefId = String(selectedDoc?.versions?.[0]?.sections?.[0]?.sourceId || "");
        setState({
          analyse: {
            legalLibraryActiveDocument: documentId,
            legalLibraryActiveVersion: firstVersionId,
            legalLibraryPreviewSection: firstSectionId,
          },
        });
        renderAnalyseLegalLibrary();
        if (firstSourceRefId) {
          loadAnalyseLegalSourceSectionTextIfNeeded(firstSourceRefId, 1);
        }
        showAnalyseLegalLibraryLatency("Dokument", startMs);
        return;
      }
      const versionBtn = target.closest("[data-analyse-legal-version-id]");
      if (versionBtn instanceof HTMLElement) {
        const versionId = String(versionBtn.dataset.analyseLegalVersionId || "").trim();
        if (!versionId) return;
        const catalog = Array.isArray((getState().sagsbehandling || {}).legalLibraryCatalog)
          ? (getState().sagsbehandling || {}).legalLibraryCatalog
          : [];
        const activeDocumentId = String((getState().analyse || {}).legalLibraryActiveDocument || "").trim();
        const activeDocument = catalog.find((doc) => String(doc.id || "").trim() === activeDocumentId);
        const selectedVersion = (activeDocument?.versions || []).find(
          (version) => String(version?.id || "").trim() === versionId,
        );
        const firstSectionId = String(selectedVersion?.sections?.[0]?.id || "");
        const firstSourceRefId = String(selectedVersion?.sections?.[0]?.sourceId || "");
        setState({
          analyse: {
            legalLibraryActiveVersion: versionId,
            legalLibraryPreviewSection: firstSectionId,
          },
        });
        renderAnalyseLegalLibrary();
        if (firstSourceRefId) {
          loadAnalyseLegalSourceSectionTextIfNeeded(firstSourceRefId, 1);
        }
        showAnalyseLegalLibraryLatency("Version", startMs);
        return;
      }
      const sourceBtn = target.closest("[data-analyse-legal-source-id]");
      if (!(sourceBtn instanceof HTMLElement)) return;
      const sectionId = String(sourceBtn.dataset.analyseLegalSourceId || "").trim();
      const sourceRefId = String(sourceBtn.dataset.analyseLegalSourceRef || "").trim();
      if (!sectionId || !sourceRefId) return;
      setState({
        analyse: {
          legalLibraryPreviewSection: sectionId,
          legalLibraryPreviewPageBySourceId: {
            ...(getState().analyse.legalLibraryPreviewPageBySourceId || {}),
            [sourceRefId]: 1,
          },
        },
      });
      renderAnalyseLegalLibrary();
      showAnalyseLegalLibraryLatency("Paragraf visning", startMs);
      loadAnalyseLegalSourceSectionTextIfNeeded(sourceRefId, 1);
    });
  }
  if (elements.analyseLegalOpenSourceBtn) {
    elements.analyseLegalOpenSourceBtn.addEventListener("click", () => {
      const sourceId = String(elements.analyseLegalOpenSourceBtn.dataset.analyseLegalSourceId || "").trim();
      if (!sourceId) {
        setStatus("Ingen kilde valgt endnu.", "error");
        return;
      }
      window.open(`/api/legal-sources/file/${encodeURIComponent(sourceId)}`, "_blank", "noopener,noreferrer");
    });
  }
  if (elements.analyseLegalAddSelectionBtn) {
    elements.analyseLegalAddSelectionBtn.addEventListener("click", () => {
      if (!hasActiveSagsCaseSelected()) {
        showMissingCasePopup();
        return;
      }
      const previewEl = elements.analyseLegalPreviewText;
      if (!(previewEl instanceof HTMLElement)) return;
      const selection = window.getSelection();
      if (!selection || selection.rangeCount === 0) {
        setStatus("Markér først den tekst, du vil tilføje.", "error");
        return;
      }
      const selectedText = String(selection.toString() || "").trim();
      if (!selectedText || selectedText.length < 10) {
        setStatus("Markeringen er for kort. Vælg et større tekstudsnit.", "error");
        return;
      }
      const range = selection.getRangeAt(0);
      const containerNode = range.commonAncestorContainer;
      const selectionNode = containerNode.nodeType === Node.TEXT_NODE
        ? containerNode.parentNode
        : containerNode;
      if (!(selectionNode instanceof Node) || !previewEl.contains(selectionNode)) {
        setStatus("Markeringen skal være inde i visningsboksen.", "error");
        return;
      }
      const sourceId = String(elements.analyseLegalAddSelectionBtn.dataset.analyseLegalSourceId || "").trim();
      const sectionId = String(elements.analyseLegalAddSelectionBtn.dataset.analyseLegalSectionId || "").trim();
      const contextTitleRaw = String(elements.analyseLegalAddSelectionBtn.dataset.analyseLegalContextTitle || "").trim();
      if (!sourceId || !sectionId || !contextTitleRaw) {
        setStatus("Vælg en paragraf først.", "error");
        return;
      }
      const trimmedText = selectedText.length > 6000 ? `${selectedText.slice(0, 6000)}...` : selectedText;
      const id = `analyse_legal_selection:${sourceId}:${sectionId}:${Date.now()}`;
      const currentList = Array.isArray(getState().analyse.legalContexts) ? getState().analyse.legalContexts : [];
      const nextList = [
        ...currentList,
        {
          id,
          sourceType: "legal_selection",
          title: `${contextTitleRaw} (markeret tekst)`,
          previewText: trimmedText,
        },
      ];
      setState({
        analyse: {
          legalContexts: nextList,
        },
      });
      renderAnalyse(elements, getState());
      setStatus("Markeret retskildetekst er tilføjet til analysen.", "ok");
    });
  }
  if (elements.analyseLegalPrevPageBtn) {
    elements.analyseLegalPrevPageBtn.addEventListener("click", () => {
      const sourceId = String(elements.analyseLegalPrevPageBtn.dataset.analyseLegalSourceId || "").trim();
      if (!sourceId) return;
      const currentPage = Math.max(
        1,
        Number(elements.analyseLegalPrevPageBtn.dataset.analyseLegalCurrentPage || "1") || 1,
      );
      const nextPage = Math.max(1, currentPage - 1);
      if (nextPage === currentPage) return;
      loadAnalyseLegalSourceSectionTextIfNeeded(sourceId, nextPage);
    });
  }
  if (elements.analyseLegalNextPageBtn) {
    elements.analyseLegalNextPageBtn.addEventListener("click", () => {
      const sourceId = String(elements.analyseLegalNextPageBtn.dataset.analyseLegalSourceId || "").trim();
      if (!sourceId) return;
      const currentPage = Math.max(
        1,
        Number(elements.analyseLegalNextPageBtn.dataset.analyseLegalCurrentPage || "1") || 1,
      );
      const totalPages = Math.max(
        1,
        Number(elements.analyseLegalNextPageBtn.dataset.analyseLegalTotalPages || "1") || 1,
      );
      const nextPage = Math.min(totalPages, currentPage + 1);
      if (nextPage === currentPage) return;
      loadAnalyseLegalSourceSectionTextIfNeeded(sourceId, nextPage);
    });
  }
  if (elements.analyseLegalContextList) {
    elements.analyseLegalContextList.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      const removeBtn = target.closest("[data-action=remove-analyse-legal-context]");
      if (!(removeBtn instanceof HTMLElement)) return;
      const contextId = String(removeBtn.dataset.contextId || "").trim();
      if (!contextId) return;
      const currentList = Array.isArray(getState().analyse.legalContexts) ? getState().analyse.legalContexts : [];
      const nextList = currentList.filter((entry) => String(entry.id || "") !== contextId);
      setState({
        analyse: {
          legalContexts: nextList,
        },
      });
      renderAnalyse(elements, getState());
    });
  }
  if (elements.analyseLegalContextClearBtn) {
    elements.analyseLegalContextClearBtn.addEventListener("click", () => {
      setState({
        analyse: {
          legalContexts: [],
          useSemanticWithLegalContext: false,
        },
      });
      renderAnalyse(elements, getState());
      setStatus("Retskildekontekst er ryddet for analyse.", "ok");
    });
  }
  if (elements.analyseUseSemanticWithLegalContext) {
    elements.analyseUseSemanticWithLegalContext.addEventListener("change", () => {
      setState({
        analyse: {
          useSemanticWithLegalContext: Boolean(elements.analyseUseSemanticWithLegalContext.checked),
        },
      });
      renderAnalyse(elements, getState());
    });
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
            legalLibraryPanelOpen: false,
            legalLibrarySearchQuery: "",
            legalLibraryActiveDocumentBySubtab: {
              ...(sags.legalLibraryActiveDocumentBySubtab || {}),
              [subtab]: "",
            },
            legalLibraryActiveVersionBySubtab: {
              ...(sags.legalLibraryActiveVersionBySubtab || {}),
              [subtab]: "",
            },
            legalLibraryPreviewSectionBySubtab: {
              ...(sags.legalLibraryPreviewSectionBySubtab || {}),
              [subtab]: "",
            },
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

  if (elements.chatUseVectorSearch) {
    elements.chatUseVectorSearch.addEventListener("change", () => {
      const enabled = Boolean(elements.chatUseVectorSearch.checked);
      setState({
        chat: {
          useVectorSearch: enabled,
        },
      });
      renderChat(elements, getState());
      setStatus(
        enabled
          ? "Chat vector search er aktiveret."
          : "Chat vector search er deaktiveret.",
        "ok",
      );
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
      const activeSubtab = getState().sagsbehandling.activeSubtab || "";
      const activeCategoryBySubtab = getState().sagsbehandling.legalLibraryActiveCategoryBySubtab || {};
      const nextCategoryBySubtab = activeSubtab === "beskatningsret_indkomst"
        ? {
          ...activeCategoryBySubtab,
          [activeSubtab]: "dobbeltbeskatningsoverenskomster",
        }
        : activeCategoryBySubtab;
      setState({
        sagsbehandling: {
          activeFunction: functionLabel,
          legalLibraryPanelOpen:
            activeSubtab === "beskatningsret_indkomst" && functionLabel === "Retskilder",
          factsPanelOpen: false,
          legalLibrarySearchQuery: "",
          legalLibraryActiveCategoryBySubtab: nextCategoryBySubtab,
          legalLibraryActiveDocumentBySubtab: {
            ...(getState().sagsbehandling.legalLibraryActiveDocumentBySubtab || {}),
            [activeSubtab]: "",
          },
          legalLibraryActiveVersionBySubtab: {
            ...(getState().sagsbehandling.legalLibraryActiveVersionBySubtab || {}),
            [activeSubtab]: "",
          },
          legalLibraryPreviewSectionBySubtab: {
            ...(getState().sagsbehandling.legalLibraryPreviewSectionBySubtab || {}),
            [activeSubtab]: "",
          },
        },
      });
      renderSagsbehandling(elements, getState());
      if (activeSubtab === "beskatningsret_indkomst" && functionLabel === "Retskilder") {
        loadLegalSourcesCatalogIfNeeded(true);
      }
    });
  }

  if (elements.sagsFactsToggleBtn) {
    elements.sagsFactsToggleBtn.addEventListener("click", () => {
      const isOpen = Boolean(getState().sagsbehandling.factsPanelOpen);
      const activeSubtab = getState().sagsbehandling.activeSubtab || "skattepligt_ligningsfrist";
      setState({
        sagsbehandling: {
          factsPanelOpen: !isOpen,
          legalLibraryPanelOpen: false,
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

  if (elements.sagsLegalLibraryToggleBtn) {
    elements.sagsLegalLibraryToggleBtn.addEventListener("click", () => {
      const startMs = performance.now();
      const sags = getState().sagsbehandling || {};
      const activeSubtab = sags.activeSubtab || "";
      if (!hasActiveSagsCaseSelected()) {
        showMissingCasePopup();
        return;
      }
      if (activeSubtab !== "beskatningsret_indkomst") {
        setStatus("Retskildebibliotek er kun aktiv i undertab: Beskatningsret til indkomst.", "error");
        return;
      }
      const isOpen = Boolean(sags.legalLibraryPanelOpen);
      setState({
        sagsbehandling: {
          legalLibraryPanelOpen: !isOpen,
          factsPanelOpen: false,
          legalLibrarySearchQuery: "",
          legalLibraryActiveCategoryBySubtab: {
            ...(sags.legalLibraryActiveCategoryBySubtab || {}),
            [activeSubtab]: "dobbeltbeskatningsoverenskomster",
          },
          legalLibraryActiveDocumentBySubtab: {
            ...(sags.legalLibraryActiveDocumentBySubtab || {}),
            [activeSubtab]: "",
          },
          legalLibraryActiveVersionBySubtab: {
            ...(sags.legalLibraryActiveVersionBySubtab || {}),
            [activeSubtab]: "",
          },
          legalLibraryPreviewSectionBySubtab: {
            ...(sags.legalLibraryPreviewSectionBySubtab || {}),
            [activeSubtab]: "",
          },
        },
      });
      renderSagsbehandling(elements, getState());
      if (!isOpen) {
        loadLegalSourcesCatalogIfNeeded(true);
      }
      showLegalLibraryLatency("Toggle panel", startMs);
    });
  }

  if (elements.sagsLegalLibraryCloseBtn) {
    elements.sagsLegalLibraryCloseBtn.addEventListener("click", () => {
      setState({
        sagsbehandling: {
          legalLibraryPanelOpen: false,
        },
      });
      renderSagsbehandling(elements, getState());
    });
  }

  if (elements.sagsLegalLibrarySearch) {
    elements.sagsLegalLibrarySearch.addEventListener("input", () => {
      const startMs = performance.now();
      setState({
        sagsbehandling: {
          legalLibrarySearchQuery: elements.sagsLegalLibrarySearch.value,
        },
      });
      renderSagsbehandling(elements, getState());
      showLegalLibraryLatency("Søgning", startMs);
    });
  }

  if (elements.sagsLegalLibraryCategories) {
    elements.sagsLegalLibraryCategories.addEventListener("click", (event) => {
      const startMs = performance.now();
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      const categoryButton = target.closest("[data-sags-legal-category-toggle-id]");
      if (!(categoryButton instanceof HTMLElement)) {
        return;
      }
      const categoryId = String(categoryButton.dataset.sagsLegalCategoryToggleId || "").trim();
      if (!categoryId) {
        return;
      }
      const activeSubtab = getState().sagsbehandling.activeSubtab || "";
      const activeBySubtab = getState().sagsbehandling.legalLibraryActiveCategoryBySubtab || {};
      const currentlyOpen = String(activeBySubtab[activeSubtab] || "").trim();
      const nextCategory = currentlyOpen === categoryId ? "" : categoryId;
      setState({
        sagsbehandling: {
          legalLibraryActiveCategoryBySubtab: {
            ...activeBySubtab,
            [activeSubtab]: nextCategory,
          },
          legalLibraryActiveDocumentBySubtab: {
            ...(getState().sagsbehandling.legalLibraryActiveDocumentBySubtab || {}),
            [activeSubtab]: "",
          },
          legalLibraryActiveVersionBySubtab: {
            ...(getState().sagsbehandling.legalLibraryActiveVersionBySubtab || {}),
            [activeSubtab]: "",
          },
          legalLibraryPreviewSectionBySubtab: {
            ...(getState().sagsbehandling.legalLibraryPreviewSectionBySubtab || {}),
            [activeSubtab]: "",
          },
        },
      });
      renderSagsbehandling(elements, getState());
      showLegalLibraryLatency("Kategori", startMs);
    });
  }

  if (elements.sagsLegalLibrarySources) {
    elements.sagsLegalLibrarySources.addEventListener("click", (event) => {
      const startMs = performance.now();
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      const activeSubtab = getState().sagsbehandling.activeSubtab || "";
      const documentButton = target.closest("[data-sags-legal-document-id]");
      if (documentButton instanceof HTMLElement) {
        const documentId = String(documentButton.dataset.sagsLegalDocumentId || "").trim();
        if (!documentId) {
          return;
        }
        setState({
          sagsbehandling: {
            legalLibraryActiveDocumentBySubtab: {
              ...(getState().sagsbehandling.legalLibraryActiveDocumentBySubtab || {}),
              [activeSubtab]: documentId,
            },
            legalLibraryActiveVersionBySubtab: {
              ...(getState().sagsbehandling.legalLibraryActiveVersionBySubtab || {}),
              [activeSubtab]: "",
            },
            legalLibraryPreviewSectionBySubtab: {
              ...(getState().sagsbehandling.legalLibraryPreviewSectionBySubtab || {}),
              [activeSubtab]: "",
            },
          },
        });
        renderSagsbehandling(elements, getState());
        showLegalLibraryLatency("Dokument", startMs);
        return;
      }
      const versionButton = target.closest("[data-sags-legal-version-id]");
      if (versionButton instanceof HTMLElement) {
        const versionId = String(versionButton.dataset.sagsLegalVersionId || "").trim();
        if (!versionId) {
          return;
        }
        setState({
          sagsbehandling: {
            legalLibraryActiveVersionBySubtab: {
              ...(getState().sagsbehandling.legalLibraryActiveVersionBySubtab || {}),
              [activeSubtab]: versionId,
            },
            legalLibraryPreviewSectionBySubtab: {
              ...(getState().sagsbehandling.legalLibraryPreviewSectionBySubtab || {}),
              [activeSubtab]: "",
            },
          },
        });
        renderSagsbehandling(elements, getState());
        showLegalLibraryLatency("Version", startMs);
        return;
      }
      const addSectionButton = target.closest("[data-sags-legal-add-section-id]");
      if (addSectionButton instanceof HTMLElement) {
        if (!hasActiveSagsCaseSelected()) {
          showMissingCasePopup();
          return;
        }
        const sectionId = String(addSectionButton.dataset.sagsLegalAddSectionId || "").trim();
        const sourceId = String(addSectionButton.dataset.sagsLegalAddSourceId || "").trim();
        const contextTitle = String(addSectionButton.dataset.sagsLegalAddTitle || "").trim();
        const previewText = String(addSectionButton.dataset.sagsLegalAddText || "").trim();
        if (!sectionId || !sourceId || !contextTitle || !previewText) {
          return;
        }
        const logId = `legal:${sourceId}:${sectionId}`;
        const contextBySubtab = getState().sagsbehandling.contextBySubtab || {};
        const currentListRaw = contextBySubtab[activeSubtab];
        const currentList = Array.isArray(currentListRaw)
          ? currentListRaw
          : currentListRaw
            ? [currentListRaw]
            : [];
        const nextList = currentList.some((entry) => String(entry.logId || "") === logId)
          ? currentList
          : [
            ...currentList,
            {
              logId,
              sourceType: "legal",
              title: contextTitle,
              createdAt: "Retskilde",
              previewText,
              approved: true,
            },
          ];
        setState({
          sagsbehandling: {
            contextBySubtab: {
              ...contextBySubtab,
              [activeSubtab]: nextList,
            },
          },
        });
        renderSagsbehandling(elements, getState());
        setStatus("Paragraf tilføjet som kontekst for undertab.", "ok");
        showLegalLibraryLatency("Tilføj paragraf", startMs);
        saveCurrentSagsCaseSnapshot();
        return;
      }
      const sourceButton = target.closest("[data-sags-legal-source-id]");
      if (!(sourceButton instanceof HTMLElement)) {
        return;
      }
      const sourceId = String(sourceButton.dataset.sagsLegalSourceId || "").trim();
      const sourceRefId = String(sourceButton.dataset.sagsLegalSourceRef || "").trim();
      if (!sourceId) {
        return;
      }
      const previewBySubtab = getState().sagsbehandling.legalLibraryPreviewSectionBySubtab || {};
      const previewPageBySourceId = getState().sagsbehandling.legalLibraryPreviewPageBySourceId || {};
      setState({
        sagsbehandling: {
          legalLibraryPreviewSectionBySubtab: {
            ...previewBySubtab,
            [activeSubtab]: sourceId,
          },
          legalLibraryPreviewPageBySourceId: sourceRefId
            ? {
              ...previewPageBySourceId,
              [sourceRefId]: 1,
            }
            : previewPageBySourceId,
        },
      });
      renderSagsbehandling(elements, getState());
      showLegalLibraryLatency("Paragraf visning", startMs);
      if (sourceRefId) {
        loadLegalSourceSectionTextIfNeeded(sourceRefId, 1);
      }
    });
  }

  if (elements.sagsLegalOpenSourceBtn) {
    elements.sagsLegalOpenSourceBtn.addEventListener("click", () => {
      const sourceId = String(elements.sagsLegalOpenSourceBtn.dataset.sagsLegalSourceId || "").trim();
      if (!sourceId) {
        setStatus("Ingen kilde valgt endnu.", "error");
        return;
      }
      window.open(`/api/legal-sources/file/${encodeURIComponent(sourceId)}`, "_blank", "noopener,noreferrer");
    });
  }

  if (elements.sagsLegalAddSelectionBtn) {
    elements.sagsLegalAddSelectionBtn.addEventListener("click", () => {
      if (!hasActiveSagsCaseSelected()) {
        showMissingCasePopup();
        return;
      }
      const previewEl = elements.sagsLegalPreviewText;
      if (!(previewEl instanceof HTMLElement)) {
        return;
      }
      const selection = window.getSelection();
      if (!selection || selection.rangeCount === 0) {
        setStatus("Markér først den tekst, du vil tilføje.", "error");
        return;
      }
      const selectedText = String(selection.toString() || "").trim();
      if (!selectedText || selectedText.length < 10) {
        setStatus("Markeringen er for kort. Vælg et større tekstudsnit.", "error");
        return;
      }
      const range = selection.getRangeAt(0);
      const containerNode = range.commonAncestorContainer;
      const selectionNode = containerNode.nodeType === Node.TEXT_NODE
        ? containerNode.parentNode
        : containerNode;
      if (!(selectionNode instanceof Node) || !previewEl.contains(selectionNode)) {
        setStatus("Markeringen skal være inde i visningsboksen.", "error");
        return;
      }
      const sourceId = String(elements.sagsLegalAddSelectionBtn.dataset.sagsLegalSourceId || "").trim();
      const sectionId = String(elements.sagsLegalAddSelectionBtn.dataset.sagsLegalSectionId || "").trim();
      const contextTitleRaw = String(elements.sagsLegalAddSelectionBtn.dataset.sagsLegalContextTitle || "").trim();
      if (!sourceId || !sectionId || !contextTitleRaw) {
        setStatus("Vælg en paragraf først.", "error");
        return;
      }
      const activeSubtab = getState().sagsbehandling.activeSubtab || "";
      const contextBySubtab = getState().sagsbehandling.contextBySubtab || {};
      const currentListRaw = contextBySubtab[activeSubtab];
      const currentList = Array.isArray(currentListRaw)
        ? currentListRaw
        : currentListRaw
          ? [currentListRaw]
          : [];
      const trimmedText = selectedText.length > 6000 ? `${selectedText.slice(0, 6000)}...` : selectedText;
      const logId = `legal_selection:${sourceId}:${sectionId}:${Date.now()}`;
      const nextList = [
        ...currentList,
        {
          logId,
          sourceType: "legal_selection",
          title: `${contextTitleRaw} (markeret tekst)`,
          createdAt: "Retskilde",
          previewText: trimmedText,
          approved: true,
        },
      ];
      setState({
        sagsbehandling: {
          contextBySubtab: {
            ...contextBySubtab,
            [activeSubtab]: nextList,
          },
        },
      });
      renderSagsbehandling(elements, getState());
      setStatus("Markeret tekst tilføjet som kontekst for undertab.", "ok");
      saveCurrentSagsCaseSnapshot();
    });
  }

  if (elements.sagsLegalPrevPageBtn) {
    elements.sagsLegalPrevPageBtn.addEventListener("click", () => {
      const sourceId = String(elements.sagsLegalPrevPageBtn.dataset.sagsLegalSourceId || "").trim();
      if (!sourceId) return;
      const currentPage = Math.max(1, Number(elements.sagsLegalPrevPageBtn.dataset.sagsLegalCurrentPage || "1") || 1);
      const nextPage = Math.max(1, currentPage - 1);
      if (nextPage === currentPage) return;
      loadLegalSourceSectionTextIfNeeded(sourceId, nextPage);
    });
  }

  if (elements.sagsLegalNextPageBtn) {
    elements.sagsLegalNextPageBtn.addEventListener("click", () => {
      const sourceId = String(elements.sagsLegalNextPageBtn.dataset.sagsLegalSourceId || "").trim();
      if (!sourceId) return;
      const currentPage = Math.max(1, Number(elements.sagsLegalNextPageBtn.dataset.sagsLegalCurrentPage || "1") || 1);
      const totalPages = Math.max(1, Number(elements.sagsLegalNextPageBtn.dataset.sagsLegalTotalPages || "1") || 1);
      const nextPage = Math.min(totalPages, currentPage + 1);
      if (nextPage === currentPage) return;
      loadLegalSourceSectionTextIfNeeded(sourceId, nextPage);
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
          legalLibraryPanelOpen: false,
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
        incomeDboArticle: "",
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
      if (String(target.dataset.sagsIncomeDboArticle || "").trim() === "true") {
        updateSagsFactsForActiveSubtab({
          incomeDboArticle: target.value,
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
  applyTabAvailability();
  setState({
    ui: {
      activeTab: normalizeTabId(getActiveTab("chat")),
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
