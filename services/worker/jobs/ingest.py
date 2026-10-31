"""Probe and index a newly stored original."""

import asyncio
import os
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from services.api.db.models import (
    DerivedArtifact,
    JobStatus,
    MediaStatus,
    ProcessingJob,
    ProcessingLog,
    SourceMedia,
)
from services.worker.celery_app import app
from services.worker.media.frame_index import build_frame_index
from services.worker.media.integrity import sha256_file
from services.worker.media.probe import probe_media


async def process_media(media_id: str, job_id: str) -> None:
    engine = create_async_engine(os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./blackbox.db"))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as db:
            media = await db.get(SourceMedia, media_id)
            job = await db.get(ProcessingJob, job_id)
            if media is None or job is None:
                raise ValueError("Media or job was deleted")
            job.status = JobStatus.RUNNING
            media.status = MediaStatus.PROBING
            await db.commit()
            try:
                source = Path(media.storage_path)
                if sha256_file(source) != media.sha256:
                    raise ValueError("Original media hash mismatch before processing")
                metadata = await asyncio.to_thread(probe_media, source)
                index_path = (
                    source.parent.parent.parent
                    / "derived"
                    / media.case_id
                    / f"{media.id}-frames.json"
                )
                index_meta = await asyncio.to_thread(build_frame_index, source, index_path)
                index_hash = sha256_file(index_path)
                for key, value in {**metadata, **index_meta}.items():
                    setattr(media, key, value)
                media.status = MediaStatus.INDEXED
                job.status = JobStatus.DONE
                job.progress = 100
                db.add(
                    DerivedArtifact(
                        id=str(uuid.uuid4()),
                        source_media_id=media.id,
                        artifact_type="frame_index",
                        storage_path=str(index_path),
                        sha256=index_hash,
                        tool_name="ffprobe",
                        tool_version="runtime",
                        parameters='{"unit":"microseconds"}',
                    )
                )
                db.add(
                    ProcessingLog(
                        case_id=media.case_id,
                        media_id=media.id,
                        stage="probe-and-frame-index",
                        tool_name="ffprobe",
                        tool_version="runtime",
                        input_hash=media.sha256,
                        output_hash=index_hash,
                        parameters='{"unit":"microseconds"}',
                        operator="system",
                        notes=f"Indexed {index_meta['frame_count']} frames from presentation timestamps.",
                    )
                )
            except Exception as exc:
                media.status = MediaStatus.FAILED
                job.status = JobStatus.FAILED
                job.error_message = str(exc)[:1000]
                raise
            finally:
                await db.commit()
    finally:
        await engine.dispose()


@app.task(name="blackbox.probe_media")
def probe_media_task(media_id: str, job_id: str) -> None:
    asyncio.run(process_media(media_id, job_id))
