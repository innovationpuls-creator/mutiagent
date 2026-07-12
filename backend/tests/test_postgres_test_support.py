from __future__ import annotations

from pathlib import Path

import sqlalchemy
from sqlalchemy import text

from tests.postgres import cleanup_registered_test_schemas, postgresql_test_url


def test_cleanup_registered_test_schemas_drops_created_schemas(tmp_path: Path) -> None:
    first_url = postgresql_test_url(tmp_path, "cleanup-first")
    second_url = postgresql_test_url(tmp_path, "cleanup-second")
    first_schema = _schema_name(first_url)
    second_schema = _schema_name(second_url)

    cleanup_registered_test_schemas()

    engine = sqlalchemy.create_engine(first_url)
    try:
        with engine.connect() as connection:
            remaining_schemas = {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT schema_name FROM information_schema.schemata "
                        "WHERE schema_name IN (:first_schema, :second_schema)"
                    ),
                    {"first_schema": first_schema, "second_schema": second_schema},
                )
            }
    finally:
        engine.dispose()

    assert remaining_schemas == set()


def _schema_name(database_url: str) -> str:
    options = sqlalchemy.engine.make_url(database_url).query["options"]
    return options.removeprefix("-c search_path=")
