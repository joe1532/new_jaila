"""HTTP-wrapper om read-only SKAT-retrieval. Ingen DSN eller vektorer i svar."""

from __future__ import annotations

import html
import os
import re
import time
from pathlib import Path
from typing import Any

from backend.config import BASE_DIR
from backend.db.skat_retrieval.settings import CLI_SEARCH_MODES, DEFAULT_CLI_SEARCH_MODE

SEARCH_API_ENV = "JAILA_SKAT_SEARCH_API"
RAW_HTML_ENV = "JAILA_SKAT_RAW_HTML_DIR"
INFO_SKAT_BASE = "https://info.skat.dk/"
MAX_QUERY_CHARS = 4_000
MAX_LIMIT = 20
MIN_LIMIT = 1

# SKM2021.486.LSR / SKM2023.18.ØLR / SKM2023.471.GÆLDST
_SKM_RE = re.compile(r"^SKM[0-9]{4}\.[0-9]+\.[A-ZÆØÅ0-9]+$", re.IGNORECASE)
_OID_RE = re.compile(r"^[0-9]{4,12}$")
_RAW_HTML_NAME_RE = re.compile(
    r"^SKM[0-9]{4}\.[0-9]+\.[A-ZÆØÅ0-9]+__oid-[0-9]{4,12}\.html$",
    re.IGNORECASE,
)

SECTION_LABELS = {
    "summary": "Resumé",
    "questions": "Spørgsmål",
    "answers": "Svar",
    "facts": "Sagens faktum",
    "claimant_arguments": "Klagerens opfattelse",
    "other_party_arguments": "Modpartens opfattelse",
    "authority_reasoning": "Myndighedens begrundelse",
    "authority_recommendation": "Indstilling",
    "authority_decision": "Myndighedens afgørelse",
    "court_reasoning": "Rettens begrundelse",
    "court_result": "Rettens resultat",
    "court_reasoning_and_result": "Rettens begrundelse og resultat",
    "prior_instance_reasoning": "Tidligere instans — begrundelse",
    "prior_instance_result": "Tidligere instans — resultat",
    "legal_basis": "Retsgrundlag",
    "preparatory_material": "Forarbejder",
    "case_law": "Praksis",
    "administrative_guidance": "Vejledning",
    "references": "Henvisninger",
    "ocr_supplement": "OCR-tillæg",
    "other": "Øvrigt",
    "unstructured": "Øvrigt",
}


def skat_search_api_enabled() -> bool:
    """Eksplicit opt-in. Blandes ikke sammen med chat-flaget JAILA_SKAT_RETRIEVAL_ENABLED."""
    value = os.getenv(SEARCH_API_ENV, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def skat_database_configured() -> bool:
    return bool((os.getenv("JAILA_SKAT_DATABASE_URL") or "").strip())


def search_status() -> dict[str, bool]:
    return {
        "enabled": skat_search_api_enabled(),
        "database_configured": skat_database_configured(),
        "raw_html_configured": raw_html_root() is not None,
    }


def default_raw_html_dir() -> Path:
    data_dir = BASE_DIR / "data" / "skat_info"
    if data_dir.is_dir():
        return data_dir
    return BASE_DIR / "Dokumenter" / "Originale filer crawlet fra nettet" / "skat_info"


def raw_html_root() -> Path | None:
    """Mappe med {år}/raw_html/{SKM}__oid-{oid}.html. Ingen path-traversal ud herfra."""
    configured = (os.getenv(RAW_HTML_ENV) or "").strip()
    path = Path(configured) if configured else default_raw_html_dir()
    try:
        resolved = path.resolve()
    except OSError:
        return None
    if not resolved.is_dir():
        return None
    return resolved


def normalize_skm_number(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text or not _SKM_RE.fullmatch(text):
        return None
    return text


def normalize_source_oid(value: str | None) -> str | None:
    text = str(value or "").strip()
    if text.lower().startswith("oid="):
        text = text[4:].strip()
    if not text or not _OID_RE.fullmatch(text):
        return None
    return text


def inject_info_skat_base(markup: str) -> str:
    """Relative /style/-stier i crawl'en skal ramme info.skat.dk, ikke JAILA."""
    if re.search(r"<base\b", markup, flags=re.IGNORECASE):
        return markup
    tag = f'<base href="{INFO_SKAT_BASE}">'
    match = re.search(r"<head[^>]*>", markup, flags=re.IGNORECASE)
    if not match:
        return tag + "\n" + markup
    at = match.end()
    return markup[:at] + "\n" + tag + markup[at:]


def _safe_html_file(root: Path, candidate: Path) -> Path | None:
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None
    if not resolved.is_file() or resolved.suffix.lower() != ".html":
        return None
    if not _RAW_HTML_NAME_RE.fullmatch(resolved.name):
        return None
    return resolved


def find_raw_html_file(
    *,
    identifier: str = "",
    skm_number: str | None = None,
    source_oid: str | None = None,
    publication_year: int | None = None,
    root: Path | None = None,
) -> Path | None:
    """Find crawl-fil ud fra SKM, OID eller begge. Bliver inden for root."""
    base = root if root is not None else raw_html_root()
    if base is None:
        return None

    skm = normalize_skm_number(skm_number) or normalize_skm_number(identifier)
    oid = normalize_source_oid(source_oid) or normalize_source_oid(identifier)
    year: int | None = None
    if publication_year is not None:
        try:
            parsed_year = int(publication_year)
        except (TypeError, ValueError):
            parsed_year = None
        if parsed_year is not None and 1990 <= parsed_year <= 2100:
            year = parsed_year

    candidates: list[Path] = []
    if year is not None and skm and oid:
        candidates.append(base / str(year) / "raw_html" / f"{skm}__oid-{oid}.html")
    if year is not None and oid:
        year_dir = base / str(year) / "raw_html"
        if year_dir.is_dir():
            candidates.extend(sorted(year_dir.glob(f"*__oid-{oid}.html")))
    if oid:
        candidates.extend(sorted(base.glob(f"*/raw_html/*__oid-{oid}.html")))
    if skm:
        candidates.extend(sorted(base.glob(f"*/raw_html/{skm}__oid-*.html")))

    seen: set[Path] = set()
    for item in candidates:
        safe = _safe_html_file(base, item)
        if safe is None or safe in seen:
            continue
        seen.add(safe)
        return safe
    return None


def load_original_html(identifier: str, *, root: Path | None = None) -> str:
    """Returnér scraped HTML med <base href> til info.skat.dk."""
    clean = str(identifier or "").strip()
    if not clean:
        raise ValueError("identifier mangler")
    if normalize_skm_number(clean) is None and normalize_source_oid(clean) is None:
        raise ValueError("identifier skal være et SKM-nummer eller en OID")
    base = root if root is not None else raw_html_root()
    if base is None:
        raise FileNotFoundError("Original HTML-mappen blev ikke fundet")
    path = find_raw_html_file(identifier=clean, root=base)
    if path is None:
        raise FileNotFoundError(f"Ingen original HTML for {clean}")
    try:
        markup = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FileNotFoundError(f"Kunne ikke læse original HTML for {clean}") from exc
    return inject_info_skat_base(markup)


def section_label(section_type: str) -> str:
    key = str(section_type or "").strip()
    return SECTION_LABELS.get(key, key or "Afsnit")


def collapse_hits_to_summaries(
    results: list[dict[str, Any]],
    summaries: dict[str, str],
) -> list[dict[str, Any]]:
    """Én række pr. dokument. Visningstekst er altid resuméet; ramte afsnit gemmes."""
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in results:
        document_id = str(item.get("document_id") or "")
        if not document_id or document_id in seen:
            continue
        seen.add(document_id)
        row = dict(item)
        matched = str(row.get("section_type") or "")
        summary = (summaries.get(document_id) or "").strip()
        if summary:
            row["text"] = summary
            row["section_type"] = "summary"
        row["matched_section_type"] = matched
        row["matched_section_label"] = section_label(matched)
        unique.append(row)
    for index, row in enumerate(unique, start=1):
        row["rank"] = index
    return unique


def assemble_sections(rows: list[tuple[Any, ...]]) -> list[dict[str, str]]:
    """Saml fortløbende chunks med samme section_type."""
    sections: list[dict[str, str]] = []
    for chunk_index, section_type, chunk_text in rows:
        text = str(chunk_text or "").strip()
        if not text:
            continue
        kind = str(section_type or "other")
        if sections and sections[-1]["section_type"] == kind:
            sections[-1]["text"] = sections[-1]["text"] + "\n\n" + text
            continue
        sections.append(
            {
                "section_type": kind,
                "heading": section_label(kind),
                "text": text,
                "chunk_index": str(chunk_index if chunk_index is not None else ""),
            }
        )
    return sections


def sections_to_html(sections: list[dict[str, str]]) -> str:
    """Simpel artikel-HTML. Chunk-tekst escapes, så den ikke fortolkes som markup."""
    parts = ['<article class="skat-afgoerelse">']
    for section in sections:
        heading = html.escape(section.get("heading") or section_label(section.get("section_type") or ""))
        body = html.escape(section.get("text") or "")
        paragraphs = "".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in body.split("\n\n") if p.strip())
        parts.append(
            f'<section data-section="{html.escape(section.get("section_type") or "")}">'
            f"<h2>{heading}</h2>{paragraphs}</section>"
        )
    parts.append("</article>")
    return "".join(parts)


def _load_summaries(conn, document_ids: list[str]) -> dict[str, str]:
    if not document_ids:
        return {}
    summaries: dict[str, str] = {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT document_id, summary
            FROM skat.legal_documents
            WHERE document_id = ANY(%s)
            """,
            (document_ids,),
        )
        for document_id, summary in cur.fetchall():
            if summary and str(summary).strip():
                summaries[str(document_id)] = str(summary).strip()
        missing = [item for item in document_ids if item not in summaries]
        if missing:
            cur.execute(
                """
                SELECT DISTINCT ON (document_id) document_id, chunk_text
                FROM skat.chunks
                WHERE document_id = ANY(%s) AND section_type = 'summary'
                ORDER BY document_id, chunk_index
                """,
                (missing,),
            )
            for document_id, chunk_text in cur.fetchall():
                if chunk_text and str(chunk_text).strip():
                    summaries[str(document_id)] = str(chunk_text).strip()
    return summaries


def present_search_payload(conn, payload: dict[str, Any]) -> dict[str, Any]:
    """Erstat hit-tekst med dokumentets resumé. Lookup-summary røres ikke."""
    results = list(payload.get("results") or [])
    ids = [str(item.get("document_id") or "") for item in results if item.get("document_id")]
    if ids:
        payload["results"] = collapse_hits_to_summaries(results, _load_summaries(conn, ids))
        payload["result_count"] = len(payload["results"])
    document = payload.get("document")
    if isinstance(document, dict) and payload.get("summary"):
        payload["summary"] = str(payload["summary"])
    return payload


def load_skat_document(identifier: str) -> dict[str, Any]:
    """Fuld afgørelse som afsnit + escaped HTML. Ingen ekstern side."""
    from backend.db.skat_retrieval.db import connect_readonly
    from backend.db.skat_retrieval.lookup import get_document
    from backend.db.skat_retrieval.output import document_meta

    clean = str(identifier or "").strip()
    if not clean:
        raise ValueError("identifier mangler")
    conn = connect_readonly()
    try:
        document = get_document(conn, clean)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT chunk_index, section_type, chunk_text
                FROM skat.chunks
                WHERE document_id = %s
                ORDER BY chunk_index
                """,
                (document.document_id,),
            )
            rows = list(cur.fetchall())
        sections = assemble_sections(rows)
        summary = (document.summary or "").strip()
        if summary and not any(item["section_type"] == "summary" for item in sections):
            sections.insert(
                0,
                {
                    "section_type": "summary",
                    "heading": section_label("summary"),
                    "text": summary,
                    "chunk_index": "",
                },
            )
        return {
            "document": document_meta(document),
            "summary": summary or None,
            "sections": sections,
            "html": sections_to_html(sections),
        }
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()


def run_skat_search(
    query: str,
    *,
    mode: str = DEFAULT_CLI_SEARCH_MODE,
    limit: int = 10,
    exact_vector: bool = False,
    embed_client: Any = None,
) -> dict[str, Any]:
    """Kør retrieve() og returnér CLI-JSON uden hemmeligheder."""
    from backend.db.skat_embed.client import OpenAIEmbeddingsClient
    from backend.db.skat_retrieval.db import connect_readonly
    from backend.db.skat_retrieval.engine import retrieve
    from backend.db.skat_retrieval.output import search_payload

    clean = str(query or "").strip()
    if not clean:
        raise ValueError("Søgeforespørgslen må ikke være tom")
    if len(clean) > MAX_QUERY_CHARS:
        raise ValueError(f"Søgeforespørgslen må højst være {MAX_QUERY_CHARS} tegn")
    requested = str(mode or DEFAULT_CLI_SEARCH_MODE).strip()
    if requested not in CLI_SEARCH_MODES:
        raise ValueError(f"ukendt søgemode {requested}")
    if not MIN_LIMIT <= int(limit) <= MAX_LIMIT:
        raise ValueError(f"limit skal være mellem {MIN_LIMIT} og {MAX_LIMIT}")

    embedding_api = embed_client
    if embed_client is not None and not hasattr(embed_client, "embeddings_create"):
        embedding_api = OpenAIEmbeddingsClient(inner=embed_client)

    started = time.perf_counter()
    conn = connect_readonly()
    try:
        response = retrieve(
            conn,
            clean,
            limit=int(limit),
            mode=requested,
            exact_vector=bool(exact_vector),
            embed_client=embedding_api,
            honor_route_lookup=requested == "auto",
        )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        payload = search_payload(
            response,
            query=clean,
            limit=int(limit),
            filters=None,
            elapsed_ms=elapsed_ms,
            include_references=False,
        )
        return present_search_payload(conn, payload)
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()
