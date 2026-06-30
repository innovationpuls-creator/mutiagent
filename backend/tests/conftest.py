from __future__ import annotations

import os
from typing import Generator

import pytest
import sqlalchemy
from sqlalchemy import text

from tests.postgres import DEFAULT_DATABASE_URL


@pytest.fixture(scope="session", autouse=True)
def cleanup_postgres_test_schemas() -> Generator[None, None, None]:
    yield
    database_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    engine = sqlalchemy.create_engine(database_url)
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT schema_name FROM information_schema.schemata "
                    "WHERE schema_name LIKE 'test_%'"
                )
            )
            schemas = [row[0] for row in result.all()]
            for schema in schemas:
                conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            conn.commit()
    except Exception as e:
        print(f"Error cleaning up test schemas: {e}")
    finally:
        engine.dispose()
