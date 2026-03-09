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


class AnalyseLogSaveRequest(BaseModel):
    user: str = Field(..., min_length=1, description="Brugernavn")
    question: str = Field(..., description="Spørgsmål")
    answer: str = Field(..., description="Svar")
    citations: list[dict] = Field(default_factory=list)
    retrieval_results: list[dict] = Field(default_factory=list)
    used_model: str = Field(..., description="Model brugt")
    log_question: str | None = Field(default=None, description="Fuld log-spørgsmål")
    used_vector_store_ids: list[str] | None = Field(default=None)
    log_pdf_filename: str | None = Field(default=None)
    log_pdf_url: str | None = Field(default=None)


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
