(function () {
  "use strict";

  const API_BASE_URL = "/api";
  const SESSION_KEY = "jaila_auth_user";
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
    question: document.getElementById("question"),
    analyzeBtn: document.getElementById("analyzeBtn"),
    answer: document.getElementById("answer"),
    citations: document.getElementById("citations"),
    pdfLogLink: document.getElementById("pdfLogLink"),
    tabButtons: Array.from(document.querySelectorAll(".tab-button")),
    tabPaneAnalyse: document.getElementById("tabPaneAnalyse"),
    tabPaneSagsbehandling: document.getElementById("tabPaneSagsbehandling"),
    tabPaneChat: document.getElementById("tabPaneChat"),
    chatConversation: document.getElementById("chatConversation"),
    chatInput: document.getElementById("chatInput"),
    chatSendBtn: document.getElementById("chatSendBtn"),
    chatResetBtn: document.getElementById("chatResetBtn"),
  };

  const state = {
    ui: {
      activeTab: "analyse",
      loading: false,
    },
    analyse: {
      previousResponseId: null,
    },
    chat: {
      previousResponseId: null,
    },
  };

  function normalizeDanishDisplayText(value) {
    const text = String(value || "");
    if (!text) {
      return text;
    }

    // Only attempt repair when common mojibake markers are present.
    if (!/[ÃÂâ]/.test(text)) {
      return text;
    }

    try {
      const bytes = new Uint8Array(Array.from(text, function (char) {
        return char.charCodeAt(0) & 0xff;
      }));
      const decoded = new TextDecoder("utf-8", { fatal: false }).decode(bytes);

      const mojibakeScore = function (input) {
        const matches = input.match(/[ÃÂâ]/g);
        return matches ? matches.length : 0;
      };

      return mojibakeScore(decoded) < mojibakeScore(text) ? decoded : text;
    } catch (_err) {
      return text;
    }
  }

  function setStatus(text, mode) {
    if (!elements.status) {
      return;
    }

    elements.status.textContent = text;
    elements.status.classList.remove("ok", "error");

    if (mode === "ok") {
      elements.status.classList.add("ok");
    } else if (mode === "error") {
      elements.status.classList.add("error");
    }
  }

  function setLoading(isLoading) {
    state.ui.loading = isLoading;
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
  }

  function renderCitations(citations) {
    if (!elements.citations) {
      return;
    }
    elements.citations.innerHTML = "";
    if (!citations || citations.length === 0) {
      const li = document.createElement("li");
      li.textContent = "Ingen citations fundet.";
      elements.citations.appendChild(li);
      return;
    }

    citations.forEach((citation) => {
      const li = document.createElement("li");
      const filename = normalizeDanishDisplayText(citation.filename || "(ukendt filnavn)");
      const fileId = citation.file_id || "(ukendt file_id)";
      li.textContent = filename + " (file_id: " + fileId + ")";
      elements.citations.appendChild(li);
    });
  }

  function renderLogLink(url, label) {
    if (!elements.pdfLogLink) {
      return;
    }
    if (!url) {
      elements.pdfLogLink.textContent = "Ingen PDF-log endnu.";
      elements.pdfLogLink.removeAttribute("href");
      return;
    }
    elements.pdfLogLink.textContent = label || "Åbn PDF-log";
    elements.pdfLogLink.href = url;
  }

  function appendChatMessage(role, text) {
    if (!elements.chatConversation) {
      return;
    }
    const conversationEl = elements.chatConversation;
    const isEmptyState = conversationEl.children.length === 1
      && conversationEl.firstElementChild
      && conversationEl.firstElementChild.classList.contains("msg-system");

    if (isEmptyState) {
      conversationEl.innerHTML = "";
    }

    const el = document.createElement("div");
    el.classList.add("msg");
    if (role === "user") {
      el.classList.add("msg-user");
      el.textContent = "Du: " + (text || "");
    } else if (role === "assistant") {
      el.classList.add("msg-assistant");
      el.textContent = "JAILA: " + (text || "");
    } else {
      el.classList.add("msg-system");
      el.textContent = text || "";
    }
    conversationEl.appendChild(el);
    conversationEl.scrollTop = conversationEl.scrollHeight;
  }

  function resetAnalyse() {
    state.analyse.previousResponseId = null;
    if (elements.question) {
      elements.question.value = "";
    }
    if (elements.answer) {
      elements.answer.textContent = "Intet svar endnu.";
    }
    renderCitations([]);
    renderLogLink("", "");
    setStatus("Analyse nulstillet.", "ok");
  }

  function resetChat() {
    state.chat.previousResponseId = null;
    if (elements.chatInput) {
      elements.chatInput.value = "";
    }
    if (elements.chatConversation) {
      elements.chatConversation.innerHTML =
        '<div class="msg msg-system">Start en rå chat uden vector store.</div>';
    }
    setStatus("Chat nulstillet.", "ok");
  }

  function switchTab(tabId) {
    state.ui.activeTab = tabId;
    const paneMap = {
      analyse: elements.tabPaneAnalyse,
      sagsbehandling: elements.tabPaneSagsbehandling,
      chat: elements.tabPaneChat,
    };

    Object.keys(paneMap).forEach(function (key) {
      const pane = paneMap[key];
      if (!pane) {
        return;
      }
      pane.classList.toggle("hidden", key !== tabId);
    });

    elements.tabButtons.forEach(function (btn) {
      const isActive = btn.dataset.tab === tabId;
      btn.classList.toggle("tab-button-active", isActive);
    });
  }

  function showApp(user) {
    if (elements.loginSection) {
      elements.loginSection.classList.add("hidden");
    }
    if (elements.appSection) {
      elements.appSection.classList.remove("hidden");
    }
    if (elements.sessionLabel) {
      elements.sessionLabel.textContent = "Logget ind som: " + user;
    }
    switchTab(state.ui.activeTab);
    setStatus("Klar til analyse.", "ok");
  }

  function showLogin(message, mode) {
    if (elements.loginSection) {
      elements.loginSection.classList.remove("hidden");
    }
    if (elements.appSection) {
      elements.appSection.classList.add("hidden");
    }
    setStatus(message || "Log ind for at bruge systemet.", mode || "ok");
  }

  function tryLogin() {
    if (!elements.username || !elements.password) {
      return;
    }

    const username = elements.username.value.trim().toLowerCase();
    const password = elements.password.value;
    const expectedPassword = VALID_USERS[username];

    if (!expectedPassword || password !== expectedPassword) {
      showLogin("Forkert brugernavn eller adgangskode.", "error");
      return;
    }

    localStorage.setItem(SESSION_KEY, username);
    elements.password.value = "";
    showApp(username);
  }

  function logout() {
    localStorage.removeItem(SESSION_KEY);
    resetAnalyse();
    resetChat();
    if (elements.password) {
      elements.password.value = "";
    }
    showLogin("Du er logget ud.", "ok");
  }

  async function analyze() {
    if (!elements.answer) {
      return;
    }
    const question = (elements.question ? elements.question.value : "").trim();
    if (!question) {
      setStatus("Skriv et spørgsmål først.", "error");
      return;
    }

    setLoading(true);
    setStatus("Sender forespørgsel til backend...", "ok");

    try {
      const response = await fetch(API_BASE_URL + "/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: question,
        }),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Ukendt API-fejl");
      }

      state.analyse.previousResponseId = data.response_id || null;
      elements.answer.textContent = data.answer || "Intet svar returneret.";
      renderCitations(data.citations || []);
      renderLogLink(data.log_pdf_url || "", data.log_pdf_filename || "Aabn PDF-log");
      setStatus("Analyse færdig. Model: " + (data.used_model || "ukendt"), "ok");
    } catch (err) {
      elements.answer.textContent = "Kunne ikke hente svar.";
      renderCitations([]);
      renderLogLink("", "");
      setStatus("Fejl: " + (err && err.message ? err.message : "Ukendt fejl"), "error");
    } finally {
      setLoading(false);
    }
  }

  async function sendChatMessage() {
    const message = (elements.chatInput ? elements.chatInput.value : "").trim();
    if (!message) {
      setStatus("Skriv en chatbesked først.", "error");
      return;
    }

    appendChatMessage("user", message);
    if (elements.chatInput) {
      elements.chatInput.value = "";
    }

    setLoading(true);
    setStatus("Sender chatbesked...", "ok");

    try {
      const response = await fetch(API_BASE_URL + "/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: message,
          previous_response_id: state.chat.previousResponseId,
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Ukendt API-fejl");
      }

      state.chat.previousResponseId = data.response_id || null;
      appendChatMessage("assistant", data.answer || "Intet svar returneret.");
      setStatus("Chat svar modtaget. Model: " + (data.used_model || "ukendt"), "ok");
    } catch (err) {
      appendChatMessage("system", "Fejl: " + (err && err.message ? err.message : "Ukendt fejl"));
      setStatus("Fejl: " + (err && err.message ? err.message : "Ukendt fejl"), "error");
    } finally {
      setLoading(false);
    }
  }

  if (elements.tabButtons.length) {
    elements.tabButtons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        switchTab(btn.dataset.tab || "analyse");
      });
    });
  }

  if (elements.analyzeBtn) {
    elements.analyzeBtn.addEventListener("click", analyze);
  }
  if (elements.chatSendBtn) {
    elements.chatSendBtn.addEventListener("click", sendChatMessage);
  }
  if (elements.chatResetBtn) {
    elements.chatResetBtn.addEventListener("click", resetChat);
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
  if (elements.password) {
    elements.password.addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        tryLogin();
      }
    });
  }
  if (elements.chatInput) {
    elements.chatInput.addEventListener("keydown", function (event) {
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
        sendChatMessage();
      }
    });
  }

  const activeUser = localStorage.getItem(SESSION_KEY);
  if (activeUser && Object.prototype.hasOwnProperty.call(VALID_USERS, activeUser)) {
    showApp(activeUser);
  } else {
    showLogin("Log ind for at bruge systemet.", "ok");
  }
})();
