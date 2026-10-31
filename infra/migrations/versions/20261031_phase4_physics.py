"""
Alembic migration: Phase 4 — dynamics_runs, counterfactual_runs, rival_searches

Revision ID: 20261031_phase4_physics
Revises: 20261031_phase3
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20261031_phase4_physics"
down_revision = "20261031_phase3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    # Phase 4 separates tracker pixel-localisation error from Phase 2's
    # combined position budget. Existing tracks remain NULL and are refused
    # for metric inference until tracking is rerun with the new schema.
    if "track_points" in existing:
        columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("track_points")}
        if "pixel_localisation_sigma_m" not in columns:
            op.add_column("track_points", sa.Column("pixel_localisation_sigma_m", sa.Float(), nullable=True))
    expected = {"dynamics_runs", "counterfactual_runs", "rival_searches"}
    if expected.issubset(existing):
        # Development API startup currently calls create_all(); make the
        # migration safe when those tables were already created from metadata.
        indexes = {
            table: {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}
            for table in expected
        }
        if "ix_dynamics_runs_case_media" not in indexes["dynamics_runs"]:
            op.create_index("ix_dynamics_runs_case_media", "dynamics_runs", ["case_id", "media_id"])
        if "ix_dynamics_runs_track" not in indexes["dynamics_runs"]:
            op.create_index("ix_dynamics_runs_track", "dynamics_runs", ["track_id"])
        if "ix_cf_runs_baseline" not in indexes["counterfactual_runs"]:
            op.create_index("ix_cf_runs_baseline", "counterfactual_runs", ["baseline_run_id"])
        if "ix_rival_searches_primary_run" not in indexes["rival_searches"]:
            op.create_index("ix_rival_searches_primary_run", "rival_searches", ["primary_run_id"])
        return
    # ── dynamics_runs ────────────────────────────────────────────────────────
    op.create_table(
        "dynamics_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("media_id", sa.String(36), sa.ForeignKey("source_media.id", ondelete="CASCADE"), nullable=False),
        sa.Column("track_id", sa.String(36), sa.ForeignKey("object_tracks.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("track_version_hash", sa.String(64), nullable=False),
        sa.Column("calibration_fit_id", sa.String(36), sa.ForeignKey("homography_fits.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("media_sha256", sa.String(64), nullable=False),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("model_version", sa.String(20), nullable=False),
        sa.Column("software_revision", sa.String(64), nullable=False),
        sa.Column("seed", sa.Integer, nullable=False),
        sa.Column("params_json", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("processing_jobs.id"), nullable=True),
        sa.Column("fitted_points_json", sa.Text, nullable=True),
        sa.Column("uncertainty_json", sa.Text, nullable=True),
        sa.Column("certificates_json", sa.Text, nullable=True),
        sa.Column("fit_quality_json", sa.Text, nullable=True),
        sa.Column("braking_onset_json", sa.Text, nullable=True),
        sa.Column("entry_speed_kmh", sa.Float, nullable=True),
        sa.Column("entry_speed_lo_kmh", sa.Float, nullable=True),
        sa.Column("entry_speed_hi_kmh", sa.Float, nullable=True),
        sa.Column("mean_decel_ms2", sa.Float, nullable=True),
        sa.Column("mean_decel_lo_ms2", sa.Float, nullable=True),
        sa.Column("mean_decel_hi_ms2", sa.Float, nullable=True),
        sa.Column("interval_type", sa.String(30), nullable=False, server_default="illustrative_range"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_dynamics_runs_case_media", "dynamics_runs", ["case_id", "media_id"])
    op.create_index("ix_dynamics_runs_track", "dynamics_runs", ["track_id"])

    # ── counterfactual_runs ──────────────────────────────────────────────────
    op.create_table(
        "counterfactual_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("media_id", sa.String(36), sa.ForeignKey("source_media.id", ondelete="CASCADE"), nullable=False),
        sa.Column("baseline_run_id", sa.String(36), sa.ForeignKey("dynamics_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("intervention_json", sa.Text, nullable=False),
        sa.Column("simulated_points_json", sa.Text, nullable=True),
        sa.Column("sensitivity_json", sa.Text, nullable=True),
        sa.Column("stopping_distance_m", sa.Float, nullable=True),
        sa.Column("stopping_time_s", sa.Float, nullable=True),
        sa.Column("extrapolation_outside_support", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("assumptions_json", sa.Text, nullable=False, server_default="{}"),
        sa.Column("illustrative_label", sa.String(200), nullable=False,
                  server_default="ILLUSTRATIVE — model scenario, not observed fact"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("created_by", sa.String(100), nullable=False, server_default="system"),
    )
    op.create_index("ix_cf_runs_baseline", "counterfactual_runs", ["baseline_run_id"])

    # ── rival_searches ───────────────────────────────────────────────────────
    op.create_table(
        "rival_searches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("media_id", sa.String(36), sa.ForeignKey("source_media.id", ondelete="CASCADE"), nullable=False),
        sa.Column("primary_run_id", sa.String(36), sa.ForeignKey("dynamics_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("manifest_json", sa.Text, nullable=False),
        sa.Column("rivals_json", sa.Text, nullable=False, server_default="[]"),
        sa.Column("empty_search_message", sa.Text, nullable=False, server_default=""),
        sa.Column("second_view_used", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("second_view_notes", sa.Text, nullable=False, server_default="No second view provided."),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_rival_searches_primary_run", "rival_searches", ["primary_run_id"])


def downgrade() -> None:
    op.drop_table("rival_searches")
    op.drop_table("counterfactual_runs")
    op.drop_table("dynamics_runs")
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "track_points" in existing:
        columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("track_points")}
        if "pixel_localisation_sigma_m" in columns:
            op.drop_column("track_points", "pixel_localisation_sigma_m")
