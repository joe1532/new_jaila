#!/usr/bin/env python3
"""Build frontend-ready legal source catalog JSON for Norden DBO."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from pypdf import PdfReader


VERSION_PATTERN = re.compile(r"_v(\d{4})$")
KARNOV_LINE_PATTERN = re.compile(
    r"printet fra karnov til brug i overensstemmelse med licensvilk[aå]rene",
    re.IGNORECASE,
)
PREVIEW_START_MARKER_PATTERN = re.compile(
    r"er\s+blevet\s+enige\s+om\s+f[oø]lgende\s*:?",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Norden legal source catalog from metadata JSON.")
    parser.add_argument(
        "--metadata-json",
        default="backend/tools/output/norden_metadata_from_attached_folder.json",
        help="Input metadata JSON path.",
    )
    parser.add_argument(
        "--output-json",
        default="backend/tools/output/norden_catalog.json",
        help="Output catalog JSON path.",
    )
    parser.add_argument(
        "--output-previews-json",
        default="backend/tools/output/norden_previews.json",
        help="Output precomputed preview JSON path.",
    )
    parser.add_argument(
        "--pdf-root-dir",
        default="Dokumenter/DBO/Norden",
        help="Folder containing Norden PDF files.",
    )
    return parser.parse_args()


def version_label(source_id: str) -> str:
    match = VERSION_PATTERN.search(source_id)
    if match:
        return f"Version {match.group(1)}"
    return "Version ukendt"


def section_sort_key(section: dict[str, Any]) -> tuple[int, int, str]:
    section_type = str(section.get("section_type", "")).strip().lower()
    if section_type == "article":
        try:
            return (0, int(str(section.get("section_number", "0") or "0")), "")
        except ValueError:
            return (0, 9999, str(section.get("section_label", "")))
    if section_type == "protocol":
        return (1, 0, str(section.get("section_label", "")))
    return (2, 0, str(section.get("section_label", "")))


def normalize_line(line: str) -> str:
    return re.sub(r"\s+", " ", str(line or "").strip())


def clean_preview_page(text: str) -> str:
    lines = [normalize_line(line) for line in str(text or "").splitlines()]
    kept: list[str] = []
    for line in lines:
        if not line:
            kept.append("")
            continue
        if KARNOV_LINE_PATTERN.search(line):
            continue
        kept.append(line)
    page_text = "\n".join(kept).strip()
    page_text = re.sub(r"\n{3,}", "\n\n", page_text)
    marker_match = PREVIEW_START_MARKER_PATTERN.search(page_text)
    if marker_match:
        page_text = page_text[marker_match.end() :].strip()
    return page_text.strip()


def extract_pdf_pages(file_path: Path) -> list[str]:
    try:
        reader = PdfReader(str(file_path))
        pages: list[str] = []
        for page in reader.pages:
            cleaned = clean_preview_page(page.extract_text() or "")
            if cleaned:
                pages.append(cleaned)
        return pages
    except Exception:
        return []


def find_pdf_for_row(row: dict[str, Any], pdf_files: list[Path]) -> Path | None:
    section_type = str(row.get("section_type", "")).strip().lower()
    section_number = str(row.get("section_number", "")).strip().lower()
    section_label = str(row.get("section_label", "")).strip().lower()
    title_hint = str(row.get("section_title", "")).strip().lower()
    for file_path in pdf_files:
        name = file_path.name.lower()
        if section_type == "article" and section_number:
            if f"artikel {section_number}" in name:
                return file_path
        if section_type == "protocol":
            if "protokol" in name:
                return file_path
        if section_label and section_label in name:
            return file_path
        if title_hint and f"({title_hint})" in name:
            return file_path
    return None


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    metadata_path = (repo_root / args.metadata_json).resolve()
    output_path = (repo_root / args.output_json).resolve()
    output_previews_path = (repo_root / args.output_previews_json).resolve()
    pdf_root_dir = (repo_root / args.pdf_root_dir).resolve()
    if not metadata_path.exists():
        print(f"[ERROR] Metadata file not found: {metadata_path}")
        return 1

    rows = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        print("[ERROR] Metadata JSON is empty or invalid.")
        return 1

    first = rows[0]
    instrument_id = str(first.get("instrument_id", "norden_dbo")).strip() or "norden_dbo"
    title = str(first.get("title", "Nordisk DBO")).strip() or "Nordisk DBO"

    sections = sorted(rows, key=section_sort_key)
    pdf_files = sorted([p for p in pdf_root_dir.glob("*.pdf") if p.is_file()])
    version_id = f"{instrument_id}_v1996"
    sections_payload = []
    preview_entries: dict[str, dict[str, Any]] = {}
    for row in sections:
        source_id = str(row.get("source_id", "")).strip()
        section_label = str(row.get("section_label", "")).strip()
        section_title = str(row.get("section_title", "")).strip()
        label_text = section_title if section_title else section_label
        if section_label and section_title:
            label_text = f"{section_label} - {section_title}"
        elif section_label:
            label_text = section_label
        else:
            label_text = source_id

        sections_payload.append(
            {
                "id": source_id,
                "title": label_text,
                "text": section_title or section_label or source_id,
                "sourceId": source_id,
            }
        )
        pdf_path = find_pdf_for_row(row, pdf_files)
        if pdf_path and pdf_path.exists():
            pages = extract_pdf_pages(pdf_path)
        else:
            pages = []
        preview_entries[source_id.lower()] = {
            "title": label_text,
            "pages": pages,
        }

    catalog = {
        "categories": [
            {"id": "dobbeltbeskatningsoverenskomster", "title": "Dobbeltbeskatningsoverenskomster"},
        ],
        "documents": [
            {
                "id": instrument_id,
                "category": "dobbeltbeskatningsoverenskomster",
                "title": title,
                "tags": ["dbo", "norden"],
                "versions": [
                    {
                        "id": version_id,
                        "label": version_label(str(sections[0].get("source_id", ""))),
                        "validFrom": "1996-09-23",
                        "validTo": "",
                        "sections": sections_payload,
                    }
                ],
            }
        ],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    output_previews_path.parent.mkdir(parents=True, exist_ok=True)
    output_previews_path.write_text(
        json.dumps({"entries": preview_entries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[OK] Catalog written: {output_path}")
    print(f"[OK] Previews written: {output_previews_path}")
    print(f"[OK] Sections: {len(sections_payload)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
