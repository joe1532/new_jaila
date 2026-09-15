"""JSONL-streaming, filhash og kanonisk JSON. Indlæser ikke hele korpusset."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterator
from uuid import UUID, uuid5

from backend.db.skat_import.constants import REFERENCE_ID_NAMESPACE


def canonical_json_bytes(obj: object) -> bytes:
    """UTF-8 JSON med sorterede nøgler, uden ASCII-escaping, faste separatorer."""
    return json.dumps(
        obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_reference_sha256(record: dict) -> str:
    return sha256_hex(canonical_json_bytes(record))


def occurrence_reference_key(canonical_sha: str, occurrence_index: int) -> str:
    return sha256_hex(f"{canonical_sha}:{occurrence_index}".encode("utf-8"))


class ReferenceOccurrenceAssigner:
    """Giver deterministisk occurrence_index i stabil JSONL-rækkefølge."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    def assign(self, record: dict) -> tuple[str, int, str]:
        canonical = canonical_reference_sha256(record)
        index = self._counts.get(canonical, 0)
        self._counts[canonical] = index + 1
        key = occurrence_reference_key(canonical, index)
        return canonical, index, key


def reference_id(key: str) -> UUID:
    return uuid5(REFERENCE_ID_NAMESPACE, key)


def hash_and_count_file(path: Path) -> tuple[str, int, int]:
    """SHA-256 af rå filbytes, antal ikke-tomme linjer, størrelse i bytes."""
    digest = hashlib.sha256()
    records = 0
    size = 0
    with path.open("rb") as handle:
        for line in handle:
            digest.update(line)
            size += len(line)
            if line.strip():
                records += 1
    return digest.hexdigest(), records, size


def iter_jsonl(path: Path) -> Iterator[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"ugyldig JSON i {path} linje {line_no}: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"forventede objekt i {path} linje {line_no}")
            yield record


def jsonb(value: object):
    from psycopg.types.json import Jsonb

    return Jsonb(value)


def redact_dsn(url: str) -> str:
    if "://" not in url or "@" not in url:
        return url
    scheme, rest = url.split("://", 1)
    creds, _, host = rest.partition("@")
    if ":" not in creds:
        return url
    user, _, _password = creds.partition(":")
    return f"{scheme}://{user}:***@{host}"


def year_dir(input_root: Path, year: int) -> Path:
    return input_root / str(year)


def documents_path(input_root: Path, year: int) -> Path:
    return year_dir(input_root, year) / "documents" / f"{year}.jsonl"


def chunks_path(input_root: Path, year: int) -> Path:
    return year_dir(input_root, year) / "chunks" / f"{year}.jsonl"


def references_path(input_root: Path, year: int) -> Path:
    return year_dir(input_root, year) / "references" / f"{year}.jsonl"
