"""Pydantic schemas for Cases."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from services.api.db.models import CaseStatus


class CaseCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=255)
    description: Optional[str] = None
    jurisdiction: Optional[str] = None
    incident_date: Optional[datetime] = None
    incident_location: Optional[str] = None
    consent_given: bool = False


class CaseUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=255)
    description: Optional[str] = None
    jurisdiction: Optional[str] = None
    incident_date: Optional[datetime] = None
    incident_location: Optional[str] = None
    consent_given: Optional[bool] = None


class CaseResponse(BaseModel):
    id: str
    title: str
    description: Optional[str]
    jurisdiction: Optional[str]
    incident_date: Optional[datetime]
    incident_location: Optional[str]
    status: CaseStatus
    consent_given: bool
    owner_id: str
    created_at: datetime
    updated_at: datetime
    media_count: int = 0

    class Config:
        from_attributes = True
