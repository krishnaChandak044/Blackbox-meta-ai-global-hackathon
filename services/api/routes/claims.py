"""Claims router - part 1."""
from __future__ import annotations
import asyncio, json, uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from services.api.auth.session import current_user
from services.api.db.models import Case, ClaimCheck, HomographyFit, JobStage, JobStatus, ObjectTrack, ProcessingJob, SourceMedia, TrackPointRow, Transcript, TranscriptClaim
from services.api.db.session import get_db
from services.api.schemas.claim import ClaimCheckResponse, TranscriptClaimResponse, TranscriptClaimUpdate

router = APIRouter(prefix="/cases/{case_id}/claims", tags=["claims"])
async def _get_case_or_404(case_id: str, db: AsyncSession) -> Case:
    result = await db.execute(select(Case).where(Case.id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case
def _claim_to_response(row: TranscriptClaim) -> TranscriptClaimResponse:
    try:
        assertions = json.loads(row.assertions_json) if row.assertions_json else []
    except Exception:
        assertions = []
    return TranscriptClaimResponse(id=row.id, transcript_id=row.transcript_id, case_id=row.case_id, media_id=row.media_id, speaker=row.speaker, raw_text=row.raw_text, assertions=assertions, extraction_confidence=row.extraction_confidence, source_ts_start=row.source_ts_start, source_ts_end=row.source_ts_end, created_at=row.created_at, created_by=row.created_by)
@router.get("/", response_model=list[TranscriptClaimResponse])
async def list_claims(case_id: str, db: AsyncSession = Depends(get_db), _: str = Depends(current_user)) -> list[TranscriptClaimResponse]:
    await _get_case_or_404(case_id, db)
    result = await db.execute(select(TranscriptClaim).where(TranscriptClaim.case_id == case_id).order_by(TranscriptClaim.created_at.desc()))
    return [_claim_to_response(r) for r in result.scalars().all()]
@router.get("/{claim_id}", response_model=TranscriptClaimResponse)
async def get_claim(case_id: str, claim_id: str, db: AsyncSession = Depends(get_db), _: str = Depends(current_user)) -> TranscriptClaimResponse:
    await _get_case_or_404(case_id, db)
    result = await db.execute(select(TranscriptClaim).where(TranscriptClaim.id == claim_id, TranscriptClaim.case_id == case_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Claim not found")
    return _claim_to_response(row)
@router.post("/extract/{transcript_id}", status_code=status.HTTP_202_ACCEPTED)
async def extract_claims_for_transcript(case_id: str, transcript_id: str, db: AsyncSession = Depends(get_db), user: str = Depends(current_user)) -> dict:
    await _get_case_or_404(case_id, db)
    result = await db.execute(select(Transcript).where(Transcript.id == transcript_id, Transcript.case_id == case_id))
    tr = result.scalar_one_or_none()
    if not tr:
        raise HTTPException(status_code=404, detail="Transcript not found")
    job = ProcessingJob(id=str(uuid.uuid4()), case_id=case_id, media_id=tr.media_id, stage=JobStage.CLAIM_CHECK, status=JobStatus.QUEUED)
    db.add(job)
    await db.commit()
    try:
        from services.worker.jobs.claim_extraction import extract_claims_task
        await asyncio.to_thread(extract_claims_task.delay, transcript_id, job.id)
    except Exception as exc:
        job.status = JobStatus.FAILED
        job.error_message = f"Could not enqueue extraction: {exc}"[:1000]
        await db.commit()
        raise HTTPException(status_code=503, detail="Extraction queue unavailable") from exc
    return {"job_id": job.id, "status": "queued"}


@router.post("/{claim_id}/check", response_model=ClaimCheckResponse)
async def check_claim(case_id: str, claim_id: str, db: AsyncSession = Depends(get_db), user: str = Depends(current_user)) -> ClaimCheckResponse:
    await _get_case_or_404(case_id, db)
    r1 = await db.execute(select(TranscriptClaim).where(TranscriptClaim.id == claim_id, TranscriptClaim.case_id == case_id))
    cr = r1.scalar_one_or_none()
    if not cr:
        raise HTTPException(status_code=404, detail="Claim not found")
    mid = cr.media_id
    trks: list[ObjectTrack] = []
    hid = None
    hr = None
    sr = None
    if mid:
        trks = list((await db.execute(select(ObjectTrack).where(ObjectTrack.media_id == mid))).scalars().all())
        qr = await db.execute(select(HomographyFit).where(HomographyFit.media_id == mid, HomographyFit.is_active == True).order_by(HomographyFit.fitted_at.desc()).limit(1))  # noqa: E712
        hom = qr.scalar_one_or_none()
        if hom:
            hid = hom.id
            try:
                import numpy as np
                from engine.geometry.homography import HomographyResult as HR
                from engine.geometry.scale import ScaleResult as SR

                H = np.array(json.loads(hom.H_json), dtype=np.float64)
                hr = HR(H=H, reprojection_rmse_px=hom.reprojection_rmse_px, condition_number=hom.condition_number, anchor_count=hom.anchor_count)
                if hom.scale_metres_per_pixel is not None:
                    sr = SR(metres_per_pixel=hom.scale_metres_per_pixel, reference_distance_m=0, measured_distance_m=0, relative_error=hom.scale_relative_error or 0, source=hom.scale_source or "stored")
            except Exception:
                pass
    from engine.claims.checker import check_claim as eng_check
    from engine.claims.models import Claim as EC, ClaimAssertion as EA, TrackDetailLite, TrackPointLite

    try:
        ad = json.loads(cr.assertions_json) if cr.assertions_json else []
    except Exception:
        ad = []
    assr: list[EA] = []
    for a in ad:
        try:
            assr.append(EA(assertion_type=a["assertion_type"], subject=a.get("subject", "unknown"), value=a.get("value"), unit=a.get("unit"), qualifier=a.get("qualifier"), raw_text=a.get("raw_text", ""), source_ts_start=a.get("source_ts_start", 0), source_ts_end=a.get("source_ts_end", 0)))
        except Exception:
            continue
    co = EC(id=cr.id, case_id=cr.case_id, media_id=cr.media_id, transcript_id=cr.transcript_id, speaker=cr.speaker, assertions=assr, raw_text=cr.raw_text, confidence=cr.extraction_confidence)
    tds: list[TrackDetailLite] = []
    for ot in trks:
        pr = await db.execute(select(TrackPointRow).where(TrackPointRow.track_id == ot.id).order_by(TrackPointRow.frame_index))
        pts = pr.scalars().all()
        lpts = [TrackPointLite(frame_index=p.frame_index, presentation_ts_s=p.presentation_ts_s, world_x=p.world_x, world_y=p.world_y, bbox_x_min=p.bbox_x_min, bbox_y_min=p.bbox_y_min, bbox_x_max=p.bbox_x_max, bbox_y_max=p.bbox_y_max) for p in pts]
        tds.append(TrackDetailLite(id=ot.id, points=lpts))
    v = eng_check(co, tds, hr, sr)
    ej = json.dumps({"world_positions": v.evidence_world_positions, "frame_range": [v.evidence_frame_start, v.evidence_frame_end]}) if v.evidence_world_positions else None
    row = ClaimCheck(id=str(uuid.uuid4()), claim_id=cr.id, case_id=case_id, verdict=v.verdict, confidence=v.confidence, evidence_frame_start=v.evidence_frame_start, evidence_frame_end=v.evidence_frame_end, evidence_json=ej, explanation=v.explanation, homography_fit_id=hid, checked_by=user)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return ClaimCheckResponse.model_validate(row)


@router.get("/{claim_id}/check", response_model=ClaimCheckResponse | None)
async def get_latest_check(case_id: str, claim_id: str, db: AsyncSession = Depends(get_db), _: str = Depends(current_user)) -> ClaimCheckResponse | None:
    await _get_case_or_404(case_id, db)
    rr = await db.execute(select(TranscriptClaim).where(TranscriptClaim.id == claim_id, TranscriptClaim.case_id == case_id))
    if not rr.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Claim not found")
    r2 = await db.execute(select(ClaimCheck).where(ClaimCheck.claim_id == claim_id).order_by(ClaimCheck.checked_at.desc()).limit(1))
    row = r2.scalar_one_or_none()
    if not row:
        return None
    return ClaimCheckResponse.model_validate(row)


@router.patch("/{claim_id}", response_model=TranscriptClaimResponse)
async def patch_claim(
    case_id: str,
    claim_id: str,
    payload: TranscriptClaimUpdate,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(current_user),
) -> TranscriptClaimResponse:
    """
    Patch a claim.

    If raw_text is updated:
    - Assertions are re-extracted immediately from the new text.
    - All prior ClaimCheck verdicts for this claim are invalidated (verdict set to
      'stale_edit') so the UI can prompt the user to re-run the check.
    - An edit history entry is appended to edit_history_json.
    """
    await _get_case_or_404(case_id, db)
    rr = await db.execute(
        select(TranscriptClaim).where(
            TranscriptClaim.id == claim_id, TranscriptClaim.case_id == case_id
        )
    )
    row = rr.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Claim not found")

    updates = payload.model_dump(exclude_unset=True)
    now = datetime.now(timezone.utc)

    # Track edit history
    history: list[dict] = []
    try:
        history = json.loads(row.edit_history_json) if row.edit_history_json else []
    except Exception:
        history = []

    text_changed = "raw_text" in updates and updates["raw_text"] != row.raw_text

    for k, vv in updates.items():
        old_val = getattr(row, k, None)
        if old_val != vv:
            history.append({
                "ts": now.isoformat(),
                "field": k,
                "old": str(old_val)[:200] if old_val is not None else None,
                "new": str(vv)[:200] if vv is not None else None,
                "by": user,
            })
        setattr(row, k, vv)

    row.edit_history_json = json.dumps(history)

    if text_changed:
        # Re-extract assertions from the new text
        from engine.claims.extractor import extract_claims as eng_extract
        new_claims = eng_extract(
            row.raw_text,
            row.case_id,
            row.transcript_id,
            media_id=row.media_id,
            speaker=row.speaker,
        )
        if new_claims:
            assertions_data = [
                {
                    "assertion_type": a.assertion_type,
                    "subject": a.subject,
                    "value": a.value,
                    "unit": a.unit,
                    "qualifier": a.qualifier,
                    "raw_text": a.raw_text,
                    "source_ts_start": a.source_ts_start,
                    "source_ts_end": a.source_ts_end,
                }
                for extracted in new_claims
                for a in extracted.assertions
            ]
            row.assertions_json = json.dumps(assertions_data)
            row.extraction_confidence = max(c.confidence for c in new_claims)
            # Claim assertion timestamps came from ASR segments; retain their
            # bounds when only the displayed claim text is edited.
        else:
            row.assertions_json = "[]"
            row.extraction_confidence = 0.0

        row.assertions_edited_at = now

    if "speaker" in updates and updates["speaker"] is not None:
        # Keep assertion subject labels separate; the claim-level speaker is the
        # diarisation/editor attribution, not an inferred vehicle identity.
        row.speaker = updates["speaker"]

    if updates:
        # Any material edit changes attribution/context and invalidates checks.
        stale_checks = (
            await db.execute(select(ClaimCheck).where(ClaimCheck.claim_id == claim_id))
        ).scalars().all()
        for check in stale_checks:
            check.verdict = "stale_edit"
            check.explanation = (
                f"[INVALIDATED] Claim edited at {now.isoformat()} by {user}. "
                "Re-run the check to get a fresh verdict."
            )
        row.verdict_invalidated_at = now


    await db.commit()
    await db.refresh(row)
    return _claim_to_response(row)


@router.delete("/{claim_id}", status_code=204)
async def delete_claim(case_id: str, claim_id: str, db: AsyncSession = Depends(get_db), _: str = Depends(current_user)) -> None:
    await _get_case_or_404(case_id, db)
    rr = await db.execute(select(TranscriptClaim).where(TranscriptClaim.id == claim_id, TranscriptClaim.case_id == case_id))
    row = rr.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Claim not found")
    await db.delete(row)
    await db.commit()
