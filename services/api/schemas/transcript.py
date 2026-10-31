"""Pydantic schemas for Transcript."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TranscriptCreate(BaseModel):
    raw_text: str = Field(..., min_length=1)
    language: str = Field(default="en", max_length=10)
    media_id: str | None = None
    speaker_count: int = Field(default=1, ge=1)
    diarised_json: str | None = None
    duration_seconds: float | None = Field(None, ge=0)
    transcription_model: str = Field(default="manual")


class TranscriptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str
    media_id: str | None
    speaker_count: int
    language: str
    raw_text: str
    diarised_json: str | None
    transcription_model: str
    word_count: int
    duration_seconds: float | None
    created_at: datetime
    created_by: str


class TranscriptUpdate(BaseModel):
    raw_text: str | None = Field(None, min_length=1)
    language: str | None = None
    speaker_count: int | None = Field(None, ge=1)
