"""Deterministisk query-routing. Ingen embeddings."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

INTENT_EXACT = "exact_lookup"
INTENT_SUMMARY = "summary"
INTENT_RESULT = "final_result"
INTENT_REASONING = "reasoning"
INTENT_REFERENCES = "references"
INTENT_TOPICAL = "topical"
INTENT_QUESTIONS = "questions"
INTENT_ANSWERS = "answers"

SKM_RE = re.compile(
    r"\bSKM\s*\d{4}\s*\.\s*\d+\s*(?:\.\s*)?[A-Za-zÆØÅæøå]*",
    re.IGNORECASE,
)
OID_RE = re.compile(
    r"\b(?:skat-info:oid:|oid:)\s*\d+\b",
    re.IGNORECASE,
)
BARE_OID_RE = re.compile(r"^\d{4,}$")

SUMMARY_TERMS = ("resume", "resumé", "sammendrag", "sammenfatning")
RESULT_TERMS = ("resultat", "afgorelse", "afgørelse", "udtalelse", "stadfaest", "stadfæst")
REASONING_TERMS = ("begrunde", "premiss", "præmiss", "praemiss")
REFERENCE_TERMS = ("henvisning", "referencer", "reference", "citat", "kilder", "paberab", "påberåb")
QUESTION_TERMS = ("sporgsmal", "spørgsmål")
ANSWER_TERMS = ("svar", "bindende svar")


def fold(text: str) -> str:
    lowered = text.lower().replace("æ", "ae").replace("ø", "oe").replace("å", "aa")
    decomposed = unicodedata.normalize("NFKD", lowered)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _contains_any(haystack: str, terms: tuple[str, ...]) -> bool:
    return any(fold(term) in haystack for term in terms)


@dataclass(frozen=True)
class Route:
    intent: str
    identifier: str | None
    search_text: str
    filters: dict[str, object] = field(default_factory=dict)


def extract_identifier(query: str) -> str | None:
    stripped = query.strip()
    skm = SKM_RE.search(stripped)
    if skm:
        return re.sub(r"\s+", "", skm.group(0)).upper().replace("SKM", "SKM", 1)
    oid = OID_RE.search(stripped)
    if oid:
        raw = re.sub(r"\s+", "", oid.group(0))
        digits = re.search(r"\d+", raw)
        if digits:
            return f"skat-info:oid:{digits.group(0)}"
    if BARE_OID_RE.fullmatch(stripped):
        return stripped
    return None


def normalize_skm(identifier: str) -> str:
    compact = re.sub(r"\s+", "", identifier)
    if compact.upper().startswith("SKM"):
        return "SKM" + compact[3:]
    return compact


def route_query(query: str, *, filters: dict[str, object] | None = None) -> Route:
    """A–F i fast rækkefølge. Embeddings indgår aldrig."""
    text = query.strip()
    identifier = extract_identifier(text)
    remainder = text
    if identifier:
        remainder = SKM_RE.sub(" ", remainder)
        remainder = OID_RE.sub(" ", remainder)
        remainder = re.sub(r"\s+", " ", remainder).strip()
    folded = fold(remainder if remainder else text)
    merged_filters = dict(filters or {})

    # A: rent SKM-/OID-opslag.
    if identifier and not remainder:
        return Route(INTENT_EXACT, identifier, "", merged_filters)

    # B–E er kommandoer på et identificeret dokument, ikke emnesøgning.
    # Uden identifier er "afgørelse om moms" F (topical), ikke C (resultatchunks).
    if identifier:
        if _contains_any(folded, SUMMARY_TERMS):
            return Route(INTENT_SUMMARY, identifier, remainder, merged_filters)
        if _contains_any(folded, RESULT_TERMS):
            return Route(INTENT_RESULT, identifier, remainder, merged_filters)
        if _contains_any(folded, REASONING_TERMS):
            return Route(INTENT_REASONING, identifier, remainder, merged_filters)
        if _contains_any(folded, REFERENCE_TERMS):
            return Route(INTENT_REFERENCES, identifier, remainder, merged_filters)
        if _contains_any(folded, QUESTION_TERMS):
            merged_filters.setdefault("section_type", "questions")
            return Route(INTENT_QUESTIONS, identifier, remainder or text, merged_filters)
        if _contains_any(folded, ANSWER_TERMS):
            merged_filters.setdefault("section_type", "answers")
            return Route(INTENT_ANSWERS, identifier, remainder or text, merged_filters)
        return Route(INTENT_EXACT, identifier, remainder, merged_filters)

    if _contains_any(folded, QUESTION_TERMS):
        merged_filters.setdefault("section_type", "questions")
        return Route(INTENT_QUESTIONS, None, text, merged_filters)
    if _contains_any(folded, ANSWER_TERMS):
        merged_filters.setdefault("section_type", "answers")
        return Route(INTENT_ANSWERS, None, text, merged_filters)
    return Route(INTENT_TOPICAL, None, text, merged_filters)
