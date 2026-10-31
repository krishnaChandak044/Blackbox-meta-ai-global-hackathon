"""
services/worker/jobs/dynamics.py
──────────────────────────────────
Celery task: run piecewise-constant-acceleration inference.

Contract:
- Dispatched only AFTER db.commit() (no race condition).
- Snapshots all input IDs and versions before running.
- Marks DynamicsRun stale (status=stale) when track/calibration/media changes.
- Stores immutable result JSON — never overwrites a completed run.
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import uuid
from dataclasses import asdict
from datetime import datetime, timezone

from sqlalchemy import select

from engine.dynamics.inference import run_inference, InferenceRejected
from services.api.db.models import (
    DynamicsRun, HomographyFit, JobStatus, ObjectTrack,
    ProcessingJob, ProcessingLog, SourceMedia, TrackPointRow,
)
from services.worker.celery_app import app as celery_app
from services.worker.db import get_sync_session

logger = logging.getLogger(__name__)


def _git_revision() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "unknown"


def _hash_track_version(points: list) -> str:
    blob = json.dumps(
        [{"fi": p.frame_index, "x": p.world_x, "y": p.world_y, "ts": p.presentation_ts_s,
          "sigma": p.pixel_localisation_sigma_m}
         for p in points],
        sort_keys=True, separators=(",", ":"),
    ).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


@celery_app.task(
    bind=True,
    name="blackbox.run_dynamics",
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
)
def run_dynamics_task(self, dynamics_run_id: str, job_id: str) -> dict:
    with get_sync_session() as db:
        job = db.get(ProcessingJob, job_id)
        if job is None:
            return {"error": "job_not_found"}
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        job.celery_task_id = self.request.id
        db.commit()

        try:
            result = _run(db, dynamics_run_id)
            job.status = JobStatus.DONE
            job.progress = 100
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
            return result
        except Exception as exc:
            logger.exception("dynamics.task_failed", extra={"dynamics_run_id": dynamics_run_id})
            db.rollback()
            job = db.get(ProcessingJob, job_id)
            if job:
                job.status = JobStatus.FAILED
                job.error_message = str(exc)[:1000]
                job.completed_at = datetime.now(timezone.utc)
                db.commit()

            # Mark dynamics run failed too
            try:
                with get_sync_session() as db2:
                    dr = db2.get(DynamicsRun, dynamics_run_id)
                    if dr and dr.status != "stale":
                        dr.status = "failed"
                        dr.error_message = str(exc)[:1000]
                        dr.completed_at = datetime.now(timezone.utc)
                        db2.commit()
            except Exception:
                pass

            raise self.retry(exc=exc) from exc


def _run(db, dynamics_run_id: str) -> dict:
    dr = db.get(DynamicsRun, dynamics_run_id)
    if dr is None:
        raise RuntimeError(f"DynamicsRun {dynamics_run_id!r} not found")

    if dr.status == "done":
        logger.info("dynamics.already_done", extra={"dynamics_run_id": dynamics_run_id})
        return {"status": "already_done", "run_id": dynamics_run_id}

    # ── Load track observations ───────────────────────────────────────────────
    track = db.get(ObjectTrack, dr.track_id)
    if track is None:
        raise RuntimeError(f"Track {dr.track_id!r} not found")
    if not track.is_human_confirmed:
        raise InferenceRejected("track_unconfirmed: a reviewer must confirm the vehicle track first")

    points_q = (
        db.execute(
            select(TrackPointRow)
            .where(TrackPointRow.track_id == dr.track_id)
            .order_by(TrackPointRow.presentation_ts_s)
        )
        .scalars()
        .all()
    )

    if not points_q:
        raise InferenceRejected(f"track_empty: track {dr.track_id!r} has no points")

    # Build observation dicts
    observations = [
        {
            "frame_index": p.frame_index,
            "presentation_ts_s": p.presentation_ts_s,
            "world_x_m": p.world_x,
            "world_y_m": p.world_y,
            "localisation_sigma_m": p.pixel_localisation_sigma_m,
        }
        for p in points_q
    ]

    # Validate version hash matches what was recorded at job creation
    actual_hash = _hash_track_version(points_q)
    if actual_hash != dr.track_version_hash:
        dr.status = "stale"
        dr.error_message = (
            f"Track version mismatch: expected {dr.track_version_hash!r}, "
            f"got {actual_hash!r}. Re-queue the dynamics job."
        )
        db.commit()
        raise RuntimeError(dr.error_message)

    # ── Load calibration ──────────────────────────────────────────────────────
    hf = db.get(HomographyFit, dr.calibration_fit_id)
    if hf is None or not hf.is_active:
        raise InferenceRejected(f"calibration_stale: active HomographyFit {dr.calibration_fit_id!r} not found")

    calibration = {
        "metres_per_pixel": hf.scale_metres_per_pixel,
        "homography_rmse_px": hf.reprojection_rmse_px,
        "scale_relative_error": hf.scale_relative_error,
        "homography_fit_id": hf.id,
    }

    # ── Load VFR metadata ─────────────────────────────────────────────────────
    media = db.get(SourceMedia, dr.media_id)
    vfr_meta = {
        "has_vfr": bool(media.is_variable_framerate),
        "pts_available": all(p.presentation_ts_s is not None for p in points_q),
        "mean_frame_duration_s": 1.0 / max(media.fps_nominal or 25.0, 1.0),
        # Phase 1 frame index stores ffprobe PTS rounded to microseconds.
        # This is only quantization precision; camera clock accuracy remains an
        # explicit limitation in the uncertainty report.
        "frame_duration_sigma_s": 0.0000005,
        "timestamp_metadata": "ffprobe best_effort_timestamp_time rounded to 1 microsecond; camera clock error unknown",
    }

    params = json.loads(dr.params_json)

    # ── Run inference ─────────────────────────────────────────────────────────
    result = run_inference(
        observations=observations,
        calibration=calibration,
        vfr_meta=vfr_meta,
        params=params,
        track_id=dr.track_id,
        track_version_hash=dr.track_version_hash,
        media_sha256=dr.media_sha256,
        software_revision=dr.software_revision,
        seed=dr.seed,
    )

    # ── Persist results ───────────────────────────────────────────────────────
    dr.status = "done"
    dr.fitted_points_json = json.dumps([asdict(fp) for fp in result.fitted_points])
    dr.uncertainty_json = json.dumps(asdict(result.uncertainty))
    dr.certificates_json = json.dumps({k: asdict(v) for k, v in result.certificates.items()})
    dr.fit_quality_json = json.dumps(asdict(result.fit_quality))
    dr.braking_onset_json = json.dumps(asdict(result.braking_onset)) if result.braking_onset else None
    dr.entry_speed_kmh = result.entry_speed_kmh
    dr.entry_speed_lo_kmh = result.entry_speed_lo_kmh
    dr.entry_speed_hi_kmh = result.entry_speed_hi_kmh
    dr.mean_decel_ms2 = result.mean_decel_ms2
    dr.mean_decel_lo_ms2 = result.mean_decel_lo_ms2
    dr.mean_decel_hi_ms2 = result.mean_decel_hi_ms2
    dr.interval_type = result.interval_type
    dr.completed_at = datetime.now(timezone.utc)

    db.add(ProcessingLog(
        case_id=dr.case_id,
        media_id=dr.media_id,
        stage="dynamics",
        tool_name="piecewise_const_accel_2d",
        tool_version=result.model_version,
        operator="system",
        notes=(
            f"Dynamics run {dynamics_run_id}: "
            f"entry_speed={result.entry_speed_kmh:.1f} km/h "
            f"[{result.entry_speed_lo_kmh if result.entry_speed_lo_kmh is not None else '?'}, "
            f"{result.entry_speed_hi_kmh if result.entry_speed_hi_kmh is not None else '?'}] "
            f"interval_type={result.interval_type}"
        ),
    ))
    db.commit()

    return {
        "run_id": dynamics_run_id,
        "entry_speed_kmh": result.entry_speed_kmh,
        "interval_type": result.interval_type,
    }
