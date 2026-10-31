"""
engine/claims/models.py
───────────────────────
Pure dataclasses for Phase 3 Language & Claims.

Framework-free: no FastAPI / SQLAlchemy / Celery imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass(frozen=True, slots=True)
class ClaimAssertion:
    assertion_type: Literal["speed", "direction", "timing", "position", "action", "stop"]
    subject: str
    value: float | None
    unit: str | None
    qualifier: str | None
    raw_text: str
    source_ts_start: float
    source_ts_end: float


@dataclass(frozen=True, slots=True)
class Claim:
    id: str
    case_id: str
    media_id: str | None
    transcript_id: str
    speaker: str
    assertions: list[ClaimAssertion]
    raw_text: str
    confidence: float


@dataclass(frozen=True, slots=True)
class ClaimVerdict:
    claim_id: str
    verdict: Literal["supported", "contradicted", "inconclusive", "insufficient_data"]
    confidence: float
    evidence_frame_start: int | None
    evidence_frame_end: int | None
    evidence_world_positions: list[tuple[float, float]] | None
    explanation: str
    checked_at: datetime


# ── Lightweight helpers used by checker (not persisted) ──────────────────────


@dataclass(frozen=True, slots=True)
class TrackPointLite:
    """Minimal track point for checker — intentionally decoupled from DB models."""

    frame_index: int
    presentation_ts_s: float
    world_x: float | None
    world_y: float | None
    bbox_x_min: float = 0.0
    bbox_y_min: float = 0.0
    bbox_x_max: float = 0.0
    bbox_y_max: float = 0.0


@dataclass(frozen=True, slots=True)
class TrackDetailLite:
    """Minimal track container for checker."""

    id: str
    points: list[TrackPointLite] = field(default_factory=list)
