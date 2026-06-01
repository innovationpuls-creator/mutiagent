from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine

from app.api import orchestration as orchestration_api
from app.main import create_app
from app.models import UserLearningPath


class ReplyOnlyGraph:
    async def ainvoke(self, state: dict, config: dict) -> dict:
        return {
            **state,
            "session_id": state["session_id"],
            "answer": {"user_message": "你好，我可以帮你规划学习。", "question_box": None},
            "agent_trace": [],
            "agent_results": {},
            "profile": None,
            "learning_path": None,
            "completed": False,
            "error": "",
        }


class EchoSessionGraph:
    def __init__(self) -> None:
        self.states: list[dict] = []

    async def ainvoke(self, state: dict, config: dict) -> dict:
        self.states.append(state.copy())
        return {
            **state,
            "session_id": state["session_id"],
            "answer": {"user_message": f"继续：{state['query']}", "question_box": None},
            "agent_trace": [
                {
                    "step_id": "main_reply",
                    "agent_key": "main_agent",
                    "label": "主智能体",
                    "phase": "reply",
                    "status": "completed",
                    "message": "主智能体已回复。",
                    "depends_on": [],
                    "parallel_group": None,
                }
            ],
            "agent_results": {},
            "profile": None,
            "learning_path": None,
            "completed": False,
            "error": "",
        }


def register(client: TestClient, identifier: str = "sessions@example.com") -> tuple[str, str]:
    response = client.post(
        "/api/auth/register",
        json={
            "username": "会话用户",
            "identifier": identifier,
            "password": "test-password-123",
            "confirm_password": "test-password-123",
        },
    )
    body = response.json()
    return body["access_token"], body["user"]["uid"]


def test_start_session_returns_main_agent_answer(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'sessions.db'}"
    monkeypatch.setattr(orchestration_api, "graph", ReplyOnlyGraph())
    client = TestClient(create_app(database_url=database_url))
    token, _ = register(client)

    response = client.post(
        "/api/orchestration/sessions/start",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "你好"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"]
    assert body["answer"]["user_message"] == "你好，我可以帮你规划学习。"
    assert body["learning_path"] is None


def test_continue_session_uses_existing_session_id(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'sessions-continue.db'}"
    fake_graph = EchoSessionGraph()
    monkeypatch.setattr(orchestration_api, "graph", fake_graph)
    client = TestClient(create_app(database_url=database_url))
    token, _ = register(client, "sessions-continue@example.com")

    first = client.post(
        "/api/orchestration/sessions/start",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "开始"},
    )
    session_id = first.json()["session_id"]

    response = client.post(
        "/api/orchestration/sessions/continue",
        headers={"Authorization": f"Bearer {token}"},
        json={"session_id": session_id, "query": "继续"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    assert body["answer"]["user_message"] == "继续：继续"
    assert fake_graph.states[1]["session_id"] == session_id


def test_continue_session_rejects_unknown_session_id(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'sessions-continue-404.db'}"
    monkeypatch.setattr(orchestration_api, "graph", ReplyOnlyGraph())
    client = TestClient(create_app(database_url=database_url))
    token, _ = register(client, "sessions-missing@example.com")

    response = client.post(
        "/api/orchestration/sessions/continue",
        headers={"Authorization": f"Bearer {token}"},
        json={"session_id": "missing-session", "query": "继续"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "对话不存在"


async def fake_stream_session_events(state: dict) -> AsyncGenerator[dict, None]:
    yield {
        "event": "agent_step_started",
        "step_id": "main_agent",
        "agent_key": "main_agent",
        "label": "主智能体",
        "message": "主智能体开始处理。",
    }
    yield {
        "event": "agent_step_completed",
        "step_id": "main_agent",
        "agent_key": "main_agent",
        "label": "主智能体",
        "message": "主智能体已完成。",
    }
    yield {
        "event": "orchestration_completed",
        "state": {
            **state,
            "session_id": state["session_id"],
            "answer": {"user_message": "流式完成", "question_box": None},
            "agent_trace": [],
            "profile": None,
            "learning_path": None,
            "completed": False,
            "error": "",
        },
    }


def test_start_session_stream_emits_session_events(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'sessions-stream.db'}"
    monkeypatch.setattr(orchestration_api, "stream_orchestration_events", fake_stream_session_events)
    client = TestClient(create_app(database_url=database_url))
    token, _ = register(client, "sessions-stream@example.com")

    with client.stream(
        "POST",
        "/api/orchestration/sessions/start/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "开始流式"},
    ) as response:
        body = response.read().decode()

    assert response.status_code == 200
    assert "event: agent_step_started" in body
    assert "event: agent_step_completed" in body
    assert "event: orchestration_completed" in body
    assert "流式完成" in body


def test_continue_session_stream_uses_existing_session_id(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'sessions-continue-stream.db'}"
    monkeypatch.setattr(orchestration_api, "graph", ReplyOnlyGraph())
    monkeypatch.setattr(orchestration_api, "stream_orchestration_events", fake_stream_session_events)
    client = TestClient(create_app(database_url=database_url))
    token, _ = register(client, "sessions-continue-stream@example.com")
    first = client.post(
        "/api/orchestration/sessions/start",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "开始"},
    )
    session_id = first.json()["session_id"]

    with client.stream(
        "POST",
        "/api/orchestration/sessions/continue/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={"session_id": session_id, "query": "继续流式"},
    ) as response:
        body = response.read().decode()

    assert response.status_code == 200
    assert "event: orchestration_completed" in body
    assert session_id in body


def test_get_learning_path_me_returns_saved_path(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'learning-path-api.db'}"
    client = TestClient(create_app(database_url=database_url))
    token, uid = register(client, "sessions-learning-path@example.com")
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    with Session(engine) as session:
        session.add(UserLearningPath(user_uid=uid, path_data={"learning_goal": {"target_course_or_skill": "Python"}}))
        session.commit()

    response = client.get("/api/learning-path/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["learning_path"]["learning_goal"]["target_course_or_skill"] == "Python"


def test_get_learning_path_me_returns_404_without_path(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'learning-path-api-404.db'}"
    client = TestClient(create_app(database_url=database_url))
    token, _ = register(client, "sessions-learning-path-404@example.com")

    response = client.get("/api/learning-path/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404
    assert "还没有生成学习路径" in response.json()["detail"]
