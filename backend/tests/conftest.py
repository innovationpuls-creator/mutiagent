from __future__ import annotations

import pytest

from tests.postgres import (
    cleanup_orphaned_test_schemas,
    cleanup_registered_test_schemas,
)


@pytest.fixture(scope="session", autouse=True)
def cleanup_orphaned_postgres_test_schemas() -> None:
    cleanup_orphaned_test_schemas()
    yield
    cleanup_orphaned_test_schemas()


@pytest.fixture(autouse=True)
def cleanup_registered_postgres_test_schemas() -> None:
    yield
    cleanup_registered_test_schemas()
