from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Brugerens juridiske spørgsmål")


class Citation(BaseModel):
    file_id: str
    filename: str


class RetrievalResult(BaseModel):
    filename: str
    score: str
    text: str


class AnalyzeResponse(BaseModel):
    answer: str
    used_model: str
    citations: list[Citation]
    retrieval_results: list[RetrievalResult]
    log_pdf_filename: str
    log_pdf_url: str
