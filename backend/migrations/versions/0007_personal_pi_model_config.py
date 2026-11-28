"""Add personal Pi model configuration tables."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007_personal_pi_model_config"
down_revision = "0006_admin_program_drop_embed"
branch_labels = None
depends_on = None

TABLES = (
    "user_model_usage_log",
    "user_model_preferences",
    "user_custom_model",
    "user_model_provider",
)


def _jsonb() -> JSONB:
    return JSONB(none_as_null=False)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    # Partial legacy databases (migration-recovery tests) may lack the user table.
    user_fk = (
        [sa.ForeignKeyConstraint(["user_uid"], ["user.uid"])]
        if inspector.has_table("user")
        else []
    )
    if not inspector.has_table("user_model_provider"):
        op.create_table(
            "user_model_provider",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("user_uid", sa.String(), nullable=False),
            sa.Column("provider_id", sa.String(length=64), nullable=False),
            sa.Column("display_name", sa.String(length=128), nullable=False),
            sa.Column("is_builtin", sa.Boolean(), nullable=False),
            sa.Column("protocol", sa.String(length=32), nullable=False),
            sa.Column("base_url", sa.String(length=512), nullable=False),
            sa.Column("headers_encrypted", sa.String(), nullable=True),
            sa.Column("auth_type", sa.String(length=16), nullable=False),
            sa.Column("secret_encrypted", sa.String(), nullable=True),
            sa.Column("oauth_refresh_encrypted", sa.String(), nullable=True),
            sa.Column("oauth_expires_at", sa.DateTime(), nullable=True),
            sa.Column("oauth_account_label", sa.String(length=128), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            *user_fk,
            sa.UniqueConstraint(
                "user_uid", "provider_id", name="uq_user_model_provider"
            ),
            sa.CheckConstraint(
                "auth_type IN ('api_key', 'oauth')",
                name="ck_user_model_provider_auth_type",
            ),
        )
        op.create_index(
            "ix_user_model_provider_user_uid", "user_model_provider", ["user_uid"]
        )
    if not inspector.has_table("user_custom_model"):
        op.create_table(
            "user_custom_model",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("user_uid", sa.String(), nullable=False),
            sa.Column("provider_id", sa.String(length=64), nullable=False),
            sa.Column("model_id", sa.String(length=128), nullable=False),
            sa.Column("display_name", sa.String(length=128), nullable=False),
            sa.Column("context_window", sa.Integer(), nullable=False),
            sa.Column("max_tokens", sa.Integer(), nullable=False),
            sa.Column("supports_vision", sa.Boolean(), nullable=False),
            sa.Column("supports_tools", sa.Boolean(), nullable=False),
            sa.Column("supports_reasoning", sa.Boolean(), nullable=False),
            sa.Column("compat_config", _jsonb(), nullable=True),
            sa.Column("pricing", _jsonb(), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            *user_fk,
            sa.UniqueConstraint(
                "user_uid", "provider_id", "model_id", name="uq_user_custom_model"
            ),
        )
        op.create_index(
            "ix_user_custom_model_user_uid", "user_custom_model", ["user_uid"]
        )
    if not inspector.has_table("user_model_preferences"):
        op.create_table(
            "user_model_preferences",
            sa.Column("user_uid", sa.String(), primary_key=True),
            sa.Column("config_mode", sa.String(length=16), nullable=False),
            sa.Column("default_model_ref", JSONB(none_as_null=True), nullable=True),
            sa.Column(
                "default_vision_model_ref", JSONB(none_as_null=True), nullable=True
            ),
            sa.Column("default_thinking_level", sa.String(length=16), nullable=False),
            sa.Column("runtime_options", _jsonb(), nullable=True),
            sa.Column("slot_bindings", _jsonb(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            *user_fk,
            sa.CheckConstraint(
                "config_mode IN ('simple', 'advanced')",
                name="ck_user_model_preferences_config_mode",
            ),
        )
    if not inspector.has_table("user_model_usage_log"):
        op.create_table(
            "user_model_usage_log",
            sa.Column("usage_id", sa.String(length=32), primary_key=True),
            sa.Column("user_uid", sa.String(), nullable=False),
            sa.Column("request_id", sa.String(length=128), nullable=True),
            sa.Column("scene", sa.String(length=64), nullable=False),
            sa.Column("provider_id", sa.String(length=64), nullable=False),
            sa.Column("model_id", sa.String(length=128), nullable=False),
            sa.Column("thinking_level", sa.String(length=16), nullable=True),
            sa.Column("input_tokens", sa.Integer(), nullable=False),
            sa.Column("output_tokens", sa.Integer(), nullable=False),
            sa.Column("cache_read_tokens", sa.Integer(), nullable=False),
            sa.Column("cache_write_tokens", sa.Integer(), nullable=False),
            sa.Column("reasoning_tokens", sa.Integer(), nullable=False),
            sa.Column("estimated_cost_usd", sa.Float(), nullable=False),
            sa.Column("latency_ms", sa.Integer(), nullable=False),
            sa.Column("success", sa.Boolean(), nullable=False),
            sa.Column("error_code", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            *user_fk,
        )
        op.create_index(
            "idx_user_model_usage_user_time",
            "user_model_usage_log",
            ["user_uid", "created_at"],
        )
        op.create_index(
            "idx_user_model_usage_user_scene",
            "user_model_usage_log",
            ["user_uid", "scene"],
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table in TABLES:
        if inspector.has_table(table):
            op.drop_table(table)
