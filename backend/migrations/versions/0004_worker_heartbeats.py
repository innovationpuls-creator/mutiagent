"""Add durable background worker heartbeat storage."""

import sqlalchemy as sa
from alembic import op

revision = "0004_worker_heartbeats"
down_revision = "0003_repair_ingestion_job_leases"
branch_labels = None
depends_on = None

TABLE_NAME = "workerheartbeat"


def upgrade() -> None:
    connection = op.get_bind()
    if sa.inspect(connection).has_table(TABLE_NAME):
        return
    op.create_table(
        TABLE_NAME,
        sa.Column("worker_name", sa.String(length=64), primary_key=True),
        sa.Column("worker_id", sa.String(length=64), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_workerheartbeat_last_heartbeat_at",
        TABLE_NAME,
        ["last_heartbeat_at"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    if not sa.inspect(connection).has_table(TABLE_NAME):
        return
    op.drop_table(TABLE_NAME)
