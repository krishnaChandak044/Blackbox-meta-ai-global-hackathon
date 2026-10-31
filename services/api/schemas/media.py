"""Pydantic schemas for Source Media."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from services.api.db.models import MediaStatus


class SourceMediaResponse(BaseModel):
    id: str
    case_id: str
    original_filename: str
    mime_type: str
    byte_length: int
    sha256: str
    status: MediaStatus
    upload_time: datetime

    # Probe results
    codec: Optional[str]
    container: Optional[str]
    duration_seconds: Optional[float]
    frame_count: Optional[int]
    fps_nominal: Optional[float]
    is_variable_framerate: Optional[bool]
    width: Optional[int]
    height: Optional[int]
    has_audio: Optional[bool]

    class Config:
        from_attributes = True


class IntegrityCheckResponse(BaseModel):
    media_id: str
    original_sha256: str
    verified_sha256: str
    intact: bool
    checked_at: datetime
