from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.core.config import load_settings
from app.main import create_app
from app.migration_state import migrate_to_head
from tests.postgres import postgresql_test_url


def make_client(tmp_path: Path, allowed_origins: str) -> TestClient:
    database_url = postgresql_test_url(tmp_path, "cors-test")
    migrate_to_head(create_engine(database_url))
    settings = load_settings(
        {
            "APP_ENV": "production",
            "DATABASE_URL": database_url,
            "JWT_SECRET": "cors-test-jwt-secret",
            "LLM_API_KEY": "cors-test-llm-api-key",
            "LLM_MODEL": "cors-test-llm-model",
            "ALLOWED_ORIGINS": allowed_origins,
        }
    )
    return TestClient(create_app(database_url=database_url, settings=settings))


def test_production_cors_allows_configured_origin(tmp_path: Path) -> None:
    client = make_client(tmp_path, "https://onetree.chat")

    response = client.options(
        "/api/health",
        headers={
            "Origin": "https://onetree.chat",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://onetree.chat"


def test_production_cors_rejects_unconfigured_origin(tmp_path: Path) -> None:
    client = make_client(tmp_path, "https://onetree.chat")

    response = client.options(
        "/api/health",
        headers={
            "Origin": "https://app.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert "access-control-allow-origin" not in response.headers
