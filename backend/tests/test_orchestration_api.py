from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine

from app.api import orchestration as orchestration_api
from app.main import create_app
from app.models import UserAgentConversation


class EchoSessionGraph:
    def __init__(self) -> None:
        self.states: list[dict] = []
        self.configs: list[dict] = []

    async def ainvoke(self, state: dict, config: dict) -> dict:
        self.states.append(state.copy())
        self.configs.append(config)
        return {
            **state,
            "answer": {"user_message": f"会话：{state['query']}", "question_box": None},
            "agent_trace": [],
            "agent_results": {},
            "profile": None,
            "learning_path": None,
            "completed": False,
            "error": "",
        }


def register(client: TestClient, identifier: str) -> tuple[str, str]:
    response = client.post(
        "/api/auth/register",
        json={
            "username": "编排用户",
            "identifier": identifier,
            "password": "test-password-123",
            "confirm_password": "test-password-123",
        },
    )
    body = response.json()
    return body["access_token"], body["user"]["uid"]


def test_chatflow_routes_are_removed(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'removed-chatflow.db'}"
    monkeypatch.setattr(orchestration_api, "graph", EchoSessionGraph())
    client = TestClient(create_app(database_url=database_url))
    token, _ = register(client, "removed-chatflow@example.com")

    response = client.post(
        "/api/orchestration/chatflow/start",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "旧入口"},
    )

    assert response.status_code == 404


def test_session_uses_user_scoped_graph_thread(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'session-thread.db'}"
    fake_graph = EchoSessionGraph()
    monkeypatch.setattr(orchestration_api, "graph", fake_graph)
    client = TestClient(create_app(database_url=database_url))
    token, uid = register(client, "session-thread@example.com")

    first = client.post(
        "/api/orchestration/sessions/start",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "第一次"},
    )
    second = client.post(
        "/api/orchestration/sessions/start",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "第二次"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    thread_ids = [config["configurable"]["thread_id"] for config in fake_graph.configs]
    assert thread_ids == [uid, uid]
    assert ":" not in thread_ids[0]


def test_completed_profile_session_returns_main_agent_final(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'profile-final.db'}"
    client = TestClient(create_app(database_url=database_url))
    token, uid = register(client, "profile-final@example.com")
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    with Session(engine) as session:
        session.add(UserAgentConversation(user_uid=uid, agent_key="profile_agent", conversation_id="profile-conv"))
        session.commit()

    async def completed_profile_state(state: dict, session: Session) -> dict:
        return {
            **state,
            "answer": {"user_message": "画像完成", "question_box": None},
            "agent_results": {"profile": {"type": "basic_profile", "stage": "generated", "text": "画像"}},
            "agent_trace": [],
            "profile": {"type": "basic_profile", "stage": "generated", "text": "画像"},
            "user_profile": {"type": "basic_profile", "stage": "generated", "text": "画像"},
            "learning_path": None,
            "awaiting_profile": False,
            "completed": True,
            "error": "",
        }

    async def final_state(state: dict, session: Session) -> dict:
        return {
            **state,
            "answer": {"user_message": "主智能体最终总结", "question_box": None},
            "completed": True,
            "error": "",
        }

    monkeypatch.setattr(orchestration_api, "_profile_session_state", completed_profile_state)
    monkeypatch.setattr(orchestration_api, "_finalize_completed_profile_state", final_state)

    response = client.post(
        "/api/orchestration/sessions/start",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "补充完成"},
    )

    assert response.status_code == 200
    assert response.json()["answer"]["user_message"] == "主智能体最终总结"
