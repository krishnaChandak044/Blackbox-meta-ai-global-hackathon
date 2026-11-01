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
    calibration_anchors: Mapped[list["CalibrationAnchor"]] = relationship(
        "CalibrationAnchor", cascade="all, delete-orphan"
    )
    homography_fits: Mapped[list["HomographyFit"]] = relationship(
        "HomographyFit", cascade="all, delete-orphan"
    )
    object_tracks: Mapped[list["ObjectTrack"]] = relationship(
        "ObjectTrack", cascade="all, delete-orphan"
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


# ══════════════════════════════════════════════════════════════════════════════
# Phase 2 — Perception & Geometry
# ══════════════════════════════════════════════════════════════════════════════


# ── Calibration Anchor ────────────────────────────────────────────────────────


class CalibrationAnchor(Base):
    """
    A single pixel ↔ world correspondence used to fit the homography.

    pixel_(x,y) is the image-space location (column, row).
    world_(x,y) is the real-world ground-plane position in metres
    (origin is user-defined, typically the first anchor placed).

    known_distance_ref marks the two anchors that define the validation
    distance (at most one pair per media clip).
    """

    __tablename__ = "calibration_anchors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    media_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("source_media.id", ondelete="CASCADE")
    )
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(100))  # human-readable, e.g. "stop-line NW"
    pixel_x: Mapped[float] = mapped_column(Float)  # column
    pixel_y: Mapped[float] = mapped_column(Float)  # row
    world_x: Mapped[float] = mapped_column(Float)  # east, metres
    world_y: Mapped[float] = mapped_column(Float)  # north, metres
    known_distance_m: Mapped[float | None] = mapped_column(Float)  # validation pair A
    is_distance_ref_b: Mapped[bool] = mapped_column(Boolean, default=False)  # validation pair B
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by: Mapped[str] = mapped_column(String(100))  # user or "system"

    # Reprojection error for this anchor after the last homography fit (px)
    reprojection_error_px: Mapped[float | None] = mapped_column(Float)


# ── Homography Fit ────────────────────────────────────────────────────────────


class HomographyFit(Base):
    """
    Stored result of one homography estimation run.

    H_json stores the 3×3 matrix as a JSON array [[r0c0, r0c1, r0c2], ...].
    Recomputation is idempotent: same anchors → same H.
    """

    __tablename__ = "homography_fits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    media_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("source_media.id", ondelete="CASCADE")
    )
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"))
    anchor_count: Mapped[int] = mapped_column(Integer)
    reprojection_rmse_px: Mapped[float] = mapped_column(Float)
    condition_number: Mapped[float] = mapped_column(Float)
    scale_metres_per_pixel: Mapped[float | None] = mapped_column(Float)
    scale_relative_error: Mapped[float | None] = mapped_column(Float)
    scale_source: Mapped[str | None] = mapped_column(String(100))
    H_json: Mapped[str] = mapped_column(Text)  # [[...],[...],[...]]
    fitted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    fitted_by: Mapped[str] = mapped_column(String(100))  # user or "system"
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # latest wins


# ── Object Track ──────────────────────────────────────────────────────────────


class ObjectTrack(Base):
    """
    One detected object's complete trajectory in a single media clip.

    category: "vehicle" | "pedestrian" | "cyclist" | "unknown"
    tracker_model: e.g. "sam-3.1-hiera-large" or "synthetic-v0"
    is_human_confirmed: set True when a human has reviewed the track.
    """

    __tablename__ = "object_tracks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    media_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("source_media.id", ondelete="CASCADE")
    )
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"))
    tracker_track_id: Mapped[str] = mapped_column(String(100))  # ID assigned by tracker
    category: Mapped[str] = mapped_column(String(50))
    tracker_model: Mapped[str] = mapped_column(String(100))
    first_frame: Mapped[int] = mapped_column(Integer)
    last_frame: Mapped[int] = mapped_column(Integer)
    point_count: Mapped[int] = mapped_column(Integer)
    is_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    is_human_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    human_confirmed_by: Mapped[str | None] = mapped_column(String(100))
    human_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    points: Mapped[list["TrackPointRow"]] = relationship(
        "TrackPointRow",
        back_populates="track",
        cascade="all, delete-orphan",
        order_by="TrackPointRow.frame_index",
    )


# ── Track Point ───────────────────────────────────────────────────────────────


class TrackPointRow(Base):
    """
    Single detection within an ObjectTrack.

    Stores both the pixel bounding box and the projected world position
    (if a calibrated HomographyFit existed at track time).

    sigma_m is the 1-sigma combined position uncertainty in metres.
    NULL world_* means no calibration was available — callers must not
    compute speed from NULL world positions.
    """

    __tablename__ = "track_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    track_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("object_tracks.id", ondelete="CASCADE")
    )
    frame_index: Mapped[int] = mapped_column(Integer)
    presentation_ts_s: Mapped[float] = mapped_column(Float)

    # Pixel bounding box
    bbox_x_min: Mapped[float] = mapped_column(Float)
    bbox_y_min: Mapped[float] = mapped_column(Float)
    bbox_x_max: Mapped[float] = mapped_column(Float)
    bbox_y_max: Mapped[float] = mapped_column(Float)

    # Ground contact pixel (bottom-centre of bbox)
    gc_pixel_x: Mapped[float] = mapped_column(Float)
    gc_pixel_y: Mapped[float] = mapped_column(Float)

    # World projection (NULL when no calibration)
    world_x: Mapped[float | None] = mapped_column(Float)
    world_y: Mapped[float | None] = mapped_column(Float)
    sigma_m: Mapped[float | None] = mapped_column(Float)
    # Pixel-localisation component kept separately; sigma_m is the combined
    # Phase 2 budget and must not be double-counted by Phase 4.
    pixel_localisation_sigma_m: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Detection quality
    detection_confidence: Mapped[float] = mapped_column(Float)
    is_interpolated: Mapped[bool] = mapped_column(Boolean, default=False)
    is_human_corrected: Mapped[bool] = mapped_column(Boolean, default=False)

    track: Mapped["ObjectTrack"] = relationship("ObjectTrack", back_populates="points")

# ══════════════════════════════════════════════════════════════════════════════
# Phase 3 — Language & Claims
# ══════════════════════════════════════════════════════════════════════════════


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"))
    media_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("source_media.id", ondelete="SET NULL"), nullable=True)
    speaker_count: Mapped[int] = mapped_column(Integer, default=1)
    language: Mapped[str] = mapped_column(String(10), default="en")
    raw_text: Mapped[str] = mapped_column(Text)
    diarised_json: Mapped[str | None] = mapped_column(Text)
    transcription_model: Mapped[str] = mapped_column(String(100), default="manual")
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    # is_synthetic=True means the text was machine-generated (not real audio)
    # Claims derived from synthetic transcripts must not be treated as evidence.
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by: Mapped[str] = mapped_column(String(100), default="system")


class TranscriptClaim(Base):
    __tablename__ = "transcript_claims"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    transcript_id: Mapped[str] = mapped_column(String(36), ForeignKey("transcripts.id", ondelete="CASCADE"))
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"))
    media_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("source_media.id", ondelete="SET NULL"), nullable=True)
    speaker: Mapped[str] = mapped_column(String(100), default="witness_1")
    raw_text: Mapped[str] = mapped_column(Text)
    assertions_json: Mapped[str] = mapped_column(Text)
    extraction_confidence: Mapped[float] = mapped_column(Float, default=0.5)
    source_ts_start: Mapped[float] = mapped_column(Float, default=0.0)
    source_ts_end: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by: Mapped[str] = mapped_column(String(100), default="system")
    # When raw_text is edited, assertions are re-extracted and old verdicts are invalidated
    assertions_edited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    verdict_invalidated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    edit_history_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of {ts, field, old, new, by}


class ClaimCheck(Base):
    __tablename__ = "claim_checks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    claim_id: Mapped[str] = mapped_column(String(36), ForeignKey("transcript_claims.id", ondelete="CASCADE"))
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"))
    verdict: Mapped[str] = mapped_column(String(30))
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    evidence_frame_start: Mapped[int | None] = mapped_column(Integer)
    evidence_frame_end: Mapped[int | None] = mapped_column(Integer)
    evidence_json: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)
    homography_fit_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("homography_fits.id", ondelete="SET NULL"), nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    checked_by: Mapped[str] = mapped_column(String(100), default="system")


# ── Phase 4: Dynamics inference run ─────────────────────────────────────────


class DynamicsRun(Base):
    """
    Immutable record of one piecewise-constant-acceleration inference run.
    Linked to specific track, calibration, and media content versions.
    Outputs are stored as JSON blobs — never reused when inputs change.
    """
    __tablename__ = "dynamics_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"))
    media_id: Mapped[str] = mapped_column(String(36), ForeignKey("source_media.id", ondelete="CASCADE"))

    # Input provenance — changing any of these makes this run stale
    track_id: Mapped[str] = mapped_column(String(36), ForeignKey("object_tracks.id", ondelete="RESTRICT"))
    track_version_hash: Mapped[str] = mapped_column(String(64))
    calibration_fit_id: Mapped[str] = mapped_column(String(36), ForeignKey("homography_fits.id", ondelete="RESTRICT"))
    media_sha256: Mapped[str] = mapped_column(String(64))
    model_name: Mapped[str] = mapped_column(String(100))
    model_version: Mapped[str] = mapped_column(String(20))
    software_revision: Mapped[str] = mapped_column(String(64))
    seed: Mapped[int] = mapped_column(Integer)
    params_json: Mapped[str] = mapped_column(Text)          # exact parameters snapshot

    # Run status
    status: Mapped[str] = mapped_column(String(20), default="queued")
    job_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("processing_jobs.id"), nullable=True)

    # Results — stored as serialised JSON (immutable after status=done)
    fitted_points_json: Mapped[str | None] = mapped_column(Text)
    uncertainty_json: Mapped[str | None] = mapped_column(Text)
    certificates_json: Mapped[str | None] = mapped_column(Text)
    fit_quality_json: Mapped[str | None] = mapped_column(Text)
    braking_onset_json: Mapped[str | None] = mapped_column(Text)

    # Derived scalars (also in fitted_points_json but surfaced for quick queries)
    entry_speed_kmh: Mapped[float | None] = mapped_column(Float)
    entry_speed_lo_kmh: Mapped[float | None] = mapped_column(Float)
    entry_speed_hi_kmh: Mapped[float | None] = mapped_column(Float)
    mean_decel_ms2: Mapped[float | None] = mapped_column(Float)
    mean_decel_lo_ms2: Mapped[float | None] = mapped_column(Float)
    mean_decel_hi_ms2: Mapped[float | None] = mapped_column(Float)
    interval_type: Mapped[str] = mapped_column(String(30), default="illustrative_range")

    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


# ── Phase 4: Counterfactual simulation result ────────────────────────────────


class CounterfactualRun(Base):
    """
    Versioned counterfactual simulation result.
    Always labeled ILLUSTRATIVE — linked to an immutable DynamicsRun.
    """
    __tablename__ = "counterfactual_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"))
    media_id: Mapped[str] = mapped_column(String(36), ForeignKey("source_media.id", ondelete="CASCADE"))
    baseline_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("dynamics_runs.id", ondelete="CASCADE"))

    # User-declared intervention (JSON)
    intervention_json: Mapped[str] = mapped_column(Text)

    # Results
    simulated_points_json: Mapped[str | None] = mapped_column(Text)
    sensitivity_json: Mapped[str | None] = mapped_column(Text)
    stopping_distance_m: Mapped[float | None] = mapped_column(Float)
    stopping_time_s: Mapped[float | None] = mapped_column(Float)
    extrapolation_outside_support: Mapped[bool] = mapped_column(Boolean, default=False)
    assumptions_json: Mapped[str] = mapped_column(Text, default="{}")
    illustrative_label: Mapped[str] = mapped_column(
        String(200), default="ILLUSTRATIVE — model scenario, not observed fact"
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by: Mapped[str] = mapped_column(String(100), default="system")


# ── Phase 4: Rival hypothesis search ────────────────────────────────────────


class RivalSearch(Base):
    """
    Immutable record of a bounded rival-hypothesis search.
    Includes the full manifest (never implies exhaustiveness).
    """
    __tablename__ = "rival_searches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"))
    media_id: Mapped[str] = mapped_column(String(36), ForeignKey("source_media.id", ondelete="CASCADE"))
    primary_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("dynamics_runs.id", ondelete="CASCADE"))

    # Search manifest (JSON) — dimensions, bounds, seed, objective, threshold, n_evaluated
    manifest_json: Mapped[str] = mapped_column(Text)

    # Results
    rivals_json: Mapped[str] = mapped_column(Text, default="[]")
    empty_search_message: Mapped[str] = mapped_column(Text, default="")
    second_view_used: Mapped[bool] = mapped_column(Boolean, default=False)
    second_view_notes: Mapped[str] = mapped_column(Text, default="No second view provided.")

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ── Phase 5: evidence needs, opt-in prevention atlas, immutable exports ──────


class EvidenceNeed(Base):
    __tablename__ = "evidence_needs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    need_key: Mapped[str] = mapped_column(String(120))
    snapshot_json: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(30), default="suggested")
    verification_json: Mapped[str | None] = mapped_column(Text)
    draft_text: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(100))
    updated_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ReviewerAction(Base):
    __tablename__ = "reviewer_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    target_type: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[str] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(60))
    before_json: Mapped[str | None] = mapped_column(Text)
    after_json: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AtlasConsent(Base):
    __tablename__ = "atlas_consents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), unique=True)
    opted_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    scope_version: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(100))
    consented_at: Mapped[datetime | None] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AtlasConsentEvent(Base):
    __tablename__ = "atlas_consent_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    opted_in: Mapped[bool] = mapped_column(Boolean, nullable=False)
    scope_version: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AtlasContribution(Base):
    __tablename__ = "atlas_contributions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    source_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("dynamics_runs.id", ondelete="RESTRICT"))
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True)
    coarse_cell: Mapped[str] = mapped_column(String(40), index=True)
    time_bucket: Mapped[str] = mapped_column(String(12))
    conflict_type: Mapped[str] = mapped_column(String(40))
    road_user_mix_json: Mapped[str] = mapped_column(Text)
    metrics_json: Mapped[str] = mapped_column(Text)
    provenance_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ExportRecord(Base):
    __tablename__ = "export_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    case_revision_hash: Mapped[str] = mapped_column(String(64))
    manifest_sha256: Mapped[str | None] = mapped_column(String(64))
    pdf_sha256: Mapped[str | None] = mapped_column(String(64))
    json_sha256: Mapped[str | None] = mapped_column(String(64))
    pdf_path: Mapped[str | None] = mapped_column(String(1000))
    json_path: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    job_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("processing_jobs.id"), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
