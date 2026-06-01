from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine

from app.api import orchestration as orchestration_api
from app.main import create_app
from app.models import UserDifyConversation, UserProfile


class CompletedProfileGraph:
    async def ainvoke(self, state: dict, config: dict) -> dict:
        return {
            **state,
            "intent_conversation_id": "intent-api",
            "conversation_id": "conv-api",
            "phase": "completed",
            "answer_json": {
                "type": "basic_profile",
                "stage": "generated",
                "question_mode": "none",
                "confirmed_info": {"current_grade": "大三", "major": "软件工程"},
                "defaulted_fields": [],
                "question_md": "",
                "question_box": {"question": "", "options": []},
                "text": "【用户基础信息】\n大三软件工程",
            },
        }


def test_start_chatflow_saves_completed_profile(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'orchestration-test.db'}"
    monkeypatch.setattr(orchestration_api, "graph", CompletedProfileGraph())
    client = TestClient(create_app(database_url=database_url))

    auth_response = client.post(
        "/api/auth/register",
        json={
            "username": "画像用户",
            "identifier": "profile-api@example.com",
            "password": "test-password-123",
            "confirm_password": "test-password-123",
        },
    )
    token = auth_response.json()["access_token"]
    uid = auth_response.json()["user"]["uid"]

    response = client.post(
        "/api/orchestration/chatflow/start",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "我想完善基础画像"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["completed"] is True
    assert body["conversation_id"] == "conv-api"
    assert body["answer"]["type"] == "basic_profile"

    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    with Session(engine) as session:
        profile = session.get(UserProfile, uid)
        dify_conversation = session.get(UserDifyConversation, uid)

    assert profile is not None
    assert profile.profile_data["type"] == "basic_profile"
    assert "大三软件工程" in profile.profile_text
    assert dify_conversation is not None
    assert dify_conversation.intent_conversation_id == "intent-api"
    assert dify_conversation.profile_conversation_id == "conv-api"


class EchoConversationGraph:
    def __init__(self) -> None:
        self.states: list[dict] = []
        self.configs: list[dict] = []

    async def ainvoke(self, state: dict, config: dict) -> dict:
        self.states.append(state.copy())
        self.configs.append(config)
        return {
            **state,
            "intent_conversation_id": state.get("intent_conversation_id") or "intent-restored",
            "conversation_id": state.get("conversation_id") or "profile-restored",
            "phase": "collecting",
            "answer_json": {
                "type": "collecting",
                "stage": "basic_info",
                "question_mode": "question_md",
                "confirmed_info": {},
                "defaulted_fields": [],
                "question_md": "继续画像",
                "question_box": {"question": "", "options": []},
                "text": "继续画像",
            },
        }


def test_start_chatflow_reuses_saved_dify_conversations(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'orchestration-session-test.db'}"
    fake_graph = EchoConversationGraph()
    monkeypatch.setattr(orchestration_api, "graph", fake_graph)
    client = TestClient(create_app(database_url=database_url))
    auth_response = client.post(
        "/api/auth/register",
        json={
            "username": "上下文用户",
            "identifier": "profile-context@example.com",
            "password": "test-password-123",
            "confirm_password": "test-password-123",
        },
    )
    token = auth_response.json()["access_token"]
    uid = auth_response.json()["user"]["uid"]
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    with Session(engine) as session:
        session.add(
            UserDifyConversation(
                user_uid=uid,
                intent_conversation_id="intent-saved",
                profile_conversation_id="profile-saved",
            )
        )
        session.commit()

    response = client.post(
        "/api/orchestration/chatflow/start",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "刷新后继续问"},
    )

    assert response.status_code == 200
    assert fake_graph.states[0]["intent_conversation_id"] == "intent-saved"
    assert fake_graph.states[0]["conversation_id"] == "profile-saved"


async def fake_stream_orchestration_events(state: dict):
    yield {
        "event": "agent_started",
        "agent": "intent_recognition_agent",
        "label": "意图识别智能体",
        "message": "正在判断这次对话应该交给哪个智能体。",
    }
    yield {
        "event": "route_decided",
        "agent": "profile_agent",
        "label": "基础画像智能体",
        "intent": "profile_agent",
        "route_status": "supported",
        "message": "路由已完成，准备进入具体智能体。",
    }
    yield {
        "event": "agent_started",
        "agent": "profile_agent",
        "label": "基础画像智能体",
        "message": "正在整理基础画像信息。",
    }
    final_state = {
        **state,
        "intent_conversation_id": "intent-stream",
        "conversation_id": "profile-stream",
        "phase": "collecting",
        "answer_json": {
            "type": "collecting",
            "stage": "basic_info",
            "question_mode": "question_md",
            "confirmed_info": {},
            "defaulted_fields": [],
            "question_md": "请介绍",
            "question_box": {"question": "", "options": []},
            "text": "请介绍",
        },
    }
    yield {
        "event": "completed",
        "agent": "profile_agent",
        "label": "基础画像智能体",
        "state": final_state,
        "answer": final_state["answer_json"],
        "completed": False,
        "phase": "collecting",
    }


def test_start_chatflow_stream_emits_agent_events(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'orchestration-stream-test.db'}"
    monkeypatch.setattr(orchestration_api, "stream_orchestration_events", fake_stream_orchestration_events)
    client = TestClient(create_app(database_url=database_url))

    auth_response = client.post(
        "/api/auth/register",
        json={
            "username": "流式用户",
            "identifier": "profile-stream@example.com",
            "password": "test-password-123",
            "confirm_password": "test-password-123",
        },
    )
    token = auth_response.json()["access_token"]

    with client.stream(
        "POST",
        "/api/orchestration/chatflow/start/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "我想完善基础画像"},
    ) as response:
        body = response.read().decode()

    assert response.status_code == 200
    assert "event: agent_started" in body
    assert "意图识别智能体" in body
    assert "event: route_decided" in body
    assert "基础画像智能体" in body
    assert "event: completed" in body
    assert "profile-stream" in body


def test_start_chatflow_uses_user_scoped_graph_thread(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'orchestration-thread-test.db'}"
    fake_graph = EchoConversationGraph()
    monkeypatch.setattr(orchestration_api, "graph", fake_graph)
    client = TestClient(create_app(database_url=database_url))
    auth_response = client.post(
        "/api/auth/register",
        json={
            "username": "线程用户",
            "identifier": "profile-thread@example.com",
            "password": "test-password-123",
            "confirm_password": "test-password-123",
        },
    )
    token = auth_response.json()["access_token"]
    uid = auth_response.json()["user"]["uid"]

    first = client.post(
        "/api/orchestration/chatflow/start",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "第一次开始"},
    )
    second = client.post(
        "/api/orchestration/chatflow/start",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "刷新后再次开始"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    thread_ids = [config["configurable"]["thread_id"] for config in fake_graph.configs]
    assert thread_ids == [uid, uid]
    assert ":" not in thread_ids[0]
    assert fake_graph.states[0]["intent_conversation_id"] == ""
    assert fake_graph.states[0]["conversation_id"] == ""
    assert fake_graph.states[1]["intent_conversation_id"] == "intent-restored"
    assert fake_graph.states[1]["conversation_id"] == "profile-restored"
