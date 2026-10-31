"""Pydantic schemas for Claim + ClaimCheck."""
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class ClaimAssertionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    assertion_type: str
    subject: str
    value: float | None
    unit: str | None
    qualifier: str | None
    raw_text: str
    source_ts_start: float
    source_ts_end: float

class TranscriptClaimResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    transcript_id: str
    case_id: str
    media_id: str | None
    speaker: str
    raw_text: str
    assertions: list[ClaimAssertionOut] = Field(default_factory=list)
    extraction_confidence: float
    source_ts_start: float
    source_ts_end: float
    created_at: datetime
    created_by: str

class TranscriptClaimUpdate(BaseModel):
    raw_text: str | None = Field(None, min_length=1)
    speaker: str | None = Field(None, min_length=1)

class ClaimCheckResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    claim_id: str
    case_id: str
    verdict: str
    confidence: float
    evidence_frame_start: int | None
    evidence_frame_end: int | None
    evidence_json: str | None
    explanation: str
    homography_fit_id: str | None
    checked_at: datetime
    checked_by: str

