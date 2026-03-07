function normalizeDanishDisplayText(value) {
  const text = String(value || "");
  if (!text) {
    return text;
  }
  if (!/[ÃÂâ]/.test(text)) {
    return text;
  }

  try {
    const bytes = new Uint8Array(Array.from(text, (char) => char.charCodeAt(0) & 0xff));
    const decoded = new TextDecoder("utf-8", { fatal: false }).decode(bytes);
    const mojibakeScore = (input) => {
      const matches = input.match(/[ÃÂâ]/g);
      return matches ? matches.length : 0;
    };
    return mojibakeScore(decoded) < mojibakeScore(text) ? decoded : text;
  } catch (_err) {
    return text;
  }
}

export function renderAnalyse(elements, state) {
  if (elements.question && elements.question.value !== state.analyse.question) {
    elements.question.value = state.analyse.question || "";
  }

  if (elements.answer) {
    elements.answer.textContent = state.analyse.answer || "Intet svar endnu.";
  }

  if (elements.citations) {
    elements.citations.innerHTML = "";
    const citations = state.analyse.citations || [];
    if (!citations.length) {
      const li = document.createElement("li");
      li.textContent = "Ingen citations fundet.";
      elements.citations.appendChild(li);
    } else {
      citations.forEach((citation) => {
        const li = document.createElement("li");
        const filename = normalizeDanishDisplayText(citation.filename || "(ukendt filnavn)");
        const fileId = citation.file_id || "(ukendt file_id)";
        li.textContent = filename + " (file_id: " + fileId + ")";
        elements.citations.appendChild(li);
      });
    }
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
    usedModel: null,
    citations: [],
    retrievalResults: [],
    logPdfUrl: "",
    logPdfLabel: "",
    previousResponseId: null,
  };
}
