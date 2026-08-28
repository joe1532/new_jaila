"""To-lags søgning for opgaveløsning. Python formulerer og kører opslagene."""

from __future__ import annotations

import logging
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from openai import OpenAI

from backend.config import FALLBACK_MODEL, PRIMARY_MODEL
from backend.services.djv_opslag import lookup_djv_hits
from backend.services.legal_search import search_legal_sources
from backend.services.opslagsvaerk import lookup_hit_for_anchor

_log = logging.getLogger(__name__)

MAX_NORM_QUERIES = 3
MAX_ISSUE_B_QUERIES = 2
MAX_GAP_QUERIES = 2
MAX_DISCOVERY_ANCHORS = 3
DISCOVERY_WINDOW_CHARS = 180
RESULTS_PER_QUERY = 6
MAX_CHUNKS_PER_FILE = 2
MAX_STATUTE_CHUNKS_PER_FILE = 4
MAX_GAP_CHUNKS_PER_FILE = 1
MAX_CHUNK_CHARS = 3_000
MAX_CONTEXT_CHARS = 24_000
SEARCH_WORKERS = 4
MAX_REWRITE_CHARS = 240
LAYER0_REWRITE_CACHE_KEY = "jaila-layer0-rewrite-v1"
LAYER0_REWRITE_INSTRUCTIONS = """Du skriver én søgestreng til JAILAs danske skatteretlige kilder.
Ikke et svar. Ikke en analyse. Én linje, højst 200 tegn.
Brug sagens distinkte emneord. Du må nævne lov og paragraf som søgeord,
hvis teksten peger på det; det er ikke et facit.
Ingen citationstegn. Ingen markdown."""


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

# Bogstav kun som paragrafsuffiks (9 A). Ikke «stk» og ikke næste ord («ligningsloven»).
_SECTION_CAPTURE = r"(\d+(?:\s*[A-Za-z](?![A-Za-zæøåÆØÅ]))?)"
_ABBREV_PATTERN = re.compile(
    r"\b("
    + "|".join(sorted(LAW_ABBREVIATIONS, key=len, reverse=True))
    + r")\s*§+\s*"
    + _SECTION_CAPTURE,
    re.IGNORECASE,
)
_FULL_LAW_PATTERN = re.compile(
    r"\b([a-zæøå]{4,}lov(?:en|ens)?)\s*§+\s*" + _SECTION_CAPTURE,
    re.IGNORECASE,
)
_DBO_PATTERN = re.compile(
    r"\b(?:dbo|dobbeltbeskatningsoverenskomst(?:en)?)\s*(?:art(?:ikel)?\.?\s*)(\d+)",
    re.IGNORECASE,
)
_SECTION_PATTERN = re.compile(
    r"(\d+)(?:\s*([A-Za-z])(?![A-Za-zæøåÆØÅ]))?",
    re.IGNORECASE,
)
_BEK_PATTERN = re.compile(
    r"bekendtgørelse(?:n)?(?:[^.\n]{0,80})?\s+nr\.?\s*(\d+)",
    re.IGNORECASE,
)
_LOV_NAME_RE = re.compile(r"\b([a-zæøå]{4,}lov(?:en|ens)?)\b", re.IGNORECASE)
_BARE_SECTION_RE = re.compile(r"§+\s*" + _SECTION_CAPTURE, re.IGNORECASE)
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
        "derfor",
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
        "herunder",
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
        "mener",
        "måtte",
        "nærmere",
        "nr",
        "også",
        "oplyser",
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

# Ord der åbner nabostykker uden at bære sagen (værdi/kilometer i en firmabilopgave).
_WEAK_RELEVANCE_TOKENS = frozenset(
    {
        "bopæl",
        "kilometer",
        "privat",
        "stiller",
        "udbetale",
        "udbetales",
        "udbetalt",
        "værdi",
    }
)

SearchFn = Callable[[str], list[dict[str, Any]]]
RewriteFn = Callable[[str], str]


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


def lookup_hits_for_anchors(anchors: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Slå ankre op i opslagsværket. Tom liste hvis loven endnu ikke har noder."""
    hits: list[dict[str, Any]] = []
    seen: set[str] = set()
    for anchor in anchors[:MAX_NORM_QUERIES]:
        hit = lookup_hit_for_anchor(anchor)
        if not hit:
            continue
        file_id = str(hit.get("file_id") or "")
        if file_id in seen:
            continue
        seen.add(file_id)
        hits.append(hit)
    return hits


def lookup_hits_for_text(text: str) -> list[dict[str, Any]]:
    """Slå ankre i teksten op. Tom liste hvis ingen opslagsbar lov."""
    return lookup_hits_for_anchors(extract_anchors(text))


def discover_anchors_from_hits(
    hits: list[dict[str, Any]],
    facts: str = "",
) -> list[dict[str, str]]:
    """Lag 0: træk (lov, paragraf) ud af semantiske træf. Gæt ikke lov."""
    fact_tokens = _content_tokens(facts)
    ranked: list[tuple[int, int, dict[str, str]]] = []
    for hit_index, hit in enumerate(hits):
        filename = str(hit.get("filename") or "")
        text = str(hit.get("text") or "")
        source_laws = _laws_named_in(filename, text)
        seen_in_hit: set[str] = set()
        for anchor in _anchors_in_discovery_hit(filename, text, source_laws):
            key = anchor["label"].lower()
            if key in seen_in_hit:
                continue
            seen_in_hit.add(key)
            windows = _section_windows(text, *_section_parts(anchor))
            overlap = 0
            for window in windows:
                overlap = max(overlap, len(_content_tokens(window) & fact_tokens))
            if fact_tokens and overlap < 1:
                continue
            ranked.append((overlap, -hit_index, anchor))
    ranked.sort(key=lambda item: (-item[0], -item[1]))
    ranked = _keep_competitive_anchors(ranked)
    return _dedupe_anchors([item[2] for item in ranked])[:MAX_DISCOVERY_ANCHORS]


def _keep_competitive_anchors(
    ranked: list[tuple[int, int, dict[str, str]]],
) -> list[tuple[int, int, dict[str, str]]]:
    """Kun ankre hvis overlap er i nærheden af vinderen.

    Ellers bliver § 9 C/§ 9 B med, fordi et befordringsuddrag deler «bopæl»
    og «kilometer» med en firmabilsag.
    """
    if not ranked:
        return []
    best = ranked[0][0]
    if best <= 1:
        return ranked
    floor = max(2, (best + 1) // 2)
    return [item for item in ranked if item[0] >= floor]


def _anchors_in_discovery_hit(
    filename: str,
    text: str,
    source_laws: list[str],
) -> list[dict[str, str]]:
    found = list(extract_anchors(f"{filename}\n{text}"))
    seen = {item["label"].lower() for item in found}
    inherited_law = source_laws[0] if len(source_laws) == 1 else ""
    if not inherited_law:
        return found
    for match in _BARE_SECTION_RE.finditer(text):
        section = _canonical_section(match.group(1))
        prefix = text[max(0, match.start() - 48) : match.start()].lower()
        if _LOV_NAME_RE.search(prefix) or re.search(
            r"\b(?:" + "|".join(re.escape(key) for key in LAW_ABBREVIATIONS) + r")\s*$",
            prefix,
        ):
            continue
        label = f"{inherited_law} {section}".strip()
        if label.lower() in seen:
            continue
        seen.add(label.lower())
        found.append(
            {
                "law": inherited_law,
                "section": section,
                "label": label,
                "kind": "statute",
            }
        )
    return found


def _laws_named_in(*parts: str) -> list[str]:
    """Love nævnt i filnavn eller uddrag. Ingen default-lov."""
    blob = "\n".join(str(part or "") for part in parts)
    found: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        law = _canonical_law_name(raw)
        if not law or law in seen or law in {"loven", "lovens"}:
            return
        seen.add(law)
        found.append(law)

    for match in _LOV_NAME_RE.finditer(blob):
        add(match.group(1))
    for abbrev, law in LAW_ABBREVIATIONS.items():
        if re.search(rf"\b{re.escape(abbrev)}\s*§", blob, re.IGNORECASE):
            add(law)
        elif _law_in_filename(law, blob):
            add(law)
    return found


def _section_windows(
    text: str,
    number: str | None,
    letter: str,
    radius: int = DISCOVERY_WINDOW_CHARS,
) -> list[str]:
    source = str(text or "")
    if not number:
        return [source[: radius * 2]] if source else []
    if letter:
        pattern = re.compile(
            rf"§+\s*{re.escape(number)}\s*{re.escape(letter)}\b",
            re.IGNORECASE,
        )
    else:
        pattern = re.compile(
            rf"§+\s*{re.escape(number)}(?!\s*[A-Za-zæøåÆØÅ]|\d)",
            re.IGNORECASE,
        )
    windows = []
    for match in pattern.finditer(source):
        start = max(0, match.start() - radius)
        end = min(len(source), match.end() + radius)
        windows.append(source[start:end])
    if not letter and "artikel" in source.lower():
        for match in re.finditer(rf"\bartikel\s*{re.escape(number)}\b", source, re.I):
            start = max(0, match.start() - radius)
            end = min(len(source), match.end() + radius)
            windows.append(source[start:end])
    return windows


def _dedupe_anchors(anchors: list[dict[str, str]]) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for anchor in anchors:
        key = str(anchor.get("label") or "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        found.append(anchor)
    return found


def _stated_anchors(
    legal_locus: str = "",
    message: str = "",
    issues: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    blobs = [legal_locus, message]
    for item in issues or []:
        if isinstance(item, dict):
            blobs.append(_issue_question(item))
    return extract_anchors("\n".join(blobs))


def _layer_zero_query(message: str, issues: list[dict[str, Any]] | None) -> str:
    return _door_fact_blob(message, issues).strip()[:4_000]


def _clean_rewrite(text: str, original: str) -> str:
    """Første linje, uden citationstegn. Tom hvis den ikke tilføjer noget."""
    line = str(text or "").strip().splitlines()[0].strip() if str(text or "").strip() else ""
    line = line.strip(" \"'`")
    if line.lower().startswith("query:"):
        line = line.split(":", 1)[1].strip().strip(" \"'`")
    if len(line) > MAX_REWRITE_CHARS:
        line = line[:MAX_REWRITE_CHARS].rstrip()
    if not line:
        return ""
    if line.casefold() == str(original or "").strip().casefold():
        return ""
    return line


def _rewrite_discovery_query(client: OpenAI, facts: str) -> str:
    """GPT-søgestreng. Tom ved fejl, så Python-sporet stadig gælder."""
    source = str(facts or "").strip()
    if client is None or not source:
        return ""
    last_error: Exception | None = None
    for model in (PRIMARY_MODEL, FALLBACK_MODEL):
        try:
            resp = client.responses.create(
                model=model,
                instructions=LAYER0_REWRITE_INSTRUCTIONS,
                input=source,
                reasoning={"effort": "low"},
                prompt_cache_key=LAYER0_REWRITE_CACHE_KEY,
            )
            text = str(getattr(resp, "output_text", None) or "")
            cleaned = _clean_rewrite(text, source)
            if cleaned:
                return cleaned
        except Exception as exc:
            last_error = exc
            _log.warning("lag 0 rewrite fejlede (%s): %s", model, exc)
    if last_error:
        _log.warning("lag 0 rewrite gav op: %s", last_error)
    return ""


def _merge_hits(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for group in groups:
        for hit in group:
            key = (str(hit.get("file_id") or ""), str(hit.get("text") or "")[:200])
            if key in seen:
                continue
            seen.add(key)
            merged.append(hit)
    return merged


def _parallel_discovery(
    query: str,
    facts: str,
    search_fn: SearchFn,
    rewrite_fn: RewriteFn | None,
) -> tuple[list[dict[str, str]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Python-søgning og GPT-query ved siden af hinanden. Parseren ejer ankeret."""
    python_hits: list[dict[str, Any]] = []
    gpt_hits: list[dict[str, Any]] = []
    rewritten = ""
    logs: list[dict[str, Any]] = []

    def run_python() -> list[dict[str, Any]]:
        return _safe_search(search_fn, query)

    def run_gpt() -> list[dict[str, Any]]:
        nonlocal rewritten
        if not rewrite_fn:
            return []
        try:
            rewritten = _clean_rewrite(rewrite_fn(query), query)
        except Exception as exc:
            _log.warning("lag 0 rewrite_fn fejlede: %s", exc)
            rewritten = ""
        if not rewritten:
            return []
        return _safe_search(search_fn, rewritten)

    if rewrite_fn:
        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_python = pool.submit(run_python)
            fut_gpt = pool.submit(run_gpt)
            python_hits = fut_python.result()
            gpt_hits = fut_gpt.result()
    else:
        python_hits = run_python()

    hits = _merge_hits(python_hits, gpt_hits)
    discovered = discover_anchors_from_hits(hits, facts=facts)
    logs.append(
        {
            "queries": [f"Lag 0: {query[:180]}"],
            "status": "completed" if python_hits else "skipped",
            "num_results": len(discovered),
            "layer": "0",
            "source": "discovery",
        }
    )
    if rewrite_fn:
        logs.append(
            {
                "queries": [f"Lag 0 GPT: {(rewritten or '(tom)')[:180]}"],
                "status": "completed" if gpt_hits else "empty",
                "num_results": len(gpt_hits),
                "layer": "0",
                "source": "discovery-gpt",
                "rewrite": rewritten,
            }
        )
    return discovered, hits, logs


def _run_layer_zero(
    message: str,
    issues: list[dict[str, Any]] | None,
    legal_locus: str,
    search_fn: SearchFn,
    searches: list[dict[str, Any]],
    rewrite_fn: RewriteFn | None = None,
) -> list[dict[str, str]]:
    """Rå faktum → vektorsøgning, parallelt med GPT-query. Tom hvis anker allerede er givet."""
    if _stated_anchors(legal_locus, message, issues):
        return []
    query = _layer_zero_query(message, issues)
    if not query:
        return []
    discovered, _hits, logs = _parallel_discovery(
        query=query,
        facts=query,
        search_fn=search_fn,
        rewrite_fn=rewrite_fn,
    )
    searches.extend(logs)
    return discovered


def lookup_pack_for_chat(message: str) -> dict[str, Any]:
    """Paragrafnoder til almindelig chat. file_search må stadig hente praksis."""
    hits = lookup_hits_for_text(message)
    doors = _open_doors(hits, message, None)
    djv_hits = lookup_djv_hits(extract_anchors(message), doors, facts=message)
    hits = hits + djv_hits
    searches = [
        {
            "queries": [f"Opslag: {hit.get('anchor') or hit.get('filename') or ''}"],
            "status": "completed",
            "num_results": 1,
            "layer": hit.get("layer") or "A",
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
    extra_anchors: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Lag A: unikke ankre. Lag B: personkreds for ankeret + issue-opslag med sagens ord."""
    issue_rows = [item for item in (issues or []) if isinstance(item, dict)]
    anchors = _dedupe_anchors(
        _stated_anchors(legal_locus, message, issue_rows) + list(extra_anchors or [])
    )

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
    rewrite_fn: RewriteFn | None = None,
) -> dict[str, Any]:
    """Kør lag 0 ved manglende anker, derefter A, B og højst én hul-runde."""
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

    if rewrite_fn is None and client is not None and search_fn is None:
        rewrite_fn = lambda facts: _rewrite_discovery_query(client, facts)

    searches: list[dict[str, Any]] = []
    extra_anchors = _run_layer_zero(
        message=message,
        issues=issues,
        legal_locus=legal_locus,
        search_fn=worker_b,
        searches=searches,
        rewrite_fn=rewrite_fn,
    )
    plan = build_search_plan(
        issues,
        legal_locus=legal_locus,
        message=message,
        extra_anchors=extra_anchors,
    )
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
    stated_labels = {
        item["label"].lower()
        for item in _stated_anchors(legal_locus, message, issues)
    }
    hits_lookup_a, dropped_lookups = _filter_packed_lookups(
        hits_lookup_a,
        message,
        issues,
        stated_labels,
    )
    for hit in dropped_lookups:
        searches.append(
            {
                "queries": [
                    "Opslag forkastet: "
                    + str(hit.get("anchor") or hit.get("filename") or "")
                    + " (noden matcher ikke sagens distinkte ord)"
                ],
                "status": "skipped",
                "num_results": 0,
                "layer": "A",
                "source": "opslag-filter",
            }
        )
    kept_labels = {
        str(hit.get("anchor") or "").lower()
        for hit in hits_lookup_a
        if hit.get("anchor")
    }
    if kept_labels:
        plan["anchors"] = [
            anchor
            for anchor in plan["anchors"]
            if str(anchor.get("label") or "").lower() in kept_labels
            or str(anchor.get("kind") or "") in {"dbo", "regulation"}
        ]
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
    # Sagens faktum, ikke issue-formuleringen. «Er Mette på rejse» trækker
    # C.A.7.2/7.3 (ordet rejse) foran C.A.7.1.4 (midlertidigt arbejdssted).
    hits_djv = lookup_djv_hits(
        plan["anchors"],
        open_doors,
        facts=message,
    )
    if hits_djv:
        searches.append(
            {
                "queries": [
                    "DJV-opslag: "
                    + ", ".join(
                        str(hit.get("lookup_address") or hit.get("anchor") or "")
                        for hit in hits_djv
                        if not hit.get("lookup_clip")
                    )
                ],
                "status": "completed",
                "num_results": len(hits_djv),
                "layer": "B",
                "source": "opslag",
            }
        )
    hits_b = _filter_layer_b(
        _run_query_batch(plan["interpretive_queries"], worker_b, searches),
        plan["anchors"],
        open_doors=open_doors,
    )
    hits_b = _drop_replaced_djv_files(hits_b, hits_djv)

    gap_queries = _gap_queries(
        plan["anchors"],
        hits_a,
        hits_b=hits_djv + hits_b,
        doors=open_doors,
    )
    hits_lookup_gap, remaining_gap = _resolve_lookups(gap_queries, searches)
    hits_gap = hits_lookup_gap + _run_query_batch(remaining_gap, worker_a, searches)

    lookup_hits = [hit for hit in hits_a + hits_gap if hit.get("from_lookup")]
    hits_a = _drop_replaced_statute_files(hits_a, lookup_hits)
    hits_gap = _filter_gap_statute_nodes(
        _drop_replaced_statute_files(hits_gap, lookup_hits)
    )
    chunks = _pack_chunks(hits_a + hits_djv, hits_b, hits_gap, anchors=plan["anchors"])
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
    if any(chunk.get("lookup_kind") == "djv" for chunk in chunks):
        intro += (
            " DJV-afsnit med adresse er slået op som node, ikke søgt. "
            "Brug ikke andre uddrag af samme DJV-familie som erstatning. "
            "Citer de specifikke afsnit der bærer konklusionen. "
            "Et afsnit med overskriften Regel er kun indgangen, hvis et mere "
            "specifikt afsnit er hentet."
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
        # Lov- og DJV-krop klippes ikke. Praksistabel og vector-uddrag fylder resten.
        should_clip = (not chunk.get("from_lookup")) or chunk.get("lookup_clip")
        if should_clip and used + len(block) > MAX_CONTEXT_CHARS:
            room = MAX_CONTEXT_CHARS - used
            if room < 400:
                break
            block = block[: room - 1].rstrip() + "…"
        lines.append(block)
        used += len(block)
    lines.append("[/Hentede retskilder]")
    return "\n\n".join(lines).strip()


def prefetch_chat_retrieval(
    client: OpenAI,
    query: str,
    vector_store_ids: list[str] | None = None,
    search_fn: SearchFn | None = None,
    rewrite_fn: RewriteFn | None = None,
) -> dict[str, Any]:
    """Opslag af noder plus semantisk søgning. Lag 0 kører når beskeden ikke har anker."""
    clean = str(query or "").strip()
    if not clean:
        return {
            "retrieved_chunks": [],
            "retrieved_sources": [],
            "searches": [],
            "context_text": "",
            "diagnosis_question": "",
        }

    def run_search(text: str) -> list[dict[str, Any]]:
        if search_fn:
            return list(search_fn(text) or [])
        if client is not None:
            return search_legal_sources(
                client,
                text,
                max_results=10,
                vector_store_ids=vector_store_ids,
                rewrite_query=True,
            )
        return []

    if rewrite_fn is None and client is not None and search_fn is None:
        rewrite_fn = lambda facts: _rewrite_discovery_query(client, facts)

    searches: list[dict[str, Any]] = []
    anchors = extract_anchors(clean)
    raw_hits: list[dict[str, Any]] = []
    if not anchors:
        anchors, raw_hits, disc_logs = _parallel_discovery(
            query=clean,
            facts=clean,
            search_fn=run_search,
            rewrite_fn=rewrite_fn,
        )
        searches.extend(disc_logs)

    lookups = lookup_hits_for_anchors(anchors)
    lookups, dropped_lookups = _filter_packed_lookups(
        lookups, clean, None, {item["label"].lower() for item in extract_anchors(clean)}
    )
    for hit in dropped_lookups:
        searches.append(
            {
                "queries": [
                    "Opslag forkastet: "
                    + str(hit.get("anchor") or hit.get("filename") or "")
                    + " (noden matcher ikke sagens distinkte ord)"
                ],
                "status": "skipped",
                "num_results": 0,
                "layer": "A",
                "source": "opslag-filter",
            }
        )
    if lookups:
        anchors = _dedupe_anchors(
            [
                item
                for hit in lookups
                for item in extract_anchors(str(hit.get("anchor") or ""))
            ]
        )
    doors = _open_doors(lookups, clean, None)
    djv_hits = lookup_djv_hits(anchors, doors, facts=clean)
    lookups = lookups + djv_hits
    if not raw_hits:
        raw_hits = run_search(clean)
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
    semantic = _drop_replaced_djv_files(semantic, djv_hits)
    chunks = lookups + semantic
    lookup_searches = [
        {
            "queries": [f"Opslag: {hit.get('anchor') or hit.get('filename') or ''}"],
            "status": "completed",
            "num_results": 1,
            "layer": "A",
            "source": "opslag",
        }
        for hit in lookups
    ]
    searches.extend(lookup_searches)
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
        node_key = str(hit.get("lookup_key") or "").strip().lower()
        for door in _doors_for_node(subs, facts):
            seen_key = (str(hit.get("file_id") or ""), door["label"])
            if seen_key in seen:
                continue
            seen.add(seen_key)
            row = dict(door)
            if node_key:
                row["key"] = node_key
            opened.append(row)
    return opened


def _doors_for_node(
    subsections: list[Any],
    fact_tokens: set[str],
) -> list[dict[str, str]]:
    rows = _subsection_rows(subsections)
    if not rows:
        return []
    df: Counter[str] = Counter()
    for _label, _text, tokens in rows:
        df.update(tokens)
    opened: list[dict[str, str]] = []
    extra_hits: set[str] = set()
    for index, (label, text, tokens) in enumerate(rows):
        rare = {token for token in tokens if df[token] <= 2}
        strong = (fact_tokens & rare) - _WEAK_RELEVANCE_TOKENS
        if index == 0:
            opened.append({"label": label, "text": text})
            continue
        if not strong:
            continue
        # Første ekstra stykke er emnet (stk. 4 firmabil). Senere stykker
        # (lystbåd, bolig) må ikke åbne på de samme sagsord.
        if extra_hits and not (strong - extra_hits):
            continue
        extra_hits |= strong
        opened.append({"label": label, "text": text})
    return opened


def _subsection_rows(
    subsections: list[Any],
) -> list[tuple[str, str, set[str]]]:
    rows: list[tuple[str, str, set[str]]] = []
    for item in subsections:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip() or f"Stk. {len(rows) + 1}."
        text = str(item.get("text") or item.get("leadText") or "").strip()
        if not text:
            continue
        rows.append((label, text, _content_tokens(text)))
    return rows


def _extra_door_signal(hit: dict[str, Any], fact_tokens: set[str]) -> set[str]:
    """Sagens ord der åbner andre stykker end stk. 1. Ikke stk. 1 selv."""
    rows = _subsection_rows(hit.get("lookup_subsections") or [])
    if len(rows) < 2:
        return set()
    df: Counter[str] = Counter()
    for _label, _text, tokens in rows:
        df.update(tokens)
    signal: set[str] = set()
    for index, (_label, _text, tokens) in enumerate(rows):
        if index == 0:
            continue
        rare = {token for token in tokens if df[token] <= 2}
        signal |= fact_tokens & rare
    return signal


def _lookup_hit_is_relevant(
    hit: dict[str, Any],
    fact_tokens: set[str],
    *,
    required: bool,
) -> bool:
    """Pak noden hvis den er påkrævet, eller hvis et særligt stykke rammer sagens ord."""
    if required:
        return True
    strong = _extra_door_signal(hit, fact_tokens) - _WEAK_RELEVANCE_TOKENS
    return bool(strong)


def _filter_packed_lookups(
    hits: list[dict[str, Any]],
    message: str,
    issues: list[dict[str, Any]] | None,
    stated_labels: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Slå alle ankre op, men pak kun noder sagen kan bære.

    Udtrykkeligt nævnte ankre beholdes. Øvrige kun hvis et stykke ud over
    stk. 1 rammer distinkte sagsord. Rækkefølgen i lag 0 må ikke gøre § 9 C
    obligatorisk, bare fordi den blev fundet før § 16.
    """
    lookup_hits = [hit for hit in hits if hit.get("from_lookup")]
    others = [hit for hit in hits if not hit.get("from_lookup")]
    if len(lookup_hits) <= 1:
        return hits, []
    fact_tokens = _content_tokens(_door_fact_blob(message, issues))
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for hit in lookup_hits:
        label = str(hit.get("anchor") or "").lower()
        required = bool(stated_labels) and label in stated_labels
        has_signal = _lookup_hit_is_relevant(hit, fact_tokens, required=False)
        if required or has_signal:
            kept.append(hit)
        else:
            dropped.append(hit)
    if not kept and lookup_hits:
        kept = [lookup_hits[0]]
        dropped = lookup_hits[1:]
    return kept + others, dropped



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
        "lookup_kind": str(hit.get("lookup_kind") or ""),
        "lookup_clip": bool(hit.get("lookup_clip")),
        "lookup_address": str(hit.get("lookup_address") or ""),
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


def _drop_replaced_djv_files(
    hits: list[dict[str, Any]],
    djv_hits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Når DJV-noden er slået op, droppes PDF af samme kapitel-familie.

    C.F.4.2.1 erstatter C.F.4-uddrag, men ikke C.F.7. JURV-filen for C.A
    droppes, når en C.A-node er slået op — filnavnet har ikke kapiteladresse.
    """
    families = {
        _heading_family(hit)
        for hit in djv_hits
        if _heading_family(hit)
    }
    volumes = {
        _djv_volume(hit)
        for hit in djv_hits
        if _djv_volume(hit)
    }
    if not families and not volumes:
        return hits
    kept: list[dict[str, Any]] = []
    dropped = 0
    for hit in hits:
        if hit.get("from_lookup"):
            kept.append(hit)
            continue
        if not _looks_like_djv(str(hit.get("filename") or "")):
            kept.append(hit)
            continue
        family = _heading_family(hit)
        volume = _djv_volume(hit)
        if family and family in families:
            dropped += 1
            continue
        if (
            volume
            and volume in volumes
            and "jurv" in str(hit.get("filename") or "").lower()
        ):
            dropped += 1
            continue
        kept.append(hit)
    if dropped:
        _log.info("task_search: dropped %s DJV-chunks replaced by node lookup", dropped)
    return kept


def _looks_like_djv(filename: str) -> bool:
    name = filename.lower()
    return (
        "djv" in name
        or "jurv" in name
        or "juridiske vejledning" in name
    )


def _djv_volume(hit: dict[str, Any]) -> str:
    """C.A fra C.A.5.14.1.4 eller fra JURV2026-2_C.A_…-filnavn."""
    code = _heading_code(hit)
    parts = [part for part in code.split(".") if part]
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"
    name = str(hit.get("filename") or "")
    match = re.search(r"(C\.[A-Z])(?:_|$)", name)
    return match.group(1) if match else ""


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
    ll_lookup = [
        chunk
        for chunk in chunks
        if chunk.get("from_lookup") and chunk.get("lookup_kind") != "djv"
    ]
    djv_lookup = [chunk for chunk in chunks if chunk.get("lookup_kind") == "djv"]
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
    return ll_lookup + djv_lookup + bound_b + rest


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
