"""Repair ingestion job lease fields missing from databases at revision 0002."""

import sqlalchemy as sa
from alembic import op

revision = "0003_repair_ingestion_job_leases"
down_revision = "0002_ingestion_job_leases"
branch_labels = None
depends_on = None

TABLE_NAME = "knowledgebaseingestionjob"


def upgrade() -> None:
    connection = op.get_bind()
    existing_columns = {
        column["name"] for column in sa.inspect(connection).get_columns(TABLE_NAME)
    }
    columns = (
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column(
            "available_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("worker_id", sa.String(length=64), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )
    for column in columns:
        if column.name not in existing_columns:
            op.add_column(TABLE_NAME, column)


def downgrade() -> None:
    pass
