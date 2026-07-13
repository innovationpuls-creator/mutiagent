from __future__ import annotations

import asyncio
import json
from pathlib import Path

from langchain_core.messages import AIMessage
from sqlmodel import Session, SQLModel, create_engine

from app.database import set_engine
from app.models import Textbook, TextbookSectionContent, User
from app.orchestration.agents.course_knowledge import run_course_knowledge_agent
from app.orchestration.agents.learning_path import _bind_confirmed_course_sources
from app.orchestration.agents.learning_path_intake import (
    get_published_textbook_context_for_topic,
)
from app.schema_upgrades import run_schema_upgrades
from tests.postgres import postgresql_test_url


def _engine(tmp_path: Path):
    return create_engine(
        postgresql_test_url(tmp_path, "rag-knowledge-base-e2e"),
    )


def _published_textbook() -> Textbook:
    return Textbook(
        textbook_id="textbook-published-e2e",
        source_id="source-e2e",
        title="FastAPI 开发基础",
        original_title="FastAPI Basics",
        language="en",
        translated_language="zh",
        description="覆盖 API 设计与依赖注入",
        tags=["FastAPI", "后端"],
        download_url="https://example.test/fastapi.pdf",
        file_asset_url="https://example.test/fastapi.md",
        outline={
            "chapters": [
                {
                    "chapter_number": 1,
                    "title": "第一章 FastAPI 入门",
                    "sections": [
                        {"section_id": "1.1", "title": "1.1 路由设计"},
                        {"section_id": "1.2", "title": "1.2 依赖注入"},
                        {"section_id": "1.3", "title": "1.3 中间件"},
                    ],
                }
            ]
        },
        student_availability_status="published",
        outline_review_status="approved",
        ingestion_status="completed",
    )


def _draft_textbook() -> Textbook:
    return Textbook(
        textbook_id="textbook-draft-e2e",
        source_id="source-e2e",
        title="未发布 FastAPI 草稿",
        original_title="FastAPI Draft",
        language="en",
        translated_language="zh",
        description="草稿教材",
        tags=["FastAPI", "后端"],
        download_url="https://example.test/fastapi-draft.pdf",
        file_asset_url="https://example.test/fastapi-draft.md",
        outline={"chapters": []},
        student_availability_status="draft",
        outline_review_status="unreviewed",
        ingestion_status="completed",
    )


def _published_section(
    textbook_id: str, section_id: str, title: str
) -> TextbookSectionContent:
    return TextbookSectionContent(
        section_content_id=f"{textbook_id}-{section_id}",
        textbook_id=textbook_id,
        section_id=section_id,
        parent_section_id="1",
        order_index=1 if section_id == "1.1" else 2,
        title=title,
        original_title=title,
        content_zh=f"{title} 的详细正文。",
        content_char_count=20,
    )


def _state(textbook_id: str | None) -> dict:
    course = {
        "course_node_id": "year_3_course_1",
        "course_or_chapter_theme": "FastAPI 开发基础",
        "grade_id": "year_3",
        "course_goal": "掌握 FastAPI 基础能力",
        "time_arrangement": {
            "semester_scope": "上学期",
            "duration": "4 周",
            "pace_reason": "项目驱动",
        },
        "key_points": ["路由设计", "依赖注入"],
        "difficult_points": ["依赖注入"],
        "learning_sequence": ["路由设计", "依赖注入", "中间件"],
        "prerequisite_node_ids": [],
        "chapter_nodes": [],
        "core_knowledge_points": [],
        "knowledge_relations": [],
        "downstream_resource_direction_ids": [],
        "acceptance_criteria": ["完成一个可运行的 FastAPI 应用"],
    }
    if textbook_id is not None:
        course["source_textbook_id"] = textbook_id
        course["source_textbook_title"] = "FastAPI 开发基础"
        course["source_outline_section_ids"] = ["1.1", "1.2", "1.3"]

    return {
        "user_id": "user-1",
        "profile": {
            "type": "basic_profile",
            "summary_text": "大三软件工程，想学 FastAPI。",
            "confirmed_info": {
                "current_grade": "大三",
                "major": "软件工程",
                "learning_stage": "项目实践",
                "has_clear_goal": "是",
                "learning_method_preference": "项目驱动学习",
                "learning_pace_preference": "按周推进",
                "content_preference": ["文档"],
                "need_guidance": "需要",
                "knowledge_foundation": "有 Python 基础",
                "strengths": "能完成小型功能",
                "weaknesses": "接口设计经验不足",
                "experience": "做过课程项目",
                "short_term_goal": "学习 FastAPI",
                "long_term_goal": "形成后端开发能力",
                "weekly_available_time": "每周 8 小时",
                "constraints": "时间有限",
            },
        },
        "year_learning_paths": {
            "year_3": {
                "current_learning_course": {
                    "grade_id": "year_3",
                    "course_node_id": "year_3_course_1",
                },
                "grade_plans": {
                    "year_3": {"course_nodes": [course]},
                },
            }
        },
        "messages": [],
    }


def test_rag_knowledge_base_end_to_end_flow(tmp_path: Path) -> None:
    captured: dict[str, object] = {"queries": []}

    class RecordingLlm:
        pass

    class OutlineNamingChain:
        async def ainvoke(self, payload):
            captured["queries"].append(payload["query"])
            naming_payload = {
                "personalization_summary": "按 FastAPI 教材正文完成课程学习。",
                "section_texts": {
                    "1": {
                        "title": "FastAPI 核心能力",
                        "description": "建立路由、依赖注入与中间件的整体认识。",
                        "key_knowledge_points": ["路由设计", "依赖注入", "中间件"],
                    },
                    "1.1": {
                        "title": "路由设计",
                        "description": "掌握 FastAPI 路由的定义与组织方式。",
                        "key_knowledge_points": ["路由定义", "请求处理"],
                    },
                    "1.2": {
                        "title": "依赖注入",
                        "description": "理解依赖声明、解析和复用方式。",
                        "key_knowledge_points": ["依赖声明", "依赖复用"],
                    },
                    "1.3": {
                        "title": "中间件",
                        "description": "理解中间件在请求处理链路中的作用。",
                        "key_knowledge_points": ["请求链路", "横切处理"],
                    },
                },
            }
            return AIMessage(content=json.dumps(naming_payload, ensure_ascii=False))

    class OutlineNamingPrompt:
        def __or__(self, _other):
            return OutlineNamingChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return OutlineNamingPrompt()

    engine = _engine(tmp_path)
    set_engine(engine)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(_draft_textbook())
        textbook = _published_textbook()
        session.add(textbook)
        session.add(_published_section(textbook.textbook_id, "1.1", "1.1 路由设计"))
        session.add(_published_section(textbook.textbook_id, "1.2", "1.2 依赖注入"))
        session.add(_published_section(textbook.textbook_id, "1.3", "1.3 中间件"))
        session.commit()

    with Session(engine) as session:
        context = get_published_textbook_context_for_topic(session, "FastAPI")
    assert context["gap_id"] is None
    assert context["textbooks"][0]["textbook_id"] == "textbook-published-e2e"
    assert all(
        item["textbook_id"] != "textbook-draft-e2e" for item in context["textbooks"]
    )

    bound_path = _bind_confirmed_course_sources(
        {
            "grade_plans": {
                "year_3": {
                    "course_nodes": [
                        {
                            "course_node_id": "year_3_course_1",
                            "course_or_chapter_theme": "FastAPI 开发基础",
                        }
                    ]
                }
            }
        },
        "year_3",
        [
            {
                "title": "FastAPI 开发基础",
                "purpose": "学习 FastAPI",
                "source_textbook_id": "textbook-published-e2e",
                "source_textbook_title": "FastAPI 开发基础",
                "source_outline_section_ids": ["1.1", "1.2", "1.3"],
            }
        ],
    )
    course_node = bound_path["grade_plans"]["year_3"]["course_nodes"][0]
    assert course_node["source_textbook_id"] == "textbook-published-e2e"
    assert course_node["source_textbook_title"] == "FastAPI 开发基础"
    assert course_node["source_outline_section_ids"] == ["1.1", "1.2", "1.3"]

    import app.orchestration.agents.course_knowledge as course_knowledge_module

    original_factory = course_knowledge_module.ChatPromptTemplate
    course_knowledge_module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_course_knowledge_agent(_state("textbook-published-e2e"), RecordingLlm())
        )
    finally:
        course_knowledge_module.ChatPromptTemplate = original_factory

    assert len(captured["queries"]) == 1
    assert result["course_knowledge"]["course_id"] == "year_3_course_1"
    assert (
        result["course_knowledge"]["sections"][0]["source_textbook_id"]
        == "textbook-published-e2e"
    )
