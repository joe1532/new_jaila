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


def lookup_djv_hits(
    anchors: list[dict[str, str]],
    doors: list[dict[str, str]],
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
        if not nodes:
            nodes = para_index.get((law, key)) or []
        for node in nodes:
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
    stks = []
    seen_stk: set[int] = set()
    for door in doors:
        match = _STK_LABEL_RE.search(str(door.get("label") or ""))
        if not match:
            continue
        stk = int(match.group(1))
        if stk in seen_stk:
            continue
        seen_stk.add(stk)
        stks.append(stk)
    if not stks:
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
    """Noder hvis overskrift nævner LL § uden stk. Bruges når stk-adressen mangler."""
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
