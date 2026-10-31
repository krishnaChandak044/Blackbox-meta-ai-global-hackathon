"""
Media upload router — source-preserving intake with SHA-256 integrity.

Every byte of the original is stored untouched. SHA-256 is computed
server-side as the stream lands. A probe job is queued immediately.
"""

import hashlib
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.db.session import get_db
from services.api.db.models import (
    Case, SourceMedia, ProcessingJob, ProcessingLog,
    MediaStatus, JobStatus, JobStage,
)
from services.api.schemas.media import SourceMediaResponse, IntegrityCheckResponse

router = APIRouter(prefix="/cases/{case_id}/media", tags=["media"])

STORAGE_ROOT = Path(os.getenv("STORAGE_LOCAL_PATH", "./storage"))
ALLOWED_MIMES = {"video/mp4", "video/quicktime", "video/x-msvideo", "video/webm"}
MAX_CLIPS = int(os.getenv("MAX_CLIPS_PER_CASE", 3))
MAX_SIZE_BYTES = int(os.getenv("MAX_UPLOAD_SIZE_MB", 500)) * 1024 * 1024


def _case_storage(case_id: str) -> Path:
    p = STORAGE_ROOT / "originals" / case_id
    p.mkdir(parents=True, exist_ok=True)
    return p


async def _get_case_or_404(case_id: str, db: AsyncSession) -> Case:
    result = await db.execute(select(Case).where(Case.id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@router.post("/", response_model=SourceMediaResponse, status_code=status.HTTP_201_CREATED)
async def upload_media(
    case_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> SourceMediaResponse:
    """
    Upload a video clip.

    Original bytes are stored unchanged. SHA-256 is computed server-side
    during streaming write (no double read). A probe job is queued.
    """
    await _get_case_or_404(case_id, db)

    # Check clip limit
    count_result = await db.execute(
        select(SourceMedia).where(SourceMedia.case_id == case_id)
    )
    existing = count_result.scalars().all()
    if len(existing) >= MAX_CLIPS:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_CLIPS} clips per case. Remove one to add another.",
        )

    # Validate MIME
    if file.content_type not in ALLOWED_MIMES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported media type '{file.content_type}'. Accepted: MP4, MOV, AVI, WebM.",
        )

    media_id = str(uuid.uuid4())
    storage_dir = _case_storage(case_id)
    ext = Path(file.filename or "upload").suffix or ".mp4"
    dest_path = storage_dir / f"{media_id}{ext}"

    # Stream to disk + compute SHA-256 in a single pass
    hasher = hashlib.sha256()
    total_bytes = 0
    chunk_size = 1024 * 1024  # 1 MB chunks

    with open(dest_path, "wb") as f:
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > MAX_SIZE_BYTES:
                dest_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds {os.getenv('MAX_UPLOAD_SIZE_MB', 500)} MB limit.",
                )
            hasher.update(chunk)
            f.write(chunk)

    sha256_hex = hasher.hexdigest()

    # Persist source media record
    media = SourceMedia(
        id=media_id,
        case_id=case_id,
        original_filename=file.filename or "upload",
        mime_type=file.content_type,
        byte_length=total_bytes,
        sha256=sha256_hex,
        storage_path=str(dest_path),
        status=MediaStatus.STORED,
    )
    db.add(media)

    # Queue probe job
    job = ProcessingJob(
        id=str(uuid.uuid4()),
        case_id=case_id,
        media_id=media_id,
        stage=JobStage.PROBE,
        status=JobStatus.QUEUED,
    )
    db.add(job)

    # Append to processing log
    log = ProcessingLog(
        case_id=case_id,
        media_id=media_id,
        stage="intake",
        tool_name="blackbox-intake",
        tool_version="0.1.0",
        input_hash=sha256_hex,
        output_hash=sha256_hex,
        operator="system",
        notes=f"Original upload stored. {total_bytes} bytes. SHA-256 computed during stream.",
    )
    db.add(log)

    await db.commit()
    await db.refresh(media)
    return SourceMediaResponse.model_validate(media)


@router.get("/", response_model=list[SourceMediaResponse])
async def list_media(case_id: str, db: AsyncSession = Depends(get_db)) -> list[SourceMediaResponse]:
    await _get_case_or_404(case_id, db)
    result = await db.execute(
        select(SourceMedia).where(SourceMedia.case_id == case_id).order_by(SourceMedia.upload_time)
    )
    return [SourceMediaResponse.model_validate(m) for m in result.scalars().all()]


@router.get("/{media_id}", response_model=SourceMediaResponse)
async def get_media(case_id: str, media_id: str, db: AsyncSession = Depends(get_db)) -> SourceMediaResponse:
    result = await db.execute(
        select(SourceMedia).where(SourceMedia.id == media_id, SourceMedia.case_id == case_id)
    )
    media = result.scalar_one_or_none()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    return SourceMediaResponse.model_validate(media)


@router.get("/{media_id}/integrity", response_model=IntegrityCheckResponse)
async def verify_integrity(
    case_id: str, media_id: str, db: AsyncSession = Depends(get_db)
) -> IntegrityCheckResponse:
    """
    Re-compute SHA-256 of the stored original and compare to the recorded hash.
    A mismatch means the file has been altered since upload — hard failure.
    """
    result = await db.execute(
        select(SourceMedia).where(SourceMedia.id == media_id, SourceMedia.case_id == case_id)
    )
    media = result.scalar_one_or_none()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    path = Path(media.storage_path)
    if not path.exists():
        raise HTTPException(status_code=500, detail="Stored file not found on disk.")

    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    verified = hasher.hexdigest()

    return IntegrityCheckResponse(
        media_id=media_id,
        original_sha256=media.sha256,
        verified_sha256=verified,
        intact=verified == media.sha256,
        checked_at=datetime.now(timezone.utc),
    )


@router.delete("/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_media(case_id: str, media_id: str, db: AsyncSession = Depends(get_db)) -> None:
    result = await db.execute(
        select(SourceMedia).where(SourceMedia.id == media_id, SourceMedia.case_id == case_id)
    )
    media = result.scalar_one_or_none()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    Path(media.storage_path).unlink(missing_ok=True)
    await db.delete(media)
    await db.commit()
