from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import load_settings
from app.main import create_app
from app.models import User
from tests.postgres import postgresql_test_url


def _production_settings(database_url: str):
    return load_settings(
        {
            "APP_ENV": "production",
            "DATABASE_URL": database_url,
            "JWT_SECRET": "alembic-production-jwt-secret",
            "LLM_API_KEY": "alembic-test-llm-api-key",
            "LLM_MODEL": "alembic-test-model",
            "ALLOWED_ORIGINS": "https://onetree.chat",
        }
    )


def test_empty_schema_upgrades_to_alembic_head(tmp_path: Path) -> None:
    from alembic import command
    from alembic.config import Config

    database_url = postgresql_test_url(tmp_path, "alembic-empty")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    table_names = set(inspect(engine).get_table_names())
    assert table_names == set(SQLModel.metadata.tables) | {"alembic_version"}
    with engine.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version"))
        assert revision.scalar_one() == "0001_production_baseline"


def test_current_sqlmodel_schema_is_current_unversioned(tmp_path: Path) -> None:
    from app.migration_state import inspect_schema_state

    engine = create_engine(postgresql_test_url(tmp_path, "alembic-current"))
    SQLModel.metadata.create_all(engine)

    assert inspect_schema_state(engine) == "current_unversioned"


def test_schema_missing_exact_model_column_is_legacy(tmp_path: Path) -> None:
    from app.migration_state import inspect_schema_state, migrate_to_head

    engine = create_engine(postgresql_test_url(tmp_path, "alembic-legacy"))
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE "user" (uid VARCHAR PRIMARY KEY)'))

    assert inspect_schema_state(engine) == "legacy"
    with pytest.raises(RuntimeError, match="legacy"):
        migrate_to_head(engine)


def test_schema_with_wrong_exact_column_type_is_legacy(tmp_path: Path) -> None:
    from app.migration_state import inspect_schema_state

    engine = create_engine(postgresql_test_url(tmp_path, "alembic-wrong-type"))
    SQLModel.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text('ALTER TABLE "user" ALTER COLUMN username TYPE TEXT'))

    assert inspect_schema_state(engine) == "legacy"


def test_schema_missing_exact_unique_constraint_is_legacy(tmp_path: Path) -> None:
    from app.migration_state import inspect_schema_state

    engine = create_engine(postgresql_test_url(tmp_path, "alembic-missing-constraint"))
    SQLModel.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE textbooksectioncontent "
                "DROP CONSTRAINT uq_textbooksectioncontent_textbook_section"
            )
        )

    assert inspect_schema_state(engine) == "legacy"


def test_current_unversioned_schema_is_verified_before_stamp(tmp_path: Path) -> None:
    from app.migration_state import (
        assert_schema_at_head,
        inspect_schema_state,
        migrate_to_head,
    )

    engine = create_engine(postgresql_test_url(tmp_path, "alembic-stamp-current"))
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            User(
                uid="existing-user",
                username="现有用户",
                identifier="existing@example.com",
            )
        )
        session.commit()

    migrate_to_head(engine)

    assert inspect_schema_state(engine) == "versioned"
    assert_schema_at_head(engine)
    with Session(engine) as session:
        assert session.get(User, "existing-user") is not None


def test_production_create_app_does_not_run_startup_ddl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_url = postgresql_test_url(tmp_path, "production-no-startup-ddl")

    def fail_startup_ddl(*_args, **_kwargs) -> None:
        raise AssertionError("production startup executed DDL")

    monkeypatch.setattr("app.main.init_db", fail_startup_ddl)
    monkeypatch.setattr("app.main.assert_schema_at_head", lambda _engine: None)

    create_app(database_url=database_url, settings=_production_settings(database_url))
