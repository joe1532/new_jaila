"""Byg flade DJV-noder til opslag fra den rensede JSON.

Kilden er json-cleanerens `build/cleaned/DJV C.*.json` (udgave 2026-2).
Træet flattenes til én post pr. adresse, så runtime slår `C.A.7.1.1` op
uden at gå i HTML-dumpet. Binding til LL § læses af overskriften og af afsnittets Regel/indledning,
ikke af eksempler, «Se også» eller praksistabellen, og ikke af en embedding.
Umærket barn arver den paragraf, flertallet af søskende er bundet til.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

from backend.services.djv_opslag import split_practice

REPO = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = Path(
    os.environ.get(
        "DJV_CLEANED_DIR",
        r"C:\Users\minel\OneDrive\- Projekter\josn-cleaner\build\cleaned",
    )
)
DEST = REPO / "backend" / "opslagsvaerk" / "djv"
EDITION = "2026-2"
SOURCES = (
    ("DJV C.A.json", "c-a.json"),
    ("DJV C.F.json", "c-f.json"),
    ("DJV C.H.json", "c-h.json"),
)

_ADDRESS_RE = re.compile(r"^(C\.[A-Z](?:\.\d+)*)\b")
_LL_STK_RE = re.compile(
    r"(?:LL|ligningslovens?)\s*§+\s*(\d+\s*[A-Za-z]?)\s*,?\s*stk\.?\s*(\d+)",
    re.IGNORECASE,
)
# Paragraf uden stk. «nr. 1» under § 7 er ikke en selvstændig opslagsnøgle.
# Ikke «§ 9» inde i «§ 9 A»: bogstavet skal med, ellers matcher lookaheaden ikke.
_LL_PARA_RE = re.compile(
    r"(?:LL|ligningslovens?)\s*§+\s*(\d+(?:\s*[A-Za-z])?)"
    r"(?!\s*[A-Za-z])"
    r"(?!\s*,?\s*stk)"
    r"(?!\s*,?\s*nr)",
    re.IGNORECASE,
)
_SECTION_KEY = re.compile(r"(\d+)\s*([A-Za-z])?", re.IGNORECASE)
_REGEL_HEADING = re.compile(r"(?m)^#+\s*Regel\b")
_HEADING_LINE = re.compile(r"(?m)^#{1,6}\s+.+$")
# Eksempler og henvisningsbokse. «LL § 9 C» i et mod-eksempel er ikke nodens hjemmel.
_SKIP_SECTION_HEADING = re.compile(
    r"(?i)^#{1,6}\s+(?:eksempel(?:er)?|se også)\b"
)
# Kun indledningen. Hele kroppen før tabellen har for mange «se også §».
_LEAD_CHARS = 2500


def paragraph_key(raw: str) -> str:
    source = str(raw or "").replace("§", " ").strip()
    match = _SECTION_KEY.search(source)
    if not match:
        return ""
    letter = (match.group(2) or "").lower()
    return match.group(1) + letter


def address_of(heading: str) -> str:
    match = _ADDRESS_RE.match(str(heading or "").strip())
    return match.group(1) if match else ""


def bindings_from_heading(heading: str) -> list[dict[str, str | int]]:
    source = str(heading or "")
    found: list[dict[str, str | int]] = []
    seen: set[tuple[str, int | None]] = set()
    stk_spans: list[tuple[int, int]] = []

    for match in _LL_STK_RE.finditer(source):
        key = paragraph_key(match.group(1))
        stk = int(match.group(2))
        stk_spans.append((match.start(), match.end()))
        if not key or (key, stk) in seen:
            continue
        seen.add((key, stk))
        found.append({"law": "ligningsloven", "key": key, "stk": stk})

    for match in _LL_PARA_RE.finditer(source):
        if any(start <= match.start() < end for start, end in stk_spans):
            continue
        key = paragraph_key(match.group(1))
        if not key or (key, None) in seen:
            continue
        seen.add((key, None))
        found.append({"law": "ligningsloven", "key": key})
    return found


def _without_skip_sections(text: str) -> str:
    """Fjern eksempel- og Se også-afsnit, før lapperne læses."""
    source = str(text or "")
    headings = list(_HEADING_LINE.finditer(source))
    if not headings:
        return source
    kept = [source[: headings[0].start()]]
    for index, match in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(source)
        if _SKIP_SECTION_HEADING.match(match.group(0)):
            continue
        kept.append(source[match.start() : end])
    return "".join(kept)


def lead_for_bindings(text: str) -> str:
    """Teksten lapperne må læses af: Regel-brødteksten, ellers starten af kroppen.

    Eksempler og Se også tæller ikke. Næste overskrift (Bemærk) tæller ikke,
    så en henvisning i en boks ikke binder noden til den forkerte paragraf.
    """
    body, _practice = split_practice(text)
    if not body:
        return ""
    body = _without_skip_sections(body)
    if not body.strip():
        return ""
    match = _REGEL_HEADING.search(body)
    if not match:
        return body[:_LEAD_CHARS]
    rest = body[match.end() :]
    stop = re.search(r"\n#{1,6}\s+", rest)
    chunk = rest[: stop.start()] if stop else rest
    return chunk[:_LEAD_CHARS]


def bindings_from_node(heading: str, text: str) -> list[dict[str, str | int]]:
    """Overskrift først (stk. når det står der). Kroppen giver kun paragrafnøgle."""
    found = bindings_from_heading(heading)
    seen_keys = {str(item.get("key") or "") for item in found if item.get("key")}
    lead = lead_for_bindings(text)
    if not lead:
        return found
    stk_spans = [(match.start(), match.end()) for match in _LL_STK_RE.finditer(lead)]
    for match in list(_LL_STK_RE.finditer(lead)) + list(_LL_PARA_RE.finditer(lead)):
        if match.re is not _LL_STK_RE and any(
            start <= match.start() < end for start, end in stk_spans
        ):
            continue
        key = paragraph_key(match.group(1))
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        found.append({"law": "ligningsloven", "key": key})
    return found


def _parent_address(address: str) -> str:
    source = str(address or "")
    if "." not in source:
        return ""
    return source.rsplit(".", 1)[0]


def inherit_sibling_bindings(nodes: list[dict]) -> None:
    """Umærket barn arver (lov, paragraf), som flertallet af søskende bærer.

    C.A.5.14.1.11 citerer ikke LL i Regel, men hører til firmabil-familien.
    Kræver mindst to mærkede søskende, så et enligt nabo-citat ikke smitter.
    """
    children_of: dict[str, list[dict]] = defaultdict(list)
    for node in nodes:
        parent = _parent_address(str(node.get("address") or ""))
        if parent:
            children_of[parent].append(node)
    for children in children_of.values():
        bound = [node for node in children if node.get("bindings")]
        unbound = [node for node in children if not node.get("bindings")]
        if not unbound or len(bound) < 2:
            continue
        counts: Counter[tuple[str, str]] = Counter()
        for node in bound:
            seen: set[tuple[str, str]] = set()
            for item in node.get("bindings") or []:
                if not isinstance(item, dict):
                    continue
                law = str(item.get("law") or "").strip()
                key = str(item.get("key") or "").strip()
                pair = (law, key)
                if not law or not key or pair in seen:
                    continue
                seen.add(pair)
                counts[pair] += 1
        majority = len(bound) / 2
        inherited = [
            {"law": law, "key": key}
            for (law, key), count in counts.items()
            if count > majority
        ]
        if not inherited:
            continue
        for node in unbound:
            node["bindings"] = [dict(item) for item in inherited]


def finalize_node_bindings(nodes: list[dict]) -> None:
    """Sæt lapper fra overskrift/Regel og arv umærkede søskende.

    Køres både ved import og ved indlæsning, så en ældre c-a.json får
    den samme mærkning uden at skulle flattenes forfra.
    """
    for node in nodes:
        node["bindings"] = bindings_from_node(
            str(node.get("heading") or ""),
            str(node.get("text") or ""),
        )
    inherit_sibling_bindings(nodes)


def flatten_tree(payload: object, edition: str = EDITION) -> list[dict]:
    roots: list[dict]
    if isinstance(payload, list):
        roots = [item for item in payload if isinstance(item, dict)]
    elif isinstance(payload, dict):
        roots = [payload]
    else:
        return []

    nodes: list[dict] = []
    seen: set[str] = set()

    def walk(node: dict) -> None:
        heading = str(node.get("Overskrift") or "").strip()
        address = address_of(heading)
        if address and address not in seen:
            seen.add(address)
            text = str(node.get("Tekst") or node.get("Indledning") or "").strip()
            nodes.append(
                {
                    "address": address,
                    "heading": heading,
                    "oid": str(node.get("oid") or ""),
                    "id": str(node.get("id") or ""),
                    "edition": edition,
                    "text": text,
                    "bindings": bindings_from_node(heading, text),
                }
            )
        for child in node.get("children") or []:
            if isinstance(child, dict):
                walk(child)

    for root in roots:
        walk(root)
    inherit_sibling_bindings(nodes)
    return nodes


def import_volume(source: Path, dest: Path, edition: str = EDITION) -> tuple[int, int]:
    payload = json.loads(source.read_text(encoding="utf-8"))
    nodes = flatten_tree(payload, edition=edition)
    if not nodes:
        raise SystemExit(f"Ingen DJV-noder i {source}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(nodes, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    bound = sum(1 for node in nodes if node["bindings"])
    return len(nodes), bound


def main() -> None:
    for source_name, dest_name in SOURCES:
        source = DEFAULT_SOURCE / source_name
        if not source.is_file():
            raise SystemExit(f"Renset DJV mangler: {source}")
        dest = DEST / dest_name
        count, bound = import_volume(source, dest)
        print(f"{source_name}: {count} noder, {bound} med LL-binding -> {dest}")
    meta = DEST / "edition.json"
    meta.write_text(
        json.dumps(
            {
                "edition": EDITION,
                "volumes": ["C.A", "C.F", "C.H"],
                "source": str(DEFAULT_SOURCE),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"DJV-udgave {EDITION} -> {meta}")
    _clear_lookup_cache()


def _clear_lookup_cache() -> None:
    from backend.services import djv_opslag as opslag

    for name in (
        "_edition_meta",
        "_nodes",
        "_address_index",
        "_binding_index",
        "_paragraph_index",
    ):
        getattr(opslag, name).cache_clear()


if __name__ == "__main__":
    main()
