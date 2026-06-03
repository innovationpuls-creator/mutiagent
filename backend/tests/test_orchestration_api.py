from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import create_app


def make_client(tmp_path: Path) -> TestClient:
    database_url = f"sqlite:///{tmp_path / 'orchestration-test.db'}"
    return TestClient(create_app(database_url=database_url))


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


class MockGraph:
    def __init__(self, response_template: str = "回复：{query}", extra_state: dict | None = None) -> None:
        self.response_template = response_template
        self.extra_state = extra_state or {}

    async def ainvoke(self, state: dict, config: dict) -> dict:
        return {
            **state,
            "response": self.response_template.format(query=state.get("query", "")),
            "agent_trace": [],
            "error": None,
            **self.extra_state,
        }

    async def astream_events(self, state: dict, config: dict, version: str = "v2"):
        output = {
            **state,
            "response": self.response_template.format(query=state.get("query", "")),
            "agent_trace": [],
            "error": None,
            **self.extra_state,
        }
        yield {
            "event": "on_chain_end",
            "name": "LangGraph",
            "data": {"output": output},
        }


@contextmanager
def _mock_create_graph(graph: MockGraph | None = None):
    g = graph or MockGraph()
    with patch("app.api.orchestration.create_orchestration_graph", return_value=g), \
         patch("app.orchestration.graph.create_orchestration_graph", return_value=g):
        yield g


def test_start_session_returns_response(tmp_path: Path) -> None:
    with _mock_create_graph():
        client = make_client(tmp_path)
        token, _ = register(client, "start-session@example.com")

        response = client.post(
            "/api/orchestration/sessions/start",
            headers={"Authorization": f"Bearer {token}"},
            json={"query": "你好"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["answer"]["user_message"] == "回复：你好"
        assert body["completed"] is True
        assert "session_id" in body


def test_start_session_stream_returns_sse(tmp_path: Path) -> None:
    with _mock_create_graph():
        client = make_client(tmp_path)
        token, _ = register(client, "stream-session@example.com")

        response = client.post(
            "/api/orchestration/sessions/start/stream",
            headers={"Authorization": f"Bearer {token}"},
            json={"query": "你好"},
        )

        assert response.status_code == 200
        assert "orchestration_completed" in response.text


def test_continue_session_uses_session_id(tmp_path: Path) -> None:
    with _mock_create_graph():
        client = make_client(tmp_path)
        token, _ = register(client, "continue-session@example.com")

        start_response = client.post(
            "/api/orchestration/sessions/start",
            headers={"Authorization": f"Bearer {token}"},
            json={"query": "第一次"},
        )
        session_id = start_response.json()["session_id"]

        continue_response = client.post(
            "/api/orchestration/sessions/continue",
            headers={"Authorization": f"Bearer {token}"},
            json={"session_id": session_id, "query": "继续"},
        )

        assert continue_response.status_code == 200
        assert continue_response.json()["answer"]["user_message"] == "回复：继续"


def test_continue_session_rejects_wrong_user(tmp_path: Path) -> None:
    with _mock_create_graph():
        client = make_client(tmp_path)
        token_a, _ = register(client, "user-a@example.com")

        start_response = client.post(
            "/api/orchestration/sessions/start",
            headers={"Authorization": f"Bearer {token_a}"},
            json={"query": "用户A的会话"},
        )
        session_id = start_response.json()["session_id"]

        token_b, _ = register(client, "user-b@example.com")

        continue_response = client.post(
            "/api/orchestration/sessions/continue",
            headers={"Authorization": f"Bearer {token_b}"},
            json={"session_id": session_id, "query": "用户B尝试继续"},
        )

        assert continue_response.status_code == 404
        assert continue_response.json()["detail"] == "对话不存在"


def test_start_session_requires_auth(tmp_path: Path) -> None:
    with _mock_create_graph():
        client = make_client(tmp_path)

        response = client.post(
            "/api/orchestration/sessions/start",
            json={"query": "你好"},
        )

        assert response.status_code == 401


def test_session_response_includes_profile_when_present(tmp_path: Path) -> None:
    profile_data = {"type": "basic_profile", "stage": "generated", "text": "用户画像"}
    with _mock_create_graph(MockGraph(extra_state={"profile": profile_data})):
        client = make_client(tmp_path)
        token, _ = register(client, "profile-response@example.com")

        response = client.post(
            "/api/orchestration/sessions/start",
            headers={"Authorization": f"Bearer {token}"},
            json={"query": "你好"},
        )

        assert response.status_code == 200
        assert response.json()["profile"] == profile_data


def test_session_response_handles_error(tmp_path: Path) -> None:
    with _mock_create_graph(MockGraph(extra_state={"error": "服务异常，请稍后重试"})):
        client = make_client(tmp_path)
        token, _ = register(client, "error-response@example.com")

        response = client.post(
            "/api/orchestration/sessions/start",
            headers={"Authorization": f"Bearer {token}"},
            json={"query": "你好"},
        )

        assert response.status_code == 500
