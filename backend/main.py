import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from openai import OpenAI

from backend.config import LOG_DIR, PRIMARY_MODEL, get_allowed_origins
from backend.models import AnalyzeRequest, AnalyzeResponse, ChatRequest, ChatResponse
from backend.services.openai_service import analyze_question
from backend.services.pdf_log import save_pdf_log


app = FastAPI(title="JAILA Backend API", version="1.0.0")

allowed_origins = get_allowed_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    if not os.getenv("OPENAI_API_KEY"):
        return {"status": "degraded", "reason": "OPENAI_API_KEY mangler"}
    return {"status": "ok"}


@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze(payload: AnalyzeRequest) -> AnalyzeResponse:
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Spørgsmål må ikke være tomt")
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY mangler på server")

    try:
        client = OpenAI()
        parsed, used_model, response_id = analyze_question(
            client, question, payload.previous_response_id
        )
        log_path = save_pdf_log(question, parsed, used_model)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Analyse fejlede: {exc}") from exc

    log_filename = log_path.name
    return AnalyzeResponse(
        answer=parsed.get("output_text", ""),
        used_model=used_model,
        response_id=response_id,
        citations=parsed.get("citations", []),
        retrieval_results=parsed.get("retrieved_chunks", []),
        log_pdf_filename=log_filename,
        log_pdf_url=f"/api/logs/{log_filename}",
    )


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Chatbesked må ikke være tom")
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY mangler på server")

    try:
        client = OpenAI()
        request_payload: dict[str, object] = {
            "model": PRIMARY_MODEL,
            "input": message,
            "reasoning": {"effort": "high"},
        }
        if payload.previous_response_id:
            request_payload["previous_response_id"] = payload.previous_response_id
        resp = client.responses.create(**request_payload)
        answer = str(getattr(resp, "output_text", "") or "").strip()
        response_id = str(getattr(resp, "id", "") or "")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chat fejlede: {exc}") from exc

    return ChatResponse(
        answer=answer or "Intet svar returneret.",
        used_model=PRIMARY_MODEL,
        response_id=response_id,
    )


@app.get("/api/logs/{filename}")
def get_log_file(filename: str) -> FileResponse:
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Kun PDF logs er tilladt")

    candidate = (LOG_DIR / filename).resolve()
    log_dir_resolved = LOG_DIR.resolve()

    # Avoid path traversal and ensure file stays in logs directory.
    if log_dir_resolved not in candidate.parents or not candidate.exists():
        raise HTTPException(status_code=404, detail="Logfil ikke fundet")

    return FileResponse(path=candidate, media_type="application/pdf", filename=filename)
