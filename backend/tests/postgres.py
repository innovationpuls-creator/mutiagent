from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

import sqlalchemy
from sqlalchemy import text
from sqlalchemy.engine import make_url

DEFAULT_DATABASE_URL = "postgresql://mutiagent:mutiagent@localhost:5432/mutiagent"

_schema_by_key: dict[tuple[str, str], str] = {}


def postgresql_test_url(tmp_path: Path, database_name: str) -> str:
    key = (str(tmp_path), database_name)
    if key not in _schema_by_key:
        schema_name = _schema_name(database_name)
        _schema_by_key[key] = schema_name
        base_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
        engine = sqlalchemy.create_engine(base_url)
        try:
            with engine.connect() as conn:
                conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema_name}"))
                conn.commit()
        finally:
            engine.dispose()

    base_url = make_url(os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL))
    query = dict(base_url.query)
    query["options"] = f"-c search_path={_schema_by_key[key]}"
    return base_url.set(query=query).render_as_string(hide_password=False)


def _schema_name(database_name: str) -> str:
    normalized_name = re.sub(r"[^A-Za-z0-9_]+", "_", database_name).strip("_")
    if not normalized_name:
        normalized_name = "test"
    return f"test_{normalized_name.lower()}_{uuid.uuid4().hex[:8]}"
