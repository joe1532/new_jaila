#!/usr/bin/env python3
"""Generate backend metadata for Nordic DBO PDF files.

This script reads PDF files from an input folder and outputs metadata in JSON/CSV.
It does not upload anything. Purpose is local validation before server import.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ARTICLE_PATTERN = re.compile(r"artikel\s*(\d+)", re.IGNORECASE)
PROTOCOL_PATTERN = re.compile(r"protokol", re.IGNORECASE)


def compute_sha256(file_path: Path) -> str:
    """Return SHA256 hex digest for a file."""
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_source_id(file_name: str, version_tag: str) -> tuple[str, str]:
    """Build source_id and article_or_section from filename."""
    article_match = ARTICLE_PATTERN.search(file_name)
    if article_match:
        article_number = int(article_match.group(1))
        return f"norden_dbo_art{article_number:02d}_{version_tag}", f"artikel {article_number}"
    if PROTOCOL_PATTERN.search(file_name):
        return f"norden_dbo_protokol_{version_tag}", "protokol"
    sanitized = re.sub(r"[^a-z0-9]+", "_", file_name.lower()).strip("_")
    return f"norden_dbo_{sanitized}_{version_tag}", ""


def build_metadata_for_file(
    file_path: Path,
    *,
    title: str,
    document_type: str,
    jurisdiction: str,
    version_tag: str,
    status: str,
) -> dict[str, Any]:
    """Create metadata dictionary for one PDF file."""
    source_id, article_or_section = build_source_id(file_path.stem, version_tag)
    canonical_path = f"/documents/dbo/norden/{source_id}/source.pdf"
    return {
        "source_id": source_id,
        "title": title,
        "document_type": document_type,
        "jurisdiction": jurisdiction,
        "canonical_path": canonical_path,
        "sha256": compute_sha256(file_path),
        "status": status,
        "article_or_section": article_or_section,
        "filename_original": file_path.name,
    }


def write_json(output_path: Path, rows: list[dict[str, Any]]) -> None:
    """Write metadata as UTF-8 JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(output_path: Path, rows: list[dict[str, Any]]) -> None:
    """Write metadata as UTF-8 CSV."""
    if not rows:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Generate metadata for Nordic DBO PDF files.")
    parser.add_argument(
        "--input-dir",
        default="Dokumenter/DBO/Norden",
        help="Folder with PDF files (default: Dokumenter/DBO/Norden).",
    )
    parser.add_argument(
        "--output-json",
        default="backend/tools/output/norden_metadata.json",
        help="JSON output path (default: backend/tools/output/norden_metadata.json).",
    )
    parser.add_argument(
        "--output-csv",
        default="backend/tools/output/norden_metadata.csv",
        help="CSV output path (default: backend/tools/output/norden_metadata.csv).",
    )
    parser.add_argument(
        "--title",
        default="DBO mellem de nordiske lande",
        help="Metadata title.",
    )
    parser.add_argument(
        "--document-type",
        default="Dobbeltbeskatningsoverenskomst",
        help="Metadata document_type.",
    )
    parser.add_argument(
        "--jurisdiction",
        default="norden",
        help="Metadata jurisdiction.",
    )
    parser.add_argument(
        "--version-tag",
        default="v1996",
        help="Version suffix used in source_id (default: v1996).",
    )
    parser.add_argument(
        "--status",
        default="active",
        choices=["active", "deprecated"],
        help="Metadata status.",
    )
    return parser.parse_args()


def main() -> int:
    """Script entry point."""
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    input_dir = (repo_root / args.input_dir).resolve()
    output_json = (repo_root / args.output_json).resolve()
    output_csv = (repo_root / args.output_csv).resolve()

    if not input_dir.exists():
        print(f"[ERROR] Input folder does not exist: {input_dir}")
        return 1
    if not input_dir.is_dir():
        print(f"[ERROR] Input path is not a folder: {input_dir}")
        return 1

    pdf_files = sorted(input_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"[ERROR] No PDF files found in: {input_dir}")
        return 1

    rows = [
        build_metadata_for_file(
            file_path,
            title=args.title,
            document_type=args.document_type,
            jurisdiction=args.jurisdiction,
            version_tag=args.version_tag,
            status=args.status,
        )
        for file_path in pdf_files
    ]

    duplicate_source_ids = {}
    for row in rows:
        source_id = row["source_id"]
        duplicate_source_ids[source_id] = duplicate_source_ids.get(source_id, 0) + 1
    duplicates = [key for key, count in duplicate_source_ids.items() if count > 1]
    if duplicates:
        print("[ERROR] Duplicate source_id values generated:")
        for source_id in duplicates:
            print(f"  - {source_id}")
        print("Tip: adjust filenames or version tag before using this metadata.")
        return 1

    write_json(output_json, rows)
    write_csv(output_csv, rows)

    print(f"[OK] Processed {len(rows)} files")
    print(f"[OK] JSON: {output_json}")
    print(f"[OK] CSV:  {output_csv}")
    print("[Preview] First 3 source_id values:")
    for row in rows[:3]:
        print(f"  - {row['source_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

