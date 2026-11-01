"""Canonical case-content revision hashing shared by API and export worker."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from enum import Enum
from typing import Any


def _default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"Unsupported revision value: {type(value).__name__}")


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, default=_default, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def case_revision_hash(snapshot: dict[str, Any]) -> str:
    """Hash the exact persisted records that feed an export snapshot."""
    return hashlib.sha256(canonical_json(snapshot)).hexdigest()
