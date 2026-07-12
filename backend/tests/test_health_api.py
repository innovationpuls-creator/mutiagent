from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.api.health import create_health_router
from app.main import create_app
from tests.postgres import postgresql_test_url


def test_liveness_does_not_query_database() -> None:
    app = FastAPI()
    broken_engine = create_engine(
        "postgresql://mutiagent:mutiagent@127.0.0.1:1/mutiagent"
    )
    app.include_router(create_health_router(broken_engine))
    client = TestClient(app)

    response = client.get("/api/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_fails_when_database_is_unavailable() -> None:
    app = FastAPI()
    broken_engine = create_engine(
        "postgresql://mutiagent:mutiagent@127.0.0.1:1/mutiagent"
    )
    app.include_router(create_health_router(broken_engine))
    client = TestClient(app)

    response = client.get("/api/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "error", "database": "unavailable"}


def test_readiness_and_legacy_health_report_database_state(tmp_path: Path) -> None:
    database_url = postgresql_test_url(tmp_path, "health-api")
    client = TestClient(create_app(database_url=database_url))

    readiness_response = client.get("/api/health/ready")
    legacy_response = client.get("/api/health")

    assert readiness_response.json() == {"status": "ok", "database": "connected"}
    assert legacy_response.json() == {"status": "ok", "database": "connected"}
