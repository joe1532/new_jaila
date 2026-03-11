"""
Persistent chat-logs per bruger.
Gemmer hele chatforløb pr. session-id, så samme chat kan åbnes igen.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from openai import OpenAI

from backend.config import ANALYSE_LOGS_DIR

TITLE_MODEL = "gpt-4o-mini"
TITLE_MAX_TOKENS = 30

_log = logging.getLogger(__name__)


def _sanitize_username(username: str) -> str:
    """Kun alfanumerisk og bindestreg."""
    return re.sub(r"[^\w\-]", "", (username or "").strip().lower()) or "default"


def _user_logs_path(username: str) -> Path:
    return ANALYSE_LOGS_DIR / f"{_sanitize_username(username)}_chat.json"


def _generate_title_from_messages(messages: list[dict]) -> str:
    """LLM genererer kort titel ud fra første brugerbesked."""
    first_user_text = ""
    for msg in messages or []:
        if str(msg.get("role", "")).strip().lower() == "user":
            first_user_text = str(msg.get("text", "")).strip()
            break
    if not first_user_text:
        return "Chat uden titel"
    try:
        client = OpenAI()
        resp = client.chat.completions.create(
            model=TITLE_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Du giver chatforløb en kort beskrivende titel på max 6-8 ord. "
                        "Returner KUN titlen, ingen forklaring."
                    ),
                },
                {"role": "user", "content": first_user_text[:500]},
            ],
            max_tokens=TITLE_MAX_TOKENS,
        )
        text = (resp.choices[0].message.content or "").strip()
        return text[:80] if text else first_user_text[:50] + ("…" if len(first_user_text) > 50 else "")
    except Exception as exc:
        _log.warning("Titel-generering for chat fejlede: %s", exc)
        return first_user_text[:50] + ("…" if len(first_user_text) > 50 else "")


def save_chat_log(
    username: str,
    session_id: str,
    messages: list[dict],
    used_model: str,
    last_response_id: str | None = None,
) -> dict:
    """
    Upsert chat-log for en session.
    Returnerer metadata til visning i liste.
    """
    username = _sanitize_username(username)
    clean_session_id = str(session_id or "").strip()
    if not clean_session_id:
        raise ValueError("session_id mangler")

    ANALYSE_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    path = _user_logs_path(username)
    now = datetime.now().isoformat(timespec="seconds")

    entries: list[dict] = []
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                entries = json.load(f)
        except (json.JSONDecodeError, OSError):
            entries = []

    normalized_messages = [
        {
            "role": str(msg.get("role", "")).strip(),
            "text": str(msg.get("text", "")).strip(),
        }
        for msg in (messages or [])
        if str(msg.get("text", "")).strip()
    ]
    if not normalized_messages:
        raise ValueError("messages er tom")

    existing_idx = next(
        (idx for idx, entry in enumerate(entries) if str(entry.get("session_id", "")).strip() == clean_session_id),
        None,
    )

    if existing_idx is None:
        entry = {
            "id": uuid4().hex[:12],
            "session_id": clean_session_id,
            "created_at": now,
            "updated_at": now,
            "title": _generate_title_from_messages(normalized_messages),
            "messages": normalized_messages,
            "used_model": str(used_model or "").strip(),
            "last_response_id": str(last_response_id or "").strip() or None,
        }
        entries.insert(0, entry)
    else:
        existing = entries.pop(existing_idx)
        existing["updated_at"] = now
        existing["messages"] = normalized_messages
        existing["used_model"] = str(used_model or existing.get("used_model", "")).strip()
        existing["last_response_id"] = str(last_response_id or "").strip() or existing.get("last_response_id")
        entry = existing
        entries.insert(0, entry)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

    return {
        "id": entry["id"],
        "session_id": entry["session_id"],
        "title": entry.get("title", "Chat uden titel"),
        "created_at": entry.get("created_at", now),
        "updated_at": entry.get("updated_at", now),
        "used_model": entry.get("used_model", ""),
    }


def list_chat_logs(username: str) -> list[dict]:
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
            "id": e.get("id", ""),
            "session_id": e.get("session_id", ""),
            "title": e.get("title", "Chat uden titel"),
            "created_at": e.get("created_at", ""),
            "updated_at": e.get("updated_at", e.get("created_at", "")),
            "used_model": e.get("used_model", ""),
        }
        for e in entries
        if e.get("id")
    ]


def get_chat_log(username: str, entry_id: str) -> dict | None:
    path = _user_logs_path(username)
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            entries = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    for entry in entries:
        if entry.get("id") == entry_id:
            return entry
    return None


def delete_chat_log(username: str, entry_id: str) -> bool:
    """Slet chat-log efter id. Returnerer True hvis slettet."""
    path = _user_logs_path(username)
    if not path.exists():
        return False
    try:
        with open(path, encoding="utf-8") as f:
            entries = json.load(f)
    except (json.JSONDecodeError, OSError):
        return False
    remaining = [entry for entry in entries if entry.get("id") != entry_id]
    if len(remaining) == len(entries):
        return False
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(remaining, f, ensure_ascii=False, indent=2)
    except OSError:
        return False
    return True
