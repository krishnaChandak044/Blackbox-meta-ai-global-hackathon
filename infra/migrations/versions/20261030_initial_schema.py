"""Create the Blackbox schema on a fresh database.

Revision ID: 20261030_initial_schema
Revises:
"""

from alembic import op
from services.api.db.models import Base

revision = "20261030_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=True)
