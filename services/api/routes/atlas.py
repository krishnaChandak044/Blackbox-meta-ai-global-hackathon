"""Private-by-default Prevention Atlas contribution and aggregation APIs."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.auth.session import current_user
from services.api.db.models import (
    AtlasConsent,
    AtlasConsentEvent,
    AtlasContribution,
    Case,
    DynamicsRun,
)
from services.api.db.session import get_db

router = APIRouter(prefix="/atlas", tags=["prevention-atlas"])
SCOPE_VERSION = "atlas-derived-coarse-v1"
MIN_COHORT = max(5, int(os.getenv("ATLAS_MIN_COHORT", "5")))


class ConsentInput(BaseModel):
    opted_in: bool
    scope_version: str = SCOPE_VERSION

    @model_validator(mode="after")
    def require_current_scope(self):
        if self.scope_version != SCOPE_VERSION:
            raise ValueError(f"scope_version must equal {SCOPE_VERSION}")
        return self


class ContributionInput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    source_run_id: str
    coarse_cell: str = Field(..., pattern=r"^[0123456789bcdefghjkmnpqrstuvwxyz]{4,5}$",
                             description="Coarse geohash cell of length 4–5; exact coordinates are rejected")
    time_bucket: str = Field(..., pattern=r"^\d{4}-Q[1-4]$")
    conflict_type: str = Field(..., pattern="^(crossing|rear_end|turning|merge|other)$")
    road_user_mix: dict[str, int]
    metrics: dict[str, float]
    reviewer_confirmed: bool

    @model_validator(mode="after")
    def validate_vocabulary(self):
        allowed_users = {"pedestrian", "cyclist", "motor_vehicle", "other"}
        allowed_metrics = {"conflict_count", "minimum_ttc_s", "p95_speed_kmh", "near_miss_count"}
        if not set(self.road_user_mix).issubset(allowed_users):
            raise ValueError("road_user_mix keys must be from the approved aggregate vocabulary")
        if not set(self.metrics).issubset(allowed_metrics):
            raise ValueError("metrics keys must be from the approved aggregate vocabulary")
        if any(value < 0 for value in self.road_user_mix.values()):
            raise ValueError("road_user_mix values cannot be negative")
        if any(value < 0 or value > 10000 for value in self.metrics.values()):
            raise ValueError("metrics must be between 0 and 10000")
        if "minimum_ttc_s" in self.metrics and self.metrics["minimum_ttc_s"] < 0:
            raise ValueError("minimum_ttc_s cannot be negative")
        if "p95_speed_kmh" in self.metrics and self.metrics["p95_speed_kmh"] > 500:
            raise ValueError("p95_speed_kmh exceeds the supported range")
        return self


@router.post("/cases/{case_id}/consent")
async def set_consent(case_id: str, payload: ConsentInput,
                      db: AsyncSession = Depends(get_db), user: str = Depends(current_user)) -> dict:
    case = await db.get(Case, case_id)
    if case is None:
        raise HTTPException(404, "Case not found")
    if payload.scope_version != SCOPE_VERSION:
        raise HTTPException(422, f"Unsupported consent scope; expected {SCOPE_VERSION}")
    consent = (await db.execute(select(AtlasConsent).where(AtlasConsent.case_id == case_id))).scalar_one_or_none()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if consent is None:
        consent = AtlasConsent(id=str(uuid.uuid4()), case_id=case_id, opted_in=payload.opted_in,
                               scope_version=SCOPE_VERSION, actor=user,
                               consented_at=now if payload.opted_in else None,
                               revoked_at=None if payload.opted_in else now)
        db.add(consent)
    else:
        consent.opted_in = payload.opted_in
        consent.actor = user
        consent.scope_version = SCOPE_VERSION
        consent.consented_at = now if payload.opted_in else consent.consented_at
        consent.revoked_at = None if payload.opted_in else now
        if not payload.opted_in:
            # Revocation immediately removes this case from all future aggregates.
            await db.execute(AtlasContribution.__table__.delete().where(AtlasContribution.case_id == case_id))
    db.add(AtlasConsentEvent(id=str(uuid.uuid4()), case_id=case_id, opted_in=payload.opted_in,
                             scope_version=SCOPE_VERSION, actor=user))
    await db.commit()
    return {"case_id": case_id, "opted_in": consent.opted_in, "scope_version": consent.scope_version,
            "actor": user, "consented_at": consent.consented_at, "revoked_at": consent.revoked_at}


@router.get("/cases/{case_id}/consent")
async def get_consent(case_id: str, db: AsyncSession = Depends(get_db),
                      _: str = Depends(current_user)) -> dict:
    if await db.get(Case, case_id) is None:
        raise HTTPException(404, "Case not found")
    consent = (await db.execute(select(AtlasConsent).where(
        AtlasConsent.case_id == case_id
    ))).scalar_one_or_none()
    return {"case_id": case_id, "opted_in": bool(consent and consent.opted_in),
            "scope_version": consent.scope_version if consent else SCOPE_VERSION,
            "consented_at": consent.consented_at if consent else None,
            "revoked_at": consent.revoked_at if consent else None}


@router.post("/cases/{case_id}/contributions", status_code=201)
async def add_contribution(case_id: str, payload: ContributionInput,
                           db: AsyncSession = Depends(get_db), user: str = Depends(current_user)) -> dict:
    consent = (await db.execute(select(AtlasConsent).where(
        AtlasConsent.case_id == case_id, AtlasConsent.opted_in.is_(True)
    ))).scalar_one_or_none()
    if consent is None:
        raise HTTPException(409, "Separate Prevention Atlas opt-in consent is required")
    if not payload.reviewer_confirmed:
        raise HTTPException(422, "A reviewer must confirm the derived incident summary")
    run = await db.get(DynamicsRun, payload.source_run_id)
    if run is None or run.case_id != case_id or run.status != "done":
        raise HTTPException(422, "A completed dynamics run from this case is required")
    if any(value > 10000 for value in payload.road_user_mix.values()):
        raise HTTPException(422, "Road-user counts must be between 0 and 10000")
    if not payload.road_user_mix or not payload.metrics:
        raise HTTPException(422, "At least one bounded derived metric and road-user count are required")
    dedupe = hashlib.sha256(f"{case_id}:{payload.source_run_id}:{payload.coarse_cell}:{payload.time_bucket}".encode()).hexdigest()
    same_cell = (await db.execute(select(AtlasContribution).where(
        AtlasContribution.case_id == case_id, AtlasContribution.coarse_cell == payload.coarse_cell,
        AtlasContribution.time_bucket == payload.time_bucket, AtlasContribution.conflict_type == payload.conflict_type
    ).limit(1))).scalar_one_or_none()
    if same_cell:
        raise HTTPException(409, "Only one contribution per case, cell, period, and conflict type is counted")
    existing = (await db.execute(select(AtlasContribution).where(AtlasContribution.dedupe_key == dedupe))).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "This case/run is already represented in this Atlas cell and period")
    row = AtlasContribution(id=str(uuid.uuid4()), case_id=case_id, source_run_id=run.id,
                            dedupe_key=dedupe, coarse_cell=payload.coarse_cell,
                            time_bucket=payload.time_bucket, conflict_type=payload.conflict_type,
                            road_user_mix_json=json.dumps(payload.road_user_mix, sort_keys=True),
                            metrics_json=json.dumps(payload.metrics, sort_keys=True),
                            provenance_json=json.dumps({"run_id": run.id, "reviewer_confirmed": True,
                                                        "reviewer": user, "consent_id": consent.id,
                                                        "consent_scope": consent.scope_version}, sort_keys=True))
    db.add(row)
    await db.commit()
    return {"contribution_id": row.id, "included": True, "public_or_cross_case_visibility": "suppressed until cohort threshold"}


@router.get("")
async def atlas_aggregates(db: AsyncSession = Depends(get_db),
                           _: str = Depends(current_user)) -> dict:
    rows = (await db.execute(select(AtlasContribution).join(
        AtlasConsent, AtlasConsent.case_id == AtlasContribution.case_id
    ).where(AtlasConsent.opted_in.is_(True)).order_by(
        AtlasContribution.coarse_cell, AtlasContribution.time_bucket, AtlasContribution.conflict_type
    ))).scalars().all()
    groups: dict[tuple[str, str, str], list[AtlasContribution]] = {}
    for row in rows:
        groups.setdefault((row.coarse_cell, row.time_bucket, row.conflict_type), []).append(row)
    output = []
    for (cell, bucket, conflict), members in sorted(groups.items()):
        distinct_cases = {m.case_id for m in members}
        if len(distinct_cases) < MIN_COHORT:
            continue
        metrics: dict[str, list[float]] = {}
        road_users: dict[str, int] = {}
        for member in members:
            for name, value in json.loads(member.metrics_json).items():
                metrics.setdefault(name, []).append(float(value))
            for name, value in json.loads(member.road_user_mix_json).items():
                road_users[name] = road_users.get(name, 0) + int(value)
        output.append({"coarse_cell": cell, "time_bucket": bucket, "conflict_type": conflict,
                       "distinct_case_count": len(distinct_cases), "provenance": "consented derived summaries",
                       "synthetic_included": False,
                       "road_user_mix": road_users,
                       "mean_metrics": {name: sum(values) / len(values) for name, values in metrics.items()},
                       "limitations": "Aggregated descriptive patterns; not causal evidence or an engineering recommendation."})
    return {"minimum_cohort": MIN_COHORT, "private_by_default": True,
            "access_scope": "authenticated private analyst view; no public endpoint",
            "suppressed_group_count": sum(len(v) < MIN_COHORT for v in groups.values()),
            "aggregates": output}
