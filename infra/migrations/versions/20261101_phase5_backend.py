"""Phase 5 backend: evidence radar, atlas consent/contributions, exports.

Revision ID: 20261101_phase5_backend
Revises: 20261031_phase4_physics
"""
import sqlalchemy as sa
from alembic import op

revision = "20261101_phase5_backend"
down_revision = "20261031_phase4_physics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "evidence_needs" not in existing:
        op.create_table("evidence_needs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
            sa.Column("need_key", sa.String(120), nullable=False), sa.Column("snapshot_json", sa.Text(), nullable=False),
            sa.Column("state", sa.String(30), nullable=False, server_default="suggested"),
            sa.Column("verification_json", sa.Text()), sa.Column("draft_text", sa.Text()),
            sa.Column("created_by", sa.String(100), nullable=False), sa.Column("updated_by", sa.String(100), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()))
        op.create_index("ix_evidence_needs_case_id", "evidence_needs", ["case_id"])
    if "reviewer_actions" not in existing:
        op.create_table("reviewer_actions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
            sa.Column("target_type", sa.String(40), nullable=False), sa.Column("target_id", sa.String(36), nullable=False),
            sa.Column("action", sa.String(60), nullable=False), sa.Column("before_json", sa.Text()),
            sa.Column("after_json", sa.Text(), nullable=False), sa.Column("actor", sa.String(100), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()))
        op.create_index("ix_reviewer_actions_case_id", "reviewer_actions", ["case_id"])
    if "atlas_consents" not in existing:
        op.create_table("atlas_consents",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("opted_in", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("scope_version", sa.String(40), nullable=False), sa.Column("actor", sa.String(100), nullable=False),
            sa.Column("consented_at", sa.DateTime()), sa.Column("revoked_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()))
    if "atlas_consent_events" not in existing:
        op.create_table("atlas_consent_events",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
            sa.Column("opted_in", sa.Boolean(), nullable=False), sa.Column("scope_version", sa.String(40), nullable=False),
            sa.Column("actor", sa.String(100), nullable=False), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()))
        op.create_index("ix_atlas_consent_events_case_id", "atlas_consent_events", ["case_id"])
    if "atlas_contributions" not in existing:
        op.create_table("atlas_contributions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
            sa.Column("source_run_id", sa.String(36), sa.ForeignKey("dynamics_runs.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("dedupe_key", sa.String(64), nullable=False, unique=True), sa.Column("coarse_cell", sa.String(40), nullable=False),
            sa.Column("time_bucket", sa.String(12), nullable=False), sa.Column("conflict_type", sa.String(40), nullable=False),
            sa.Column("road_user_mix_json", sa.Text(), nullable=False), sa.Column("metrics_json", sa.Text(), nullable=False),
            sa.Column("provenance_json", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()))
        op.create_index("ix_atlas_contributions_case_id", "atlas_contributions", ["case_id"])
        op.create_index("ix_atlas_contributions_coarse_cell", "atlas_contributions", ["coarse_cell"])
    if "export_records" not in existing:
        op.create_table("export_records",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
            sa.Column("case_revision_hash", sa.String(64), nullable=False), sa.Column("manifest_sha256", sa.String(64)),
            sa.Column("pdf_sha256", sa.String(64)), sa.Column("json_sha256", sa.String(64)),
            sa.Column("pdf_path", sa.String(1000)), sa.Column("json_path", sa.String(1000)),
            sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
            sa.Column("job_id", sa.String(36), sa.ForeignKey("processing_jobs.id")), sa.Column("error_message", sa.Text()),
            sa.Column("created_by", sa.String(100), nullable=False), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("completed_at", sa.DateTime()))
        op.create_index("ix_export_records_case_id", "export_records", ["case_id"])


def downgrade() -> None:
    for table in ("export_records", "atlas_contributions", "atlas_consent_events", "atlas_consents", "reviewer_actions", "evidence_needs"):
        op.drop_table(table)
