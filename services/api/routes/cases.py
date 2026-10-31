"""Cases CRUD router — full Phase 1 implementation."""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.db.models import Case, CaseStatus, DerivedArtifact, SourceMedia
from services.api.db.session import get_db
from services.api.schemas.case import CaseCreate, CaseResponse, CaseUpdate

router = APIRouter(prefix="/cases", tags=["cases"])

SYSTEM_OWNER = "demo-user"  # Phase 1: no auth yet


@router.post("/", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
async def create_case(
    payload: CaseCreate,
    db: AsyncSession = Depends(get_db),
) -> CaseResponse:
    case = Case(
        id=str(uuid.uuid4()),
        title=payload.title,
        description=payload.description,
        jurisdiction=payload.jurisdiction,
        incident_date=payload.incident_date,
        incident_location=payload.incident_location,
        consent_given=payload.consent_given,
        status=CaseStatus.DRAFT,
        owner_id=SYSTEM_OWNER,
    )
    db.add(case)
    await db.commit()
    await db.refresh(case)

    result = CaseResponse.model_validate(case)
    result.media_count = 0
    return result


@router.get("/", response_model=list[CaseResponse])
async def list_cases(db: AsyncSession = Depends(get_db)) -> list[CaseResponse]:
    result = await db.execute(select(Case).order_by(Case.created_at.desc()))
    cases = result.scalars().all()

    responses = []
    for case in cases:
        mc_result = await db.execute(select(func.count()).where(SourceMedia.case_id == case.id))
        media_count = mc_result.scalar() or 0
        r = CaseResponse.model_validate(case)
        r.media_count = media_count
        responses.append(r)
    return responses


@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(case_id: str, db: AsyncSession = Depends(get_db)) -> CaseResponse:
    result = await db.execute(select(Case).where(Case.id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    mc_result = await db.execute(select(func.count()).where(SourceMedia.case_id == case_id))
    media_count = mc_result.scalar() or 0
    r = CaseResponse.model_validate(case)
    r.media_count = media_count
    return r


@router.patch("/{case_id}", response_model=CaseResponse)
async def update_case(
    case_id: str,
    payload: CaseUpdate,
    db: AsyncSession = Depends(get_db),
) -> CaseResponse:
    result = await db.execute(select(Case).where(Case.id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(case, field, value)

    await db.commit()
    await db.refresh(case)
    r = CaseResponse.model_validate(case)
    r.media_count = 0
    return r


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_case(case_id: str, db: AsyncSession = Depends(get_db)) -> None:
    result = await db.execute(select(Case).where(Case.id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    media_result = await db.execute(select(SourceMedia).where(SourceMedia.case_id == case_id))
    media_rows = media_result.scalars().all()
    paths = [Path(media.storage_path) for media in media_rows]
    for media in media_rows:
        artifacts_result = await db.execute(
            select(DerivedArtifact).where(DerivedArtifact.source_media_id == media.id)
        )
        paths.extend(Path(artifact.storage_path) for artifact in artifacts_result.scalars().all())
    await db.delete(case)
    await db.commit()
    for path in paths:
        path.unlink(missing_ok=True)
