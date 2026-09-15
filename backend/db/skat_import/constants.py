"""Faste korpusforventninger. Ændres kun ved nyt valideret korpus."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid5, NAMESPACE_URL

CORPUS = "skat_info_skm"
SCHEMA_VERSION_DOCUMENT = "jaila.skat.document.v1"
SCHEMA_VERSION_CHUNK = "jaila.skat.chunk.v1"
CHUNKER_VERSION = "1.0.1"

EXPECTED_SOURCE_MANIFEST_SHA256 = (
    "e87faff39b20a238bcdf28707e9713a58c77f4d9a7824f5db752f81f225d0329"
)
EXPECTED_CHUNK_CONFIG_SHA256 = (
    "853d300cbb5017e5233419f0c60544509fd7030f2df387b508a96b9ebd2e07b9"
)

EXPECTED_STATUS = "complete"
EXPECTED_YEAR_COUNT = 26
EXPECTED_DOCUMENT_COUNT = 11707
EXPECTED_CHUNK_COUNT = 295697
EXPECTED_REFERENCE_COUNT = 280548

EXPECTED_SUMMARY_CHUNK_COUNT = 12485
EXPECTED_AUTHORITATIVE_REASONING_COUNT = 38634
EXPECTED_AUTHORITATIVE_RESULT_COUNT = 11887
EXPECTED_FINAL_RESULT_COUNT = 20018
EXPECTED_PUBLICATION_YEAR_INFERRED = 1259
EXPECTED_YEARS_WITH_CHUNKS = 26

DEFAULT_BATCH_SIZE = 1000

# UUIDv5-namespace for reference_id. Fast, dokumenteret identitet.
# uuid5(NAMESPACE_URL, "https://jaila.local/skat/reference/v1")
REFERENCE_ID_NAMESPACE: UUID = uuid5(
    NAMESPACE_URL, "https://jaila.local/skat/reference/v1"
)


@dataclass(frozen=True)
class CorpusExpectations:
    status: str = EXPECTED_STATUS
    year_count: int = EXPECTED_YEAR_COUNT
    document_count: int = EXPECTED_DOCUMENT_COUNT
    chunk_count: int = EXPECTED_CHUNK_COUNT
    reference_count: int = EXPECTED_REFERENCE_COUNT
    source_manifest_sha256: str = EXPECTED_SOURCE_MANIFEST_SHA256
    chunk_config_sha256: str = EXPECTED_CHUNK_CONFIG_SHA256
    chunker_version: str = CHUNKER_VERSION


@dataclass(frozen=True)
class YearExpectations:
    year: int
    document_count: int
    chunk_count: int
    reference_count: int
    summary_chunk_count: int
    authoritative_reasoning_count: int
    authoritative_result_count: int
    final_result_count: int
    token_max: int = 1000
    span_count: int | None = None


YEAR_2026 = YearExpectations(
    year=2026,
    document_count=284,
    chunk_count=14167,
    reference_count=12722,
    summary_chunk_count=345,
    authoritative_reasoning_count=1972,
    authoritative_result_count=416,
    final_result_count=884,
    token_max=1000,
    span_count=96881,
)


@dataclass(frozen=True)
class SmokeSpec:
    skm_number: str
    summary_min_length: int
    older_citation: str
    manual_skm_number: str


SMOKE_2026 = SmokeSpec(
    skm_number="SKM2026.46.BR",
    summary_min_length=1000,
    older_citation="SKM2022.129.ØLR",
    manual_skm_number="SKM2026.5.SR",
)

PRODUCTION_EXPECTATIONS = CorpusExpectations()
