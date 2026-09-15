"""API-nøgle. Læses kun fra OPENAI_API_KEY. Aldrig logget."""

from __future__ import annotations

import os

from backend.db.migrate import load_env
from backend.db.skat_embed.errors import MissingApiKeyError

_KEY_ENV = "OPENAI_API_KEY"


def openai_api_key() -> str:
    load_env()
    value = os.getenv(_KEY_ENV)
    if not value or not value.strip():
        raise MissingApiKeyError("OPENAI_API_KEY mangler")
    return value.strip()


def redact_secrets(text: str) -> str:
    """Fjern nøgle-lignende tokens fra logtekst."""
    key = os.getenv(_KEY_ENV) or ""
    redacted = text
    if key:
        redacted = redacted.replace(key, "***")
    if "sk-" in redacted:
        parts = []
        for token in redacted.split():
            if token.startswith("sk-") and len(token) > 8:
                parts.append("sk-***")
            else:
                parts.append(token)
        redacted = " ".join(parts)
    return redacted
