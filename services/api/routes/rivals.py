"""Bounded rival-hypothesis search API."""

from __future__ import annotations

import json
import asyncio
import uuid
from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from engine.rival.hypothesis_search import search_rivals
from services.api.auth.session import current_user
from services.api.db.models import DynamicsRun, HomographyFit, ObjectTrack, RivalSearch, TrackPointRow
from services.api.db.session import get_db
from services.api.routes.dynamics import _hash_track_points, _require_case_media

router = APIRouter(prefix="/cases/{case_id}/media/{media_id}", tags=["rivals"])


class SecondViewInput(BaseModel):
    """Second-view observations plus primary-to-second synchronization metadata."""
    synchronized: bool = False
    calibrated: bool = False
    same_world_frame: bool = False
    observations: list[dict] = Field(default_factory=list)
    primary_observations: list[dict] = Field(default_factory=list)


class RivalSearchRequest(BaseModel):
    primary_run_id: str
    seed: int = 42
    grid_n: int = Field(15, ge=3, le=25)
    acceptance_threshold_m: float = Field(1.0, gt=0, le=20)
    speed_lo_kmh: float | None = Field(None, ge=0)
    speed_hi_kmh: float | None = Field(None, gt=0, le=250)
    decel_lo_ms2: float | None = Field(None, gt=0)
    decel_hi_ms2: float | None = Field(None, gt=0, le=30)
    second_view: SecondViewInput | None = None


class RivalSearchResponse(BaseModel):
    id: str
    primary_run_id: str
    manifest: dict
    rivals: list[dict]
    empty_search_message: str
    second_view_used: bool
    second_view_notes: str
    created_at: datetime


def _to_response(row: RivalSearch) -> RivalSearchResponse:
    return RivalSearchResponse(
        id=row.id, primary_run_id=row.primary_run_id,
        manifest=json.loads(row.manifest_json), rivals=json.loads(row.rivals_json),
        empty_search_message=row.empty_search_message,
        second_view_used=row.second_view_used,
        second_view_notes=row.second_view_notes, created_at=row.created_at,
    )


@router.post("/rivals/search", response_model=RivalSearchResponse, status_code=201)
async def run_rival_search(
    case_id: str,
    media_id: str,
    payload: RivalSearchRequest,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(current_user),
) -> RivalSearchResponse:
    media = await _require_case_media(case_id, media_id, db)
    primary = await db.get(DynamicsRun, payload.primary_run_id)
    if primary is None or primary.case_id != case_id or primary.media_id != media_id or primary.status != "done":
        raise HTTPException(409, "A completed dynamics run for this media is required")
    if primary.entry_speed_kmh is None:
        raise HTTPException(409, "Primary entry speed is not available; cannot bound rival search")
    track = await db.get(ObjectTrack, primary.track_id)
    if track is None or not track.is_human_confirmed:
        raise HTTPException(409, "The source track must still exist and be reviewer-confirmed")
    points_result = await db.execute(
        select(TrackPointRow).where(TrackPointRow.track_id == track.id)
        .order_by(TrackPointRow.presentation_ts_s)
    )
    points = points_result.scalars().all()
    if _hash_track_points(points) != primary.track_version_hash:
        raise HTTPException(409, "Track changed after the primary run; queue a fresh dynamics run")
    fit = await db.get(HomographyFit, primary.calibration_fit_id)
    if fit is None or fit.media_id != media_id or not fit.is_active:
        raise HTTPException(409, "Calibration changed after the primary run")
    if media.sha256 != primary.media_sha256:
        raise HTTPException(409, "Media changed after the primary run")
    observations = [
        {"frame_index": p.frame_index, "presentation_ts_s": p.presentation_ts_s,
         "world_x_m": p.world_x, "world_y_m": p.world_y}
        for p in points if p.world_x is not None and p.world_y is not None
    ]
    onset_data = json.loads(primary.braking_onset_json) if primary.braking_onset_json else None
    primary_data = {
        "run_id": primary.id, "entry_speed_kmh": primary.entry_speed_kmh,
        "mean_decel_ms2": primary.mean_decel_ms2,
        "braking_onset_s": onset_data.get("ts_lo_s") if onset_data else observations[0]["presentation_ts_s"],
    }
    params = {
        "n_grid": payload.grid_n,
        "acceptance_threshold_m": payload.acceptance_threshold_m,
        "decel_reference_ms2": primary.mean_decel_ms2 or 4.0,
    }
    for key in ("speed_lo_kmh", "speed_hi_kmh", "decel_lo_ms2", "decel_hi_ms2"):
        value = getattr(payload, key)
        if value is not None:
            params[key] = value
    second_view = payload.second_view.model_dump() if payload.second_view else None
    try:
        result = await asyncio.to_thread(
            search_rivals, primary_data, observations,
            {"calibrated": fit.scale_metres_per_pixel is not None},
            params, second_view, payload.seed,
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    existing = await db.get(RivalSearch, result.manifest.search_id)
    if existing is not None:
        return _to_response(existing)
    row = RivalSearch(
        id=result.manifest.search_id, case_id=case_id, media_id=media_id,
        primary_run_id=primary.id,
        manifest_json=json.dumps(asdict(result.manifest), sort_keys=True),
        rivals_json=json.dumps([asdict(rival) for rival in result.rivals]),
        empty_search_message=result.empty_search_message,
        second_view_used=result.second_view_used,
        second_view_notes=result.second_view_notes,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _to_response(row)


@router.get("/rivals", response_model=RivalSearchResponse)
async def get_latest_rivals(
    case_id: str,
    media_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(current_user),
) -> RivalSearchResponse:
    media = await _require_case_media(case_id, media_id, db)
    result = await db.execute(
        select(RivalSearch).where(RivalSearch.case_id == case_id, RivalSearch.media_id == media_id)
        .order_by(RivalSearch.created_at.desc()).limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "No rival search found; submit POST /rivals/search")
    primary = await db.get(DynamicsRun, row.primary_run_id)
    if primary is None or media.sha256 != primary.media_sha256:
        raise HTTPException(409, "Rival search is stale because its primary run or source media changed")
    points_result = await db.execute(
        select(TrackPointRow).where(TrackPointRow.track_id == primary.track_id)
        .order_by(TrackPointRow.presentation_ts_s)
    )
    if _hash_track_points(points_result.scalars().all()) != primary.track_version_hash:
        raise HTTPException(409, "Rival search is stale because the source track changed")
    fit = await db.get(HomographyFit, primary.calibration_fit_id)
    if fit is None or not fit.is_active:
        raise HTTPException(409, "Rival search is stale because its calibration is no longer active")
    return _to_response(row)
