from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import create_app


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _register_user(client: TestClient, identifier: str, password: str) -> str:
    """Register a user and return the JWT token."""
    resp = client.post("/api/auth/register", json={
        "username": "测试用户",
        "identifier": identifier,
        "password": password,
        "confirm_password": password,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["access_token"]


@contextmanager
def chat_app(tmp_path: Path):
    database_url = f"sqlite:///{tmp_path / 'chat-test.db'}"
    app = create_app(database_url=database_url)
    with TestClient(app) as client:
        yield client


class TestChatEndpoints:
    def test_start_chat_returns_session(self, tmp_path: Path) -> None:
        with chat_app(tmp_path) as client:
            token = _register_user(client, "chatuser@example.com", "chat123456")

            response = client.post(
                "/api/chat/start",
                json={"query": "你好"},
                headers=_auth_header(token),
            )

            assert response.status_code == 200
            data = response.json()
            assert "session_id" in data
            assert len(data["session_id"]) > 0

    def test_start_chat_requires_auth(self, tmp_path: Path) -> None:
        with chat_app(tmp_path) as client:
            response = client.post("/api/chat/start", json={"query": "你好"})
            assert response.status_code == 401

    def test_get_session_404_for_nonexistent(self, tmp_path: Path) -> None:
        with chat_app(tmp_path) as client:
            token = _register_user(client, "sessionuser@example.com", "session123")
            response = client.get(
                "/api/chat/sessions/nonexistent-id",
                headers=_auth_header(token),
            )
            assert response.status_code == 404

    @patch("app.api.orchestration.stream_orchestration_events")
    def test_send_message_streams_sse(self, mock_stream, tmp_path: Path) -> None:
        async def mock_events(state):
            yield {"event": "session_started", "session_id": state["session_id"]}
            yield {"event": "supervisor_thinking", "message": "thinking"}
            yield {"event": "session_completed", "session_id": state["session_id"]}

        mock_stream.side_effect = mock_events

        with chat_app(tmp_path) as client:
            token = _register_user(client, "sseuser@example.com", "sse123456")
            start_resp = client.post(
                "/api/chat/start",
                json={"query": "开始"},
                headers=_auth_header(token),
            )
            session_id = start_resp.json()["session_id"]

            response = client.post(
                "/api/chat/message",
                json={"session_id": session_id, "message": "我想学Python"},
                headers=_auth_header(token),
            )

            assert response.status_code == 200
            assert "session_started" in response.text
            assert "session_completed" in response.text
