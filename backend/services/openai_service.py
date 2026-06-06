import logging
import re
import time
import unicodedata
from typing import Any

from openai import OpenAI

from backend.services.pdf_log import save_pdf_log

from backend.config import (
    ANSWER_INSTRUCTIONS,
    FALLBACK_MODEL,
    MAX_NUM_RESULTS,
    PRIMARY_MODEL,
    PROMPT_CACHE_KEY_ANALYSE,
    PROMPT_CACHE_RETENTION,
    REASONING_EFFORT_ANALYSE,
    STRICT_SOURCING,
    VECTOR_STORE_IDS,
)

MAX_VECTOR_STORES_PER_REQUEST = 2
_log = logging.getLogger(__name__)


def _log_performance(
    flow: str,
    model: str,
    duration_ms: float,
    resp: Any,
    reasoning_effort: str,
    num_retrieval_results: int = 0,
) -> None:
    """Log performance data for debugging og optimering."""
    usage = get_value(resp, "usage")
    input_tokens = get_value(usage, "input_tokens", 0) if usage else 0
    output_tokens = get_value(usage, "output_tokens", 0) if usage else 0
    cached_tokens = 0
    if usage:
        details = get_value(usage, "prompt_tokens_details")
        if isinstance(details, dict):
            cached_tokens = details.get("cached_tokens", 0)
    request_id = getattr(resp, "_request_id", None) or getattr(resp, "request_id", None)
    processing_ms = getattr(resp, "_headers", None)
    if processing_ms and hasattr(processing_ms, "get"):
        processing_ms = processing_ms.get("openai-processing-ms")
    else:
        processing_ms = None
    _log.info(
        "perf flow=%s model=%s duration_ms=%.0f openai_processing_ms=%s x_request_id=%s "
        "input_tokens=%s output_tokens=%s cached_tokens=%s reasoning_effort=%s retrieval_results=%s",
        flow,
        model,
        duration_ms,
        processing_ms or "?",
        request_id or "?",
        input_tokens,
        output_tokens,
        cached_tokens,
        reasoning_effort,
        num_retrieval_results,
    )


def get_value(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def select_vector_store_ids_for_query(
    client: OpenAI,
    question: str,
    vector_store_ids: list[str],
) -> list[str]:
    """
    Respect API constraint: max 2 vector stores in file_search tools call.
    Probe search er fjernet for at undgå ekstra OpenAI-kald.
    """
    _ = client
    _ = question
    return vector_store_ids[:MAX_VECTOR_STORES_PER_REQUEST]


def normalize_mojibake_text(text: str) -> str:
    """Repair common UTF-8/latin1 mojibake such as Ã¸, Ã¦, Ã¥."""
    if not text:
        return text
    if not any(marker in text for marker in ("Ã", "Â", "â")):
        return text

    candidates = [text]

    try:
        candidates.append(text.encode("latin1").decode("utf-8"))
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass

    try:
        candidates.append(text.encode("cp1252").decode("utf-8"))
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass

    def mojibake_score(value: str) -> int:
        return value.count("Ã") + value.count("Â") + value.count("â")

    best = min(candidates, key=mojibake_score)
    return unicodedata.normalize("NFC", best)


def clean_answer_text(text: str) -> str:
    """Remove raw inline filecite markers from model output text."""
    cleaned = re.sub(r"filecite.*?", "", text, flags=re.DOTALL)
    # Remove markdown quote markers at line start.
    cleaned = re.sub(r"(?m)^\s*>\s?", "", cleaned)
    # Remove markdown bold markers because they add no legal value in output.
    cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned, flags=re.DOTALL)
    cleaned = cleaned.replace("**", "")
    cleaned = re.sub(
        r"(?i)\bkarnov[-\s]*noter?\b",
        "Note til relevant lovbestemmelse",
        cleaned,
    )
    # Use lowercase "note til" when it appears mid-sentence.
    cleaned = re.sub(
        r"(?<=[A-Za-zÆØÅæøå0-9])\s+Note(\s*\(\d{2,4}\))?\s+til\b",
        lambda m: f" note{m.group(1) or ''} til",
        cleaned,
    )
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = normalize_mojibake_text(cleaned)
    cleaned = unicodedata.normalize("NFC", cleaned)
    return cleaned.strip()


def parse_response(resp: Any) -> dict[str, Any]:
    output_text = get_value(resp, "output_text", "") or ""
    output_text = clean_answer_text(output_text)
    output_items = get_value(resp, "output", []) or []

    citations: list[dict[str, str]] = []
    retrieved_chunks: list[dict[str, str]] = []
    retrieved_sources: list[dict[str, str]] = []
    retrieved_source_seen: set[tuple[str, str]] = set()

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
                                "filename": normalize_mojibake_text(
                                    str(get_value(annotation, "filename", ""))
                                ),
                            }
                        )

        if item_type == "file_search_call":
            for result in get_value(item, "results", []) or []:
                file_id = str(get_value(result, "file_id", ""))
                filename = normalize_mojibake_text(str(get_value(result, "filename", "")))
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
                        "file_id": file_id,
                        "filename": filename,
                        "score": str(get_value(result, "score", "")),
                        "text": normalize_mojibake_text(chunk_text),
                    }
                )

                source_key = (file_id, filename)
                if file_id and source_key not in retrieved_source_seen:
                    retrieved_source_seen.add(source_key)
                    retrieved_sources.append({"file_id": file_id, "filename": filename})

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
        "retrieved_sources": retrieved_sources,
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


def extract_note_refs_from_text(text: str) -> list[str]:
    """Extract likely note references, e.g. (422), from source text."""
    refs: list[str] = []
    seen: set[str] = set()
    for match in re.findall(r"\((\d{2,4})\)", text or ""):
        normalized = f"({match})"
        if normalized in seen:
            continue
        seen.add(normalized)
        refs.append(normalized)
        if len(refs) >= 12:
            break
    return refs


def extract_section_refs_from_output(text: str) -> list[str]:
    """Extract referenced legal sections from answer text, e.g. § 9 C."""
    refs: list[str] = []
    seen: set[str] = set()
    for match in re.findall(r"§\s*\d+\s*[A-Za-z]?", text or "", flags=re.IGNORECASE):
        normalized = re.sub(r"\s+", " ", match).strip()
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        refs.append(normalized)
        if len(refs) >= 12:
            break
    return refs


def extract_note_refs_near_sections(text: str, section_refs: list[str]) -> list[str]:
    """
    Extract note refs near cited section mentions.

    This reduces noisy notes from unrelated parts of large chunks.
    """
    if not text:
        return []
    if not section_refs:
        return extract_note_refs_from_text(text)

    refs: list[str] = []
    seen: set[str] = set()
    lower_text = text.lower()
    for section in section_refs:
        needle = section.lower()
        pos = lower_text.find(needle)
        if pos == -1:
            continue
        start = max(0, pos - 350)
        end = min(len(text), pos + len(needle) + 350)
        window = text[start:end]
        for ref in extract_note_refs_from_text(window):
            if ref in seen:
                continue
            seen.add(ref)
            refs.append(ref)
            if len(refs) >= 8:
                return refs

    if refs:
        return refs
    return extract_note_refs_from_text(text)[:8]


def enforce_note_number_format(
    output_text: str,
    citation_hit_mapping: list[dict[str, Any]],
) -> str:
    """
    Ensure note bullets use explicit note-number format, e.g. "Note (454) til ...".

    This post-processes only source-section bullet lines that start with "Note til"
    and only if a note number is available from strict sourcing audit.
    """
    note_pool: list[str] = []
    seen: set[str] = set()
    for item in citation_hit_mapping:
        for ref in item.get("note_refs", []) or []:
            if ref in seen:
                continue
            seen.add(ref)
            note_pool.append(ref)

    if not note_pool:
        return output_text

    lines = output_text.splitlines()
    next_note_idx = 0
    updated_lines: list[str] = []
    note_line_pattern = re.compile(r"^(\s*-\s*)note\s+til\b", flags=re.IGNORECASE)
    already_numbered_pattern = re.compile(r"^(\s*-\s*)note\s*\(\d{2,4}\)\s*til\b", flags=re.IGNORECASE)

    for line in lines:
        if already_numbered_pattern.search(line):
            updated_lines.append(line)
            continue

        match = note_line_pattern.search(line)
        if not match or next_note_idx >= len(note_pool):
            updated_lines.append(line)
            continue

        note_ref = note_pool[next_note_idx]
        next_note_idx += 1
        replaced = re.sub(
            r"(?i)\bnote\s+til\b",
            f"Note {note_ref} til",
            line,
            count=1,
        )
        updated_lines.append(replaced)

    return "\n".join(updated_lines)


def ensure_sources_section(parsed: dict[str, Any]) -> dict[str, Any]:
    output_text = (parsed.get("output_text", "") or "").strip()
    if re.search(r"anvendte\s+kilder(?:/love)?\s*:?", output_text, flags=re.IGNORECASE):
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


def strip_sources_section(output_text: str) -> str:
    cleaned = re.split(
        r"\n\s*anvendte\s+kilder(?:/love)?\s*:?\s*\n",
        output_text,
        flags=re.IGNORECASE,
        maxsplit=1,
    )[0]
    return cleaned.strip()


def enforce_strict_sourcing(parsed: dict[str, Any]) -> dict[str, Any]:
    """
    Ensure citations only come from the actually retrieved file_search context.

    If model-level citations are missing, fall back to deterministic citations
    directly from retrieved sources to keep behavior stable.
    """
    retrieved_sources = parsed.get("retrieved_sources", []) or []
    allowed_file_ids = {
        str(item.get("file_id", "")).strip()
        for item in retrieved_sources
        if str(item.get("file_id", "")).strip()
    }

    raw_citations = parsed.get("citations", []) or []
    rejected_citations: list[dict[str, str]] = []
    filtered_citations: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for citation in raw_citations:
        file_id = str(citation.get("file_id", "")).strip()
        filename = normalize_mojibake_text(str(citation.get("filename", "")).strip())
        if not file_id or file_id not in allowed_file_ids:
            rejected_citations.append({"file_id": file_id, "filename": filename})
            continue
        key = (file_id, filename)
        if key in seen:
            continue
        seen.add(key)
        filtered_citations.append({"file_id": file_id, "filename": filename})

    if not filtered_citations:
        for source in retrieved_sources:
            file_id = str(source.get("file_id", "")).strip()
            filename = normalize_mojibake_text(str(source.get("filename", "")).strip())
            if not file_id:
                continue
            key = (file_id, filename)
            if key in seen:
                continue
            seen.add(key)
            filtered_citations.append({"file_id": file_id, "filename": filename})

    if not filtered_citations:
        raise RuntimeError(
            "Strict sourcing fejlede: ingen tilladte kilder fundet i file_search-resultater."
        )

    retrieved_chunks = parsed.get("retrieved_chunks", []) or []
    answer_text_for_targeting = str(parsed.get("output_text", "") or "")
    section_refs = extract_section_refs_from_output(answer_text_for_targeting)

    hit_map: dict[str, list[int]] = {}
    for idx, chunk in enumerate(retrieved_chunks, start=1):
        chunk_file_id = str(chunk.get("file_id", "")).strip()
        if not chunk_file_id:
            continue
        hit_map.setdefault(chunk_file_id, []).append(idx)

    citation_hit_mapping: list[dict[str, Any]] = []
    for citation in filtered_citations:
        file_id = str(citation.get("file_id", "")).strip()
        # Use only top hits per file to avoid noisy, unrelated note references.
        hit_indices = hit_map.get(file_id, [])[:3]
        note_refs: list[str] = []
        note_seen: set[str] = set()
        for hit_idx in hit_indices:
            if not isinstance(hit_idx, int) or hit_idx < 1:
                continue
            if hit_idx > len(retrieved_chunks):
                continue
            chunk = retrieved_chunks[hit_idx - 1]
            for ref in extract_note_refs_near_sections(
                str(chunk.get("text", "")),
                section_refs,
            ):
                if ref in note_seen:
                    continue
                note_seen.add(ref)
                note_refs.append(ref)
                if len(note_refs) >= 4:
                    break
            if len(note_refs) >= 4:
                break
        citation_hit_mapping.append(
            {
                "file_id": file_id,
                "filename": normalize_mojibake_text(str(citation.get("filename", ""))),
                "retrieval_hit_indices": hit_indices,
                "note_refs": note_refs,
            }
        )

    output_text = parsed.get("output_text", "") or ""
    has_sources_header = re.search(
        r"anvendte\s+kilder(?:/love)?\s*:?",
        output_text,
        flags=re.IGNORECASE,
    )
    if has_sources_header:
        # Keep model's concise source section; strict filtering is still enforced
        # on the structured citations payload.
        parsed["output_text"] = output_text
    else:
        lines: list[str] = []
        for citation in filtered_citations:
            filename = citation.get("filename", "").strip()
            if filename:
                lines.append(f"- Kilde: {filename}")
        if not lines:
            lines.append("- Ingen eksplicitte kilder kunne udledes automatisk.")
        base_answer = strip_sources_section(output_text)
        parsed["output_text"] = base_answer + "\n\nAnvendte kilder/love\n" + "\n".join(lines)
    parsed["raw_citations"] = raw_citations
    parsed["citations"] = filtered_citations
    parsed["strict_sourcing_audit"] = {
        "allowed_file_ids": sorted(allowed_file_ids),
        "raw_citation_count": len(raw_citations),
        "filtered_citation_count": len(filtered_citations),
        "rejected_citations": rejected_citations,
        "citation_hit_mapping": citation_hit_mapping,
    }
    parsed["output_text"] = enforce_note_number_format(
        parsed.get("output_text", "") or "",
        citation_hit_mapping,
    )
    return parsed


def extract_used_retrieval_results(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    retrieval = parsed.get("retrieved_chunks", []) or []
    if not isinstance(retrieval, list):
        return []
    strict_audit = parsed.get("strict_sourcing_audit", {}) or {}
    if not isinstance(strict_audit, dict):
        return retrieval
    mapping = strict_audit.get("citation_hit_mapping", []) or []
    if not isinstance(mapping, list):
        return retrieval
    indices: list[int] = []
    seen: set[int] = set()
    for item in mapping:
        if not isinstance(item, dict):
            continue
        for hit_idx in item.get("retrieval_hit_indices", []) or []:
            if not isinstance(hit_idx, int):
                continue
            if hit_idx < 1 or hit_idx > len(retrieval):
                continue
            if hit_idx in seen:
                continue
            seen.add(hit_idx)
            indices.append(hit_idx)
    if not indices:
        return retrieval
    return [retrieval[idx - 1] for idx in indices if 0 < idx <= len(retrieval)]


def analyze_question(
    client: OpenAI,
    question: str,
    previous_response_id: str | None = None,
    vector_store_ids: list[str] | None = None,
    instructions: str | None = None,
    models_to_try: list[str] | None = None,
    reasoning_effort: str | None = None,
    prompt_cache_key: str | None = None,
    use_file_search: bool = True,
) -> tuple[dict[str, Any], str, str]:
    effective_vector_store_ids = vector_store_ids or VECTOR_STORE_IDS
    effective_instructions = instructions or ANSWER_INSTRUCTIONS
    effective_reasoning = reasoning_effort or REASONING_EFFORT_ANALYSE
    effective_cache_key = prompt_cache_key or PROMPT_CACHE_KEY_ANALYSE
    selected_vector_store_ids = select_vector_store_ids_for_query(
        client=client,
        question=question,
        vector_store_ids=effective_vector_store_ids,
    )

    effective_models_to_try = models_to_try or [PRIMARY_MODEL, FALLBACK_MODEL]
    last_error: Exception | None = None

    for model in effective_models_to_try:
        try:
            request_payload: dict[str, Any] = {
                "model": model,
                "instructions": effective_instructions,
                "input": question,
                "reasoning": {"effort": effective_reasoning},
                "prompt_cache_key": effective_cache_key,
                "prompt_cache_retention": PROMPT_CACHE_RETENTION,
            }
            if use_file_search:
                request_payload["tools"] = [
                    {
                        "type": "file_search",
                        "vector_store_ids": selected_vector_store_ids,
                        "max_num_results": MAX_NUM_RESULTS,
                    }
                ]
                request_payload["include"] = ["file_search_call.results"]
            if previous_response_id:
                request_payload["previous_response_id"] = previous_response_id

            t0 = time.perf_counter()
            resp = client.responses.create(**request_payload)
            duration_ms = (time.perf_counter() - t0) * 1000
            parsed = parse_response(resp)
            _log_performance(
                flow="analyse",
                model=model,
                duration_ms=duration_ms,
                resp=resp,
                reasoning_effort=effective_reasoning,
                num_retrieval_results=len(parsed.get("retrieved_chunks", [])),
            )
            if STRICT_SOURCING:
                parsed = enforce_strict_sourcing(parsed)
            else:
                parsed = ensure_sources_section(parsed)
            parsed["used_vector_store_ids"] = selected_vector_store_ids if use_file_search else []
            parsed["used_retrieval_results"] = extract_used_retrieval_results(parsed)
            response_id = str(get_value(resp, "id", ""))
            return parsed, model, response_id
        except Exception as exc:
            last_error = exc

    raise RuntimeError(
        f"Kald fejlede for modellerne {', '.join(effective_models_to_try)}: {last_error}"
    )


def analyze_question_stream(
    client: OpenAI,
    question: str,
    log_question: str | None = None,
    previous_response_id: str | None = None,
    vector_store_ids: list[str] | None = None,
    instructions: str | None = None,
    models_to_try: list[str] | None = None,
    reasoning_effort: str | None = None,
    prompt_cache_key: str | None = None,
    use_file_search: bool = True,
):
    """
    Streaming variant af analyze_question. Yielder dict-events: delta, done, error.
    """
    effective_vector_store_ids = vector_store_ids or VECTOR_STORE_IDS
    effective_instructions = instructions or ANSWER_INSTRUCTIONS
    effective_reasoning = reasoning_effort or REASONING_EFFORT_ANALYSE
    effective_cache_key = prompt_cache_key or PROMPT_CACHE_KEY_ANALYSE
    selected_vector_store_ids = select_vector_store_ids_for_query(
        client=client,
        question=question,
        vector_store_ids=effective_vector_store_ids,
    )
    effective_models_to_try = models_to_try or [PRIMARY_MODEL, FALLBACK_MODEL]
    last_error: Exception | None = None

    for model in effective_models_to_try:
        try:
            request_payload: dict[str, Any] = {
                "model": model,
                "instructions": effective_instructions,
                "input": question,
                "reasoning": {"effort": effective_reasoning},
                "prompt_cache_key": effective_cache_key,
                "prompt_cache_retention": PROMPT_CACHE_RETENTION,
                "stream": True,
            }
            if use_file_search:
                request_payload["tools"] = [
                    {
                        "type": "file_search",
                        "vector_store_ids": selected_vector_store_ids,
                        "max_num_results": MAX_NUM_RESULTS,
                    }
                ]
                request_payload["include"] = ["file_search_call.results"]
            if previous_response_id:
                request_payload["previous_response_id"] = previous_response_id

            t0 = time.perf_counter()
            stream = client.responses.create(**request_payload)
            for event in stream:
                event_type = get_value(event, "type", "")
                if event_type == "response.output_text.delta":
                    delta = get_value(event, "delta", "")
                    if delta:
                        yield {"type": "delta", "text": delta}
                elif event_type == "response.completed":
                    resp = get_value(event, "response")
                    duration_ms = (time.perf_counter() - t0) * 1000
                    parsed = parse_response(resp)
                    _log_performance(
                        flow="analyse",
                        model=model,
                        duration_ms=duration_ms,
                        resp=resp,
                        reasoning_effort=effective_reasoning,
                        num_retrieval_results=len(parsed.get("retrieved_chunks", [])),
                    )
                    if STRICT_SOURCING:
                        parsed = enforce_strict_sourcing(parsed)
                    else:
                        parsed = ensure_sources_section(parsed)
                    parsed["used_vector_store_ids"] = selected_vector_store_ids if use_file_search else []
                    parsed["used_retrieval_results"] = extract_used_retrieval_results(parsed)
                    response_id = str(get_value(resp, "id", ""))
                    log_path = save_pdf_log(log_question or question, parsed, model)
                    yield {
                        "type": "done",
                        "answer": parsed.get("output_text", ""),
                        "used_model": model,
                        "response_id": response_id,
                        "citations": parsed.get("citations", []),
                        "retrieval_results": parsed.get("retrieved_chunks", []),
                        "used_retrieval_results": parsed.get("used_retrieval_results", []),
                        "used_vector_store_ids": selected_vector_store_ids if use_file_search else [],
                        "log_pdf_filename": log_path.name,
                        "log_pdf_url": f"/api/logs/{log_path.name}",
                    }
                    return
            last_error = RuntimeError("Stream sluttede uden response.completed")
        except Exception as exc:
            last_error = exc

    raise RuntimeError(
        f"Kald fejlede for modellerne {', '.join(effective_models_to_try)}: {last_error}"
    )
