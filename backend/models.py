from pydantic import BaseModel, Field
from typing import Any
from typing import Literal


class DecisionSelectedArticle(BaseModel):
    article: int | None = None
    section: int | None = None
    raw_text: str = ""
    source: str = "ui"
    origin: Literal["oplyst", "udledt", "beregnet", "valgt"] = "valgt"
    certainty: Literal["høj", "middel", "lav"] = "middel"
    status: Literal["aktiv", "konfliktende", "uafklaret"] = "uafklaret"
    candidate_articles: list[str] = Field(default_factory=list)


class DecisionSagskontekst(BaseModel):
    indkomsttype: str = ""
    valgt_artikel: DecisionSelectedArticle = Field(default_factory=DecisionSelectedArticle)
    bopaelsland: str = ""
    arbejdsgivertype: str = ""


class DecisionRuleProfile(BaseModel):
    profile_id: str = ""
    requires_day_allocation: bool = False
    requires_employer_assessment: bool = False


class DecisionFact(BaseModel):
    fact_key: str
    value: Any = None
    source: str = "ui"
    origin: Literal["oplyst", "udledt", "beregnet", "valgt"] = "oplyst"
    certainty: Literal["høj", "middel", "lav"] = "middel"
    status: Literal["aktiv", "konfliktende", "uafklaret"] = "aktiv"
    note: str = ""


class DecisionFordelingsmetode(BaseModel):
    method_id: str = ""
    description: str = ""
    basis: Any = ""
    period: str = ""
    begrundelse: str = ""
    begrænsninger: list[str] = Field(default_factory=list)
    calculation: dict[str, Any] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)


class DecisionTaxRightShare(BaseModel):
    label: str = ""
    country: str = ""
    amount: float | None = None
    currency: str = "DKK"
    share_ratio: float | None = None
    basis: str = ""
    juridisk_hjemmel: str = ""
    forudsætninger: list[str] = Field(default_factory=list)
    kilde_trin: list[str] = Field(default_factory=list)
    status: Literal["aktiv", "konfliktende", "uafklaret"] = "uafklaret"
    note: str = ""


class DecisionAssessmentStep(BaseModel):
    trin_id: str = ""
    juridisk_spoergsmaal: str = ""
    faktagrundlag: list[str] = Field(default_factory=list)
    resultat: Any = None
    status: Literal["afklaret", "uafklaret", "konfliktende"] = "uafklaret"
    tekstlinje: str = ""


class DecisionQaBlock(BaseModel):
    mangler: list[Any] = Field(default_factory=list)
    konflikter: list[Any] = Field(default_factory=list)
    risici: list[Any] = Field(default_factory=list)


class DecisionInputQuality(BaseModel):
    niveau: Literal["høj", "middel", "lav"] = "middel"
    begrundelse: list[str] = Field(default_factory=list)


class SagsDecisionPackage(BaseModel):
    sagskontekst: DecisionSagskontekst = Field(default_factory=DecisionSagskontekst)
    regelprofil: DecisionRuleProfile = Field(default_factory=DecisionRuleProfile)
    konstaterede_fakta: list[DecisionFact] = Field(default_factory=list)
    afledte_praemisser: list[Any] = Field(default_factory=list)
    relevante_retskilder: list[dict[str, Any]] = Field(default_factory=list)
    uafklarede_sporgsmaal: list[Any] = Field(default_factory=list)
    fordelingsmetode: DecisionFordelingsmetode = Field(default_factory=DecisionFordelingsmetode)
    foreloebig_beskatningsret: list[DecisionTaxRightShare] = Field(default_factory=list)
    vurderingstrin: list[DecisionAssessmentStep] = Field(default_factory=list)
    samlet_konklusion: dict[str, Any] = Field(default_factory=dict)
    konflikter: list[Any] = Field(default_factory=list)
    advarsler: list[Any] = Field(default_factory=list)
    qa: DecisionQaBlock = Field(default_factory=DecisionQaBlock)
    input_kvalitet: DecisionInputQuality = Field(default_factory=DecisionInputQuality)


class AnalyzeRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Brugerens juridiske spørgsmål")
    previous_response_id: str | None = Field(
        default=None,
        description="Response ID fra forrige analysekald til opfølgende spørgsmål",
    )
    source_tab: str | None = Field(
        default=None,
        description="UI-kontekst, fx analyse eller sagsbehandling",
    )
    subtab: str | None = Field(
        default=None,
        description="Undertab i source_tab, fx skattepligt_ligningsfrist",
    )
    case_facts: dict[str, Any] | None = Field(
        default=None,
        description="Strukturerede faktafelter fra sagsbehandling",
    )
    sags_decision_package: SagsDecisionPackage | None = Field(
        default=None,
        description="Struktureret beslutningspakke til LLM-vurdering",
    )
    context_log_id: str | None = Field(
        default=None,
        description="(Forældet) Enkelt analyse-log. Brug context_log_ids i stedet.",
    )
    context_log_ids: list[str] | None = Field(
        default=None,
        description="Valgte analyse-logs der skal bruges som kontekst i sagsbehandling",
    )
    context_user: str | None = Field(
        default=None,
        description="Bruger som ejer analyse-loggen",
    )
    context_approved: bool = Field(
        default=False,
        description="Frontend har vist kontekst og bruger har godkendt den",
    )
    case_id: str | None = Field(
        default=None,
        description="Aktiv sag i sagsbehandling (niveau 2)",
    )
    case_user: str | None = Field(
        default=None,
        description="Ejer af aktiv sag i sagsbehandling",
    )
    legal_context_blocks: list[str] | None = Field(
        default=None,
        description="Valgte retskilde-tekstblokke fra Analyse-fanen",
    )
    use_semantic_search_with_legal_context: bool = Field(
        default=False,
        description="Hvis true bruges file_search også når legal_context_blocks er sat",
    )


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Brugerens chatbesked")
    previous_response_id: str | None = Field(
        default=None,
        description="Response ID fra forrige chatkald for fortsat samtale",
    )
    use_vector_search: bool = Field(
        default=True,
        description="Hvis true bruges file_search mod vector stores i chat",
    )
    vector_store_ids: list[str] | None = Field(
        default=None,
        description="Valgfri override af vector stores i chat",
    )
    allow_markdown: bool = Field(
        default=False,
        description="Hvis true må svaret bruge markdown (##, **fed**, lister, tabeller)",
    )


class Citation(BaseModel):
    file_id: str
    filename: str


class RetrievalResult(BaseModel):
    file_id: str = ""
    filename: str
    score: str
    text: str


class AnalyzeResponse(BaseModel):
    answer: str
    used_model: str
    response_id: str
    citations: list[Citation]
    retrieval_results: list[RetrievalResult]
    log_pdf_filename: str
    log_pdf_url: str


class RetrievalSearch(BaseModel):
    """En enkelt søgning, modellen selv formulerede og sendte til file_search."""

    queries: list[str] = Field(default_factory=list)
    status: str = ""
    num_results: int = 0


class RetrievalDiagnostics(BaseModel):
    """Observation af, om søgningen hentede det, spørgsmålet nævnte.

    Felterne har defaults hele vejen, fordi diagnosen udelades, når vector search er slået
    fra. Et tomt objekt betyder derfor "ikke målt", ikke "intet fundet".
    """

    searches: list[RetrievalSearch] = Field(default_factory=list)
    num_results: int = 0
    score_min: float | None = None
    score_max: float | None = None
    asked_references: dict[str, list[str]] = Field(default_factory=dict)
    missing_references: dict[str, list[str]] = Field(default_factory=dict)
    has_missing_references: bool = False


class ChatResponse(BaseModel):
    answer: str
    used_model: str
    response_id: str
    used_vector_store_ids: list[str] = Field(default_factory=list)
    vector_search_enabled: bool = False
    citations: list[Citation] = Field(default_factory=list)
    retrieval_results: list[RetrievalResult] = Field(default_factory=list)
    used_retrieval_results: list[RetrievalResult] = Field(default_factory=list)
    retrieval_diagnostics: RetrievalDiagnostics = Field(default_factory=RetrievalDiagnostics)


class ChatMessage(BaseModel):
    role: str = Field(..., min_length=1, description="Rolle: user/assistant/system")
    text: str = Field(..., min_length=1, description="Beskedtekst")


class ChatExportRequest(BaseModel):
    messages: list[ChatMessage] = Field(
        default_factory=list,
        description="Hele chatforløbet der skal eksporteres til PDF",
    )
    citations: list[dict] = Field(default_factory=list)
    retrieval_results: list[dict] = Field(default_factory=list)
    used_retrieval_results: list[dict] = Field(default_factory=list)
    used_vector_store_ids: list[str] = Field(default_factory=list)


class ChatExportResponse(BaseModel):
    log_pdf_filename: str
    log_pdf_url: str


class ChatLogSaveRequest(BaseModel):
    user: str = Field(..., min_length=1, description="Brugernavn")
    session_id: str = Field(..., min_length=1, description="Chat-session-id")
    kind: str = Field(
        default="chat",
        description="Hvilken historik loggen hører til: 'chat' eller 'test'",
    )
    messages: list[ChatMessage] = Field(
        default_factory=list,
        description="Hele chatforløbet der skal gemmes",
    )
    used_model: str = Field(..., description="Model brugt")
    last_response_id: str | None = Field(
        default=None,
        description="Seneste response_id for chatforløbet",
    )
    citations: list[dict] = Field(default_factory=list)
    retrieval_results: list[dict] = Field(default_factory=list)
    used_retrieval_results: list[dict] = Field(default_factory=list)
    used_vector_store_ids: list[str] = Field(default_factory=list)


class ChatLogSaveResponse(BaseModel):
    id: str
    session_id: str
    title: str
    created_at: str
    updated_at: str
    used_model: str


class ChatLogEntry(BaseModel):
    id: str
    session_id: str
    title: str
    created_at: str
    updated_at: str
    used_model: str


class ChatLogListResponse(BaseModel):
    entries: list[ChatLogEntry]


class ChatLogGetResponse(BaseModel):
    id: str
    session_id: str
    title: str
    created_at: str
    updated_at: str
    used_model: str
    last_response_id: str | None = None
    messages: list[ChatMessage] = Field(default_factory=list)
    citations: list[dict] = Field(default_factory=list)
    retrieval_results: list[dict] = Field(default_factory=list)
    used_retrieval_results: list[dict] = Field(default_factory=list)
    used_vector_store_ids: list[str] = Field(default_factory=list)


class ChatContextFileResponse(BaseModel):
    context_id: str
    filename: str
    file_type: str
    size_chars: int
    extraction_note: str | None = None
    # Arten styrer, hvordan materialet rammesættes for modellen: sagens fakta,
    # fortolkningsbidrag eller vejledning i sprog og form.
    kind: str = "fakta"
    enabled: bool = True


class ChatContextListResponse(BaseModel):
    files: list[ChatContextFileResponse]


class ChatContextToggleRequest(BaseModel):
    enabled: bool


class ChatContextTextRequest(BaseModel):
    """Kontekst, der er dannet i JAILA selv - fx forarbejder - og ikke uploadet fra disk."""

    filename: str
    text: str
    kind: str = "retskilde"


class SagsLegalBasisResponse(BaseModel):
    subtab: str
    vector_store_id: str | None = None
    documents: list[str] = Field(default_factory=list)


class LegalSourcesCatalogResponse(BaseModel):
    categories: list[dict[str, Any]] = Field(default_factory=list)
    documents: list[dict[str, Any]] = Field(default_factory=list)


class LegalSourceSectionResponse(BaseModel):
    source_id: str
    title: str
    text: str
    truncated: bool = False
    page: int = 1
    total_pages: int = 1


class CaseCreateRequest(BaseModel):
    user: str = Field(..., min_length=1, description="Brugernavn")
    title: str | None = Field(default=None, description="Valgfri sags-titel")


class CaseEntry(BaseModel):
    id: str
    title: str
    status: str
    created_at: str
    updated_at: str


class CaseListResponse(BaseModel):
    entries: list[CaseEntry]


class CaseGetResponse(BaseModel):
    id: str
    title: str
    status: str
    created_at: str
    updated_at: str
    active_subtab: str = "skattepligt_ligningsfrist"
    shared_facts: dict[str, Any] = Field(default_factory=dict)
    subtab_outputs: dict[str, Any] = Field(default_factory=dict)
    locked_by_subtab: dict[str, bool] = Field(default_factory=dict)
    facts_locked_by_subtab: dict[str, bool] = Field(default_factory=dict)
    facts_by_subtab: dict[str, Any] = Field(default_factory=dict)
    context_by_subtab: dict[str, Any] = Field(default_factory=dict)
    messages_by_subtab: dict[str, list[ChatMessage]] = Field(default_factory=dict)
    previous_response_id_by_subtab: dict[str, str | None] = Field(default_factory=dict)
    used_model_by_subtab: dict[str, str | None] = Field(default_factory=dict)


class CaseUpdateRequest(BaseModel):
    user: str = Field(..., min_length=1, description="Brugernavn")
    title: str | None = None
    status: str | None = None
    active_subtab: str | None = None
    shared_facts: dict[str, Any] | None = None
    subtab_outputs: dict[str, Any] | None = None
    locked_by_subtab: dict[str, bool] | None = None
    facts_locked_by_subtab: dict[str, bool] | None = None
    facts_by_subtab: dict[str, Any] | None = None
    context_by_subtab: dict[str, Any] | None = None
    messages_by_subtab: dict[str, list[ChatMessage]] | None = None
    previous_response_id_by_subtab: dict[str, str | None] | None = None
    used_model_by_subtab: dict[str, str | None] | None = None


class AnalyseLogSaveRequest(BaseModel):
    user: str = Field(..., min_length=1, description="Brugernavn")
    session_id: str | None = Field(
        default=None,
        description="Analyse-session-id for upsert (én log per aktiv analyse)",
    )
    question: str = Field(..., description="Spørgsmål")
    answer: str = Field(..., description="Svar")
    citations: list[dict] = Field(default_factory=list)
    retrieval_results: list[dict] = Field(default_factory=list)
    used_model: str = Field(..., description="Model brugt")
    log_question: str | None = Field(default=None, description="Fuld log-spørgsmål")
    used_vector_store_ids: list[str] | None = Field(default=None)
    log_pdf_filename: str | None = Field(default=None)
    log_pdf_url: str | None = Field(default=None)
    messages: list[ChatMessage] = Field(
        default_factory=list,
        description="Hele analyseforløbet som beskedliste",
    )
    last_response_id: str | None = Field(
        default=None,
        description="Seneste response_id for analyseforløbet",
    )


class AnalyseLogSaveResponse(BaseModel):
    id: str
    title: str
    created_at: str
    log_pdf_filename: str | None = None
    log_pdf_url: str | None = None


class AnalyseLogEntry(BaseModel):
    id: str
    created_at: str
    title: str
    log_pdf_filename: str | None = None
    log_pdf_url: str | None = None


class AnalyseLogListResponse(BaseModel):
    entries: list[AnalyseLogEntry]


class AnalyseLogGetResponse(BaseModel):
    id: str
    session_id: str | None = None
    created_at: str
    title: str
    question: str
    answer: str
    citations: list[dict]
    retrieval_results: list[dict]
    used_model: str
    used_vector_store_ids: list[str]
    log_pdf_filename: str | None = None
    log_pdf_url: str | None = None
    messages: list[ChatMessage] = Field(default_factory=list)
    last_response_id: str | None = None


class ForarbejderLawEntry(BaseModel):
    name: str = Field(..., description="Lovens almindelige navn, fx 'Ligningsloven'")
    eli: str = Field(..., description="Kendt holdepunkt, fx 'eli/lta/2025/1500'")


class ForarbejderLawsResponse(BaseModel):
    laws: list[ForarbejderLawEntry] = Field(default_factory=list)
    available: bool = Field(
        default=True,
        description="Kunne forarbejdsmotoren indlæses? Er den falsk, står grunden i reason",
    )
    reason: str = ""


class ForarbejderVersionEntry(BaseModel):
    eli: str
    label: str = Field(..., description="Fx 'LBK 1500 af 6. november 2025'")
    date: str = Field(..., description="ISO-dato for bekendtgørelsen")


class ForarbejderVersionsResponse(BaseModel):
    newest_eli: str = Field(..., description="Lovens seneste bekendtgørelse")
    versions: list[ForarbejderVersionEntry] = Field(default_factory=list)
    notice: str = Field(
        default="",
        description="Oplyses, hvis holdepunktet var overhalet, eller kontrollen fejlede",
    )


class ForarbejderParagraphsResponse(BaseModel):
    eli: str
    paragraphs: list[str] = Field(default_factory=list)


class ForarbejderHistoryRequest(BaseModel):
    eli: str = Field(..., min_length=1, description="Den udgave af loven, der spørges til")
    paragraph: str = Field(..., min_length=1, description="Paragraffen, fx '9 C' eller '9C'")
    steps: int = Field(
        default=8,
        ge=1,
        le=40,
        description="Led i kæden af lovbekendtgørelser, der gås bagud",
    )
