"""Transcripts router."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.auth.session import current_user
from services.api.db.models import Case, JobStage, JobStatus, ProcessingJob, SourceMedia, Transcript
from services.api.db.session import get_db
from services.api.schemas.transcript import TranscriptCreate, TranscriptResponse

router = APIRouter(prefix="/cases/{case_id}/transcripts", tags=["transcripts"])


async def _get_case_or_404(case_id: str, db: AsyncSession) -> Case:
    result = await db.execute(select(Case).where(Case.id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@router.post("/", response_model=TranscriptResponse, status_code=status.HTTP_201_CREATED)
async def create_transcript(case_id: str, payload: TranscriptCreate, db: AsyncSession = Depends(get_db), user: str = Depends(current_user)) -> TranscriptResponse:
    await _get_case_or_404(case_id, db)
    if payload.media_id:
        m = await db.execute(select(SourceMedia).where(SourceMedia.id == payload.media_id, SourceMedia.case_id == case_id))
        if not m.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Media not found for this case")
    tr = Transcript(
        id=str(uuid.uuid4()),
        case_id=case_id,
        media_id=payload.media_id,
        speaker_count=payload.speaker_count,
        language=payload.language,
        raw_text=payload.raw_text,
        diarised_json=payload.diarised_json,
        transcription_model=payload.transcription_model,
        word_count=len(payload.raw_text.split()),
        duration_seconds=payload.duration_seconds,
        created_by=user,
    )
    db.add(tr)
    await db.commit()
    await db.refresh(tr)
    return TranscriptResponse.model_validate(tr)


@router.get("/", response_model=list[TranscriptResponse])
async def list_transcripts(case_id: str, db: AsyncSession = Depends(get_db), _: str = Depends(current_user)) -> list[TranscriptResponse]:
    await _get_case_or_404(case_id, db)
    result = await db.execute(select(Transcript).where(Transcript.case_id == case_id).order_by(Transcript.created_at.desc()))
    return [TranscriptResponse.model_validate(t) for t in result.scalars().all()]


@router.get("/{transcript_id}", response_model=TranscriptResponse)
async def get_transcript(case_id: str, transcript_id: str, db: AsyncSession = Depends(get_db), _: str = Depends(current_user)) -> TranscriptResponse:
    await _get_case_or_404(case_id, db)
    result = await db.execute(select(Transcript).where(Transcript.id == transcript_id, Transcript.case_id == case_id))
    tr = result.scalar_one_or_none()
    if not tr:
        raise HTTPException(status_code=404, detail="Transcript not found")
    return TranscriptResponse.model_validate(tr)


@router.delete("/{transcript_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transcript(case_id: str, transcript_id: str, db: AsyncSession = Depends(get_db), _: str = Depends(current_user)) -> None:
    await _get_case_or_404(case_id, db)
    result = await db.execute(select(Transcript).where(Transcript.id == transcript_id, Transcript.case_id == case_id))
    tr = result.scalar_one_or_none()
    if not tr:
        raise HTTPException(status_code=404, detail="Transcript not found")
    await db.delete(tr)
    await db.commit()


@router.post("/media/{media_id}/transcribe", status_code=status.HTTP_202_ACCEPTED)
async def transcribe_media(case_id: str, media_id: str, db: AsyncSession = Depends(get_db), user: str = Depends(current_user)) -> dict:
    await _get_case_or_404(case_id, db)
    result = await db.execute(select(SourceMedia).where(SourceMedia.id == media_id, SourceMedia.case_id == case_id))
    media = result.scalar_one_or_none()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    job = ProcessingJob(id=str(uuid.uuid4()), case_id=case_id, media_id=media_id, stage=JobStage.TRANSCRIBE, status=JobStatus.QUEUED)
    db.add(job)
    await db.commit()
    try:
        from services.worker.jobs.transcription import transcribe_media_task

        await asyncio.to_thread(transcribe_media_task.delay, media_id, job.id)
    except Exception as exc:
        job.status = JobStatus.FAILED
        job.error_message = f"Could not enqueue transcription: {exc}"[:1000]
        await db.commit()
        raise HTTPException(status_code=503, detail="Transcription queue unavailable") from exc
    return {"job_id": job.id, "status": "queued"}
