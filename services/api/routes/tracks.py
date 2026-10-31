"""
services/api/routes/tracks.py
──────────────────────────────
Track CRUD + human-correction endpoints.

GET  /cases/{case_id}/media/{media_id}/tracks           — list tracks (summary)
GET  /cases/{case_id}/media/{media_id}/tracks/{id}      — track detail with points
POST /cases/{case_id}/media/{media_id}/tracks/run       — queue tracking job
POST /cases/{case_id}/media/{media_id}/tracks/{id}/confirm  — human confirm
PATCH /cases/{case_id}/media/{media_id}/tracks/{id}/points/{frame}  — correct point
DELETE /cases/{case_id}/media/{media_id}/tracks/{id}    — delete one track
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.auth.session import current_user
from services.api.db.models import (
    JobStage,
    JobStatus,
    ObjectTrack,
    ProcessingJob,
    SourceMedia,
    TrackPointRow,
)
from services.api.db.session import get_db

router = APIRouter(
    prefix="/cases/{case_id}/media/{media_id}/tracks",
    tags=["tracks"],
)


# ── Schemas ────────────────────────────────────────────────────────────────────


class TrackPointOut(BaseModel):
    frame_index: int
    presentation_ts_s: float
    bbox_x_min: float
    bbox_y_min: float
    bbox_x_max: float
    bbox_y_max: float
    gc_pixel_x: float
    gc_pixel_y: float
    world_x: float | None
    world_y: float | None
    sigma_m: float | None
    detection_confidence: float
    is_interpolated: bool
    is_human_corrected: bool

    class Config:
        from_attributes = True


class TrackSummary(BaseModel):
    id: str
    tracker_track_id: str
    category: str
    tracker_model: str
    first_frame: int
    last_frame: int
    point_count: int
    is_complete: bool
    is_human_confirmed: bool
    created_at: datetime

    class Config:
        from_attributes = True


class TrackDetail(TrackSummary):
    points: list[TrackPointOut]

    class Config:
        from_attributes = True


class PointCorrection(BaseModel):
    bbox_x_min: float = Field(..., ge=0)
    bbox_y_min: float = Field(..., ge=0)
    bbox_x_max: float = Field(..., gt=0)
    bbox_y_max: float = Field(..., gt=0)


# ── Helpers ────────────────────────────────────────────────────────────────────


async def _get_media_or_404(case_id: str, media_id: str, db: AsyncSession) -> SourceMedia:
    result = await db.execute(
        select(SourceMedia).where(SourceMedia.id == media_id, SourceMedia.case_id == case_id)
    )
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Media not found")
    return m


async def _get_track_or_404(track_id: str, media_id: str, db: AsyncSession) -> ObjectTrack:
    result = await db.execute(
        select(ObjectTrack).where(ObjectTrack.id == track_id, ObjectTrack.media_id == media_id)
    )
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Track not found")
    return t


# ── List tracks ────────────────────────────────────────────────────────────────


@router.get("/", response_model=list[TrackSummary])
async def list_tracks(
    case_id: str,
    media_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(current_user),
) -> list[TrackSummary]:
    await _get_media_or_404(case_id, media_id, db)
    result = await db.execute(
        select(ObjectTrack)
        .where(ObjectTrack.media_id == media_id)
        .order_by(ObjectTrack.first_frame)
    )
    return [TrackSummary.model_validate(t) for t in result.scalars().all()]


# ── Get single track with all points ──────────────────────────────────────────


@router.get("/{track_id}", response_model=TrackDetail)
async def get_track(
    case_id: str,
    media_id: str,
    track_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(current_user),
) -> TrackDetail:
    await _get_media_or_404(case_id, media_id, db)
    track = await _get_track_or_404(track_id, media_id, db)

    pts_result = await db.execute(
        select(TrackPointRow)
        .where(TrackPointRow.track_id == track_id)
        .order_by(TrackPointRow.frame_index)
    )
    pts = pts_result.scalars().all()

    summary = TrackSummary.model_validate(track)
    return TrackDetail(
        **summary.model_dump(), points=[TrackPointOut.model_validate(p) for p in pts]
    )


# ── Queue tracking run ─────────────────────────────────────────────────────────


@router.post("/run", status_code=status.HTTP_202_ACCEPTED)
async def run_tracking(
    case_id: str,
    media_id: str,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(current_user),
) -> dict:
    """
    Queue a tracking job for this media clip.

    Any existing tracks will be replaced when the job completes.
    Returns the queued job ID so the client can poll /jobs/{id}.
    """
    await _get_media_or_404(case_id, media_id, db)

    job = ProcessingJob(
        id=str(uuid.uuid4()),
        case_id=case_id,
        media_id=media_id,
        stage=JobStage.TRACK,
        status=JobStatus.QUEUED,
    )
    db.add(job)
    await db.commit()

    # Dispatch Celery task
    try:
        import asyncio

        from services.worker.jobs.tracking import run_tracking_task

        await asyncio.to_thread(run_tracking_task.delay, media_id, job.id)
    except Exception as exc:
        job.status = JobStatus.FAILED
        job.error_message = f"Could not enqueue tracking: {exc}"[:500]
        await db.commit()
        raise HTTPException(status_code=503, detail="Worker unavailable") from exc

    return {"job_id": job.id, "status": "queued"}


# ── Human confirm ──────────────────────────────────────────────────────────────


@router.post("/{track_id}/confirm", response_model=TrackSummary)
async def confirm_track(
    case_id: str,
    media_id: str,
    track_id: str,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(current_user),
) -> TrackSummary:
    """
    Mark a track as human-confirmed.

    This is recorded in the audit trail.  Confirmed tracks are shown with
    a different visual indicator in the trajectory overlay.
    """
    await _get_media_or_404(case_id, media_id, db)
    track = await _get_track_or_404(track_id, media_id, db)
    track.is_human_confirmed = True
    track.human_confirmed_by = user
    track.human_confirmed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(track)
    return TrackSummary.model_validate(track)


# ── Correct a single point ─────────────────────────────────────────────────────


@router.patch("/{track_id}/points/{frame_index}", response_model=TrackPointOut)
async def correct_point(
    case_id: str,
    media_id: str,
    track_id: str,
    frame_index: int,
    payload: PointCorrection,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(current_user),
) -> TrackPointOut:
    """
    Human correction of a bounding box at a specific frame.

    Marks the point is_human_corrected=True.  The world projection is
    cleared (set to NULL) and will be recomputed on next tracking run
    so that homography projection uses the corrected pixel.
    """
    await _get_media_or_404(case_id, media_id, db)
    await _get_track_or_404(track_id, media_id, db)

    result = await db.execute(
        select(TrackPointRow).where(
            TrackPointRow.track_id == track_id,
            TrackPointRow.frame_index == frame_index,
        )
    )
    point = result.scalar_one_or_none()
    if not point:
        raise HTTPException(status_code=404, detail=f"No point at frame {frame_index}")

    # Update bbox
    point.bbox_x_min = payload.bbox_x_min
    point.bbox_y_min = payload.bbox_y_min
    point.bbox_x_max = payload.bbox_x_max
    point.bbox_y_max = payload.bbox_y_max

    # Update ground contact (bottom-centre)
    point.gc_pixel_x = (payload.bbox_x_min + payload.bbox_x_max) / 2.0
    point.gc_pixel_y = payload.bbox_y_max

    # Invalidate world projection — will be recalculated on next tracking run
    point.world_x = None
    point.world_y = None
    point.sigma_m = None

    point.is_human_corrected = True

    await db.commit()
    await db.refresh(point)
    return TrackPointOut.model_validate(point)


# ── Delete track ───────────────────────────────────────────────────────────────


@router.delete("/{track_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_track(
    case_id: str,
    media_id: str,
    track_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(current_user),
) -> None:
    await _get_media_or_404(case_id, media_id, db)
    track = await _get_track_or_404(track_id, media_id, db)
    await db.delete(track)
    await db.commit()
