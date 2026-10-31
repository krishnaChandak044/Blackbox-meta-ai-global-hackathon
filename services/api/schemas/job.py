"""Pydantic schemas for Processing Jobs."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from services.api.db.models import JobStage, JobStatus


class JobResponse(BaseModel):
    id: str
    case_id: str
    media_id: Optional[str]
    stage: JobStage
    status: JobStatus
    progress: int
    error_message: Optional[str]
    queued_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True
