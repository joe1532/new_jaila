"""Årsinterval og YearExpectations fra årsmanifest + JSONL."""

from __future__ import annotations

from pathlib import Path

from backend.db.skat_import.constants import YearExpectations
from backend.db.skat_import.io import chunks_path, iter_jsonl, year_dir
from backend.db.skat_import.preflight import load_json

APPROVED_PILOT_YEAR = 2026


def descending_years(start_year: int, end_year: int, *, skip: set[int] | None = None) -> list[int]:
    """Inklusivt interval. 2025→2001 bliver [2025, 2024, …, 2001]."""
    skip = skip or set()
    step = -1 if start_year >= end_year else 1
    return [year for year in range(start_year, end_year + step, step) if year not in skip]


def expectations_from_year_files(input_root: Path, year: int) -> YearExpectations:
    """Dokument/chunk/ref fra manifest. Klassifikation og spans tælles i JSONL."""
    manifest = load_json(year_dir(input_root, year) / "manifest.json")
    if int(manifest["year"]) != year:
        raise ValueError(f"{year}: manifest.year={manifest.get('year')}")
    summary = 0
    reasoning = 0
    result = 0
    final = 0
    spans = 0
    for record in iter_jsonl(chunks_path(input_root, year)):
        if record.get("section_type") == "summary":
            summary += 1
        weight = record.get("legal_weight")
        if weight == "authoritative_reasoning":
            reasoning += 1
        elif weight == "authoritative_result":
            result += 1
        if record.get("is_final_result"):
            final += 1
        spans += len(record.get("source_spans") or [])
    if "summary_chunk_count" in manifest and int(manifest["summary_chunk_count"]) != summary:
        raise ValueError(
            f"{year}: summary-chunks JSONL={summary}, manifest={manifest['summary_chunk_count']}"
        )
    if (
        "authoritative_reasoning_chunk_count" in manifest
        and int(manifest["authoritative_reasoning_chunk_count"]) != reasoning
    ):
        raise ValueError(f"{year}: authoritative_reasoning JSONL afviger fra manifest")
    if (
        "authoritative_result_chunk_count" in manifest
        and int(manifest["authoritative_result_chunk_count"]) != result
    ):
        raise ValueError(f"{year}: authoritative_result JSONL afviger fra manifest")
    return YearExpectations(
        year=year,
        document_count=int(manifest["document_count"]),
        chunk_count=int(manifest["chunk_count"]),
        reference_count=int(manifest["reference_count"]),
        summary_chunk_count=summary,
        authoritative_reasoning_count=reasoning,
        authoritative_result_count=result,
        final_result_count=final,
        token_max=1000,
        span_count=spans,
    )
