from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def make_client(tmp_path: Path) -> TestClient:
    database_url = f"sqlite:///{tmp_path / 'cors-test.db'}"
    return TestClient(create_app(database_url=database_url))


def test_cors_preflight_allows_public_https_origin(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.options(
        "/api/health",
        headers={
            "Origin": "https://app.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://app.example.com"

