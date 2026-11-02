"""Reviewer tools: auditable clip offsets, frame annotations, and audio candidates."""
from __future__ import annotations

import asyncio
import json
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.auth.session import current_user
from services.api.db.models import Case, ReviewerAction, SourceMedia
from services.api.db.session import get_db
from services.worker.media.integrity import sha256_file

router = APIRouter(prefix="/cases/{case_id}/review-workspace", tags=["review-workspace"])


async def _verify_original(media: SourceMedia) -> None:
    try:
        current_hash = await asyncio.to_thread(sha256_file, Path(media.storage_path))
    except OSError as exc:
        raise HTTPException(409, "The original clip is unavailable; this review action was not saved") from exc
    if current_hash != media.sha256:
        raise HTTPException(409, "Original-byte hash mismatch. Restore the verified source before continuing.")


async def _case_media(case_id: str, db: AsyncSession) -> list[SourceMedia]:
    if await db.get(Case, case_id) is None:
        raise HTTPException(404, "Case not found")
    return list((await db.execute(select(SourceMedia).where(
        SourceMedia.case_id == case_id
    ).order_by(SourceMedia.upload_time, SourceMedia.id))).scalars().all())


def _latest_action_map(rows: list[ReviewerAction], action: str) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for row in rows:
        if row.action != action:
            continue
        try:
            payload = json.loads(row.after_json)
        except (TypeError, json.JSONDecodeError):
            continue
        old = latest.get(row.target_id)
        if old is None or (int(payload.get("version", 0)), payload.get("saved_at", payload.get("created_at", ""))) >= (
            int(old.get("version", 0)), old.get("saved_at", old.get("created_at", ""))
        ):
            latest[row.target_id] = payload
    return latest


@router.get("")
async def get_workspace(case_id: str, db: AsyncSession = Depends(get_db),
                        _: str = Depends(current_user)) -> dict:
    media = await _case_media(case_id, db)
    actions = list((await db.execute(select(ReviewerAction).where(
        ReviewerAction.case_id == case_id,
        ReviewerAction.target_type.in_(["media_sync", "frame_annotation", "acoustic_analysis"]),
    ).order_by(ReviewerAction.created_at, ReviewerAction.id))).scalars().all())
    syncs = _latest_action_map(actions, "save_media_sync")
    annotations: list[dict] = []
    acoustic: dict[str, dict] = {}
    for row in actions:
        try:
            payload = json.loads(row.after_json)
        except (TypeError, json.JSONDecodeError):
            continue
        if row.target_type == "frame_annotation" and row.action in {"create_annotation", "correct_annotation"}:
            annotations.append(payload)
        elif row.target_type == "acoustic_analysis" and row.action == "analyze_acoustics":
            if row.target_id not in acoustic or payload.get("created_at", "") >= acoustic[row.target_id].get("created_at", ""):
                acoustic[row.target_id] = payload
    return {
        "case_id": case_id,
        "media": [{"id": item.id, "filename": item.original_filename,
                   "sha256": item.sha256, "duration_seconds": item.duration_seconds,
                   "width": item.width, "height": item.height, "fps_nominal": item.fps_nominal,
                   "is_variable_framerate": item.is_variable_framerate, "frame_count": item.frame_count,
                   "has_audio": item.has_audio, "stream_url": f"/api/v1/cases/{case_id}/media/{item.id}/stream",
                   "sync": syncs.get(item.id)} for item in media],
        "annotations": annotations,
        "acoustic_analyses": list(acoustic.values()),
        "sync_semantics": "common_time_seconds = source_clip_time_seconds + offset_seconds; offsets are reviewer estimates, not automatic synchronization claims",
    }


class SyncUpdate(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    reference_media_id: str
    offset_seconds: float = Field(ge=-3600, le=3600)
    uncertainty_seconds: float = Field(ge=0, le=60)
    alignment_basis: str = Field(..., min_length=3, max_length=300)
    source_anchor_seconds: float | None = Field(None, ge=0)
    reference_anchor_seconds: float | None = Field(None, ge=0)


@router.put("/media/{media_id}/sync")
async def save_sync(case_id: str, media_id: str, payload: SyncUpdate,
                    db: AsyncSession = Depends(get_db), user: str = Depends(current_user)) -> dict:
    media = await _case_media(case_id, db)
    by_id = {item.id: item for item in media}
    target, reference = by_id.get(media_id), by_id.get(payload.reference_media_id)
    if target is None or reference is None:
        raise HTTPException(404, "Both clips must belong to this case")
    await _verify_original(target)
    if reference.id != target.id:
        await _verify_original(reference)
    if payload.source_anchor_seconds is not None and target.duration_seconds is not None and payload.source_anchor_seconds > target.duration_seconds:
        raise HTTPException(422, "Source anchor is outside the clip duration")
    if payload.reference_anchor_seconds is not None and reference.duration_seconds is not None and payload.reference_anchor_seconds > reference.duration_seconds:
        raise HTTPException(422, "Reference anchor is outside the clip duration")
    if (payload.source_anchor_seconds is None) != (payload.reference_anchor_seconds is None):
        raise HTTPException(422, "Provide both matching anchor times or neither")
    if payload.source_anchor_seconds is not None:
        computed = payload.reference_anchor_seconds - payload.source_anchor_seconds
        if abs(computed - payload.offset_seconds) > max(0.05, payload.uncertainty_seconds):
            raise HTTPException(422, "Offset does not agree with the two matching event times within the stated uncertainty")
    if media_id == payload.reference_media_id and abs(payload.offset_seconds) > 1e-9:
        raise HTTPException(422, "The reference clip offset must be zero")
    after = {
        "media_id": media_id, "reference_media_id": payload.reference_media_id,
        "offset_seconds": payload.offset_seconds, "uncertainty_seconds": payload.uncertainty_seconds,
        "alignment_basis": payload.alignment_basis.strip(),
        "source_anchor_seconds": payload.source_anchor_seconds,
        "reference_anchor_seconds": payload.reference_anchor_seconds,
        "source_sha256": target.sha256, "reference_sha256": reference.sha256,
        "version": 1, "saved_at": datetime.now(timezone.utc).isoformat(), "saved_by": user,
    }
    prior_rows = list((await db.execute(select(ReviewerAction).where(
        ReviewerAction.case_id == case_id, ReviewerAction.target_type == "media_sync",
        ReviewerAction.target_id == media_id,
    ).order_by(ReviewerAction.created_at.desc(), ReviewerAction.id.desc()))).scalars().all())
    parsed_prior = []
    for prior in prior_rows:
        try:
            parsed_prior.append((int(json.loads(prior.after_json).get("version", 0)), prior))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    previous_row = max(parsed_prior, key=lambda item: item[0])[1] if parsed_prior else None
    after["version"] = (max((version for version, _ in parsed_prior), default=0) + 1)
    db.add(ReviewerAction(id=str(uuid.uuid4()), case_id=case_id, target_type="media_sync",
                          target_id=media_id, action="save_media_sync",
                          before_json=previous_row.after_json if previous_row else None,
                          after_json=json.dumps(after, sort_keys=True), actor=user))
    await db.commit()
    return after


class AnnotationInput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    annotation_key: str | None = None
    media_id: str
    kind: str = Field(pattern="^(event|signal_state|stop_line|ground_contact|occlusion_boundary|road_condition|note)$")
    label: str = Field(..., min_length=1, max_length=120)
    note: str = Field("", max_length=2000)
    timestamp_seconds: float = Field(ge=0)
    frame_index: int = Field(ge=0)
    x_normalized: float | None = Field(None, ge=0, le=1)
    y_normalized: float | None = Field(None, ge=0, le=1)


@router.post("/annotations", status_code=201)
async def create_annotation(case_id: str, payload: AnnotationInput,
                            db: AsyncSession = Depends(get_db), user: str = Depends(current_user)) -> dict:
    media = await _case_media(case_id, db)
    source = next((item for item in media if item.id == payload.media_id), None)
    if source is None:
        raise HTTPException(404, "Media not found in this case")
    await _verify_original(source)
    if source.duration_seconds is not None and payload.timestamp_seconds > source.duration_seconds:
        raise HTTPException(422, "Annotation time is outside the clip")
    if source.frame_count is not None and payload.frame_index >= source.frame_count:
        raise HTTPException(422, "Frame index is outside the clip")
    if (payload.x_normalized is None) != (payload.y_normalized is None):
        raise HTTPException(422, "Image point needs both x and y coordinates")
    key = payload.annotation_key or str(uuid.uuid4())
    previous_rows = list((await db.execute(select(ReviewerAction).where(
        ReviewerAction.case_id == case_id, ReviewerAction.target_type == "frame_annotation",
        ReviewerAction.target_id == key,
    ).order_by(ReviewerAction.created_at.desc(), ReviewerAction.id.desc()))).scalars().all())
    version = 1
    previous = None
    prior_versions = []
    for prior in previous_rows:
        try:
            prior_versions.append((int(json.loads(prior.after_json).get("version", 0)), prior))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    previous_row = max(prior_versions, key=lambda item: item[0])[1] if prior_versions else None
    if previous_row:
        previous = json.loads(previous_row.after_json)
        version = max(value for value, _ in prior_versions) + 1
        if previous.get("media_id") != source.id:
            raise HTTPException(422, "A correction must stay linked to its original clip")
    record = {
        "annotation_key": key, "version": version, "previous_version": previous.get("version_id") if previous else None,
        "version_id": str(uuid.uuid4()), "media_id": source.id, "source_sha256": source.sha256,
        "kind": payload.kind, "label": payload.label.strip(), "note": payload.note.strip(),
        "timestamp_seconds": payload.timestamp_seconds, "frame_index": payload.frame_index,
        "frame_index_basis": "timestamp multiplied by nominal fps; approximate for variable-frame-rate footage" if source.is_variable_framerate else "timestamp multiplied by nominal fps; source timestamp is the primary locator",
        "x_normalized": payload.x_normalized, "y_normalized": payload.y_normalized,
        "created_at": datetime.now(timezone.utc).isoformat(), "created_by": user,
    }
    db.add(ReviewerAction(id=str(uuid.uuid4()), case_id=case_id, target_type="frame_annotation",
                          target_id=key, action="correct_annotation" if previous else "create_annotation",
                          before_json=previous_row.after_json if previous_row else None,
                          after_json=json.dumps(record, sort_keys=True), actor=user))
    await db.commit()
    return record


def _extract_audio_candidates(path: str, duration: float | None) -> tuple[list[dict], dict]:
    if duration is not None and duration > 1800:
        raise ValueError("Audio review is limited to clips of 30 minutes or less")
    result = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", "8000", "-f", "f32le", "pipe:1"],
        capture_output=True, timeout=120, check=False,
    )
    if result.returncode != 0:
        raise ValueError("Could not decode an audio track from this original clip")
    samples = np.frombuffer(result.stdout, dtype="<f4")
    if len(samples) < 800:
        return [], {"sample_rate_hz": 8000, "window_seconds": 0.08, "method": "windowed RMS transient screening"}
    samples = np.nan_to_num(samples, nan=0.0, posinf=0.0, neginf=0.0)
    window = 640  # 80 ms at 8 kHz
    usable = samples[: (len(samples) // window) * window].reshape(-1, window)
    rms = np.sqrt(np.mean(usable * usable, axis=1))
    baseline = float(np.median(rms))
    mad = float(np.median(np.abs(rms - baseline)))
    threshold = max(0.035, baseline + 8.0 * mad, baseline * 3.5)
    active = rms >= threshold
    groups: list[tuple[int, int]] = []
    start = None
    for index, is_active in enumerate(active):
        if is_active and start is None:
            start = index
        elif not is_active and start is not None:
            groups.append((start, index - 1)); start = None
    if start is not None:
        groups.append((start, len(active) - 1))
    merged: list[list[int]] = []
    for left, right in groups:
        if merged and left - merged[-1][1] <= 3:
            merged[-1][1] = right
        else:
            merged.append([left, right])
    peaks = []
    for left, right in merged:
        peak_index = left + int(np.argmax(rms[left:right + 1]))
        level = float(rms[peak_index])
        peaks.append({"timestamp_seconds": round(peak_index * 0.08, 3),
                      "duration_seconds": round((right - left + 1) * 0.08, 3),
                      "relative_level": round(level / max(baseline, 1e-6), 2),
                      "rms": round(level, 5), "label": "candidate acoustic transient",
                      "classification": "not classified"})
    return peaks, {"sample_rate_hz": 8000, "window_seconds": 0.08,
                   "median_rms": round(baseline, 6), "threshold_rms": round(threshold, 6),
                   "method": "Windowed RMS transient screening; not a horn, impact, or braking classifier."}


@router.post("/media/{media_id}/acoustic-candidates")
async def acoustic_candidates(case_id: str, media_id: str,
                              db: AsyncSession = Depends(get_db), user: str = Depends(current_user)) -> dict:
    media = await _case_media(case_id, db)
    source = next((item for item in media if item.id == media_id), None)
    if source is None:
        raise HTTPException(404, "Media not found in this case")
    await _verify_original(source)
    if not source.has_audio:
        raise HTTPException(422, "This clip has no audio track to review")
    try:
        events, method = await asyncio.to_thread(_extract_audio_candidates, source.storage_path, source.duration_seconds)
    except (ValueError, subprocess.TimeoutExpired, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc
    record = {"analysis_id": str(uuid.uuid4()), "media_id": source.id,
              "source_sha256": source.sha256, "events": events, "method": method,
              "created_at": datetime.now(timezone.utc).isoformat(), "created_by": user,
              "limitation": "Candidates are audio energy transients only. They are not identified as impact, horn, braking, or causal events; inspect the original audio and matching video."}
    db.add(ReviewerAction(id=str(uuid.uuid4()), case_id=case_id, target_type="acoustic_analysis",
                          target_id=source.id, action="analyze_acoustics",
                          after_json=json.dumps(record, sort_keys=True), actor=user))
    await db.commit()
    return record
