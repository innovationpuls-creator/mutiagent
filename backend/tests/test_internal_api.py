from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlmodel import Session

from app.core.config import DEFAULT_INTERNAL_API_TOKEN, load_settings
from app.database import DEMO_USER_UID
from app.main import create_app
from app.migration_state import migrate_to_head
from app.models import User
from tests.postgres import postgresql_test_url

TOKEN_HEADER = "X-Internal-Token"
DISABLED_UID = "00000000-0000-0000-0000-0000000000d1"


def make_client(tmp_path: Path, name: str = "internal-api") -> TestClient:
    database_url = postgresql_test_url(tmp_path, name)
    return TestClient(create_app(database_url=database_url))


def auth_headers(**extra: str) -> dict[str, str]:
    return {TOKEN_HEADER: DEFAULT_INTERNAL_API_TOKEN, **extra}


def test_missing_token_is_rejected_with_401(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/internal/health")

    assert response.status_code == 401
    assert response.json() == {"detail": "缺少内部令牌"}


def test_wrong_token_is_rejected_with_403(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/internal/health", headers={TOKEN_HEADER: "wrong-token"})

    assert response.status_code == 403
    assert response.json() == {"detail": "内部令牌无效"}


def test_non_ascii_wrong_token_is_rejected_with_403(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get(
        "/internal/health", headers={TOKEN_HEADER.encode(): "错误令牌".encode()}
    )

    assert response.status_code == 403


def test_correct_token_returns_health_and_logs_request_id(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    client = make_client(tmp_path)
    caplog.set_level(logging.INFO, logger="app.access")

    response = client.get(
        "/internal/health", headers=auth_headers(**{"X-Request-ID": "m1-trace-001"})
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}
    assert response.headers["X-Request-ID"] == "m1-trace-001"
    record = next(r for r in caplog.records if r.name == "app.access")
    assert record.request_id == "m1-trace-001"
    assert record.path == "/internal/health"
    assert record.status_code == 200
    assert DEFAULT_INTERNAL_API_TOKEN not in caplog.text


def test_token_never_logged_on_rejected_requests(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    client = make_client(tmp_path)
    caplog.set_level(logging.INFO)

    client.get("/internal/health", headers={TOKEN_HEADER: "wrong-secret-value"})
    client.get("/internal/health", headers=auth_headers())

    assert "wrong-secret-value" not in caplog.text
    assert DEFAULT_INTERNAL_API_TOKEN not in caplog.text


def test_auth_status_for_demo_user(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get(
        f"/internal/users/{DEMO_USER_UID}/auth-status", headers=auth_headers()
    )

    assert response.status_code == 200
    assert response.json() == {
        "user_uid": DEMO_USER_UID,
        "exists": True,
        "role": "student",
        "is_active": True,
    }


def test_auth_status_for_disabled_user(tmp_path: Path) -> None:
    database_url = postgresql_test_url(tmp_path, "internal-api-disabled")
    client = TestClient(create_app(database_url=database_url))
    engine = create_engine(database_url)
    with Session(engine) as session:
        session.add(
            User(
                uid=DISABLED_UID,
                username="disabled",
                identifier="disabled@mutiagent.local",
                role="student",
                is_active=False,
            )
        )
        session.commit()
    engine.dispose()

    response = client.get(
        f"/internal/users/{DISABLED_UID}/auth-status", headers=auth_headers()
    )

    assert response.status_code == 200
    assert response.json() == {
        "user_uid": DISABLED_UID,
        "exists": True,
        "role": "student",
        "is_active": False,
    }


def test_auth_status_for_unknown_user(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get(
        "/internal/users/does-not-exist/auth-status", headers=auth_headers()
    )

    assert response.status_code == 200
    assert response.json() == {
        "user_uid": "does-not-exist",
        "exists": False,
        "role": None,
        "is_active": False,
    }


def test_auth_status_requires_token(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get(f"/internal/users/{DEMO_USER_UID}/auth-status")

    assert response.status_code == 401


def test_openapi_schema_hides_internal_routes(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    schema = client.get("/openapi.json").json()

    assert not any(path.startswith("/internal") for path in schema["paths"])
    assert "/internal" not in str(schema)


def production_environ(database_url: str) -> dict[str, str]:
    return {
        "APP_ENV": "production",
        "DATABASE_URL": database_url,
        "JWT_SECRET": "internal-test-jwt-secret",
        "INTERNAL_API_TOKEN": "test-production-internal-token",
        "AI_GATEWAY_URL": "http://ai-gateway:8100",
        "MODEL_SECRET_ENCRYPTION_KEY": "test-production-model-secret-key",
        "ALLOWED_ORIGINS": "https://onetree.chat",
    }


def make_production_client(tmp_path: Path, internal_token: str | None) -> TestClient:
    database_url = postgresql_test_url(tmp_path, "internal-api-prod")
    migrate_to_head(create_engine(database_url))
    environ = production_environ(database_url)
    if internal_token is not None:
        environ["INTERNAL_API_TOKEN"] = internal_token
    settings = load_settings(environ)
    if internal_token is None:
        # Production refuses to load without a token; the app itself must still fail
        # closed if settings are ever built without one.
        settings = replace(settings, internal_api_token=None)
    return TestClient(create_app(database_url=database_url, settings=settings))


def test_production_without_internal_token_fails_closed(tmp_path: Path) -> None:
    client = make_production_client(tmp_path, None)

    response = client.get("/internal/health", headers=auth_headers())
    missing = client.get("/internal/health")

    assert response.status_code == 403
    assert response.json() == {"detail": "内部接口未启用"}
    assert missing.status_code == 401


def test_production_with_internal_token_accepts_it(tmp_path: Path) -> None:
    client = make_production_client(tmp_path, "prod-internal-test-token")

    ok = client.get(
        "/internal/health", headers={TOKEN_HEADER: "prod-internal-test-token"}
    )
    default = client.get("/internal/health", headers=auth_headers())

    assert ok.status_code == 200
    assert default.status_code == 403
    assert default.json() == {"detail": "内部令牌无效"}


def test_development_default_token_emits_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="app.main")

    make_client(tmp_path, "internal-api-warn")

    assert any(
        r.name == "app.main" and r.levelno == logging.WARNING for r in caplog.records
    )
    assert DEFAULT_INTERNAL_API_TOKEN not in caplog.text
