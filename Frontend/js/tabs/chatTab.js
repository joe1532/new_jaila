function formatChatLogEntryAsText(entry) {
  if (!entry) return "";
  const lines = [];
  lines.push("Chat-log");
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

export function renderChat(elements, state) {
  if (elements.chatUseVectorSearch) {
    elements.chatUseVectorSearch.checked = state.chat.useVectorSearch !== false;
  }

  if (elements.chatContextList) {
    elements.chatContextList.innerHTML = "";
    const files = state.chat.contextFiles || [];
    if (!files.length) {
      const li = document.createElement("li");
      li.className = "context-file-item-empty";
      li.textContent = "Ingen filer uploadet endnu.";
      elements.chatContextList.appendChild(li);
    } else {
      files.forEach((file) => {
        const li = document.createElement("li");
        li.className = "context-file-item";

        const name = document.createElement("span");
        name.className = "context-file-name";
        const typeLabel = file.file_type ? "[" + file.file_type + "] " : "";
        const noteLabel = file.extraction_note ? " - " + file.extraction_note : "";
        name.textContent =
          typeLabel + file.filename + " (" + (file.size_chars || 0) + " tegn)" + noteLabel;
        li.appendChild(name);

        const removeBtn = document.createElement("button");
        removeBtn.type = "button";
        removeBtn.className = "context-file-remove";
        removeBtn.setAttribute("data-context-id", file.context_id);
        removeBtn.setAttribute("aria-label", "Fjern " + file.filename);
        removeBtn.textContent = "×";
        li.appendChild(removeBtn);

        elements.chatContextList.appendChild(li);
      });
    }
  }

  if (elements.chatLogContent) {
    const savedLogs = state.chat.savedLogs || [];
    const selectedLogContent = state.chat.selectedLogContent;

    if (selectedLogContent) {
      elements.chatLogContent.innerHTML = "";
      const backBtn = document.createElement("button");
      backBtn.type = "button";
      backBtn.className = "button-secondary analyse-log-back";
      backBtn.textContent = "← Tilbage til liste";
      backBtn.dataset.action = "chat-log-back";
      elements.chatLogContent.appendChild(backBtn);

      const loadBtn = document.createElement("button");
      loadBtn.type = "button";
      loadBtn.className = "button-secondary analyse-log-back";
      loadBtn.textContent = "Indlæs chat";
      loadBtn.dataset.action = "chat-log-load";
      loadBtn.dataset.entryId = selectedLogContent.id || "";
      elements.chatLogContent.appendChild(loadBtn);
      const deleteBtn = document.createElement("button");
      deleteBtn.type = "button";
      deleteBtn.className = "button-secondary analyse-log-back";
      deleteBtn.textContent = "Slet gemt chat";
      deleteBtn.dataset.action = "chat-log-delete";
      deleteBtn.dataset.entryId = selectedLogContent.id || "";
      elements.chatLogContent.appendChild(deleteBtn);

      const useInSagsBtn = document.createElement("button");
      useInSagsBtn.type = "button";
      useInSagsBtn.className = "button-secondary analyse-log-back";
      useInSagsBtn.textContent = "Brug i sagsbehandling";
      useInSagsBtn.dataset.action = "use-chat-as-sags-context";
      useInSagsBtn.dataset.entryId = selectedLogContent.id || "";
      elements.chatLogContent.appendChild(useInSagsBtn);

      const pre = document.createElement("pre");
      pre.className = "analyse-log-full";
      pre.textContent = formatChatLogEntryAsText(selectedLogContent);
      elements.chatLogContent.appendChild(pre);
    } else if (savedLogs.length) {
      elements.chatLogContent.innerHTML = "";
      const ul = document.createElement("ul");
      ul.className = "analyse-log-list";
      savedLogs.forEach((entry) => {
        const li = document.createElement("li");
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "analyse-log-entry";
        btn.dataset.entryId = entry.id || "";
        const when = entry.updated_at || entry.created_at || "";
        btn.textContent = `${entry.title || "Chat uden titel"} (${when})`;
        li.appendChild(btn);
        ul.appendChild(li);
      });
      elements.chatLogContent.appendChild(ul);
    } else {
      elements.chatLogContent.innerHTML = "";
      const p = document.createElement("p");
      p.className = "analyse-log-empty";
      p.textContent = "Ingen gemte chats endnu.";
      elements.chatLogContent.appendChild(p);
    }
  }

  if (!elements.chatConversation) {
    return;
  }
  const conversationEl = elements.chatConversation;
  const messages = state.chat.messages || [];
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

  // Auto-scroll kun hvis brugeren allerede er nær bunden (fx under streaming).
  // Så kan man scrolle op og læse uden at blive trukket ned.
  const threshold = 80;
  const atBottom =
    conversationEl.scrollHeight - conversationEl.scrollTop - conversationEl.clientHeight <= threshold;
  if (atBottom) {
    conversationEl.scrollTop = conversationEl.scrollHeight;
  }

  if (elements.chatInput && elements.chatInput.value !== state.chat.inputText) {
    elements.chatInput.value = state.chat.inputText || "";
  }
}

export function getInitialChatState() {
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
