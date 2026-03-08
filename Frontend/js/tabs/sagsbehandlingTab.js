const SUBTAB_CONFIG = {
  skattepligt_ligningsfrist: {
    title: "Sagsbehandling - Skattepligt og ligningsfrist",
    placeholder: "Beskriv sagen om skattepligt/ligningsfrist (dummy)...",
    functions: [
      "Vurder skattepligt (dummy)",
      "Vurder ligningsfrist (dummy)",
      "Opsummer risikopunkter (dummy)",
    ],
  },
  opgoerelse_indkomst: {
    title: "Sagsbehandling - Opgørelse af indkomst",
    placeholder: "Beskriv opgørelsen af indkomst (dummy)...",
    functions: [
      "Beregn skattepligtig indkomst (dummy)",
      "Vurder fradragsposter (dummy)",
      "Lav opgørelsesnotat (dummy)",
    ],
  },
  beskatningsret_indkomst: {
    title: "Sagsbehandling - Beskatningsret til indkomst",
    placeholder: "Beskriv spørgsmålet om beskatningsret (dummy)...",
    functions: [
      "Fordel beskatningsret (dummy)",
      "Vurder DBO-relevans (dummy)",
      "Opsummer hjemmel (dummy)",
    ],
  },
  lempelse: {
    title: "Sagsbehandling - Lempelse",
    placeholder: "Beskriv spørgsmålet om lempelse (dummy)...",
    functions: [
      "Vælg lempelsesmetode (dummy)",
      "Beregn credit/exemption (dummy)",
      "Dokumentationscheck (dummy)",
    ],
  },
  andet: {
    title: "Sagsbehandling - Andet",
    placeholder: "Beskriv anden sagsbehandling (dummy)...",
    functions: [
      "Generel juridisk vurdering (dummy)",
      "Klassificer problemstilling (dummy)",
      "Lav handlingsplan (dummy)",
    ],
  },
};

export function renderSagsbehandling(elements, state) {
  const activeSubtab = state.sagsbehandling.activeSubtab || "skattepligt_ligningsfrist";
  const cfg = SUBTAB_CONFIG[activeSubtab] || SUBTAB_CONFIG.skattepligt_ligningsfrist;

  if (elements.sagsbehandlingTitle) {
    elements.sagsbehandlingTitle.textContent = cfg.title;
  }

  if (elements.sagsbehandlingInput) {
    if (elements.sagsbehandlingInput.value !== state.sagsbehandling.inputText) {
      elements.sagsbehandlingInput.value = state.sagsbehandling.inputText || "";
    }
    elements.sagsbehandlingInput.placeholder = cfg.placeholder;
  }

  if (elements.sagsbehandlingConversation) {
    const messages = state.sagsbehandling.messages || [];
    const container = elements.sagsbehandlingConversation;
    container.innerHTML = "";
    if (!messages.length) {
      const msg = document.createElement("div");
      msg.className = "msg msg-system";
      msg.textContent =
        "Dummy-fane for nu. Undertabben styrer senere prompt, vector stores og flow i denne midterboks.";
      container.appendChild(msg);
    } else {
      messages.forEach((entry) => {
        const msg = document.createElement("div");
        msg.classList.add("msg", "msg-system");
        msg.textContent = entry;
        container.appendChild(msg);
      });
    }
    container.scrollTop = container.scrollHeight;
  }

  if (elements.sagsSubtabButtons && elements.sagsSubtabButtons.length) {
    elements.sagsSubtabButtons.forEach((btn) => {
      const isActive = btn.dataset.sagsSubtab === activeSubtab;
      btn.classList.toggle("sags-subtab-button-active", isActive);
    });
  }

  if (elements.sagsFunctionList) {
    const activeFunction = state.sagsbehandling.activeFunction || "";
    elements.sagsFunctionList.innerHTML = "";
    const functions = cfg.functions || [];
    functions.forEach((label) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "button-secondary sags-function-button";
      if (label === activeFunction) {
        btn.classList.add("sags-function-button-active");
      }
      btn.dataset.sagsFunction = label;
      btn.textContent = label;
      elements.sagsFunctionList.appendChild(btn);
    });
  }
}
