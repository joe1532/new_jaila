"""To-lags søgning for opgaveløsning. Python formulerer og kører opslagene."""

from __future__ import annotations

import logging
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from openai import OpenAI

from backend.services.legal_search import search_legal_sources
from backend.services.opslagsvaerk import lookup_hit_for_anchor

_log = logging.getLogger(__name__)

MAX_NORM_QUERIES = 3
MAX_ISSUE_B_QUERIES = 2
MAX_GAP_QUERIES = 2
RESULTS_PER_QUERY = 6
MAX_CHUNKS_PER_FILE = 2
MAX_STATUTE_CHUNKS_PER_FILE = 4
MAX_GAP_CHUNKS_PER_FILE = 1
MAX_CHUNK_CHARS = 3_000
MAX_CONTEXT_CHARS = 24_000
SEARCH_WORKERS = 4

LAW_ABBREVIATIONS = {
    "ll": "ligningsloven",
    "ksl": "kildeskatteloven",
    "psl": "personskatteloven",
    "sl": "statsskatteloven",
    "abl": "aktieavancebeskatningsloven",
    "pbl": "pensionsbeskatningsloven",
    "kgl": "kursgevinstloven",
    "ebl": "ejendomsavancebeskatningsloven",
    "sel": "selskabsskatteloven",
    "fbl": "fondsbeskatningsloven",
    "dbl": "dødsboskatteloven",
    "mbl": "momsloven",
    "al": "afskrivningsloven",
}

STATUTE_STEMS = tuple(
    sorted(
        {name[: -len("en")] if name.endswith("en") else name for name in LAW_ABBREVIATIONS.values()}
        | {"kildeskattelov", "ligningslov", "personskattelov", "statsskattelov"},
        key=len,
        reverse=True,
    )
)

_ABBREV_PATTERN = re.compile(
    r"\b(" + "|".join(sorted(LAW_ABBREVIATIONS, key=len, reverse=True)) + r")\s*§+\s*(\d+\s*[A-Za-z]?)",
    re.IGNORECASE,
)
_FULL_LAW_PATTERN = re.compile(
    r"\b([a-zæøå]{4,}lov(?:en|ens)?)\s*§+\s*(\d+\s*[A-Za-z]?)",
    re.IGNORECASE,
)
_DBO_PATTERN = re.compile(
    r"\b(?:dbo|dobbeltbeskatningsoverenskomst(?:en)?)\s*(?:art(?:ikel)?\.?\s*)(\d+)",
    re.IGNORECASE,
)
_SECTION_PATTERN = re.compile(r"(\d+)\s*([A-Za-z])?")
_BEK_PATTERN = re.compile(
    r"bekendtgørelse(?:n)?\s+nr\.?\s*(\d+)",
    re.IGNORECASE,
)
_HEADING_RE = re.compile(r"\b([A-Z]\.[A-Z]\.\d+(?:\.\d+)*)")
_TOKEN_RE = re.compile(r"[a-zæøå]+", re.IGNORECASE)

# Funktionsord og processprog. Ikke skatteretlige begreber.
_STOPWORDS = frozenset(
    {
        "anden",
        "anvendelse",
        "anvendes",
        "bestemmelse",
        "bestemmelsen",
        "blandt",
        "blev",
        "blive",
        "blevet",
        "både",
        "denne",
        "deres",
        "dette",
        "disse",
        "dog",
        "efter",
        "eller",
        "endvidere",
        "enten",
        "finder",
        "foregående",
        "første",
        "følgende",
        "gennem",
        "gælde",
        "gælder",
        "hans",
        "have",
        "havde",
        "hendes",
        "henholdsvis",
        "hvilken",
        "hvilket",
        "hvis",
        "ifølge",
        "ikke",
        "inden",
        "indkomstopgørelse",
        "indkomstopgørelsen",
        "jf",
        "kunne",
        "litra",
        "lov",
        "lovbekendtgørelse",
        "loven",
        "lovens",
        "mellem",
        "måtte",
        "nr",
        "også",
        "omfattet",
        "opfyldt",
        "over",
        "paragraf",
        "pkt",
        "punktum",
        "regler",
        "reglerne",
        "samt",
        "skattepligtig",
        "skattepligtige",
        "skulle",
        "stk",
        "sådan",
        "såfremt",
        "således",
        "tilsvarende",
        "uanset",
        "uden",
        "under",
        "være",
        "været",
    }
)

SearchFn = Callable[[str], list[dict[str, Any]]]


def extract_anchors(text: str) -> list[dict[str, str]]:
    """Udled lov- og DBO-henvisninger, med forkortelser foldet ud."""
    source = str(text or "")
    found: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(law: str, section: str, kind: str = "statute") -> None:
        label = f"{law} {section}".strip()
        key = label.lower()
        if not law or key in seen:
            return
        seen.add(key)
        found.append({"law": law, "section": section, "label": label, "kind": kind})

    for match in _ABBREV_PATTERN.finditer(source):
        add(LAW_ABBREVIATIONS[match.group(1).lower()], _canonical_section(match.group(2)))

    for match in _FULL_LAW_PATTERN.finditer(source):
        add(_canonical_law_name(match.group(1)), _canonical_section(match.group(2)))

    for match in _DBO_PATTERN.finditer(source):
        add("dobbeltbeskatningsoverenskomst", f"artikel {match.group(1)}", kind="dbo")

    return found


def extract_regulations(text: str) -> list[dict[str, str]]:
    """Udled bekendtgørelse nr. N. Samme slags adresse som en lovparagraf."""
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in _BEK_PATTERN.finditer(str(text or "")):
        number = match.group(1)
        label = f"bekendtgørelse nr. {number}"
        if label in seen:
            continue
        seen.add(label)
        found.append(
            {
                "law": "bekendtgørelse",
                "section": number,
                "label": label,
                "kind": "regulation",
            }
        )
    return found


def lookup_hits_for_text(text: str) -> list[dict[str, Any]]:
    """Slå LL-ankre i teksten op. Tom liste hvis ingen ligningslovsanker."""
    hits: list[dict[str, Any]] = []
    seen: set[str] = set()
    for anchor in extract_anchors(text)[:MAX_NORM_QUERIES]:
        hit = lookup_hit_for_anchor(anchor)
        if not hit:
            continue
        file_id = str(hit.get("file_id") or "")
        if file_id in seen:
            continue
        seen.add(file_id)
        hits.append(hit)
    return hits


def lookup_pack_for_chat(message: str) -> dict[str, Any]:
    """Paragrafnoder til almindelig chat. file_search må stadig hente praksis."""
    hits = lookup_hits_for_text(message)
    searches = [
        {
            "queries": [f"Opslag: {hit.get('anchor') or hit.get('filename') or ''}"],
            "status": "completed",
            "num_results": 1,
            "layer": "A",
            "source": "opslag",
        }
        for hit in hits
    ]
    return {
        "retrieved_chunks": hits,
        "retrieved_sources": _sources_from_chunks(hits),
        "searches": searches,
        "context_text": (
            format_retrieved_context(hits, allow_extra_search=True) if hits else ""
        ),
        "diagnosis_question": str(message or ""),
        "keep_file_search": True,
    }


def build_search_plan(
    issues: list[dict[str, Any]] | None,
    legal_locus: str = "",
    message: str = "",
) -> dict[str, Any]:
    """Lag A: unikke ankre. Lag B: personkreds for ankeret + issue-opslag med sagens ord."""
    issue_rows = [item for item in (issues or []) if isinstance(item, dict)]
    blobs = [legal_locus, message]
    for item in issue_rows:
        blobs.append(_issue_question(item))
    anchors = extract_anchors("\n".join(blobs))

    norm_queries: list[dict[str, str]] = []
    for anchor in anchors[:MAX_NORM_QUERIES]:
        norm_queries.append(
            {
                "layer": "A",
                "query": _norm_query(anchor),
                "anchor": anchor["label"],
                "issue_id": "",
            }
        )
    if not norm_queries:
        seed = (legal_locus or _issue_question(issue_rows[0]) if issue_rows else message).strip()
        seed = seed[:180] or "skatteret lovtekst"
        norm_queries.append(
            {
                "layer": "A",
                "query": f"{seed} lovtekst lovbekendtgørelse",
                "anchor": seed,
                "issue_id": "",
            }
        )

    interpretive_queries: list[dict[str, str]] = []
    primary = anchors[0] if anchors else None
    if primary:
        interpretive_queries.append(
            {
                "layer": "B",
                "query": _scope_query(primary),
                "anchor": primary["label"],
                "issue_id": "scope",
            }
        )

    excerpt = _fact_excerpt(message)
    b_issues = issue_rows[:MAX_ISSUE_B_QUERIES] or [
        {
            "id": "I",
            "question": (legal_locus or excerpt or message)[:180] or "skatteretlig fortolkning",
        }
    ]
    for item in b_issues:
        question = _issue_question(item) or (legal_locus or excerpt)[:180]
        related = extract_anchors(question) or anchors[:1]
        related_label = " ".join(anchor["label"] for anchor in related[:2])
        interpretive_queries.append(
            {
                "layer": "B",
                "query": " ".join(
                    part
                    for part in (
                        question,
                        related_label,
                        excerpt,
                        "praksis Den juridiske vejledning afgørelse SKM",
                    )
                    if part
                ),
                "anchor": related_label,
                "issue_id": str(item.get("id") or item.get("issue_id") or ""),
            }
        )

    return {
        "anchors": anchors,
        "norm_queries": norm_queries,
        "interpretive_queries": interpretive_queries,
    }


def _ligningslov_anchors(anchors: list[dict[str, str]]) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    for anchor in anchors:
        if anchor.get("kind") == "dbo":
            continue
        if _canonical_law_name(anchor.get("law") or "") == "ligningsloven":
            found.append(anchor)
    return found


def _resolve_lookups(
    queries: list[dict[str, str]],
    searches: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Slå LL-ankre op. Resten går til vektorsøgning."""
    hits: list[dict[str, Any]] = []
    remaining: list[dict[str, str]] = []
    for item in queries:
        hit = _lookup_query(item)
        if not hit:
            remaining.append(item)
            continue
        layer = item.get("layer") or "A"
        if layer == "gap":
            hit = {**hit, "layer": "gap"}
        hits.append(hit)
        searches.append(
            {
                "queries": [f"Opslag: {item.get('anchor') or item.get('query') or ''}"],
                "status": "completed",
                "num_results": 1,
                "layer": layer,
                "source": "opslag",
            }
        )
    return hits, remaining


def _lookup_query(item: dict[str, str]) -> dict[str, Any] | None:
    blob = " ".join(
        part for part in (item.get("anchor") or "", item.get("query") or "") if part
    )
    for anchor in extract_anchors(blob):
        hit = lookup_hit_for_anchor(anchor)
        if hit:
            tagged = dict(hit)
            tagged["issue_id"] = item.get("issue_id") or ""
            tagged["anchor"] = item.get("anchor") or tagged.get("anchor") or ""
            return tagged
    return None


def run_layered_search(
    client: OpenAI,
    message: str,
    legal_locus: str = "",
    issues: list[dict[str, Any]] | None = None,
    vector_store_ids: list[str] | None = None,
    search_fn: SearchFn | None = None,
) -> dict[str, Any]:
    """Kør A, derefter B, derefter højst én hul-runde. Returnér pakke til notatet."""
    plan = build_search_plan(issues, legal_locus=legal_locus, message=message)
    if search_fn:
        worker_a = worker_b = search_fn
    else:
        def worker_a(query: str) -> list[dict[str, Any]]:
            return search_legal_sources(
                client,
                query,
                max_results=RESULTS_PER_QUERY,
                vector_store_ids=vector_store_ids,
                rewrite_query=False,
            )

        def worker_b(query: str) -> list[dict[str, Any]]:
            return search_legal_sources(
                client,
                query,
                max_results=RESULTS_PER_QUERY,
                vector_store_ids=vector_store_ids,
                rewrite_query=True,
            )

    searches: list[dict[str, Any]] = []
    if not _ligningslov_anchors(plan["anchors"]):
        searches.append(
            {
                "queries": ["Opslag: intet ligningslovsanker — intet paragrafopslag"],
                "status": "skipped",
                "num_results": 0,
                "layer": "A",
                "source": "opslag",
            }
        )
    hits_lookup_a, remaining_a = _resolve_lookups(plan["norm_queries"], searches)
    hits_a = hits_lookup_a + _run_query_batch(remaining_a, worker_a, searches)
    open_doors = _open_doors(hits_a, message, issues)
    plan["open_doors"] = [door["label"] for door in open_doors]
    if open_doors:
        searches.append(
            {
                "queries": [
                    "Døre: " + ", ".join(door["label"] for door in open_doors)
                ],
                "status": "completed",
                "num_results": len(open_doors),
                "layer": "A",
                "source": "døre",
            }
        )
        door_query = _door_b_query(open_doors, plan["anchors"], message)
        if door_query:
            existing = plan["interpretive_queries"]
            plan["interpretive_queries"] = (
                [existing[0], door_query, *existing[1:]]
                if existing
                else [door_query]
            )
    hits_b = _filter_layer_b(
        _run_query_batch(plan["interpretive_queries"], worker_b, searches),
        plan["anchors"],
        open_doors=open_doors,
    )

    gap_queries = _gap_queries(
        plan["anchors"],
        hits_a,
        hits_b=hits_b,
        doors=open_doors,
    )
    hits_lookup_gap, remaining_gap = _resolve_lookups(gap_queries, searches)
    hits_gap = hits_lookup_gap + _run_query_batch(remaining_gap, worker_a, searches)

    lookup_hits = [hit for hit in hits_a + hits_gap if hit.get("from_lookup")]
    hits_a = _drop_replaced_statute_files(hits_a, lookup_hits)
    hits_gap = _filter_gap_statute_nodes(
        _drop_replaced_statute_files(hits_gap, lookup_hits)
    )
    chunks = _pack_chunks(hits_a, hits_b, hits_gap, anchors=plan["anchors"])
    sources = _sources_from_chunks(chunks)
    diagnosis_question = " ".join(
        [legal_locus, message] + [anchor["label"] for anchor in plan["anchors"]]
        + [item["anchor"] for item in gap_queries]
    )
    return {
        "plan": plan,
        "retrieved_chunks": chunks,
        "retrieved_sources": sources,
        "searches": searches,
        "context_text": format_retrieved_context(chunks, open_doors=open_doors),
        "diagnosis_question": diagnosis_question,
    }


def format_retrieved_context(
    chunks: list[dict[str, Any]],
    open_doors: list[dict[str, str]] | None = None,
    allow_extra_search: bool = False,
) -> str:
    """Pak hentede uddrag, så notatet kan skrives uden file_search."""
    if not chunks:
        return ""
    has_lookup = any(chunk.get("from_lookup") for chunk in chunks)
    if has_lookup and allow_extra_search:
        intro = (
            "Lag A er slået op som paragrafnode, ikke søgt. Hele noden fra LBKG 1500. "
            "Du må også slå praksis og vejledning op. Brug ikke andre uddrag af samme "
            "lov som erstatning for noden. Gengiv ikke lovtekst fra intern viden."
        )
    elif has_lookup:
        intro = (
            "Lag A er slået op som paragrafnode, ikke søgt. Hele noden fra LBKG 1500. "
            "Lag B er semantisk søgning bundet til samme anker. Du må kun bruge "
            "uddragene nedenfor og materiale, brugeren selv har lagt op. Gengiv ikke "
            "lovtekst fra intern viden."
        )
    else:
        intro = (
            "Systemet har søgt i to lag: først lovtekst, derefter praksis og "
            "Den juridiske vejledning. Du må kun bruge uddragene nedenfor og "
            "materiale, brugeren selv har lagt op. Gengiv ikke lovtekst fra intern viden."
        )
    if open_doors:
        labels = ", ".join(door["label"] for door in open_doors)
        intro += (
            f" Python har åbnet disse stykker ud fra faktum: {labels}. "
            "Henvisninger i øvrige stykker er ikke hentet som hul. "
            "Konkludér ikke på et åbent stykke, der mangler fortolkningsgrundlag."
        )
    lines = ["[Hentede retskilder]", intro, ""]
    current_layer = ""
    used = 0
    # Opslag, derefter B (ankerets praksis), derefter hul. Ellers æder KSL/SL
    # henvisninger i noden de 24.000 tegn, før DJV kommer med.
    ordered = _prompt_chunk_order(chunks)
    for chunk in ordered:
        layer = str(chunk.get("layer") or "")
        heading = {
            "A": "## Lag A — normgrundlag",
            "B": "## Lag B — fortolkningsgrundlag",
            "gap": "## Lag A — hulopslag",
        }.get(layer)
        if heading and layer != current_layer:
            lines.append(heading)
            current_layer = layer
        filename = str(chunk.get("filename") or "ukendt kilde")
        text = str(chunk.get("text") or "").strip()
        if not text:
            continue
        notice = str(chunk.get("lookup_notice") or "").strip()
        block = f"### {filename}\n{notice}\n{text}" if notice else f"### {filename}\n{text}"
        # Opslåede noder klippes ikke. Vector-uddrag fylder resten af budgettet.
        if not chunk.get("from_lookup") and used + len(block) > MAX_CONTEXT_CHARS:
            break
        lines.append(block)
        used += len(block)
    lines.append("[/Hentede retskilder]")
    return "\n\n".join(lines).strip()


def prefetch_chat_retrieval(
    client: OpenAI,
    query: str,
    vector_store_ids: list[str] | None = None,
    search_fn: SearchFn | None = None,
) -> dict[str, Any]:
    """Opslag af LL-noder plus semantisk søgning. Bruges når modellen ikke selv søger."""
    clean = str(query or "").strip()
    lookups = lookup_hits_for_text(clean)
    if not clean and not lookups:
        return {
            "retrieved_chunks": [],
            "retrieved_sources": [],
            "searches": [],
            "context_text": "",
            "diagnosis_question": "",
        }
    if search_fn:
        raw_hits = list(search_fn(clean) or []) if clean else []
    elif client is not None and clean:
        raw_hits = search_legal_sources(
            client,
            clean,
            max_results=10,
            vector_store_ids=vector_store_ids,
            rewrite_query=True,
        )
    else:
        raw_hits = []
    semantic: list[dict[str, Any]] = []
    for hit in raw_hits:
        text = str(hit.get("text") or "").strip()
        if not text:
            continue
        semantic.append(
            {
                "file_id": str(hit.get("file_id") or ""),
                "filename": str(hit.get("filename") or ""),
                "score": str(hit.get("score") or ""),
                "text": text[:MAX_CHUNK_CHARS] if not hit.get("from_lookup") else text,
                "layer": "B",
            }
        )
    semantic = _drop_replaced_statute_files(semantic, lookups)
    chunks = lookups + semantic
    searches: list[dict[str, Any]] = [
        {
            "queries": [f"Opslag: {hit.get('anchor') or hit.get('filename') or ''}"],
            "status": "completed",
            "num_results": 1,
            "layer": "A",
            "source": "opslag",
        }
        for hit in lookups
    ]
    if clean:
        searches.append(
            {"queries": [clean], "status": "completed", "num_results": len(semantic)}
        )
    has_lookup = bool(lookups)
    return {
        "retrieved_chunks": chunks,
        "retrieved_sources": _sources_from_chunks(chunks),
        "searches": searches,
        "context_text": (
            format_retrieved_context(chunks)
            if has_lookup
            else format_flat_retrieved_context(chunks)
        ),
        "diagnosis_question": clean,
        "keep_file_search": False,
    }


def format_flat_retrieved_context(chunks: list[dict[str, Any]]) -> str:
    """Pak hentede uddrag uden to-lags-overskrifter. Bruges til almindelig Grok-chat."""
    if not chunks:
        return ""
    lines = [
        "[Hentede retskilder]",
        "Systemet har søgt i retskildesamlingen. Du må kun bruge uddragene "
        "nedenfor og materiale, brugeren selv har lagt op. Gengiv ikke lovtekst "
        "fra intern viden.",
        "",
    ]
    used = 0
    for chunk in chunks:
        filename = str(chunk.get("filename") or "ukendt kilde")
        text = str(chunk.get("text") or "").strip()
        if not text:
            continue
        block = f"### {filename}\n{text}"
        if used + len(block) > MAX_CONTEXT_CHARS:
            break
        lines.append(block)
        used += len(block)
    lines.append("[/Hentede retskilder]")
    return "\n\n".join(lines).strip()


def compose_write_input(
    message: str,
    prefetch_context: str,
    uploaded_context: str = "",
    framing: str = "",
) -> str:
    """Brugerens opgave + oplagt materiale + de hentede kilder."""
    parts = [str(message or "").strip()]
    uploaded = str(uploaded_context or "").strip()
    if uploaded:
        block = (
            "---\n[Materiale lagt op af brugeren]\n"
            + uploaded
            + "\n[/Materiale lagt op af brugeren]\n---"
        )
        if framing.strip():
            block = block + "\n" + framing.strip()
        parts.append(block)
    prefetch = str(prefetch_context or "").strip()
    if prefetch:
        parts.append(prefetch)
    return "\n\n".join(part for part in parts if part)


def filename_looks_like_statute(filename: str) -> bool:
    name = str(filename or "").replace("\\", "/").rsplit("/", 1)[-1].lower().strip()
    if not name:
        return False
    return any(name.startswith(stem) for stem in STATUTE_STEMS)


def _canonical_law_name(raw: str) -> str:
    match = re.match(r"(.+lov)(?:en|ens|e|s)?$", str(raw or "").lower().strip())
    if not match:
        return str(raw or "").lower().strip()
    return match.group(1) + "en"


def _canonical_section(raw: str) -> str:
    match = _SECTION_PATTERN.match(str(raw or "").strip())
    if not match:
        return f"§ {str(raw or '').strip()}"
    letter = (match.group(2) or "").upper()
    return f"§ {match.group(1)}" + (f" {letter}" if letter else "")


def _norm_query(anchor: dict[str, str]) -> str:
    if anchor.get("kind") == "dbo":
        return f"{anchor['law']} {anchor['section']} overenskomst"
    if anchor.get("kind") == "regulation":
        return f"{anchor['label']} bekendtgørelse"
    section = anchor["section"]
    return (
        f"{anchor['law']} {section} \"{section}.\" stk. 1 "
        "lovtekst lovbekendtgørelse"
    )


def _scope_query(anchor: dict[str, str]) -> str:
    """Fortolkning af hvem bestemmelsen omfatter - uden at gætte statusord."""
    return (
        f"{anchor['law']} {anchor['section']} hvem kan anvende personkreds "
        "skattepligt Den juridiske vejledning"
    )


def _fact_excerpt(message: str, max_chars: int = 180) -> str:
    """Sagens egne ord med i B-query. Supplementer har forrang for det første snapshot."""
    text = str(message or "").strip()
    text = re.sub(r"^faktum:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(
        r"\n\s*retligt udgangspunkt:.*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    parts = re.split(
        r"\n\s*supplerende oplysninger:?\s*",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )
    original = " ".join(parts[0].split())
    supplements = " ".join(parts[1].split()) if len(parts) > 1 else ""
    if supplements:
        blob = f"{supplements} {original}".strip()
        return blob[:max_chars]
    return original[:max_chars]


def _issue_question(item: dict[str, Any]) -> str:
    return str(item.get("question") or item.get("legal_question") or "").strip()


def _content_tokens(text: str) -> set[str]:
    found: set[str] = set()
    for raw in _TOKEN_RE.findall(str(text or "").lower()):
        if len(raw) < 5 or raw in _STOPWORDS:
            continue
        found.add(raw)
    return found


def _door_fact_blob(message: str, issues: list[dict[str, Any]] | None) -> str:
    parts = [str(message or "")]
    for item in issues or []:
        if isinstance(item, dict):
            parts.append(_issue_question(item))
    return "\n".join(parts)


def _open_doors(
    hits_a: list[dict[str, Any]],
    message: str,
    issues: list[dict[str, Any]] | None,
) -> list[dict[str, str]]:
    """Åbn stk. 1 altid. Øvrige stk. kun hvis faktum rammer ord, der er sjældne i noden."""
    facts = _content_tokens(_door_fact_blob(message, issues))
    opened: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for hit in hits_a:
        subs = hit.get("lookup_subsections") or []
        if not isinstance(subs, list) or not subs:
            continue
        for door in _doors_for_node(subs, facts):
            key = (str(hit.get("file_id") or ""), door["label"])
            if key in seen:
                continue
            seen.add(key)
            opened.append(door)
    return opened


def _doors_for_node(
    subsections: list[Any],
    fact_tokens: set[str],
) -> list[dict[str, str]]:
    rows: list[tuple[str, str, set[str]]] = []
    for item in subsections:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip() or f"Stk. {len(rows) + 1}."
        text = str(item.get("text") or item.get("leadText") or "").strip()
        if not text:
            continue
        rows.append((label, text, _content_tokens(text)))
    if not rows:
        return []
    df: Counter[str] = Counter()
    for _label, _text, tokens in rows:
        df.update(tokens)
    opened: list[dict[str, str]] = []
    for index, (label, text, tokens) in enumerate(rows):
        rare = {token for token in tokens if df[token] <= 2}
        if index == 0 or fact_tokens & rare:
            opened.append({"label": label, "text": text})
    return opened


def _door_search_terms(doors: list[dict[str, str]]) -> list[str]:
    """Stk. 1 først. Ellers æder lange ord fra sats-stykker rejsebegrebet."""
    ordered: list[str] = []
    seen: set[str] = set()
    for door in doors:
        tokens = [
            token
            for token in _content_tokens(door.get("text") or "")
            if len(token) >= 6
        ]
        for token in sorted(tokens, key=lambda item: (-len(item), item)):
            if token in seen:
                continue
            seen.add(token)
            ordered.append(token)
            if len(ordered) >= 12:
                return ordered
    return ordered


def _door_b_query(
    open_doors: list[dict[str, str]],
    anchors: list[dict[str, str]],
    message: str,
) -> dict[str, str] | None:
    terms = " ".join(_door_search_terms(open_doors))
    if not terms:
        return None
    primary = anchors[0]["label"] if anchors else ""
    excerpt = _fact_excerpt(message)
    return {
        "layer": "B",
        "query": " ".join(
            part
            for part in (
                primary,
                terms,
                excerpt,
                "praksis Den juridiske vejledning afgørelse SKM bekendtgørelse",
            )
            if part
        ),
        "anchor": primary,
        "issue_id": "døre",
    }


def _heading_code(hit: dict[str, Any]) -> str:
    blob = f"{hit.get('filename') or ''}\n{str(hit.get('text') or '')[:400]}"
    match = _HEADING_RE.search(blob)
    return match.group(1) if match else ""


def _heading_family(hit: dict[str, Any]) -> str:
    parts = _heading_code(hit).split(".")
    if len(parts) >= 3:
        return ".".join(parts[:3])
    return ".".join(parts) if parts and parts[0] else ""


def _heading_pack_key(hit: dict[str, Any]) -> str:
    parts = _heading_code(hit).split(".")
    if len(parts) >= 4:
        return ".".join(parts[:4])
    return _heading_code(hit)


def _prefer_distinct_headings(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Første pass: én bid pr. DJV-sektion. Resten bagefter, så skema ikke æder begreb."""
    ranked = sorted(hits, key=_score, reverse=True)
    first: list[dict[str, Any]] = []
    rest: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, hit in enumerate(ranked):
        key = _heading_pack_key(hit) or f"none:{index}"
        if key in seen:
            rest.append(hit)
            continue
        seen.add(key)
        first.append(hit)
    return first + rest


def _door_term_hits(hit: dict[str, Any], terms: list[str]) -> int:
    blob = f"{hit.get('filename') or ''}\n{hit.get('text') or ''}".lower()
    return sum(1 for term in terms if term in blob)


def _hit_is_competing_anchor(
    hit: dict[str, Any],
    anchors: list[dict[str, str]],
) -> bool:
    """Sandt når uddraget handler om en anden paragraf i samme lov."""
    blob = f"{hit.get('filename') or ''}\n{hit.get('text') or ''}"
    lead = blob[:240]
    for extra in extract_anchors(blob):
        if extra.get("kind") != "statute":
            continue
        for anchor in anchors:
            if extra.get("law") != anchor.get("law"):
                continue
            if extra.get("section") == anchor.get("section"):
                continue
            if _section_in_text(extra, lead) and not _section_in_text(anchor, lead):
                return True
    return False


def _run_query_batch(
    queries: list[dict[str, str]],
    search_fn: SearchFn,
    searches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not queries:
        return []
    hits_by_index: dict[int, list[dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=min(SEARCH_WORKERS, len(queries))) as pool:
        futures = {
            pool.submit(_safe_search, search_fn, item["query"]): index
            for index, item in enumerate(queries)
        }
        for future in as_completed(futures):
            index = futures[future]
            item = queries[index]
            try:
                raw_hits = future.result()
            except Exception as exc:
                _log.warning("task_search query fejlede (%s): %s", item.get("query"), exc)
                raw_hits = []
            hits_by_index[index] = [_tag_hit(hit, item) for hit in raw_hits]
    ordered: list[dict[str, Any]] = []
    for index, item in enumerate(queries):
        tagged = hits_by_index.get(index) or []
        ordered.extend(tagged)
        searches.append(
            {
                "queries": [_prefixed_query(item)],
                "status": "completed" if tagged else "empty",
                "num_results": len(tagged),
                "layer": item.get("layer") or "",
            }
        )
    return ordered


def _safe_search(search_fn: SearchFn, query: str) -> list[dict[str, Any]]:
    try:
        return list(search_fn(query) or [])
    except Exception:
        _log.exception("task_search: søgning fejlede for %r", query)
        return []


def _tag_hit(hit: dict[str, Any], item: dict[str, str]) -> dict[str, Any]:
    text = str(hit.get("text") or "").strip()
    # Opslåede noder er hele paragrafen. Klip ikke. Vector-hits er stadig uddrag.
    if not hit.get("from_lookup") and len(text) > MAX_CHUNK_CHARS:
        text = text[:MAX_CHUNK_CHARS].rstrip() + "…"
    score = hit.get("score", "")
    return {
        "file_id": str(hit.get("file_id") or ""),
        "filename": str(hit.get("filename") or ""),
        "score": str(score),
        "text": text,
        "layer": item.get("layer") or "",
        "anchor": item.get("anchor") or "",
        "issue_id": item.get("issue_id") or "",
        "from_lookup": bool(hit.get("from_lookup")),
        "lookup_notice": str(hit.get("lookup_notice") or ""),
    }


def _prefixed_query(item: dict[str, str]) -> str:
    prefix = {"A": "Norm", "B": "Fortolkning", "gap": "Hul"}.get(item.get("layer") or "", "Søgning")
    return f"{prefix}: {item.get('query') or ''}"


def _gap_queries(
    anchors: list[dict[str, str]],
    hits_a: list[dict[str, Any]],
    hits_b: list[dict[str, Any]] | None = None,
    doors: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Én hul-runde: manglende anker, henvisning i åbne døre, eller bekendtgørelse i B."""
    known_labels = {anchor["label"].lower() for anchor in anchors}
    missing = [
        anchor
        for anchor in anchors
        if anchor.get("kind") != "regulation" and not _anchor_found(anchor, hits_a)
    ]
    cited: list[dict[str, str]] = []
    door_blobs = (
        [str(door.get("text") or "") for door in doors]
        if doors
        else [
            str(hit.get("text") or "")
            for hit in hits_a
            if filename_looks_like_statute(str(hit.get("filename") or ""))
        ]
    )
    b_blobs = [
        f"{hit.get('filename') or ''}\n{hit.get('text') or ''}"
        for hit in hits_b or []
    ]

    def take(extras: list[dict[str, str]]) -> bool:
        for extra in extras:
            if extra["label"].lower() in known_labels:
                continue
            known_labels.add(extra["label"].lower())
            cited.append(extra)
            if len(cited) >= MAX_GAP_QUERIES:
                return True
        return False

    for blob in door_blobs:
        if take(extract_anchors(blob) + extract_regulations(blob)):
            break
    if len(cited) < MAX_GAP_QUERIES:
        for blob in b_blobs:
            if take(extract_regulations(blob)):
                break

    gap_anchors = (missing + cited)[:MAX_GAP_QUERIES]
    queries: list[dict[str, str]] = []
    for anchor in gap_anchors:
        queries.append(
            {
                "layer": "gap",
                "query": _norm_query(anchor),
                "anchor": anchor["label"],
                "issue_id": "",
            }
        )
    return queries


def _anchor_found(anchor: dict[str, str], hits: list[dict[str, Any]]) -> bool:
    """Kræver det rigtige dokument *og* at uddraget er paragrafnoden, ikke en henvisning."""
    if anchor.get("kind") == "dbo":
        needle = "overenskomst"
        for hit in hits:
            name = str(hit.get("filename") or "").lower()
            if needle in name or "dbo" in name:
                return True
        return False
    law_stem = _canonical_law_name(anchor["law"])
    if law_stem.endswith("en"):
        law_stem = law_stem[: -len("en")]
    for hit in hits:
        filename = str(hit.get("filename") or "").lower()
        if not (law_stem in filename and filename_looks_like_statute(filename)):
            continue
        if _section_is_node(anchor, str(hit.get("text") or "")):
            return True
    return False


def _filter_layer_b(
    hits: list[dict[str, Any]],
    anchors: list[dict[str, str]],
    open_doors: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Lag B er fortolkning af ankeret. Lovtekst og nabostykker hører ikke hjemme her."""
    statute_anchors = [
        item for item in anchors if item.get("kind") not in {"dbo", "regulation"}
    ]
    interpretive: list[dict[str, Any]] = []
    dropped = 0
    for hit in hits:
        if filename_looks_like_statute(str(hit.get("filename") or "")):
            dropped += 1
            continue
        interpretive.append(hit)

    seeds = [
        hit for hit in interpretive if _hit_mentions_any_anchor(hit, statute_anchors)
    ]
    seed_families = {family for hit in seeds if (family := _heading_family(hit))}
    door_terms = _door_search_terms(open_doors or [])

    kept: list[dict[str, Any]] = []
    for hit in interpretive:
        if statute_anchors and _hit_is_competing_anchor(hit, statute_anchors):
            dropped += 1
            continue
        bound = (
            not statute_anchors
            or _hit_mentions_any_anchor(hit, statute_anchors)
            or bool(_heading_family(hit) and _heading_family(hit) in seed_families)
            or _door_term_hits(hit, door_terms) >= 2
        )
        if not bound:
            dropped += 1
            continue
        kept.append(hit)
    if dropped:
        _log.info("task_search: dropped %s lag-B hits not bound to anchors", dropped)
    return kept


def _drop_replaced_statute_files(
    hits: list[dict[str, Any]],
    lookup_hits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Når noden er slået op, må samme lovs PDF-chunks ikke ind som erstatning."""
    laws = _laws_from_lookup(lookup_hits)
    if not laws:
        return hits
    kept: list[dict[str, Any]] = []
    for hit in hits:
        if hit.get("from_lookup"):
            kept.append(hit)
            continue
        filename = str(hit.get("filename") or "")
        if filename_looks_like_statute(filename) and any(
            _law_in_filename(law, filename) for law in laws
        ):
            continue
        kept.append(hit)
    return kept


def _laws_from_lookup(lookup_hits: list[dict[str, Any]]) -> set[str]:
    found: set[str] = set()
    for hit in lookup_hits:
        filename = str(hit.get("filename") or "")
        for law in LAW_ABBREVIATIONS.values():
            if _law_in_filename(law, filename):
                found.add(law)
    return found


def _law_in_filename(law: str, filename: str) -> bool:
    name = str(filename or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
    stem = law[: -len("en")] if law.endswith("en") else law
    return stem in name


def _hit_mentions_any_anchor(hit: dict[str, Any], anchors: list[dict[str, str]]) -> bool:
    blob = f"{hit.get('filename') or ''}\n{hit.get('text') or ''}"
    return any(_section_in_text(anchor, blob) for anchor in anchors)


def _section_in_text(anchor: dict[str, str], text: str) -> bool:
    source = str(text or "")
    number, letter = _section_parts(anchor)
    if number is None:
        return False
    if letter:
        return bool(re.search(rf"§+\s*{number}\s*{letter}\b", source, re.IGNORECASE))
    if str(anchor.get("section") or "").lower().startswith("artikel"):
        return bool(re.search(rf"\bartikel\s*{number}\b", source, re.IGNORECASE))
    return bool(re.search(rf"§+\s*{number}(?!\d|[A-Za-zÆØÅæøå])", source, re.IGNORECASE))


def _section_is_node(anchor: dict[str, str], text: str) -> bool:
    """Sandt når uddraget *er* bestemmelsen, ikke en henvisning til den."""
    source = str(text or "")
    if anchor.get("kind") == "dbo":
        return "artikel" in source.lower()
    number, letter = _section_parts(anchor)
    if number is None:
        return False
    letter_pat = rf"\s*{letter}" if letter else r"(?!\s*[A-Za-zÆØÅæøå])"
    heading = re.compile(
        rf"(?m)^[ \t]*§+\s*{number}{letter_pat}\b",
        re.IGNORECASE,
    )
    stk = re.compile(
        rf"§+\s*{number}{letter_pat}\s*,\s*stk",
        re.IGNORECASE,
    )
    return bool(heading.search(source) or stk.search(source))


def _section_parts(anchor: dict[str, str]) -> tuple[str | None, str]:
    section = str(anchor.get("section") or "")
    if section.lower().startswith("artikel"):
        number = re.search(r"\d+", section)
        return (number.group(0) if number else None, "")
    match = _SECTION_PATTERN.search(section.replace("§", "").strip())
    if not match:
        return (None, "")
    return (match.group(1), match.group(2) or "")


def _hit_is_section_node(hit: dict[str, Any], anchors: list[dict[str, str]]) -> bool:
    text = str(hit.get("text") or "")
    label = str(hit.get("anchor") or "")
    candidates = extract_anchors(label) or anchors
    return any(_section_is_node(anchor, text) for anchor in candidates)


def _prompt_chunk_order(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lookup = [chunk for chunk in chunks if chunk.get("from_lookup")]
    bound_b = [
        chunk
        for chunk in chunks
        if chunk.get("layer") == "B" and not chunk.get("from_lookup")
    ]
    rest = [
        chunk
        for chunk in chunks
        if not chunk.get("from_lookup") and chunk.get("layer") != "B"
    ]
    return lookup + bound_b + rest


def _filter_gap_statute_nodes(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hul-runden må kun lægge den citerede paragrafnode ind, ikke nabosider."""
    kept: list[dict[str, Any]] = []
    for hit in hits:
        if hit.get("from_lookup"):
            kept.append(hit)
            continue
        filename = str(hit.get("filename") or "")
        if not filename_looks_like_statute(filename):
            kept.append(hit)
            continue
        gap_anchors = extract_anchors(str(hit.get("anchor") or ""))
        if gap_anchors and _hit_is_section_node(hit, gap_anchors):
            kept.append(hit)
    return kept


def _pack_chunks(
    norm_hits: list[dict[str, Any]],
    interpretive_hits: list[dict[str, Any]],
    gap_hits: list[dict[str, Any]] | None = None,
    anchors: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Opslag og A, derefter B, derefter hul. B må ikke tabes til henvisninger i noden."""

    def rank(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            hits,
            key=lambda hit: (
                0 if hit.get("from_lookup") else 1,
                0 if filename_looks_like_statute(str(hit.get("filename") or "")) else 1,
                0 if _hit_is_section_node(hit, anchors or []) else 1,
                -_score(hit),
            ),
        )

    packed: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    per_file: dict[str, int] = {}
    for hit in rank(norm_hits) + _prefer_distinct_headings(interpretive_hits) + rank(
        gap_hits or []
    ):
        key = (str(hit.get("file_id") or ""), str(hit.get("text") or "")[:200])
        if not hit.get("text") or key in seen:
            continue
        file_id = str(hit.get("file_id") or hit.get("filename") or "")
        filename = str(hit.get("filename") or "")
        if hit.get("layer") == "gap" and not hit.get("from_lookup"):
            limit = MAX_GAP_CHUNKS_PER_FILE
        elif filename_looks_like_statute(filename):
            limit = MAX_STATUTE_CHUNKS_PER_FILE
        else:
            limit = MAX_CHUNKS_PER_FILE
        if per_file.get(file_id, 0) >= limit:
            continue
        seen.add(key)
        per_file[file_id] = per_file.get(file_id, 0) + 1
        packed.append(hit)
    return packed


def _sources_from_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for chunk in chunks:
        file_id = str(chunk.get("file_id") or "")
        filename = str(chunk.get("filename") or "")
        key = (file_id, filename)
        if not file_id or key in seen:
            continue
        seen.add(key)
        sources.append({"file_id": file_id, "filename": filename})
    return sources


def _score(hit: dict[str, Any]) -> float:
    try:
        return float(hit.get("score") or 0)
    except (TypeError, ValueError):
        return 0.0
