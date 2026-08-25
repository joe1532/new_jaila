"""Byg flade DJV-noder til opslag fra den rensede JSON.

Kilden er json-cleanerens `build/cleaned/DJV C.*.json` (udgave 2026-2).
Træet flattenes til én post pr. adresse, så runtime slår `C.A.7.1.1` op
uden at gå i HTML-dumpet. Binding til LL § (og stk. når overskriften har
det) læses af overskriften, ikke af en embedding.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

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
_LL_PARA_RE = re.compile(
    r"(?:LL|ligningslovens?)\s*§+\s*(\d+\s*[A-Za-z]?)"
    r"(?!\s*,?\s*stk)"
    r"(?!\s*,?\s*nr)",
    re.IGNORECASE,
)
_SECTION_KEY = re.compile(r"(\d+)\s*([A-Za-z])?", re.IGNORECASE)


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
                    "bindings": bindings_from_heading(heading),
                }
            )
        for child in node.get("children") or []:
            if isinstance(child, dict):
                walk(child)

    for root in roots:
        walk(root)
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


if __name__ == "__main__":
    main()
