"""Create the production baseline schema."""

from alembic import op
from sqlmodel import SQLModel

import app.models  # noqa: F401

revision = "0001_production_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    SQLModel.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    SQLModel.metadata.drop_all(bind=op.get_bind())
