from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from tests.postgres import postgresql_test_url

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def make_client(tmp_path: Path) -> TestClient:
    database_url = postgresql_test_url(tmp_path, "request-id")
    return TestClient(create_app(database_url=database_url))


def test_response_reuses_valid_incoming_request_id(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/api/health", headers={"X-Request-ID": "req-123"})

    assert response.headers["X-Request-ID"] == "req-123"


def test_response_generates_request_id_when_missing(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/api/health")

    assert REQUEST_ID_PATTERN.fullmatch(response.headers["X-Request-ID"])


def test_response_replaces_invalid_request_id(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/api/health", headers={"X-Request-ID": "invalid id"})

    assert response.headers["X-Request-ID"] != "invalid id"
    assert REQUEST_ID_PATTERN.fullmatch(response.headers["X-Request-ID"])


def test_access_log_contains_matching_request_id_without_credentials(
    tmp_path: Path, caplog
) -> None:
    client = make_client(tmp_path)
    caplog.set_level(logging.INFO, logger="app.access")

    response = client.post(
        "/api/auth/login",
        headers={"X-Request-ID": "req-login"},
        json={"account": "demo@mutiagent.local", "password": "secret-password"},
    )

    assert response.status_code == 401
    record = next(record for record in caplog.records if record.name == "app.access")
    assert record.request_id == "req-login"
    assert record.method == "POST"
    assert record.path == "/api/auth/login"
    assert record.status_code == 401
    assert record.duration_ms >= 0
    assert "secret-password" not in caplog.text
    assert "Authorization" not in caplog.text
