"""Canonical JSON evidence export helpers."""
from __future__ import annotations

import hashlib
from enum import Enum
from typing import Any


def json_default(value: Any) -> Any:
    from services.api.db.revision import _default
    try:
        return _default(value)
    except TypeError:
        pass
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"Unsupported JSON value: {type(value).__name__}")


def canonical_json(value: Any) -> bytes:
    from services.api.db.revision import canonical_json as encode
    return encode(value)


def seal_manifest(manifest: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Add a deterministic manifest digest computed without the digest field."""
    payload = dict(manifest)
    payload.pop("manifest_sha256", None)
    digest = hashlib.sha256(canonical_json(payload)).hexdigest()
    payload["manifest_sha256"] = digest
    return payload, digest
