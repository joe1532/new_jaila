#!/usr/bin/env python3
"""Generate v2 metadata for DBO PDF files.

This script scans PDF files recursively under a DBO folder and outputs JSON/CSV
metadata for review. It does not upload anything.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from pypdf import PdfReader


ARTICLE_PATTERN = re.compile(r"artikel\s*(\d+)", re.IGNORECASE)
PROTOCOL_PATTERN = re.compile(r"protokol", re.IGNORECASE)
DATE8_PATTERN = re.compile(r"(19\d{2}|20\d{2})(\d{2})(\d{2})")
YEAR_PATTERN = re.compile(r"(19\d{2}|20\d{2})")
EXCLUDE_NAME_PATTERN = re.compile(r"chat_log", re.IGNORECASE)

COUNTRY_ALIASES = {
    "danmark": "dk",
    "tyskland": "de",
    "sverige": "se",
    "norge": "no",
    "finland": "fi",
    "faeroeerne": "fo",
    "feroeerne": "fo",
    "island": "is",
    "nordiske lande": "norden",
}
NORDIC_SEARCH_COUNTRIES = ["norge", "sverige", "finland", "island", "færøerne", "grønland"]


def normalize_text(text: str) -> str:
    """Lowercase text and strip diacritics for robust matching."""
    lowered = text.lower()
    normalized = unicodedata.normalize("NFKD", lowered)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def compute_sha256(file_path: Path) -> str:
    """Return SHA256 hex digest for a file."""
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_pdf_text_head(file_path: Path, max_pages: int = 2) -> str:
    """Extract text from first pages of a PDF. Returns empty string on failure."""
    try:
        reader = PdfReader(str(file_path))
        pages = reader.pages[:max_pages]
        return "\n".join((page.extract_text() or "") for page in pages)
    except Exception:
        return ""


def infer_jurisdiction(file_path: Path, head_text: str, default_jurisdiction: str) -> str:
    """Infer jurisdiction using folder name + PDF head text."""
    combined = normalize_text(f"{str(file_path.parent)}\n{head_text}")
    if "norden" in combined or "nordiske lande" in combined:
        return "norden"

    found_codes: set[str] = set()
    for alias, code in COUNTRY_ALIASES.items():
        if alias in combined and code != "norden":
            found_codes.add(code)

    if "dk" in found_codes and len(found_codes) == 2:
        other = sorted(code for code in found_codes if code != "dk")[0]
        return f"dk-{other}"
    if len(found_codes) == 1:
        return sorted(found_codes)[0]
    if len(found_codes) > 1:
        return "-".join(sorted(found_codes))
    return default_jurisdiction


def infer_version_tag(file_name: str, fallback_version_tag: str) -> str:
    """Infer version tag from filename. Falls back to provided version."""
    match_date8 = DATE8_PATTERN.search(file_name)
    if match_date8:
        return f"v{match_date8.group(1)}"
    match_year = YEAR_PATTERN.search(file_name)
    if match_year:
        return f"v{match_year.group(1)}"
    return fallback_version_tag


def slugify(value: str) -> str:
    """Create a filesystem-safe lowercase slug."""
    normalized = normalize_text(value)
    return re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")


def build_source_id(
    *,
    jurisdiction: str,
    file_name_stem: str,
    version_tag: str,
    article_or_section: str,
) -> str:
    """Build source_id based on jurisdiction and filename."""
    if article_or_section.startswith("artikel "):
        article_number = int(article_or_section.split(" ", 1)[1])
        return f"{jurisdiction}_dbo_art{article_number:02d}_{version_tag}"
    if article_or_section == "protokol":
        return f"{jurisdiction}_dbo_protokol_{version_tag}"
    stem_slug = slugify(file_name_stem)
    return f"{jurisdiction}_dbo_{stem_slug}_{version_tag}"


def infer_article_or_section(file_name: str, head_text: str) -> str:
    """Infer article/section from filename first, then PDF head text."""
    for source in (file_name, head_text):
        article_match = ARTICLE_PATTERN.search(source)
        if article_match:
            return f"artikel {int(article_match.group(1))}"
        if PROTOCOL_PATTERN.search(source):
            return "protokol"
    return ""


def infer_article_or_section_from_filename(file_name: str) -> str:
    """Infer article/section strictly from filename for stable source_id."""
    article_match = ARTICLE_PATTERN.search(file_name)
    if article_match:
        return f"artikel {int(article_match.group(1))}"
    if PROTOCOL_PATTERN.search(file_name):
        return "protokol"
    return ""


def build_aliases(jurisdiction: str, article_or_section: str, title: str) -> list[str]:
    """Generate simple search aliases for catalog search."""
    aliases = ["dbo", "dobbeltbeskatningsoverenskomst", title.lower()]
    if jurisdiction == "norden":
        aliases.extend(NORDIC_SEARCH_COUNTRIES)
    if jurisdiction.startswith("dk-"):
        right = jurisdiction.split("-", 1)[1]
        aliases.extend([jurisdiction, f"danmark {right}", f"dbo {right}"])
    if article_or_section:
        aliases.extend([article_or_section, article_or_section.replace("artikel ", "art ")])
    deduped: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        key = normalize_text(alias).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(key)
    return deduped


def build_metadata_for_file(
    file_path: Path,
    *,
    title: str,
    document_type: str,
    default_jurisdiction: str,
    default_version_tag: str,
    status: str,
) -> dict[str, Any]:
    """Create metadata row for one DBO PDF file."""
    head_text = extract_pdf_text_head(file_path)
    article_or_section = infer_article_or_section(file_path.stem, head_text)
    source_id_article_or_section = infer_article_or_section_from_filename(file_path.stem)
    jurisdiction = infer_jurisdiction(file_path, head_text, default_jurisdiction)
    version_tag = infer_version_tag(file_path.stem, default_version_tag)
    source_id = build_source_id(
        jurisdiction=jurisdiction,
        file_name_stem=file_path.stem,
        version_tag=version_tag,
        article_or_section=source_id_article_or_section,
    )
    canonical_path = f"/documents/dbo/{jurisdiction}/{source_id}/source.pdf"
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
        "relative_path": str(file_path).replace("\\", "/"),
        "search_aliases": build_aliases(jurisdiction, article_or_section, title),
    }


def write_json(output_path: Path, rows: list[dict[str, Any]]) -> None:
    """Write rows to UTF-8 JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(output_path: Path, rows: list[dict[str, Any]]) -> None:
    """Write rows to UTF-8 CSV."""
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
    parser = argparse.ArgumentParser(description="Generate v2 metadata for DBO PDFs.")
    parser.add_argument(
        "--input-dir",
        default="Dokumenter/DBO",
        help="Root folder for DBO files (default: Dokumenter/DBO).",
    )
    parser.add_argument(
        "--output-json",
        default="backend/tools/output/dbo_metadata_v2.json",
        help="JSON output path.",
    )
    parser.add_argument(
        "--output-csv",
        default="backend/tools/output/dbo_metadata_v2.csv",
        help="CSV output path.",
    )
    parser.add_argument(
        "--title",
        default="DBO mellem de nordiske lande",
        help="Title metadata value.",
    )
    parser.add_argument(
        "--document-type",
        default="Dobbeltbeskatningsoverenskomst",
        help="Document type metadata value.",
    )
    parser.add_argument(
        "--default-jurisdiction",
        default="ukendt",
        help="Fallback jurisdiction if no inference is possible.",
    )
    parser.add_argument(
        "--version-tag",
        default="v1996",
        help="Fallback version tag in source_id.",
    )
    parser.add_argument(
        "--status",
        default="active",
        choices=["active", "deprecated"],
        help="Status metadata value.",
    )
    parser.add_argument(
        "--fail-on-unknown-jurisdiction",
        action="store_true",
        help="Exit with error if one or more rows have jurisdiction=ukendt.",
    )
    return parser.parse_args()


def main() -> int:
    """Script entry point."""
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    input_dir = (repo_root / args.input_dir).resolve()
    output_json = (repo_root / args.output_json).resolve()
    output_csv = (repo_root / args.output_csv).resolve()

    if not input_dir.exists() or not input_dir.is_dir():
        print(f"[ERROR] Input folder missing or invalid: {input_dir}")
        return 1

    pdf_files = sorted(path for path in input_dir.rglob("*.pdf") if not EXCLUDE_NAME_PATTERN.search(path.name))
    if not pdf_files:
        print(f"[ERROR] No PDF files found in: {input_dir}")
        return 1

    rows = [
        build_metadata_for_file(
            file_path,
            title=args.title,
            document_type=args.document_type,
            default_jurisdiction=args.default_jurisdiction,
            default_version_tag=args.version_tag,
            status=args.status,
        )
        for file_path in pdf_files
    ]

    source_id_counts: dict[str, int] = {}
    for row in rows:
        source_id = str(row["source_id"])
        source_id_counts[source_id] = source_id_counts.get(source_id, 0) + 1
    duplicate_source_ids = [key for key, count in source_id_counts.items() if count > 1]
    if duplicate_source_ids:
        print("[ERROR] Duplicate source_id values generated:")
        for source_id in duplicate_source_ids:
            print(f"  - {source_id}")
        print("Adjust naming, jurisdiction inference, or version tags.")
        return 1

    unknown_rows = [row for row in rows if row["jurisdiction"] == "ukendt"]
    if unknown_rows:
        print(f"[WARN] {len(unknown_rows)} rows have jurisdiction=ukendt")
        for row in unknown_rows[:10]:
            print(f"  - {row['filename_original']}")
        if args.fail_on_unknown_jurisdiction:
            print("[ERROR] --fail-on-unknown-jurisdiction is enabled.")
            return 1

    write_json(output_json, rows)
    write_csv(output_csv, rows)

    print(f"[OK] Processed {len(rows)} files")
    print(f"[OK] JSON: {output_json}")
    print(f"[OK] CSV:  {output_csv}")
    print("[Preview] First 5 source_id values:")
    for row in rows[:5]:
        print(f"  - {row['source_id']} ({row['jurisdiction']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

