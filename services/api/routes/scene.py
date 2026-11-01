"""Read-only, provenance-preserving 3D scene API (backend contract only)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from engine.scene3d import build_scene_payload
from services.api.auth.session import current_user
from services.api.db.models import (
    CounterfactualRun,
    DynamicsRun,
    HomographyFit,
    ObjectTrack,
    RivalSearch,
    SourceMedia,
    TrackPointRow,
)
from services.api.db.session import get_db

router = APIRouter(prefix="/cases/{case_id}/media/{media_id}/scene3d", tags=["scene3d"])


@router.get("")
async def get_scene(case_id: str, media_id: str,
                    db: AsyncSession = Depends(get_db),
                    _: str = Depends(current_user)) -> dict:
    media = await db.get(SourceMedia, media_id)
    if media is None or media.case_id != case_id:
        raise HTTPException(404, "Media not found in this case")
    track_rows = (await db.execute(select(ObjectTrack).where(
        ObjectTrack.case_id == case_id, ObjectTrack.media_id == media_id
    ).order_by(ObjectTrack.id))).scalars().all()
    tracks = []
    for track in track_rows:
        points = (await db.execute(select(TrackPointRow).where(
            TrackPointRow.track_id == track.id
        ).order_by(TrackPointRow.presentation_ts_s, TrackPointRow.frame_index))).scalars().all()
        tracks.append({"track_id": track.id, "category": track.category,
                       "is_human_confirmed": track.is_human_confirmed,
                       "points": [{"frame_index": p.frame_index, "presentation_ts_s": p.presentation_ts_s,
                                   "world_x_m": p.world_x, "world_y_m": p.world_y,
                                   "sigma_m": p.sigma_m, "is_interpolated": p.is_interpolated}
                                  for p in points]})
    fit = (await db.execute(select(HomographyFit).where(
        HomographyFit.case_id == case_id, HomographyFit.media_id == media_id,
        HomographyFit.is_active.is_(True)
    ).order_by(HomographyFit.fitted_at.desc()).limit(1))).scalar_one_or_none()
    dynamics = (await db.execute(select(DynamicsRun).where(
        DynamicsRun.case_id == case_id, DynamicsRun.media_id == media_id, DynamicsRun.status == "done"
    ).order_by(DynamicsRun.id))).scalars().all()
    dynamics = [r for r in dynamics if r.calibration_fit_id == (fit.id if fit else None)]
    dynamics_by_id = {run.id: run for run in dynamics}
    tracks_by_id = {track["track_id"]: track for track in tracks}
    run_ids = [r.id for r in dynamics]
    counterfactuals = (await db.execute(select(CounterfactualRun).where(
        CounterfactualRun.case_id == case_id, CounterfactualRun.media_id == media_id,
        CounterfactualRun.baseline_run_id.in_(run_ids) if run_ids else False
    ).order_by(CounterfactualRun.id))).scalars().all()
    rivals = (await db.execute(select(RivalSearch).where(
        RivalSearch.case_id == case_id, RivalSearch.media_id == media_id,
        RivalSearch.primary_run_id.in_(run_ids) if run_ids else False
    ).order_by(RivalSearch.id))).scalars().all()
    rival_inputs = []
    for rival in rivals:
        primary = dynamics_by_id.get(rival.primary_run_id)
        matched_track = tracks_by_id.get(primary.track_id) if primary else None
        rival_inputs.append({"id": rival.id, "manifest_json": rival.manifest_json,
            "rivals_json": rival.rivals_json,
            "track_observations": matched_track["points"] if matched_track else []})
    return build_scene_payload(
        case_id=case_id, media_id=media_id, media_sha256=media.sha256,
        calibration={"id": fit.id, "scale_metres_per_pixel": fit.scale_metres_per_pixel,
                     "reprojection_rmse_px": fit.reprojection_rmse_px} if fit else None,
        tracks=tracks,
        dynamics_runs=[{"id": r.id, "interval_type": r.interval_type,
                        "fitted_points_json": r.fitted_points_json} for r in dynamics],
        counterfactuals=[{"id": r.id, "baseline_run_id": r.baseline_run_id,
                          "simulated_points_json": r.simulated_points_json,
                          "illustrative_label": r.illustrative_label} for r in counterfactuals],
        rivals=rival_inputs,
    )
