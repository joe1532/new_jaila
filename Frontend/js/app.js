import { analyzeQuestion } from "./api/analyzeApi.js";
import { exportChatPdf, sendChat } from "./api/chatApi.js";
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

const elements = {
  loginSection: document.getElementById("loginSection"),
  appSection: document.getElementById("appSection"),
  username: document.getElementById("username"),
  password: document.getElementById("password"),
  loginBtn: document.getElementById("loginBtn"),
  logoutBtn: document.getElementById("logoutBtn"),
  resetBtn: document.getElementById("resetBtn"),
  sessionLabel: document.getElementById("sessionLabel"),
  status: document.getElementById("status"),
  analyseConversation: document.getElementById("analyseConversation"),
  question: document.getElementById("question"),
  analyzeBtn: document.getElementById("analyzeBtn"),
  pdfLogLink: document.getElementById("pdfLogLink"),
  tabButtons: Array.from(document.querySelectorAll(".tab-button")),
  tabPaneAnalyse: document.getElementById("tabPaneAnalyse"),
  tabPaneSagsbehandling: document.getElementById("tabPaneSagsbehandling"),
  tabPaneChat: document.getElementById("tabPaneChat"),
  sagsbehandlingTitle: document.getElementById("sagsbehandlingTitle"),
  sagsbehandlingConversation: document.getElementById("sagsbehandlingConversation"),
  sagsbehandlingInput: document.getElementById("sagsbehandlingInput"),
  sagsbehandlingSendBtn: document.getElementById("sagsbehandlingSendBtn"),
  sagsFunctionList: document.getElementById("sagsFunctionList"),
  sagsSubtabButtons: Array.from(document.querySelectorAll(".sags-subtab-button")),
  chatConversation: document.getElementById("chatConversation"),
  chatInput: document.getElementById("chatInput"),
  chatSendBtn: document.getElementById("chatSendBtn"),
  chatResetBtn: document.getElementById("chatResetBtn"),
  chatSavePdfBtn: document.getElementById("chatSavePdfBtn"),
  chatContextFile: document.getElementById("chatContextFile"),
  chatContextUploadBtn: document.getElementById("chatContextUploadBtn"),
  chatContextList: document.getElementById("chatContextList"),
};

function renderStatus() {
  if (!elements.status) {
    return;
  }
  const state = getState();
  elements.status.textContent = state.ui.statusMessage;
  elements.status.classList.remove("ok", "error");
  if (state.ui.statusMode === "ok") {
    elements.status.classList.add("ok");
  } else if (state.ui.statusMode === "error") {
    elements.status.classList.add("error");
  }
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
  if (elements.chatResetBtn) {
    elements.chatResetBtn.disabled = isLoading;
  }
  if (elements.chatSavePdfBtn) {
    elements.chatSavePdfBtn.disabled = isLoading;
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
  renderStatus();
  setStatus("Klar til analyse.", "ok");
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
  setState({ analyse: getInitialAnalyseState() });
  renderAnalyse(elements, getState());
  setStatus("Analyse nulstillet.", "ok");
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

function addAnalyseMessage(role, text) {
  const currentMessages = getState().analyse.messages || [];
  setState({
    analyse: {
      messages: currentMessages.concat([{ role: role, text: text || "" }]),
    },
  });
  renderAnalyse(elements, getState());
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

  try {
    const previousResponseId = getState().analyse.previousResponseId;
    const data = await analyzeQuestion(question, previousResponseId);
    setState({
      analyse: {
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
  } catch (err) {
    const errorText = err && err.message ? err.message : "Ukendt fejl";
    setState({
      analyse: {
        answer: "Kunne ikke hente svar: " + errorText,
        citations: [],
        logPdfUrl: "",
        logPdfLabel: "",
      },
    });
    addAnalyseMessage("system", "Fejl: " + errorText);
    renderAnalyse(elements, getState());
    setStatus("Fejl: " + errorText, "error");
  } finally {
    setLoading(false);
  }
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

  try {
    const previousResponseId = getState().chat.previousResponseId;
    const sessionId = getOrCreateChatSessionId();
    const data = await sendChat(message, previousResponseId, sessionId);
    setState({
      chat: {
        previousResponseId: data.response_id || null,
        usedModel: data.used_model || null,
      },
    });
    addChatMessage("assistant", data.answer || "Intet svar returneret.");
    setStatus("Chat svar modtaget. Model: " + (data.used_model || "ukendt"), "ok");
  } catch (err) {
    addChatMessage("system", "Fejl: " + (err && err.message ? err.message : "Ukendt fejl"));
    setStatus("Fejl: " + (err && err.message ? err.message : "Ukendt fejl"), "error");
  } finally {
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
  if (elements.chatSendBtn) {
    elements.chatSendBtn.addEventListener("click", runChat);
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
          },
        });
        renderSagsbehandling(elements, getState());
        setStatus("Sagsbehandling undertab valgt (dummy): " + btn.textContent, "ok");
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

  if (elements.sagsbehandlingInput) {
    elements.sagsbehandlingInput.addEventListener("input", () => {
      setState({
        sagsbehandling: {
          inputText: elements.sagsbehandlingInput.value,
        },
      });
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
      setStatus("Sagsbehandling funktion valgt (dummy): " + functionLabel, "ok");
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
