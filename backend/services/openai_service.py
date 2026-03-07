import re
from typing import Any

from openai import OpenAI

from backend.config import (
    ANSWER_INSTRUCTIONS,
    FALLBACK_MODEL,
    MAX_NUM_RESULTS,
    PRIMARY_MODEL,
    VECTOR_STORE_IDS,
)


def get_value(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def parse_response(resp: Any) -> dict[str, Any]:
    output_text = get_value(resp, "output_text", "") or ""
    output_items = get_value(resp, "output", []) or []

    citations: list[dict[str, str]] = []
    retrieved_chunks: list[dict[str, str]] = []

    for item in output_items:
        item_type = get_value(item, "type", "")

        if item_type == "message":
            for content in get_value(item, "content", []) or []:
                if get_value(content, "type", "") != "output_text":
                    continue
                for annotation in get_value(content, "annotations", []) or []:
                    if get_value(annotation, "type", "") == "file_citation":
                        citations.append(
                            {
                                "file_id": str(get_value(annotation, "file_id", "")),
                                "filename": str(get_value(annotation, "filename", "")),
                            }
                        )

        if item_type == "file_search_call":
            for result in get_value(item, "results", []) or []:
                chunk_text = str(get_value(result, "text", "")).strip()
                if not chunk_text:
                    for part in get_value(result, "content", []) or []:
                        if get_value(part, "type", "") == "text":
                            text_part = str(get_value(part, "text", "")).strip()
                            if text_part:
                                chunk_text = text_part
                                break

                retrieved_chunks.append(
                    {
                        "filename": str(get_value(result, "filename", "")),
                        "score": str(get_value(result, "score", "")),
                        "text": chunk_text,
                    }
                )

    seen: set[tuple[str, str]] = set()
    unique_citations: list[dict[str, str]] = []
    for citation in citations:
        key = (citation["file_id"], citation["filename"])
        if key in seen:
            continue
        seen.add(key)
        unique_citations.append(citation)

    return {
        "output_text": output_text.strip(),
        "citations": unique_citations,
        "retrieved_chunks": retrieved_chunks,
    }


def extract_legal_references(chunks: list[dict[str, str]]) -> list[str]:
    references: list[str] = []
    seen: set[str] = set()
    patterns = [
        r"(?:ligningsloven|ligningslovens)\s*§+\s*\d+\s*[A-Za-z]?",
        r"(?:kildeskatteloven|kildeskattelovens)\s*§+\s*\d+\s*[A-Za-z]?",
        r"(?:personskatteloven|personskattelovens)\s*§+\s*\d+\s*[A-Za-z]?",
        r"(?:pensionsbeskatningsloven|PBL)\s*§+\s*\d+\s*[A-Za-z]?",
        r"\bSKM\s*\d{4}\s*\d+\s*[A-ZÆØÅ]{2,5}\b",
    ]

    for chunk in chunks:
        text = chunk.get("text", "") or ""
        for pattern in patterns:
            for match in re.findall(pattern, text, flags=re.IGNORECASE):
                normalized = re.sub(r"\s+", " ", match).strip()
                key = normalized.lower()
                if key in seen:
                    continue
                seen.add(key)
                references.append(normalized)
                if len(references) >= 12:
                    return references
    return references


def ensure_sources_section(parsed: dict[str, Any]) -> dict[str, Any]:
    output_text = (parsed.get("output_text", "") or "").strip()
    if "anvendte kilder/love" in output_text.lower():
        return parsed

    lines: list[str] = []
    for citation in parsed.get("citations", []) or []:
        filename = citation.get("filename", "").strip()
        if filename:
            lines.append(f"- Kilde: {filename}")

    for ref in extract_legal_references(parsed.get("retrieved_chunks", []) or []):
        lines.append(f"- Lov/praksis: {ref}")

    if not lines:
        lines.append("- Ingen eksplicitte kilder/love kunne udledes automatisk.")

    parsed["output_text"] = output_text + "\n\nAnvendte kilder/love\n" + "\n".join(lines)
    return parsed


def analyze_question(client: OpenAI, question: str) -> tuple[dict[str, Any], str]:
    models_to_try = [PRIMARY_MODEL, FALLBACK_MODEL]
    last_error: Exception | None = None

    for model in models_to_try:
        try:
            resp = client.responses.create(
                model=model,
                instructions=ANSWER_INSTRUCTIONS,
                input=question,
                reasoning={"effort": "high"},
                tools=[
                    {
                        "type": "file_search",
                        "vector_store_ids": VECTOR_STORE_IDS,
                        "max_num_results": MAX_NUM_RESULTS,
                    }
                ],
                include=["file_search_call.results"],
            )
            parsed = ensure_sources_section(parse_response(resp))
            return parsed, model
        except Exception as exc:
            last_error = exc

    raise RuntimeError(
        f"Kald fejlede for modellerne {PRIMARY_MODEL} og {FALLBACK_MODEL}: {last_error}"
    )
