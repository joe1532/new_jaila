function formatLogEntryAsText(entry) {
  if (!entry) return "";
  const lines = [];
  lines.push("Juridisk forespørgselslog");
  lines.push(`Tidspunkt: ${entry.created_at || ""}`);
  lines.push(`Model brugt: ${entry.used_model || ""}`);
  const vs = entry.used_vector_store_ids || [];
  lines.push(`Vector stores: ${vs.join(", ")}`);
  lines.push("");
  lines.push("─── Spørgsmål ───");
  lines.push(entry.question || "");
  lines.push("");
  lines.push("─── Svar ───");
  lines.push(entry.answer || "(Tomt svar)");
  lines.push("");
  lines.push("─── Kilder (citations) ───");
  (entry.citations || []).forEach((c, i) => {
    lines.push(`  ${i + 1}. ${c.filename || c.file_id || "?"}`);
  });
  lines.push("");
  lines.push("─── Retrieval-træf ───");
  (entry.retrieval_results || []).slice(0, 10).forEach((r, i) => {
    const txt = (r.text || "").slice(0, 100).replace(/\n/g, " ");
    lines.push(`  ${i + 1}. ${r.filename || "?"}: ${txt}…`);
  });
  return lines.join("\n");
}

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
    // Auto-scroll kun hvis brugeren allerede er nær bunden (fx under streaming).
    const threshold = 80;
    const atBottom =
      conversationEl.scrollHeight - conversationEl.scrollTop - conversationEl.clientHeight <= threshold;
    if (atBottom) {
      conversationEl.scrollTop = conversationEl.scrollHeight;
    }
  }

  if (elements.pdfLogLink) {
    // PDF-download er flyttet til forespørgselsloggen pr. gemt entry.
    elements.pdfLogLink.disabled = true;
    elements.pdfLogLink.style.display = "none";
  }

  if (elements.analyseLogContent) {
    const savedLogs = state.analyse.savedLogs || [];
    const selectedLogId = state.analyse.selectedLogId;
    const selectedLogContent = state.analyse.selectedLogContent;

    if (selectedLogContent) {
      elements.analyseLogContent.innerHTML = "";
      const pre = document.createElement("pre");
      pre.className = "analyse-log-full";
      pre.textContent = formatLogEntryAsText(selectedLogContent);
      const backBtn = document.createElement("button");
      backBtn.type = "button";
      backBtn.className = "button-secondary analyse-log-back";
      backBtn.textContent = "← Tilbage til liste";
      backBtn.dataset.action = "log-back";
      elements.analyseLogContent.appendChild(backBtn);
      const logPdfUrl = (selectedLogContent.log_pdf_url || "").trim();
      if (logPdfUrl) {
        const pdfLink = document.createElement("a");
        pdfLink.className = "button-secondary analyse-log-back";
        pdfLink.textContent = selectedLogContent.log_pdf_filename || "Download analyse-PDF";
        pdfLink.href = logPdfUrl;
        pdfLink.target = "_blank";
        pdfLink.rel = "noopener noreferrer";
        elements.analyseLogContent.appendChild(pdfLink);
      }
      elements.analyseLogContent.appendChild(pre);
    } else if (savedLogs.length) {
      elements.analyseLogContent.innerHTML = "";
      const ul = document.createElement("ul");
      ul.className = "analyse-log-list";
      savedLogs.forEach((entry) => {
        const li = document.createElement("li");
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "analyse-log-entry";
        btn.dataset.entryId = entry.id;
        btn.textContent = `${entry.title || "Uden titel"} (${entry.created_at || ""})`;
        li.appendChild(btn);
        ul.appendChild(li);
      });
      elements.analyseLogContent.appendChild(ul);
    } else {
      elements.analyseLogContent.innerHTML = "";
      const p = document.createElement("p");
      p.className = "analyse-log-empty";
      p.textContent = "Ingen gemte forespørgsler endnu. Kør en analyse for at gemme.";
      elements.analyseLogContent.appendChild(p);
    }
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
    savedLogs: [],
    selectedLogId: null,
    selectedLogContent: null,
  };
}
