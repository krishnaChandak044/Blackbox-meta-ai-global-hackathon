"""Add Phase 3 transcript safety and claim edit audit fields.

Revision ID: 20261031_phase3
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "20261031_phase3"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "transcripts" in tables:
        columns = {c["name"] for c in inspector.get_columns("transcripts")}
        if "is_synthetic" not in columns:
            op.add_column("transcripts", sa.Column("is_synthetic", sa.Boolean(), nullable=False, server_default=sa.false()))
    if "transcript_claims" in tables:
        columns = {c["name"] for c in inspector.get_columns("transcript_claims")}
        if "assertions_edited_at" not in columns:
            op.add_column("transcript_claims", sa.Column("assertions_edited_at", sa.DateTime(), nullable=True))
        if "verdict_invalidated_at" not in columns:
            op.add_column("transcript_claims", sa.Column("verdict_invalidated_at", sa.DateTime(), nullable=True))
        if "edit_history_json" not in columns:
            op.add_column("transcript_claims", sa.Column("edit_history_json", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "transcript_claims" in tables:
        columns = {c["name"] for c in inspector.get_columns("transcript_claims")}
        for name in ("edit_history_json", "verdict_invalidated_at", "assertions_edited_at"):
            if name in columns:
                op.drop_column("transcript_claims", name)
    if "transcripts" in tables:
        columns = {c["name"] for c in inspector.get_columns("transcripts")}
        if "is_synthetic" in columns:
            op.drop_column("transcripts", "is_synthetic")
