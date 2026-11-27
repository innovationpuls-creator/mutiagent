"""Version and durable result snapshot for quiz submission recovery."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005_quiz_submission_recovery"
down_revision = "0004_worker_heartbeats"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("chapterquizattempt")
    }
    if "quiz_version" not in columns:
        op.add_column(
            "chapterquizattempt",
            sa.Column("quiz_version", sa.String(64), nullable=True),
        )
    if "recovery_snapshot" not in columns:
        op.add_column(
            "chapterquizattempt",
            sa.Column(
                "recovery_snapshot",
                sa.JSON().with_variant(JSONB(), "postgresql"),
                nullable=True,
            ),
        )


def downgrade() -> None:
    op.drop_column("chapterquizattempt", "recovery_snapshot")
    op.drop_column("chapterquizattempt", "quiz_version")
