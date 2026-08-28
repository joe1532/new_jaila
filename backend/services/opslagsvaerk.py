"""Deterministisk opslag af lovparagraffer (lag A).

Ligningsloven slås op på paragraphNumber i LBKG 1500. Ingen embedding.
Stabilitet mod LBKG 42 og 1735 bruges som metadata, ikke til at gætte ældre tekst.
Indkomstår er slået fra: svaret er altid 1500.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[1] / "opslagsvaerk" / "ligningsloven"

CURRENT_EDITION = "1500"

EDITIONS: dict[str, dict[str, str]] = {
    "1735": {
        "id": "1735",
        "date": "2021-08-17",
        "file": "lbkg-1735-2021-08-17.json",
        "label": "LBKG nr. 1735 af 17. august 2021",
        "short": "1735",
    },
    "42": {
        "id": "42",
        "date": "2023-01-13",
        "file": "lbkg-42-2023-01-13.json",
        "label": "LBKG nr. 42 af 13. januar 2023",
        "short": "42",
    },
    "1500": {
        "id": "1500",
        "date": "2025-11-24",
        "file": "lbkg-1500-2025-11-24.json",
        "label": "LBKG nr. 1500 af 24. november 2025",
        "short": "1500",
    },
}

# Baglæns fra nyeste: hvis hoppet er juridisk uændret, kan 1500 bruges så langt.
STABILITY_HOPS: tuple[tuple[str, str, str], ...] = (
    ("42", "1500", "42-1500"),
    ("1735", "42", "1735-42"),
)

LOOKUP_LAWS = frozenset({"ligningsloven"})

_SECTION_KEY = re.compile(
    r"(\d+)(?:\s*([A-Za-z])(?![A-Za-zæøåÆØÅ]))?",
    re.IGNORECASE,
)
_HYPHEN_RE = re.compile(r"[\u00ad\u2010\u2011\u2012\u2013\u2014\u2212-]")


def paragraph_key(raw: str) -> str:
    """`§ 9 A` / `9 A` / `9a` → `9a`. Tom streng hvis nøglen ikke kan læses."""
    source = str(raw or "").replace("§", " ").strip()
    match = _SECTION_KEY.search(source)
    if not match:
        return ""
    letter = (match.group(2) or "").lower()
    return match.group(1) + letter


def normalize_normative_text(text: str) -> str:
    """Sammenligning uden bindestreg og whitespace. Bruges til at skelne retsændring fra typografi."""
    folded = unicodedata.normalize("NFKC", text or "")
    folded = _HYPHEN_RE.sub("", folded)
    return re.sub(r"\s+", " ", folded).strip().lower()


def lookup_paragraph(law: str, key_or_section: str) -> dict[str, Any] | None:
    """Hent paragrafnoden i nyeste LBKG. Kun ligningsloven i første snit."""
    law_name = str(law or "").strip().lower()
    if law_name not in LOOKUP_LAWS:
        return None
    key = paragraph_key(key_or_section)
    if not key:
        return None
    node = _index(CURRENT_EDITION).get(key)
    if not node:
        return None
    stability = paragraph_stability(key)
    edition = EDITIONS[CURRENT_EDITION]
    label = str(node.get("paragraphLabel") or f"§ {key}").rstrip(".")
    return {
        "law": "ligningsloven",
        "key": key,
        "edition": CURRENT_EDITION,
        "paragraphLabel": node.get("paragraphLabel") or "",
        "normativeText": str(node.get("normativeText") or ""),
        "subsections": node.get("subsections") or [],
        "contentSha256": str(node.get("contentSha256") or ""),
        "filename": f"Ligningsloven ({edition['label']}) {label}",
        "file_id": f"opslag:ll:{key}:{CURRENT_EDITION}",
        "notice": _stability_notice(stability),
        "stability": stability,
    }


def paragraph_stability(key: str) -> dict[str, Any]:
    """Hvor langt tilbage 1500-teksten juridisk kan bruges. Gætter aldrig ældre ordlyd."""
    key = paragraph_key(key)
    current = _index(CURRENT_EDITION).get(key)
    if not current:
        return {
            "stable_since": None,
            "stable_since_edition": None,
            "changed_hops": [],
            "used_lbkg": CURRENT_EDITION,
        }
    stable_edition = CURRENT_EDITION
    changed_hops: list[str] = []
    for older_id, newer_id, hop_id in STABILITY_HOPS:
        if not _hop_legally_unchanged(key, older_id, newer_id, hop_id):
            changed_hops.append(hop_id)
            break
        stable_edition = older_id
    return {
        "stable_since": EDITIONS[stable_edition]["date"],
        "stable_since_edition": stable_edition,
        "changed_hops": changed_hops,
        "used_lbkg": CURRENT_EDITION,
    }


def lookup_hit_for_anchor(anchor: dict[str, str]) -> dict[str, Any] | None:
    """Lag-A-hit til task_search, eller None hvis ankeret ikke er LL eller mangler."""
    if str(anchor.get("kind") or "") == "dbo":
        return None
    found = lookup_paragraph(str(anchor.get("law") or ""), str(anchor.get("section") or ""))
    if not found:
        return None
    text = found["normativeText"].strip()
    if not text:
        return None
    return {
        "file_id": found["file_id"],
        "filename": found["filename"],
        "score": "1",
        "text": text,
        "layer": "A",
        "anchor": str(anchor.get("label") or ""),
        "issue_id": "",
        "from_lookup": True,
        "lookup_notice": found["notice"],
        "lookup_key": found["key"],
        "lookup_stability": found["stability"],
        "lookup_subsections": found["subsections"],
    }


def _stability_notice(stability: dict[str, Any]) -> str:
    used = EDITIONS[CURRENT_EDITION]["label"]
    since = stability.get("stable_since_edition")
    hops = stability.get("changed_hops") or []
    if since == "1735":
        return (
            f"Opslag (ikke søgning). Hele paragrafnoden. {used}. "
            "Normativ tekst uændret siden LBKG 1735 (17. august 2021)."
        )
    if since == "42":
        return (
            f"Opslag (ikke søgning). Hele paragrafnoden. {used}. "
            "Uændret siden LBKG 42 (13. januar 2023). Ændret mellem 1735 og 42; "
            "gælder ikke automatisk før januar 2023."
        )
    hop = hops[0] if hops else "42-1500"
    if hop == "1735-42":
        return (
            f"Opslag (ikke søgning). Hele paragrafnoden. {used}. "
            "Ændret mellem LBKG 1735 og 42. Indkomstår er slået fra; teksten er LBKG 1500. "
            "Gæt ikke virkning for årene imellem."
        )
    return (
        f"Opslag (ikke søgning). Hele paragrafnoden. {used}. "
        "Ændret mellem LBKG 42 (13. januar 2023) og LBKG 1500 (24. november 2025). "
        "Indkomstår er slået fra; teksten er LBKG 1500. Gæt ikke virkning for årene imellem."
    )


def _hop_legally_unchanged(key: str, older_id: str, newer_id: str, hop_id: str) -> bool:
    older = _index(older_id).get(key)
    newer = _index(newer_id).get(key)
    if not older or not newer:
        return False
    if older.get("contentSha256") and older.get("contentSha256") == newer.get("contentSha256"):
        return True
    remaining = [
        row
        for row in _changes()
        if row.get("hop") == hop_id
        and str(row.get("paragraphNumber") or "") == key
        and not row.get("cosmetic")
    ]
    return not remaining


@lru_cache(maxsize=8)
def _index(edition_id: str) -> dict[str, dict[str, Any]]:
    meta = EDITIONS.get(edition_id)
    if not meta:
        return {}
    path = DATA_DIR / meta["file"]
    try:
        nodes = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _log.warning("opslagsvaerk: kunne ikke læse %s: %s", path, exc)
        return {}
    index: dict[str, dict[str, Any]] = {}
    if not isinstance(nodes, list):
        return {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        key = paragraph_key(str(node.get("paragraphNumber") or ""))
        if key:
            index[key] = node
    return index


@lru_cache(maxsize=1)
def _changes() -> list[dict[str, Any]]:
    path = DATA_DIR / "aendringer-2021-2025.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _log.warning("opslagsvaerk: kunne ikke læse ændringer: %s", exc)
        return []
    rows = payload.get("changes") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]
