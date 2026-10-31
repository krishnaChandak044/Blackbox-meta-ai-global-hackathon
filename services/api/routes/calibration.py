"""
services/api/routes/calibration.py
────────────────────────────────────
Calibration anchor management and homography fitting.

POST   /cases/{case_id}/media/{media_id}/calibration/anchors       — add anchor
GET    /cases/{case_id}/media/{media_id}/calibration/anchors       — list anchors
DELETE /cases/{case_id}/media/{media_id}/calibration/anchors/{id}  — remove anchor
POST   /cases/{case_id}/media/{media_id}/calibration/fit           — fit homography
GET    /cases/{case_id}/media/{media_id}/calibration/fit           — get active fit
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from engine.geometry.homography import (
    PixelPoint,
    WorldPoint,
    estimate_homography,
    reprojection_errors_px,
)
from engine.geometry.scale import ScaleUnavailable, derive_scale
from services.api.auth.session import current_user
from services.api.db.models import (
    CalibrationAnchor,
    HomographyFit,
    ObjectTrack,
    SourceMedia,
    TrackPointRow,
)
from services.api.db.session import get_db

router = APIRouter(
    prefix="/cases/{case_id}/media/{media_id}/calibration",
    tags=["calibration"],
)


# ── Schemas ────────────────────────────────────────────────────────────────────


class AnchorCreate(BaseModel):
    label: str = Field(..., min_length=1, max_length=100)
    pixel_x: float = Field(..., ge=0)
    pixel_y: float = Field(..., ge=0)
    world_x: float
    world_y: float
    known_distance_m: float | None = Field(None, gt=0)
    is_distance_ref_b: bool = False


class AnchorResponse(BaseModel):
    id: str
    media_id: str
    label: str
    pixel_x: float
    pixel_y: float
    world_x: float
    world_y: float
    known_distance_m: float | None
    is_distance_ref_b: bool
    reprojection_error_px: float | None
    created_at: datetime

    class Config:
        from_attributes = True


class HomographyFitResponse(BaseModel):
    id: str
    media_id: str
    anchor_count: int
    reprojection_rmse_px: float
    condition_number: float
    scale_metres_per_pixel: float | None
    scale_relative_error: float | None
    scale_source: str | None
    H: list[list[float]]  # 3×3 for the UI
    fitted_at: datetime
    is_active: bool
    per_anchor_errors_px: list[float] = []

    class Config:
        from_attributes = True


# ── Helpers ────────────────────────────────────────────────────────────────────


async def _get_media_or_404(case_id: str, media_id: str, db: AsyncSession) -> SourceMedia:
    result = await db.execute(
        select(SourceMedia).where(
            SourceMedia.id == media_id,
            SourceMedia.case_id == case_id,
        )
    )
    media = result.scalar_one_or_none()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    return media


async def _invalidate_calibration(db: AsyncSession, media_id: str) -> None:
    fits = await db.execute(select(HomographyFit).where(HomographyFit.media_id == media_id))
    for old in fits.scalars():
        old.is_active = False
    ids = select(ObjectTrack.id).where(ObjectTrack.media_id == media_id)
    await db.execute(
        update(TrackPointRow)
        .where(TrackPointRow.track_id.in_(ids))
        .values(world_x=None, world_y=None, sigma_m=None)
    )


# ── Anchor endpoints ───────────────────────────────────────────────────────────


@router.post(
    "/anchors",
    response_model=AnchorResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_anchor(
    case_id: str,
    media_id: str,
    payload: AnchorCreate,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(current_user),
) -> AnchorResponse:
    await _get_media_or_404(case_id, media_id, db)

    anchor = CalibrationAnchor(
        id=str(uuid.uuid4()),
        media_id=media_id,
        case_id=case_id,
        label=payload.label,
        pixel_x=payload.pixel_x,
        pixel_y=payload.pixel_y,
        world_x=payload.world_x,
        world_y=payload.world_y,
        known_distance_m=payload.known_distance_m,
        is_distance_ref_b=payload.is_distance_ref_b,
        created_by=user,
    )
    db.add(anchor)
    await _invalidate_calibration(db, media_id)
    await db.commit()
    await db.refresh(anchor)
    return AnchorResponse.model_validate(anchor)


@router.get("/anchors", response_model=list[AnchorResponse])
async def list_anchors(
    case_id: str,
    media_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(current_user),
) -> list[AnchorResponse]:
    await _get_media_or_404(case_id, media_id, db)
    result = await db.execute(
        select(CalibrationAnchor)
        .where(CalibrationAnchor.media_id == media_id)
        .order_by(CalibrationAnchor.created_at)
    )
    return [AnchorResponse.model_validate(a) for a in result.scalars().all()]


@router.delete("/anchors/{anchor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_anchor(
    case_id: str,
    media_id: str,
    anchor_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(current_user),
) -> None:
    result = await db.execute(
        select(CalibrationAnchor).where(
            CalibrationAnchor.id == anchor_id,
            CalibrationAnchor.media_id == media_id,
        )
    )
    anchor = result.scalar_one_or_none()
    if not anchor:
        raise HTTPException(status_code=404, detail="Anchor not found")
    if anchor.case_id != case_id:
        raise HTTPException(status_code=404, detail="Anchor not found")
    await db.delete(anchor)
    await _invalidate_calibration(db, media_id)
    await db.commit()


# ── Homography fit endpoint ───────────────────────────────────────────────────


@router.post("/fit", response_model=HomographyFitResponse, status_code=status.HTTP_201_CREATED)
async def fit_homography(
    case_id: str,
    media_id: str,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(current_user),
) -> HomographyFitResponse:
    """
    Fit a homography from all stored anchors for this media clip.

    Requires ≥ 4 anchors.  Per-anchor reprojection errors are stored back
    into the CalibrationAnchor rows.  If the anchors include a validated
    reference distance pair, scale is derived and stored.

    The previous active fit is marked is_active=False.
    """
    await _get_media_or_404(case_id, media_id, db)

    anchors_result = await db.execute(
        select(CalibrationAnchor)
        .where(CalibrationAnchor.media_id == media_id)
        .order_by(CalibrationAnchor.created_at)
    )
    anchors = list(anchors_result.scalars().all())

    if len(anchors) < 4:
        raise HTTPException(
            status_code=422,
            detail=f"At least 4 anchors are required to fit a homography; "
            f"currently {len(anchors)} anchor(s) placed.",
        )

    if (
        sum(a.known_distance_m is not None for a in anchors) > 1
        or sum(a.is_distance_ref_b for a in anchors) > 1
    ):
        raise HTTPException(status_code=422, detail="Choose exactly one distance reference pair")
    ref_a = next((a for a in anchors if a.known_distance_m is not None), None)
    ref_b = next((a for a in anchors if a.is_distance_ref_b), None)
    if (ref_a is None) != (ref_b is None) or (ref_a is not None and ref_a.id == ref_b.id):
        raise HTTPException(
            status_code=422, detail="Choose two distinct distance reference anchors"
        )

    pixel_pts = [PixelPoint(x=a.pixel_x, y=a.pixel_y) for a in anchors]
    world_pts = [WorldPoint(x=a.world_x, y=a.world_y) for a in anchors]

    try:
        hom = estimate_homography(pixel_pts, world_pts)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Per-anchor errors
    per_errors = reprojection_errors_px(hom, pixel_pts, world_pts)
    for anchor, err in zip(anchors, per_errors):
        anchor.reprojection_error_px = err

    # Scale derivation (optional)
    scale_mpp = scale_err = scale_src = None
    if ref_a and ref_b:
        try:
            scale = derive_scale(
                hom,
                PixelPoint(x=ref_a.pixel_x, y=ref_a.pixel_y),
                PixelPoint(x=ref_b.pixel_x, y=ref_b.pixel_y),
                ref_a.known_distance_m,  # type: ignore[arg-type]
            )
            scale_mpp = scale.metres_per_pixel
            scale_err = scale.relative_error
            scale_src = scale.source
        except ScaleUnavailable as exc:
            # Non-fatal: store without scale
            scale_src = f"unavailable:{exc.reason}"

    # Deactivate previous fits
    prev_result = await db.execute(
        select(HomographyFit).where(
            HomographyFit.media_id == media_id,
            HomographyFit.is_active == True,  # noqa: E712
        )
    )
    for old in prev_result.scalars().all():
        old.is_active = False

    fit_row = HomographyFit(
        id=str(uuid.uuid4()),
        media_id=media_id,
        case_id=case_id,
        anchor_count=hom.anchor_count,
        reprojection_rmse_px=hom.reprojection_rmse_px,
        condition_number=hom.condition_number,
        scale_metres_per_pixel=scale_mpp,
        scale_relative_error=scale_err,
        scale_source=scale_src,
        H_json=json.dumps(hom.H.tolist()),
        fitted_by=user,
        is_active=True,
    )
    db.add(fit_row)
    await db.commit()
    await db.refresh(fit_row)

    return HomographyFitResponse(
        id=fit_row.id,
        media_id=fit_row.media_id,
        anchor_count=fit_row.anchor_count,
        reprojection_rmse_px=fit_row.reprojection_rmse_px,
        condition_number=fit_row.condition_number,
        scale_metres_per_pixel=fit_row.scale_metres_per_pixel,
        scale_relative_error=fit_row.scale_relative_error,
        scale_source=fit_row.scale_source,
        H=json.loads(fit_row.H_json),
        fitted_at=fit_row.fitted_at,
        is_active=fit_row.is_active,
        per_anchor_errors_px=per_errors,
    )


@router.get("/fit", response_model=HomographyFitResponse | None)
async def get_active_fit(
    case_id: str,
    media_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(current_user),
) -> HomographyFitResponse | None:
    await _get_media_or_404(case_id, media_id, db)
    result = await db.execute(
        select(HomographyFit)
        .where(HomographyFit.media_id == media_id, HomographyFit.is_active == True)  # noqa: E712
        .order_by(HomographyFit.fitted_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if not row:
        return None
    return HomographyFitResponse(
        id=row.id,
        media_id=row.media_id,
        anchor_count=row.anchor_count,
        reprojection_rmse_px=row.reprojection_rmse_px,
        condition_number=row.condition_number,
        scale_metres_per_pixel=row.scale_metres_per_pixel,
        scale_relative_error=row.scale_relative_error,
        scale_source=row.scale_source,
        H=json.loads(row.H_json),
        fitted_at=row.fitted_at,
        is_active=row.is_active,
    )
