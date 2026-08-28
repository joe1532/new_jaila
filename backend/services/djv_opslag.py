"""Deterministisk opslag af DJV-afsnit (fortolkningsnode).

Adressen er nøglen, ligesom paragraphNumber i lag A. Bindingen LL §
(og stk. når overskriften har det) kommer fra den rensede DJV 2026-2.
Ingen embedding.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.services.opslagsvaerk import paragraph_key

_log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[1] / "opslagsvaerk" / "djv"
EDITION_PATH = DATA_DIR / "edition.json"

_STK_LABEL_RE = re.compile(r"stk\.?\s*(\d+)", re.IGNORECASE)
_PRACTICE_RE = re.compile(
    r"\n#+\s*Oversigt over domme, kendelser, afgørelser, SKM-meddelelser mv\.\s*\n",
    re.IGNORECASE,
)
_HEADING_AFTER_TOC_RE = re.compile(r"\n#\s+(?!Indhold\b)\S")
_GENERIC_LEAF_RE = re.compile(r"^regel\b", re.IGNORECASE)
_TOKEN_RE = re.compile(r"[a-zæøå]+", re.IGNORECASE)
# Højst fire paragrafnoder. Hele C.A.7 må ikke i de 24.000 tegn.
MAX_PARAGRAPH_NODES = 4


def lookup_djv_hits(
    anchors: list[dict[str, str]],
    doors: list[dict[str, str]],
    facts: str = "",
) -> list[dict[str, Any]]:
    """DJV-noder for åbne stykker. Tom liste hvis ankeret ikke har en DJV-adresse."""
    wanted = _wanted_bindings(anchors, doors)
    if not wanted:
        return []
    stk_index = _binding_index()
    para_index = _paragraph_index()
    hits: list[dict[str, Any]] = []
    seen: set[str] = set()
    for law, key, stk in wanted:
        nodes = stk_index.get((law, key, stk)) or []
        if nodes:
            chosen = nodes
        else:
            chosen = _pick_paragraph_nodes(
                para_index.get((law, key)) or [],
                doors,
                facts,
                key,
            )
        for node in chosen:
            address = str(node.get("address") or "")
            if not address or address in seen:
                continue
            seen.add(address)
            hits.extend(_hits_for_node(node, key, stk))
    return hits


def lookup_djv_address(address: str) -> dict[str, Any] | None:
    """Hent én node på DJV-adresse. Til tests og direkte opslag."""
    return _address_index().get(str(address or "").strip())


def djv_edition() -> str:
    """Udgave på de importerede noder. Tom streng hvis metadata mangler."""
    return str(_edition_meta().get("edition") or "").strip()


def _wanted_bindings(
    anchors: list[dict[str, str]],
    doors: list[dict[str, str]],
) -> list[tuple[str, str, int]]:
    """Stk. fra en paragrafnode må kun åbne DJV for den samme paragraf.

    Uden nøgle på døren (tests med syntetiske døre) gælder stykkerne alle ankre.
    """
    keyed_stks: dict[str, list[int]] = defaultdict(list)
    unkeyed_stks: list[int] = []
    seen_keyed: dict[str, set[int]] = defaultdict(set)
    seen_unkeyed: set[int] = set()
    for door in doors:
        match = _STK_LABEL_RE.search(str(door.get("label") or ""))
        if not match:
            continue
        stk = int(match.group(1))
        door_key = str(door.get("key") or "").strip().lower()
        if door_key:
            if stk in seen_keyed[door_key]:
                continue
            seen_keyed[door_key].add(stk)
            keyed_stks[door_key].append(stk)
            continue
        if stk in seen_unkeyed:
            continue
        seen_unkeyed.add(stk)
        unkeyed_stks.append(stk)
    if not keyed_stks and not unkeyed_stks:
        return []
    wanted: list[tuple[str, str, int]] = []
    seen: set[tuple[str, str, int]] = set()
    for anchor in anchors:
        if str(anchor.get("kind") or "") in {"dbo", "regulation"}:
            continue
        law = str(anchor.get("law") or "").strip().lower()
        if law != "ligningsloven":
            continue
        key = paragraph_key(str(anchor.get("section") or ""))
        if not key:
            continue
        stks = keyed_stks.get(key) or unkeyed_stks
        for stk in stks:
            item = (law, key, stk)
            if item in seen:
                continue
            seen.add(item)
            wanted.append(item)
    return wanted


def _hits_for_node(node: dict[str, Any], key: str, stk: int) -> list[dict[str, Any]]:
    heading = str(node.get("heading") or node.get("address") or "")
    address = str(node.get("address") or "")
    edition = str(node.get("edition") or djv_edition() or "2026-2")
    body, practice = split_practice(str(node.get("text") or ""))
    notice = (
        f"Opslag (ikke søgning). DJV {edition} node {address}. Bundet til "
        f"ligningsloven § {key} stk. {stk}."
    )
    hits: list[dict[str, Any]] = []
    if body:
        hits.append(
            _hit(
                node,
                text=body,
                filename=f"DJV {heading}",
                notice=notice,
                clip=False,
                part="body",
            )
        )
    if practice:
        hits.append(
            _hit(
                node,
                text=practice,
                filename=f"DJV {heading} — praksis",
                notice=notice + " Praksistabel. Klippes hvis konteksten er fuld.",
                clip=True,
                part="praksis",
            )
        )
    return hits


def split_practice(text: str) -> tuple[str, str]:
    """Krop først, praksistabel bagefter. Uden overskriften er det hele krop."""
    source = str(text or "").strip()
    if not source:
        return "", ""
    matches = list(_PRACTICE_RE.finditer(source))
    if not matches:
        return source, ""
    split_at = matches[-1].start()
    body = source[:split_at].strip()
    practice = source[split_at:].strip()
    return body, practice


def _pick_paragraph_nodes(
    direct: list[dict[str, Any]],
    doors: list[dict[str, str]],
    facts: str,
    key: str,
) -> list[dict[str, Any]]:
    """Vælg blade i samme underafsnit som de citerede noder. Ikke hele kapitlet."""
    if not direct:
        return []
    query_tokens = _query_tokens(doors, facts)
    fact_tokens = _tokens(facts)
    candidates = _expand_siblings(direct, key)
    substantive = [
        node for node in candidates if not _is_toc_node(node, fact_tokens)
    ]
    if substantive:
        candidates = substantive
    headed = [node for node in candidates if _node_matches_query(node, query_tokens)]
    if headed:
        candidates = headed
    on_topic = [
        node
        for node in candidates
        if not _heading_is_off_topic(
            node, fact_tokens | _primary_door_tokens(doors, fact_tokens)
        )
    ]
    if on_topic:
        candidates = on_topic
    ranked = sorted(
        candidates,
        key=lambda node: (
            -_heading_score(node, fact_tokens, query_tokens),
            -sum(len(word) for word in _matched_heading_words(node, query_tokens)),
            str(node.get("address") or ""),
        ),
    )
    by_family: dict[str, list[dict[str, Any]]] = {}
    family_order: list[str] = []
    for node in ranked:
        family = _section_family(str(node.get("address") or ""))
        if family not in by_family:
            family_order.append(family)
            by_family[family] = []
        by_family[family].append(node)
    family_order = _prefer_same_chapter(family_order)
    family_order = _put_door_family_first(
        family_order, by_family, _primary_door_tokens(doors, fact_tokens)
    )
    return _fill_family_slots(family_order, by_family, doors)


def _expand_siblings(direct: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    """Tag umiddelbare søskende, når underafsnittet er lille.

    C.A.7.1.4 → C.A.7.1.2 (afstand) selv om overskriften ikke citerer 9 A.
    C.F.4.2.4 citerer 9 A i Regel, men søskende bundet til 33 A kommer ikke med.
    """
    by_address: dict[str, dict[str, Any]] = {}
    for node in direct:
        address = str(node.get("address") or "")
        if address:
            by_address[address] = node
        parent = _parent_address(address)
        if not parent:
            continue
        siblings = _immediate_children(parent)
        if len(siblings) > 8:
            continue
        for child in siblings:
            if not _sibling_shares_topic(child, key):
                continue
            child_addr = str(child.get("address") or "")
            if child_addr:
                by_address[child_addr] = child
    return list(by_address.values())


def _sibling_shares_topic(node: dict[str, Any], key: str) -> bool:
    keys = {
        str(item.get("key") or "")
        for item in (node.get("bindings") or [])
        if isinstance(item, dict)
    }
    keys.discard("")
    return (not keys) or key in keys


def _parent_address(address: str) -> str:
    source = str(address or "")
    if "." not in source:
        return ""
    return source.rsplit(".", 1)[0]


def _section_family(address: str) -> str:
    """C.A.7.1.4 og C.A.7.1.2 er samme familie. C.A.7.2.4 er en anden."""
    parts = [part for part in str(address or "").split(".") if part]
    if len(parts) >= 4:
        return ".".join(parts[:4])
    return ".".join(parts)


def _prefer_same_chapter(family_order: list[str]) -> list[str]:
    """Bliv i kapitlet for det bedste hit, før C.A.2.5.2.30 tager pladsen fra C.A.7.1."""
    if not family_order:
        return family_order
    chapter = _chapter_of(family_order[0])
    same = [family for family in family_order if _chapter_of(family) == chapter]
    other = [family for family in family_order if family not in same]
    return same + other


def _stk1_tokens(doors: list[dict[str, str]]) -> set[str]:
    """Stk. 1 er rejsebegrebet. Stk. 3-4 om satser må ikke skubbe C.A.7.1 ud."""
    for door in doors:
        if str(door.get("label") or "").lower().startswith("stk. 1"):
            return _tokens(str(door.get("text") or ""))
    return _query_tokens(doors, "")


def _family_door_score(
    family: str,
    by_family: dict[str, list[dict[str, Any]]],
    door_tokens: set[str],
) -> tuple[int, int]:
    """Antal dør-ord i familiens bedste overskrift. Bruges til 9 A-parring."""
    best = 0
    length = 0
    for node in by_family.get(family) or []:
        words = _matched_heading_words(node, door_tokens)
        best = max(best, len(words))
        length = max(length, sum(len(word) for word in words))
    return best, length


def _primary_door_tokens(
    doors: list[dict[str, str]],
    fact_tokens: set[str],
) -> set[str]:
    """Stk. 1 som udgangspunkt. Et senere stykke kun hvis det rammer egne sagsord.

    § 9 A: stk. 1 er rejsebegrebet, stk. 3-satser må ikke åbne C.A.7.3.
    § 16: stk. 4 (bilen) er distinkt fra stk. 1 (telefon).
    """
    stk1 = None
    extra: list[dict[str, str]] = []
    for door in doors:
        if str(door.get("label") or "").lower().startswith("stk. 1"):
            stk1 = door
        else:
            extra.append(door)
    stk1_tokens = _tokens(str(stk1.get("text") or "")) if stk1 else set()
    weak = _WEAK_TOKENS | {"udbetale", "udbetales", "udbetalt"}
    stk1_hits = (stk1_tokens & fact_tokens) - weak
    for door in extra:
        hits = (_tokens(str(door.get("text") or "")) & fact_tokens) - weak
        if hits - stk1_hits:
            return _tokens(str(door.get("text") or ""))
    if stk1_tokens:
        return stk1_tokens
    return _stk1_tokens(doors)


def _put_door_family_first(
    family_order: list[str],
    by_family: dict[str, list[dict[str, Any]]],
    door_tokens: set[str],
) -> list[str]:
    """Familien hvis overskrift rammer døren, foran et nabo-hit på samme ord.

    C.A.2.5.2.30 citerer § 9 A i overskriften (rejsegodtgørelse), men
    C.A.7.1 rammer stk. 1 (midlertidigt arbejdssted) og skal åbne.
    """
    if len(family_order) < 2 or not door_tokens:
        return family_order
    best = max(
        family_order,
        key=lambda family: (
            _family_door_score(family, by_family, door_tokens)[0],
            _family_door_score(family, by_family, door_tokens)[1],
            -family_order.index(family),
        ),
    )
    first_score = _family_door_score(family_order[0], by_family, door_tokens)
    best_score = _family_door_score(best, by_family, door_tokens)
    if best != family_order[0] and best_score > first_score:
        family_order = [best] + [family for family in family_order if family != best]
    first = family_order[0]
    rest = family_order[1:]
    rest_sorted = sorted(
        rest,
        key=lambda family: (
            -_family_door_score(family, by_family, door_tokens)[0],
            -_family_door_score(family, by_family, door_tokens)[1],
            family,
        ),
    )
    return [first] + rest_sorted


def _chapter_is_broad(chapter: str) -> bool:
    """C.A.5 Personalegoder har 17 børn. C.A.7 Rejseudgifter har 4 og må parres."""
    return len(_immediate_children(chapter)) > 8


def _paired_family(
    family_order: list[str],
    by_family: dict[str, list[dict[str, Any]]],
    doors: list[dict[str, str]],
) -> str:
    """Anden familie i samme snævre kapitel, rangordnet efter stk. 1 (7.1 + 7.2).

    Satser i stk. 3-4 må ikke gøre C.A.7.3 til partner. Bredt kapitel (C.A.5
    personalegoder) parres ikke, så firmabil ikke får telefon.
    """
    if len(family_order) < 2:
        return ""
    first = family_order[0]
    chapter = _chapter_of(first)
    if _chapter_is_broad(chapter):
        return ""
    stk1_tokens = _stk1_tokens(doors)
    if not stk1_tokens:
        return ""
    best = ""
    best_score = (1, 0)
    for family in family_order[1:]:
        if _chapter_of(family) != chapter:
            continue
        score = _family_door_score(family, by_family, stk1_tokens)
        if score > best_score:
            best_score = score
            best = family
    return best


def _fill_family_slots(
    family_order: list[str],
    by_family: dict[str, list[dict[str, Any]]],
    doors: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """To+to når to familier hører sammen. Ellers cap fra den vindende familie."""
    if not family_order:
        return []
    first = family_order[0]
    partner = _paired_family(family_order, by_family, doors)
    picked: list[dict[str, Any]] = []
    if partner:
        for family in (first, partner):
            for node in by_family[family][:2]:
                picked.append(node)
                if len(picked) >= MAX_PARAGRAPH_NODES:
                    return picked
        return picked
    for node in by_family[first][:MAX_PARAGRAPH_NODES]:
        picked.append(node)
    return picked


def _chapter_of(family: str) -> str:
    parts = [part for part in str(family or "").split(".") if part]
    if len(parts) >= 3:
        return ".".join(parts[:3])
    return str(family or "")


def _immediate_children(parent: str) -> list[dict[str, Any]]:
    prefix = parent + "."
    depth = parent.count(".") + 1
    found: list[dict[str, Any]] = []
    for node in _nodes():
        address = str(node.get("address") or "")
        if address.startswith(prefix) and address.count(".") == depth:
            found.append(node)
    return found


def _query_tokens(doors: list[dict[str, str]], facts: str) -> set[str]:
    blobs = [str(facts or "")]
    for door in doors:
        blobs.append(str(door.get("label") or ""))
        blobs.append(str(door.get("text") or ""))
    return _tokens("\n".join(blobs))


def _tokens(text: str) -> set[str]:
    found: set[str] = set()
    for raw in _TOKEN_RE.findall(str(text or "").lower()):
        if len(raw) >= 5:
            found.add(raw)
    return found


def _matched_heading_words(node: dict[str, Any], query_tokens: set[str]) -> set[str]:
    return _matched_words(str(node.get("heading") or ""), query_tokens)


def _matched_words(text: str, query_tokens: set[str]) -> set[str]:
    if not query_tokens:
        return set()
    heading_tokens = _tokens(text)
    matched: set[str] = set()
    for word in heading_tokens:
        if word in _WEAK_TOKENS:
            continue
        if any(
            token not in _WEAK_TOKENS
            and (token == word or _soft_hit(token, {word}))
            for token in query_tokens
        ):
            matched.add(word)
    return matched


def _ancestor_headings(node: dict[str, Any]) -> str:
    parts: list[str] = []
    address = _parent_address(str(node.get("address") or ""))
    seen: set[str] = set()
    while address and address not in seen:
        seen.add(address)
        ancestor = _address_index().get(address)
        if ancestor:
            parts.append(str(ancestor.get("heading") or ""))
        address = _parent_address(address)
    return "\n".join(parts)


def _node_matches_query(node: dict[str, Any], query_tokens: set[str]) -> bool:
    if _matched_heading_words(node, query_tokens):
        return True
    title = _leaf_title(node)
    if not _GENERIC_LEAF_RE.match(title):
        return False
    if _matched_words(_ancestor_headings(node), query_tokens):
        return True
    return bool(_matched_words(_body_lead(node), query_tokens))


_GENERIC_HEADING_HITS = frozenset(
    {
        "anskaffelse",
        "anskaffelsen",
        "betales",
        "betalt",
        "beskrevet",
        "gælder",
    }
)


def _heading_is_off_topic(node: dict[str, Any], query_tokens: set[str]) -> bool:
    """Lange, specifikke overskrifter uden sagsord (gule plader) fylder ikke cap 4."""
    title = _leaf_title(node)
    if _GENERIC_LEAF_RE.match(title):
        return False
    specific = [
        word
        for word in _tokens(title)
        if word not in _WEAK_TOKENS and len(word) >= 6
    ]
    if len(specific) < 2:
        return False
    matched = _matched_words(title, query_tokens) - _GENERIC_HEADING_HITS
    return not matched


def _leaf_title(node: dict[str, Any]) -> str:
    heading = str(node.get("heading") or "")
    address = str(node.get("address") or "")
    if heading.startswith(address):
        heading = heading[len(address) :].lstrip(" .:-")
    return heading.strip()


def _body_lead(node: dict[str, Any], max_chars: int = 500) -> str:
    body, _practice = split_practice(str(node.get("text") or ""))
    text = body.lstrip()
    if text.startswith("# Indhold"):
        match = _HEADING_AFTER_TOC_RE.search(text)
        if not match:
            return ""
        text = text[match.start() :].lstrip()
    return text[:max_chars]


def _heading_score(
    node: dict[str, Any],
    fact_tokens: set[str],
    query_tokens: set[str],
) -> int:
    """Sagens ord i overskriften vejer tungest. Dørtekst må højst give to point."""
    heading = str(node.get("heading") or "")
    fact_hits = _matched_words(heading, fact_tokens)
    query_hits = _matched_words(heading, query_tokens)
    score = 3 * len(fact_hits)
    extra_door = len(query_hits) - len(fact_hits)
    if extra_door > 0:
        score += min(extra_door, 2)
    score += _compound_topic_bonus(node, fact_tokens)
    title = _leaf_title(node)
    if not _GENERIC_LEAF_RE.match(title):
        return score
    rank_tokens = fact_tokens or query_tokens
    ancestor_hits = _matched_words(_ancestor_headings(node), rank_tokens)
    lead_hits = _matched_words(_body_lead(node), rank_tokens)
    if ancestor_hits or lead_hits:
        score += 2
    score += 3 * len(ancestor_hits)
    score += min(3 * len(lead_hits), 9)
    return score


_WEAK_TOKENS = frozenset(
    {
        "anden",
        "dette",
        "denne",
        "disse",
        "efter",
        "eller",
        "første",
        "grund",
        "kilometer",
        "mellem",
        "samme",
        "være",
        # Pris/antal i faktum må ikke slå «Rådighedsbeskatning» til
        # «Opgørelse af bilens værdi».
        "værdi",
    }
)


_INFLECTIONS = frozenset({"", "e", "en", "et", "er", "es", "s", "ene", "ens"})


def _soft_hit(token: str, words: set[str]) -> bool:
    """Bøjning og sammensætning (firmabilen, rådighedsbeskatning). Ikke privat⊂privatbenyttelsesafgift."""
    if token in _WEAK_TOKENS:
        return False
    for word in words:
        if word in _WEAK_TOKENS or min(len(token), len(word)) < 5:
            continue
        longer, shorter = (token, word) if len(token) >= len(word) else (word, token)
        if longer == shorter:
            return True
        if not longer.startswith(shorter):
            continue
        rest = longer[len(shorter) :]
        if rest in _INFLECTIONS:
            return True
        if rest.startswith("s") and len(rest) > 1:
            return True
    return False


def _compound_topic_bonus(node: dict[str, Any], fact_tokens: set[str]) -> int:
    """Sammensat overskrift (rådighedsbeskatning) slår bøjning (rådigheden)."""
    title_words = _tokens(_leaf_title(node))
    for word in title_words:
        if word in _WEAK_TOKENS:
            continue
        for token in fact_tokens:
            if token in _WEAK_TOKENS or min(len(token), len(word)) < 5:
                continue
            if len(word) <= len(token) + 2 or not word.startswith(token):
                continue
            if word[len(token) :] not in _INFLECTIONS:
                return 2
    return 0


def _is_toc_node(node: dict[str, Any], fact_tokens: set[str] | None = None) -> bool:
    """Rene indholdssider. Langt blad med h1 tæller, hvis overskriften rammer faktum."""
    body, _practice = split_practice(str(node.get("text") or ""))
    lead = body.lstrip()
    if not lead.startswith("# Indhold"):
        return False
    if "# Regel" in body[:1200]:
        return False
    facts = fact_tokens or set()
    if facts and _matched_words(_leaf_title(node), facts):
        match = _HEADING_AFTER_TOC_RE.search(lead)
        if match and len(lead[match.start() :]) >= 2000:
            return False
    return True


def _hit(
    node: dict[str, Any],
    text: str,
    filename: str,
    notice: str,
    clip: bool,
    part: str,
) -> dict[str, Any]:
    address = str(node.get("address") or "")
    return {
        "file_id": f"opslag:djv:{address}:{part}",
        "filename": filename,
        "score": "1",
        "text": text,
        "layer": "B",
        "anchor": address,
        "issue_id": "",
        "from_lookup": True,
        "lookup_kind": "djv",
        "lookup_clip": clip,
        "lookup_notice": notice,
        "lookup_address": address,
        "lookup_edition": str(node.get("edition") or djv_edition() or ""),
    }


@lru_cache(maxsize=1)
def _edition_meta() -> dict[str, Any]:
    try:
        payload = json.loads(EDITION_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


@lru_cache(maxsize=1)
def _nodes() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(DATA_DIR.glob("c-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _log.warning("djv_opslag: kunne ikke læse %s: %s", path, exc)
            continue
        if not isinstance(payload, list):
            continue
        rows.extend(row for row in payload if isinstance(row, dict))
    from backend.tools.import_djv import finalize_node_bindings

    finalize_node_bindings(rows)
    return rows


@lru_cache(maxsize=1)
def _address_index() -> dict[str, dict[str, Any]]:
    return {
        str(node.get("address") or ""): node
        for node in _nodes()
        if node.get("address")
    }


@lru_cache(maxsize=1)
def _binding_index() -> dict[tuple[str, str, int], list[dict[str, Any]]]:
    index: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, str, int, str]] = set()
    for node in _nodes():
        address = str(node.get("address") or "")
        for binding in node.get("bindings") or []:
            if not isinstance(binding, dict) or binding.get("stk") is None:
                continue
            law = str(binding.get("law") or "").strip().lower()
            key = paragraph_key(str(binding.get("key") or ""))
            try:
                stk = int(binding.get("stk"))
            except (TypeError, ValueError):
                continue
            if not (law and key and stk and address):
                continue
            item = (law, key, stk, address)
            if item in seen:
                continue
            seen.add(item)
            index[(law, key, stk)].append(node)
    return index


@lru_cache(maxsize=1)
def _paragraph_index() -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Noder hvis overskrift eller Regel nævner LL § uden stk. Bruges når stk-adressen mangler."""
    index: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, str, str]] = set()
    for node in _nodes():
        address = str(node.get("address") or "")
        for binding in node.get("bindings") or []:
            if not isinstance(binding, dict) or binding.get("stk") is not None:
                continue
            law = str(binding.get("law") or "").strip().lower()
            key = paragraph_key(str(binding.get("key") or ""))
            if not (law and key and address):
                continue
            item = (law, key, address)
            if item in seen:
                continue
            seen.add(item)
            index[(law, key)].append(node)
    return index
