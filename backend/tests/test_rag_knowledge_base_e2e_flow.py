from __future__ import annotations

import asyncio
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from app.database import set_engine
from app.models import Textbook, TextbookSectionContent, User
from app.orchestration.agents.course_knowledge import run_course_knowledge_agent
from app.orchestration.agents.learning_path import _bind_confirmed_course_sources
from app.orchestration.agents.learning_path_intake import (
    get_published_textbook_context_for_topic,
)
from app.schema_upgrades import run_schema_upgrades


def _engine(tmp_path: Path):
    return create_engine(
        f"sqlite:///{tmp_path / 'rag-knowledge-base-e2e.db'}",
        connect_args={"check_same_thread": False},
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

    context = get_published_textbook_context_for_topic(Session(engine), "FastAPI")
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

    result = asyncio.run(
        run_course_knowledge_agent(_state("textbook-published-e2e"), object())
    )
    assert result["course_knowledge"]["course_id"] == "year_3_course_1"
    assert (
        result["course_knowledge"]["sections"][0]["source_textbook_id"]
        == "textbook-published-e2e"
    )
