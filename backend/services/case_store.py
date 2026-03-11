"""
Persistent sager per bruger.

Designet som et simpelt store-interface, så backend kan skiftes fra JSON til fx
SQLite/PostgreSQL senere uden at ændre API-kontrakten.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.config import ANALYSE_LOGS_DIR


def _sanitize_username(username: str) -> str:
    """Kun alfanumerisk og bindestreg."""
    return re.sub(r"[^\w\-]", "", (username or "").strip().lower()) or "default"


def _deep_merge(target: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    for key, value in patch.items():
        if (
            isinstance(value, dict)
            and isinstance(target.get(key), dict)
        ):
            target[key] = _deep_merge(dict(target.get(key) or {}), value)
        else:
            target[key] = value
    return target


class CaseStore:
    def create_case(self, username: str, title: str | None = None) -> dict[str, Any]:
        raise NotImplementedError

    def list_cases(self, username: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def get_case(self, username: str, case_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def update_case(self, username: str, case_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        raise NotImplementedError

    def delete_case(self, username: str, case_id: str) -> bool:
        raise NotImplementedError


class JsonCaseStore(CaseStore):
    def __init__(self, base_dir: Path):
        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _user_path(self, username: str) -> Path:
        return self._base_dir / f"{_sanitize_username(username)}_cases.json"

    def _load(self, username: str) -> list[dict[str, Any]]:
        path = self._user_path(username)
        if not path.exists():
            return []
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, OSError):
            return []
        return []

    def _save(self, username: str, entries: list[dict[str, Any]]) -> None:
        path = self._user_path(username)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)

    def _default_case(self, title: str | None = None) -> dict[str, Any]:
        now = datetime.now().isoformat(timespec="seconds")
        return {
            "id": uuid4().hex[:12],
            "schema_version": 1,
            "title": (title or "").strip() or "Ny sag",
            "status": "open",
            "created_at": now,
            "updated_at": now,
            "active_subtab": "skattepligt_ligningsfrist",
            "shared_facts": {},
            "subtab_outputs": {},
            "locked_by_subtab": {},
            "facts_by_subtab": {},
            "context_by_subtab": {},
            "messages_by_subtab": {},
            "previous_response_id_by_subtab": {},
            "used_model_by_subtab": {},
        }

    def create_case(self, username: str, title: str | None = None) -> dict[str, Any]:
        entries = self._load(username)
        entry = self._default_case(title)
        entries.insert(0, entry)
        self._save(username, entries)
        return entry

    def list_cases(self, username: str) -> list[dict[str, Any]]:
        entries = self._load(username)
        return [
            {
                "id": entry.get("id", ""),
                "title": entry.get("title", "Ny sag"),
                "status": entry.get("status", "open"),
                "created_at": entry.get("created_at", ""),
                "updated_at": entry.get("updated_at", entry.get("created_at", "")),
            }
            for entry in entries
            if entry.get("id")
        ]

    def get_case(self, username: str, case_id: str) -> dict[str, Any] | None:
        entries = self._load(username)
        for entry in entries:
            if entry.get("id") == case_id:
                return entry
        return None

    def update_case(self, username: str, case_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        entries = self._load(username)
        for idx, entry in enumerate(entries):
            if entry.get("id") != case_id:
                continue
            now = datetime.now().isoformat(timespec="seconds")
            merged = _deep_merge(dict(entry), dict(patch or {}))
            merged["id"] = entry.get("id")
            merged["created_at"] = entry.get("created_at", now)
            merged["updated_at"] = now
            merged["schema_version"] = entry.get("schema_version", 1)
            entries.pop(idx)
            entries.insert(0, merged)
            self._save(username, entries)
            return merged
        return None

    def delete_case(self, username: str, case_id: str) -> bool:
        entries = self._load(username)
        remaining = [entry for entry in entries if entry.get("id") != case_id]
        if len(remaining) == len(entries):
            return False
        self._save(username, remaining)
        return True


_case_store_instance: CaseStore | None = None


def get_case_store() -> CaseStore:
    global _case_store_instance
    if _case_store_instance is None:
        _case_store_instance = JsonCaseStore(ANALYSE_LOGS_DIR)
    return _case_store_instance
