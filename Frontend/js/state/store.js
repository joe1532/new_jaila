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
    legalLibraryPanelOpen: false,
    legalLibrarySearchQuery: "",
    legalLibraryActiveCategory: "",
    legalLibraryActiveDocument: "",
    legalLibraryActiveVersion: "",
    legalLibraryPreviewSection: "",
    legalLibraryPreviewLoadingSourceId: "",
    legalLibrarySectionTextBySourceId: {},
    legalLibraryPreviewPageBySourceId: {},
    legalLibraryPreviewTotalPagesBySourceId: {},
    legalContexts: [],
    useSemanticWithLegalContext: false,
  },
  sagsbehandling: {
    activeCaseId: null,
    cases: [],
    activeSubtab: "skattepligt_ligningsfrist",
    activeFunction: "",
    inputText: "",
    messages: [],
    messagesBySubtab: {},
    previousResponseId: null,
    previousResponseIdBySubtab: {},
    usedModel: null,
    usedModelBySubtab: {},
    sharedFacts: {},
    subtabOutputs: {},
    subtabOutputLocked: {},
    factsLockedBySubtab: {},
    factsPanelOpen: false,
    legalLibraryPanelOpen: false,
    legalLibrarySearchQuery: "",
    selectedLegalSourcesBySubtab: {},
    legalLibraryActiveCategoryBySubtab: {},
    legalLibraryPreviewSourceBySubtab: {},
    legalLibraryActiveDocumentBySubtab: {},
    legalLibraryActiveVersionBySubtab: {},
    legalLibraryPreviewSectionBySubtab: {},
    legalLibraryCategories: [],
    legalLibraryCatalog: [],
    legalLibraryCatalogLoaded: false,
    legalLibrarySectionTextBySourceId: {},
    legalLibraryPreviewLoadingSourceId: "",
    legalLibraryPreviewPageBySourceId: {},
    legalLibraryPreviewTotalPagesBySourceId: {},
    factsBySubtab: {},
    contextBySubtab: {},
    legalBasisBySubtab: {},
    legalBasisLoadingBySubtab: {},
    autoLegalBasisTextBySubtab: {},
  },
  chat: {
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
