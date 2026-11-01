"""Asynchronous, immutable PDF + JSON export job."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

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
from services.worker.celery_app import app as celery_app
from services.worker.db import get_sync_session
from services.worker.exports.json_manifest import canonical_json, seal_manifest
from services.worker.exports.pdf_report import render_pdf


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _row_dict(row, fields: tuple[str, ...]) -> dict:
    return {key: getattr(row, key) for key in fields}


@celery_app.task(bind=True, name="blackbox.build_case_export", acks_late=True, max_retries=1)
def build_case_export_task(self, export_id: str, job_id: str) -> dict:
    with get_sync_session() as db:
        record = db.get(ExportRecord, export_id)
        job = db.get(ProcessingJob, job_id)
        if record is None or job is None:
            return {"error": "export_or_job_not_found"}
        if record.status == "complete":
            return {"status": "already_complete", "export_id": export_id}
        record.status = "running"
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        job.celery_task_id = self.request.id
        db.commit()
        try:
            result = _build(db, record)
            record.status = "complete"
            record.completed_at = datetime.now(timezone.utc)
            job.status = JobStatus.DONE
            job.progress = 100
            job.completed_at = datetime.now(timezone.utc)
            db.add(ProcessingLog(case_id=record.case_id, stage="export", tool_name="blackbox-review-package",
                tool_version="1.0.0", operator=f"user:{record.created_by}", input_hash=record.case_revision_hash,
                output_hash=record.manifest_sha256, notes=f"Export {export_id} completed; PDF and JSON hashes recorded."))
            db.commit()
            return result
        except Exception as exc:
            db.rollback()
            record = db.get(ExportRecord, export_id)
            job = db.get(ProcessingJob, job_id)
            if record:
                record.status = "failed"
                record.error_message = str(exc)[:2000]
                record.completed_at = datetime.now(timezone.utc)
            if job:
                job.status = JobStatus.FAILED
                job.error_message = str(exc)[:2000]
                job.completed_at = datetime.now(timezone.utc)
            db.commit()
            raise


def _build(db, record: ExportRecord) -> dict:
    case = db.get(Case, record.case_id)
    if case is None:
        raise ValueError("Case was deleted before export generation")
    media_rows = db.execute(select(SourceMedia).where(SourceMedia.case_id == case.id).order_by(SourceMedia.id)).scalars().all()
    media = []
    for row in media_rows:
        path = Path(row.storage_path)
        if not path.is_file():
            raise ValueError(f"Original media is unavailable: {row.id}")
        actual_hash = _sha256_file(path)
        intact = actual_hash == row.sha256
        if not intact:
            raise ValueError(f"Original integrity check failed for media {row.id}")
        media.append({**_row_dict(row, ("id", "original_filename", "mime_type", "byte_length", "sha256", "status",
            "upload_time", "codec", "container", "duration_seconds", "frame_count", "fps_nominal",
            "is_variable_framerate", "width", "height", "has_audio", "device_clock_metadata", "acquisition_notes")),
            "integrity": "verified_at_export", "verified_sha256": actual_hash,
            "original_included": False, "source_reference": "retained in case storage; not embedded in this package"})

    tracks = db.execute(select(ObjectTrack).where(ObjectTrack.case_id == case.id).order_by(ObjectTrack.id)).scalars().all()
    track_data = []
    for track in tracks:
        pts = db.execute(select(TrackPointRow).where(TrackPointRow.track_id == track.id)
                         .order_by(TrackPointRow.frame_index)).scalars().all()
        track_data.append({"track": _row_dict(track, ("id", "media_id", "tracker_track_id", "category", "tracker_model",
            "first_frame", "last_frame", "point_count", "is_complete", "is_human_confirmed", "human_confirmed_by", "human_confirmed_at")),
            "observations": [_row_dict(p, ("frame_index", "presentation_ts_s", "bbox_x_min", "bbox_y_min", "bbox_x_max",
                "bbox_y_max", "gc_pixel_x", "gc_pixel_y", "world_x", "world_y", "sigma_m",
                "pixel_localisation_sigma_m", "detection_confidence", "is_interpolated", "is_human_corrected")) for p in pts]})

    fits = db.execute(select(HomographyFit).where(HomographyFit.case_id == case.id).order_by(HomographyFit.id)).scalars().all()
    dynamics = db.execute(select(DynamicsRun).where(DynamicsRun.case_id == case.id).order_by(DynamicsRun.id)).scalars().all()
    counterfactuals = db.execute(select(CounterfactualRun).where(CounterfactualRun.case_id == case.id).order_by(CounterfactualRun.id)).scalars().all()
    rivals = db.execute(select(RivalSearch).where(RivalSearch.case_id == case.id).order_by(RivalSearch.id)).scalars().all()
    transcripts = db.execute(select(Transcript).where(Transcript.case_id == case.id).order_by(Transcript.id)).scalars().all()
    claims = db.execute(select(TranscriptClaim).where(TranscriptClaim.case_id == case.id).order_by(TranscriptClaim.id)).scalars().all()
    checks = db.execute(select(ClaimCheck).where(ClaimCheck.case_id == case.id).order_by(ClaimCheck.id)).scalars().all()
    needs = db.execute(select(EvidenceNeed).where(EvidenceNeed.case_id == case.id).order_by(EvidenceNeed.id)).scalars().all()
    consent = db.execute(select(AtlasConsent).where(AtlasConsent.case_id == case.id)).scalar_one_or_none()
    atlas = db.execute(select(AtlasContribution).where(AtlasContribution.case_id == case.id)).scalars().all() if consent and consent.opted_in else []
    logs = db.execute(select(ProcessingLog).where(ProcessingLog.case_id == case.id).order_by(ProcessingLog.timestamp, ProcessingLog.id)).scalars().all()
    reviewer_actions = db.execute(select(ReviewerAction).where(ReviewerAction.case_id == case.id).order_by(ReviewerAction.id)).scalars().all()
    consent_events = db.execute(select(AtlasConsentEvent).where(AtlasConsentEvent.case_id == case.id).order_by(AtlasConsentEvent.id)).scalars().all()

    revision_snapshot = {
        "case": {"id": case.id, "title": case.title, "description": case.description,
            "jurisdiction": case.jurisdiction, "incident_date": case.incident_date,
            "incident_location": case.incident_location, "status": case.status,
            "consent_given": case.consent_given, "updated_at": case.updated_at},
        "media": [{"id": r.id, "sha256": r.sha256, "byte_length": r.byte_length,
            "status": r.status, "original_filename": r.original_filename, "acquisition_notes": r.acquisition_notes} for r in media_rows],
        "tracks": [{"id": track.id, "category": track.category, "confirmed": track.is_human_confirmed,
            "points": [{"frame": p.frame_index, "time": p.presentation_ts_s,
                "world": [p.world_x, p.world_y], "box": [p.bbox_x_min, p.bbox_y_min, p.bbox_x_max, p.bbox_y_max],
                "sigma": p.sigma_m, "pixel_sigma": p.pixel_localisation_sigma_m,
                "corrected": p.is_human_corrected, "interpolated": p.is_interpolated} for p in
                db.execute(select(TrackPointRow).where(TrackPointRow.track_id == track.id).order_by(TrackPointRow.frame_index)).scalars().all()]}
            for track in tracks],
        "fits": [{"id": r.id, "H_json": r.H_json, "reprojection_rmse_px": r.reprojection_rmse_px,
            "scale_metres_per_pixel": r.scale_metres_per_pixel, "scale_relative_error": r.scale_relative_error,
            "is_active": r.is_active, "fitted_at": r.fitted_at} for r in fits],
        "dynamics": [{"id": r.id, "status": r.status, "params_json": r.params_json,
            "fitted_points_json": r.fitted_points_json, "uncertainty_json": r.uncertainty_json,
            "certificates_json": r.certificates_json, "fit_quality_json": r.fit_quality_json,
            "error_message": r.error_message} for r in dynamics],
        "counterfactuals": [{"id": r.id, "intervention_json": r.intervention_json,
            "simulated_points_json": r.simulated_points_json, "assumptions_json": r.assumptions_json} for r in counterfactuals],
        "rivals": [{"id": r.id, "manifest_json": r.manifest_json, "rivals_json": r.rivals_json} for r in rivals],
        "transcripts": [{"id": r.id, "raw_text": r.raw_text, "language": r.language,
            "is_synthetic": r.is_synthetic} for r in transcripts],
        "claims": [{"id": r.id, "raw_text": r.raw_text, "assertions_json": r.assertions_json,
            "source_ts_start": r.source_ts_start, "source_ts_end": r.source_ts_end} for r in claims],
        "checks": [{"id": r.id, "claim_id": r.claim_id, "verdict": r.verdict, "evidence_json": r.evidence_json,
            "explanation": r.explanation, "evidence_frame_start": r.evidence_frame_start,
            "evidence_frame_end": r.evidence_frame_end} for r in checks],
        "needs": [{"id": r.id, "snapshot_json": r.snapshot_json, "state": r.state,
            "verification_json": r.verification_json, "draft_text": r.draft_text} for r in needs],
        "reviewer_actions": [{"id": r.id, "target_type": r.target_type, "target_id": r.target_id,
            "action": r.action, "before_json": r.before_json, "after_json": r.after_json,
            "actor": r.actor, "created_at": r.created_at} for r in reviewer_actions],
        "atlas_consent": ([{"id": consent.id, "opted_in": consent.opted_in,
            "scope_version": consent.scope_version, "consented_at": consent.consented_at,
            "revoked_at": consent.revoked_at}] if consent else []),
        "atlas_consent_events": [{"id": r.id, "opted_in": r.opted_in, "scope_version": r.scope_version,
            "actor": r.actor, "created_at": r.created_at} for r in consent_events],
        "atlas_contributions": [{"id": r.id, "dedupe_key": r.dedupe_key, "coarse_cell": r.coarse_cell,
            "time_bucket": r.time_bucket, "metrics_json": r.metrics_json} for r in atlas],
        "processing_log": [{"id": r.id, "stage": r.stage, "tool_name": r.tool_name,
            "input_hash": r.input_hash, "output_hash": r.output_hash, "parameters": r.parameters,
            "timestamp": r.timestamp, "notes": r.notes} for r in logs],
    }

    media_frame_counts = {item["id"]: item.get("frame_count") for item in media}
    claim_checks = {c.claim_id: c for c in checks}
    claim_records = []
    citation_warnings = []
    for claim in claims:
        check = claim_checks.get(claim.id)
        citation = None
        if check:
            citation = {"media_id": claim.media_id, "frame_start": check.evidence_frame_start,
                        "frame_end": check.evidence_frame_end}
            frame_count = media_frame_counts.get(claim.media_id)
            if frame_count is not None and any(f is not None and not 0 <= f < frame_count
                                                for f in (check.evidence_frame_start, check.evidence_frame_end)):
                citation_warnings.append(f"Claim {claim.id} has a frame citation outside indexed media bounds")
        claim_records.append({"claim": _row_dict(claim, ("id", "transcript_id", "media_id", "speaker", "raw_text",
            "assertions_json", "extraction_confidence", "source_ts_start", "source_ts_end", "created_at")),
            "finding": _row_dict(check, ("verdict", "confidence", "evidence_frame_start", "evidence_frame_end", "evidence_json",
                                         "explanation", "homography_fit_id", "checked_at", "checked_by")) if check else None,
            "frame_citation": citation})

    manifest = {
        "schema": "blackbox.review-export", "schema_version": "1.0.0", "export_id": record.id,
        "generated_at": datetime.now(timezone.utc).isoformat(), "case_revision_hash": record.case_revision_hash,
        "case": _row_dict(case, ("id", "title", "description", "jurisdiction", "incident_date", "incident_location", "status", "consent_given", "created_at", "updated_at")),
        "media": media, "calibration_fits": [_row_dict(r, ("id", "media_id", "anchor_count", "reprojection_rmse_px", "condition_number",
            "scale_metres_per_pixel", "scale_relative_error", "scale_source", "H_json", "fitted_at", "fitted_by", "is_active")) for r in fits],
        "tracks": track_data,
        "dynamics_runs": [_row_dict(r, ("id", "media_id", "track_id", "track_version_hash", "calibration_fit_id", "media_sha256",
            "model_name", "model_version", "software_revision", "seed", "params_json", "status", "fitted_points_json",
            "uncertainty_json", "certificates_json", "fit_quality_json", "braking_onset_json", "entry_speed_kmh",
            "entry_speed_lo_kmh", "entry_speed_hi_kmh", "mean_decel_ms2", "mean_decel_lo_ms2", "mean_decel_hi_ms2", "interval_type", "error_message")) for r in dynamics],
        "counterfactuals": [_row_dict(r, ("id", "media_id", "baseline_run_id", "intervention_json", "simulated_points_json",
            "sensitivity_json", "stopping_distance_m", "stopping_time_s", "extrapolation_outside_support", "assumptions_json", "illustrative_label")) for r in counterfactuals],
        "rival_searches": [_row_dict(r, ("id", "media_id", "primary_run_id", "manifest_json", "rivals_json", "empty_search_message",
            "second_view_used", "second_view_notes")) for r in rivals],
        "transcripts": [_row_dict(r, ("id", "media_id", "speaker_count", "language", "raw_text", "diarised_json", "transcription_model",
            "word_count", "duration_seconds", "is_synthetic", "created_at", "created_by")) for r in transcripts],
        "claims": claim_records,
        "evidence_needs": [{"id": n.id, "need_key": n.need_key, "snapshot_json": n.snapshot_json,
                            "state": n.state, "verification_json": n.verification_json,
                            "draft_text": n.draft_text} for n in needs],
        "reviewer_actions": [{"id": r.id, "target_type": r.target_type, "target_id": r.target_id,
            "action": r.action, "before_json": r.before_json, "after_json": r.after_json,
            "actor": r.actor, "created_at": r.created_at} for r in reviewer_actions],
        "atlas_consent_events": [{"opted_in": r.opted_in, "scope_version": r.scope_version,
            "actor": r.actor, "created_at": r.created_at} for r in consent_events],
        "atlas": {"included": bool(consent and consent.opted_in),
                  "contributions": [{"coarse_cell": r.coarse_cell, "time_bucket": r.time_bucket,
                      "conflict_type": r.conflict_type, "road_user_mix_json": r.road_user_mix_json,
                      "metrics_json": r.metrics_json, "provenance_json": r.provenance_json} for r in atlas]},
        "processing_history": [_row_dict(r, ("media_id", "stage", "tool_name", "tool_version", "input_hash", "output_hash",
            "parameters", "operator", "timestamp", "notes")) for r in logs],
        "limitations": ["This package is a review aid, not a legal fault determination.",
            "Illustrative ranges have not established empirical confidence coverage.",
            "Generated 3D scene assets and simulated paths are illustrative, not source footage.",
            "Original media is referenced by verified hash and retained separately; it is not embedded."],
        "citation_warnings": citation_warnings,
        "provenance_classes": {"OBSERVED": len(media) + sum(len(x["observations"]) for x in track_data),
            "MEASURED": len(fits) + len(dynamics), "ASSUMED": sum(len(json.loads(r.params_json or "{}")) for r in dynamics),
            "SIMULATED": len(counterfactuals) + len(rivals), "UNKNOWN": len(citation_warnings)},
    }
    manifest, manifest_hash = seal_manifest(manifest)
    # Refuse a stale request snapshot if the source/media set changed during generation.
    revision = case_revision_hash(revision_snapshot)
    if revision != record.case_revision_hash:
        raise ValueError("Case inputs changed after export was queued; create a fresh export snapshot")
    out_dir = Path(os.getenv("STORAGE_LOCAL_PATH", "./storage")) / "exports" / case.id / record.id
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path, pdf_path = out_dir / "manifest.json", out_dir / "review.pdf"
    json_bytes = canonical_json(manifest)
    json_path.write_bytes(json_bytes)
    render_pdf(manifest, pdf_path)
    record.manifest_sha256 = manifest_hash
    record.json_sha256 = hashlib.sha256(json_bytes).hexdigest()
    record.pdf_sha256 = _sha256_file(pdf_path)
    record.json_path, record.pdf_path = str(json_path), str(pdf_path)
    return {"export_id": record.id, "manifest_sha256": record.manifest_sha256,
            "json_sha256": record.json_sha256, "pdf_sha256": record.pdf_sha256}
