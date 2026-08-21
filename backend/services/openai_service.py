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

# Modeller fra GPT-5.6 og frem sætter cachens levetid med `prompt_cache_options`;
# ældre modeller bruger `prompt_cache_retention`. Præfikserne står eksplicit, fordi
# en fremtidig generation (5.7, 6) ellers stiltiende ville havne i den gamle gren.
# Kommer der en ny generation, skal den tilføjes her.
NEW_CACHE_FORMAT_PREFIXES = ("gpt-5.6",)


def cache_fields_for_model(model: str) -> dict[str, Any]:
    """De cache-felter, der hører til modellens generation.

    Skellet er nødvendigt, fordi fallback-kæden kan ramme både en 5.6-model og en
    ældre inden for samme kald. Sendes det gamle felt til en 5.6-model, risikerer vi
    at få afvist netop det kald, der skulle redde requesten.

    For 5.6 sættes intet levetidsfelt: den eneste tilladte værdi er "30m", som også
    er standard. Det er samtidig en reel ændring i forhold til de 24 timer, ældre
    modeller fik — cachen holder kortere, men fornys hver gang prefikset genbruges.
    """
    if model.startswith(NEW_CACHE_FORMAT_PREFIXES):
        return {}
    return {"prompt_cache_retention": PROMPT_CACHE_RETENTION}


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
    # Responses API lægger cache-tallene i input_tokens_details. Feltet hed tidligere
    # prompt_tokens_details i denne kode, hvilket er Chat Completions-formen — derfor
    # blev cached_tokens altid logget som 0. Begge læses nu, så gamle logs kan
    # sammenlignes med nye. cache_write_tokens er ny fra 5.6 og viser, om vi betaler
    # for at skrive cache uden at læse den bagefter.
    cached_tokens = 0
    cache_write_tokens = 0
    if usage:
        details = get_value(usage, "input_tokens_details") or get_value(
            usage, "prompt_tokens_details"
        )
        if details is not None:
            cached_tokens = get_value(details, "cached_tokens", 0) or 0
            cache_write_tokens = get_value(details, "cache_write_tokens", 0) or 0
    request_id = getattr(resp, "_request_id", None) or getattr(resp, "request_id", None)
    processing_ms = getattr(resp, "_headers", None)
    if processing_ms and hasattr(processing_ms, "get"):
        processing_ms = processing_ms.get("openai-processing-ms")
    else:
        processing_ms = None
    _log.info(
        "perf flow=%s model=%s duration_ms=%.0f openai_processing_ms=%s x_request_id=%s "
        "input_tokens=%s output_tokens=%s cached_tokens=%s cache_write_tokens=%s "
        "reasoning_effort=%s retrieval_results=%s",
        flow,
        model,
        duration_ms,
        processing_ms or "?",
        request_id or "?",
        input_tokens,
        output_tokens,
        cached_tokens,
        cache_write_tokens,
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


def clean_answer_text(text: str, preserve_markdown: bool = False) -> str:
    """Remove raw inline filecite markers from model output text."""
    cleaned = re.sub(r"filecite.*?", "", text, flags=re.DOTALL)
    if not preserve_markdown:
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


def parse_response(resp: Any, preserve_markdown: bool = False) -> dict[str, Any]:
    output_text = get_value(resp, "output_text", "") or ""
    output_text = clean_answer_text(output_text, preserve_markdown=preserve_markdown)
    output_items = get_value(resp, "output", []) or []

    citations: list[dict[str, str]] = []
    retrieved_chunks: list[dict[str, str]] = []
    retrieved_sources: list[dict[str, str]] = []
    retrieved_source_seen: set[tuple[str, str]] = set()
    searches: list[dict[str, Any]] = []

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
            # Modellen formulerer selv sine søgestrenge. De er den eneste kilde til at se,
            # om et dårligt svar skyldtes en dårlig søgning eller manglende materiale, så
            # de gemmes her i stedet for at blive kasseret sammen med resten af item'et.
            # num_results tæller kun de hits, vi faktisk fik udleveret; uden
            # include=["file_search_call.results"] er listen tom, selv om der blev søgt.
            search_results = get_value(item, "results", []) or []
            searches.append(
                {
                    "queries": [
                        str(query).strip()
                        for query in (get_value(item, "queries", []) or [])
                        if str(query).strip()
                    ],
                    "status": str(get_value(item, "status", "") or ""),
                    "num_results": len(search_results),
                }
            )
            for result in search_results:
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
        "searches": searches,
    }


# --- Retrieval-diagnostik ---------------------------------------------------------
#
# Alt herunder er observation. Det ændrer ikke svaret og blokerer intet; formålet er
# udelukkende at kunne se, hvorfor et svar blev dårligt — blev der søgt forkert, eller
# kom det rigtige materiale bare ikke hjem?
#
# Vigtig begrænsning: diagnosen kan kun måle på de retskilder, spørgsmålet selv nævner.
# Spørger nogen bredt ("hvordan beskattes fri bil?"), er der intet at holde søgningen op
# imod, og diagnosen melder ingenting. Den fanger altså den fejl, hvor en nævnt
# bestemmelse ikke kom hjem — ikke den, hvor en relevant bestemmelse aldrig blev nævnt.

# Et enkelt bogstav efter paragraffens nummer kan være paragrafbogstavet ("§ 33 A") eller
# et almindeligt dansk ord ("§ 5 i loven"). Uden denne liste ville det sidste blive læst
# som "§ 5 I", og diagnosen ville melde en manglende bestemmelse, ingen har spurgt om.
_PARAGRAPH_LETTER_STOPWORDS = {"i", "o", "e", "å"}

# Bogstavet tages kun med, hvis der ikke står flere bogstaver lige efter. Det holder
# "§ 5 om fradrag" og "§ 5 stk. 2" fri af at blive læst som "§ 5 O" og "§ 5 S".
_PARAGRAPH_PATTERN = re.compile(
    r"§+\s*(\d+)\s*(?:([A-Za-zÆØÅæøå])(?![A-Za-zÆØÅæøå]))?"
)
# Kræver mindst fire bogstaver før "lov", så det generiske ord "loven" ikke tælles med
# som en selvstændig retskilde. Stammen gemmes uden endelse, så "ligningsloven",
# "ligningslovens" og "ligningslov" giver samme nøgle.
_LAW_PATTERN = re.compile(r"([a-zæøå]{4,}lov)(?:en|ens|e|s)?\b", re.IGNORECASE)
_RULING_PATTERN = re.compile(
    r"\b(?:SKM|TfS|LSR|SKDM)\s*\.?\s*\d{4}\s*[.,]?\s*\d+\s*[.,]?\s*[A-ZÆØÅ]{0,5}\b",
    re.IGNORECASE,
)
_ARTICLE_PATTERN = re.compile(r"\bartikel\s*(\d+)", re.IGNORECASE)

REFERENCE_KINDS = ("paragraffer", "love", "afgørelser", "artikler")


def _normalize_key(value: str) -> str:
    return re.sub(r"[^0-9a-zæøå]", "", value.lower())


def _reference_keys(text: str) -> dict[str, set[str]]:
    """Normaliserede nøgler for de retskilder, en tekst nævner.

    Nøglerne er med vilje grove: "§ 33 A", "§33 a" og "§ 33 A, stk. 1" giver alle
    "§33a". Det er en forudsætning for at kunne sammenligne et spørgsmål med de hentede
    tekststykker, hvor skrivemåden sjældent er den samme.

    Stykke og litra ignoreres. To spørgsmål om henholdsvis stk. 1 og stk. 3 i samme
    paragraf kan derfor ikke skelnes her — diagnosen er på paragrafniveau.
    """
    source = text or ""

    paragraphs: set[str] = set()
    for match in _PARAGRAPH_PATTERN.finditer(source):
        number = match.group(1)
        letter = (match.group(2) or "").lower()
        if letter in _PARAGRAPH_LETTER_STOPWORDS:
            letter = ""
        paragraphs.add(f"§{number}{letter}")

    laws = {match.group(1).lower() for match in _LAW_PATTERN.finditer(source)}
    rulings = {_normalize_key(match.group(0)) for match in _RULING_PATTERN.finditer(source)}
    articles = {f"artikel{match.group(1)}" for match in _ARTICLE_PATTERN.finditer(source)}

    return {
        "paragraffer": paragraphs,
        "love": laws,
        "afgørelser": rulings,
        "artikler": articles,
    }


def _filename_is_named_statute(filename: str, law_stems: set[str]) -> bool:
    """True if the file *is* the named statute, not a document that merely mentions it.

    "Ligningsloven (2025-11-24 nr. 1500).pdf" matches stem ligningslov.
    "Cirkulære 1996-04-17 nr. 72 om ligningsloven.pdf" does not: the circular is
    not the statute, even though the filename contains the law's name.
    """
    name = filename.replace("\\", "/").rsplit("/", 1)[-1].lower().strip()
    if not name:
        return False
    for stem in law_stems:
        if len(stem) < 4:
            continue
        if name.startswith(stem):
            return True
    return False


def attach_named_law_citations(parsed: dict[str, Any]) -> dict[str, Any]:
    """Add retrieved statute files that the answer names but the model did not cite.

    file_search can return ligningsloven while the model only filecites DJV that
    quotes the section. The answer then names the law, but the citation cards and
    PDF source list omit it. This is display/audit only: it does not change the
    model text.
    """
    answer = str(parsed.get("output_text", "") or "")
    law_stems = _reference_keys(answer).get("love") or set()
    if not law_stems:
        return parsed

    citations = [
        citation
        for citation in (parsed.get("citations") or [])
        if isinstance(citation, dict)
    ]
    seen: set[tuple[str, str]] = set()
    for citation in citations:
        file_id = str(citation.get("file_id", "")).strip()
        filename = normalize_mojibake_text(str(citation.get("filename", "")).strip())
        if file_id:
            seen.add((file_id, filename))

    extra: list[dict[str, str]] = []
    for source in parsed.get("retrieved_sources") or []:
        if not isinstance(source, dict):
            continue
        file_id = str(source.get("file_id", "")).strip()
        filename = normalize_mojibake_text(str(source.get("filename", "")).strip())
        if not file_id or not filename:
            continue
        if not _filename_is_named_statute(filename, law_stems):
            continue
        key = (file_id, filename)
        if key in seen:
            continue
        seen.add(key)
        extra.append({"file_id": file_id, "filename": filename})

    if extra:
        # Love først, så kortene følger retskildehierarkiet.
        parsed["citations"] = extra + citations
    return parsed


def diagnose_retrieval(question: str, parsed: dict[str, Any]) -> dict[str, Any]:
    """Sammenhold spørgsmålets retskilder med det, søgningen faktisk hentede hjem.

    Filnavnet tælles med på lige fod med teksten, fordi et lovdokument sjældent gentager
    sit eget navn inde i teksten — "aktieavancebeskatningsloven" står typisk kun i
    filnavnet.

    Et fund betyder kun, at bestemmelsen er nævnt et sted i det hentede materiale. Den
    kan optræde i en henvisningsliste uden at være det, tekststykket handler om. Signalet
    er derfor pålideligt, når det melder noget som manglende, og svagere når det melder
    alt fundet.
    """
    chunks = [chunk for chunk in (parsed.get("retrieved_chunks") or []) if isinstance(chunk, dict)]
    haystack = "\n".join(
        f"{chunk.get('filename', '')}\n{chunk.get('text', '')}" for chunk in chunks
    )

    asked = _reference_keys(question)
    found = _reference_keys(haystack)
    missing = {kind: sorted(asked[kind] - found[kind]) for kind in REFERENCE_KINDS}

    scores: list[float] = []
    for chunk in chunks:
        raw_score = str(chunk.get("score", "")).strip()
        if not raw_score:
            continue
        try:
            scores.append(float(raw_score))
        except ValueError:
            # Scoren kommer som streng fra API'et. Kan den ikke læses som tal, er det
            # ikke værd at fejle på — den indgår bare ikke i opsummeringen.
            continue

    return {
        "searches": parsed.get("searches") or [],
        "num_results": len(chunks),
        "score_min": min(scores) if scores else None,
        "score_max": max(scores) if scores else None,
        "asked_references": {kind: sorted(asked[kind]) for kind in REFERENCE_KINDS},
        "missing_references": missing,
        "has_missing_references": any(missing[kind] for kind in REFERENCE_KINDS),
    }


def _log_retrieval(flow: str, model: str, diagnostics: dict[str, Any]) -> None:
    """Én linje pr. kald, så mange spørgsmål kan aflæses samlet bagefter.

    Formatet er key=value, så linjerne kan filtreres med grep og tælles op uden at skulle
    parses. Søgestrengene skrives ud i fuld længde — det er netop dem, der skal kunne
    læses, når et svar er gået galt.
    """
    searches = diagnostics.get("searches") or []
    queries = [query for search in searches for query in (search.get("queries") or [])]
    missing = diagnostics.get("missing_references") or {}
    missing_flat = [value for kind in REFERENCE_KINDS for value in (missing.get(kind) or [])]

    def _fmt(value: Any) -> str:
        return "-" if value is None else f"{value:.3f}" if isinstance(value, float) else str(value)

    _log.info(
        "retrieval flow=%s model=%s searches=%s results=%s score_min=%s score_max=%s "
        'missing=%s asked=%s queries="%s"',
        flow,
        model,
        len(searches),
        diagnostics.get("num_results", 0),
        _fmt(diagnostics.get("score_min")),
        _fmt(diagnostics.get("score_max")),
        ",".join(missing_flat) or "-",
        ",".join(
            value
            for kind in REFERENCE_KINDS
            for value in (diagnostics.get("asked_references", {}).get(kind) or [])
        )
        or "-",
        '" | "'.join(queries) or "-",
    )


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
    user_question: str | None = None,
    flow: str = "analyse",
    preserve_markdown: bool = False,
) -> tuple[dict[str, Any], str, str]:
    """`user_question` er brugerens rå spørgsmål og bruges kun til retrieval-diagnosen.

    I chat indeholder `question` også uploadet kontekst og en instruktionshale. Måltes
    diagnosen på den, ville den tælle retskilder, brugeren aldrig har nævnt.

    `flow` er den etiket, kaldet får i loggen. Chat bruger denne funktion med analysens
    regler, og indtil nu blev chat-kald derfor logget som "analyse". Det er rettet, så
    de to kan skelnes — bemærk at ældre logs bruger den gamle, forkerte etiket.
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
                **cache_fields_for_model(model),
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
            parsed = parse_response(resp, preserve_markdown=preserve_markdown)
            _log_performance(
                flow=flow,
                model=model,
                duration_ms=duration_ms,
                resp=resp,
                reasoning_effort=effective_reasoning,
                num_retrieval_results=len(parsed.get("retrieved_chunks", [])),
            )
            if use_file_search:
                parsed["retrieval_diagnostics"] = diagnose_retrieval(
                    user_question or question, parsed
                )
                _log_retrieval(
                    flow=flow,
                    model=model,
                    diagnostics=parsed["retrieval_diagnostics"],
                )
            parsed = attach_named_law_citations(parsed)
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
    user_question: str | None = None,
    flow: str = "analyse",
    preserve_markdown: bool = False,
):
    """
    Streaming variant af analyze_question. Yielder dict-events: delta, done, error.

    `user_question` og `flow` virker som i analyze_question — se dokumentationen der.
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
                **cache_fields_for_model(model),
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
                    parsed = parse_response(resp, preserve_markdown=preserve_markdown)
                    _log_performance(
                        flow=flow,
                        model=model,
                        duration_ms=duration_ms,
                        resp=resp,
                        reasoning_effort=effective_reasoning,
                        num_retrieval_results=len(parsed.get("retrieved_chunks", [])),
                    )
                    if use_file_search:
                        parsed["retrieval_diagnostics"] = diagnose_retrieval(
                            user_question or log_question or question, parsed
                        )
                        _log_retrieval(
                            flow=flow,
                            model=model,
                            diagnostics=parsed["retrieval_diagnostics"],
                        )
                    parsed = attach_named_law_citations(parsed)
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
                        "searches": parsed.get("searches", []),
                        "retrieval_diagnostics": parsed.get("retrieval_diagnostics", {}),
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
