from pydantic import BaseModel, Field
from typing import Any


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


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Brugerens chatbesked")
    previous_response_id: str | None = Field(
        default=None,
        description="Response ID fra forrige chatkald for fortsat samtale",
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


class ChatResponse(BaseModel):
    answer: str
    used_model: str
    response_id: str


class ChatMessage(BaseModel):
    role: str = Field(..., min_length=1, description="Rolle: user/assistant/system")
    text: str = Field(..., min_length=1, description="Beskedtekst")


class ChatExportRequest(BaseModel):
    messages: list[ChatMessage] = Field(
        default_factory=list,
        description="Hele chatforløbet der skal eksporteres til PDF",
    )


class ChatExportResponse(BaseModel):
    log_pdf_filename: str
    log_pdf_url: str


class ChatLogSaveRequest(BaseModel):
    user: str = Field(..., min_length=1, description="Brugernavn")
    session_id: str = Field(..., min_length=1, description="Chat-session-id")
    messages: list[ChatMessage] = Field(
        default_factory=list,
        description="Hele chatforløbet der skal gemmes",
    )
    used_model: str = Field(..., description="Model brugt")
    last_response_id: str | None = Field(
        default=None,
        description="Seneste response_id for chatforløbet",
    )


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


class ChatContextFileResponse(BaseModel):
    context_id: str
    filename: str
    file_type: str
    size_chars: int
    extraction_note: str | None = None


class ChatContextListResponse(BaseModel):
    files: list[ChatContextFileResponse]


class SagsLegalBasisResponse(BaseModel):
    subtab: str
    vector_store_id: str | None = None
    documents: list[str] = Field(default_factory=list)


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
