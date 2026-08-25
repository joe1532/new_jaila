"""Opgaveløsning: vurder om faktum rækker, før der søges og skrives notat."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from openai import OpenAI

from backend.config import FALLBACK_MODEL, PRIMARY_MODEL
from backend.services.openai_service import cache_fields_for_model, get_value

_log = logging.getLogger(__name__)

MAX_QUESTIONS = 5
MAX_ADDED_QUESTIONS = 3
MIN_EXCERPT_CHARS = 24
ALLOWED_KINDS = frozenset({"yes_no", "text", "amount", "number", "date", "country"})
ALLOWED_STATUS = frozenset({"KNOWN", "UNKNOWN"})
ALLOWED_MATERIALITY = frozenset({"DECISIVE", "RELEVANT", "IRRELEVANT"})
PROMPT_CACHE_KEY = "jaila-task-intake-v4"
EXPAND_CACHE_KEY = "jaila-task-expand-v1"
_COUNT_HINT = re.compile(
    r"\b(dage?|måneder|måned|timer?|uge[nr]?|antal)\b",
    re.IGNORECASE,
)
_MONEY_HINT = re.compile(
    r"\b(kr\.?|kroner|beløb|indkomst|løn|honorar)\b",
    re.IGNORECASE,
)

INTAKE_INSTRUCTIONS = """Du vurderer, om en konkret skatteretlig opgave kan subsumeres,
eller om der mangler faktiske oplysninger, der realistisk kan ændre konklusionen.

Du søger ikke i retskilder. Du skriver ikke et notat. Du returnerer kun JSON.

Porten er ikke "mangler der oplysninger?", men "mangler der oplysninger, som
realistisk kan ændre den juridiske konklusion?".

Materialitet
- DECISIVE: hvis faktum vender, vender udfaldet af dette issue. Kun DECISIVE +
  UNKNOWN må stoppe analysen.
- RELEVANT: bør indgå i et senere notat, men må ikke stoppe. Stil ikke spørgsmål.
- IRRELEVANT: må ikke medtages og må ikke spørges om.

Status
- KNOWN: faktum er oplyst i beskeden eller i oplagt materiale.
- UNKNOWN: faktum er ikke oplyst.

Hvornår can_proceed er true
- Beskeden er et retligt spørgsmål uden konkret sag. Da er issues tom.
- Ingen required_facts har status UNKNOWN og materiality DECISIVE.

Hvornår can_proceed er false
- Mindst ét DECISIVE-faktum er UNKNOWN. question og kind udfyldes kun på disse.

Spørgsmål
- question er den formulering, brugeren skal besvare. Kun ved DECISIVE + UNKNOWN.
- kind: yes_no, text, amount, number, date eller country.
- amount er kun penge (kr.). number er antal: dage, måneder, timer, uger. "Hvor
  mange dage" er number, aldrig amount.
- Spørg ikke om det, der allerede er KNOWN. Spørg ikke hvilken regel det er, hvis
  brugeren har anvist lov og paragraf. Spørg efter de fakta, den regel kræver.
- Sæt ikke 42-dage, DBO, dokumentation eller lignende til DECISIVE, medmindre
  udfaldet af netop dette issue vender, hvis det faktum vender.

Personkreds
- En regels henvisning til en skattepligtsbestemmelse er ikke automatisk den
  eneste vej ind i personkredsen. Spørg ikke ja/nej om fuld skattepligt, hvis
  flere statusser kan være afgørende. Spørg hvilken skattepligtsstatus der
  gælder (text), når det er DECISIVE og UNKNOWN.
- Har brugeren allerede angivet en status ved navn eller henvisning, er den
  KNOWN. Spørg ikke om en anden skattepligtsregel, som om den status ikke
  findes.

Sprog: dansk i question, fact og question-feltet på unknown facts."""

EXPAND_INSTRUCTIONS = """Du udvider issue-kortet med betingelser, der først fremgår af de hentede
retskilder. Du søger ikke. Du skriver ikke et notat. Du returnerer kun JSON.

Regler
- Tilføj kun et faktum, hvis det er begrundet i et konkret uddrag under
  "Hentede retskilder". source_excerpt skal være et ordret citat fra uddraget.
- Opfind ikke statusser, personkredse, afgørelser eller ekstra love, som ikke
  står i uddragene.
- Har brugeren allerede oplyst faktum i beskeden, er status KNOWN. Spørg ikke.
- Gentag ikke et faktum, der allerede er på issue-kortet, heller ikke med anden
  formulering.
- Materialitet som i intake: DECISIVE kun hvis udfaldet af issue vender, hvis
  faktum vender. RELEVANT må medtages, men stiller ikke spørgsmål.
- question og kind kun ved DECISIVE + UNKNOWN.
- Højst tre nye DECISIVE-spørgsmål.
- Er beskeden et retligt spørgsmål uden konkret sag, skal additions være tom.
- Tilføjer kilderne intet nyt, skal additions være tom."""

INTAKE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "can_proceed": {"type": "boolean"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "issue_id": {"type": "string"},
                    "question": {"type": "string"},
                    "required_facts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "fact": {"type": "string"},
                                "status": {"type": "string", "enum": ["KNOWN", "UNKNOWN"]},
                                "materiality": {
                                    "type": "string",
                                    "enum": ["DECISIVE", "RELEVANT", "IRRELEVANT"],
                                },
                                "question": {"type": "string"},
                                "kind": {
                                    "type": "string",
                                    "enum": [
                                        "yes_no",
                                        "text",
                                        "amount",
                                        "number",
                                        "date",
                                        "country",
                                    ],
                                },
                            },
                            "required": [
                                "fact",
                                "status",
                                "materiality",
                                "question",
                                "kind",
                            ],
                        },
                    },
                },
                "required": ["issue_id", "question", "required_facts"],
            },
        },
    },
    "required": ["can_proceed", "issues"],
}

EXPAND_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "additions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "issue_id": {"type": "string"},
                    "issue_question": {"type": "string"},
                    "fact": {"type": "string"},
                    "status": {"type": "string", "enum": ["KNOWN", "UNKNOWN"]},
                    "materiality": {
                        "type": "string",
                        "enum": ["DECISIVE", "RELEVANT", "IRRELEVANT"],
                    },
                    "question": {"type": "string"},
                    "kind": {
                        "type": "string",
                        "enum": [
                            "yes_no",
                            "text",
                            "amount",
                            "number",
                            "date",
                            "country",
                        ],
                    },
                    "source_excerpt": {"type": "string"},
                    "source_filename": {"type": "string"},
                },
                "required": [
                    "issue_id",
                    "issue_question",
                    "fact",
                    "status",
                    "materiality",
                    "question",
                    "kind",
                    "source_excerpt",
                    "source_filename",
                ],
            },
        },
    },
    "required": ["additions"],
}


def pin_legal_locus(question: str, legal_locus: str) -> str:
    """Lås første søgning til den anviste bestemmelse. Tom anvisning ændrer intet."""
    locus = str(legal_locus or "").strip()
    body = str(question or "").strip()
    if not locus:
        return body
    return (
        f"Retligt udgangspunkt anvist af brugeren: {locus}\n"
        "Søg først denne lovbestemmelse (lovens navn og paragrafnummer) i selve "
        "lovteksten. Søg derefter praksis og Den juridiske vejledning om samme emne.\n\n"
        + body
    )


def parse_intake_payload(raw: object) -> dict[str, Any]:
    """Normalisér modellens JSON. Fejler den, behandles sagen som tilstrækkelig."""
    data: Any = raw
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            _log.warning("task_solve intake: ugyldig JSON, fortsætter uden stop")
            return _empty_proceed()
    if not isinstance(data, dict):
        return _empty_proceed()

    issues: list[dict[str, Any]] = []
    for index, item in enumerate(data.get("issues") or []):
        if not isinstance(item, dict):
            continue
        legal_question = str(
            item.get("question") or item.get("legal_question") or ""
        ).strip()
        if not legal_question:
            continue
        issue_id = str(item.get("issue_id") or item.get("id") or f"I{index + 1}").strip()
        facts = _parse_required_facts(item.get("required_facts"))
        issues.append(
            {
                "id": issue_id,
                "issue_id": issue_id,
                "question": legal_question,
                "legal_question": legal_question,
                "required_facts": facts,
            }
        )

    questions = _questions_from_facts(issues)[:MAX_QUESTIONS]
    can_proceed = not any(
        fact["status"] == "UNKNOWN" and fact["materiality"] == "DECISIVE"
        for issue in issues
        for fact in issue["required_facts"]
    )
    return {
        "can_proceed": can_proceed,
        "sufficient": can_proceed,
        "issues": issues,
        "questions": questions,
    }


def normalize_question_kind(kind: object, question: str = "", fact: str = "") -> str:
    """amount er penge. Antal dage/måneder må ikke lande som beløb i kr."""
    raw = str(kind or "text").strip()
    blob = f"{question} {fact}"
    if _COUNT_HINT.search(blob) and not _MONEY_HINT.search(blob):
        return "number"
    if raw not in ALLOWED_KINDS:
        return "text"
    return raw


def should_ask_facts(intake: dict[str, Any]) -> bool:
    """Stop kun ved DECISIVE + UNKNOWN, og kun hvis der er et spørgsmål at stille."""
    if intake.get("can_proceed", intake.get("sufficient", True)):
        return False
    return bool(intake.get("questions"))


def assess_task_facts(
    client: OpenAI,
    message: str,
    legal_locus: str = "",
    context_text: str = "",
) -> dict[str, Any]:
    """Ét kald uden file_search. Returnerer normaliseret intake-dict."""
    user_input = _intake_user_input(message, legal_locus, context_text)
    models = [PRIMARY_MODEL, FALLBACK_MODEL]
    last_error: Exception | None = None
    for model in models:
        try:
            raw = _call_intake(client, model, user_input, use_schema=True)
            return parse_intake_payload(raw)
        except Exception as exc:
            last_error = exc
            _log.warning("task_solve intake schema-kald fejlede (%s): %s", model, exc)
            try:
                raw = _call_intake(client, model, user_input, use_schema=False)
                return parse_intake_payload(raw)
            except Exception as fallback_exc:
                last_error = fallback_exc
                _log.warning(
                    "task_solve intake fritekst-kald fejlede (%s): %s",
                    model,
                    fallback_exc,
                )
    _log.error("task_solve intake gav op: %s", last_error)
    return _empty_proceed()


def expand_issue_map(
    client: OpenAI,
    message: str,
    retrieved_context: str,
    legal_locus: str = "",
    issues: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Én udvidelse efter retrieval. Kun facts med citat i de hentede uddrag."""
    base = [item for item in (issues or []) if isinstance(item, dict)]
    context = str(retrieved_context or "").strip()
    if not context:
        return parse_intake_payload({"issues": base})

    user_input = _expand_user_input(message, legal_locus, base, context)
    models = [PRIMARY_MODEL, FALLBACK_MODEL]
    last_error: Exception | None = None
    for model in models:
        try:
            raw = _call_expand(client, model, user_input, use_schema=True)
            additions = parse_expansion_additions(raw)
            return apply_issue_additions(base, additions, context)
        except Exception as exc:
            last_error = exc
            _log.warning("task_solve expand schema-kald fejlede (%s): %s", model, exc)
            try:
                raw = _call_expand(client, model, user_input, use_schema=False)
                additions = parse_expansion_additions(raw)
                return apply_issue_additions(base, additions, context)
            except Exception as fallback_exc:
                last_error = fallback_exc
                _log.warning(
                    "task_solve expand fritekst-kald fejlede (%s): %s",
                    model,
                    fallback_exc,
                )
    _log.error("task_solve expand gav op: %s", last_error)
    return parse_intake_payload({"issues": base})


def parse_expansion_additions(raw: object) -> list[dict[str, Any]]:
    """Normalisér modellens additions. Ugyldig JSON giver tom liste."""
    data: Any = raw
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            _log.warning("task_solve expand: ugyldig JSON, ignorerer udvidelse")
            return []
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = data.get("additions") or []
    else:
        return []
    if not isinstance(rows, list):
        return []

    additions: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        label = str(item.get("fact") or "").strip()
        excerpt = str(item.get("source_excerpt") or "").strip()
        if not label or not excerpt:
            continue
        status = str(item.get("status") or "UNKNOWN").strip().upper()
        if status not in ALLOWED_STATUS:
            status = "UNKNOWN"
        materiality = str(item.get("materiality") or "RELEVANT").strip().upper()
        if materiality not in ALLOWED_MATERIALITY:
            materiality = "RELEVANT"
        if materiality == "IRRELEVANT":
            continue
        prompt = str(item.get("question") or "").strip()
        kind = normalize_question_kind(item.get("kind"), prompt, label)
        additions.append(
            {
                "issue_id": str(item.get("issue_id") or "").strip(),
                "issue_question": str(item.get("issue_question") or "").strip(),
                "fact": label,
                "status": status,
                "materiality": materiality,
                "question": prompt,
                "kind": kind,
                "source_excerpt": excerpt,
                "source_filename": str(item.get("source_filename") or "").strip(),
            }
        )
    return additions


def excerpt_is_grounded(excerpt: str, context: str) -> bool:
    """Kræver at citatet står i de hentede uddrag. Ingen paraphrasering."""
    needle = _fold_text(excerpt)
    haystack = _fold_text(context)
    if len(needle) < MIN_EXCERPT_CHARS:
        return False
    return needle in haystack


def apply_issue_additions(
    base_issues: list[dict[str, Any]],
    additions: list[dict[str, Any]],
    retrieved_context: str,
) -> dict[str, Any]:
    """Merge kun grounded, ikke-duplikerede facts. can_proceed beregnes i kode."""
    merged = [_clone_issue(item) for item in base_issues if isinstance(item, dict)]
    known_flat: set[str] = set()
    for issue in merged:
        known_flat.update(_fact_keys(issue))
    added_questions = 0
    new_prompts: set[str] = set()

    for item in additions:
        if not excerpt_is_grounded(str(item.get("source_excerpt") or ""), retrieved_context):
            continue
        fact_key = _fold_text(str(item.get("fact") or ""))
        question_key = _fold_text(str(item.get("question") or ""))
        if fact_key in known_flat or (question_key and question_key in known_flat):
            continue
        if item.get("status") == "UNKNOWN" and item.get("materiality") == "DECISIVE":
            if added_questions >= MAX_ADDED_QUESTIONS:
                continue
            added_questions += 1
        issue = _match_or_create_issue(merged, item)
        fact_row = {
            "fact": item["fact"],
            "status": item["status"],
            "materiality": item["materiality"],
            "question": item.get("question") or "",
            "kind": item.get("kind") or "text",
            "source_excerpt": item.get("source_excerpt") or "",
            "source_filename": item.get("source_filename") or "",
        }
        issue["required_facts"].append(fact_row)
        known_flat.update(_fact_keys(issue))
        prompt = _fold_text(str(item.get("question") or item.get("fact") or ""))
        if (
            prompt
            and item.get("status") == "UNKNOWN"
            and item.get("materiality") == "DECISIVE"
        ):
            new_prompts.add(prompt)

    parsed = parse_intake_payload({"issues": merged})
    if new_prompts:
        parsed["questions"] = [
            question
            for question in parsed["questions"]
            if _fold_text(question.get("prompt") or "") in new_prompts
        ]
        parsed["can_proceed"] = not parsed["questions"]
        parsed["sufficient"] = parsed["can_proceed"]
    else:
        parsed["questions"] = []
        parsed["can_proceed"] = True
        parsed["sufficient"] = True
    return parsed


def _empty_proceed() -> dict[str, Any]:
    return {"can_proceed": True, "sufficient": True, "issues": [], "questions": []}


def _parse_required_facts(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    facts: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        label = str(item.get("fact") or "").strip()
        if not label:
            continue
        status = str(item.get("status") or "UNKNOWN").strip().upper()
        if status not in ALLOWED_STATUS:
            status = "UNKNOWN"
        materiality = str(item.get("materiality") or "RELEVANT").strip().upper()
        if materiality not in ALLOWED_MATERIALITY:
            materiality = "RELEVANT"
        prompt = str(item.get("question") or "").strip()
        kind = normalize_question_kind(item.get("kind"), prompt, label)
        row = {
            "fact": label,
            "status": status,
            "materiality": materiality,
            "question": prompt,
            "kind": kind,
        }
        excerpt = str(item.get("source_excerpt") or "").strip()
        filename = str(item.get("source_filename") or "").strip()
        if excerpt:
            row["source_excerpt"] = excerpt
        if filename:
            row["source_filename"] = filename
        facts.append(row)
    return facts


def _questions_from_facts(issues: list[dict[str, Any]]) -> list[dict[str, str]]:
    questions: list[dict[str, str]] = []
    for issue in issues:
        issue_id = str(issue.get("id") or "I")
        for index, fact in enumerate(issue.get("required_facts") or []):
            if fact.get("status") != "UNKNOWN" or fact.get("materiality") != "DECISIVE":
                continue
            prompt = str(fact.get("question") or "").strip() or str(fact.get("fact") or "").strip()
            if not prompt:
                continue
            kind = normalize_question_kind(
                fact.get("kind"), prompt, str(fact.get("fact") or "")
            )
            questions.append(
                {
                    "id": f"{issue_id}-f{index + 1}",
                    "prompt": prompt,
                    "kind": kind,
                }
            )
            if len(questions) >= MAX_QUESTIONS:
                return questions
    return questions


def _intake_user_input(message: str, legal_locus: str, context_text: str) -> str:
    locus = str(legal_locus or "").strip() or "(ikke anvist)"
    uploaded = str(context_text or "").strip() or "(intet)"
    return (
        "Faktum / opgave:\n"
        f"{str(message or '').strip()}\n\n"
        "Retligt udgangspunkt:\n"
        f"{locus}\n\n"
        "Materiale lagt op af brugeren:\n"
        f"{uploaded}"
    )


def _expand_user_input(
    message: str,
    legal_locus: str,
    issues: list[dict[str, Any]],
    retrieved_context: str,
) -> str:
    locus = str(legal_locus or "").strip() or "(ikke anvist)"
    compact = []
    for issue in issues:
        compact.append(
            {
                "issue_id": issue.get("issue_id") or issue.get("id") or "",
                "question": issue.get("question") or issue.get("legal_question") or "",
                "required_facts": [
                    {
                        "fact": fact.get("fact"),
                        "status": fact.get("status"),
                        "materiality": fact.get("materiality"),
                    }
                    for fact in issue.get("required_facts") or []
                    if isinstance(fact, dict)
                ],
            }
        )
    return (
        "Faktum / opgave:\n"
        f"{str(message or '').strip()}\n\n"
        "Retligt udgangspunkt:\n"
        f"{locus}\n\n"
        "Nuværende issue-kort:\n"
        f"{json.dumps(compact, ensure_ascii=False)}\n\n"
        f"{retrieved_context}"
    )


def _fold_text(value: str) -> str:
    return " ".join(str(value or "").lower().split())


def _clone_issue(issue: dict[str, Any]) -> dict[str, Any]:
    legal_question = str(issue.get("question") or issue.get("legal_question") or "").strip()
    issue_id = str(issue.get("issue_id") or issue.get("id") or "").strip()
    facts = []
    for fact in issue.get("required_facts") or []:
        if not isinstance(fact, dict):
            continue
        facts.append(dict(fact))
    return {
        "id": issue_id,
        "issue_id": issue_id,
        "question": legal_question,
        "legal_question": legal_question,
        "required_facts": facts,
    }


def _fact_keys(issue: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for fact in issue.get("required_facts") or []:
        if not isinstance(fact, dict):
            continue
        label = _fold_text(str(fact.get("fact") or ""))
        prompt = _fold_text(str(fact.get("question") or ""))
        if label:
            keys.add(label)
        if prompt:
            keys.add(prompt)
    return keys


def _match_or_create_issue(
    merged: list[dict[str, Any]],
    item: dict[str, Any],
) -> dict[str, Any]:
    wanted_id = _fold_text(str(item.get("issue_id") or ""))
    wanted_question = _fold_text(str(item.get("issue_question") or ""))
    for issue in merged:
        issue_id = _fold_text(str(issue.get("issue_id") or issue.get("id") or ""))
        legal = _fold_text(str(issue.get("question") or issue.get("legal_question") or ""))
        if wanted_id and issue_id == wanted_id:
            return issue
        if wanted_question and legal == wanted_question:
            return issue
    legal_question = str(item.get("issue_question") or "").strip() or (
        "Nye betingelser fra de hentede kilder"
    )
    issue_id = str(item.get("issue_id") or "").strip() or f"I{len(merged) + 1}"
    existing_ids = {
        _fold_text(str(issue.get("issue_id") or issue.get("id") or "")) for issue in merged
    }
    if _fold_text(issue_id) in existing_ids:
        issue_id = f"I{len(merged) + 1}"
    created = {
        "id": issue_id,
        "issue_id": issue_id,
        "question": legal_question,
        "legal_question": legal_question,
        "required_facts": [],
    }
    merged.append(created)
    return created


def _call_intake(client: OpenAI, model: str, user_input: str, use_schema: bool) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "instructions": INTAKE_INSTRUCTIONS,
        "input": user_input,
        "reasoning": {"effort": "low"},
        "prompt_cache_key": PROMPT_CACHE_KEY,
        **cache_fields_for_model(model),
    }
    if use_schema:
        payload["text"] = {
            "format": {
                "type": "json_schema",
                "name": "task_intake",
                "strict": True,
                "schema": INTAKE_SCHEMA,
            }
        }
    else:
        payload["instructions"] = (
            INTAKE_INSTRUCTIONS + "\n\nSvar kun med ét JSON-objekt. Ingen markdown."
        )
    resp = client.responses.create(**payload)
    return str(get_value(resp, "output_text", "") or "")


def _call_expand(client: OpenAI, model: str, user_input: str, use_schema: bool) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "instructions": EXPAND_INSTRUCTIONS,
        "input": user_input,
        "reasoning": {"effort": "low"},
        "prompt_cache_key": EXPAND_CACHE_KEY,
        **cache_fields_for_model(model),
    }
    if use_schema:
        payload["text"] = {
            "format": {
                "type": "json_schema",
                "name": "task_expand",
                "strict": True,
                "schema": EXPAND_SCHEMA,
            }
        }
    else:
        payload["instructions"] = (
            EXPAND_INSTRUCTIONS + "\n\nSvar kun med ét JSON-objekt. Ingen markdown."
        )
    resp = client.responses.create(**payload)
    return str(get_value(resp, "output_text", "") or "")
