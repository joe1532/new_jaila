"""Valg mellem OpenAI og Grok til at skrive chatsvaret.

Søgning i vector stores sker altid via OpenAI. Grok har ikke file_search
mod JAILA's stores, så hits sendes ind som tekst.
"""

from __future__ import annotations

import os
from typing import Any

from openai import OpenAI

from backend.config import GROK_MODEL, XAI_BASE_URL

CHAT_PROVIDERS = ("openai", "grok")
MAX_HISTORY_TURNS = 8


def normalize_chat_provider(raw: str | None) -> str:
    value = str(raw or "openai").strip().lower()
    if value not in CHAT_PROVIDERS:
        raise ValueError("provider skal være openai eller grok")
    return value


def grok_client() -> OpenAI:
    key = str(os.getenv("XAI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("XAI_API_KEY mangler på server")
    return OpenAI(api_key=key, base_url=XAI_BASE_URL)


def grok_is_configured() -> bool:
    return bool(str(os.getenv("XAI_API_KEY") or "").strip())


def format_history_prefix(turns: list[Any] | None) -> str:
    """Grok har ikke OpenAIs previous_response_id, så fortiden sendes som tekst."""
    if not turns:
        return ""
    lines = ["[Tidligere samtale]"]
    kept = 0
    for item in list(turns)[-MAX_HISTORY_TURNS:]:
        if isinstance(item, dict):
            role = str(item.get("role") or "").strip().lower()
            text = str(item.get("text") or "").strip()
        else:
            role = str(getattr(item, "role", "") or "").strip().lower()
            text = str(getattr(item, "text", "") or "").strip()
        if not text or role not in {"user", "assistant"}:
            continue
        label = "Bruger" if role == "user" else "Assistent"
        lines.append(f"{label}:\n{text}")
        kept += 1
    if not kept:
        return ""
    lines.append("[/Tidligere samtale]")
    return "\n\n".join(lines)


def with_history(prefix: str, body: str) -> str:
    head = str(prefix or "").strip()
    tail = str(body or "").strip()
    if head and tail:
        return head + "\n\n" + tail
    return head or tail
