"""
services/worker/jobs/tracking.py
─────────────────────────────────
Celery task: run object tracking on a source media clip.

Execution order:
  1. Load the source file path from DB.
  2. Run the fixed-camera OpenCV motion tracker on decoded source frames.
  3. Run tracking.
  4. Load the active HomographyFit for this media (if any).
  5. Project each TrackPoint to world coordinates via ground_contact.project_track.
  6. Persist ObjectTrack + TrackPointRow records.
  7. Append a ProcessingLog entry.

The task is idempotent: re-running it deletes old tracks for this media first.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.geometry.homography import HomographyResult
from engine.geometry.scale import ScaleResult
from engine.tracking.ground_contact import project_track
from engine.tracking.motion import MotionTracker
from engine.tracking.protocols import Track
from services.api.db.models import (
    HomographyFit,
    JobStatus,
    ObjectTrack,
    ProcessingJob,
    ProcessingLog,
    SourceMedia,
    TrackPointRow,
)
from services.worker.celery_app import app as celery_app
from services.worker.db import get_sync_session

logger = logging.getLogger(__name__)

TRACKER_VERSION = "0.2.0"


@celery_app.task(
    bind=True,
    name="blackbox.tracking.run_tracking",
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
)
def run_tracking_task(self, media_id: str, job_id: str) -> dict:
    """
    Run tracking for one source media clip.

    Returns a summary dict with track_count and whether world projection
    was available.
    """
    with get_sync_session() as db:
        job = db.get(ProcessingJob, job_id)
        if job is None:
            logger.error("tracking.job_not_found", extra={"job_id": job_id})
            return {"error": "job_not_found"}

        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        job.celery_task_id = self.request.id
        db.commit()

        try:
            result = _run(db, media_id, job)
            job.status = JobStatus.DONE
            job.progress = 100
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
            return result
        except Exception as exc:
            logger.exception("tracking.task_failed", extra={"media_id": media_id})
            db.rollback()
            job = db.get(ProcessingJob, job_id)
            job.status = JobStatus.FAILED
            job.error_message = str(exc)[:1000]
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
            raise self.retry(exc=exc) from exc


def _run(db: Session, media_id: str, job: ProcessingJob) -> dict:
    # ── 1. Load source media ───────────────────────────────────────────────────
    media = db.get(SourceMedia, media_id)
    if media is None:
        raise RuntimeError(f"SourceMedia {media_id!r} not found")

    video_path = media.storage_path
    if not Path(video_path).exists():
        raise FileNotFoundError(f"Video file missing: {video_path}")

    # ── 2. Choose tracker ─────────────────────────────────────────────────────
    tracker = MotionTracker()

    # ── 3. Run tracking ───────────────────────────────────────────────────────
    job.progress = 10
    db.commit()
    tracks: list[Track] = tracker.track(video_path, min_confidence=0.4)
    logger.info("tracking.raw_tracks", extra={"media_id": media_id, "n": len(tracks)})

    # ── 4. Load active homography ─────────────────────────────────────────────
    job.progress = 60
    db.commit()
    hom_result, scale_result = _load_homography(db, media_id)

    # ── 5. Clear old tracks for this media ───────────────────────────────────
    existing = (
        db.execute(select(ObjectTrack).where(ObjectTrack.media_id == media_id)).scalars().all()
    )
    for ot in existing:
        db.delete(ot)
    db.flush()

    # ── 6. Project & persist ──────────────────────────────────────────────────
    for raw_track in tracks:
        ground_traj = (
            project_track(raw_track, hom_result, scale_result)
            if hom_result is not None and scale_result is not None
            else None
        )

        # Build world lookup for fast access
        world_by_frame: dict[int, tuple[float, float, float]] = {}
        if ground_traj:
            for gp in ground_traj.positions:
                world_by_frame[gp.frame_index] = (gp.world.x, gp.world.y, gp.sigma_m)

        ot = ObjectTrack(
            id=str(uuid.uuid4()),
            media_id=media_id,
            case_id=media.case_id,
            tracker_track_id=raw_track.track_id,
            category=raw_track.points[0].label.category if raw_track.points else "unknown",
            tracker_model=raw_track.points[0].label.source_model if raw_track.points else "unknown",
            first_frame=raw_track.points[0].frame_index if raw_track.points else 0,
            last_frame=raw_track.points[-1].frame_index if raw_track.points else 0,
            point_count=len(raw_track.points),
            is_complete=raw_track.is_complete,
        )
        db.add(ot)
        db.flush()  # get ot.id

        for tp in raw_track.points:
            gx, gy = tp.bbox.ground_contact_px
            wx, wy, sig = world_by_frame.get(tp.frame_index, (None, None, None))
            db.add(
                TrackPointRow(
                    track_id=ot.id,
                    frame_index=tp.frame_index,
                    presentation_ts_s=tp.presentation_ts_s,
                    bbox_x_min=tp.bbox.x_min,
                    bbox_y_min=tp.bbox.y_min,
                    bbox_x_max=tp.bbox.x_max,
                    bbox_y_max=tp.bbox.y_max,
                    gc_pixel_x=gx,
                    gc_pixel_y=gy,
                    world_x=wx,
                    world_y=wy,
                    sigma_m=sig,
                    detection_confidence=tp.detection_confidence,
                    is_interpolated=tp.is_interpolated,
                    is_human_corrected=tp.is_human_corrected,
                )
            )

    # ── 7. Append audit log ───────────────────────────────────────────────────
    db.add(
        ProcessingLog(
            case_id=media.case_id,
            media_id=media_id,
            stage="track",
            tool_name=MotionTracker.MODEL_NAME,
            tool_version=TRACKER_VERSION,
            operator="system",
            notes=(
                f"{len(tracks)} tracks produced. "
                f"Metric projection: {'yes' if scale_result else 'no (validated scale unavailable)'}."
            ),
        )
    )

    job.progress = 95
    db.commit()

    return {
        "track_count": len(tracks),
        "world_projection": scale_result is not None,
        "scale_available": scale_result is not None,
    }


def _load_homography(
    db: Session, media_id: str
) -> tuple[HomographyResult | None, ScaleResult | None]:
    """Load the active HomographyFit and reconstruct engine objects."""
    row: HomographyFit | None = db.execute(
        select(HomographyFit)
        .where(HomographyFit.media_id == media_id, HomographyFit.is_active == True)  # noqa: E712
        .order_by(HomographyFit.fitted_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    if row is None:
        return None, None

    H = np.array(json.loads(row.H_json), dtype=np.float64)
    hom = HomographyResult(
        H=H,
        reprojection_rmse_px=row.reprojection_rmse_px,
        condition_number=row.condition_number,
        anchor_count=row.anchor_count,
    )

    scale: ScaleResult | None = None
    if row.scale_metres_per_pixel is not None:
        scale = ScaleResult(
            metres_per_pixel=row.scale_metres_per_pixel,
            reference_distance_m=0.0,  # stored separately; not needed post-fit
            measured_distance_m=0.0,
            relative_error=row.scale_relative_error or 0.0,
            source=row.scale_source or "stored",
        )

    return hom, scale
