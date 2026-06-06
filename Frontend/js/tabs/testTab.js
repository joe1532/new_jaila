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

export function renderTestChat(elements, state) {
  if (elements.testChatUseVectorSearch) {
    elements.testChatUseVectorSearch.checked = state.testChat.useVectorSearch !== false;
  }

  if (elements.testChatContextList) {
    elements.testChatContextList.innerHTML = "";
    const files = state.testChat.contextFiles || [];
    if (!files.length) {
      const li = document.createElement("li");
      li.className = "context-file-item-empty";
      li.textContent = "Ingen filer uploadet endnu.";
      elements.testChatContextList.appendChild(li);
    } else {
      files.forEach((file) => {
        const li = document.createElement("li");
        li.className = "context-file-item";
        const name = document.createElement("span");
        name.className = "context-file-name";
        const typeLabel = file.file_type ? "[" + file.file_type + "] " : "";
        const noteLabel = file.extraction_note ? " - " + file.extraction_note : "";
        name.textContent = typeLabel + file.filename + " (" + (file.size_chars || 0) + " tegn)" + noteLabel;
        li.appendChild(name);
        const removeBtn = document.createElement("button");
        removeBtn.type = "button";
        removeBtn.className = "context-file-remove";
        removeBtn.setAttribute("data-context-id", file.context_id);
        removeBtn.setAttribute("aria-label", "Fjern " + file.filename);
        removeBtn.textContent = "×";
        li.appendChild(removeBtn);
        elements.testChatContextList.appendChild(li);
      });
    }
  }

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
    savedLogs: [],
    selectedLogId: null,
    selectedLogContent: null,
  };
}
