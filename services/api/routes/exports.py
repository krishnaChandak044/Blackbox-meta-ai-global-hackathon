"""Authenticated case export job creation and immutable downloads."""
from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.auth.session import current_user
from services.api.db.models import (
    AtlasConsent,
    AtlasConsentEvent,
    AtlasContribution,
    Case,
    ClaimCheck,
    CounterfactualRun,
    DynamicsRun,
    EvidenceNeed,
    ExportRecord,
    HomographyFit,
    JobStage,
    JobStatus,
    ObjectTrack,
    ProcessingJob,
    ProcessingLog,
    ReviewerAction,
    RivalSearch,
    SourceMedia,
    TrackPointRow,
    Transcript,
    TranscriptClaim,
)
from services.api.db.revision import case_revision_hash
from services.api.db.session import get_db

router = APIRouter(prefix="/cases/{case_id}/exports", tags=["exports"])


async def _revision_hash(case_id: str, db: AsyncSession) -> str:
    case = await db.get(Case, case_id)
    if case is None:
        raise HTTPException(404, "Case not found")
    def rows(model, where, order):
        return db.execute(select(model).where(where).order_by(order))
    media = (await rows(SourceMedia, SourceMedia.case_id == case_id, SourceMedia.id)).scalars().all()
    tracks = (await rows(ObjectTrack, ObjectTrack.case_id == case_id, ObjectTrack.id)).scalars().all()
    fits = (await rows(HomographyFit, HomographyFit.case_id == case_id, HomographyFit.id)).scalars().all()
    dynamics = (await rows(DynamicsRun, DynamicsRun.case_id == case_id, DynamicsRun.id)).scalars().all()
    cf = (await rows(CounterfactualRun, CounterfactualRun.case_id == case_id, CounterfactualRun.id)).scalars().all()
    rivals = (await rows(RivalSearch, RivalSearch.case_id == case_id, RivalSearch.id)).scalars().all()
    transcripts = (await rows(Transcript, Transcript.case_id == case_id, Transcript.id)).scalars().all()
    claims = (await rows(TranscriptClaim, TranscriptClaim.case_id == case_id, TranscriptClaim.id)).scalars().all()
    checks = (await rows(ClaimCheck, ClaimCheck.case_id == case_id, ClaimCheck.id)).scalars().all()
    needs = (await rows(EvidenceNeed, EvidenceNeed.case_id == case_id, EvidenceNeed.id)).scalars().all()
    actions = (await rows(ReviewerAction, ReviewerAction.case_id == case_id, ReviewerAction.id)).scalars().all()
    consent = (await db.execute(select(AtlasConsent).where(AtlasConsent.case_id == case_id))).scalar_one_or_none()
    atlas = (await rows(AtlasContribution, AtlasContribution.case_id == case_id, AtlasContribution.id)).scalars().all() if consent and consent.opted_in else []
    consent_events = (await rows(AtlasConsentEvent, AtlasConsentEvent.case_id == case_id, AtlasConsentEvent.id)).scalars().all()
    logs = (await db.execute(select(ProcessingLog).where(ProcessingLog.case_id == case_id)
                             .order_by(ProcessingLog.timestamp, ProcessingLog.id))).scalars().all()
    point_map = {}
    for track in tracks:
        pts = (await db.execute(select(TrackPointRow).where(TrackPointRow.track_id == track.id)
                                .order_by(TrackPointRow.frame_index))).scalars().all()
        point_map[track.id] = [{"frame": p.frame_index, "time": p.presentation_ts_s,
            "world": [p.world_x, p.world_y], "box": [p.bbox_x_min, p.bbox_y_min, p.bbox_x_max, p.bbox_y_max],
            "sigma": p.sigma_m, "pixel_sigma": p.pixel_localisation_sigma_m,
            "corrected": p.is_human_corrected, "interpolated": p.is_interpolated} for p in pts]
    def rows_data(records, fields):
        return [{name: getattr(row, name) for name in fields} for row in records]
    snapshot = {"case": {"id": case.id, "title": case.title, "description": case.description,
        "jurisdiction": case.jurisdiction, "incident_date": case.incident_date,
        "incident_location": case.incident_location, "status": case.status, "consent_given": case.consent_given,
        "updated_at": case.updated_at},
        "media": rows_data(media, ("id", "sha256", "byte_length", "status", "original_filename", "acquisition_notes")),
        "tracks": [{"id": t.id, "category": t.category, "confirmed": t.is_human_confirmed,
                    "points": point_map[t.id]} for t in tracks],
        "fits": rows_data(fits, ("id", "H_json", "reprojection_rmse_px", "scale_metres_per_pixel",
            "scale_relative_error", "is_active", "fitted_at")),
        "dynamics": rows_data(dynamics, ("id", "status", "params_json", "fitted_points_json", "uncertainty_json",
            "certificates_json", "fit_quality_json", "error_message")),
        "counterfactuals": rows_data(cf, ("id", "intervention_json", "simulated_points_json", "assumptions_json")),
        "rivals": rows_data(rivals, ("id", "manifest_json", "rivals_json")),
        "transcripts": rows_data(transcripts, ("id", "raw_text", "language", "is_synthetic")),
        "claims": rows_data(claims, ("id", "raw_text", "assertions_json", "source_ts_start", "source_ts_end")),
        "checks": rows_data(checks, ("id", "claim_id", "verdict", "evidence_json", "explanation", "evidence_frame_start", "evidence_frame_end")),
        "needs": rows_data(needs, ("id", "snapshot_json", "state", "verification_json", "draft_text")),
        "reviewer_actions": rows_data(actions, ("id", "target_type", "target_id", "action", "before_json", "after_json", "actor", "created_at")),
        "atlas_consent": rows_data([consent], ("id", "opted_in", "scope_version", "consented_at", "revoked_at")) if consent else [],
        "atlas_consent_events": rows_data(consent_events, ("id", "opted_in", "scope_version", "actor", "created_at")),
        "atlas_contributions": rows_data(atlas, ("id", "dedupe_key", "coarse_cell", "time_bucket", "metrics_json")),
        "processing_log": rows_data(logs, ("id", "stage", "tool_name", "input_hash", "output_hash", "parameters", "timestamp", "notes"))}
    return case_revision_hash(snapshot)


@router.post("", status_code=202)
async def create_export(case_id: str, db: AsyncSession = Depends(get_db),
                        user: str = Depends(current_user)) -> dict:
    case = await db.get(Case, case_id)
    if case is None:
        raise HTTPException(404, "Case not found")
    revision = await _revision_hash(case_id, db)
    record = ExportRecord(id=str(uuid.uuid4()), case_id=case_id, case_revision_hash=revision,
                          status="queued", created_by=user)
    job = ProcessingJob(id=str(uuid.uuid4()), case_id=case_id, media_id=None,
                        stage=JobStage.EXPORT, status=JobStatus.QUEUED)
    record.job_id = job.id
    db.add_all([record, job])
    await db.commit()
    try:
        from services.worker.jobs.export import build_case_export_task
        await asyncio.to_thread(build_case_export_task.delay, record.id, job.id)
    except Exception as exc:
        record.status = "failed"
        record.error_message = f"Could not enqueue export: {exc}"[:1000]
        job.status = JobStatus.FAILED
        job.error_message = record.error_message
        await db.commit()
        raise HTTPException(503, "Export worker unavailable") from exc
    return {"export_id": record.id, "job_id": job.id, "status": record.status,
            "case_revision_hash": revision}


@router.get("")
async def list_exports(case_id: str, db: AsyncSession = Depends(get_db),
                       _: str = Depends(current_user)) -> list[dict]:
    if await db.get(Case, case_id) is None:
        raise HTTPException(404, "Case not found")
    rows = (await db.execute(select(ExportRecord).where(ExportRecord.case_id == case_id)
                             .order_by(ExportRecord.created_at.desc()))).scalars().all()
    return [_response(row) for row in rows]


@router.get("/{export_id}")
async def get_export(case_id: str, export_id: str, db: AsyncSession = Depends(get_db),
                     _: str = Depends(current_user)) -> dict:
    row = await db.get(ExportRecord, export_id)
    if row is None or row.case_id != case_id:
        raise HTTPException(404, "Export not found")
    return _response(row)


@router.get("/{export_id}/files/{kind}")
async def download_export(case_id: str, export_id: str, kind: str,
                          db: AsyncSession = Depends(get_db),
                          _: str = Depends(current_user)) -> FileResponse:
    if kind not in {"pdf", "json"}:
        raise HTTPException(404, "Export file type not found")
    row = await db.get(ExportRecord, export_id)
    if row is None or row.case_id != case_id or row.status != "complete":
        raise HTTPException(404, "Completed export not found")
    path_text = row.pdf_path if kind == "pdf" else row.json_path
    expected = row.pdf_sha256 if kind == "pdf" else row.json_sha256
    if not path_text or not expected:
        raise HTTPException(404, "Export artifact unavailable")
    root = (Path(os.getenv("STORAGE_LOCAL_PATH", "./storage")) / "exports" / case_id / export_id).resolve()
    path = Path(path_text).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(404, "Export artifact unavailable")
    hasher = hashlib.sha256()
    with path.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    if digest != expected:
        raise HTTPException(409, "Export artifact integrity check failed")
    return FileResponse(path, media_type="application/pdf" if kind == "pdf" else "application/json",
                        filename=f"blackbox-{export_id}.{kind}")


def _response(row: ExportRecord) -> dict:
    return {"export_id": row.id, "case_id": row.case_id, "status": row.status, "job_id": row.job_id,
            "case_revision_hash": row.case_revision_hash, "manifest_sha256": row.manifest_sha256,
            "pdf_sha256": row.pdf_sha256, "json_sha256": row.json_sha256,
            "error_message": row.error_message, "created_at": row.created_at,
            "completed_at": row.completed_at}
