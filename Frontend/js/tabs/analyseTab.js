export function renderAnalyse(elements, state) {
  if (elements.question && elements.question.value !== state.analyse.question) {
    elements.question.value = state.analyse.question || "";
  }

  if (elements.analyseConversation) {
    const conversationEl = elements.analyseConversation;
    const messages = state.analyse.messages || [];
    conversationEl.innerHTML = "";

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
    conversationEl.scrollTop = conversationEl.scrollHeight;
  }

  if (elements.pdfLogLink) {
    const url = state.analyse.logPdfUrl || "";
    const defaultLabel = "Download analyse";
    elements.pdfLogLink.textContent = defaultLabel;
    elements.pdfLogLink.disabled = !url;
    elements.pdfLogLink.dataset.pdfUrl = url;
  }
}

export function getInitialAnalyseState() {
  return {
    question: "",
    answer: "Intet svar endnu.",
    messages: [],
    usedModel: null,
    citations: [],
    retrievalResults: [],
    logPdfUrl: "",
    logPdfLabel: "",
    previousResponseId: null,
  };
}
