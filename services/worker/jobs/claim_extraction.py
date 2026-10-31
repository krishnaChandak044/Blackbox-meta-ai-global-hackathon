"""
services/worker/jobs/claim_extraction.py

Claim extraction worker task.

Key changes from original:
- Blocks extraction on synthetic transcripts (is_synthetic=True) — they must
  never produce claim records that could be mistaken for real witness statements.
- Uses extract_claims_from_segments (with real ASR timestamps) when diarised
  segments are available, otherwise falls back to extract_claims (timestamps 0.0).
- Idempotent: deletes old claims for this transcript before re-extracting.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from engine.claims.extractor import extract_claims, extract_claims_from_segments
from services.api.db.models import JobStatus, ProcessingJob, ProcessingLog, Transcript, TranscriptClaim
from services.worker.celery_app import app as celery_app
from services.worker.db import get_sync_session

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="blackbox.extract_claims",
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
)
def extract_claims_task(self, transcript_id: str, job_id: str) -> dict:
    with get_sync_session() as db:
        job = db.get(ProcessingJob, job_id)
        if job is None:
            return {"error": "job_not_found"}
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        job.celery_task_id = self.request.id
        db.commit()
        try:
            result = _run(db, transcript_id, job)
            job.status = JobStatus.DONE
            job.progress = 100
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
            return result
        except Exception as exc:
            logger.exception("extract_claims.task_failed", extra={"transcript_id": transcript_id})
            db.rollback()
            job = db.get(ProcessingJob, job_id)
            if job:
                job.status = JobStatus.FAILED
                job.error_message = str(exc)[:1000]
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
            raise self.retry(exc=exc) from exc


def _run(db, transcript_id: str, job: ProcessingJob) -> dict:
    tr = db.get(Transcript, transcript_id)
    if tr is None:
        raise RuntimeError(f"Transcript {transcript_id!r} not found")

    # ── Safety gate: never extract claims from synthetic transcripts ──────────
    if getattr(tr, "is_synthetic", False):
        logger.warning(
            "extract_claims.blocked_synthetic",
            extra={"transcript_id": transcript_id},
        )
        db.add(ProcessingLog(
            case_id=tr.case_id,
            media_id=tr.media_id,
            stage="claim_check",
            tool_name="claim-extractor-v1",
            tool_version="0.2.0",
            operator="system",
            notes=(
                f"Claim extraction BLOCKED for transcript {transcript_id}: "
                "transcript is synthetic (is_synthetic=True). "
                "No claims were created — synthetic text must not be treated as witness evidence."
            ),
        ))
        db.commit()
        return {"claim_count": 0, "transcript_id": transcript_id, "blocked": "synthetic"}

    # ── Idempotent: delete old claims for this transcript first ───────────────
    existing = db.execute(
        select(TranscriptClaim).where(TranscriptClaim.transcript_id == transcript_id)
    ).scalars().all()
    for old in existing:
        db.delete(old)
    db.flush()

    # ── Use segment timestamps when available (preferred) ─────────────────────
    claims = []
    if tr.diarised_json:
        try:
            segments = json.loads(tr.diarised_json)
            if isinstance(segments, list) and segments:
                claims = extract_claims_from_segments(
                    segments,
                    tr.case_id,
                    tr.id,
                    media_id=tr.media_id,
                )
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("extract_claims.segment_parse_failed", extra={"error": str(e)})

    # Fallback to plain text (timestamps 0.0 = unknown)
    if not claims:
        claims = extract_claims(
            tr.raw_text or "",
            tr.case_id,
            tr.id,
            media_id=tr.media_id,
        )

    # ── Persist claims ────────────────────────────────────────────────────────
    for claim in claims:
        ts_start = claim.assertions[0].source_ts_start if claim.assertions else 0.0
        ts_end = claim.assertions[0].source_ts_end if claim.assertions else 0.0
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
            for a in claim.assertions
        ]
        row = TranscriptClaim(
            id=claim.id,
            transcript_id=tr.id,
            case_id=tr.case_id,
            media_id=claim.media_id,
            speaker=claim.speaker,
            raw_text=claim.raw_text,
            assertions_json=json.dumps(assertions_data),
            extraction_confidence=claim.confidence,
            source_ts_start=ts_start,
            source_ts_end=ts_end,
            created_by="system",
        )
        db.add(row)

    db.add(ProcessingLog(
        case_id=tr.case_id,
        media_id=tr.media_id,
        stage="claim_check",
        tool_name="claim-extractor-v1",
        tool_version="0.2.0",
        operator="system",
        notes=f"Extracted {len(claims)} claims from transcript {transcript_id}.",
    ))
    db.commit()
    return {"claim_count": len(claims), "transcript_id": transcript_id}
