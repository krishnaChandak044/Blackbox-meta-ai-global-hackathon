"""
services/api/routes/dynamics.py
────────────────────────────────
Phase 4 — Dynamics inference API routes.

POST /cases/{case_id}/media/{media_id}/dynamics  — queue inference job
GET  /cases/{case_id}/media/{media_id}/dynamics  — get latest run + status
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.auth.session import current_user
from services.api.db.models import (
    DynamicsRun, HomographyFit, JobStatus, JobStage,
    ObjectTrack, ProcessingJob, SourceMedia, TrackPointRow,
)
from services.api.db.session import get_db

router = APIRouter(prefix="/cases/{case_id}/media/{media_id}", tags=["dynamics"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class DynamicsParams(BaseModel):
    """User-declared parameters for the dynamics inference job."""
    track_id: str
    calibration_fit_id: str
    seed: int = 42
    max_speed_ms: float = Field(50.0, ge=1.0, le=200.0, description="Upper bound on speed (m/s)")
    max_accel_ms2: float = Field(15.0, ge=0.1, le=50.0, description="Upper bound on |acceleration| (m/s²)")
    try_two_segment: bool = True


class DynamicsRunStatus(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: str = Field(validation_alias="id")
    status: str
    track_id: str
    calibration_fit_id: str
    model_name: str
    model_version: str
    seed: int
    interval_type: str
    entry_speed_kmh: float | None
    entry_speed_lo_kmh: float | None
    entry_speed_hi_kmh: float | None
    mean_decel_ms2: float | None
    mean_decel_lo_ms2: float | None
    mean_decel_hi_ms2: float | None
    fitted_points_json: str | None
    uncertainty_json: str | None
    certificates_json: str | None
    fit_quality_json: str | None
    braking_onset_json: str | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None

# ── Helpers ───────────────────────────────────────────────────────────────────

async def _require_case_media(case_id: str, media_id: str, db: AsyncSession) -> SourceMedia:
    media = await db.get(SourceMedia, media_id)
    if media is None or media.case_id != case_id:
        raise HTTPException(404, detail="Media not found in this case")
    return media


def _git_rev() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "unknown"


def _hash_track_points(points) -> str:
    blob = json.dumps(
        [{"fi": p.frame_index, "x": p.world_x, "y": p.world_y,
          "ts": p.presentation_ts_s, "sigma": p.pixel_localisation_sigma_m}
         for p in points],
        sort_keys=True, separators=(",", ":"),
    ).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/dynamics", status_code=202)
async def queue_dynamics(
    case_id: str,
    media_id: str,
    payload: DynamicsParams,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(current_user),
) -> dict[str, str]:
    """
    Queue a new dynamics inference job.

    Validates:
    - Track exists and belongs to this media/case
    - Calibration fit exists
    - Track has ≥5 world-coordinate observations

    Returns job_id and dynamics_run_id.
    """
    media = await _require_case_media(case_id, media_id, db)

    # Validate track
    track = await db.get(ObjectTrack, payload.track_id)
    if track is None or track.media_id != media_id or track.case_id != case_id:
        raise HTTPException(400, "track_not_found: track must belong to this media")
    if track.category != "vehicle":
        raise HTTPException(422, "track_category_invalid: dynamics fit requires a vehicle track")
    if not track.is_human_confirmed:
        raise HTTPException(422, "track_unconfirmed: confirm the selected vehicle track first")

    # Load + hash track points for version locking
    pts_result = await db.execute(
        select(TrackPointRow)
        .where(TrackPointRow.track_id == payload.track_id)
        .order_by(TrackPointRow.presentation_ts_s)
    )
    pts = pts_result.scalars().all()
    if len(pts) < 5:
        raise HTTPException(422, f"insufficient_observations: need ≥5, got {len(pts)}")
    if any(p.pixel_localisation_sigma_m is None or p.pixel_localisation_sigma_m <= 0 for p in pts):
        raise HTTPException(422, "localisation_uncertainty_missing: rerun tracking to store pixel-localisation uncertainty")

    track_version_hash = _hash_track_points(pts)

    # Validate calibration fit
    hf = await db.get(HomographyFit, payload.calibration_fit_id)
    if hf is None or hf.media_id != media_id or hf.case_id != case_id or not hf.is_active:
        raise HTTPException(400, "calibration_not_found: HomographyFit must belong to this media")

    if hf.scale_metres_per_pixel is None or hf.scale_relative_error is None:
        raise HTTPException(422, "calibration_invalid: scale and its relative error are required")
    if hf.reprojection_rmse_px is None or hf.reprojection_rmse_px <= 0:
        raise HTTPException(422, "calibration_invalid: positive homography RMSE is required")
    if media.sha256 is None:
        raise HTTPException(422, "media_hash_missing: source media hash is required")

    # Create DynamicsRun record
    params_dict = {
        "bounds": {
            "max_speed_ms": payload.max_speed_ms,
            "max_accel_ms2": payload.max_accel_ms2,
        },
        "try_two_segment": payload.try_two_segment,
    }

    software_revision = _git_rev()
    params_json = json.dumps(params_dict, sort_keys=True, default=str)
    provenance = json.dumps({
        "track_id": payload.track_id,
        "track_version_hash": track_version_hash,
        "calibration_fit_id": hf.id,
        "media_sha256": media.sha256,
        "model": "piecewise_const_accel_2d_v1",
        "model_version": "1.0.0",
        "software_revision": software_revision,
        "seed": payload.seed,
        "params": params_json,
    }, sort_keys=True).encode()
    stable_run_id = hashlib.sha256(provenance).hexdigest()[:36]
    existing = await db.get(DynamicsRun, stable_run_id)
    if existing is not None:
        if existing.job_id:
            return {"dynamics_run_id": existing.id, "job_id": existing.job_id, "status": existing.status}
        raise HTTPException(409, "An identical dynamics run already exists without a linked job")

    dr = DynamicsRun(
        id=stable_run_id,
        case_id=case_id,
        media_id=media_id,
        track_id=payload.track_id,
        track_version_hash=track_version_hash,
        calibration_fit_id=payload.calibration_fit_id,
        media_sha256=media.sha256 or "",
        model_name="piecewise_const_accel_2d_v1",
        model_version="1.0.0",
        software_revision=software_revision,
        seed=payload.seed,
        params_json=params_json,
        status="queued",
    )
    db.add(dr)

    # Create processing job
    job = ProcessingJob(
        id=str(uuid.uuid4()),
        case_id=case_id,
        media_id=media_id,
        stage=JobStage.DYNAMICS,
        status=JobStatus.QUEUED,
    )
    db.add(job)
    dr.job_id = job.id

    await db.commit()

    # Dispatch Celery task AFTER commit (no race condition)
    try:
        import asyncio
        from services.worker.jobs.dynamics import run_dynamics_task
        await asyncio.to_thread(run_dynamics_task.delay, dr.id, job.id)
    except Exception as exc:
        job.status = JobStatus.FAILED
        job.error_message = f"Could not enqueue dynamics: {exc}"[:1000]
        dr.status = "failed"
        dr.error_message = job.error_message
        await db.commit()
        raise HTTPException(503, "Dynamics worker unavailable") from exc

    return {"dynamics_run_id": dr.id, "job_id": job.id, "status": "queued"}


@router.get("/dynamics", response_model=DynamicsRunStatus)
async def get_dynamics(
    case_id: str,
    media_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(current_user),
) -> DynamicsRunStatus:
    """
    Get the latest dynamics run for this media.
    Returns run status, fit results, uncertainty, certificates.
    Stale runs (track/calibration changed) are surfaced — not silently reused.
    """
    await _require_case_media(case_id, media_id, db)

    result = await db.execute(
        select(DynamicsRun)
        .where(DynamicsRun.case_id == case_id, DynamicsRun.media_id == media_id)
        .order_by(DynamicsRun.created_at.desc())
        .limit(1)
    )
    dr = result.scalar_one_or_none()
    if dr is None:
        raise HTTPException(404, "No dynamics run found for this media. POST to queue one.")

    # Surface stale runs when track inputs or the active calibration changed.
    pts_result = await db.execute(
        select(TrackPointRow).where(TrackPointRow.track_id == dr.track_id)
        .order_by(TrackPointRow.presentation_ts_s)
    )
    pts = pts_result.scalars().all()
    current_fit = await db.execute(
        select(HomographyFit.id).where(
            HomographyFit.media_id == media_id, HomographyFit.is_active.is_(True)
        ).order_by(HomographyFit.fitted_at.desc()).limit(1)
    )
    active_fit_id = current_fit.scalar_one_or_none()
    if dr.status == "done" and (
        _hash_track_points(pts) != dr.track_version_hash
        or active_fit_id != dr.calibration_fit_id
        or media.sha256 != dr.media_sha256
    ):
        dr.status = "stale"
        dr.error_message = "Inputs changed after this run; queue a new dynamics analysis."
        await db.commit()
    return DynamicsRunStatus.model_validate(dr)
