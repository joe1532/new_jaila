"""Fase 1: preflight. Ingen databaseændringer."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from backend.db.skat_import.constants import CorpusExpectations, PRODUCTION_EXPECTATIONS
from backend.db.skat_import.errors import PreflightError
from backend.db.skat_import.io import (
    chunks_path,
    documents_path,
    hash_and_count_file,
    references_path,
    year_dir,
)


@dataclass
class YearFileCheck:
    year: int
    document_count: int
    chunk_count: int
    reference_count: int
    documents_sha256: str
    chunks_sha256: str
    references_sha256: str


@dataclass
class PreflightResult:
    corpus_status: dict
    years: list[int]
    year_checks: list[YearFileCheck]
    expected: CorpusExpectations
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run_preflight(
    input_root: Path,
    expected: CorpusExpectations = PRODUCTION_EXPECTATIONS,
    *,
    hash_files: bool = True,
) -> PreflightResult:
    errors: list[str] = []
    status_path = input_root / "corpus_status.json"
    if not status_path.is_file():
        raise PreflightError(f"mangler {status_path}")
    corpus_status = load_json(status_path)

    if corpus_status.get("status") != expected.status:
        errors.append(
            f"corpus_status.status={corpus_status.get('status')!r}, forventet {expected.status!r}"
        )
    completed = list(corpus_status.get("completed_years") or [])
    if len(completed) != expected.year_count:
        errors.append(
            f"completed_years={len(completed)}, forventet {expected.year_count}"
        )
    totals = corpus_status.get("totals") or {}
    for key, exp in (
        ("document_count", expected.document_count),
        ("chunk_count", expected.chunk_count),
        ("reference_count", expected.reference_count),
    ):
        actual = totals.get(key)
        if actual != exp:
            errors.append(f"totals.{key}={actual}, forventet {exp}")

    if corpus_status.get("source_manifest_sha256") != expected.source_manifest_sha256:
        errors.append("source_manifest_sha256 matcher ikke det forventede korpus")
    if corpus_status.get("chunk_config_sha256") != expected.chunk_config_sha256:
        errors.append("chunk_config_sha256 matcher ikke det forventede korpus")

    years = sorted(int(y) for y in completed)
    year_checks: list[YearFileCheck] = []
    for year in years:
        year_checks.append(
            _check_year(input_root, year, expected, errors, hash_files=hash_files)
        )

    result = PreflightResult(
        corpus_status=corpus_status,
        years=years,
        year_checks=year_checks,
        expected=expected,
        errors=errors,
    )
    if errors:
        raise PreflightError("preflight fejlede:\n- " + "\n- ".join(errors))
    return result


def _check_year(
    input_root: Path,
    year: int,
    expected: CorpusExpectations,
    errors: list[str],
    *,
    hash_files: bool,
) -> YearFileCheck:
    folder = year_dir(input_root, year)
    manifest_path = folder / "manifest.json"
    report_path = folder / "validation_report.json"
    docs = documents_path(input_root, year)
    chunks = chunks_path(input_root, year)
    refs = references_path(input_root, year)
    empty = YearFileCheck(year, 0, 0, 0, "", "", "")

    missing = [p for p in (manifest_path, report_path, docs, chunks, refs) if not p.is_file()]
    if missing:
        errors.append(f"{year}: mangler {', '.join(str(p) for p in missing)}")
        return empty

    manifest = load_json(manifest_path)
    report = load_json(report_path)
    if report.get("status") != "pass":
        errors.append(f"{year}: validation_report.status={report.get('status')!r}")
    if report.get("error_count") != 0:
        errors.append(f"{year}: validation_report.error_count={report.get('error_count')}")
    if manifest.get("chunker_version") != expected.chunker_version:
        errors.append(
            f"{year}: chunker_version={manifest.get('chunker_version')!r}"
        )
    if manifest.get("source_manifest_sha256") != expected.source_manifest_sha256:
        errors.append(f"{year}: manifest source_manifest_sha256 afviger")
    if manifest.get("chunk_config_sha256") != expected.chunk_config_sha256:
        errors.append(f"{year}: manifest chunk_config_sha256 afviger")

    jsonl_meta = manifest.get("jsonl") or {}
    checks = [
        ("documents", docs, jsonl_meta.get("documents") or {}),
        ("chunks", chunks, jsonl_meta.get("chunks") or {}),
        ("references", refs, jsonl_meta.get("references") or {}),
    ]
    hashes = {"documents": "", "chunks": "", "references": ""}
    counts = {"documents": 0, "chunks": 0, "references": 0}
    if hash_files:
        for name, path, meta in checks:
            digest, records, size = hash_and_count_file(path)
            hashes[name] = digest
            counts[name] = records
            if meta.get("sha256") and digest != meta["sha256"]:
                errors.append(f"{year}: {name} SHA-256 matcher ikke manifestet")
            if meta.get("count") is not None and records != meta["count"]:
                errors.append(
                    f"{year}: {name} linjeantal={records}, manifest={meta.get('count')}"
                )
            if meta.get("bytes") is not None and size != meta["bytes"]:
                errors.append(
                    f"{year}: {name} bytes={size}, manifest={meta.get('bytes')}"
                )
    else:
        counts["documents"] = int((jsonl_meta.get("documents") or {}).get("count") or 0)
        counts["chunks"] = int((jsonl_meta.get("chunks") or {}).get("count") or 0)
        counts["references"] = int((jsonl_meta.get("references") or {}).get("count") or 0)

    return YearFileCheck(
        year=year,
        document_count=counts["documents"],
        chunk_count=counts["chunks"],
        reference_count=counts["references"],
        documents_sha256=hashes["documents"],
        chunks_sha256=hashes["chunks"],
        references_sha256=hashes["references"],
    )
