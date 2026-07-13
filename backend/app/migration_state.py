from __future__ import annotations

from typing import Literal

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Float, Table, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.engine.reflection import Inspector
from sqlmodel import SQLModel

SchemaState = Literal["empty", "current_unversioned", "legacy", "versioned"]


def inspect_schema_state(engine: Engine) -> SchemaState:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "alembic_version" in table_names:
        return "versioned"

    expected_tables = set(SQLModel.metadata.tables)
    if not table_names:
        return "empty"
    if table_names != expected_tables:
        return "legacy"
    if not _matches_current_metadata(engine):
        return "legacy"
    return "current_unversioned"


def assert_schema_at_head(engine: Engine) -> None:
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)
    expected_heads = set(script.get_heads())
    with engine.connect() as connection:
        current_heads = set(MigrationContext.configure(connection).get_current_heads())
    if current_heads != expected_heads:
        raise RuntimeError("数据库迁移版本不是 Alembic head")


def migrate_to_head(engine: Engine) -> None:
    state = inspect_schema_state(engine)
    if state == "legacy":
        raise RuntimeError("legacy 数据库结构不能自动 stamp")

    config = _alembic_config(engine)
    if state == "current_unversioned":
        command.stamp(config, "head")
        return
    command.upgrade(config, "head")


def _alembic_config(engine: Engine) -> Config:
    config = Config("alembic.ini")
    database_url = engine.url.render_as_string(hide_password=False)
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def _matches_current_metadata(engine: Engine) -> bool:
    inspector = inspect(engine)
    return all(
        _table_matches_metadata(engine, inspector, table_name, table)
        for table_name, table in SQLModel.metadata.tables.items()
    )


def _table_matches_metadata(
    engine: Engine, inspector: Inspector, table_name: str, table: Table
) -> bool:
    actual_columns = {
        column["name"]: column for column in inspector.get_columns(table_name)
    }
    if set(actual_columns) != set(table.columns.keys()):
        return False
    for column in table.columns:
        actual = actual_columns[column.name]
        if _type_signature(actual["type"], engine) != _type_signature(
            column.type, engine
        ):
            return False
        if bool(actual["nullable"]) != bool(column.nullable):
            return False

    expected_primary_key = tuple(column.name for column in table.primary_key.columns)
    actual_primary_key = tuple(
        inspector.get_pk_constraint(table_name)["constrained_columns"]
    )
    if actual_primary_key != expected_primary_key:
        return False

    expected_unique = {
        (constraint.name, tuple(column.name for column in constraint.columns))
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    actual_unique = {
        (constraint["name"], tuple(constraint["column_names"]))
        for constraint in inspector.get_unique_constraints(table_name)
    }
    if actual_unique != expected_unique:
        return False

    expected_checks = {
        constraint.name
        for constraint in table.constraints
        if constraint.__class__.__name__ == "CheckConstraint"
    }
    actual_checks = {
        constraint["name"] for constraint in inspector.get_check_constraints(table_name)
    }
    if actual_checks != expected_checks:
        return False

    expected_foreign_keys = {
        (
            tuple(element.parent.name for element in constraint.elements),
            constraint.referred_table.name,
            tuple(element.column.name for element in constraint.elements),
        )
        for constraint in table.foreign_key_constraints
    }
    actual_foreign_keys = {
        (
            tuple(constraint["constrained_columns"]),
            constraint["referred_table"],
            tuple(constraint["referred_columns"]),
        )
        for constraint in inspector.get_foreign_keys(table_name)
    }
    if actual_foreign_keys != expected_foreign_keys:
        return False

    expected_indexes = {
        (index.name, tuple(column.name for column in index.columns), index.unique)
        for index in table.indexes
    }
    actual_indexes = {
        (index["name"], tuple(index["column_names"]), bool(index["unique"]))
        for index in inspector.get_indexes(table_name)
        if not index.get("duplicates_constraint")
    }
    return actual_indexes == expected_indexes


def _type_signature(column_type: object, engine: Engine) -> tuple[object, ...]:
    item_type = getattr(column_type, "item_type", None)
    if item_type is not None:
        return (column_type._type_affinity, _type_signature(item_type, engine))
    precision = getattr(column_type, "precision", None)
    if isinstance(column_type, Float) and precision is None:
        precision = 53
    return (
        column_type._type_affinity,
        getattr(column_type, "length", None),
        precision,
        getattr(column_type, "scale", None),
        getattr(column_type, "timezone", None),
    )
