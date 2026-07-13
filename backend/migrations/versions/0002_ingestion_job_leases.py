"""Add durable ingestion job lease fields."""

import sqlalchemy as sa
from alembic import op

revision = "0002_ingestion_job_leases"
down_revision = "0001_production_baseline"
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
    existing_columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns(TABLE_NAME)
    }
    for column_name in (
        "updated_at",
        "request_id",
        "worker_id",
        "lease_expires_at",
        "available_at",
        "max_attempts",
        "attempt_count",
    ):
        if column_name in existing_columns:
            op.drop_column(TABLE_NAME, column_name)
