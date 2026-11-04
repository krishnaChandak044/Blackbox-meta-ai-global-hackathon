"""Create the Blackbox schema on a fresh database.

This is the true baseline migration for Phases 1–2 tables.
Subsequent revisions add columns/tables incrementally with explicit DDL.
Schema is managed ONLY by Alembic; API startup does NOT call create_all().

Revision ID: 20261030_initial_schema
Revises: (none — root migration)
"""

import sqlalchemy as sa
from alembic import op

revision = "20261030_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── cases ─────────────────────────────────────────────────────────────────
    op.create_table(
        "cases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("jurisdiction", sa.String(100), nullable=True),
        sa.Column("incident_date", sa.DateTime(), nullable=True),
        sa.Column("incident_location", sa.String(500), nullable=True),
        sa.Column(
            "status",
            sa.Enum("draft", "processing", "ready", "exported", name="casestatus"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("consent_given", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # ── source_media ──────────────────────────────────────────────────────────
    op.create_table(
        "source_media",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("byte_length", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_path", sa.String(1000), nullable=False),
        sa.Column(
            "status",
            sa.Enum("uploading", "stored", "probing", "indexed", "failed", name="mediastatus"),
            nullable=False,
            server_default="uploading",
        ),
        sa.Column("upload_time", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("codec", sa.String(50), nullable=True),
        sa.Column("container", sa.String(50), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("frame_count", sa.Integer(), nullable=True),
        sa.Column("fps_nominal", sa.Float(), nullable=True),
        sa.Column("is_variable_framerate", sa.Boolean(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("has_audio", sa.Boolean(), nullable=True),
        sa.Column("device_clock_metadata", sa.Text(), nullable=True),
        sa.Column("acquisition_notes", sa.Text(), nullable=True),
    )

    # ── derived_artifacts ─────────────────────────────────────────────────────
    op.create_table(
        "derived_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_media_id", sa.String(36), sa.ForeignKey("source_media.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_type", sa.String(100), nullable=False),
        sa.Column("storage_path", sa.String(1000), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("tool_name", sa.String(100), nullable=False),
        sa.Column("tool_version", sa.String(50), nullable=False),
        sa.Column("parameters", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # ── processing_jobs ───────────────────────────────────────────────────────
    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("media_id", sa.String(36), sa.ForeignKey("source_media.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "stage",
            sa.Enum(
                "probe", "frame_index", "integrity", "track", "calibrate",
                "transcribe", "claim_check", "dynamics", "counterfactual", "export",
                name="jobstage",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("queued", "running", "done", "failed", "retrying", name="jobstatus"),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("celery_task_id", sa.String(100), nullable=True),
        sa.Column("queued_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )

    # ── processing_log ────────────────────────────────────────────────────────
    op.create_table(
        "processing_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("media_id", sa.String(36), nullable=True),
        sa.Column("stage", sa.String(100), nullable=False),
        sa.Column("tool_name", sa.String(100), nullable=False),
        sa.Column("tool_version", sa.String(50), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=True),
        sa.Column("output_hash", sa.String(64), nullable=True),
        sa.Column("parameters", sa.Text(), nullable=True),
        sa.Column("operator", sa.String(100), nullable=False),
        sa.Column("timestamp", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("notes", sa.Text(), nullable=True),
    )

    # ── calibration_anchors ───────────────────────────────────────────────────
    op.create_table(
        "calibration_anchors",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("media_id", sa.String(36), sa.ForeignKey("source_media.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("pixel_x", sa.Float(), nullable=False),
        sa.Column("pixel_y", sa.Float(), nullable=False),
        sa.Column("world_x", sa.Float(), nullable=False),
        sa.Column("world_y", sa.Float(), nullable=False),
        sa.Column("known_distance_m", sa.Float(), nullable=True),
        sa.Column("is_distance_ref_b", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("reprojection_error_px", sa.Float(), nullable=True),
    )

    # ── homography_fits ───────────────────────────────────────────────────────
    # NOTE: validation_anchor_count is included here from the start so that
    # migration 20261102_calibration_validation is a true no-op on fresh DBs.
    op.create_table(
        "homography_fits",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("media_id", sa.String(36), sa.ForeignKey("source_media.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("anchor_count", sa.Integer(), nullable=False),
        sa.Column("validation_anchor_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reprojection_rmse_px", sa.Float(), nullable=False),
        sa.Column("condition_number", sa.Float(), nullable=False),
        sa.Column("scale_metres_per_pixel", sa.Float(), nullable=True),
        sa.Column("scale_relative_error", sa.Float(), nullable=True),
        sa.Column("scale_source", sa.String(100), nullable=True),
        sa.Column("H_json", sa.Text(), nullable=False),
        sa.Column("fitted_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("fitted_by", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    # ── object_tracks ─────────────────────────────────────────────────────────
    op.create_table(
        "object_tracks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("media_id", sa.String(36), sa.ForeignKey("source_media.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tracker_track_id", sa.String(100), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("tracker_model", sa.String(100), nullable=False),
        sa.Column("first_frame", sa.Integer(), nullable=False),
        sa.Column("last_frame", sa.Integer(), nullable=False),
        sa.Column("point_count", sa.Integer(), nullable=False),
        sa.Column("is_complete", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_human_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("human_confirmed_by", sa.String(100), nullable=True),
        sa.Column("human_confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # ── track_points ──────────────────────────────────────────────────────────
    # NOTE: pixel_localisation_sigma_m included here so that the Phase 4
    # migration is a no-op on fresh databases.
    op.create_table(
        "track_points",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("track_id", sa.String(36), sa.ForeignKey("object_tracks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("frame_index", sa.Integer(), nullable=False),
        sa.Column("presentation_ts_s", sa.Float(), nullable=False),
        sa.Column("bbox_x_min", sa.Float(), nullable=False),
        sa.Column("bbox_y_min", sa.Float(), nullable=False),
        sa.Column("bbox_x_max", sa.Float(), nullable=False),
        sa.Column("bbox_y_max", sa.Float(), nullable=False),
        sa.Column("gc_pixel_x", sa.Float(), nullable=False),
        sa.Column("gc_pixel_y", sa.Float(), nullable=False),
        sa.Column("world_x", sa.Float(), nullable=True),
        sa.Column("world_y", sa.Float(), nullable=True),
        sa.Column("sigma_m", sa.Float(), nullable=True),
        sa.Column("pixel_localisation_sigma_m", sa.Float(), nullable=True),
        sa.Column("detection_confidence", sa.Float(), nullable=False),
        sa.Column("is_interpolated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_human_corrected", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # ── transcripts ───────────────────────────────────────────────────────────
    # NOTE: is_synthetic included here so Phase 3 migration is a no-op on fresh DBs.
    op.create_table(
        "transcripts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("media_id", sa.String(36), sa.ForeignKey("source_media.id", ondelete="SET NULL"), nullable=True),
        sa.Column("speaker_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("language", sa.String(10), nullable=False, server_default="en"),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("diarised_json", sa.Text(), nullable=True),
        sa.Column("transcription_model", sa.String(100), nullable=False, server_default="manual"),
        sa.Column("word_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("created_by", sa.String(100), nullable=False, server_default="system"),
    )

    # ── transcript_claims ─────────────────────────────────────────────────────
    # NOTE: edit_history columns included here so Phase 3 migration is a no-op.
    op.create_table(
        "transcript_claims",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("transcript_id", sa.String(36), sa.ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("media_id", sa.String(36), sa.ForeignKey("source_media.id", ondelete="SET NULL"), nullable=True),
        sa.Column("speaker", sa.String(100), nullable=False, server_default="witness_1"),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("assertions_json", sa.Text(), nullable=False),
        sa.Column("extraction_confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("source_ts_start", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("source_ts_end", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("created_by", sa.String(100), nullable=False, server_default="system"),
        sa.Column("assertions_edited_at", sa.DateTime(), nullable=True),
        sa.Column("verdict_invalidated_at", sa.DateTime(), nullable=True),
        sa.Column("edit_history_json", sa.Text(), nullable=True),
    )

    # ── claim_checks ──────────────────────────────────────────────────────────
    op.create_table(
        "claim_checks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("claim_id", sa.String(36), sa.ForeignKey("transcript_claims.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("verdict", sa.String(30), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("evidence_frame_start", sa.Integer(), nullable=True),
        sa.Column("evidence_frame_end", sa.Integer(), nullable=True),
        sa.Column("evidence_json", sa.Text(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("homography_fit_id", sa.String(36), sa.ForeignKey("homography_fits.id", ondelete="SET NULL"), nullable=True),
        sa.Column("checked_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("checked_by", sa.String(100), nullable=False, server_default="system"),
    )


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("claim_checks")
    op.drop_table("transcript_claims")
    op.drop_table("transcripts")
    op.drop_table("track_points")
    op.drop_table("object_tracks")
    op.drop_table("homography_fits")
    op.drop_table("calibration_anchors")
    op.drop_table("processing_log")
    op.drop_table("processing_jobs")
    op.drop_table("derived_artifacts")
    op.drop_table("source_media")
    op.drop_table("cases")
    # Drop enums (PostgreSQL only; SQLite ignores these)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS casestatus")
        op.execute("DROP TYPE IF EXISTS mediastatus")
        op.execute("DROP TYPE IF EXISTS jobstage")
        op.execute("DROP TYPE IF EXISTS jobstatus")
