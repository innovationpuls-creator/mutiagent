from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.config import load_settings
from app.database import build_engine
from app.main import create_app
from app.models import User
from tests.postgres import postgresql_test_url


def make_client(tmp_path: Path) -> TestClient:
    database_url = postgresql_test_url(tmp_path, "auth-test")
    return TestClient(create_app(database_url=database_url))


def test_register_persists_user_and_returns_jwt(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post(
        "/api/auth/register",
        json={
            "username": "林小鹿",
            "identifier": "lin@example.com",
            "password": "learn-agent-123",
            "confirm_password": "learn-agent-123",
            "school": "南山大学",
            "major": "软件工程",
            "class_name": "一班",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 20
    assert body["user"]["username"] == "林小鹿"
    assert body["user"]["identifier"] == "lin@example.com"
    assert body["user"]["role"] == "student"
    assert body["user"]["school"] == "南山大学"
    assert body["user"]["major"] == "软件工程"
    assert body["user"]["class_name"] == "一班"
    assert "uid" in body["user"]
    assert "-" in body["user"]["uid"]

    login_response = client.post(
        "/api/auth/login",
        json={"account": "lin@example.com", "password": "learn-agent-123"},
    )

    assert login_response.status_code == 200
    assert login_response.json()["user"]["username"] == "林小鹿"
    assert login_response.json()["user"]["role"] == "student"


def test_register_can_create_admin_role(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post(
        "/api/auth/register",
        json={
            "username": "管理员用户",
            "identifier": "admin@example.com",
            "password": "learn-agent-123",
            "confirm_password": "learn-agent-123",
            "role": "admin",
            "school": "南山大学",
            "major": "软件工程",
            "class_name": "一班",
        },
    )

    assert response.status_code == 201
    assert response.json()["user"]["role"] == "admin"


def test_register_rejects_class_name_equal_to_identifier(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post(
        "/api/auth/register",
        json={
            "username": "错误班级",
            "identifier": "18771701100",
            "password": "learn-agent-123",
            "confirm_password": "learn-agent-123",
            "school": "wc",
            "major": "计算机",
            "class_name": "18771701100",
        },
    )

    assert response.status_code == 422
    assert "班级不能填写登录标识" in response.text


def test_init_db_creates_admin_from_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_USERNAME", "管理员")
    monkeypatch.setenv("ADMIN_IDENTIFIER", "admin@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-password-123")
    client = make_client(tmp_path)

    response = client.post(
        "/api/auth/login",
        json={"account": "admin@example.com", "password": "admin-password-123"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["username"] == "管理员"
    assert body["user"]["role"] == "admin"


def test_production_startup_does_not_create_demo_user(tmp_path: Path) -> None:
    database_url = postgresql_test_url(tmp_path, "production-no-demo")
    settings = load_settings(
        {
            "APP_ENV": "production",
            "DATABASE_URL": database_url,
            "JWT_SECRET": "production-no-demo-jwt-secret",
            "LLM_API_KEY": "production-no-demo-llm-api-key",
            "LLM_MODEL": "production-no-demo-llm-model",
            "ALLOWED_ORIGINS": "https://onetree.chat",
        }
    )

    create_app(database_url=database_url, settings=settings)

    with Session(build_engine(database_url)) as session:
        demo_user = session.exec(
            select(User).where(User.identifier == "demo@mutiagent.local")
        ).first()
    assert demo_user is None


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
    assert body["user"]["role"] == "student"


def test_me_returns_current_user_with_valid_token(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    register_response = client.post(
        "/api/auth/register",
        json={
            "username": "测试用户",
            "identifier": "me-test@example.com",
            "password": "test-password-123",
            "confirm_password": "test-password-123",
            "school": "南山大学",
            "major": "软件工程",
            "class_name": "二班",
        },
    )
    token = register_response.json()["access_token"]

    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "测试用户"
    assert body["identifier"] == "me-test@example.com"
    assert body["role"] == "student"
    assert body["school"] == "南山大学"
    assert body["major"] == "软件工程"
    assert body["class_name"] == "二班"


def test_me_rejects_invalid_token(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401


def test_me_rejects_missing_token(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/api/auth/me")

    assert response.status_code == 401


def test_login_updates_last_login_at(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    client.post(
        "/api/auth/register",
        json={
            "username": "时间测试",
            "identifier": "time-test@example.com",
            "password": "test-password-123",
            "confirm_password": "test-password-123",
            "school": "南山大学",
            "major": "软件工程",
            "class_name": "三班",
        },
    )

    login_response = client.post(
        "/api/auth/login",
        json={"account": "time-test@example.com", "password": "test-password-123"},
    )
    me_before = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {login_response.json()['access_token']}"},
    )
    assert me_before.json()["last_login_at"] is not None
