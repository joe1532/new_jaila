"""Kopiér ligningslovens LBKG-noder og de to 2021-hop ind i backend/opslagsvaerk/.

Kilden er Retsinfo-høsten. `data/` i JAILA er gitignored, så opslaget skal ligge
under `backend/` for at komme med i deploy.

oldText/newText fra jsonl gemmes ikke. Bindestreg-lighed forudberegnes som
`cosmetic`, så promptkoden aldrig ser de to tekster.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HARVEST = Path(
    os.environ.get(
        "RETSINFO_HARVEST_DIR",
        r"C:\Users\minel\OneDrive\- Projekter\Retsinfo-lbkg-familier",
    )
)
FAMILY = HARVEST / "data" / "families" / "ligningsloven"
CHUNKS = FAMILY / "structured-chunks"
JSONL = FAMILY / "reports" / "lbkg-sammenligning-struktureret" / "rapport.jsonl"
DEST = REPO / "backend" / "opslagsvaerk" / "ligningsloven"

EDITIONS = [
    {
        "id": "1735",
        "date": "2021-08-17",
        "source": "Lbkg Nr. 1735 af 17. august 2021 - struktureret.json",
        "dest": "lbkg-1735-2021-08-17.json",
    },
    {
        "id": "42",
        "date": "2023-01-13",
        "source": "Lbkg Nr. 42 af 13. januar 2023 - struktureret.json",
        "dest": "lbkg-42-2023-01-13.json",
    },
    {
        "id": "1500",
        "date": "2025-11-24",
        "source": "Lbkg Nr. 1500 af 24. november 2025 - struktureret.json",
        "dest": "lbkg-1500-2025-11-24.json",
    },
]

# Kun hoppene 1735→42 og 42→1500. Ældre linjer i jsonl ignoreres.
HOPS = {
    ("2021-08-17", "2023-01-13"): "1735-42",
    ("2023-01-13", "2025-11-24"): "42-1500",
}

_HYPHEN_RE = re.compile(r"[\u00ad\u2010\u2011\u2012\u2013\u2014\u2212-]")


def _compact_dump(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def _normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text or "")
    folded = _HYPHEN_RE.sub("", folded)
    return re.sub(r"\s+", " ", folded).strip().lower()


def _is_cosmetic(change: dict) -> bool:
    if change.get("editorial") is True:
        return True
    if str(change.get("level") or "") == "note":
        return True
    if str(change.get("changeType") or "") != "TEXT_CHANGED":
        return False
    return _normalize(change.get("oldText") or "") == _normalize(change.get("newText") or "")


def _copy_editions() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    for edition in EDITIONS:
        src = CHUNKS / edition["source"]
        if not src.is_file():
            raise FileNotFoundError(src)
        nodes = json.loads(src.read_text(encoding="utf-8"))
        _compact_dump(DEST / edition["dest"], nodes)
        print(f"copied {edition['id']}: {len(nodes)} noder")


def _filter_changes() -> None:
    if not JSONL.is_file():
        raise FileNotFoundError(JSONL)
    rows: list[dict] = []
    with JSONL.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            hop = HOPS.get((obj["from"]["documentDate"], obj["to"]["documentDate"]))
            if not hop:
                continue
            change = obj.get("change") or {}
            rows.append(
                {
                    "hop": hop,
                    "paragraphNumber": str(change.get("paragraphNumber") or ""),
                    "level": str(change.get("level") or ""),
                    "changeType": str(change.get("changeType") or ""),
                    "editorial": bool(change.get("editorial")),
                    "cosmetic": _is_cosmetic(change),
                }
            )
    payload = {
        "source": "Retsinfo-lbkg-familier rapport.jsonl, kun hop 1735→42 og 42→1500",
        "hops": [
            {"id": "1735-42", "from": "1735", "to": "42"},
            {"id": "42-1500", "from": "42", "to": "1500"},
        ],
        "changes": rows,
    }
    _compact_dump(DEST / "aendringer-2021-2025.json", payload)
    legal = sum(1 for row in rows if not row["cosmetic"])
    print(f"jsonl-hop 2021+: {len(rows)} linjer, {legal} juridiske")


def main() -> None:
    if not FAMILY.is_dir():
        raise SystemExit(f"Høst mangler: {FAMILY}")
    _copy_editions()
    _filter_changes()
    readme = REPO / "backend" / "opslagsvaerk" / "README.md"
    if not readme.is_file():
        readme.write_text(
            "Lovtekst-noder til lag A. Importeret med "
            "`python -m backend.tools.import_opslagsvaerk`.\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
