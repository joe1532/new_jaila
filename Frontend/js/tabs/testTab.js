import { renderContextList } from "./contextList.js";

function formatTestChatLogEntryAsText(entry) {
  if (!entry) return "";
  const lines = [];
  lines.push("Test-chat-log");
  lines.push(`Oprettet: ${entry.created_at || ""}`);
  lines.push(`Opdateret: ${entry.updated_at || entry.created_at || ""}`);
  lines.push(`Model brugt: ${entry.used_model || ""}`);
  lines.push("");
  lines.push("─── Samtale ───");
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

// Rækkefølgen bestemmer, hvordan de manglende henvisninger listes. Nøglerne skal matche
// REFERENCE_KINDS i backendens openai_service.
const REFERENCE_KIND_LABELS = [
  ["paragraffer", "Paragraffer"],
  ["love", "Love"],
  ["afgørelser", "Afgørelser"],
  ["artikler", "Artikler"],
];

function formatScore(value) {
  return typeof value === "number" ? value.toFixed(2) : "–";
}

function renderRetrievalPanel(container, diagnostics) {
  if (!container) return;

  container.innerHTML = "";
  if (!diagnostics) {
    container.classList.add("hidden");
    return;
  }
  container.classList.remove("hidden");

  const heading = document.createElement("h3");
  heading.className = "retrieval-panel-heading";
  heading.textContent = "Søgning";
  container.appendChild(heading);

  const searches = Array.isArray(diagnostics.searches) ? diagnostics.searches : [];
  const queries = searches.flatMap((search) => (Array.isArray(search.queries) ? search.queries : []));

  const summary = document.createElement("p");
  summary.className = "retrieval-panel-summary";
  summary.textContent =
    `${searches.length} søgning(er), ${diagnostics.num_results || 0} tekststykker hentet · ` +
    `score ${formatScore(diagnostics.score_min)}–${formatScore(diagnostics.score_max)}`;
  container.appendChild(summary);

  if (queries.length) {
    const list = document.createElement("ul");
    list.className = "retrieval-panel-queries";
    queries.forEach((query) => {
      const li = document.createElement("li");
      li.textContent = query;
      list.appendChild(li);
    });
    container.appendChild(list);
  } else {
    const none = document.createElement("p");
    none.className = "retrieval-panel-note";
    // Sker blandt andet, når modellen svarer uden at søge. Det er i sig selv et fund.
    none.textContent = "Modellen sendte ingen søgestrenge.";
    container.appendChild(none);
  }

  const missing = diagnostics.missing_references || {};
  const missingParts = REFERENCE_KIND_LABELS
    .filter(([key]) => Array.isArray(missing[key]) && missing[key].length)
    .map(([key, label]) => `${label}: ${missing[key].join(", ")}`);

  const verdict = document.createElement("p");
  if (missingParts.length) {
    verdict.className = "retrieval-panel-missing";
    verdict.textContent = "Nævnt i spørgsmålet, men ikke fundet i materialet — " + missingParts.join(" · ");
  } else {
    verdict.className = "retrieval-panel-note";
    // Formuleringen er bevidst forbeholden: kontrollen ser kun efter de henvisninger,
    // spørgsmålet selv nævner, og et fund betyder blot, at henvisningen optræder et sted
    // i det hentede materiale.
    verdict.textContent = "Ingen af de henvisninger, spørgsmålet nævner, mangler i materialet.";
  }
  container.appendChild(verdict);
}

export function renderTestChat(elements, state) {
  renderRetrievalPanel(elements.testChatRetrievalPanel, state.testChat.retrievalDiagnostics);

  if (elements.testChatUseVectorSearch) {
    elements.testChatUseVectorSearch.checked = state.testChat.useVectorSearch !== false;
  }

  renderContextList(elements.testChatContextList, state.testChat.contextFiles || []);

  if (elements.testChatLogContent) {
    const savedLogs = state.testChat.savedLogs || [];
    const selectedLogContent = state.testChat.selectedLogContent;
    if (selectedLogContent) {
      elements.testChatLogContent.innerHTML = "";
      const backBtn = document.createElement("button");
      backBtn.type = "button";
      backBtn.className = "button-secondary analyse-log-back";
      backBtn.textContent = "← Tilbage til liste";
      backBtn.dataset.action = "test-chat-log-back";
      elements.testChatLogContent.appendChild(backBtn);
      const loadBtn = document.createElement("button");
      loadBtn.type = "button";
      loadBtn.className = "button-secondary analyse-log-back";
      loadBtn.textContent = "Indlæs test-chat";
      loadBtn.dataset.action = "test-chat-log-load";
      loadBtn.dataset.entryId = selectedLogContent.id || "";
      elements.testChatLogContent.appendChild(loadBtn);
      const deleteBtn = document.createElement("button");
      deleteBtn.type = "button";
      deleteBtn.className = "button-secondary analyse-log-back";
      deleteBtn.textContent = "Slet gemt test-chat";
      deleteBtn.dataset.action = "test-chat-log-delete";
      deleteBtn.dataset.entryId = selectedLogContent.id || "";
      elements.testChatLogContent.appendChild(deleteBtn);
      const pre = document.createElement("pre");
      pre.className = "analyse-log-full";
      pre.textContent = formatTestChatLogEntryAsText(selectedLogContent);
      elements.testChatLogContent.appendChild(pre);
    } else if (savedLogs.length) {
      elements.testChatLogContent.innerHTML = "";
      const ul = document.createElement("ul");
      ul.className = "analyse-log-list";
      savedLogs.forEach((entry) => {
        const li = document.createElement("li");
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "analyse-log-entry";
        btn.dataset.entryId = entry.id || "";
        const when = entry.updated_at || entry.created_at || "";
        btn.textContent = `${entry.title || "Test-chat uden titel"} (${when})`;
        li.appendChild(btn);
        ul.appendChild(li);
      });
      elements.testChatLogContent.appendChild(ul);
    } else {
      elements.testChatLogContent.innerHTML = "";
      const p = document.createElement("p");
      p.className = "analyse-log-empty";
      p.textContent = "Ingen gemte test-chats endnu.";
      elements.testChatLogContent.appendChild(p);
    }
  }

  if (!elements.testChatConversation) {
    return;
  }
  const conversationEl = elements.testChatConversation;
  const messages = state.testChat.messages || [];
  conversationEl.innerHTML = "";
  if (messages.length) {
    messages.forEach((msg) => {
      const el = document.createElement("div");
      el.classList.add("msg");
      if (msg.role === "user") {
        el.classList.add("msg-user");
        el.textContent = "Du: " + (msg.text || "");
      } else if (msg.role === "assistant") {
        el.classList.add("msg-assistant");
        el.textContent = "JAILA:\n\n" + (msg.text || "");
      } else {
        el.classList.add("msg-system");
        el.textContent = msg.text || "";
      }
      conversationEl.appendChild(el);
    });
  }

  const threshold = 80;
  const atBottom =
    conversationEl.scrollHeight - conversationEl.scrollTop - conversationEl.clientHeight <= threshold;
  if (atBottom) {
    conversationEl.scrollTop = conversationEl.scrollHeight;
  }

  if (elements.testChatInput && elements.testChatInput.value !== state.testChat.inputText) {
    elements.testChatInput.value = state.testChat.inputText || "";
  }
}

export function getInitialTestChatState() {
  return {
    messages: [],
    inputText: "",
    usedModel: null,
    previousResponseId: null,
    contextFiles: [],
    useVectorSearch: true,
    usedVectorStoreIds: [],
    vectorSearchEnabledLastResponse: false,
    citations: [],
    retrievalResults: [],
    usedRetrievalResults: [],
    // null betyder "ikke målt" — enten er der ikke svaret endnu, eller også var vector
    // search slået fra. Det er ikke det samme som "intet fundet".
    retrievalDiagnostics: null,
    savedLogs: [],
    selectedLogId: null,
    selectedLogContent: null,
  };
}
