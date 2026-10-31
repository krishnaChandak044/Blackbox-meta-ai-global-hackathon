"""
services/worker/jobs/transcription.py

Transcription worker task.

Adapter priority:
  1. MuseVoiceAdapter — uses real API (MUSE_VOICE_API_KEY + MUSE_VOICE_API_URL)
  2. SyntheticTranscriptAdapter — ONLY if ENABLE_SYNTHETIC_TRANSCRIPT=true

If no adapter succeeds, the job FAILS with a clear error message.
Synthetic transcripts are marked is_synthetic=True in the DB.
Claims extracted from synthetic transcripts are blocked in the extractor route.

Race fix: Celery task is dispatched AFTER db.commit() completes, not before.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.api.db.models import (
    JobStage,
    JobStatus,
    ProcessingJob,
    ProcessingLog,
    SourceMedia,
    Transcript,
)
from services.worker.adapters.muse_voice_adapter import AdapterUnavailable, MuseVoiceAdapter
from services.worker.celery_app import app as celery_app
from services.worker.db import get_sync_session

logger = logging.getLogger(__name__)

_ENABLE_SYNTHETIC = os.getenv("ENABLE_SYNTHETIC_TRANSCRIPT", "false").lower() == "true"


@celery_app.task(
    bind=True,
    name="blackbox.transcribe_media",
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
)
def transcribe_media_task(self, media_id: str, job_id: str) -> dict:
    with get_sync_session() as db:
        job = db.get(ProcessingJob, job_id)
        if job is None:
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
            # ── Dispatch claim extraction AFTER commit (no race condition) ────
            _dispatch_extraction(db, result["transcript_id"], media_id, job)
            return result
        except Exception as exc:
            logger.exception("transcribe.task_failed", extra={"media_id": media_id})
            db.rollback()
            job = db.get(ProcessingJob, job_id)
            if job:
                job.status = JobStatus.FAILED
                job.error_message = str(exc)[:1000]
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
            raise self.retry(exc=exc) from exc


def _run(db: Session, media_id: str, job: ProcessingJob) -> dict:
    media = db.get(SourceMedia, media_id)
    if media is None:
        raise RuntimeError(f"SourceMedia {media_id!r} not found")

    transcript_result = None
    used_adapter = "unknown"

    # ── Attempt 1: Muse Voice (real API) ─────────────────────────────────────
    try:
        adapter = MuseVoiceAdapter()
        transcript_result = adapter.transcribe(media.storage_path)
        used_adapter = adapter.TRANSCRIPTION_MODEL
        logger.info("transcribe.muse_voice_success", extra={"media_id": media_id})
    except AdapterUnavailable as e:
        logger.info("transcribe.muse_voice_unavailable", extra={"reason": str(e)})
    except Exception as e:
        logger.warning("transcribe.muse_voice_error", extra={"error": str(e)})

    # ── Attempt 2: Synthetic placeholder (only if explicitly enabled) ─────────
    if transcript_result is None:
        if _ENABLE_SYNTHETIC:
            from services.worker.adapters.synthetic_transcript_adapter import SyntheticTranscriptAdapter
            synth = SyntheticTranscriptAdapter()
            transcript_result = synth.transcribe(
                media.storage_path,
                media_id=media_id,
                duration_seconds=media.duration_seconds or 10.0,
            )
            used_adapter = synth.TRANSCRIPTION_MODEL
            logger.warning(
                "transcribe.using_synthetic_placeholder",
                extra={"media_id": media_id, "model": used_adapter},
            )
        else:
            raise RuntimeError(
                "No transcription service is configured. "
                "Set MUSE_VOICE_API_KEY + MUSE_VOICE_API_URL, "
                "or set ENABLE_SYNTHETIC_TRANSCRIPT=true for demo mode."
            )

    raw_text = transcript_result.raw_text or ""
    diarised = transcript_result.diarised_segments or []
    language = transcript_result.language or "en"
    duration = transcript_result.duration_seconds or media.duration_seconds
    word_count = len(raw_text.split()) if raw_text else 0
    speaker_count = len({s.get("speaker", "unknown") for s in diarised}) if diarised else 1

    tr = Transcript(
        id=str(uuid.uuid4()),
        case_id=media.case_id,
        media_id=media_id,
        speaker_count=speaker_count,
        language=language,
        raw_text=raw_text,
        diarised_json=json.dumps(diarised) if diarised else None,
        transcription_model=transcript_result.transcription_model,
        word_count=word_count,
        duration_seconds=duration,
        is_synthetic=transcript_result.is_synthetic,
        created_by="system",
    )
    db.add(tr)
    db.add(ProcessingLog(
        case_id=media.case_id,
        media_id=media_id,
        stage="transcribe",
        tool_name=used_adapter,
        tool_version="0.1.0",
        operator="system",
        notes=(
            f"Transcript {tr.id}: {word_count} words, {speaker_count} speakers."
            + (" [SYNTHETIC PLACEHOLDER]" if tr.is_synthetic else "")
        ),
    ))
    db.flush()   # get tr.id without committing
    # Caller commits — extraction is dispatched only after that commit returns
    return {
        "transcript_id": tr.id,
        "word_count": word_count,
        "model": used_adapter,
        "is_synthetic": tr.is_synthetic,
    }


def _dispatch_extraction(db: Session, transcript_id: str, media_id: str, parent_job: ProcessingJob) -> None:
    """
    Dispatch claim extraction as a new job.
    Called AFTER the transcription db.commit() — no race condition.
    """
    try:
        from services.worker.jobs.claim_extraction import extract_claims_task

        extract_job = ProcessingJob(
            id=str(uuid.uuid4()),
            case_id=parent_job.case_id,
            media_id=media_id,
            stage=JobStage.CLAIM_CHECK,
            status=JobStatus.QUEUED,
        )
        db.add(extract_job)
        db.commit()

        extract_claims_task.delay(transcript_id, extract_job.id)
        logger.info("transcribe.dispatched_extraction", extra={"transcript_id": transcript_id, "job_id": extract_job.id})
    except Exception as e:
        # Extraction failure must not fail the transcription job
        logger.warning("transcribe.extraction_dispatch_failed", extra={"error": str(e)})
