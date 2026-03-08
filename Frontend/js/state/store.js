const state = {
  auth: {
    user: null,
    isLoggedIn: false,
  },
  ui: {
    activeTab: "chat",
    loading: false,
    error: null,
    statusMessage: "Klar.",
    statusMode: "ok",
  },
  analyse: {
    question: "",
    answer: "Intet svar endnu.",
    messages: [],
    usedModel: null,
    citations: [],
    retrievalResults: [],
    logPdfUrl: "",
    logPdfLabel: "",
    previousResponseId: null,
  },
  sagsbehandling: {
    activeSubtab: "skattepligt_ligningsfrist",
    activeFunction: "",
    inputText: "",
    messages: [],
  },
  chat: {
    messages: [],
    inputText: "",
    usedModel: null,
    previousResponseId: null,
    contextFiles: [],
  },
};

function mergeObject(target, patch) {
  Object.keys(patch).forEach((key) => {
    const patchValue = patch[key];
    if (
      patchValue &&
      typeof patchValue === "object" &&
      !Array.isArray(patchValue) &&
      target[key] &&
      typeof target[key] === "object" &&
      !Array.isArray(target[key])
    ) {
      mergeObject(target[key], patchValue);
      return;
    }
    target[key] = patchValue;
  });
}

export function getState() {
  return state;
}

export function setState(patch) {
  mergeObject(state, patch);
  return state;
}
