"""Test-opgaveløsning v1: file search → writer → nodeopslag → kritik → højst én omskrivning.

Layered search, intake og expand bruges ikke. Writer ser den fulde file-search-pose.
Python slår alle citerede LL- og DJV-adresser op. Kritikeren er et nyt API-kald.
Findes en fejl, omskrives notatet. Ingen anden kritikrunde.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Iterator

from openai import OpenAI

from backend.config import (
    CRITIC_INSTRUCTIONS,
    CRITIC_REWRITE_ADDENDUM,
    FALLBACK_MODEL,
    PRIMARY_MODEL,
    PROMPT_CACHE_KEY_CRITIC,
    REASONING_EFFORT_CHAT,
)
from backend.services.djv_opslag import lookup_djv_address
from backend.services.legal_search import search_legal_sources
from backend.services.openai_service import (
    analyze_question,
    analyze_question_stream,
    cache_fields_for_model,
    get_value,
)
from backend.services.opslagsvaerk import lookup_hit_for_anchor
from backend.services.task_search import (
    compose_write_input,
    extract_anchors,
    format_flat_retrieved_context,
)

_log = logging.getLogger(__name__)

MAX_MANIFEST = 24
MAX_CITED_NODES = 12
MAX_STK_CHARS = 900
MAX_UNVERIFIED_CHARS = 1_200
MAX_RECOVERY_CHUNKS = 4
MAX_RECOVERY_ADDRESSES = 4
MAX_MANGLES = 6

_DJV_RE = re.compile(r"\b([A-Z]\.[A-Z](?:\.\d+){2,})\b")
_STK_IN_LABEL = re.compile(r"stk\.?\s*(\d+)", re.IGNORECASE)
_PRACTICE_RE = re.compile(r"(?i)\bskm\d|\btfs\b|\blsr\d")

CRITIC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "status": {"type": "string", "enum": ["godkend", "underkend", "mangler"]},
        "primaert_stk": {"type": ["integer", "null"]},
        "mangler": {"type": "array", "items": {"type": "string"}},
        "fejl": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["status", "primaert_stk", "mangler", "fejl"],
}

HENRIK_GOLD_ADDRESSES = (
    "ligningsloven § 16, stk. 4",
    "C.A.5.14.1.4",
)


def build_retrieval_manifest(chunks: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Adresser/id'er fra file search. Gætter ikke en node-nøgle, hvis den ikke er tydelig."""
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for chunk in chunks[:MAX_MANIFEST]:
        filename = str(chunk.get("filename") or "")
        text = str(chunk.get("text") or "")
        file_id = str(chunk.get("file_id") or "")
        score = str(chunk.get("score") or "")
        address = _address_from_chunk(filename, text)
        key = address or f"{file_id}|{filename}"
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "file_id": file_id,
                "filename": filename,
                "score": score,
                "address": address,
                "complete": "true" if address else "false",
            }
        )
    return rows


def extract_cited_addresses(draft: str) -> list[dict[str, str]]:
    """Adresser som draft henviser til. Ikke alt, chunks nævner."""
    text = str(draft or "")
    found: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(kind: str, value: str, stk: str = "") -> None:
        canonical = _canonical_address(kind, value, stk)
        if not canonical or canonical in seen:
            return
        seen.add(canonical)
        found.append({"kind": kind, "value": value, "stk": stk, "canonical": canonical})

    for anchor in extract_anchors(text):
        stk = _stk_for_section(text, str(anchor.get("section") or ""))
        add("ll", str(anchor.get("label") or ""), stk)

    for match in _DJV_RE.finditer(text):
        add("djv", match.group(1))

    return found


def _lookup_ll_hits(anchors: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Ét hit pr. paragraf. Dedupér ikke på file_id — samme LBKG rummer flere noder."""
    hits: list[dict[str, Any]] = []
    seen: set[str] = set()
    for anchor in anchors:
        key = f"{anchor.get('law')}|{anchor.get('section')}".casefold()
        if not key.strip("|") or key in seen:
            continue
        hit = lookup_hit_for_anchor(anchor)
        if not hit:
            continue
        seen.add(key)
        hits.append(hit)
        if len(hits) >= MAX_CITED_NODES:
            break
    return hits


def lookup_canonical_nodes(cited: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Python-opslag af alle citerede LL- og DJV-adresser. Ikke et fast loft på 4.

    Ét opslag pr. paragraf. Samme LBKG-fil må godt give flere noder
    (§ 33 A og § 33 F er ikke den samme dør).
    """
    nodes: list[dict[str, Any]] = []
    seen: set[str] = set()
    parsed_ll = extract_anchors(
        "\n".join(item.get("canonical") or item.get("value") or "" for item in cited if item.get("kind") == "ll")
    )
    for hit in _lookup_ll_hits(parsed_ll):
        addr = str(hit.get("anchor") or "")
        key = addr.casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        cited_stk = _cited_stk_for_hit(hit, cited)
        nodes.append(_ll_node_from_hit(hit, cited_stk))
        if len(nodes) >= MAX_CITED_NODES:
            break
    for item in cited:
        if item.get("kind") != "djv":
            continue
        if len(nodes) >= MAX_CITED_NODES:
            break
        address = str(item.get("value") or "")
        key = address.casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        node = lookup_djv_address(address)
        if not node:
            nodes.append(
                {
                    "kind": "djv",
                    "address": address,
                    "status": "ingen_node",
                    "text": "",
                    "subsections": [],
                }
            )
        else:
            nodes.append(
                {
                    "kind": "djv",
                    "address": address,
                    "status": "ok",
                    "text": str(node.get("text") or "")[: MAX_STK_CHARS * 4],
                    "subsections": [],
                    "edition": str(node.get("edition") or ""),
                }
            )
    return nodes


def unused_gold_in_manifest(
    manifest: list[dict[str, str]],
    cited: list[dict[str, str]],
    gold: tuple[str, ...] | list[str] = (),
) -> dict[str, list[str]]:
    """Eval: rigtig kilde i pose men ikke i draft vs. aldrig hentet."""
    manifest_keys = {_norm_key(row.get("address") or "") for row in manifest}
    manifest_keys -= {""}
    cited_keys = {_norm_key(item.get("canonical") or "") for item in cited}
    cited_keys -= {""}
    gold_keys = [_norm_key(item) for item in gold]
    in_manifest = [item for item in gold_keys if item in manifest_keys]
    unused = [item for item in in_manifest if item not in cited_keys]
    missing_retrieval = [item for item in gold_keys if item not in manifest_keys]
    return {
        "gold_in_manifest": in_manifest,
        "unused_in_draft": unused,
        "missing_from_retrieval": missing_retrieval,
    }


def parse_critic_payload(raw: object) -> dict[str, Any]:
    data: Any = raw
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = {}
    if not isinstance(data, dict):
        data = {}
    status = str(data.get("status") or "").strip().lower()
    if status not in {"godkend", "underkend", "mangler"}:
        status = "underkend"
    stk_raw = data.get("primaert_stk")
    primaert = int(stk_raw) if isinstance(stk_raw, int) and stk_raw > 0 else None
    mangler = [
        str(item).strip()
        for item in (data.get("mangler") or [])
        if str(item).strip()
    ][:MAX_MANGLES]
    fejl = [str(item).strip() for item in (data.get("fejl") or []) if str(item).strip()][:8]
    return {
        "status": status,
        "primaert_stk": primaert,
        "mangler": mangler,
        "fejl": fejl,
    }


def is_node_recovery_address(raw: str) -> bool:
    """Kun LL-stk. eller DJV-adresse kan hentes. SKM/TfS er ikke en dør."""
    text = str(raw or "").strip()
    if not text or _PRACTICE_RE.search(text):
        return False
    if _DJV_RE.search(text):
        return True
    return bool(extract_anchors(text))


def _section_key(raw: str) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for row in extract_anchors(raw):
        law = re.sub(r"\s+", "", str(row.get("law") or "").casefold())
        section = re.sub(r"\s+", "", str(row.get("section") or "").casefold())
        if law and section:
            keys.add((law, section))
    return keys


def address_already_resolved(raw: str, nodes: list[dict[str, Any]] | None) -> bool:
    """Hent ikke en adresse, Python allerede har slået op med status ok.

    § 9 dækker ikke § 9 A. Sammenligning er lov + paragraf, ikke delstreng.
    """
    text = str(raw or "").strip()
    if not text:
        return False
    wanted_djv = _DJV_RE.search(text)
    wanted_keys = _section_key(text)
    for node in nodes or []:
        if str(node.get("status") or "") != "ok":
            continue
        addr = str(node.get("address") or "").strip()
        if not addr:
            continue
        if wanted_djv:
            got = _DJV_RE.search(addr)
            if got and got.group(1).casefold() == wanted_djv.group(1).casefold():
                return True
        if wanted_keys and wanted_keys & _section_key(addr):
            return True
    return False


def decide_critic_action(
    verdict: dict[str, Any],
    nodes: list[dict[str, Any]] | None = None,
) -> str:
    """godkend | recover | revise | fail_closed.

    SKM-only mangler vises som udkastet (praksis er ikke en dør).
    Underkendelse eller fejl med slåede noder omskrives — vi finder ikke
    en fejl for at lade den stå.
    """
    status = str(verdict.get("status") or "")
    missing = recovery_addresses(verdict, nodes)
    has_nodes = any(str(item.get("status") or "") == "ok" for item in (nodes or []))
    fejl = [str(item).strip() for item in (verdict.get("fejl") or []) if str(item).strip()]
    leftover_practice = [
        str(item)
        for item in (verdict.get("mangler") or [])
        if str(item).strip() and not is_node_recovery_address(str(item))
    ]
    if status == "godkend":
        return "godkend"
    if missing:
        return "recover"
    if status == "underkend":
        return "revise" if has_nodes else "fail_closed"
    if status == "mangler":
        if fejl and has_nodes and not leftover_practice:
            return "revise"
        return "godkend"
    return "fail_closed"


def recovery_addresses(
    verdict: dict[str, Any],
    nodes: list[dict[str, Any]] | None = None,
) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for item in verdict.get("mangler") or []:
        text = str(item).strip()
        if not is_node_recovery_address(text) or address_already_resolved(text, nodes):
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        found.append(text)
        if len(found) >= MAX_RECOVERY_ADDRESSES:
            break
    return found


def recovery_address(verdict: dict[str, Any], nodes: list[dict[str, Any]] | None = None) -> str:
    rows = recovery_addresses(verdict, nodes)
    return rows[0] if rows else ""


def format_fail_closed(verdict: dict[str, Any]) -> str:
    fejl = verdict.get("fejl") or []
    lines = [
        "## Konklusion",
        "Notatet er ikke udsendt. Hjemlen i udkastet kan ikke bæres af sagens "
        "faktum, og der er ikke angivet en konkret adresse der kan hentes.",
        "",
        "## Fejl",
    ]
    if fejl:
        lines.extend("- " + str(item) for item in fejl)
    else:
        lines.append("- Kritikken underkendte uden at pege på en hentbar kilde.")
    return "\n".join(lines).strip()


def format_critic_user_input(
    case: str,
    draft: str,
    nodes: list[dict[str, Any]],
    unverified: list[dict[str, str]],
    manifest: list[dict[str, str]],
) -> str:
    parts = [
        "[Sag]",
        str(case or "").strip(),
        "[/Sag]",
        "",
        "[Udkast]",
        str(draft or "").strip(),
        "[/Udkast]",
        "",
        "[Kanoniske noder]",
        _format_nodes(nodes) or "(ingen node slået op)",
        "[/Kanoniske noder]",
        "",
        "[Uverificerede filer — ikke noder. Må ikke sættes i mangler.]",
        _format_unverified_names(unverified) or "(ingen)",
        "[/Uverificerede filer]",
        "",
        "[Retrieval-manifest — id og adresse, ikke fuld tekst]",
        _format_manifest(manifest) or "(tom pose)",
        "[/Retrieval-manifest]",
    ]
    return "\n".join(parts)


def unverified_used_chunks(
    draft: str,
    chunks: list[dict[str, Any]],
    citations: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Chunks draft har brugt, som ikke er en slået node. Kort uddrag, ikke hele posen."""
    cited_names = {
        str(row.get("filename") or "").strip().lower()
        for row in citations
        if str(row.get("filename") or "").strip()
    }
    draft_l = draft.lower()
    rows: list[dict[str, str]] = []
    for chunk in chunks:
        filename = str(chunk.get("filename") or "")
        if not filename:
            continue
        used = filename.lower() in cited_names or filename.lower() in draft_l
        if not used:
            continue
        if _address_from_chunk(filename, str(chunk.get("text") or "")[:400]):
            # Adressen slås op som node; chunken er ikke den kanoniske lovtekst.
            continue
        text = str(chunk.get("text") or "").strip()
        if len(text) > MAX_UNVERIFIED_CHARS:
            text = text[:MAX_UNVERIFIED_CHARS] + "\n[afkortet]"
        rows.append({"filename": filename, "text": text})
        if len(rows) >= 4:
            break
    return rows


def run_critic(
    client: OpenAI,
    *,
    case: str,
    draft: str,
    nodes: list[dict[str, Any]],
    unverified: list[dict[str, str]],
    manifest: list[dict[str, str]],
) -> dict[str, Any]:
    user_input = format_critic_user_input(case, draft, nodes, unverified, manifest)
    models = [PRIMARY_MODEL, FALLBACK_MODEL]
    last_error: Exception | None = None
    for model in models:
        try:
            raw = _call_critic(client, model, user_input, use_schema=True)
            return parse_critic_payload(raw)
        except Exception as exc:
            last_error = exc
            _log.warning("critic schema-kald fejlede (%s): %s", model, exc)
            try:
                raw = _call_critic(client, model, user_input, use_schema=False)
                return parse_critic_payload(raw)
            except Exception as fallback_exc:
                last_error = fallback_exc
                _log.warning("critic fritekst-kald fejlede (%s): %s", model, fallback_exc)
    _log.error("critic gav op: %s", last_error)
    return {
        "status": "underkend",
        "primaert_stk": None,
        "mangler": [],
        "fejl": ["Kritikken kunne ikke gennemføres."],
    }


def fetch_recovery(
    client: OpenAI,
    address: str,
    vector_store_ids: list[str],
) -> dict[str, Any]:
    """Én targeted hentning. Node hvis adressen er en node, ellers én file search."""
    clean = str(address or "").strip()
    djv = _DJV_RE.search(clean)
    if djv:
        node = lookup_djv_address(djv.group(1))
        if node:
            return {
                "source": "node",
                "address": djv.group(1),
                "context_text": _format_nodes(
                    [
                        {
                            "kind": "djv",
                            "address": djv.group(1),
                            "status": "ok",
                            "text": str(node.get("text") or ""),
                            "subsections": [],
                        }
                    ]
                ),
                "chunks": [],
            }
    anchors = extract_anchors(clean)
    if anchors:
        hits = _lookup_ll_hits(anchors)
        if hits:
            cited_stk = ""
            stk_match = _STK_IN_LABEL.search(clean)
            if stk_match:
                cited_stk = stk_match.group(1)
            nodes = [_ll_node_from_hit(hit, cited_stk) for hit in hits[:MAX_CITED_NODES]]
            return {
                "source": "node",
                "address": clean,
                "context_text": _format_nodes(nodes),
                "chunks": [],
            }
    chunks = search_legal_sources(
        client,
        clean,
        max_results=MAX_RECOVERY_CHUNKS,
        vector_store_ids=vector_store_ids,
        rewrite_query=False,
    )
    packed = [
        {
            "file_id": str(item.get("file_id") or ""),
            "filename": str(item.get("filename") or ""),
            "score": str(item.get("score") or ""),
            "text": str(item.get("text") or ""),
        }
        for item in chunks
    ]
    return {
        "source": "search",
        "address": clean,
        "context_text": format_flat_retrieved_context(packed),
        "chunks": packed,
    }


def iter_task_solve_critic(
    *,
    client: OpenAI,
    write_client: OpenAI,
    message: str,
    write_question: str,
    vector_store_ids: list[str],
    instructions: str,
    models_to_try: list[str],
    reasoning_effort: str,
    prompt_cache_key: str,
    preserve_markdown: bool,
    previous_response_id: str | None,
    provider: str,
    prefetched_retrieval: dict[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    """SSE-klare events: search, critic, recover, delta, done, error."""
    yield {"type": "search", "phase": "file_search"}
    yield {"type": "draft"}
    use_file_search = prefetched_retrieval is None and provider != "grok"
    try:
        parsed, used_model, response_id = analyze_question(
            client=write_client,
            question=write_question,
            previous_response_id=previous_response_id,
            vector_store_ids=vector_store_ids,
            instructions=instructions,
            models_to_try=models_to_try,
            reasoning_effort=reasoning_effort,
            prompt_cache_key=prompt_cache_key,
            use_file_search=use_file_search,
            user_question=message,
            flow="task_solve",
            preserve_markdown=preserve_markdown,
            prefetched_retrieval=prefetched_retrieval,
        )
    except Exception as exc:
        yield {"type": "error", "detail": str(exc)}
        return

    draft = str(parsed.get("output_text") or "").strip()
    chunks = list(parsed.get("retrieved_chunks") or [])
    citations = list(parsed.get("citations") or [])
    diagnostics = dict(parsed.get("retrieval_diagnostics") or {})

    manifest = build_retrieval_manifest(chunks)
    cited = extract_cited_addresses(draft)
    nodes = lookup_canonical_nodes(cited)
    unverified = unverified_used_chunks(draft, chunks, citations)
    eval_row = unused_gold_in_manifest(manifest, cited)

    yield {"type": "critic"}
    verdict = run_critic(
        client,
        case=message,
        draft=draft,
        nodes=nodes,
        unverified=unverified,
        manifest=manifest,
    )
    action = decide_critic_action(verdict, nodes=nodes)
    outcome = (
        "godkend_draft"
        if action == "godkend"
        else "fail_closed"
        if action == "fail_closed"
        else "rewrite"
    )
    diagnostics = _with_critic_diagnostics(
        diagnostics,
        verdict=verdict,
        action=action,
        manifest=manifest,
        cited=cited,
        eval_row=eval_row,
        recovered=False,
        fail_closed=action == "fail_closed",
        chunks=chunks,
        nodes=nodes,
        outcome=outcome,
        recovery_address=(
            ", ".join(recovery_addresses(verdict, nodes)) if action == "recover" else ""
        ),
    )

    if action == "godkend":
        yield {
            "type": "delta",
            "text": draft,
        }
        yield _done_event(
            answer=draft,
            used_model=used_model,
            response_id=response_id,
            parsed=parsed,
            diagnostics=diagnostics,
            vector_store_ids=parsed.get("used_vector_store_ids") or [],
        )
        return

    if action == "fail_closed":
        answer = format_fail_closed(verdict)
        yield {"type": "delta", "text": answer}
        yield _done_event(
            answer=answer,
            used_model=used_model,
            response_id=response_id,
            parsed=parsed,
            diagnostics=diagnostics,
            vector_store_ids=parsed.get("used_vector_store_ids") or [],
        )
        return

    addresses = recovery_addresses(verdict, nodes)
    recovered = {
        "address": ", ".join(addresses),
        "source": "nodes",
        "context_text": "",
        "chunks": [],
    }
    if action == "recover":
        yield {"type": "recover", "address": recovered["address"]}
        texts: list[str] = []
        packed_chunks: list[dict[str, Any]] = []
        sources: list[str] = []
        for address in addresses:
            try:
                one = fetch_recovery(client, address, vector_store_ids)
            except Exception as exc:
                _log.warning("recovery fejlede for %s: %s", address, exc)
                continue
            texts.append(str(one.get("context_text") or ""))
            packed_chunks.extend(list(one.get("chunks") or []))
            sources.append(str(one.get("source") or "search"))
        if not texts and not packed_chunks:
            if not any(str(item.get("status") or "") == "ok" for item in nodes):
                answer = format_fail_closed(
                    {
                        **verdict,
                        "fejl": list(verdict.get("fejl") or [])
                        + [f"Kunne ikke hente {recovered['address']}."],
                    }
                )
                diagnostics = _with_critic_diagnostics(
                    diagnostics,
                    verdict={
                        **verdict,
                        "fejl": list(verdict.get("fejl") or [])
                        + [f"Kunne ikke hente {recovered['address']}."],
                    },
                    action="fail_closed",
                    manifest=manifest,
                    cited=cited,
                    eval_row=eval_row,
                    recovered=False,
                    fail_closed=True,
                    chunks=chunks,
                    nodes=nodes,
                    outcome="fail_closed",
                    recovery_address=recovered["address"],
                )
                yield {"type": "delta", "text": answer}
                yield _done_event(
                    answer=answer,
                    used_model=used_model,
                    response_id=response_id,
                    parsed=parsed,
                    diagnostics=diagnostics,
                    vector_store_ids=parsed.get("used_vector_store_ids") or [],
                )
                return
            _log.warning(
                "recovery tom for %s — skriver om ud fra slåede noder",
                recovered["address"],
            )
        recovered = {
            "address": ", ".join(addresses),
            "source": "+".join(sources) or "search",
            "context_text": "\n\n".join(texts),
            "chunks": packed_chunks,
        }
        extra = lookup_canonical_nodes(extract_cited_addresses(" ".join(addresses)))
        existing = {str(item.get("address") or "").casefold() for item in nodes}
        nodes = nodes + [
            item
            for item in extra
            if str(item.get("address") or "").casefold() not in existing
        ]
    else:
        yield {"type": "revise"}

    rewrite_question = compose_write_input(
        message=message,
        prefetch_context=_rewrite_context(draft, verdict, recovered, nodes),
        uploaded_context="",
        framing="",
    )
    rewrite_instructions = instructions + "\n\n" + CRITIC_REWRITE_ADDENDUM
    did_fetch = action == "recover"
    diagnostics["recovered"] = did_fetch
    diagnostics["recovery_address"] = str(recovered.get("address") or "")
    diagnostics["recovery_source"] = recovered.get("source") or ""
    diagnostics = _with_critic_diagnostics(
        diagnostics,
        verdict=verdict,
        action=action,
        manifest=manifest,
        cited=cited,
        eval_row=eval_row,
        recovered=did_fetch,
        fail_closed=False,
        chunks=chunks,
        nodes=nodes,
        outcome="rewrite",
        recovery_address=str(recovered.get("address") or ""),
        recovery_source=str(recovered.get("source") or ""),
    )
    accumulated = ""
    try:
        for evt in analyze_question_stream(
            client=write_client,
            question=rewrite_question,
            log_question=message,
            previous_response_id=None,
            vector_store_ids=vector_store_ids,
            instructions=rewrite_instructions,
            models_to_try=models_to_try,
            reasoning_effort=reasoning_effort,
            prompt_cache_key=prompt_cache_key + ("-recover" if did_fetch else "-revise"),
            use_file_search=False,
            user_question=message,
            flow="task_solve_recover",
            preserve_markdown=preserve_markdown,
            prefetched_retrieval={
                "retrieved_chunks": chunks + list(recovered.get("chunks") or []),
                "retrieved_sources": [],
                "searches": [],
                "keep_file_search": False,
            },
        ):
            if evt.get("type") == "delta":
                accumulated += str(evt.get("text") or "")
                yield {"type": "delta", "text": evt.get("text", "")}
                continue
            if evt.get("type") == "done":
                answer = str(evt.get("answer") or accumulated or "").strip()
                merged_chunks = chunks + list(recovered.get("chunks") or [])
                parsed["retrieved_chunks"] = merged_chunks
                parsed["citations"] = evt.get("citations") or citations
                yield _done_event(
                    answer=answer,
                    used_model=str(evt.get("used_model") or used_model),
                    response_id=str(evt.get("response_id") or response_id),
                    parsed=parsed,
                    diagnostics=diagnostics,
                    vector_store_ids=evt.get("used_vector_store_ids")
                    or parsed.get("used_vector_store_ids")
                    or [],
                )
                return
            if evt.get("type") == "error":
                yield {"type": "error", "detail": str(evt.get("detail") or "Ukendt fejl")}
                return
    except Exception as exc:
        yield {"type": "error", "detail": str(exc)}


# --- interne hjælpere ---


def _address_from_chunk(filename: str, text: str) -> str:
    blob = f"{filename}\n{text[:400]}"
    djv = _DJV_RE.search(blob)
    if djv:
        return djv.group(1)
    anchors = extract_anchors(blob)
    if len(anchors) == 1:
        stk = _stk_for_section(blob, str(anchors[0].get("section") or ""))
        return _canonical_address("ll", anchors[0]["label"], stk)
    return ""


def _stk_for_section(text: str, section: str) -> str:
    number = re.search(r"\d+", str(section or ""))
    if not number:
        return ""
    match = re.search(
        rf"§+\s*{re.escape(number.group(0))}\s*,?\s*stk\.?\s*(\d+)",
        text,
        re.IGNORECASE,
    )
    return match.group(1) if match else ""


def _canonical_address(kind: str, value: str, stk: str = "") -> str:
    if kind == "djv":
        return str(value or "").strip()
    label = str(value or "").strip()
    if stk and "stk" not in label.lower():
        return f"{label}, stk. {stk}"
    return label


def _norm_key(value: str) -> str:
    text = uniclean(value).lower()
    text = text.replace("ligningslovens", "ligningsloven")
    text = text.replace("§", " ")
    return re.sub(r"\s+", " ", text).strip()


def uniclean(value: str) -> str:
    return str(value or "").replace("\u00a0", " ").strip()


def _cited_stk_for_hit(hit: dict[str, Any], cited: list[dict[str, str]]) -> str:
    label = str(hit.get("anchor") or "").lower()
    for item in cited:
        if item.get("kind") != "ll":
            continue
        if str(item.get("value") or "").lower() in label or label in str(item.get("value") or "").lower():
            return str(item.get("stk") or "")
    return ""


def _ll_node_from_hit(hit: dict[str, Any], cited_stk: str) -> dict[str, Any]:
    subsections = _stk_rows(hit.get("lookup_subsections") or [])
    return {
        "kind": "ll",
        "address": str(hit.get("anchor") or ""),
        "status": "ok",
        "cited_stk": cited_stk,
        "text": "",
        "subsections": subsections,
        "file_id": str(hit.get("file_id") or ""),
        "notice": str(hit.get("lookup_notice") or ""),
    }


def _stk_rows(subsections: list[Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in subsections:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        text = str(item.get("text") or item.get("leadText") or "").strip()
        if not text:
            continue
        match = _STK_IN_LABEL.search(label) or _STK_IN_LABEL.search(text[:80])
        stk = match.group(1) if match else str(len(rows) + 1)
        if len(text) > MAX_STK_CHARS:
            text = text[:MAX_STK_CHARS] + "\n[afkortet]"
        rows.append({"stk": stk, "label": label or f"Stk. {stk}.", "text": text})
    return rows


def _format_nodes(nodes: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for node in nodes:
        if node.get("kind") == "ll":
            lines = [f"LL {node.get('address') or ''} (status {node.get('status')})"]
            if node.get("cited_stk"):
                lines.append(f"Draft pegede på stk. {node['cited_stk']}.")
            lines.append("Peg på ét primært stk. eller ingen. Ikke 17 ja/nej.")
            for row in node.get("subsections") or []:
                lines.append(f"--- stk. {row.get('stk')} ---")
                lines.append(str(row.get("text") or ""))
            if node.get("notice"):
                lines.append(str(node["notice"]))
            blocks.append("\n".join(lines))
            continue
        if node.get("status") == "ingen_node":
            blocks.append(f"DJV {node.get('address')} — ingen_node")
            continue
        text = str(node.get("text") or "")
        if len(text) > MAX_STK_CHARS * 3:
            text = text[: MAX_STK_CHARS * 3] + "\n[afkortet]"
        blocks.append(f"DJV {node.get('address')}\n{text}")
    return "\n\n".join(blocks)


def _format_unverified_names(rows: list[dict[str, str]]) -> str:
    names: list[str] = []
    seen: set[str] = set()
    for row in rows:
        name = str(row.get("filename") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return "\n".join(names)


def _format_manifest(manifest: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for row in manifest:
        address = row.get("address") or "(ingen tydelig adresse)"
        lines.append(
            f"- {address} | {row.get('filename') or ''} | complete={row.get('complete')}"
        )
    return "\n".join(lines)


def _rewrite_context(
    draft: str,
    verdict: dict[str, Any],
    recovered: dict[str, Any],
    nodes: list[dict[str, Any]] | None = None,
) -> str:
    fejl = "\n".join(f"- {item}" for item in (verdict.get("fejl") or []) if item)
    mangler = "\n".join(f"- {item}" for item in (verdict.get("mangler") or []) if item)
    return (
        "[Kritik — omskriv notatet. Medtag ikke denne proces.]\n"
        f"Status: {verdict.get('status')}\n"
        f"Primært stk.: {verdict.get('primaert_stk')}\n"
        f"Hentet adresse: {recovered.get('address') or '(ingen ny hentning)'}\n"
        f"Mangler:\n{mangler or '- (ingen)'}\n"
        f"Fejl — ret dem alle:\n{fejl or '- (ingen)'}\n"
        "[/Kritik]\n\n"
        "[Kanoniske noder — behold disse. De er allerede slået op.]\n"
        + (_format_nodes(nodes or []) or "(ingen)")
        + "\n[/Kanoniske noder]\n\n"
        "[Tidligere udkast — rettes, vises ikke som facit]\n"
        + str(draft or "")[:8000]
        + "\n[/Tidligere udkast]\n\n"
        + str(recovered.get("context_text") or "")
    )


def build_pipeline_trace(
    *,
    chunks: list[dict[str, Any]],
    manifest: list[dict[str, str]],
    cited: list[dict[str, str]],
    nodes: list[dict[str, Any]],
    verdict: dict[str, Any],
    action: str,
    outcome: str,
    recovery_address: str = "",
    recovery_source: str = "",
) -> dict[str, Any]:
    """Hele sporet til UI, PDF og serverlog. Ikke facit — kun hvad sløjfen gjorde."""
    addresses = [row.get("address") or "" for row in manifest if row.get("address")]
    cited_labels = [item.get("canonical") or "" for item in cited if item.get("canonical")]
    node_labels = []
    for node in nodes:
        kind = str(node.get("kind") or "")
        address = str(node.get("address") or "")
        status = str(node.get("status") or "")
        stk = str(node.get("cited_stk") or "")
        extra = f", stk. {stk}" if stk else ""
        node_labels.append(f"{kind} {address}{extra} ({status})")
    fejl = [str(item) for item in (verdict.get("fejl") or []) if str(item).strip()]
    mangler = [str(item) for item in (verdict.get("mangler") or []) if str(item).strip()]
    stk = verdict.get("primaert_stk")
    critic_line = (
        f"status={verdict.get('status')}"
        + (f", primært stk. {stk}" if stk else ", intet primært stk.")
        + (f", mangler: {', '.join(mangler)}" if mangler else "")
        + (f", fejl: {'; '.join(fejl)}" if fejl else "")
    )
    action_line = {
        "godkend": "Vis udkastet. Ingen ny søgning.",
        "recover": (
            f"Hent {recovery_address or ', '.join(mangler) or 'navngivne adresser'} "
            "og skriv om. Ret alle nævnte fejl."
        ),
        "revise": "Skriv om ud fra slåede noder. Ingen ny søgning. Ret alle nævnte fejl.",
        "fail_closed": "Stop. Notatet udsendes ikke.",
    }.get(action, action)
    if action == "godkend":
        leftover = [item for item in mangler if not is_node_recovery_address(item)]
        if leftover:
            action_line = (
                "Vis udkastet. Hentede ikke "
                + ", ".join(leftover)
                + " (praksis er ikke en LL/DJV-dør)."
            )
    if outcome == "rewrite" and action == "revise":
        outcome_line = "Færdigt svar er omskrivning af fejl i udkastet. Ingen ny hentning."
    elif outcome == "rewrite":
        outcome_line = (
            f"Færdigt svar er omskrivning efter {recovery_source or 'hentning'} "
            f"af {recovery_address}."
        )
    else:
        outcome_line = {
            "godkend_draft": "Færdigt svar er første udkast.",
            "fail_closed": "Færdigt svar er stopbesked, ikke et notat.",
        }.get(outcome, outcome)
    steps = [
        {
            "id": "file_search",
            "title": "1. File search",
            "detail": f"{len(chunks)} chunks. Tydelige adresser: {', '.join(addresses) or 'ingen'}.",
        },
        {
            "id": "writer",
            "title": "2. Udkast",
            "detail": f"Citerede adresser: {', '.join(cited_labels) or 'ingen'}.",
        },
        {
            "id": "lookup",
            "title": "3. Nodeopslag",
            "detail": "; ".join(node_labels) if node_labels else "Ingen node slået op.",
        },
        {
            "id": "critic",
            "title": "4. Kritik",
            "detail": critic_line,
        },
        {
            "id": "action",
            "title": "5. Følge",
            "detail": action_line,
        },
        {
            "id": "outcome",
            "title": "6. Udfald",
            "detail": outcome_line,
        },
    ]
    trace = {
        "pipeline": "task_critic_v1",
        "ran": True,
        "outcome": outcome,
        "steps": steps,
    }
    _log.info(
        "task_critic pipeline=task_critic_v1 outcome=%s critic=%s action=%s recovery=%s cited=%s nodes=%s",
        outcome,
        verdict.get("status"),
        action,
        recovery_address or "-",
        ",".join(cited_labels) or "-",
        ",".join(node_labels) or "-",
    )
    return trace


def _with_critic_diagnostics(
    base: dict[str, Any],
    *,
    verdict: dict[str, Any],
    action: str,
    manifest: list[dict[str, str]],
    cited: list[dict[str, str]],
    eval_row: dict[str, list[str]],
    recovered: bool,
    fail_closed: bool,
    chunks: list[dict[str, Any]] | None = None,
    nodes: list[dict[str, Any]] | None = None,
    outcome: str = "",
    recovery_address: str = "",
    recovery_source: str = "",
) -> dict[str, Any]:
    out = dict(base)
    out["critic_status"] = verdict.get("status")
    out["critic_stk"] = verdict.get("primaert_stk")
    out["critic_fejl"] = list(verdict.get("fejl") or [])
    out["critic_mangler"] = list(verdict.get("mangler") or [])
    out["critic_action"] = action
    out["recovered"] = recovered
    out["fail_closed"] = fail_closed
    out["manifest_addresses"] = [row.get("address") or "" for row in manifest if row.get("address")]
    out["draft_addresses"] = [item.get("canonical") or "" for item in cited]
    out["gold_in_manifest"] = eval_row.get("gold_in_manifest") or []
    out["unused_in_draft"] = eval_row.get("unused_in_draft") or []
    out["missing_from_retrieval"] = eval_row.get("missing_from_retrieval") or []
    if outcome:
        trace = build_pipeline_trace(
            chunks=chunks or [],
            manifest=manifest,
            cited=cited,
            nodes=nodes or [],
            verdict=verdict,
            action=action,
            outcome=outcome,
            recovery_address=recovery_address,
            recovery_source=recovery_source,
        )
        out["pipeline"] = trace["pipeline"]
        out["pipeline_outcome"] = trace["outcome"]
        out["pipeline_trace"] = trace["steps"]
    return out


def _done_event(
    *,
    answer: str,
    used_model: str,
    response_id: str,
    parsed: dict[str, Any],
    diagnostics: dict[str, Any],
    vector_store_ids: list[str],
) -> dict[str, Any]:
    return {
        "type": "done",
        "answer": answer,
        "used_model": used_model,
        "response_id": response_id,
        "citations": parsed.get("citations") or [],
        "retrieval_results": parsed.get("retrieved_chunks") or [],
        "used_retrieval_results": parsed.get("used_retrieval_results")
        or parsed.get("retrieved_chunks")
        or [],
        "used_vector_store_ids": vector_store_ids,
        "retrieval_diagnostics": diagnostics,
    }


def _call_critic(client: OpenAI, model: str, user_input: str, use_schema: bool) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "instructions": CRITIC_INSTRUCTIONS,
        "input": user_input,
        "reasoning": {"effort": REASONING_EFFORT_CHAT},
        "prompt_cache_key": PROMPT_CACHE_KEY_CRITIC,
        **cache_fields_for_model(model),
    }
    if use_schema:
        payload["text"] = {
            "format": {
                "type": "json_schema",
                "name": "task_critic",
                "strict": True,
                "schema": CRITIC_SCHEMA,
            }
        }
    else:
        payload["instructions"] = (
            CRITIC_INSTRUCTIONS + "\n\nSvar kun med ét JSON-objekt. Ingen markdown."
        )
    resp = client.responses.create(**payload)
    return str(get_value(resp, "output_text", "") or "")
