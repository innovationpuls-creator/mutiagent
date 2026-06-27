from __future__ import annotations

import os
import re
import uuid
from typing import Generator

import pytest
import sqlalchemy
import sqlmodel
from sqlalchemy import ForeignKeyConstraint, text

# Force import of application models to populate SQLModel.metadata.tables
import app.models  # noqa: F401

# Save original create_engine functions
original_sqlalchemy_create_engine = sqlalchemy.create_engine
original_sqlmodel_create_engine = sqlmodel.create_engine

# Cache schema names mapped from SQLite database URLs
_sqlite_to_schema_map: dict[str, str] = {}

# Strip foreign keys from SQLModel metadata to match SQLite test assumptions
for table in sqlmodel.SQLModel.metadata.tables.values():
    fk_constraints = [
        c for c in table.constraints if isinstance(c, ForeignKeyConstraint)
    ]
    for fk in fk_constraints:
        table.constraints.remove(fk)
    for column in table.columns:
        column.foreign_keys.clear()


def custom_create_engine(url: str, *args, **kwargs) -> sqlalchemy.engine.Engine:
    url_str = str(url)
    if url_str.startswith("sqlite"):
        if url_str not in _sqlite_to_schema_map:
            match = re.search(r"([^/]+)\.db$", url_str)
            db_name = (
                match.group(1).replace("-", "_").replace(".", "_")
                if match
                else "sqlite"
            )
            schema_name = f"test_{db_name}_{uuid.uuid4().hex[:8]}"
            _sqlite_to_schema_map[url_str] = schema_name

            base_url = os.getenv(
                "DATABASE_URL",
                "postgresql://mutiagent:mutiagent@localhost:5432/mutiagent",
            )
            temp_engine = original_sqlalchemy_create_engine(base_url)
            with temp_engine.connect() as conn:
                conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema_name}"))
                conn.commit()
            temp_engine.dispose()
        else:
            schema_name = _sqlite_to_schema_map[url_str]

        base_url = os.getenv(
            "DATABASE_URL",
            "postgresql://mutiagent:mutiagent@localhost:5432/mutiagent",
        )

        connect_args = kwargs.get("connect_args", {})
        if "check_same_thread" in connect_args:
            connect_args = dict(connect_args)
            connect_args.pop("check_same_thread", None)
            kwargs["connect_args"] = connect_args

        kwargs["connect_args"] = {
            **connect_args,
            "options": f"-c search_path={schema_name}",
        }
        return original_sqlalchemy_create_engine(base_url, *args, **kwargs)
    return original_sqlalchemy_create_engine(url, *args, **kwargs)


# Monkeypatch create_engine
sqlalchemy.create_engine = custom_create_engine
sqlmodel.create_engine = custom_create_engine


@pytest.fixture(scope="session", autouse=True)
def cleanup_postgres_test_schemas() -> Generator[None, None, None]:
    yield
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://mutiagent:mutiagent@localhost:5432/mutiagent",
    )
    engine = original_sqlalchemy_create_engine(database_url)
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
