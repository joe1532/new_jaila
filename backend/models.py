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
