export function renderChat(elements, state) {
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

  conversationEl.scrollTop = conversationEl.scrollHeight;

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
  };
}
