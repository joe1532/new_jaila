from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Brugerens juridiske spørgsmål")
    previous_response_id: str | None = Field(
        default=None,
        description="Response ID fra forrige analysekald til opfølgende spørgsmål",
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
