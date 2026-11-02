"""Require an independent validation point on calibration fits."""

import sqlalchemy as sa
from alembic import op

revision = "20261102_calibration_validation"
down_revision = "20261101_phase5_backend"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("homography_fits")}
    if "validation_anchor_count" not in columns:
        op.add_column(
            "homography_fits",
            sa.Column("validation_anchor_count", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("homography_fits")}
    if "validation_anchor_count" in columns:
        op.drop_column("homography_fits", "validation_anchor_count")
