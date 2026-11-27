from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from tests.postgres import postgresql_test_url
from tests.test_canopy_api import _register


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(database_url=postgresql_test_url(tmp_path, "chat")))


def test_start_and_session_state_stay_in_python(tmp_path: Path) -> None:
    client = _client(tmp_path)
    token, uid = _register(client, "chat-session@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    started = client.post("/api/chat/start", json={"query": "开始"}, headers=headers)
    assert started.status_code == 200
    session_id = started.json()["session_id"]

    state = client.get(f"/api/chat/sessions/{session_id}", headers=headers)
    assert state.status_code == 200
    body = state.json()
    assert body["session_id"] == session_id and body["user_uid"] == uid
    assert body["messages"] == []


def test_session_state_is_private_to_its_owner(tmp_path: Path) -> None:
    client = _client(tmp_path)
    token, _ = _register(client, "chat-owner@example.com")
    other, _ = _register(client, "chat-other@example.com")
    started = client.post(
        "/api/chat/start",
        json={"query": "开始"},
        headers={"Authorization": f"Bearer {token}"},
    )
    session_id = started.json()["session_id"]

    res = client.get(
        f"/api/chat/sessions/{session_id}",
        headers={"Authorization": f"Bearer {other}"},
    )
    assert res.status_code == 404


def test_message_streaming_moved_to_the_gateway(tmp_path: Path) -> None:
    """`POST /api/chat/message` is served by the TS gateway; Python no longer has it."""
    client = _client(tmp_path)
    token, _ = _register(client, "chat-moved@example.com")
    res = client.post(
        "/api/chat/message",
        json={"session_id": "s", "message": "hi"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code in {404, 405}
