"""Remove teacher legacy columns/roles and unused textbook embedding column."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0006_admin_program_drop_embed"
down_revision = "0005_quiz_submission_recovery"
branch_labels = None
depends_on = None


def _rename_program_column(
    *,
    from_col: str,
    to_col: str,
    old_indexes: tuple[str, str],
    new_indexes: tuple[str, str],
    old_fk: str,
    new_fk: str,
) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("cultivationprogram"):
        return

    columns = {column["name"] for column in inspector.get_columns("cultivationprogram")}
    if from_col in columns and to_col not in columns:
        op.alter_column("cultivationprogram", from_col, new_column_name=to_col)
        inspector.clear_cache()

    indexes = {idx["name"] for idx in inspector.get_indexes("cultivationprogram")}
    for old_index in old_indexes:
        if old_index in indexes:
            op.drop_index(old_index, table_name="cultivationprogram")
    for new_index in new_indexes:
        if new_index not in indexes:
            op.create_index(new_index, "cultivationprogram", [to_col])

    if bind.dialect.name == "postgresql":
        fk_names = {
            fk["name"] for fk in inspector.get_foreign_keys("cultivationprogram")
        }
        if old_fk in fk_names and new_fk not in fk_names:
            op.execute(
                sa.text(
                    "ALTER TABLE cultivationprogram "
                    f"RENAME CONSTRAINT {old_fk} TO {new_fk}"
                )
            )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("user"):
        op.execute(sa.text("UPDATE \"user\" SET role = 'admin' WHERE role = 'teacher'"))

    if inspector.has_table("textbook"):
        textbook_columns = {
            column["name"] for column in inspector.get_columns("textbook")
        }
        if "embedding" in textbook_columns:
            op.drop_column("textbook", "embedding")

    _rename_program_column(
        from_col="teacher_uid",
        to_col="admin_uid",
        old_indexes=(
            "idx_cultivation_program_teacher",
            "ix_cultivationprogram_teacher_uid",
        ),
        new_indexes=(
            "idx_cultivation_program_admin",
            "ix_cultivationprogram_admin_uid",
        ),
        old_fk="cultivationprogram_teacher_uid_fkey",
        new_fk="cultivationprogram_admin_uid_fkey",
    )


def downgrade() -> None:
    _rename_program_column(
        from_col="admin_uid",
        to_col="teacher_uid",
        old_indexes=(
            "idx_cultivation_program_admin",
            "ix_cultivationprogram_admin_uid",
        ),
        new_indexes=(
            "idx_cultivation_program_teacher",
            "ix_cultivationprogram_teacher_uid",
        ),
        old_fk="cultivationprogram_admin_uid_fkey",
        new_fk="cultivationprogram_teacher_uid_fkey",
    )

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("textbook"):
        textbook_columns = {
            column["name"] for column in inspector.get_columns("textbook")
        }
        if "embedding" not in textbook_columns:
            op.add_column(
                "textbook",
                sa.Column("embedding", ARRAY(sa.Float()), nullable=True),
            )
