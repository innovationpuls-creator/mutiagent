from __future__ import annotations

import asyncio
import json
from pathlib import Path

from langchain_core.messages import AIMessage
from sqlmodel import Session, SQLModel, create_engine

from app.database import set_engine
from app.models import Textbook, TextbookSectionContent, User
from app.orchestration.agents.course_knowledge import run_course_knowledge_agent
from app.schema_upgrades import run_schema_upgrades
from tests.postgres import postgresql_test_url


def _naming_payload_from_outline(outline: dict) -> dict:
    return {
        "personalization_summary": outline["personalization_summary"],
        "section_texts": {
            section["section_id"]: {
                "title": section["title"],
                "description": section["description"],
                "key_knowledge_points": section["key_knowledge_points"],
            }
            for section in outline["sections"]
        },
    }


def _engine(tmp_path: Path):
    return create_engine(
        postgresql_test_url(tmp_path, "course-knowledge-published-only"),
    )


def _state(textbook_id: str | None) -> dict:
    course = {
        "course_node_id": "year_3_course_1",
        "course_or_chapter_theme": "矩阵专题",
        "grade_id": "year_3",
        "course_goal": "掌握矩阵乘法",
        "time_arrangement": {
            "semester_scope": "上学期",
            "duration": "4 周",
            "pace_reason": "项目驱动",
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
    }
    if textbook_id is not None:
        course["source_textbook_id"] = textbook_id
        course["source_textbook_title"] = "矩阵教材"
        course["source_outline_section_ids"] = ["1.1"]

    return {
        "user_id": "user-1",
        "profile": {
            "type": "basic_profile",
            "summary_text": "大三软件工程，想学矩阵。",
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
                "weaknesses": "线性代数不熟",
                "experience": "做过课程项目",
                "short_term_goal": "学习矩阵",
                "long_term_goal": "形成 AI 工程基础",
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


def test_run_course_knowledge_agent_requires_published_textbook(
    tmp_path: Path,
) -> None:
    engine = _engine(tmp_path)
    set_engine(engine)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(
            Textbook(
                textbook_id="textbook-draft",
                source_id="source-1",
                title="矩阵教材",
                outline={"chapters": []},
                student_availability_status="draft",
                outline_review_status="approved",
                ingestion_status="completed",
            )
        )
        session.commit()

    result = asyncio.run(run_course_knowledge_agent(_state("textbook-draft"), object()))
    assert result == {"error": "教材未发布。", "hard_error": True}


def test_run_course_knowledge_agent_requires_textbook_binding(
    tmp_path: Path,
) -> None:
    engine = _engine(tmp_path)
    set_engine(engine)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.commit()

    class ExplodingLlm:
        async def ainvoke(self, *args, **kwargs):
            raise AssertionError("LLM should not be used without textbook binding")

    result = asyncio.run(run_course_knowledge_agent(_state(None), ExplodingLlm()))
    assert result == {"error": "课程缺少已发布教材绑定。", "hard_error": True}


def test_run_course_knowledge_agent_uses_llm_for_published_textbook(
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {"queries": []}
    engine = _engine(tmp_path)
    set_engine(engine)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        textbook = Textbook(
            textbook_id="textbook-published",
            source_id="source-1",
            title="矩阵教材",
            outline={
                "chapters": [
                    {
                        "chapter_number": 1,
                        "title": "第一章 矩阵基础",
                        "sections": [{"section_id": "1.1", "title": "1.1 矩阵乘法"}],
                    }
                ]
            },
            student_availability_status="published",
            outline_review_status="approved",
            ingestion_status="completed",
        )
        session.add(textbook)
        session.add(
            TextbookSectionContent(
                section_content_id="content-1",
                textbook_id="textbook-published",
                section_id="1.1",
                parent_section_id="1",
                order_index=1,
                title="1.1 矩阵乘法",
                content_zh="矩阵乘法是线性代数的核心主题。",
                content_char_count=15,
            )
        )
        session.commit()

    class RecordingLlm:
        pass

    class DesignedOutlineChain:
        async def ainvoke(self, payload):
            captured["queries"].append(payload["query"])
            outline = {
                "personalization_summary": "按矩阵教材正文设计完整两章教学大纲。",
                "sections": [
                    {
                        "section_id": "1",
                        "parent_section_id": None,
                        "depth": 1,
                        "title": "矩阵概念与运算边界",
                        "order_index": 1,
                        "description": "建立矩阵乘法的概念边界。",
                        "key_knowledge_points": ["矩阵乘法定义"],
                        "source_textbook_id": "textbook-published",
                        "source_textbook_title": "矩阵教材",
                        "source_section_ids": ["1.1"],
                        "source_section_titles": ["1.1 矩阵乘法"],
                        "source_content_chars": 15,
                    },
                    {
                        "section_id": "1.1",
                        "parent_section_id": "1",
                        "depth": 2,
                        "title": "行列匹配概念",
                        "order_index": 2,
                        "description": "理解矩阵乘法中的维度匹配。",
                        "key_knowledge_points": ["维度匹配"],
                        "source_textbook_id": "textbook-published",
                        "source_textbook_title": "矩阵教材",
                        "source_section_ids": ["1.1"],
                        "source_section_titles": ["1.1 矩阵乘法"],
                        "source_content_chars": 15,
                    },
                ],
                "learning_sequence": ["1"],
                "total_estimated_hours": "8 小时",
            }
            return AIMessage(
                content=json.dumps(
                    _naming_payload_from_outline(outline),
                    ensure_ascii=False,
                )
            )

    class DesignedOutlinePrompt:
        def __or__(self, _other):
            return DesignedOutlineChain()

    module = __import__(
        "app.orchestration.agents.course_knowledge", fromlist=["ChatPromptTemplate"]
    )
    original_factory = module.ChatPromptTemplate

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return DesignedOutlinePrompt()

    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_course_knowledge_agent(_state("textbook-published"), RecordingLlm())
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert len(captured["queries"]) == 1
    assert "source_outline_sections" not in str(captured["queries"][0])
    assert "1.1" in str(captured["queries"][0])
    assert result["course_knowledge"]["course_id"] == "year_3_course_1"
    assert (
        result["course_knowledge"]["sections"][0]["source_textbook_id"]
        == "textbook-published"
    )
