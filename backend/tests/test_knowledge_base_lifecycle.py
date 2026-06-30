from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from sqlmodel import Session, SQLModel, create_engine

from app.database import build_engine, init_db, set_engine
from app.main import create_app
from app.models import (
    KnowledgeBaseIngestionJob,
    KnowledgeSource,
    Textbook,
    TextbookSectionContent,
    User,
    UserCourseKnowledgeOutline,
    UserYearLearningPath,
)
from app.orchestration.agents.course_knowledge import run_course_knowledge_agent
from app.orchestration.agents.course_resources.markdown import (
    run_section_markdown_agent,
)
from app.schema_upgrades import run_schema_upgrades
from app.services.knowledge_base_service import (
    create_knowledge_source,
    get_published_textbook_context_for_topic,
    publish_textbook,
    upsert_structured_textbook,
)
from tests.postgres import postgresql_test_url


def _source(source_id: str = "source-lifecycle") -> KnowledgeSource:
    return KnowledgeSource(
        source_id=source_id,
        name="生命周期来源",
        base_url="https://example.test/source",
        status="enabled",
        source_kind="open_textbook",
        download_requirement="公开下载",
        ai_search_requirement="允许搜索",
        download_status="verified",
        parse_status="supported",
        license_review_status="approved",
        human_review_status="reviewed",
    )


def _textbook(textbook_id: str = "textbook-lifecycle") -> Textbook:
    return Textbook(
        textbook_id=textbook_id,
        source_id="source-lifecycle",
        title="矩阵专题",
        original_title="Matrix Topic",
        language="en",
        translated_language="zh",
        description="覆盖矩阵乘法",
        tags=["矩阵"],
        download_url="https://example.test/book.pdf",
        file_asset_url="https://example.test/book.md",
        outline={"sections": [{"section_id": "1.1", "title": "矩阵乘法"}]},
        ingestion_status="completed",
        outline_review_status="approved",
        student_availability_status="draft",
    )


def _section(textbook_id: str = "textbook-lifecycle") -> TextbookSectionContent:
    return TextbookSectionContent(
        section_content_id=f"section-{textbook_id}-1",
        textbook_id=textbook_id,
        section_id="1.1",
        parent_section_id=None,
        order_index=1,
        title="矩阵乘法",
        original_title="Matrix Multiplication",
        content_zh="矩阵乘法中文正文。",
        content_char_count=0,
    )


def _knowledge_engine(tmp_path: Path):
    return create_engine(
        postgresql_test_url(tmp_path, "knowledge-base-lifecycle"),
    )


def _publish_textbook(
    session: Session, textbook_id: str = "textbook-lifecycle"
) -> Textbook:
    create_knowledge_source(session, _source())
    upsert_structured_textbook(session, _textbook(textbook_id), [_section(textbook_id)])
    return publish_textbook(session, textbook_id)


def _profile() -> dict:
    return {
        "type": "basic_profile",
        "summary_text": "【基础学习画像总结】大三软件工程，目标是学习矩阵。",
        "confirmed_info": {
            "current_grade": "大三",
            "major": "软件工程",
            "learning_stage": "项目实践",
            "has_clear_goal": "是",
            "learning_method_preference": "项目驱动学习",
            "learning_pace_preference": "按周推进",
            "content_preference": ["文档"],
            "need_guidance": "需要轻量提醒",
            "knowledge_foundation": "有 Python 基础",
            "strengths": "能完成小型功能",
            "weaknesses": "线性代数不熟",
            "experience": "做过课程项目",
            "short_term_goal": "学习矩阵",
            "long_term_goal": "形成 AI 工程基础",
            "weekly_available_time": "每周 8 小时",
            "constraints": "时间有限",
        },
    }


def _course_node(textbook_id: str = "textbook-lifecycle") -> dict:
    return {
        "course_node_id": "year_3_course_1",
        "course_or_chapter_theme": "矩阵专题",
        "grade_id": "year_3",
        "course_goal": "掌握矩阵乘法",
        "time_arrangement": {
            "semester_scope": "上学期",
            "duration": "4 周",
            "pace_reason": "按周推进",
        },
        "key_points": ["矩阵乘法"],
        "difficult_points": ["维度匹配"],
        "learning_sequence": ["矩阵乘法"],
        "prerequisite_node_ids": [],
        "chapter_nodes": [],
        "core_knowledge_points": [],
        "knowledge_relations": [],
        "downstream_resource_direction_ids": [],
        "acceptance_criteria": ["能完成矩阵乘法练习"],
        "source_textbook_id": textbook_id,
        "source_textbook_title": "矩阵专题",
        "source_outline_section_ids": ["1.1"],
    }


def _year_paths(textbook_id: str = "textbook-lifecycle") -> dict:
    return {
        "year_3": {
            "current_learning_course": {
                "grade_id": "year_3",
                "course_node_id": "year_3_course_1",
            },
            "grade_plans": {
                "year_3": {
                    "course_nodes": [_course_node(textbook_id)],
                }
            },
        }
    }


def _outline(textbook_id: str = "textbook-lifecycle") -> dict:
    return {
        "course_id": "year_3_course_1",
        "course_name": "矩阵专题",
        "grade_year": "year_3",
        "personalization_summary": "按矩阵专题推进。",
        "sections": [
            {
                "section_id": "1",
                "parent_section_id": None,
                "depth": 1,
                "title": "第一章：矩阵乘法",
                "order_index": 1,
                "description": "学习矩阵乘法。",
                "key_knowledge_points": ["矩阵乘法"],
                "source_textbook_id": textbook_id,
                "source_textbook_title": "矩阵专题",
                "source_section_ids": ["1.1"],
                "source_section_titles": ["矩阵乘法"],
                "source_content_chars": 1200,
            },
            {
                "section_id": "1.1",
                "parent_section_id": "1",
                "depth": 2,
                "title": "学习目标",
                "order_index": 2,
                "description": "明确目标。",
                "key_knowledge_points": ["矩阵乘法"],
                "source_textbook_id": textbook_id,
                "source_textbook_title": "矩阵专题",
                "source_section_ids": ["1.1"],
                "source_section_titles": ["矩阵乘法"],
                "source_content_chars": 1200,
            },
        ],
        "learning_sequence": ["第一章：矩阵乘法"],
        "total_estimated_hours": "4 小时",
        "section_composed_markdowns": {
            "1.1": {
                "section_id": "1.1",
                "parent_section_id": "1",
                "title": "学习目标",
                "markdown": "# 学习目标\n\n已经生成的 Markdown。",
                "blocks": [
                    {
                        "type": "markdown",
                        "markdown": "# 学习目标\n\n已经生成的 Markdown。",
                    }
                ],
                "generated_at": "2026-06-06T00:00:00Z",
            }
        },
    }


def test_unpublished_textbook_is_removed_from_new_recommendations(
    tmp_path: Path,
) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        textbook = _publish_textbook(session)
        textbook.student_availability_status = "unpublished"
        session.add(textbook)
        session.commit()

        context = get_published_textbook_context_for_topic(session, "矩阵")

    assert context["textbooks"] == []
    assert context["gap_id"] is not None


def test_published_textbook_keeps_source_trace_after_source_is_disabled(
    tmp_path: Path,
) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        textbook = _publish_textbook(session)
        source = session.get(KnowledgeSource, textbook.source_id)
        assert source is not None
        source.status = "disabled"
        session.add(source)
        session.commit()

        context = get_published_textbook_context_for_topic(session, "矩阵")
        stored_textbook = session.get(Textbook, textbook.textbook_id)

    assert stored_textbook is not None
    assert stored_textbook.student_availability_status == "published"
    assert stored_textbook.source_id == "source-lifecycle"
    assert context["textbooks"] == [
        {
            "textbook_id": "textbook-lifecycle",
            "title": "矩阵专题",
            "source_id": "source-lifecycle",
            "tags": ["矩阵"],
            "description": "覆盖矩阵乘法",
            "outline_summary": [{"section_id": "1.1", "title": "矩阵乘法"}],
        }
    ]


def test_publish_textbook_sets_published_state_and_timestamp(tmp_path: Path) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        textbook = _publish_textbook(session)

    assert textbook.student_availability_status == "published"
    assert textbook.published_at is not None
    assert textbook.unpublished_at is None
    assert textbook.archived_at is None


def test_unpublish_textbook_route_sets_unpublished_state_and_timestamp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ADMIN_USERNAME", "管理员")
    monkeypatch.setenv("ADMIN_IDENTIFIER", "admin-lifecycle@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-password-123")
    database_url = postgresql_test_url(tmp_path, "knowledge-base-unpublish")
    client = TestClient(create_app(database_url=database_url))

    login_response = client.post(
        "/api/auth/login",
        json={
            "account": "admin-lifecycle@example.com",
            "password": "admin-password-123",
        },
    )
    assert login_response.status_code == 200
    headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

    with Session(build_engine(database_url)) as session:
        _publish_textbook(session)

    response = client.post(
        "/api/admin/knowledge-base/textbooks/textbook-lifecycle/unpublish",
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["student_availability_status"] == "unpublished"
    assert body["unpublished_at"] is not None
    assert body["published_at"] is not None


def test_course_outline_generation_blocks_unpublished_source_textbook(
    tmp_path: Path,
) -> None:
    engine = build_engine(
        postgresql_test_url(tmp_path, "course-outline-unpublished")
    )
    set_engine(engine)
    init_db(engine)

    with Session(engine) as session:
        textbook = _publish_textbook(session)
        textbook.student_availability_status = "unpublished"
        session.add(textbook)
        session.add(
            User(uid="user-1", username="学生", identifier="student@example.com")
        )
        session.commit()

    class RecordingLlm:
        pass

    class OutlineChain:
        async def ainvoke(self, _payload):
            return type(
                "Output",
                (),
                {"content": json.dumps(_outline(), ensure_ascii=False)},
            )()

    class OutlinePrompt:
        def __or__(self, _other):
            return OutlineChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return OutlinePrompt()

    import app.orchestration.agents.course_knowledge as module

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_course_knowledge_agent(
                {
                    "user_id": "user-1",
                    "profile": _profile(),
                    "year_learning_paths": _year_paths(),
                    "messages": [
                        AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "name": "course_knowledge_agent",
                                    "args": {"course_id": "year_3_course_1"},
                                    "id": "force-course-knowledge",
                                }
                            ],
                        )
                    ],
                },
                RecordingLlm(),
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert result == {"error": "教材未发布。", "hard_error": True}
    with Session(engine) as session:
        row = session.get(UserCourseKnowledgeOutline, ("user-1", "year_3_course_1"))
    assert row is None


def test_leaf_keeps_existing_outline_and_markdown_after_unpublish(
    tmp_path: Path,
) -> None:
    database_url = postgresql_test_url(tmp_path, "leaf-lifecycle")
    client = TestClient(create_app(database_url=database_url))
    response = client.post(
        "/api/auth/register",
        json={
            "username": "叶茂学生",
            "identifier": "leaf-lifecycle@example.com",
            "school": "测试大学",
            "major": "软件工程",
            "class_name": "三班",
            "password": "test-password-123",
            "confirm_password": "test-password-123",
        },
    )
    assert response.status_code == 201
    token = response.json()["access_token"]
    user_uid = response.json()["user"]["uid"]
    engine = create_engine(database_url)
    with Session(engine) as session:
        _publish_textbook(session)
        textbook = session.get(Textbook, "textbook-lifecycle")
        assert textbook is not None
        textbook.student_availability_status = "unpublished"
        session.add(textbook)
        session.add(
            UserYearLearningPath(
                user_uid=user_uid,
                grade_year="year_3",
                learning_topic="矩阵专题",
                path_data={
                    "current_learning_course": {
                        "grade_id": "year_3",
                        "course_node_id": "year_3_course_1",
                        "progress_state": "in_progress",
                    },
                    "grade_plans": {
                        "year_3": {
                            "course_nodes": [_course_node()],
                        }
                    },
                },
            )
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid=user_uid,
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="矩阵专题",
                outline_data=_outline(),
            )
        )
        session.commit()

    leaf_response = client.get(
        "/api/leaf/courses/year_3_course_1",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert leaf_response.status_code == 200
    body = leaf_response.json()
    assert body["outline"]["course_id"] == "year_3_course_1"
    assert body["section_composed_markdowns"]["1.1"]["markdown"].startswith(
        "# 学习目标"
    )


def test_markdown_regeneration_blocks_unpublished_source_textbook(
    tmp_path: Path,
) -> None:
    engine = build_engine(postgresql_test_url(tmp_path, "markdown-unpublished"))
    set_engine(engine)
    init_db(engine)

    with Session(engine) as session:
        textbook = _publish_textbook(session)
        textbook.student_availability_status = "unpublished"
        session.add(textbook)
        session.add(
            User(uid="user-1", username="学生", identifier="student@example.com")
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="矩阵专题",
                outline_data=_outline(),
            )
        )
        session.commit()

    class RecordingLlm:
        pass

    class MarkdownChain:
        async def ainvoke(self, _payload):
            return "正文"

    class MarkdownPrompt:
        def __or__(self, _other):
            return MarkdownChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return MarkdownPrompt()

    import app.orchestration.agents.course_resources as module

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_section_markdown_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": _outline(),
                    "profile": _profile(),
                    "year_learning_paths": _year_paths(),
                    "messages": [],
                },
                RecordingLlm(),
                {
                    "course_id": "year_3_course_1",
                    "section_id": "1",
                    "scope": "chapter_sections",
                },
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert result == {"error": "教材未发布。", "hard_error": True}


def test_delete_archives_published_and_unpublished_but_removes_unbound_draft(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ADMIN_USERNAME", "管理员")
    monkeypatch.setenv("ADMIN_IDENTIFIER", "admin-lifecycle@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-password-123")
    client = TestClient(
        create_app(database_url=postgresql_test_url(tmp_path, "knowledge-base-api"))
    )
    login_response = client.post(
        "/api/auth/login",
        json={
            "account": "admin-lifecycle@example.com",
            "password": "admin-password-123",
        },
    )
    assert login_response.status_code == 200
    headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

    with Session(
        build_engine(postgresql_test_url(tmp_path, "knowledge-base-api"))
    ) as session:
        create_knowledge_source(session, _source())
        upsert_structured_textbook(
            session,
            _textbook("textbook-draft-delete"),
            [_section("textbook-draft-delete")],
        )
        upsert_structured_textbook(
            session,
            _textbook("textbook-published-delete"),
            [_section("textbook-published-delete")],
        )
        publish_textbook(session, "textbook-published-delete")
        upsert_structured_textbook(
            session,
            _textbook("textbook-unpublished-delete"),
            [_section("textbook-unpublished-delete")],
        )
        publish_textbook(session, "textbook-unpublished-delete")
        unpublished = session.get(Textbook, "textbook-unpublished-delete")
        assert unpublished is not None
        unpublished.student_availability_status = "unpublished"
        session.add(unpublished)
        session.add(
            KnowledgeBaseIngestionJob(
                job_id="job-draft-delete",
                textbook_id="textbook-draft-delete",
                job_type="agent_organize",
                status="queued",
            )
        )
        session.commit()

    draft_response = client.delete(
        "/api/admin/knowledge-base/textbooks/textbook-draft-delete",
        headers=headers,
    )
    published_response = client.delete(
        "/api/admin/knowledge-base/textbooks/textbook-published-delete",
        headers=headers,
    )
    unpublished_response = client.delete(
        "/api/admin/knowledge-base/textbooks/textbook-unpublished-delete",
        headers=headers,
    )

    assert draft_response.status_code == 204
    assert published_response.status_code == 204
    assert unpublished_response.status_code == 204
    with Session(
        build_engine(postgresql_test_url(tmp_path, "knowledge-base-api"))
    ) as session:
        assert session.get(Textbook, "textbook-draft-delete") is None
        published = session.get(Textbook, "textbook-published-delete")
        assert published is not None
        assert published.student_availability_status == "archived"
        unpublished = session.get(Textbook, "textbook-unpublished-delete")
        assert unpublished is not None
        assert unpublished.student_availability_status == "archived"
