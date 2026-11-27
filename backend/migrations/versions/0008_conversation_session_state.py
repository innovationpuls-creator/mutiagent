"""Add structured session_state to conversation sessions."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008_conversation_session_state"
down_revision = "0007_personal_pi_model_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("conversationsession"):
        return
    columns = {
        column["name"] for column in inspector.get_columns("conversationsession")
    }
    if "session_state" in columns:
        return
    op.add_column(
        "conversationsession",
        sa.Column(
            "session_state",
            JSONB(none_as_null=False),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("conversationsession"):
        return
    columns = {
        column["name"] for column in inspector.get_columns("conversationsession")
    }
    if "session_state" in columns:
        op.drop_column("conversationsession", "session_state")
