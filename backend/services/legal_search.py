"""Retrieval-only search shared by remote interfaces.

This module deliberately does not import the FastAPI application or generate
an LLM answer. Keeping retrieval independent lets the MCP service run in a
separate process without coupling its lifecycle to the main JAILA backend.
"""

from __future__ import annotations

from typing import Any

from openai import OpenAI

from backend.config import VECTOR_STORE_IDS


MAX_QUERY_CHARS = 4_000
MAX_RESULTS = 20
MAX_VECTOR_STORES = 2


def _value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _result_text(result: Any) -> str:
    parts: list[str] = []
    for content in _value(result, "content", []) or []:
        if _value(content, "type", "") != "text":
            continue
        text = str(_value(content, "text", "") or "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts)


def search_legal_sources(
    client: OpenAI,
    query: str,
    max_results: int = 8,
    vector_store_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Search JAILA's vector stores without asking a model to write an answer."""
    clean_query = str(query or "").strip()
    if not clean_query:
        raise ValueError("Søgeforespørgslen må ikke være tom")
    if len(clean_query) > MAX_QUERY_CHARS:
        raise ValueError(f"Søgeforespørgslen må højst være {MAX_QUERY_CHARS} tegn")
    if not 1 <= max_results <= MAX_RESULTS:
        raise ValueError(f"max_results skal være mellem 1 og {MAX_RESULTS}")

    stores = [
        str(store_id).strip()
        for store_id in (vector_store_ids or VECTOR_STORE_IDS)
        if str(store_id).strip()
    ][:MAX_VECTOR_STORES]
    if not stores:
        raise RuntimeError("Ingen vector stores er konfigureret")

    results: list[dict[str, Any]] = []
    failures: list[str] = []
    for store_id in stores:
        try:
            page = client.vector_stores.search(
                vector_store_id=store_id,
                query=clean_query,
                max_num_results=max_results,
                rewrite_query=True,
            )
        except Exception:
            # Do not expose provider details or credentials through the MCP tool.
            failures.append(store_id)
            continue

        for item in page:
            text = _result_text(item)
            if not text:
                continue
            results.append(
                {
                    "file_id": str(_value(item, "file_id", "") or ""),
                    "filename": str(_value(item, "filename", "") or ""),
                    "score": float(_value(item, "score", 0.0) or 0.0),
                    "text": text,
                    "attributes": _value(item, "attributes", None) or {},
                }
            )

    if failures and len(failures) == len(stores):
        raise RuntimeError("Søgning i retskilderne fejlede")

    results.sort(key=lambda item: item["score"], reverse=True)
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in results:
        key = (item["file_id"], item["text"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
        if len(unique) >= max_results:
            break
    return unique
