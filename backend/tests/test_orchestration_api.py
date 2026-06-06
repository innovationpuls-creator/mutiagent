from __future__ import annotations

from types import SimpleNamespace
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import app.orchestration.graph as graph_module
import app.services.conversation_session_service as conversation_session_service
from fastapi import HTTPException
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
from app.orchestration.rule_engine import (
    parse_leaf_regeneration_pending_marker,
    parse_leaf_resource_generation_request,
)

ORIGINAL_APPEND_MESSAGES = conversation_session_service.append_messages


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


def _all_years_path() -> dict:
    def course(grade_id: str, course_id: str, theme: str) -> dict:
        return {
            "course_node_id": course_id,
            "grade_id": grade_id,
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
            "key_points": ["阶段重点"],
            "difficult_points": ["阶段难点"],
            "learning_sequence": ["需求拆解", "最小闭环演示"],
            "knowledge_relations": [],
            "downstream_resource_direction_ids": [],
            "acceptance_criteria": [f"完成 {theme}"],
        }

    year_1_course = course("year_1", "year_1_course_1", "编程基础")
    year_2_course = course("year_2", "year_2_course_1", "工程化 Web 开发")
    year_3_course_1 = course("year_3", "year_3_course_1", "AI Agent 开发基础能力搭建")
    year_3_course_2 = course("year_3", "year_3_course_2", "AI Agent 项目实战")
    year_4_course = course("year_4", "year_4_course_1", "毕业项目实战")
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
            "year_1": {
                "grade_id": "year_1",
                "grade_name": "大一",
                "grade_goal": "打好编程基础",
                "course_nodes": [year_1_course],
            },
            "year_2": {
                "grade_id": "year_2",
                "grade_name": "大二",
                "grade_goal": "进入工程主线",
                "course_nodes": [year_2_course],
            },
            "year_3": {
                "grade_id": "year_3",
                "grade_name": "大三",
                "grade_goal": "完成 AI 应用开发项目",
                "course_nodes": [year_3_course_1, year_3_course_2],
            },
            "year_4": {
                "grade_id": "year_4",
                "grade_name": "大四",
                "grade_goal": "沉淀毕业项目",
                "course_nodes": [year_4_course],
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
            "time_arrangement": year_3_course_1["time_arrangement"],
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


def _leaf_generation_prompt(course_node_id: str = "year_3_course_1", chapter_section_id: str = "1") -> str:
    return "\n".join([
        "帮我生成《AI Agent 开发》第一章教学内容。",
        "",
        "[LEAF_RESOURCE_GENERATION]",
        f"course_node_id: {course_node_id}",
        f"chapter_section_id: {chapter_section_id}",
        "scope: chapter_sections",
        "mode: generate",
        "[/LEAF_RESOURCE_GENERATION]",
    ])


def test_parse_leaf_resource_generation_request_reads_exact_prompt_block() -> None:
    text = """帮我生成《AI Agent 开发》第一章教学内容。

[LEAF_RESOURCE_GENERATION]
course_node_id: year_3_course_1
chapter_section_id: 1
scope: chapter_sections
mode: generate
[/LEAF_RESOURCE_GENERATION]
"""

    parsed = parse_leaf_resource_generation_request(text)

    assert parsed == {
        "course_node_id": "year_3_course_1",
        "chapter_section_id": "1",
        "scope": "chapter_sections",
        "mode": "generate",
    }


def test_parse_leaf_regeneration_pending_marker_reads_context() -> None:
    text = """重新生成《AI Agent 开发》第一章前，请告诉我下一版需要侧重哪里。

[LEAF_REGEN_PENDING]
course_node_id: year_3_course_1
chapter_section_id: 1
[/LEAF_REGEN_PENDING]
"""

    parsed = parse_leaf_regeneration_pending_marker(text)

    assert parsed == {
        "course_node_id": "year_3_course_1",
        "chapter_section_id": "1",
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

    def test_start_chat_returns_explicit_response_shell_fields(self, tmp_path: Path) -> None:
        with chat_app(tmp_path) as client:
            token = _register_user(client, "chat-shell@example.com", "chat123456")

            response = client.post(
                "/api/chat/start",
                json={"query": "你好"},
                headers=_auth_header(token),
            )

            assert response.status_code == 200
            data = response.json()
            assert data["session_id"]
            assert data["reply_text"] == "你好！我是你的学习助手。请告诉我你的基本情况，比如年级、专业、想学什么？"
            assert data["profile"] is None
            assert data["year_learning_paths"] is None
            assert data["course_knowledge"] is None

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

    def test_get_session_state_returns_empty_messages_for_fresh_session(self, tmp_path: Path) -> None:
        with chat_app(tmp_path) as client:
            token = _register_user(client, "fresh-session@example.com", "fresh123456")

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
            data = response.json()
            assert data["session_id"] == session_id
            assert data["messages"] == []

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
    def test_send_message_rejects_nonexistent_session_id(self, mock_stream, tmp_path: Path) -> None:
        with chat_app(tmp_path) as client:
            token = _register_user(client, "missing-session@example.com", "missing123456")

            response = client.post(
                "/api/chat/message",
                json={"session_id": "missing-session-id", "message": "我想学Python"},
                headers=_auth_header(token),
            )

            assert response.status_code == 404
            assert response.json()["detail"] == "会话不存在"
            mock_stream.assert_not_called()

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
    def test_send_message_rejects_session_owned_by_another_user(self, mock_stream, tmp_path: Path) -> None:
        with chat_app(tmp_path) as client:
            owner_token = _register_user(client, "session-owner@example.com", "owner123456")
            other_token = _register_user(client, "session-other@example.com", "other123456")

            start_resp = client.post(
                "/api/chat/start",
                json={"query": "开始"},
                headers=_auth_header(owner_token),
            )
            session_id = start_resp.json()["session_id"]

            response = client.post(
                "/api/chat/message",
                json={"session_id": session_id, "message": "读取这段历史"},
                headers=_auth_header(other_token),
            )

            assert response.status_code == 404
            assert response.json()["detail"] == "会话不存在"
            mock_stream.assert_not_called()

    @patch("app.api.orchestration._load_owned_session")
    def test_send_message_streams_sse_error_when_session_disappears_after_precheck(
        self,
        mock_load_owned_session,
        tmp_path: Path,
    ) -> None:
        with chat_app(tmp_path) as client:
            token = _register_user(client, "race-session@example.com", "race123456")
            start_resp = client.post(
                "/api/chat/start",
                json={"query": "开始"},
                headers=_auth_header(token),
            )
            session_id = start_resp.json()["session_id"]

            mock_load_owned_session.side_effect = [
                SimpleNamespace(user_uid="unused", messages=[]),
                HTTPException(status_code=404, detail="会话不存在"),
            ]

            response = client.post(
                "/api/chat/message",
                json={"session_id": session_id, "message": "继续生成"},
                headers=_auth_header(token),
            )

            assert response.status_code == 200
            assert "event: error" in response.text
            assert "会话不存在" in response.text
            assert "UnboundLocalError" not in response.text
            assert mock_load_owned_session.call_count == 2

            engine = build_engine(f"sqlite:///{tmp_path / 'chat-test.db'}")
            with Session(engine) as session:
                row = session.get(ConversationSession, session_id)
                assert row is not None
                assert row.messages == []

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

    @patch("app.services.conversation_session_service.append_messages")
    @patch("app.api.orchestration.stream_orchestration_events")
    def test_send_message_keeps_only_user_message_when_graph_persistence_fails_after_completion(
        self,
        mock_stream,
        mock_append_messages,
        tmp_path: Path,
    ) -> None:
        async def mock_events(state):
            yield {"event": "message_completed", "full_text": "这是回复"}
            yield {
                "event": "session_completed",
                "session_id": state["session_id"],
                "has_profile": False,
                "has_paths": False,
                "has_outline": False,
            }

        appended_batches: list[list[dict]] = []
        def flaky_append_messages(session, session_id, new_messages):
            appended_batches.append(new_messages)
            if len(appended_batches) == 1:
                raise RuntimeError("会话持久化失败")
            return ORIGINAL_APPEND_MESSAGES(session, session_id, new_messages)

        mock_stream.side_effect = mock_events
        mock_append_messages.side_effect = flaky_append_messages

        with chat_app(tmp_path) as client:
            token = _register_user(client, "graph-persist@example.com", "graph123456")
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
            assert "会话持久化失败" in response.text
            assert "message_completed" not in response.text
            assert "session_completed" not in response.text
            assert len(appended_batches) == 2
            assert len(appended_batches[0]) == 2
            assert len(appended_batches[1]) == 1

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
    def test_send_message_regenerates_outline_instead_of_reusing_existing_outline(self, mock_stream, tmp_path: Path) -> None:
        async def regenerated_events(state):
            assert state["query"] == "重新生成该课程的大纲"
            yield {"event": "agent_calling", "agent": "course_knowledge_agent", "label": "课程大纲智能体"}
            yield {"event": "message_completed", "full_text": "课程大纲已重新生成。"}
            yield {
                "event": "session_completed",
                "session_id": state["session_id"],
                "has_profile": True,
                "has_paths": True,
                "has_outline": True,
            }

        mock_stream.side_effect = regenerated_events
        identifier = "outline-regenerate@example.com"
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
                json={"session_id": session_id, "message": "重新生成该课程的大纲"},
                headers=_auth_header(token),
            )

            assert response.status_code == 200
            assert "course_knowledge_agent" in response.text
            assert "课程大纲已重新生成。" in response.text
            assert "course_knowledge_loaded" not in response.text
            assert mock_stream.called

    @patch("app.api.orchestration.stream_orchestration_events")
    def test_send_message_returns_detailed_outline_for_section_detail_query(self, mock_stream, tmp_path: Path) -> None:
        mock_stream.side_effect = AssertionError("已有课程大纲细节应直接从数据库返回")
        identifier = "outline-detail@example.com"
        database_url = f"sqlite:///{tmp_path / 'chat-test.db'}"

        with chat_app(tmp_path) as client:
            token = _register_user(client, identifier, "outline123456")
            _seed_existing_learning_data(database_url, identifier)
            engine = build_engine(database_url)
            with Session(engine) as session:
                user = session.exec(select(User).where(User.identifier == identifier)).one()
                row = session.get(UserCourseKnowledgeOutline, (user.uid, "year_3_course_1"))
                assert row is not None
                outline_data = dict(row.outline_data)
                outline_data["sections"] = [
                    {
                        "section_id": "1",
                        "parent_section_id": None,
                        "depth": 1,
                        "title": "需求拆解",
                        "order_index": 1,
                        "description": "确认功能边界与验收标准。",
                        "key_knowledge_points": ["功能边界", "验收标准"],
                    },
                    {
                        "section_id": "1.1",
                        "parent_section_id": "1",
                        "depth": 2,
                        "title": "学习目标",
                        "order_index": 1,
                        "description": "明确本章完成后的交付物。",
                        "key_knowledge_points": ["OpenAI-compatible API 调用"],
                    },
                ]
                row.outline_data = outline_data
                session.add(row)
                session.commit()

            start_resp = client.post(
                "/api/chat/start",
                json={"query": "开始"},
                headers=_auth_header(token),
            )
            session_id = start_resp.json()["session_id"]

            response = client.post(
                "/api/chat/message",
                json={"session_id": session_id, "message": "查看这门课的具体章节大纲细节"},
                headers=_auth_header(token),
            )

            assert response.status_code == 200
            assert "1.1 学习目标" in response.text
            assert "明确本章完成后的交付物。" in response.text
            assert "核心知识点：OpenAI-compatible API 调用" in response.text
            assert "course_knowledge_agent" not in response.text

    @patch("app.api.orchestration.stream_orchestration_events")
    def test_send_message_returns_current_course_next_step_for_now_query(self, mock_stream, tmp_path: Path) -> None:
        mock_stream.side_effect = AssertionError("已有课程大纲时下一步提示应直接由当前课程状态生成")
        identifier = "outline-next-step@example.com"
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
                json={"session_id": session_id, "message": "现在我应该干嘛"},
                headers=_auth_header(token),
            )

            assert response.status_code == 200
            assert "下一步：进入《AI Agent 开发基础能力搭建》的第一章：需求拆解。" in response.text
            assert "直接发送：开始学习这门课" in response.text
            assert "course_knowledge_agent" not in response.text

    def test_send_message_generates_section_resources_from_chat(self, tmp_path: Path) -> None:
        identifier = "resource-chat@example.com"
        database_url = f"sqlite:///{tmp_path / 'chat-test.db'}"

        async def resource_events(state):
            course_knowledge = dict(state["course_knowledge"])
            course_knowledge["section_markdowns"] = {
                "1.1": {
                    "section_id": "1.1",
                    "parent_section_id": "1",
                    "title": "学习目标",
                    "markdown": "# 学习目标\n\n完整教学内容",
                    "animation_briefs": [],
                    "generated_at": "2026-06-06T00:00:00Z",
                }
            }
            course_knowledge["section_video_links"] = {
                "1.1": {
                    "section_id": "1.1",
                    "parent_section_id": "1",
                    "query": "AI 应用开发 学习目标 视频教程",
                    "videos": [
                        {
                            "title": "学习目标视频",
                            "url": "https://example.com/video",
                            "cover_url": "data:image/svg+xml;utf8,<svg></svg>",
                            "cover_status": "fallback",
                            "source": "example.com",
                        }
                    ],
                    "generated_at": "2026-06-06T00:00:00Z",
                }
            }
            course_knowledge["section_html_animations"] = {
                "1.1": {
                    "section_id": "1.1",
                    "parent_section_id": "1",
                    "animations": [],
                    "generated_at": "2026-06-06T00:00:00Z",
                }
            }
            from app.services.course_knowledge_service import upsert_user_course_knowledge_outline

            with Session(build_engine(database_url)) as session:
                upsert_user_course_knowledge_outline(session, state["user_id"], course_knowledge)
            yield {"event": "message_completed", "full_text": "《AI Agent 开发基础能力搭建》的 1.1 教学内容已生成：每个小节都有 Markdown 文档，视频与动画资源已同步保存。"}
            yield {
                "event": "session_completed",
                "session_id": state["session_id"],
                "has_profile": True,
                "has_paths": True,
                "has_outline": True,
            }

        with patch("app.api.orchestration.stream_orchestration_events", side_effect=resource_events):
            with chat_app(tmp_path) as client:
                token = _register_user(client, identifier, "resource123456")
                _seed_existing_learning_data(database_url, identifier)
                start_resp = client.post(
                    "/api/chat/start",
                    json={"query": "开始"},
                    headers=_auth_header(token),
                )
                session_id = start_resp.json()["session_id"]

                response = client.post(
                    "/api/chat/message",
                    json={"session_id": session_id, "message": "请根据课程大纲生成教学内容"},
                    headers=_auth_header(token),
                )

                assert response.status_code == 200
                assert "教学内容已生成" in response.text

                summary_response = client.post(
                    "/api/chat/message",
                    json={"session_id": session_id, "message": "查看课程大纲"},
                    headers=_auth_header(token),
                )

                assert summary_response.status_code == 200
                assert "已生成教学文档" in summary_response.text
                assert "已生成视频资源" in summary_response.text
                assert "已生成动画资源" in summary_response.text
                assert "1.1" in summary_response.text

        engine = build_engine(database_url)
        with Session(engine) as session:
            row = session.exec(select(UserCourseKnowledgeOutline)).one()

        assert "1.1" in row.outline_data["section_markdowns"]
        assert row.outline_data["section_video_links"]["1.1"]["videos"][0]["url"] == "https://example.com/video"

    def test_send_message_streams_leaf_generation_events_from_prompt_block(self, tmp_path: Path) -> None:
        identifier = "leaf-stream@example.com"
        database_url = f"sqlite:///{tmp_path / 'chat-test.db'}"
        captured = {}

        async def leaf_events(state, _llm, _search_llm, *, course_id, chapter_section_id, regeneration_focus=""):
            captured["user_id"] = state["user_id"]
            captured["course_id"] = course_id
            captured["chapter_section_id"] = chapter_section_id
            captured["regeneration_focus"] = regeneration_focus
            yield {
                "event": "agent_progress",
                "course_id": course_id,
                "chapter_section_id": chapter_section_id,
                "section_id": "1.1",
                "phase": "markdown",
                "status": "running",
                "kind": "course_resource_section",
            }
            yield {"event": "message_completed", "full_text": "本章教学内容已生成。"}
            yield {
                "event": "session_completed",
                "session_id": state["session_id"],
                "has_profile": True,
                "has_paths": True,
                "has_outline": True,
            }

        with patch("app.orchestration.llm.get_thinking_worker_llm", return_value=object()):
            with patch("app.orchestration.llm.get_search_worker_llm", return_value=object()):
                with patch(
                    "app.orchestration.agents.course_resources.stream_chapter_resource_generation",
                    side_effect=leaf_events,
                ):
                    with chat_app(tmp_path) as client:
                        token = _register_user(client, identifier, "leaf123456")
                        _seed_existing_learning_data(database_url, identifier)
                        start_resp = client.post(
                            "/api/chat/start",
                            json={"query": "开始"},
                            headers=_auth_header(token),
                        )
                        session_id = start_resp.json()["session_id"]

                        response = client.post(
                            "/api/chat/message",
                            json={"session_id": session_id, "message": _leaf_generation_prompt()},
                            headers=_auth_header(token),
                        )

        assert response.status_code == 200
        assert "\"course_id\": \"year_3_course_1\"" in response.text
        assert "\"chapter_section_id\": \"1\"" in response.text
        assert "\"section_id\": \"1.1\"" in response.text
        assert "\"phase\": \"markdown\"" in response.text
        assert "\"status\": \"running\"" in response.text
        assert "\"kind\": \"course_resource_section\"" in response.text
        assert captured["course_id"] == "year_3_course_1"
        assert captured["chapter_section_id"] == "1"
        assert captured["regeneration_focus"] == ""

    def test_send_message_leaf_generation_rejects_non_current_course(self, tmp_path: Path) -> None:
        identifier = "leaf-non-current@example.com"
        database_url = f"sqlite:///{tmp_path / 'chat-test.db'}"

        with patch(
            "app.orchestration.agents.course_resources.stream_chapter_resource_generation",
            side_effect=AssertionError("非当前课程不应触发叶子资源生成"),
        ):
            with chat_app(tmp_path) as client:
                token = _register_user(client, identifier, "leaf123456")
                _seed_existing_learning_data(database_url, identifier)
                start_resp = client.post(
                    "/api/chat/start",
                    json={"query": "开始"},
                    headers=_auth_header(token),
                )
                session_id = start_resp.json()["session_id"]

                response = client.post(
                    "/api/chat/message",
                    json={"session_id": session_id, "message": _leaf_generation_prompt("year_3_course_2", "1")},
                    headers=_auth_header(token),
                )

        assert response.status_code == 200
        assert "只能为当前课程生成教学内容。" in response.text

    def test_send_message_leaf_generation_rejects_non_first_chapter(self, tmp_path: Path) -> None:
        identifier = "leaf-non-first@example.com"
        database_url = f"sqlite:///{tmp_path / 'chat-test.db'}"

        with patch(
            "app.orchestration.agents.course_resources.stream_chapter_resource_generation",
            side_effect=AssertionError("非第一章不应触发叶子资源生成"),
        ):
            with chat_app(tmp_path) as client:
                token = _register_user(client, identifier, "leaf123456")
                _seed_existing_learning_data(database_url, identifier)
                start_resp = client.post(
                    "/api/chat/start",
                    json={"query": "开始"},
                    headers=_auth_header(token),
                )
                session_id = start_resp.json()["session_id"]

                response = client.post(
                    "/api/chat/message",
                    json={"session_id": session_id, "message": _leaf_generation_prompt("year_3_course_1", "2")},
                    headers=_auth_header(token),
                )

        assert response.status_code == 200
        assert "通过章节测验后会开放下一章内容生成。" in response.text

    def test_send_message_leaf_generation_asks_focus_before_regenerating_existing_content(self, tmp_path: Path) -> None:
        identifier = "leaf-regen@example.com"
        database_url = f"sqlite:///{tmp_path / 'chat-test.db'}"
        captured = {}

        async def leaf_events(state, _llm, _search_llm, *, course_id, chapter_section_id, regeneration_focus=""):
            captured["course_id"] = course_id
            captured["chapter_section_id"] = chapter_section_id
            captured["regeneration_focus"] = regeneration_focus
            yield {"event": "message_completed", "full_text": "本章教学内容已生成。"}
            yield {
                "event": "session_completed",
                "session_id": state["session_id"],
                "has_profile": True,
                "has_paths": True,
                "has_outline": True,
            }

        with patch("app.orchestration.llm.get_thinking_worker_llm", return_value=object()):
            with patch("app.orchestration.llm.get_search_worker_llm", return_value=object()):
                with patch(
                    "app.orchestration.agents.course_resources.stream_chapter_resource_generation",
                    side_effect=leaf_events,
                ):
                    with chat_app(tmp_path) as client:
                        token = _register_user(client, identifier, "leaf123456")
                        _seed_existing_learning_data(database_url, identifier)
                        engine = build_engine(database_url)
                        with Session(engine) as session:
                            user = session.exec(select(User).where(User.identifier == identifier)).one()
                            row = session.get(UserCourseKnowledgeOutline, (user.uid, "year_3_course_1"))
                            assert row is not None
                            outline_data = dict(row.outline_data)
                            outline_data["section_composed_markdowns"] = {
                                "1.1": {
                                    "section_id": "1.1",
                                    "parent_section_id": "1",
                                    "title": "学习目标",
                                    "markdown": "# 学习目标",
                                    "blocks": [{"type": "markdown", "markdown": "# 学习目标"}],
                                    "generated_at": "2026-06-06T00:00:00Z",
                                }
                            }
                            row.outline_data = outline_data
                            session.add(row)
                            session.commit()

                        start_resp = client.post(
                            "/api/chat/start",
                            json={"query": "开始"},
                            headers=_auth_header(token),
                        )
                        session_id = start_resp.json()["session_id"]

                        first_response = client.post(
                            "/api/chat/message",
                            json={"session_id": session_id, "message": _leaf_generation_prompt()},
                            headers=_auth_header(token),
                        )
                        second_response = client.post(
                            "/api/chat/message",
                            json={"session_id": session_id, "message": "请更关注实践任务和检查标准"},
                            headers=_auth_header(token),
                        )

        assert first_response.status_code == 200
        assert "重新生成本章前，请告诉我下一版需要侧重哪里。" in first_response.text
        assert "[LEAF_REGEN_PENDING]" in first_response.text
        assert second_response.status_code == 200
        assert "本章教学内容已生成。" in second_response.text
        assert captured["course_id"] == "year_3_course_1"
        assert captured["chapter_section_id"] == "1"
        assert captured["regeneration_focus"] == "请更关注实践任务和检查标准"

    @patch("app.services.conversation_session_service.append_messages")
    @patch("app.api.orchestration.stream_orchestration_events")
    def test_send_message_keeps_only_user_message_when_outline_shortcut_persistence_fails(
        self,
        mock_stream,
        mock_append_messages,
        tmp_path: Path,
    ) -> None:
        mock_stream.side_effect = AssertionError("已有课程大纲应直接从数据库返回")
        identifier = "outline-persist@example.com"
        database_url = f"sqlite:///{tmp_path / 'chat-test.db'}"
        appended_batches: list[list[dict]] = []
        def flaky_append_messages(session, session_id, new_messages):
            appended_batches.append(new_messages)
            if len(appended_batches) == 1:
                raise RuntimeError("课程大纲会话持久化失败")
            return ORIGINAL_APPEND_MESSAGES(session, session_id, new_messages)

        mock_append_messages.side_effect = flaky_append_messages

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
            assert "event: error" in response.text
            assert "课程大纲会话持久化失败" in response.text
            assert "message_completed" not in response.text
            assert "session_completed" not in response.text
            assert len(appended_batches) == 2
            assert len(appended_batches[0]) == 2
            assert len(appended_batches[1]) == 1

            engine = build_engine(database_url)
            with Session(engine) as session:
                row = session.get(ConversationSession, session_id)
                assert row is not None
                assert len(row.messages) == 1
                assert row.messages[0]["type"] == "human"
                assert row.messages[0]["data"]["content"] == "给我看看这个课的大纲"

    @patch("app.api.orchestration.stream_orchestration_events")
    def test_send_message_start_first_course_reuses_existing_outline_without_agent_call(self, mock_stream, tmp_path: Path) -> None:
        mock_stream.side_effect = AssertionError("开始第一门课时已有当前课程大纲应直接从数据库返回")
        identifier = "outline-start-direct@example.com"
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
                json={"session_id": session_id, "message": "开始第一门课"},
                headers=_auth_header(token),
            )

            assert response.status_code == 200
            assert "course_knowledge_loaded" in response.text
            assert "课程大纲 · year_3" in response.text
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
                assert row.messages[1]["data"]["content"].startswith("课程大纲 · year_3")

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
    def test_send_message_review_shortcut_lists_courses_by_grade_for_single_multi_year_path_row(self, mock_stream, tmp_path: Path) -> None:
        mock_stream.side_effect = AssertionError("回顾学习路径短语应直接从数据库返回")
        identifier = "path-multi-year-shortcut@example.com"
        database_url = f"sqlite:///{tmp_path / 'chat-test.db'}"

        with chat_app(tmp_path) as client:
            token = _register_user(client, identifier, "path123456")
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
                        path_data=_all_years_path(),
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
            assert "大一（year_1）：1 门课" in response.text
            assert "大二（year_2）：1 门课" in response.text
            assert "大三（year_3）：2 门课" in response.text
            assert "大四（year_4）：1 门课" in response.text
            assert "1. 编程基础：完成编程基础" in response.text
            assert "1. 工程化 Web 开发：完成工程化 Web 开发" in response.text
            assert "1. AI Agent 开发基础能力搭建：完成AI Agent 开发基础能力搭建" in response.text
            assert "2. AI Agent 项目实战：完成AI Agent 项目实战" in response.text
            assert "1. 毕业项目实战：完成毕业项目实战" in response.text

    @patch("app.api.orchestration.stream_orchestration_events")
    def test_send_message_does_not_treat_generic_look_first_phrase_as_learning_path_review(self, mock_stream, tmp_path: Path) -> None:
        async def mock_events(_state):
            yield {"event": "message_completed", "full_text": "这是画像建议"}
            yield {
                "event": "session_completed",
                "session_id": "unused",
                "has_profile": True,
                "has_paths": True,
                "has_outline": True,
            }

        mock_stream.side_effect = mock_events
        identifier = "path-generic-look-first@example.com"
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
                json={"session_id": session_id, "message": "我先看看我的个人画像，你推荐什么？"},
                headers=_auth_header(token),
            )

            assert response.status_code == 200
            assert "这是画像建议" in response.text
            assert "learning_path_loaded" not in response.text
            assert "你的学习路径里已经有这些课程：" not in response.text
            mock_stream.assert_called_once()

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

    def test_send_message_prompts_for_profile_details_on_punctuated_generic_profile_update(self, tmp_path: Path) -> None:
        identifier = "profile-update-direct-punctuated@example.com"
        database_url = f"sqlite:///{tmp_path / 'chat-test.db'}"
        graph_module._graph = None

        class GuardSupervisorLlm:
            def bind_tools(self, _tools):
                return self

            async def ainvoke(self, _messages):
                raise AssertionError("带标点的泛化画像更新提示也应走 force_call 收口，不应调用 LLM")

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
                    json={"session_id": session_id, "message": "更新个人画像。"},
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

    def test_send_message_collects_profile_again_for_unsupported_postgraduate_grade(self, tmp_path: Path) -> None:
        identifier = "unsupported-postgraduate-grade@example.com"
        database_url = f"sqlite:///{tmp_path / 'chat-test.db'}"
        graph_module._graph = None

        class GuardSupervisorLlm:
            def bind_tools(self, _tools):
                return self

            async def ainvoke(self, _messages):
                raise AssertionError("不支持的研究生年级应走 force_call + 本地画像收集，不应调用 LLM")

        class WorkerPlaceholderLlm:
            pass

        with patch("app.orchestration.graph.get_supervisor_llm", return_value=GuardSupervisorLlm()), \
             patch("app.orchestration.graph.get_worker_llm", return_value=WorkerPlaceholderLlm()), \
             patch("app.orchestration.graph.get_thinking_worker_llm", return_value=WorkerPlaceholderLlm()):
            with chat_app(tmp_path) as client:
                token = _register_user(client, identifier, "unsupported123456")

                start_resp = client.post(
                    "/api/chat/start",
                    json={"query": "开始"},
                    headers=_auth_header(token),
                )
                session_id = start_resp.json()["session_id"]

                response = client.post(
                    "/api/chat/message",
                    json={"session_id": session_id, "message": "研一，软件工程，AI，周末集中"},
                    headers=_auth_header(token),
                )

                assert response.status_code == 200
                assert "当前学习路径只支持大一到大四。你当前提供的年级是「研一」，请先确认对应的本科年级。" in response.text
                assert "\"has_profile\": false" in response.text
                assert "profile_agent" in response.text
                assert "learning_path_agent" not in response.text

                engine = build_engine(database_url)
                with Session(engine) as session:
                    user = session.exec(select(User).where(User.identifier == identifier)).one()
                    profile_row = session.get(UserProfile, user.uid)
                    assert profile_row is not None
                    assert profile_row.profile_data["type"] == "collecting"
                    assert profile_row.profile_data["confirmed_info"]["current_grade"] == "研一"

                    year_paths = session.exec(
                        select(UserYearLearningPath).where(UserYearLearningPath.user_uid == user.uid)
                    ).all()
                    assert year_paths == []

                    conversation_row = session.get(ConversationSession, session_id)
                    assert conversation_row is not None
                    assert len(conversation_row.messages) == 2
                    assert conversation_row.messages[1]["type"] == "ai"
                    assert conversation_row.messages[1]["data"]["content"].startswith("当前学习路径只支持大一到大四。")

        graph_module._graph = None

    def test_send_message_updates_existing_profile_without_reusing_stale_course_outline(self, tmp_path: Path) -> None:
        identifier = "profile-update-existing-path@example.com"
        database_url = f"sqlite:///{tmp_path / 'chat-test.db'}"
        graph_module._graph = None

        class GuardSupervisorLlm:
            def bind_tools(self, _tools):
                return self

            async def ainvoke(self, _messages):
                raise AssertionError("已有画像时的显式字段更新应走 force_call，不应调用 LLM")

        class WorkerPlaceholderLlm:
            pass

        with patch("app.orchestration.graph.get_supervisor_llm", return_value=GuardSupervisorLlm()), \
             patch("app.orchestration.graph.get_worker_llm", return_value=WorkerPlaceholderLlm()), \
             patch("app.orchestration.graph.get_thinking_worker_llm", return_value=WorkerPlaceholderLlm()):
            with chat_app(tmp_path) as client:
                token = _register_user(client, identifier, "profileupdate123456")
                _seed_existing_learning_data(database_url, identifier)

                start_resp = client.post(
                    "/api/chat/start",
                    json={"query": "开始"},
                    headers=_auth_header(token),
                )
                session_id = start_resp.json()["session_id"]

                response = client.post(
                    "/api/chat/message",
                    json={"session_id": session_id, "message": "专业改成计算机科学，当前限制改成周末集中"},
                    headers=_auth_header(token),
                )

                assert response.status_code == 200
                assert "profile_agent" in response.text
                assert "learning_path_agent" not in response.text
                assert "课程大纲已生成：《AI Agent 开发基础能力搭建》" not in response.text
                assert "【基础学习画像总结】大三计算机科学" in response.text

                engine = build_engine(database_url)
                with Session(engine) as session:
                    user = session.exec(select(User).where(User.identifier == identifier)).one()
                    profile_row = session.get(UserProfile, user.uid)
                    assert profile_row is not None
                    assert profile_row.profile_data["confirmed_info"]["major"] == "计算机科学"
                    assert profile_row.profile_data["confirmed_info"]["constraints"] == "周末集中"
                    assert session.get(UserCourseKnowledgeOutline, (user.uid, "year_3_course_1")) is None

                    conversation_row = session.get(ConversationSession, session_id)
                    assert conversation_row is not None
                    assert len(conversation_row.messages) == 2
                    assert conversation_row.messages[1]["type"] == "ai"
                    assert conversation_row.messages[1]["data"]["content"].startswith("【基础学习画像总结】大三计算机科学")

                dashboard_response = client.get(
                    "/api/profile/dashboard",
                    headers=_auth_header(token),
                )
                assert dashboard_response.status_code == 200
                assert dashboard_response.json()["todayLearning"]["currentCourseOutline"] is None

                branch_response = client.get(
                    "/api/branch/overview",
                    headers=_auth_header(token),
                )
                assert branch_response.status_code == 200
                branch_year_3 = branch_response.json()["years"]["year_3"]
                assert branch_year_3["has_outline_content"] is False
                assert branch_year_3["courses"][0]["has_outline"] is False

        graph_module._graph = None

    def test_send_message_updates_single_explicit_profile_field_with_existing_path_without_calling_llm(self, tmp_path: Path) -> None:
        identifier = "profile-update-single-field@example.com"
        database_url = f"sqlite:///{tmp_path / 'chat-test.db'}"
        graph_module._graph = None

        class GuardSupervisorLlm:
            def bind_tools(self, _tools):
                return self

            async def ainvoke(self, _messages):
                raise AssertionError("已有画像时的单字段显式更新应走 force_call，不应调用 LLM")

        class WorkerPlaceholderLlm:
            pass

        with patch("app.orchestration.graph.get_supervisor_llm", return_value=GuardSupervisorLlm()), \
             patch("app.orchestration.graph.get_worker_llm", return_value=WorkerPlaceholderLlm()), \
             patch("app.orchestration.graph.get_thinking_worker_llm", return_value=WorkerPlaceholderLlm()):
            with chat_app(tmp_path) as client:
                token = _register_user(client, identifier, "profileupdate123456")
                _seed_existing_learning_data(database_url, identifier)

                start_resp = client.post(
                    "/api/chat/start",
                    json={"query": "开始"},
                    headers=_auth_header(token),
                )
                session_id = start_resp.json()["session_id"]

                response = client.post(
                    "/api/chat/message",
                    json={"session_id": session_id, "message": "专业改成计算机科学"},
                    headers=_auth_header(token),
                )

                assert response.status_code == 200
                assert "profile_agent" in response.text
                assert "learning_path_agent" not in response.text
                assert "课程大纲已生成：《AI Agent 开发基础能力搭建》" not in response.text
                assert "【基础学习画像总结】大三计算机科学" in response.text

                engine = build_engine(database_url)
                with Session(engine) as session:
                    user = session.exec(select(User).where(User.identifier == identifier)).one()
                    profile_row = session.get(UserProfile, user.uid)
                    assert profile_row is not None
                    assert profile_row.profile_data["confirmed_info"]["major"] == "计算机科学"
                    assert session.get(UserCourseKnowledgeOutline, (user.uid, "year_3_course_1")) is None

                    conversation_row = session.get(ConversationSession, session_id)
                    assert conversation_row is not None
                    assert len(conversation_row.messages) == 2
                    assert conversation_row.messages[1]["type"] == "ai"
                    assert conversation_row.messages[1]["data"]["content"].startswith("【基础学习画像总结】大三计算机科学")

                dashboard_response = client.get(
                    "/api/profile/dashboard",
                    headers=_auth_header(token),
                )
                assert dashboard_response.status_code == 200
                assert dashboard_response.json()["todayLearning"]["currentCourseOutline"] is None

                branch_response = client.get(
                    "/api/branch/overview",
                    headers=_auth_header(token),
                )
                assert branch_response.status_code == 200
                branch_year_3 = branch_response.json()["years"]["year_3"]
                assert branch_year_3["has_outline_content"] is False
                assert branch_year_3["courses"][0]["has_outline"] is False

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
                    profile_data = _basic_profile()
                    profile_data["confirmed_info"]["knowledge_foundation"] = "已具备软件工程基础，AI 应用开发方向可从入门到基础逐步补全"
                    session.add(
                        UserProfile(
                            user_uid=user.uid,
                            profile_data=profile_data,
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
                    session.add(
                        UserCourseKnowledgeOutline(
                            user_uid=user.uid,
                            course_id="year_3_course_1",
                            grade_year="year_3",
                            course_name="AI Agent 开发基础能力搭建",
                            outline_data={
                                **_course_outline(),
                                "personalization_summary": "针对大三软件工程背景，先完成需求拆解，再进入接口接入与最小闭环演示。",
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

    def test_send_message_collects_profile_without_refreshing_path_when_followup_grade_is_unsupported(self, tmp_path: Path) -> None:
        identifier = "completed-unsupported-followup@example.com"
        database_url = f"sqlite:///{tmp_path / 'chat-test.db'}"
        graph_module._graph = None

        class GuardSupervisorLlm:
            def bind_tools(self, _tools):
                return self

            async def ainvoke(self, _messages):
                raise AssertionError("完成任务后的不支持年级跟进应走 force_call，不应调用 LLM")

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
                    profile_data = _basic_profile()
                    profile_data["confirmed_info"]["knowledge_foundation"] = "已具备软件工程基础，AI 应用开发方向可从入门到基础逐步补全"
                    session.add(
                        UserProfile(
                            user_uid=user.uid,
                            profile_data=profile_data,
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

                followup_response = client.post(
                    "/api/chat/message",
                    json={"session_id": session_id, "message": "研一，软件工程，AI，周末集中"},
                    headers=_auth_header(token),
                )

                assert followup_response.status_code == 200
                assert "当前学习路径只支持大一到大四。你当前提供的年级是「研一」，请先确认对应的本科年级。" in followup_response.text
                assert "\"has_profile\": false" in followup_response.text
                assert "profile_agent" in followup_response.text
                assert "learning_path_agent" not in followup_response.text

                with Session(engine) as session:
                    user = session.exec(select(User).where(User.identifier == identifier)).one()
                    profile_row = session.get(UserProfile, user.uid)
                    assert profile_row is not None
                    assert profile_row.profile_data["type"] == "collecting"
                    assert profile_row.profile_data["confirmed_info"]["current_grade"] == "研一"

                    year_paths = session.exec(
                        select(UserYearLearningPath).where(UserYearLearningPath.user_uid == user.uid)
                    ).all()
                    assert len(year_paths) == 1
                    assert year_paths[0].grade_year == "year_3"
                    assert session.get(UserCourseKnowledgeOutline, (user.uid, "year_3_course_1")) is None

                    conversation_row = session.get(ConversationSession, session_id)
                    assert conversation_row is not None
                    assert len(conversation_row.messages) == 4
                    assert conversation_row.messages[3]["type"] == "ai"
                    assert conversation_row.messages[3]["data"]["content"].startswith("当前学习路径只支持大一到大四。")

                dashboard_response = client.get(
                    "/api/profile/dashboard",
                    headers=_auth_header(token),
                )
                assert dashboard_response.status_code == 200
                dashboard_body = dashboard_response.json()
                assert dashboard_body["todayLearning"]["currentLearningCourse"]["course_node_id"] == "year_3_course_2"
                assert dashboard_body["todayLearning"]["currentCourseOutline"] is None

                branch_response = client.get(
                    "/api/branch/overview",
                    headers=_auth_header(token),
                )
                assert branch_response.status_code == 200
                branch_year_3 = branch_response.json()["years"]["year_3"]
                assert branch_year_3["has_outline_content"] is False
                assert branch_year_3["courses"][0]["has_outline"] is False

        graph_module._graph = None

    def test_send_message_prompts_for_profile_details_when_user_only_says_next_step_after_completed_tasks(self, tmp_path: Path) -> None:
        identifier = "completed-next-step@example.com"
        database_url = f"sqlite:///{tmp_path / 'chat-test.db'}"
        graph_module._graph = None

        class GuardSupervisorLlm:
            def bind_tools(self, _tools):
                return self

            async def ainvoke(self, _messages):
                raise AssertionError("完成任务后的下一步提示应走 force_call 收口，不应调用 LLM")

        class WorkerPlaceholderLlm:
            pass

        with patch("app.orchestration.graph.get_supervisor_llm", return_value=GuardSupervisorLlm()), \
             patch("app.orchestration.graph.get_worker_llm", return_value=WorkerPlaceholderLlm()), \
             patch("app.orchestration.graph.get_thinking_worker_llm", return_value=WorkerPlaceholderLlm()):
            with chat_app(tmp_path) as client:
                token = _register_user(client, identifier, "nextstep123456")

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
                    profile_data = _basic_profile()
                    profile_data["confirmed_info"]["knowledge_foundation"] = "已具备软件工程基础，AI 应用开发方向可从入门到基础逐步补全"
                    session.add(
                        UserProfile(
                            user_uid=user.uid,
                            profile_data=profile_data,
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

                followup_response = client.post(
                    "/api/chat/message",
                    json={"session_id": session_id, "message": "下一步"},
                    headers=_auth_header(token),
                )

                assert followup_response.status_code == 200
                assert "为了继续更新个人画像" in followup_response.text or "请先直接告诉我你想调整的具体信息" in followup_response.text
                assert "profile_agent" not in followup_response.text
                assert "course_knowledge_agent" not in followup_response.text

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
                    profile_data = _basic_profile()
                    profile_data["confirmed_info"]["knowledge_foundation"] = "已具备软件工程基础，AI 应用开发方向可从入门到基础逐步补全"
                    session.add(
                        UserProfile(
                            user_uid=user.uid,
                            profile_data=profile_data,
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
                    session.add(
                        UserCourseKnowledgeOutline(
                            user_uid=user.uid,
                            course_id="year_3_course_1",
                            grade_year="year_3",
                            course_name="AI Agent 开发基础能力搭建",
                            outline_data={
                                **_course_outline(),
                                "personalization_summary": "针对大三软件工程背景，先完成需求拆解，再进入接口接入与最小闭环演示。",
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
                assert "AI 应用开发工程化服务编排与部署监控" in refresh_response.text
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
                    assert year_3_path.path_data["current_learning_course"]["course_node_id"] == "year_3_course_3"

        graph_module._graph = None

    def test_send_message_prompts_for_profile_details_on_generic_path_refresh_after_completed_tasks(self, tmp_path: Path) -> None:
        identifier = "completed-generic-path-followup@example.com"
        database_url = f"sqlite:///{tmp_path / 'chat-test.db'}"
        graph_module._graph = None

        class GuardSupervisorLlm:
            def bind_tools(self, _tools):
                return self

            async def ainvoke(self, _messages):
                raise AssertionError("完成任务后的泛化路径刷新应走 force_call 追问，不应调用 LLM")

        class WorkerPlaceholderLlm:
            pass

        with patch("app.orchestration.graph.get_supervisor_llm", return_value=GuardSupervisorLlm()), \
             patch("app.orchestration.graph.get_worker_llm", return_value=WorkerPlaceholderLlm()), \
             patch("app.orchestration.graph.get_thinking_worker_llm", return_value=WorkerPlaceholderLlm()):
            with chat_app(tmp_path) as client:
                token = _register_user(client, identifier, "genericpath123456")

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
                    profile_data = _basic_profile()
                    profile_data["confirmed_info"]["knowledge_foundation"] = "已具备软件工程基础，AI 应用开发方向可从入门到基础逐步补全"
                    session.add(
                        UserProfile(
                            user_uid=user.uid,
                            profile_data=profile_data,
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
                    session.add(
                        UserCourseKnowledgeOutline(
                            user_uid=user.uid,
                            course_id="year_3_course_1",
                            grade_year="year_3",
                            course_name="AI Agent 开发基础能力搭建",
                            outline_data={
                                **_course_outline(),
                                "personalization_summary": "针对大三软件工程背景，先完成需求拆解，再进入接口接入与最小闭环演示。",
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

                completed_response = client.post(
                    "/api/chat/message",
                    json={"session_id": session_id, "message": "我不想要《AI Agent 项目实战》了，现在帮我生成一门新课"},
                    headers=_auth_header(token),
                )

                assert completed_response.status_code == 200
                assert "当前所有任务已经完成。" in completed_response.text

                followup_response = client.post(
                    "/api/chat/message",
                    json={"session_id": session_id, "message": "更新学习路径"},
                    headers=_auth_header(token),
                )

                assert followup_response.status_code == 200
                assert "请先直接告诉我你想调整的具体信息" in followup_response.text
                assert "profile_agent" not in followup_response.text
                assert "learning_path_agent" not in followup_response.text

        graph_module._graph = None

    def test_send_message_prompts_for_profile_details_on_punctuated_generic_path_refresh_after_completed_tasks(self, tmp_path: Path) -> None:
        identifier = "completed-generic-path-followup-punctuated@example.com"
        database_url = f"sqlite:///{tmp_path / 'chat-test.db'}"
        graph_module._graph = None

        class GuardSupervisorLlm:
            def bind_tools(self, _tools):
                return self

            async def ainvoke(self, _messages):
                raise AssertionError("带标点的完成任务后泛化路径刷新应走 force_call 追问，不应调用 LLM")

        class WorkerPlaceholderLlm:
            pass

        with patch("app.orchestration.graph.get_supervisor_llm", return_value=GuardSupervisorLlm()), \
             patch("app.orchestration.graph.get_worker_llm", return_value=WorkerPlaceholderLlm()), \
             patch("app.orchestration.graph.get_thinking_worker_llm", return_value=WorkerPlaceholderLlm()):
            with chat_app(tmp_path) as client:
                token = _register_user(client, identifier, "genericpath123456")

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
                    profile_data = _basic_profile()
                    profile_data["confirmed_info"]["knowledge_foundation"] = "已具备软件工程基础，AI 应用开发方向可从入门到基础逐步补全"
                    session.add(
                        UserProfile(
                            user_uid=user.uid,
                            profile_data=profile_data,
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
                    session.add(
                        UserCourseKnowledgeOutline(
                            user_uid=user.uid,
                            course_id="year_3_course_1",
                            grade_year="year_3",
                            course_name="AI Agent 开发基础能力搭建",
                            outline_data={
                                **_course_outline(),
                                "personalization_summary": "针对大三软件工程背景，先完成需求拆解，再进入接口接入与最小闭环演示。",
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

                completed_response = client.post(
                    "/api/chat/message",
                    json={"session_id": session_id, "message": "我不想要《AI Agent 项目实战》了，现在帮我生成一门新课"},
                    headers=_auth_header(token),
                )

                assert completed_response.status_code == 200
                assert "当前所有任务已经完成。" in completed_response.text

                followup_response = client.post(
                    "/api/chat/message",
                    json={"session_id": session_id, "message": "更新学习路径。"},
                    headers=_auth_header(token),
                )

                assert followup_response.status_code == 200
                assert "请先直接告诉我你想调整的具体信息" in followup_response.text
                assert "profile_agent" not in followup_response.text
                assert "learning_path_agent" not in followup_response.text

        graph_module._graph = None

    def test_send_message_pauses_followup_when_user_says_no_need_after_completed_tasks(self, tmp_path: Path) -> None:
        identifier = "completed-pause-followup@example.com"
        database_url = f"sqlite:///{tmp_path / 'chat-test.db'}"
        graph_module._graph = None

        class GuardSupervisorLlm:
            def bind_tools(self, _tools):
                return self

            async def ainvoke(self, _messages):
                raise AssertionError("完成任务后的礼貌收尾应直接返回文本，不应调用 LLM")

        class WorkerPlaceholderLlm:
            pass

        with patch("app.orchestration.graph.get_supervisor_llm", return_value=GuardSupervisorLlm()), \
             patch("app.orchestration.graph.get_worker_llm", return_value=WorkerPlaceholderLlm()), \
             patch("app.orchestration.graph.get_thinking_worker_llm", return_value=WorkerPlaceholderLlm()):
            with chat_app(tmp_path) as client:
                token = _register_user(client, identifier, "pausefollow123456")

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

                followup_response = client.post(
                    "/api/chat/message",
                    json={"session_id": session_id, "message": "先不用了"},
                    headers=_auth_header(token),
                )

                assert followup_response.status_code == 200
                assert "好的，当前先不调整。" in followup_response.text
                assert "profile_agent" not in followup_response.text
                assert "learning_path_agent" not in followup_response.text

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
                    profile_data = _basic_profile()
                    profile_data["confirmed_info"]["knowledge_foundation"] = "已具备软件工程基础，AI 应用开发方向可从入门到基础逐步补全"
                    session.add(
                        UserProfile(
                            user_uid=user.uid,
                            profile_data=profile_data,
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
                    session.add(
                        UserCourseKnowledgeOutline(
                            user_uid=user.uid,
                            course_id="year_3_course_1",
                            grade_year="year_3",
                            course_name="AI Agent 开发基础能力搭建",
                            outline_data={
                                **_course_outline(),
                                "personalization_summary": "针对大三软件工程背景，先完成需求拆解，再进入接口接入与最小闭环演示。",
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
                assert "AI 应用开发工程化服务编排与部署监控" in refresh_response.text
                assert "profile_agent" in refresh_response.text
                assert "learning_path_agent" in refresh_response.text

                with Session(engine) as session:
                    user = session.exec(select(User).where(User.identifier == identifier)).one()
                    profile_row = session.get(UserProfile, user.uid)
                    assert profile_row is not None
                    assert profile_row.profile_data["confirmed_info"]["current_grade"] == "大三"
                    assert profile_row.profile_data["confirmed_info"]["major"] == "计算机科学"
                    assert (
                        profile_row.profile_data["confirmed_info"]["knowledge_foundation"]
                        == "已具备计算机科学基础，AI 应用开发方向可从入门到基础逐步补全"
                    )
                    assert profile_row.profile_data["confirmed_info"]["constraints"] == "周末集中"
                    assert session.get(UserCourseKnowledgeOutline, (user.uid, "year_3_course_1")) is None

                    year_3_path = session.exec(
                        select(UserYearLearningPath).where(
                            UserYearLearningPath.user_uid == user.uid,
                            UserYearLearningPath.grade_year == "year_3",
                        )
                    ).one()
                    assert year_3_path.path_data["learner_baseline"]["major"] == "计算机科学"
                    assert year_3_path.path_data["learner_baseline"]["constraints"] == ["周末集中"]
                    assert year_3_path.path_data["current_learning_course"]["course_node_id"] == "year_3_course_3"

                dashboard_response = client.get(
                    "/api/profile/dashboard",
                    headers=_auth_header(token),
                )
                assert dashboard_response.status_code == 200
                dashboard_body = dashboard_response.json()
                assert dashboard_body["profile"]["knowledgeFoundation"] == "已具备计算机科学基础，AI 应用开发方向可从入门到基础逐步补全"
                assert dashboard_body["todayLearning"]["currentCourseOutline"] is None

                branch_response = client.get(
                    "/api/branch/overview",
                    headers=_auth_header(token),
                )
                assert branch_response.status_code == 200
                branch_year_3 = branch_response.json()["years"]["year_3"]
                assert branch_year_3["has_outline_content"] is False
                assert branch_year_3["courses"][0]["has_outline"] is False

        graph_module._graph = None
