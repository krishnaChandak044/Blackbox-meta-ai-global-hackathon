"""Illustrative counterfactual simulation API."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from engine.counterfactual.simulator import compute_sensitivity, run_counterfactual
from engine.dynamics.models import CounterfactualIntervention
from engine.dynamics.serialization import dynamics_result_from_storage
from services.api.auth.session import current_user
from services.api.db.models import CounterfactualRun, DynamicsRun, HomographyFit, ObjectTrack, TrackPointRow
from services.api.db.session import get_db
from services.api.routes.dynamics import _hash_track_points, _require_case_media

router = APIRouter(prefix="/cases/{case_id}/media/{media_id}", tags=["simulation"])


class SimulationRequest(BaseModel):
    baseline_run_id: str
    braking_onset_shift_s: float = Field(0.0, ge=-5.0, le=5.0)
    entry_speed_override_kmh: float | None = Field(None, ge=0.0, le=250.0)
    decel_override_ms2: float | None = Field(None, gt=0.0, le=20.0)


class SimulationResponse(BaseModel):
    id: str
    baseline_run_id: str
    status: str
    simulated_points: list[dict]
    stopping_distance_m: float | None
    stopping_time_s: float | None
    sensitivity: list[dict]
    extrapolation_outside_support: bool
    illustrative_label: str
    assumptions: dict
    created_at: datetime


@router.post("/simulate", response_model=SimulationResponse, status_code=201)
async def simulate(
    case_id: str,
    media_id: str,
    payload: SimulationRequest,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(current_user),
) -> SimulationResponse:
    media = await _require_case_media(case_id, media_id, db)
    baseline = await db.get(DynamicsRun, payload.baseline_run_id)
    if baseline is None or baseline.case_id != case_id or baseline.media_id != media_id:
        raise HTTPException(404, "Baseline dynamics run not found for this media")
    if baseline.status != "done":
        raise HTTPException(409, f"Baseline run is {baseline.status}; only completed runs can be simulated")
    track = await db.get(ObjectTrack, baseline.track_id)
    fit = await db.get(HomographyFit, baseline.calibration_fit_id)
    points_result = await db.execute(select(TrackPointRow).where(TrackPointRow.track_id == baseline.track_id).order_by(TrackPointRow.presentation_ts_s))
    current_points = points_result.scalars().all()
    if (track is None or not track.is_human_confirmed or not fit or not fit.is_active
            or _hash_track_points(current_points) != baseline.track_version_hash
            or media.sha256 != baseline.media_sha256):
        raise HTTPException(409, "Baseline inputs changed; queue a fresh dynamics run before simulating")
    try:
        engine_baseline = dynamics_result_from_storage(baseline)
        intervention = CounterfactualIntervention(
            braking_onset_shift_s=payload.braking_onset_shift_s,
            entry_speed_override_kmh=payload.entry_speed_override_kmh,
            decel_override_ms2=payload.decel_override_ms2,
        )
        result = run_counterfactual(engine_baseline, intervention)
        sensitivity = compute_sensitivity(engine_baseline)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc

    assumptions = json.loads(result.assumptions_json)
    row = CounterfactualRun(
        id=str(uuid.uuid4()), case_id=case_id, media_id=media_id,
        baseline_run_id=baseline.id,
        intervention_json=json.dumps(asdict(intervention), sort_keys=True),
        simulated_points_json=json.dumps([asdict(point) for point in result.simulated_points]),
        sensitivity_json=json.dumps([asdict(item) for item in sensitivity]),
        stopping_distance_m=result.stopping_distance_m,
        stopping_time_s=result.stopping_time_s,
        extrapolation_outside_support=result.extrapolation_outside_support,
        assumptions_json=result.assumptions_json,
        illustrative_label=result.illustrative_label,
        created_by=user,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return SimulationResponse(
        id=row.id, baseline_run_id=row.baseline_run_id, status="complete",
        simulated_points=json.loads(row.simulated_points_json or "[]"),
        stopping_distance_m=row.stopping_distance_m, stopping_time_s=row.stopping_time_s,
        sensitivity=json.loads(row.sensitivity_json or "[]"),
        extrapolation_outside_support=row.extrapolation_outside_support,
        illustrative_label=row.illustrative_label,
        assumptions=json.loads(row.assumptions_json), created_at=row.created_at,
    )
