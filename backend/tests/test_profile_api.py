from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine

from app.main import create_app
from app.models import UserProfile


def _register(client: TestClient) -> tuple[str, str]:
    response = client.post(
        "/api/auth/register",
        json={
            "username": "画像读取用户",
            "identifier": "profile-read@example.com",
            "password": "test-password-123",
            "confirm_password": "test-password-123",
        },
    )
    body = response.json()
    return body["access_token"], body["user"]["uid"]


def test_profile_dashboard_requires_auth(tmp_path: Path) -> None:
    client = TestClient(create_app(database_url=f"sqlite:///{tmp_path / 'profile-auth.db'}"))

    response = client.get("/api/profile/dashboard")

    assert response.status_code == 401


def test_profile_dashboard_returns_empty_state_before_profile_generated(tmp_path: Path) -> None:
    client = TestClient(create_app(database_url=f"sqlite:///{tmp_path / 'profile-empty.db'}"))
    token, _ = _register(client)

    response = client.get("/api/profile/dashboard", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["profileCompleteness"] == 0
    assert body["profile"]["major"] == "暂未确认"
    assert body["recommendations"] == []


def test_profile_dashboard_reads_saved_profile(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'profile-saved.db'}"
    client = TestClient(create_app(database_url=database_url))
    token, uid = _register(client)
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    with Session(engine) as session:
        session.add(
            UserProfile(
                user_uid=uid,
                profile_data={
                    "type": "basic_profile",
                    "stage": "generated",
                    "confirmed_info": {
                        "current_grade": "大三",
                        "major": "软件工程",
                        "learning_stage": "课程与项目并行",
                        "content_preference": ["视频", "代码实践"],
                        "short_term_goal": "提升 AI 应用开发能力",
                        "weaknesses": "算法和系统设计",
                        "weekly_available_time": "每周 8 小时",
                    },
                    "text": "【用户基础信息】\n大三软件工程，课程与项目并行。",
                },
                profile_text="【用户基础信息】\n大三软件工程，课程与项目并行。",
            )
        )
        session.commit()

    response = client.get("/api/profile/dashboard", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["currentGrade"] == "大三"
    assert body["profile"]["major"] == "软件工程"
    assert body["profile"]["contentPreference"] == ["视频", "代码实践"]
    assert body["profileCompleteness"] > 0
    assert body["todayLearning"]["source"] == "基础画像 Agent"
