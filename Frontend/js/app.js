(function () {
  "use strict";

  const API_BASE_URL = "/api";
  const SESSION_KEY = "jaila_auth_user";
  const VALID_USERS = {
    jonas: "pepsimax",
    allan: "pepsimax",
  };

  const loginSectionEl = document.getElementById("loginSection");
  const appSectionEl = document.getElementById("appSection");
  const usernameEl = document.getElementById("username");
  const passwordEl = document.getElementById("password");
  const loginBtnEl = document.getElementById("loginBtn");
  const logoutBtnEl = document.getElementById("logoutBtn");
  const sessionLabelEl = document.getElementById("sessionLabel");
  const statusEl = document.getElementById("status");
  const questionEl = document.getElementById("question");
  const analyzeBtn = document.getElementById("analyzeBtn");
  const answerEl = document.getElementById("answer");
  const citationsEl = document.getElementById("citations");
  const pdfLogLinkEl = document.getElementById("pdfLogLink");

  function setStatus(text, mode) {
    if (!statusEl) {
      return;
    }

    statusEl.textContent = text;
    statusEl.classList.remove("ok", "error");

    if (mode === "ok") {
      statusEl.classList.add("ok");
    } else if (mode === "error") {
      statusEl.classList.add("error");
    }
  }

  function setLoading(isLoading) {
    if (!analyzeBtn) {
      return;
    }
    analyzeBtn.disabled = isLoading;
    analyzeBtn.textContent = isLoading ? "Arbejder..." : "Kør analyse";
  }

  function renderCitations(citations) {
    if (!citationsEl) {
      return;
    }
    citationsEl.innerHTML = "";
    if (!citations || citations.length === 0) {
      const li = document.createElement("li");
      li.textContent = "Ingen citations fundet.";
      citationsEl.appendChild(li);
      return;
    }

    citations.forEach((citation) => {
      const li = document.createElement("li");
      const filename = citation.filename || "(ukendt filnavn)";
      const fileId = citation.file_id || "(ukendt file_id)";
      li.textContent = filename + " (file_id: " + fileId + ")";
      citationsEl.appendChild(li);
    });
  }

  function renderLogLink(url, label) {
    if (!pdfLogLinkEl) {
      return;
    }
    if (!url) {
      pdfLogLinkEl.textContent = "Ingen PDF-log endnu.";
      pdfLogLinkEl.removeAttribute("href");
      return;
    }
    pdfLogLinkEl.textContent = label || "Åbn PDF-log";
    pdfLogLinkEl.href = url;
  }

  function showApp(user) {
    if (loginSectionEl) {
      loginSectionEl.classList.add("hidden");
    }
    if (appSectionEl) {
      appSectionEl.classList.remove("hidden");
    }
    if (sessionLabelEl) {
      sessionLabelEl.textContent = "Logget ind som: " + user;
    }
    setStatus("Klar til analyse.", "ok");
  }

  function showLogin(message, mode) {
    if (loginSectionEl) {
      loginSectionEl.classList.remove("hidden");
    }
    if (appSectionEl) {
      appSectionEl.classList.add("hidden");
    }
    setStatus(message || "Log ind for at bruge systemet.", mode || "ok");
  }

  function tryLogin() {
    if (!usernameEl || !passwordEl) {
      return;
    }

    const username = usernameEl.value.trim().toLowerCase();
    const password = passwordEl.value;
    const expectedPassword = VALID_USERS[username];

    if (!expectedPassword || password !== expectedPassword) {
      showLogin("Forkert brugernavn eller adgangskode.", "error");
      return;
    }

    localStorage.setItem(SESSION_KEY, username);
    passwordEl.value = "";
    showApp(username);
  }

  function logout() {
    localStorage.removeItem(SESSION_KEY);
    if (passwordEl) {
      passwordEl.value = "";
    }
    showLogin("Du er logget ud.", "ok");
  }

  async function analyze() {
    if (!questionEl || !answerEl) {
      return;
    }
    const question = questionEl.value.trim();
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
        body: JSON.stringify({ question: question }),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Ukendt API-fejl");
      }

      answerEl.textContent = data.answer || "Intet svar returneret.";
      renderCitations(data.citations || []);
      renderLogLink(data.log_pdf_url || "", data.log_pdf_filename || "Aabn PDF-log");
      setStatus("Analyse færdig. Model: " + (data.used_model || "ukendt"), "ok");
    } catch (err) {
      answerEl.textContent = "Kunne ikke hente svar.";
      renderCitations([]);
      renderLogLink("", "");
      setStatus("Fejl: " + (err && err.message ? err.message : "Ukendt fejl"), "error");
    } finally {
      setLoading(false);
    }
  }

  if (analyzeBtn) {
    analyzeBtn.addEventListener("click", analyze);
  }

  if (loginBtnEl) {
    loginBtnEl.addEventListener("click", tryLogin);
  }
  if (logoutBtnEl) {
    logoutBtnEl.addEventListener("click", logout);
  }
  if (passwordEl) {
    passwordEl.addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        tryLogin();
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
