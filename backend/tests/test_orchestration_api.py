from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import app.orchestration.graph as graph_module
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.database import build_engine
from app.main import create_app
from app.models import (
    ConversationSession,
    User,
    UserCourseKnowledgeOutline,
    UserProfile,
    UserYearLearningPath,
)


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


def _basic_profile() -> dict:
    return {
        "type": "basic_profile",
        "summary_text": "大三软件工程学生，目标是完成 AI 应用开发项目。",
        "confirmed_info": {
            "current_grade": "大三",
            "major": "软件工程",
            "learning_stage": "项目实践",
            "has_clear_goal": "是",
            "learning_method_preference": "项目驱动",
            "learning_pace_preference": "每天少量代码",
            "content_preference": ["实践", "部署"],
            "need_guidance": "需要",
            "knowledge_foundation": "有 Python 和前端基础",
            "strengths": "能完成小型功能",
            "weaknesses": "异步工程经验不足",
            "experience": "做过课程项目",
            "short_term_goal": "完成 AI 功能模块",
            "long_term_goal": "成为全栈 AI 开发者",
            "weekly_available_time": "每周 8 小时",
            "constraints": "时间有限",
        },
    }


def _course_node(course_id: str, theme: str) -> dict:
    return {
        "course_node_id": course_id,
        "grade_id": "year_3",
        "course_or_chapter_theme": theme,
        "time_arrangement": {
            "semester_scope": "上学期",
            "duration": "6 周",
            "pace_reason": "项目驱动",
        },
        "course_goal": f"完成{theme}",
        "prerequisite_node_ids": [],
        "chapter_nodes": [],
        "core_knowledge_points": [],
        "key_points": ["OpenAI-compatible API 调用"],
        "difficult_points": ["异步调用稳定性"],
        "learning_sequence": ["需求拆解", "接口接入", "最小闭环演示"],
        "knowledge_relations": [],
        "downstream_resource_direction_ids": [],
        "acceptance_criteria": ["完成一个可运行的 AI 功能模块并接入 Web 应用"],
    }


def _year_3_path() -> dict:
    first = _course_node("year_3_course_1", "AI Agent 开发基础能力搭建")
    second = _course_node("year_3_course_2", "AI Agent 项目实战")
    return {
        "schema_version": "learning_path.v2.course_node",
        "learning_goal": {
            "target_course_or_skill": "AI 应用开发",
            "goal_type": "项目实践",
            "desired_outcome": "完成一个 AI 功能模块",
            "four_year_outcome": "具备全栈 AI 项目交付能力",
        },
        "learner_baseline": {
            "current_grade": "大三",
            "major": "软件工程",
            "mastered_content": ["Python", "前端基础"],
            "weaknesses": ["异步工程经验不足"],
            "constraints": ["时间有限"],
            "weekly_available_time": "每周 8 小时",
        },
        "planning_rules": {
            "node_unit": "course_node",
            "grade_boundary_rule": "按年级拆分",
            "sequence_rule": "先基础后项目",
            "resource_rule": "每个节点对应资源方向",
        },
        "grade_plans": {
            "year_3": {
                "grade_id": "year_3",
                "grade_name": "大三",
                "grade_goal": "完成 AI 应用开发项目",
                "course_nodes": [first, second],
            },
        },
        "knowledge_graph": {
            "global_relations": [],
            "critical_paths": [],
        },
        "resource_generation_contract": {
            "downstream_agents": [],
            "resource_directions": [],
        },
        "dynamic_update_contract": {
            "trackable_metrics": [],
            "update_triggers": [],
            "adjustment_strategy": "按周调整",
        },
        "current_learning_course": {
            "grade_id": "year_3",
            "course_node_id": "year_3_course_1",
            "course_or_chapter_theme": "AI Agent 开发基础能力搭建",
            "course_goal": "完成AI Agent 开发基础能力搭建",
            "time_arrangement": first["time_arrangement"],
            "current_focus": "正在学习 AI Agent 开发基础能力搭建",
            "progress_state": "in_progress",
            "next_action": "继续学习第一章",
        },
    }


def _course_outline() -> dict:
    return {
        "course_id": "year_3_course_1",
        "course_name": "AI Agent 开发基础能力搭建",
        "grade_year": "year_3",
        "personalization_summary": "先完成需求拆解，再进入接口接入与最小闭环演示。",
        "sections": [
            {
                "section_id": "1",
                "parent_section_id": None,
                "depth": 1,
                "title": "需求拆解",
                "order_index": 1,
                "description": "确认功能边界与验收标准。",
                "key_knowledge_points": ["功能边界", "验收标准"],
            }
        ],
        "learning_sequence": ["第一章：需求拆解"],
        "total_estimated_hours": "8 小时",
    }


def _seed_existing_learning_data(database_url: str, identifier: str) -> None:
    engine = build_engine(database_url)
    with Session(engine) as session:
        user = session.exec(select(User).where(User.identifier == identifier)).one()
        session.add(
            UserProfile(
                user_uid=user.uid,
                profile_data=_basic_profile(),
                profile_text="大三软件工程学生，目标是完成 AI 应用开发项目。",
            )
        )
        session.add(
            UserYearLearningPath(
                user_uid=user.uid,
                grade_year="year_3",
                learning_topic="AI 应用开发",
                path_data=_year_3_path(),
            )
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid=user.uid,
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI Agent 开发基础能力搭建",
                outline_data=_course_outline(),
            )
        )
        session.commit()


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
            yield {"event": "message_completed", "full_text": "这是回复"}
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

            engine = build_engine(f"sqlite:///{tmp_path / 'chat-test.db'}")
            with Session(engine) as session:
                row = session.get(ConversationSession, session_id)
                assert row is not None
                assert len(row.messages) == 2
                assert row.messages[0]["type"] == "human"
                assert row.messages[0]["data"]["content"] == "我想学Python"
                assert row.messages[1]["type"] == "ai"
                assert row.messages[1]["data"]["content"] == "这是回复"

    @patch("app.api.orchestration.stream_orchestration_events")
    def test_send_message_loads_persisted_messages(self, mock_stream, tmp_path: Path) -> None:
        captured_lengths = []

        async def mock_events(state):
            captured_lengths.append(len(state["messages"]))
            yield {"event": "message_completed", "full_text": "第二轮回复"}

        mock_stream.side_effect = mock_events

        with chat_app(tmp_path) as client:
            token = _register_user(client, "historyuser@example.com", "history123456")
            start_resp = client.post(
                "/api/chat/start",
                json={"query": "开始"},
                headers=_auth_header(token),
            )
            session_id = start_resp.json()["session_id"]

            for message in ("第一轮", "第二轮"):
                response = client.post(
                    "/api/chat/message",
                    json={"session_id": session_id, "message": message},
                    headers=_auth_header(token),
                )
                assert response.status_code == 200

            assert captured_lengths == [1, 3]

    @patch("app.api.orchestration.stream_orchestration_events")
    def test_send_message_does_not_save_failed_assistant_as_success(self, mock_stream, tmp_path: Path) -> None:
        async def mock_events(state):
            yield {
                "event": "error",
                "message": "学习路径生成失败，请重试生成学习路径。",
                "recoverable": True,
                "retryable": True,
                "retryAction": "retry_learning_path",
            }

        mock_stream.side_effect = mock_events

        with chat_app(tmp_path) as client:
            token = _register_user(client, "failedpath@example.com", "failed123456")
            start_resp = client.post(
                "/api/chat/start",
                json={"query": "开始"},
                headers=_auth_header(token),
            )
            session_id = start_resp.json()["session_id"]

            response = client.post(
                "/api/chat/message",
                json={"session_id": session_id, "message": "继续生成"},
                headers=_auth_header(token),
            )

            assert response.status_code == 200
            assert "event: error" in response.text
            assert "message_completed" not in response.text

            engine = build_engine(f"sqlite:///{tmp_path / 'chat-test.db'}")
            with Session(engine) as session:
                row = session.get(ConversationSession, session_id)
                assert row is not None
                assert len(row.messages) == 1
                assert row.messages[0]["type"] == "human"

    @patch("app.api.orchestration.stream_orchestration_events")
    def test_send_message_persists_user_message_when_stream_raises(self, mock_stream, tmp_path: Path) -> None:
        async def mock_events(state):
            raise RuntimeError("编排流异常中断")
            if False:
                yield {}

        mock_stream.side_effect = mock_events

        with chat_app(tmp_path) as client:
            token = _register_user(client, "raisedpath@example.com", "raised123456")
            start_resp = client.post(
                "/api/chat/start",
                json={"query": "开始"},
                headers=_auth_header(token),
            )
            session_id = start_resp.json()["session_id"]

            response = client.post(
                "/api/chat/message",
                json={"session_id": session_id, "message": "继续生成"},
                headers=_auth_header(token),
            )

            assert response.status_code == 200
            assert "event: error" in response.text
            assert "编排流异常中断" in response.text
            assert "message_completed" not in response.text

            engine = build_engine(f"sqlite:///{tmp_path / 'chat-test.db'}")
            with Session(engine) as session:
                row = session.get(ConversationSession, session_id)
                assert row is not None
                assert len(row.messages) == 1
                assert row.messages[0]["type"] == "human"
                assert row.messages[0]["data"]["content"] == "继续生成"

    @patch("app.api.orchestration.stream_orchestration_events")
    def test_send_message_returns_existing_outline_without_agent_call(self, mock_stream, tmp_path: Path) -> None:
        mock_stream.side_effect = AssertionError("已有课程大纲应直接从数据库返回")
        identifier = "outline-direct@example.com"
        database_url = f"sqlite:///{tmp_path / 'chat-test.db'}"

        with chat_app(tmp_path) as client:
            token = _register_user(client, identifier, "outline123456")
            _seed_existing_learning_data(database_url, identifier)
            start_resp = client.post(
                "/api/chat/start",
                json={"query": "开始"},
                headers=_auth_header(token),
            )
            session_id = start_resp.json()["session_id"]

            response = client.post(
                "/api/chat/message",
                json={"session_id": session_id, "message": "给我看看这个课的大纲"},
                headers=_auth_header(token),
            )

            assert response.status_code == 200
            assert "course_knowledge_loaded" in response.text
            assert "AI Agent 开发基础能力搭建" in response.text
            assert "第一章：需求拆解" in response.text
            assert "course_knowledge_agent" not in response.text
            assert "intent_agent" not in response.text
            assert "\"has_outline\": true" in response.text

            engine = build_engine(database_url)
            with Session(engine) as session:
                row = session.get(ConversationSession, session_id)
                assert row is not None
                assert len(row.messages) == 2
                assert row.messages[1]["type"] == "ai"
                assert "第一章：需求拆解" in row.messages[1]["data"]["content"]

    @patch("app.api.orchestration.stream_orchestration_events")
    def test_send_message_returns_existing_learning_path_without_agent_call(self, mock_stream, tmp_path: Path) -> None:
        mock_stream.side_effect = AssertionError("已有学习路径应直接从数据库返回")
        identifier = "path-direct@example.com"
        database_url = f"sqlite:///{tmp_path / 'chat-test.db'}"

        with chat_app(tmp_path) as client:
            token = _register_user(client, identifier, "path123456")
            _seed_existing_learning_data(database_url, identifier)
            start_resp = client.post(
                "/api/chat/start",
                json={"query": "开始"},
                headers=_auth_header(token),
            )
            session_id = start_resp.json()["session_id"]

            response = client.post(
                "/api/chat/message",
                json={"session_id": session_id, "message": "我的学习路径里面要学哪些课？"},
                headers=_auth_header(token),
            )

            assert response.status_code == 200
            assert "learning_path_loaded" in response.text
            assert "AI Agent 开发基础能力搭建" in response.text
            assert "AI Agent 项目实战" in response.text
            assert "learning_path_agent" not in response.text
            assert "course_knowledge_agent" not in response.text
            assert "intent_agent" not in response.text
            assert "\"has_paths\": true" in response.text

    @patch("app.api.orchestration.stream_orchestration_events")
    def test_send_message_returns_existing_learning_path_for_review_shortcut(self, mock_stream, tmp_path: Path) -> None:
        mock_stream.side_effect = AssertionError("回顾学习路径短语应直接从数据库返回")
        identifier = "path-shortcut@example.com"
        database_url = f"sqlite:///{tmp_path / 'chat-test.db'}"

        with chat_app(tmp_path) as client:
            token = _register_user(client, identifier, "path123456")
            _seed_existing_learning_data(database_url, identifier)
            start_resp = client.post(
                "/api/chat/start",
                json={"query": "开始"},
                headers=_auth_header(token),
            )
            session_id = start_resp.json()["session_id"]

            response = client.post(
                "/api/chat/message",
                json={"session_id": session_id, "message": "看看路径"},
                headers=_auth_header(token),
            )

            assert response.status_code == 200
            assert "learning_path_loaded" in response.text
            assert "AI Agent 开发基础能力搭建" in response.text
            assert "AI Agent 项目实战" in response.text
            assert "learning_path_agent" not in response.text
            assert "course_knowledge_agent" not in response.text
            assert "intent_agent" not in response.text
            assert "\"has_paths\": true" in response.text

    @patch("app.api.orchestration.stream_orchestration_events")
    def test_send_message_review_shortcut_keeps_collecting_profile_incomplete(self, mock_stream, tmp_path: Path) -> None:
        mock_stream.side_effect = AssertionError("回顾学习路径短语应直接从数据库返回")
        identifier = "path-collecting@example.com"
        database_url = f"sqlite:///{tmp_path / 'chat-test.db'}"

        with chat_app(tmp_path) as client:
            token = _register_user(client, identifier, "path123456")

            engine = build_engine(database_url)
            with Session(engine) as session:
                user = session.exec(select(User).where(User.identifier == identifier)).one()
                session.add(
                    UserProfile(
                        user_uid=user.uid,
                        profile_data={
                            "type": "collecting",
                            "stage": "basic_info",
                            "question_mode": "question_md",
                            "confirmed_info": {
                                "current_grade": "大三",
                                "major": "",
                                "learning_stage": "",
                                "has_clear_goal": "",
                                "learning_method_preference": "",
                                "learning_pace_preference": "",
                                "content_preference": [],
                                "need_guidance": "",
                                "knowledge_foundation": "",
                                "strengths": "",
                                "weaknesses": "",
                                "experience": "",
                                "short_term_goal": "",
                                "long_term_goal": "",
                                "weekly_available_time": "",
                                "constraints": "",
                            },
                            "defaulted_fields": [],
                            "question_md": "为了生成基础画像，请先告诉我你的专业。",
                            "question_box": {"question": "", "options": []},
                            "text": "为了生成基础画像，请先告诉我你的专业。",
                        },
                        profile_text="为了生成基础画像，请先告诉我你的专业。",
                    )
                )
                session.add(
                    UserYearLearningPath(
                        user_uid=user.uid,
                        grade_year="year_3",
                        learning_topic="AI 应用开发",
                        path_data=_year_3_path(),
                    )
                )
                session.commit()

            start_resp = client.post(
                "/api/chat/start",
                json={"query": "开始"},
                headers=_auth_header(token),
            )
            session_id = start_resp.json()["session_id"]

            response = client.post(
                "/api/chat/message",
                json={"session_id": session_id, "message": "看看路径"},
                headers=_auth_header(token),
            )

            assert response.status_code == 200
            assert "learning_path_loaded" in response.text
            assert "\"has_profile\": false" in response.text
            assert "\"has_paths\": true" in response.text

    def test_get_session_state_returns_current_course_outline(self, tmp_path: Path) -> None:
        identifier = "session-current-outline@example.com"
        database_url = f"sqlite:///{tmp_path / 'chat-test.db'}"

        with chat_app(tmp_path) as client:
            token = _register_user(client, identifier, "current123456")
            _seed_existing_learning_data(database_url, identifier)
            engine = build_engine(database_url)
            with Session(engine) as session:
                user = session.exec(select(User).where(User.identifier == identifier)).one()
                current_row = session.get(UserCourseKnowledgeOutline, (user.uid, "year_3_course_1"))
                assert current_row is not None
                current_row.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
                other_outline = {
                    **_course_outline(),
                    "course_id": "year_3_course_2",
                    "course_name": "AI Agent 项目实战",
                }
                session.add(
                    UserCourseKnowledgeOutline(
                        user_uid=user.uid,
                        course_id="year_3_course_2",
                        grade_year="year_3",
                        course_name="AI Agent 项目实战",
                        outline_data=other_outline,
                        updated_at=datetime(2026, 6, 5, tzinfo=timezone.utc),
                    )
                )
                session.commit()

            start_resp = client.post(
                "/api/chat/start",
                json={"query": "开始"},
                headers=_auth_header(token),
            )
            session_id = start_resp.json()["session_id"]

            response = client.get(
                f"/api/chat/sessions/{session_id}",
                headers=_auth_header(token),
            )

            assert response.status_code == 200
            assert response.json()["course_knowledge"]["course_id"] == "year_3_course_1"

    def test_get_session_state_does_not_fallback_to_latest_outline_from_other_course(self, tmp_path: Path) -> None:
        identifier = "session-no-outline-fallback@example.com"
        database_url = f"sqlite:///{tmp_path / 'chat-test.db'}"

        with chat_app(tmp_path) as client:
            token = _register_user(client, identifier, "current123456")
            _seed_existing_learning_data(database_url, identifier)
            engine = build_engine(database_url)
            with Session(engine) as session:
                user = session.exec(select(User).where(User.identifier == identifier)).one()
                current_row = session.get(UserCourseKnowledgeOutline, (user.uid, "year_3_course_1"))
                assert current_row is not None
                session.delete(current_row)
                other_outline = {
                    **_course_outline(),
                    "course_id": "year_3_course_2",
                    "course_name": "AI Agent 项目实战",
                }
                session.add(
                    UserCourseKnowledgeOutline(
                        user_uid=user.uid,
                        course_id="year_3_course_2",
                        grade_year="year_3",
                        course_name="AI Agent 项目实战",
                        outline_data=other_outline,
                        updated_at=datetime(2026, 6, 5, tzinfo=timezone.utc),
                    )
                )
                session.commit()

            start_resp = client.post(
                "/api/chat/start",
                json={"query": "开始"},
                headers=_auth_header(token),
            )
            session_id = start_resp.json()["session_id"]

            response = client.get(
                f"/api/chat/sessions/{session_id}",
                headers=_auth_header(token),
            )

            assert response.status_code == 200
            assert response.json()["course_knowledge"] is None

    @patch("app.api.orchestration.stream_orchestration_events")
    def test_get_session_state_returns_persisted_messages(self, mock_stream, tmp_path: Path) -> None:
        async def mock_events(state):
            yield {"event": "message_completed", "full_text": "这是恢复后的回复"}

        mock_stream.side_effect = mock_events

        with chat_app(tmp_path) as client:
            token = _register_user(client, "session-messages@example.com", "session123456")
            start_resp = client.post(
                "/api/chat/start",
                json={"query": "开始"},
                headers=_auth_header(token),
            )
            session_id = start_resp.json()["session_id"]

            response = client.post(
                "/api/chat/message",
                json={"session_id": session_id, "message": "恢复这段对话"},
                headers=_auth_header(token),
            )

            assert response.status_code == 200

            state_response = client.get(
                f"/api/chat/sessions/{session_id}",
                headers=_auth_header(token),
            )

            assert state_response.status_code == 200
            messages = state_response.json()["messages"]
            assert len(messages) == 2
            assert messages[0]["type"] == "human"
            assert messages[0]["data"]["content"] == "恢复这段对话"
            assert messages[1]["type"] == "ai"
            assert messages[1]["data"]["content"] == "这是恢复后的回复"

    def test_get_session_state_prefers_latest_updated_path_outline_when_multiple_years_exist(self, tmp_path: Path) -> None:
        identifier = "session-latest-path@example.com"
        database_url = f"sqlite:///{tmp_path / 'chat-test.db'}"

        with chat_app(tmp_path) as client:
            token = _register_user(client, identifier, "latest123456")

            engine = build_engine(database_url)
            with Session(engine) as session:
                user = session.exec(select(User).where(User.identifier == identifier)).one()
                session.add(
                    UserProfile(
                        user_uid=user.uid,
                        profile_data=_basic_profile(),
                        profile_text="大三软件工程学生，目标是完成 AI 应用开发项目。",
                    )
                )
                year_3_path = _year_3_path()
                year_4_path = {
                    **_year_3_path(),
                    "grade_plans": {
                        "year_4": {
                            "grade_id": "year_4",
                            "grade_name": "大四",
                            "grade_goal": "完成毕业项目",
                            "course_nodes": [
                                {
                                    **_course_node("year_4_course_1", "毕业项目实战"),
                                    "grade_id": "year_4",
                                },
                            ],
                        },
                    },
                    "current_learning_course": {
                        "grade_id": "year_4",
                        "course_node_id": "year_4_course_1",
                        "course_or_chapter_theme": "毕业项目实战",
                        "course_goal": "完成毕业项目实战",
                        "time_arrangement": {
                            "semester_scope": "上学期",
                            "duration": "6 周",
                            "pace_reason": "项目驱动",
                        },
                        "current_focus": "正在学习 毕业项目实战",
                        "progress_state": "in_progress",
                        "next_action": "继续学习第一章",
                    },
                }
                session.add(
                    UserYearLearningPath(
                        user_uid=user.uid,
                        grade_year="year_3",
                        learning_topic="AI 应用开发",
                        path_data=year_3_path,
                        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    )
                )
                session.add(
                    UserYearLearningPath(
                        user_uid=user.uid,
                        grade_year="year_4",
                        learning_topic="毕业项目",
                        path_data=year_4_path,
                        updated_at=datetime(2026, 6, 5, tzinfo=timezone.utc),
                    )
                )
                session.add(
                    UserCourseKnowledgeOutline(
                        user_uid=user.uid,
                        course_id="year_3_course_1",
                        grade_year="year_3",
                        course_name="AI Agent 开发基础能力搭建",
                        outline_data=_course_outline(),
                    )
                )
                session.add(
                    UserCourseKnowledgeOutline(
                        user_uid=user.uid,
                        course_id="year_4_course_1",
                        grade_year="year_4",
                        course_name="毕业项目实战",
                        outline_data={
                            **_course_outline(),
                            "course_id": "year_4_course_1",
                            "course_name": "毕业项目实战",
                            "grade_year": "year_4",
                        },
                    )
                )
                session.commit()

            start_resp = client.post(
                "/api/chat/start",
                json={"query": "开始"},
                headers=_auth_header(token),
            )
            session_id = start_resp.json()["session_id"]

            response = client.get(
                f"/api/chat/sessions/{session_id}",
                headers=_auth_header(token),
            )

            assert response.status_code == 200
            assert response.json()["latest_grade_year"] == "year_4"
            assert response.json()["course_knowledge"]["course_id"] == "year_4_course_1"

    def test_send_message_returns_completion_reply_when_course_change_has_no_next_course(self, tmp_path: Path) -> None:
        identifier = "completed-course@example.com"
        database_url = f"sqlite:///{tmp_path / 'chat-test.db'}"
        graph_module._graph = None

        class GuardSupervisorLlm:
            def bind_tools(self, _tools):
                return self

            async def ainvoke(self, _messages):
                raise AssertionError("最后一门课程换新课应走 force_call 收口，不应调用 LLM")

        class WorkerPlaceholderLlm:
            pass

        with patch("app.orchestration.graph.get_supervisor_llm", return_value=GuardSupervisorLlm()), \
             patch("app.orchestration.graph.get_worker_llm", return_value=WorkerPlaceholderLlm()), \
             patch("app.orchestration.graph.get_thinking_worker_llm", return_value=WorkerPlaceholderLlm()):
            with chat_app(tmp_path) as client:
                token = _register_user(client, identifier, "completed123456")

                engine = build_engine(database_url)
                with Session(engine) as session:
                    user = session.exec(select(User).where(User.identifier == identifier)).one()
                    year_path = _year_3_path()
                    year_path["current_learning_course"] = {
                        "grade_id": "year_3",
                        "course_node_id": "year_3_course_2",
                        "course_or_chapter_theme": "AI Agent 项目实战",
                        "course_goal": "完成AI Agent 项目实战",
                        "time_arrangement": year_path["grade_plans"]["year_3"]["course_nodes"][1]["time_arrangement"],
                        "current_focus": "正在学习 AI Agent 项目实战",
                        "progress_state": "completed",
                        "next_action": "当前阶段课程已全部完成",
                    }
                    session.add(
                        UserProfile(
                            user_uid=user.uid,
                            profile_data=_basic_profile(),
                            profile_text="大三软件工程学生，目标是完成 AI 应用开发项目。",
                        )
                    )
                    session.add(
                        UserYearLearningPath(
                            user_uid=user.uid,
                            grade_year="year_3",
                            learning_topic="AI 应用开发",
                            path_data=year_path,
                        )
                    )
                    session.commit()

                start_resp = client.post(
                    "/api/chat/start",
                    json={"query": "开始"},
                    headers=_auth_header(token),
                )
                session_id = start_resp.json()["session_id"]

                response = client.post(
                    "/api/chat/message",
                    json={"session_id": session_id, "message": "我不想要《AI Agent 项目实战》了，现在帮我生成一门新课"},
                    headers=_auth_header(token),
                )

                assert response.status_code == 200
                assert "当前所有任务已经完成。" in response.text
                assert "session_completed" in response.text
                assert "course_knowledge_agent" not in response.text

                with Session(engine) as session:
                    row = session.get(ConversationSession, session_id)
                    assert row is not None
                    assert len(row.messages) == 2
                    assert row.messages[1]["type"] == "ai"
                    assert row.messages[1]["data"]["content"].startswith("当前所有任务已经完成。")

        graph_module._graph = None

    def test_send_message_prompts_for_profile_details_on_generic_profile_update(self, tmp_path: Path) -> None:
        identifier = "profile-update-direct@example.com"
        database_url = f"sqlite:///{tmp_path / 'chat-test.db'}"
        graph_module._graph = None

        class GuardSupervisorLlm:
            def bind_tools(self, _tools):
                return self

            async def ainvoke(self, _messages):
                raise AssertionError("泛化画像更新提示应走 force_call 收口，不应调用 LLM")

        class WorkerPlaceholderLlm:
            pass

        with patch("app.orchestration.graph.get_supervisor_llm", return_value=GuardSupervisorLlm()), \
             patch("app.orchestration.graph.get_worker_llm", return_value=WorkerPlaceholderLlm()), \
             patch("app.orchestration.graph.get_thinking_worker_llm", return_value=WorkerPlaceholderLlm()):
            with chat_app(tmp_path) as client:
                token = _register_user(client, identifier, "profile123456")
                _seed_existing_learning_data(database_url, identifier)

                start_resp = client.post(
                    "/api/chat/start",
                    json={"query": "开始"},
                    headers=_auth_header(token),
                )
                session_id = start_resp.json()["session_id"]

                response = client.post(
                    "/api/chat/message",
                    json={"session_id": session_id, "message": "更新个人画像"},
                    headers=_auth_header(token),
                )

                assert response.status_code == 200
                assert "可以。更新个人画像前，请先直接告诉我你想调整的具体信息。" in response.text
                assert "session_completed" in response.text
                assert "profile_agent" not in response.text

                engine = build_engine(database_url)
                with Session(engine) as session:
                    row = session.get(ConversationSession, session_id)
                    assert row is not None
                    assert len(row.messages) == 2
                    assert row.messages[1]["type"] == "ai"
                    assert row.messages[1]["data"]["content"].startswith("可以。更新个人画像前，请先直接告诉我你想调整的具体信息。")

        graph_module._graph = None

    def test_send_message_updates_profile_and_refreshes_learning_path_after_completed_tasks(self, tmp_path: Path) -> None:
        identifier = "completed-followup@example.com"
        database_url = f"sqlite:///{tmp_path / 'chat-test.db'}"
        graph_module._graph = None

        class GuardSupervisorLlm:
            def bind_tools(self, _tools):
                return self

            async def ainvoke(self, _messages):
                raise AssertionError("完成任务后的画像更新与路径刷新应走 force_call，不应调用 LLM")

        class WorkerPlaceholderLlm:
            pass

        with patch("app.orchestration.graph.get_supervisor_llm", return_value=GuardSupervisorLlm()), \
             patch("app.orchestration.graph.get_worker_llm", return_value=WorkerPlaceholderLlm()), \
             patch("app.orchestration.graph.get_thinking_worker_llm", return_value=WorkerPlaceholderLlm()):
            with chat_app(tmp_path) as client:
                token = _register_user(client, identifier, "followup123456")

                engine = build_engine(database_url)
                with Session(engine) as session:
                    user = session.exec(select(User).where(User.identifier == identifier)).one()
                    year_path = _year_3_path()
                    year_path["current_learning_course"] = {
                        "grade_id": "year_3",
                        "course_node_id": "year_3_course_2",
                        "course_or_chapter_theme": "AI Agent 项目实战",
                        "course_goal": "完成AI Agent 项目实战",
                        "time_arrangement": year_path["grade_plans"]["year_3"]["course_nodes"][1]["time_arrangement"],
                        "current_focus": "当前阶段课程已全部完成",
                        "progress_state": "completed",
                        "next_action": "当前阶段课程已全部完成",
                    }
                    session.add(
                        UserProfile(
                            user_uid=user.uid,
                            profile_data=_basic_profile(),
                            profile_text="大三软件工程学生，目标是完成 AI 应用开发项目。",
                        )
                    )
                    session.add(
                        UserYearLearningPath(
                            user_uid=user.uid,
                            grade_year="year_3",
                            learning_topic="AI 应用开发",
                            path_data=year_path,
                        )
                    )
                    session.commit()

                start_resp = client.post(
                    "/api/chat/start",
                    json={"query": "开始"},
                    headers=_auth_header(token),
                )
                session_id = start_resp.json()["session_id"]

                completed_response = client.post(
                    "/api/chat/message",
                    json={"session_id": session_id, "message": "我不想要《AI Agent 项目实战》了，现在帮我生成一门新课"},
                    headers=_auth_header(token),
                )

                assert completed_response.status_code == 200
                assert "当前所有任务已经完成。" in completed_response.text

                refresh_response = client.post(
                    "/api/chat/message",
                    json={"session_id": session_id, "message": "大四，计算机科学，AI，周末集中"},
                    headers=_auth_header(token),
                )

                assert refresh_response.status_code == 200
                assert "学习路径已生成" in refresh_response.text
                assert "就业级作品集与迭代优化" in refresh_response.text
                assert "profile_agent" in refresh_response.text
                assert "learning_path_agent" in refresh_response.text
                assert "session_completed" in refresh_response.text

                with Session(engine) as session:
                    user = session.exec(select(User).where(User.identifier == identifier)).one()
                    profile_row = session.get(UserProfile, user.uid)
                    assert profile_row is not None
                    assert profile_row.profile_data["confirmed_info"]["current_grade"] == "大四"
                    assert profile_row.profile_data["confirmed_info"]["major"] == "计算机科学"

                    year_4_path = session.exec(
                        select(UserYearLearningPath).where(
                            UserYearLearningPath.user_uid == user.uid,
                            UserYearLearningPath.grade_year == "year_4",
                        )
                    ).one()
                    assert year_4_path.path_data["current_learning_course"]["course_node_id"] == "year_4_course_1"

                    conversation_row = session.get(ConversationSession, session_id)
                    assert conversation_row is not None
                    assert len(conversation_row.messages) == 4
                    assert conversation_row.messages[3]["type"] == "ai"
                    assert "学习路径已生成" in conversation_row.messages[3]["data"]["content"]

        graph_module._graph = None

    def test_send_message_updates_explicit_major_and_refreshes_learning_path_after_completed_tasks(self, tmp_path: Path) -> None:
        identifier = "completed-major-followup@example.com"
        database_url = f"sqlite:///{tmp_path / 'chat-test.db'}"
        graph_module._graph = None

        class GuardSupervisorLlm:
            def bind_tools(self, _tools):
                return self

            async def ainvoke(self, _messages):
                raise AssertionError("完成任务后的画像更新与路径刷新应走 force_call，不应调用 LLM")

        class WorkerPlaceholderLlm:
            pass

        with patch("app.orchestration.graph.get_supervisor_llm", return_value=GuardSupervisorLlm()), \
             patch("app.orchestration.graph.get_worker_llm", return_value=WorkerPlaceholderLlm()), \
             patch("app.orchestration.graph.get_thinking_worker_llm", return_value=WorkerPlaceholderLlm()):
            with chat_app(tmp_path) as client:
                token = _register_user(client, identifier, "majorfollow123456")

                engine = build_engine(database_url)
                with Session(engine) as session:
                    user = session.exec(select(User).where(User.identifier == identifier)).one()
                    year_path = _year_3_path()
                    year_path["current_learning_course"] = {
                        "grade_id": "year_3",
                        "course_node_id": "year_3_course_2",
                        "course_or_chapter_theme": "AI Agent 项目实战",
                        "course_goal": "完成AI Agent 项目实战",
                        "time_arrangement": year_path["grade_plans"]["year_3"]["course_nodes"][1]["time_arrangement"],
                        "current_focus": "当前阶段课程已全部完成",
                        "progress_state": "completed",
                        "next_action": "当前阶段课程已全部完成",
                    }
                    session.add(
                        UserProfile(
                            user_uid=user.uid,
                            profile_data=_basic_profile(),
                            profile_text="大三软件工程学生，目标是完成 AI 应用开发项目。",
                        )
                    )
                    session.add(
                        UserYearLearningPath(
                            user_uid=user.uid,
                            grade_year="year_3",
                            learning_topic="AI 应用开发",
                            path_data=year_path,
                        )
                    )
                    session.commit()

                start_resp = client.post(
                    "/api/chat/start",
                    json={"query": "开始"},
                    headers=_auth_header(token),
                )
                session_id = start_resp.json()["session_id"]

                completed_response = client.post(
                    "/api/chat/message",
                    json={"session_id": session_id, "message": "我不想要《AI Agent 项目实战》了，现在帮我生成一门新课"},
                    headers=_auth_header(token),
                )

                assert completed_response.status_code == 200
                assert "当前所有任务已经完成。" in completed_response.text

                refresh_response = client.post(
                    "/api/chat/message",
                    json={"session_id": session_id, "message": "专业改成计算机科学"},
                    headers=_auth_header(token),
                )

                assert refresh_response.status_code == 200
                assert "学习路径已生成" in refresh_response.text
                assert "AI 应用开发基础能力搭建" in refresh_response.text
                assert "profile_agent" in refresh_response.text
                assert "learning_path_agent" in refresh_response.text

                with Session(engine) as session:
                    user = session.exec(select(User).where(User.identifier == identifier)).one()
                    profile_row = session.get(UserProfile, user.uid)
                    assert profile_row is not None
                    assert profile_row.profile_data["confirmed_info"]["current_grade"] == "大三"
                    assert profile_row.profile_data["confirmed_info"]["major"] == "计算机科学"

                    year_3_path = session.exec(
                        select(UserYearLearningPath).where(
                            UserYearLearningPath.user_uid == user.uid,
                            UserYearLearningPath.grade_year == "year_3",
                        )
                    ).one()
                    assert year_3_path.path_data["learner_baseline"]["major"] == "计算机科学"
                    assert year_3_path.path_data["current_learning_course"]["course_node_id"] == "year_3_course_1"

        graph_module._graph = None

    def test_send_message_updates_multiple_explicit_profile_fields_and_refreshes_learning_path(self, tmp_path: Path) -> None:
        identifier = "completed-multi-field-followup@example.com"
        database_url = f"sqlite:///{tmp_path / 'chat-test.db'}"
        graph_module._graph = None

        class GuardSupervisorLlm:
            def bind_tools(self, _tools):
                return self

            async def ainvoke(self, _messages):
                raise AssertionError("完成任务后的画像更新与路径刷新应走 force_call，不应调用 LLM")

        class WorkerPlaceholderLlm:
            pass

        with patch("app.orchestration.graph.get_supervisor_llm", return_value=GuardSupervisorLlm()), \
             patch("app.orchestration.graph.get_worker_llm", return_value=WorkerPlaceholderLlm()), \
             patch("app.orchestration.graph.get_thinking_worker_llm", return_value=WorkerPlaceholderLlm()):
            with chat_app(tmp_path) as client:
                token = _register_user(client, identifier, "multifield123456")

                engine = build_engine(database_url)
                with Session(engine) as session:
                    user = session.exec(select(User).where(User.identifier == identifier)).one()
                    year_path = _year_3_path()
                    year_path["current_learning_course"] = {
                        "grade_id": "year_3",
                        "course_node_id": "year_3_course_2",
                        "course_or_chapter_theme": "AI Agent 项目实战",
                        "course_goal": "完成AI Agent 项目实战",
                        "time_arrangement": year_path["grade_plans"]["year_3"]["course_nodes"][1]["time_arrangement"],
                        "current_focus": "当前阶段课程已全部完成",
                        "progress_state": "completed",
                        "next_action": "当前阶段课程已全部完成",
                    }
                    session.add(
                        UserProfile(
                            user_uid=user.uid,
                            profile_data=_basic_profile(),
                            profile_text="大三软件工程学生，目标是完成 AI 应用开发项目。",
                        )
                    )
                    session.add(
                        UserYearLearningPath(
                            user_uid=user.uid,
                            grade_year="year_3",
                            learning_topic="AI 应用开发",
                            path_data=year_path,
                        )
                    )
                    session.commit()

                start_resp = client.post(
                    "/api/chat/start",
                    json={"query": "开始"},
                    headers=_auth_header(token),
                )
                session_id = start_resp.json()["session_id"]

                completed_response = client.post(
                    "/api/chat/message",
                    json={"session_id": session_id, "message": "我不想要《AI Agent 项目实战》了，现在帮我生成一门新课"},
                    headers=_auth_header(token),
                )

                assert completed_response.status_code == 200
                assert "当前所有任务已经完成。" in completed_response.text

                refresh_response = client.post(
                    "/api/chat/message",
                    json={"session_id": session_id, "message": "专业改成计算机科学，当前限制改成周末集中"},
                    headers=_auth_header(token),
                )

                assert refresh_response.status_code == 200
                assert "学习路径已生成" in refresh_response.text
                assert "AI 应用开发基础能力搭建" in refresh_response.text
                assert "profile_agent" in refresh_response.text
                assert "learning_path_agent" in refresh_response.text

                with Session(engine) as session:
                    user = session.exec(select(User).where(User.identifier == identifier)).one()
                    profile_row = session.get(UserProfile, user.uid)
                    assert profile_row is not None
                    assert profile_row.profile_data["confirmed_info"]["current_grade"] == "大三"
                    assert profile_row.profile_data["confirmed_info"]["major"] == "计算机科学"
                    assert profile_row.profile_data["confirmed_info"]["constraints"] == "周末集中"

                    year_3_path = session.exec(
                        select(UserYearLearningPath).where(
                            UserYearLearningPath.user_uid == user.uid,
                            UserYearLearningPath.grade_year == "year_3",
                        )
                    ).one()
                    assert year_3_path.path_data["learner_baseline"]["major"] == "计算机科学"
                    assert year_3_path.path_data["learner_baseline"]["constraints"] == ["周末集中"]
                    assert year_3_path.path_data["current_learning_course"]["course_node_id"] == "year_3_course_1"

        graph_module._graph = None
