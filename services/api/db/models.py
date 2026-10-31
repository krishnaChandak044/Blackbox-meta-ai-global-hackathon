"""
SQLAlchemy models for Phase 1 — Evidence Foundation.

Every entity that touches original media has a SHA-256 hash and an immutable
original_path. Derived artifacts carry a parent_id. Nothing overwrites originals.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ── Enums ─────────────────────────────────────────────────────────────────────


class CaseStatus(str, enum.Enum):
    DRAFT = "draft"
    PROCESSING = "processing"
    READY = "ready"
    EXPORTED = "exported"


class MediaStatus(str, enum.Enum):
    UPLOADING = "uploading"
    STORED = "stored"
    PROBING = "probing"
    INDEXED = "indexed"
    FAILED = "failed"


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    RETRYING = "retrying"


class JobStage(str, enum.Enum):
    PROBE = "probe"
    FRAME_INDEX = "frame_index"
    INTEGRITY = "integrity"
    TRACK = "track"
    CALIBRATE = "calibrate"
    TRANSCRIBE = "transcribe"
    CLAIM_CHECK = "claim_check"
    DYNAMICS = "dynamics"
    COUNTERFACTUAL = "counterfactual"
    EXPORT = "export"


# ── Case ──────────────────────────────────────────────────────────────────────


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    jurisdiction: Mapped[str | None] = mapped_column(String(100))
    incident_date: Mapped[datetime | None] = mapped_column(DateTime)
    incident_location: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[CaseStatus] = mapped_column(Enum(CaseStatus), default=CaseStatus.DRAFT)
    consent_given: Mapped[bool] = mapped_column(Boolean, default=False)
    owner_id: Mapped[str] = mapped_column(String(36))  # auth placeholder
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    media: Mapped[list["SourceMedia"]] = relationship(
        "SourceMedia", back_populates="case", cascade="all, delete-orphan"
    )
    jobs: Mapped[list["ProcessingJob"]] = relationship(
        "ProcessingJob", back_populates="case", cascade="all, delete-orphan"
    )
    processing_log: Mapped[list["ProcessingLog"]] = relationship(
        "ProcessingLog", back_populates="case", cascade="all, delete-orphan"
    )


# ── Source Media ──────────────────────────────────────────────────────────────


class SourceMedia(Base):
    """
    Immutable record of an original uploaded file.

    The original bytes NEVER change after upload. sha256 is computed server-side
    and must match on every re-download. derived_from_id is NULL for originals.
    """

    __tablename__ = "source_media"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"))
    original_filename: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(100))
    byte_length: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))  # hex digest
    storage_path: Mapped[str] = mapped_column(String(1000))  # server-side path
    status: Mapped[MediaStatus] = mapped_column(Enum(MediaStatus), default=MediaStatus.UPLOADING)
    upload_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Media metadata (populated after probe job)
    codec: Mapped[str | None] = mapped_column(String(50))
    container: Mapped[str | None] = mapped_column(String(50))
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    frame_count: Mapped[int | None] = mapped_column(Integer)
    fps_nominal: Mapped[float | None] = mapped_column(Float)
    is_variable_framerate: Mapped[bool | None] = mapped_column(Boolean)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    has_audio: Mapped[bool | None] = mapped_column(Boolean)
    device_clock_metadata: Mapped[str | None] = mapped_column(Text)  # JSON blob

    # Acquisition notes
    acquisition_notes: Mapped[str | None] = mapped_column(Text)

    # Relationships
    case: Mapped["Case"] = relationship("Case", back_populates="media")
    derived_artifacts: Mapped[list["DerivedArtifact"]] = relationship(
        "DerivedArtifact", back_populates="source_media", cascade="all, delete-orphan"
    )


# ── Derived Artifact ──────────────────────────────────────────────────────────


class DerivedArtifact(Base):
    """
    Any file produced FROM a source media (thumbnails, compressed previews, frame indexes).
    Always links back to its parent with a hash chain.
    """

    __tablename__ = "derived_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_media_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("source_media.id", ondelete="CASCADE")
    )
    artifact_type: Mapped[str] = mapped_column(
        String(100)
    )  # thumbnail | preview | frame_index | track_data
    storage_path: Mapped[str] = mapped_column(String(1000))
    sha256: Mapped[str] = mapped_column(String(64))
    tool_name: Mapped[str] = mapped_column(String(100))
    tool_version: Mapped[str] = mapped_column(String(50))
    parameters: Mapped[str | None] = mapped_column(Text)  # JSON
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    source_media: Mapped["SourceMedia"] = relationship(
        "SourceMedia", back_populates="derived_artifacts"
    )


# ── Processing Job ────────────────────────────────────────────────────────────


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"))
    media_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("source_media.id", ondelete="SET NULL")
    )
    stage: Mapped[JobStage] = mapped_column(Enum(JobStage))
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.QUEUED)
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    error_message: Mapped[str | None] = mapped_column(Text)
    celery_task_id: Mapped[str | None] = mapped_column(String(100))
    queued_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    case: Mapped["Case"] = relationship("Case", back_populates="jobs")


# ── Processing Log ────────────────────────────────────────────────────────────


class ProcessingLog(Base):
    """
    Immutable append-only audit trail. Every transformation is recorded here.
    """

    __tablename__ = "processing_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"))
    media_id: Mapped[str | None] = mapped_column(String(36))
    stage: Mapped[str] = mapped_column(String(100))
    tool_name: Mapped[str] = mapped_column(String(100))
    tool_version: Mapped[str] = mapped_column(String(50))
    input_hash: Mapped[str | None] = mapped_column(String(64))
    output_hash: Mapped[str | None] = mapped_column(String(64))
    parameters: Mapped[str | None] = mapped_column(Text)
    operator: Mapped[str] = mapped_column(String(100))  # system | user:<id>
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    notes: Mapped[str | None] = mapped_column(Text)

    case: Mapped["Case"] = relationship("Case", back_populates="processing_log")
