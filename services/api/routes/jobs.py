"""Jobs status router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.db.session import get_db
from services.api.db.models import ProcessingJob
from services.api.schemas.job import JobResponse

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)) -> JobResponse:
    result = await db.execute(select(ProcessingJob).where(ProcessingJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse.model_validate(job)


@router.get("/case/{case_id}", response_model=list[JobResponse])
async def list_case_jobs(case_id: str, db: AsyncSession = Depends(get_db)) -> list[JobResponse]:
    result = await db.execute(
        select(ProcessingJob).where(ProcessingJob.case_id == case_id).order_by(ProcessingJob.queued_at.desc())
    )
    return [JobResponse.model_validate(j) for j in result.scalars().all()]
