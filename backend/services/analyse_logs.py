"""
Persistent analyse-logs per bruger. Gemmer fuldt PDF-ækvivalent indhold.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from openai import OpenAI

from backend.config import ANALYSE_LOGS_DIR, VECTOR_STORE_IDS

TITLE_MODEL = "gpt-4o-mini"
TITLE_MAX_TOKENS = 30

_log = logging.getLogger(__name__)


def _sanitize_username(username: str) -> str:
    """Kun alfanumerisk og bindestreg."""
    return re.sub(r"[^\w\-]", "", (username or "").strip().lower()) or "default"


def _user_logs_path(username: str) -> Path:
    return ANALYSE_LOGS_DIR / f"{_sanitize_username(username)}.json"


def _generate_title_from_question(question: str) -> str:
    """LLM genererer kort beskrivende navn fra spørgsmålet."""
    if not question or not question.strip():
        return "Uden titel"
    try:
        client = OpenAI()
        resp = client.chat.completions.create(
            model=TITLE_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Du giver juridiske spørgsmål et kort beskrivende navn på max 6-8 ord. Returner KUN navnet, ingen forklaring.",
                },
                {"role": "user", "content": question.strip()[:500]},
            ],
            max_tokens=TITLE_MAX_TOKENS,
        )
        text = (resp.choices[0].message.content or "").strip()
        return text[:80] if text else question[:50] + ("…" if len(question) > 50 else "")
    except Exception as e:
        _log.warning("Titel-generering fejlede: %s", e)
        return question[:50] + ("…" if len(question) > 50 else "")


def save_analyse_log(
    username: str,
    session_id: str | None,
    question: str,
    answer: str,
    citations: list[dict],
    retrieval_results: list[dict],
    used_model: str,
    log_question: str | None = None,
    used_vector_store_ids: list[str] | None = None,
    log_pdf_filename: str | None = None,
    log_pdf_url: str | None = None,
    messages: list[dict] | None = None,
    last_response_id: str | None = None,
) -> dict:
    """
    Gem en analyse-log. Genererer titel via LLM fra spørgsmålet.
    Returnerer { id, title, created_at }.
    """
    username = _sanitize_username(username)
    ANALYSE_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    path = _user_logs_path(username)

    clean_session_id = str(session_id or "").strip() or None
    created_at = datetime.now().isoformat(timespec="seconds")

    entries: list[dict] = []
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                entries = json.load(f)
        except (json.JSONDecodeError, OSError):
            entries = []

    existing_idx: int | None = None
    if clean_session_id:
        existing_idx = next(
            (
                idx
                for idx, existing in enumerate(entries)
                if str(existing.get("session_id", "")).strip() == clean_session_id
            ),
            None,
        )

    if existing_idx is not None:
        existing = entries.pop(existing_idx)
        existing["question"] = question
        existing["answer"] = answer
        existing["citations"] = citations
        existing["retrieval_results"] = retrieval_results
        existing["used_model"] = used_model
        existing["log_question"] = log_question or question
        existing["used_vector_store_ids"] = used_vector_store_ids or list(VECTOR_STORE_IDS)
        existing["log_pdf_filename"] = (log_pdf_filename or "").strip() or None
        existing["log_pdf_url"] = (log_pdf_url or "").strip() or None
        existing["session_id"] = clean_session_id
        existing["messages"] = messages or existing.get("messages", [])
        existing["last_response_id"] = str(last_response_id or "").strip() or existing.get("last_response_id")
        entry = existing
    else:
        title = _generate_title_from_question(question)
        entry = {
            "id": uuid4().hex[:12],
            "created_at": created_at,
            "title": title,
            "question": question,
            "answer": answer,
            "citations": citations,
            "retrieval_results": retrieval_results,
            "used_model": used_model,
            "log_question": log_question or question,
            "used_vector_store_ids": used_vector_store_ids or list(VECTOR_STORE_IDS),
            "log_pdf_filename": (log_pdf_filename or "").strip() or None,
            "log_pdf_url": (log_pdf_url or "").strip() or None,
            "session_id": clean_session_id,
            "messages": messages or [],
            "last_response_id": str(last_response_id or "").strip() or None,
        }
    entries.insert(0, entry)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

    return {
        "id": entry.get("id", ""),
        "title": entry.get("title", "Uden titel"),
        "created_at": entry.get("created_at", created_at),
        "log_pdf_filename": entry.get("log_pdf_filename"),
        "log_pdf_url": entry.get("log_pdf_url"),
    }


def list_analyse_logs(username: str) -> list[dict]:
    """Liste af log-entries: { id, created_at, title }."""
    path = _user_logs_path(username)
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            entries = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    return [
        {
            "id": e["id"],
            "created_at": e["created_at"],
            "title": e.get("title", "Uden titel"),
            "log_pdf_filename": e.get("log_pdf_filename"),
            "log_pdf_url": e.get("log_pdf_url"),
        }
        for e in entries
    ]


def get_analyse_log(username: str, entry_id: str) -> dict | None:
    """Hent fuld log-entry efter id."""
    path = _user_logs_path(username)
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            entries = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    for e in entries:
        if e.get("id") == entry_id:
            return e
    return None


def delete_analyse_log(username: str, entry_id: str) -> bool:
    """Slet log-entry efter id. Returnerer True hvis slettet."""
    path = _user_logs_path(username)
    if not path.exists():
        return False
    try:
        with open(path, encoding="utf-8") as f:
            entries = json.load(f)
    except (json.JSONDecodeError, OSError):
        return False
    remaining = [e for e in entries if e.get("id") != entry_id]
    if len(remaining) == len(entries):
        return False
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(remaining, f, ensure_ascii=False, indent=2)
    except OSError:
        return False
    return True


def format_log_as_text(entry: dict) -> str:
    """Formatér log-entry som læsbar tekst (PDF-ækvivalent)."""
    lines = []
    lines.append("Juridisk forespørgselslog")
    lines.append(f"Tidspunkt: {entry.get('created_at', '')}")
    lines.append(f"Model brugt: {entry.get('used_model', '')}")
    vs = entry.get("used_vector_store_ids") or []
    lines.append(f"Vector stores: {', '.join(vs)}")
    lines.append("")
    lines.append("─── Spørgsmål ───")
    lines.append(entry.get("question", ""))
    lines.append("")
    lines.append("─── Svar ───")
    lines.append(entry.get("answer", "(Tomt svar)"))
    lines.append("")
    lines.append("─── Kilder (citations) ───")
    for i, c in enumerate(entry.get("citations") or [], 1):
        fn = c.get("filename", c.get("file_id", "?"))
        lines.append(f"  {i}. {fn}")
    lines.append("")
    lines.append("─── Retrieval-træf ───")
    for i, r in enumerate((entry.get("retrieval_results") or [])[:10], 1):
        fn = r.get("filename", "?")
        txt = (r.get("text") or "")[:100].replace("\n", " ")
        lines.append(f"  {i}. {fn}: {txt}…")
    return "\n".join(lines)
