"""Record which admin triggered a knowledge-base ingestion job."""

import sqlalchemy as sa
from alembic import op

revision = "0009_kb_job_triggered_by"
down_revision = "0008_conversation_session_state"
branch_labels = None
depends_on = None


def _columns() -> set[str] | None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("knowledgebaseingestionjob"):
        return None
    return {c["name"] for c in inspector.get_columns("knowledgebaseingestionjob")}


def upgrade() -> None:
    columns = _columns()
    if columns is None or "triggered_by_uid" in columns:
        return
    op.add_column(
        "knowledgebaseingestionjob",
        sa.Column("triggered_by_uid", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    columns = _columns()
    if columns is not None and "triggered_by_uid" in columns:
        op.drop_column("knowledgebaseingestionjob", "triggered_by_uid")
