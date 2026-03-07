import base64
import io
import json
import os
import re
from pathlib import Path
from uuid import uuid4

import fitz
import openpyxl
import xlrd
from docx import Document
from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from openai import OpenAI
from pypdf import PdfReader

from backend.config import BASE_DIR, CHAT_INSTRUCTIONS, LOG_DIR, PRIMARY_MODEL, get_allowed_origins
from backend.models import (
    AnalyzeRequest,
    AnalyzeResponse,
    ChatContextFileResponse,
    ChatContextListResponse,
    ChatExportRequest,
    ChatExportResponse,
    ChatRequest,
    ChatResponse,
)
from backend.services.openai_service import analyze_question
from backend.services.pdf_log import save_chat_pdf_log, save_pdf_log


app = FastAPI(title="JAILA Backend API", version="1.0.0")
CHAT_CONTEXT_DIR = BASE_DIR / "chat_context"
DEFAULT_CHAT_GUIDE_PATH = BASE_DIR / "backend" / "default_context" / "Skriveguide.md"
MAX_CHAT_CONTEXT_CHARS = 20000
MAX_CHAT_CONTEXT_PER_FILE_CHARS = 30000
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_PDF_PAGES = 20
MAX_PDF_OCR_PAGES = 8
MIN_PDF_PAGE_TEXT_FOR_NO_OCR = 40
MAX_DOCX_PARAGRAPHS = 1200
MAX_EXCEL_SHEETS = 10
MAX_EXCEL_ROWS_PER_SHEET = 400

allowed_origins = get_allowed_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    if not os.getenv("OPENAI_API_KEY"):
        return {"status": "degraded", "reason": "OPENAI_API_KEY mangler"}
    return {"status": "ok"}


def sanitize_filename(filename: str) -> str:
    cleaned = re.sub(r"[^\w.\-]+", "_", filename.strip(), flags=re.UNICODE)
    cleaned = cleaned.strip("._")
    return cleaned or "context.txt"


def normalize_text(text: str) -> str:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = cleaned.strip()
    return cleaned


def truncate_text(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars] + "\n\n[NOTE: Indhold afkortet pga. længde.]", True


def get_session_id(raw_session_id: str | None) -> str:
    session_id = (raw_session_id or "").strip()
    if not re.fullmatch(r"[a-zA-Z0-9_-]{8,80}", session_id):
        raise HTTPException(status_code=400, detail="Ugyldigt eller manglende chat_session_id")
    return session_id


def get_session_dir(session_id: str) -> Path:
    return CHAT_CONTEXT_DIR / session_id


def context_text_path(session_dir: Path, context_id: str) -> Path:
    return session_dir / f"{context_id}.txt"


def context_meta_path(session_dir: Path, context_id: str) -> Path:
    return session_dir / f"{context_id}.json"


def default_seed_marker_path(session_dir: Path) -> Path:
    return session_dir / ".default_seeded"


def list_chat_context_ids(session_id: str) -> list[str]:
    session_dir = get_session_dir(session_id)
    if not session_dir.exists():
        return []
    ids = [p.stem for p in session_dir.glob("*.json") if p.is_file()]
    ids.sort(
        key=lambda context_id: context_meta_path(session_dir, context_id).stat().st_mtime,
        reverse=True,
    )
    return ids


def load_context_meta(session_dir: Path, context_id: str) -> dict:
    meta_path = context_meta_path(session_dir, context_id)
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def ensure_default_guide_context_for_session(session_id: str) -> None:
    session_dir = get_session_dir(session_id)
    session_dir.mkdir(parents=True, exist_ok=True)
    marker_path = default_seed_marker_path(session_dir)
    if marker_path.exists():
        return

    if not DEFAULT_CHAT_GUIDE_PATH.exists():
        try:
            marker_path.write_text("missing_default_guide", encoding="utf-8")
        except Exception:
            pass
        return

    try:
        guide_text = normalize_text(DEFAULT_CHAT_GUIDE_PATH.read_text(encoding="utf-8"))
    except Exception:
        try:
            marker_path.write_text("default_guide_read_error", encoding="utf-8")
        except Exception:
            pass
        return

    if not guide_text:
        try:
            marker_path.write_text("default_guide_empty", encoding="utf-8")
        except Exception:
            pass
        return

    guide_text, was_truncated = truncate_text(guide_text, MAX_CHAT_CONTEXT_PER_FILE_CHARS)
    context_id = uuid4().hex
    context_text_path(session_dir, context_id).write_text(guide_text, encoding="utf-8")
    note = "Default skriveguide indlæst automatisk ved ny session"
    if was_truncated:
        note += ". Indhold blev afkortet."
    metadata = {
        "context_id": context_id,
        "filename": "Skriveguide.md",
        "file_type": "tekst",
        "size_chars": len(guide_text),
        "extraction_note": note,
    }
    context_meta_path(session_dir, context_id).write_text(
        json.dumps(metadata, ensure_ascii=False),
        encoding="utf-8",
    )
    try:
        marker_path.write_text("default_seeded", encoding="utf-8")
    except Exception:
        pass


def build_chat_context_list_response(session_id: str) -> ChatContextListResponse:
    ensure_default_guide_context_for_session(session_id)
    session_dir = get_session_dir(session_id)
    files: list[ChatContextFileResponse] = []
    for context_id in list_chat_context_ids(session_id):
        meta = load_context_meta(session_dir, context_id)
        filename = str(meta.get("filename", "ukendt_fil"))
        file_type = str(meta.get("file_type", "ukendt"))
        extraction_note = str(meta.get("extraction_note", "")).strip() or None
        size_chars = int(meta.get("size_chars", 0) or 0)
        files.append(
            ChatContextFileResponse(
                context_id=context_id,
                filename=filename,
                file_type=file_type,
                size_chars=size_chars,
                extraction_note=extraction_note,
            )
        )
    return ChatContextListResponse(files=files)


def load_chat_context_text(session_id: str) -> str:
    ensure_default_guide_context_for_session(session_id)
    session_dir = get_session_dir(session_id)
    context_ids = list_chat_context_ids(session_id)
    if not context_ids:
        return ""
    blocks: list[str] = []
    total_chars = 0
    for context_id in context_ids:
        meta = load_context_meta(session_dir, context_id)
        filename = str(meta.get("filename", "ukendt_fil"))
        file_type = str(meta.get("file_type", "ukendt"))
        try:
            text = context_text_path(session_dir, context_id).read_text(encoding="utf-8").strip()
        except Exception:
            continue
        if not text:
            continue
        block = f"[Kontekstfil: {filename} | type: {file_type}]\n{text}\n"
        remaining = MAX_CHAT_CONTEXT_CHARS - total_chars
        if remaining <= 0:
            break
        if len(block) > remaining:
            block = block[:remaining] + "\n[NOTE: Kontekst afkortet pga. længde]\n"
        blocks.append(block)
        total_chars += len(block)
        if total_chars >= MAX_CHAT_CONTEXT_CHARS:
            break
    return "\n".join(blocks).strip()


def ocr_image_bytes_with_openai(client: OpenAI, image_bytes: bytes, mime_type: str) -> str:
    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    response = client.responses.create(
        model=PRIMARY_MODEL,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Du udfører OCR. Returner kun den udlæste tekst, "
                            "bevar linjeskift, og opfind ikke manglende tekst."
                        ),
                    },
                    {"type": "input_image", "image_url": f"data:{mime_type};base64,{image_b64}"},
                ],
            }
        ],
        reasoning={"effort": "medium"},
    )
    return normalize_text(str(getattr(response, "output_text", "") or ""))


def get_openai_client_for_ocr(existing_client: OpenAI | None) -> OpenAI:
    if existing_client is not None:
        return existing_client
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=500,
            detail="OPENAI_API_KEY mangler på server (kræves til OCR af billeder/scannede PDF'er)",
        )
    return OpenAI()


def extract_docx_text(data: bytes) -> tuple[str, str]:
    document = Document(io.BytesIO(data))
    lines: list[str] = []
    paragraph_count = 0
    for para in document.paragraphs:
        text = normalize_text(para.text)
        if text:
            lines.append(text)
            paragraph_count += 1
            if paragraph_count >= MAX_DOCX_PARAGRAPHS:
                break
    for table in document.tables:
        for row in table.rows:
            row_values = [normalize_text(cell.text) for cell in row.cells]
            row_values = [value for value in row_values if value]
            if row_values:
                lines.append(" | ".join(row_values))
    return "\n".join(lines).strip(), "DOCX udtrukket fra afsnit/tabeller"


def extract_excel_text(data: bytes, ext: str) -> tuple[str, str]:
    lines: list[str] = []
    sheets_processed = 0
    rows_processed = 0
    if ext == ".xlsx":
        workbook = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
        for sheet in workbook.worksheets[:MAX_EXCEL_SHEETS]:
            sheets_processed += 1
            lines.append(f"[Ark: {sheet.title}]")
            row_count = 0
            for row in sheet.iter_rows(values_only=True):
                if row_count >= MAX_EXCEL_ROWS_PER_SHEET:
                    lines.append("[NOTE: Flere rækker er afkortet]")
                    break
                values = [str(value).strip() for value in row if value is not None and str(value).strip()]
                if not values:
                    continue
                lines.append(" | ".join(values))
                row_count += 1
                rows_processed += 1
    else:
        workbook = xlrd.open_workbook(file_contents=data)
        for sheet in workbook.sheets()[:MAX_EXCEL_SHEETS]:
            sheets_processed += 1
            lines.append(f"[Ark: {sheet.name}]")
            row_count = 0
            for row_idx in range(sheet.nrows):
                if row_count >= MAX_EXCEL_ROWS_PER_SHEET:
                    lines.append("[NOTE: Flere rækker er afkortet]")
                    break
                row_values = [
                    str(sheet.cell_value(row_idx, col_idx)).strip()
                    for col_idx in range(sheet.ncols)
                    if str(sheet.cell_value(row_idx, col_idx)).strip()
                ]
                if not row_values:
                    continue
                lines.append(" | ".join(row_values))
                row_count += 1
                rows_processed += 1
    note = f"Excel udtrukket fra {sheets_processed} ark og {rows_processed} rækker"
    return "\n".join(lines).strip(), note


def extract_pdf_text_with_ocr(client: OpenAI | None, data: bytes) -> tuple[str, str]:
    pages: list[str] = []
    ocr_pages = 0
    processed_pages = 0

    try:
        reader = PdfReader(io.BytesIO(data))
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"PDF kunne ikke læses: {exc}") from exc

    page_count = min(len(reader.pages), doc.page_count, MAX_PDF_PAGES)
    for idx in range(page_count):
        processed_pages += 1
        page_text = normalize_text(reader.pages[idx].extract_text() or "")
        if len(page_text) >= MIN_PDF_PAGE_TEXT_FOR_NO_OCR:
            pages.append(f"[Side {idx + 1}]\n{page_text}")
            continue

        if ocr_pages >= MAX_PDF_OCR_PAGES:
            if page_text:
                pages.append(f"[Side {idx + 1}]\n{page_text}")
            continue

        pdf_page = doc.load_page(idx)
        pixmap = pdf_page.get_pixmap(matrix=fitz.Matrix(1.8, 1.8), alpha=False)
        image_bytes = pixmap.tobytes("png")
        try:
            ocr_client = get_openai_client_for_ocr(client)
            ocr_text = ocr_image_bytes_with_openai(ocr_client, image_bytes, "image/png")
        except HTTPException:
            ocr_text = ""
        if ocr_text:
            ocr_pages += 1
            pages.append(f"[Side {idx + 1} OCR]\n{ocr_text}")
        elif page_text:
            pages.append(f"[Side {idx + 1}]\n{page_text}")

    note = f"PDF behandlet: {processed_pages} sider, OCR anvendt på {ocr_pages} sider"
    return "\n\n".join(pages).strip(), note


def extract_context_text(client: OpenAI | None, filename: str, ext: str, data: bytes) -> tuple[str, str, str]:
    if ext in {".md", ".txt"}:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="Tekstfilen skal være UTF-8") from exc
        return normalize_text(text), "tekst", "Tekstfil indlæst"

    if ext in {".png", ".jpg", ".jpeg", ".webp"}:
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }
        ocr_client = get_openai_client_for_ocr(client)
        text = ocr_image_bytes_with_openai(ocr_client, data, mime_map[ext])
        return text, "billede", "OCR udført via OpenAI vision"

    if ext == ".docx":
        text, note = extract_docx_text(data)
        return text, "word", note

    if ext in {".xlsx", ".xls"}:
        text, note = extract_excel_text(data, ext)
        return text, "excel", note

    if ext == ".pdf":
        text, note = extract_pdf_text_with_ocr(client, data)
        return text, "pdf", note

    raise HTTPException(status_code=400, detail="Filtype understøttes ikke")


@app.get("/api/chat/context", response_model=ChatContextListResponse)
def chat_context_list(
    x_chat_session_id: str | None = Header(default=None, alias="X-Chat-Session-Id"),
) -> ChatContextListResponse:
    session_id = get_session_id(x_chat_session_id)
    return build_chat_context_list_response(session_id)


@app.post("/api/chat/context", response_model=ChatContextListResponse)
async def upload_chat_context(
    file: UploadFile = File(...),
    x_chat_session_id: str | None = Header(default=None, alias="X-Chat-Session-Id"),
) -> ChatContextListResponse:
    session_id = get_session_id(x_chat_session_id)
    filename = file.filename or "context.txt"
    ext = Path(filename).suffix.lower()
    allowed_ext = {".md", ".txt", ".png", ".jpg", ".jpeg", ".webp", ".docx", ".pdf", ".xlsx", ".xls"}
    if ext not in allowed_ext:
        raise HTTPException(status_code=400, detail="Filtype ikke tilladt")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Filen er tom")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Filen er for stor")

    extracted_text, file_type, note = extract_context_text(None, filename, ext, data)
    if not extracted_text:
        raise HTTPException(status_code=400, detail="Kunne ikke udtrække brugbar tekst fra filen")

    extracted_text = normalize_text(extracted_text)
    extracted_text, was_truncated = truncate_text(extracted_text, MAX_CHAT_CONTEXT_PER_FILE_CHARS)
    if was_truncated:
        note = f"{note}. Indhold blev afkortet."

    CHAT_CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
    session_dir = get_session_dir(session_id)
    session_dir.mkdir(parents=True, exist_ok=True)

    context_id = uuid4().hex
    context_text_path(session_dir, context_id).write_text(extracted_text, encoding="utf-8")
    metadata = {
        "context_id": context_id,
        "filename": filename,
        "file_type": file_type,
        "size_chars": len(extracted_text),
        "extraction_note": note,
    }
    context_meta_path(session_dir, context_id).write_text(
        json.dumps(metadata, ensure_ascii=False),
        encoding="utf-8",
    )
    return build_chat_context_list_response(session_id)


@app.delete("/api/chat/context/{context_id}", response_model=ChatContextListResponse)
def delete_chat_context(
    context_id: str,
    x_chat_session_id: str | None = Header(default=None, alias="X-Chat-Session-Id"),
) -> ChatContextListResponse:
    session_id = get_session_id(x_chat_session_id)
    if not re.fullmatch(r"[a-f0-9]{32}", context_id):
        raise HTTPException(status_code=400, detail="Ugyldigt context_id")
    session_dir = get_session_dir(session_id)
    text_file = context_text_path(session_dir, context_id)
    meta_file = context_meta_path(session_dir, context_id)
    if not text_file.exists() and not meta_file.exists():
        raise HTTPException(status_code=404, detail="Kontekstfil ikke fundet")
    try:
        if text_file.exists():
            text_file.unlink()
        if meta_file.exists():
            meta_file.unlink()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Kunne ikke fjerne kontekstfil: {exc}") from exc
    return build_chat_context_list_response(session_id)


@app.delete("/api/chat/context", response_model=ChatContextListResponse)
def clear_chat_context(
    x_chat_session_id: str | None = Header(default=None, alias="X-Chat-Session-Id"),
) -> ChatContextListResponse:
    session_id = get_session_id(x_chat_session_id)
    session_dir = get_session_dir(session_id)
    if session_dir.exists():
        for path in session_dir.glob("*"):
            if path.is_file():
                try:
                    path.unlink()
                except Exception:
                    continue
    return build_chat_context_list_response(session_id)


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
def chat(
    payload: ChatRequest,
    x_chat_session_id: str | None = Header(default=None, alias="X-Chat-Session-Id"),
) -> ChatResponse:
    session_id = get_session_id(x_chat_session_id)
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Chatbesked må ikke være tom")
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY mangler på server")

    try:
        client = OpenAI()
        context_text = load_chat_context_text(session_id)
        chat_instructions = CHAT_INSTRUCTIONS
        if context_text:
            chat_instructions = (
                CHAT_INSTRUCTIONS
                + "\n\nYderligere uploadet kontekst til chat (skal anvendes i samspil med ovenstående):\n"
                + context_text
            )

        request_payload: dict[str, object] = {
            "model": PRIMARY_MODEL,
            "instructions": chat_instructions,
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


@app.post("/api/chat/export-pdf", response_model=ChatExportResponse)
def export_chat_pdf(
    payload: ChatExportRequest,
    x_chat_session_id: str | None = Header(default=None, alias="X-Chat-Session-Id"),
) -> ChatExportResponse:
    get_session_id(x_chat_session_id)
    messages = [
        {"role": msg.role.strip(), "text": msg.text.strip()}
        for msg in payload.messages
        if msg.text.strip()
    ]
    if not messages:
        raise HTTPException(status_code=400, detail="Der er ingen chatbeskeder at gemme")

    try:
        log_path = save_chat_pdf_log(messages, PRIMARY_MODEL)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Kunne ikke gemme chat-PDF: {exc}") from exc

    log_filename = log_path.name
    return ChatExportResponse(
        log_pdf_filename=log_filename,
        log_pdf_url=f"/api/logs/{log_filename}",
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
