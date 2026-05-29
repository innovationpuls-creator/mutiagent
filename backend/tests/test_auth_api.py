from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def make_client(tmp_path: Path) -> TestClient:
    database_url = f"sqlite:///{tmp_path / 'auth-test.db'}"
    return TestClient(create_app(database_url=database_url))


def test_register_persists_user_and_returns_token(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post(
        "/api/auth/register",
        json={
            "username": "林小鹿",
            "identifier": "lin@example.com",
            "password": "learn-agent-123",
            "confirm_password": "learn-agent-123",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["token"].startswith("mock-token-")
    assert body["user"]["username"] == "林小鹿"
    assert body["user"]["identifier"] == "lin@example.com"

    login_response = client.post(
        "/api/auth/login",
        json={"account": "lin@example.com", "password": "learn-agent-123"},
    )

    assert login_response.status_code == 200
    assert login_response.json()["user"]["username"] == "林小鹿"


def test_login_rejects_wrong_password(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post(
        "/api/auth/login",
        json={"account": "demo@mutiagent.local", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "账号或密码不正确"


def test_mock_oauth_creates_provider_user(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post(
        "/api/auth/oauth/mock",
        json={"provider": "xuexitong", "authorization_code": "mock-code"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["auth_type"] == "oauth"
    assert body["user"]["provider"] == "xuexitong"
    assert body["user"]["identifier"].endswith("@mock.local")
