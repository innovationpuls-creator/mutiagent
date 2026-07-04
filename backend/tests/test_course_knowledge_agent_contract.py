"""Contract tests for the course knowledge agent."""

# ruff: noqa: E501

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from sqlmodel import Session

from app.database import build_engine, init_db, set_engine
from app.models import User, UserCourseKnowledgeOutline
from app.orchestration.agents.course_knowledge import (
    ALL_CURRENT_GRADE_COURSES_ID,
    COURSE_KNOWLEDGE_RETRY_ERROR,
    COURSE_OUTLINE_NAMING_SYSTEM_PROMPT,
    _apply_outline_prompt_budget,
    _build_analysis_input,
    _build_year_analysis_input,
    _fill_course_source_binding_from_textbook,
    _normalize_generated_course_outline,
    _normalize_generated_sections,
    _select_course_for_outline,
    _source_section_contexts_for_courses,
    run_course_knowledge_agent,
)
from app.orchestration.agents.models import (
    SectionItem,
)
from app.orchestration.agents.prompts import COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT
from app.services.course_knowledge_service import upsert_user_course_knowledge_outline
from tests.fixtures.knowledge_base import (
    enabled_source,
    published_textbook,
    section,
)
from tests.postgres import postgresql_test_url

SOURCE_TEXTBOOK_ID = "textbook-ai-web"
SOURCE_TEXTBOOK_TITLE = "AI 应用开发项目教程"
DEFAULT_SOURCE_SECTION_IDS = [
    "1",
    "1.1",
    "1.2",
    "1.3",
    "2",
    "2.1",
    "2.2",
    "2.3",
]


def test_outline_prompt_budget_preserves_source_binding_markers() -> None:
    course = {
        "source_textbook_id": SOURCE_TEXTBOOK_ID,
        "source_outline_section_ids": ["1.1", "2.3"],
    }

    query = _apply_outline_prompt_budget("A" * 30000, [course])

    assert "prompt_budget_applied=true" in query
    assert SOURCE_TEXTBOOK_ID in query
    assert "1.1" in query
    assert "2.3" in query


def _section_source_binding(section_id: str, title: str) -> dict:
    return {
        "source_textbook_id": SOURCE_TEXTBOOK_ID,
        "source_textbook_title": SOURCE_TEXTBOOK_TITLE,
        "source_section_ids": [section_id],
        "source_section_titles": [title],
        "source_content_chars": 1200,
    }


def _with_section_sources(outline: dict) -> dict:
    return {
        **outline,
        "sections": [
            {
                **section,
                **_section_source_binding(section["section_id"], section["title"]),
            }
            for section in outline["sections"]
        ],
    }


def _complete_profile(
    summary_text: str = "【基础学习画像总结】大三软件工程，当前以AI 应用开发为主线。",
) -> dict:
    return {
        "type": "basic_profile",
        "summary_text": summary_text,
        "confirmed_info": {
            "current_grade": "大三",
            "major": "软件工程",
            "learning_stage": "项目实践",
            "has_clear_goal": "是",
            "learning_method_preference": "项目驱动学习",
            "learning_pace_preference": "按项目里程碑推进",
            "content_preference": ["代码实践", "项目案例"],
            "need_guidance": "需要轻量提醒",
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


def _course_outline_target(*, learning_sequence: list[str] | None = None) -> dict:
    return {
        "course_node_id": "year_3_course_1",
        "course_or_chapter_theme": "AI 应用开发",
        "grade_id": "year_3",
        "course_goal": "完成 AI 应用开发基础能力搭建",
        "time_arrangement": {
            "semester_scope": "上学期",
            "duration": "6 周",
            "pace_reason": "围绕平时学习安排",
        },
        "key_points": ["Prompt 设计", "前后端联调"],
        "difficult_points": ["错误处理与重试"],
        "learning_sequence": ["需求拆解", "接口接入", "最小闭环演示"]
        if learning_sequence is None
        else learning_sequence,
        "prerequisite_node_ids": [],
        "chapter_nodes": [],
        "core_knowledge_points": [],
        "knowledge_relations": [],
        "downstream_resource_direction_ids": [],
        "acceptance_criteria": ["完成一个可运行的 AI 功能模块并接入 Web 应用"],
        "source_textbook_id": SOURCE_TEXTBOOK_ID,
        "source_textbook_title": SOURCE_TEXTBOOK_TITLE,
        "source_outline_section_ids": DEFAULT_SOURCE_SECTION_IDS,
    }


def _course_with_source_sections(section_ids: list[str] | None = None) -> dict:
    return {
        **_course_outline_target(),
        "source_textbook_id": SOURCE_TEXTBOOK_ID,
        "source_textbook_title": SOURCE_TEXTBOOK_TITLE,
        "source_outline_section_ids": section_ids or ["1.1", "1.2", "1.3", "1.4"],
    }


def _source_bound_section(
    *,
    section_id: str,
    parent_section_id: str | None,
    depth: int,
    title: str,
    order_index: int,
    source_section_ids: list[str],
    source_content_chars: int = 1200,
) -> dict:
    return {
        "section_id": section_id,
        "parent_section_id": parent_section_id,
        "depth": depth,
        "title": title,
        "order_index": order_index,
        "description": f"{title}说明。",
        "key_knowledge_points": [f"{title}知识点"],
        "source_textbook_id": SOURCE_TEXTBOOK_ID,
        "source_textbook_title": SOURCE_TEXTBOOK_TITLE,
        "source_section_ids": source_section_ids,
        "source_section_titles": [
            f"模型给出的{source_id}" for source_id in source_section_ids
        ],
        "source_content_chars": source_content_chars,
    }


def _raw_outline_with_source_groups(
    first_child_source_ids: list[str],
    *,
    first_child_chars: int = 1200,
) -> dict:
    return {
        "personalization_summary": "按教材真实正文长度安排章节。",
        "sections": [
            _source_bound_section(
                section_id="1",
                parent_section_id=None,
                depth=1,
                title="教材主线",
                order_index=1,
                source_section_ids=["1.1"],
            ),
            _source_bound_section(
                section_id="1.1",
                parent_section_id="1",
                depth=2,
                title="核心概念",
                order_index=2,
                source_section_ids=first_child_source_ids,
                source_content_chars=first_child_chars,
            ),
            _source_bound_section(
                section_id="1.2",
                parent_section_id="1",
                depth=2,
                title="实践步骤",
                order_index=3,
                source_section_ids=["1.3"],
            ),
            _source_bound_section(
                section_id="1.3",
                parent_section_id="1",
                depth=2,
                title="验收复盘",
                order_index=4,
                source_section_ids=["1.4"],
            ),
            _source_bound_section(
                section_id="2",
                parent_section_id=None,
                depth=1,
                title="进阶实践",
                order_index=5,
                source_section_ids=["1.4"],
            ),
            _source_bound_section(
                section_id="2.1",
                parent_section_id="2",
                depth=2,
                title="实践准备",
                order_index=6,
                source_section_ids=["1.4"],
            ),
            _source_bound_section(
                section_id="2.2",
                parent_section_id="2",
                depth=2,
                title="过程演练",
                order_index=7,
                source_section_ids=["1.4"],
            ),
            _source_bound_section(
                section_id="2.3",
                parent_section_id="2",
                depth=2,
                title="结果检查",
                order_index=8,
                source_section_ids=["1.4"],
            ),
        ],
        "learning_sequence": ["1"],
        "total_estimated_hours": "12 小时",
    }


def _two_chapter_outline_with_source_ids(
    source_ids: list[str],
    *,
    personalization_summary: str = "按教材正文重新设计为完整教学大纲。",
) -> dict:
    first_source = source_ids[0]
    second_source = source_ids[1] if len(source_ids) > 1 else source_ids[0]

    def section(
        section_id: str,
        parent_section_id: str | None,
        depth: int,
        title: str,
        order_index: int,
        source_section_id: str,
    ) -> dict:
        return {
            "section_id": section_id,
            "parent_section_id": parent_section_id,
            "depth": depth,
            "title": title,
            "order_index": order_index,
            "description": f"{title}说明。",
            "key_knowledge_points": [f"{title}知识点"],
            "source_textbook_id": SOURCE_TEXTBOOK_ID,
            "source_textbook_title": SOURCE_TEXTBOOK_TITLE,
            "source_section_ids": [source_section_id],
            "source_section_titles": [f"教材小节 {source_section_id}"],
            "source_content_chars": 1200,
        }

    return {
        "personalization_summary": personalization_summary,
        "sections": [
            section("1", None, 1, "概念定义与学习边界", 1, first_source),
            section("1.1", "1", 2, "核心概念辨析", 2, first_source),
            section("1.2", "1", 2, "使用场景拆解", 3, first_source),
            section("1.3", "1", 2, "常见误区校正", 4, first_source),
            section("2", None, 1, "实践流程与验收方法", 5, second_source),
            section("2.1", "2", 2, "环境准备步骤", 6, second_source),
            section("2.2", "2", 2, "操作流程演练", 7, second_source),
            section("2.3", "2", 2, "结果检查标准", 8, second_source),
        ],
        "learning_sequence": ["1", "2"],
        "total_estimated_hours": "12 小时",
    }


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


def _seed_published_textbook_sections(
    contents_by_section_id: dict[str, str],
    tmp_path: Path,
):
    engine = build_engine(postgresql_test_url(tmp_path, "course-source-sections"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(enabled_source())
        row = published_textbook(
            textbook_id=SOURCE_TEXTBOOK_ID,
            title=SOURCE_TEXTBOOK_TITLE,
        )
        row.outline = {
            "sections": [
                {"section_id": section_id, "title": f"教材小节 {section_id}"}
                for section_id in contents_by_section_id
            ]
        }
        session.add(row)
        for index, (section_id, content_zh) in enumerate(
            contents_by_section_id.items(),
            start=1,
        ):
            session.add(
                section(
                    textbook_id=SOURCE_TEXTBOOK_ID,
                    section_content_id=f"section-{section_id.replace('.', '-')}",
                    section_id=section_id,
                    title=f"教材小节 {section_id}",
                    content_zh=content_zh,
                    order_index=index,
                )
            )
        session.commit()
    return engine


def _seed_published_textbook_sections_with_parents(
    rows: list[dict[str, str]],
    tmp_path: Path,
    schema_suffix: str,
):
    engine = build_engine(postgresql_test_url(tmp_path, schema_suffix))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(enabled_source())
        row = published_textbook(
            textbook_id=SOURCE_TEXTBOOK_ID,
            title=SOURCE_TEXTBOOK_TITLE,
        )
        row.outline = {
            "sections": [
                {"section_id": item["section_id"], "title": item["title"]}
                for item in rows
            ]
        }
        session.add(row)
        for index, item in enumerate(rows, start=1):
            session.add(
                section(
                    textbook_id=SOURCE_TEXTBOOK_ID,
                    section_content_id=f"section-{item['section_id'].replace('.', '-')}",
                    section_id=item["section_id"],
                    parent_section_id=item.get("parent_section_id"),
                    title=item["title"],
                    content_zh=item["content_zh"],
                    order_index=index,
                )
            )
        session.commit()
    return engine


def _add_default_source_material(session: Session) -> None:
    session.add(enabled_source())
    row = published_textbook(
        textbook_id=SOURCE_TEXTBOOK_ID,
        title=SOURCE_TEXTBOOK_TITLE,
    )
    row.outline = {}
    session.add(row)
    for index, section_id in enumerate(DEFAULT_SOURCE_SECTION_IDS, start=1):
        session.add(
            section(
                textbook_id=SOURCE_TEXTBOOK_ID,
                section_content_id=f"default-section-{section_id.replace('.', '-')}",
                section_id=section_id,
                title=f"教材小节 {section_id}",
                content_zh=f"教材小节 {section_id} 的真实正文。",
                order_index=index,
            )
        )


def _course_tool_messages(course_id: str) -> list[AIMessage]:
    return [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "course_knowledge_agent",
                    "args": {"course_id": course_id},
                    "id": "force_course_knowledge_agent",
                }
            ],
        )
    ]


def test_build_analysis_input_requires_course_source_binding() -> None:
    course = _course_outline_target()
    course.pop("source_textbook_id")

    with pytest.raises(ValueError, match="course source binding is incomplete"):
        _build_analysis_input(course, _complete_profile(), None)


def test_build_year_analysis_input_requires_each_course_source_binding() -> None:
    course = _course_outline_target()
    course["source_outline_section_ids"] = []

    with pytest.raises(ValueError, match="course source binding is incomplete"):
        _build_year_analysis_input(
            "year_3",
            [course],
            "year_3_course_1",
            _complete_profile(),
        )


def _json_block_after_label(text: str, label: str) -> object:
    match = re.search(
        rf"{re.escape(label)}：(?P<body>.*?)\n(?:同年级课程顺序|学习者输入|$)",
        text,
        re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group("body"))


def test_select_course_for_outline_uses_current_learning_course() -> None:
    path = {
        "current_learning_course": {
            "grade_id": "year_3",
            "course_node_id": "year_3_course_1",
        },
        "grade_plans": {
            "year_3": {
                "course_nodes": [
                    {
                        "course_node_id": "year_3_course_1",
                        "course_or_chapter_theme": "AI 应用开发",
                    },
                ],
            },
        },
    }

    course = _select_course_for_outline({"year_3": path}, "")

    assert course["course_node_id"] == "year_3_course_1"
    assert course["course_or_chapter_theme"] == "AI 应用开发"


def test_select_course_for_outline_requires_path() -> None:
    with pytest.raises(ValueError, match="学习路径不存在"):
        _select_course_for_outline(None, "")


def test_select_course_for_outline_rejects_unknown_explicit_course_id() -> None:
    path = {
        "current_learning_course": {
            "grade_id": "year_3",
            "course_node_id": "year_3_course_1",
        },
        "grade_plans": {
            "year_3": {
                "course_nodes": [
                    {
                        "course_node_id": "year_3_course_1",
                        "course_or_chapter_theme": "AI 应用开发",
                    },
                ],
            },
        },
    }

    with pytest.raises(ValueError, match="指定课程无法定位"):
        _select_course_for_outline({"year_3": path}, "year_3_course_missing")


def test_select_course_for_outline_accepts_exact_course_name_as_explicit_input() -> (
    None
):
    path = {
        "current_learning_course": {
            "grade_id": "year_3",
            "course_node_id": "year_3_course_1",
        },
        "grade_plans": {
            "year_3": {
                "course_nodes": [
                    {
                        "course_node_id": "year_3_course_1",
                        "course_or_chapter_theme": "构建本地知识库问答系统 (RAG基础)",
                    },
                    {
                        "course_node_id": "year_3_course_2",
                        "course_or_chapter_theme": "智能代理与工作流编排 (Agent & Workflow)",
                    },
                ],
            },
        },
    }

    course = _select_course_for_outline(
        {"year_3": path},
        "构建本地知识库问答系统 (RAG基础)",
    )

    assert course["course_node_id"] == "year_3_course_1"
    assert course["course_or_chapter_theme"] == "构建本地知识库问答系统 (RAG基础)"


def test_select_course_for_outline_prefers_latest_grade_year_when_no_explicit_course_id() -> (
    None
):
    year_3_path = {
        "current_learning_course": {
            "grade_id": "year_3",
            "course_node_id": "year_3_course_1",
        },
        "grade_plans": {
            "year_3": {
                "course_nodes": [
                    {
                        "course_node_id": "year_3_course_1",
                        "course_or_chapter_theme": "旧课程",
                    },
                ],
            },
        },
    }
    year_4_path = {
        "current_learning_course": {
            "grade_id": "year_4",
            "course_node_id": "year_4_course_1",
        },
        "grade_plans": {
            "year_4": {
                "course_nodes": [
                    {
                        "course_node_id": "year_4_course_1",
                        "course_or_chapter_theme": "最新课程",
                    },
                ],
            },
        },
    }

    course = _select_course_for_outline(
        {"year_3": year_3_path, "year_4": year_4_path},
        "",
        "year_4",
    )

    assert course["course_node_id"] == "year_4_course_1"
    assert course["course_or_chapter_theme"] == "最新课程"


def test_course_knowledge_prompt_mentions_json_output() -> None:
    assert "json" in COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT.lower()
    assert "先分析" in COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT
    assert "1.1" in COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT
    assert "key_knowledge_points" in COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT
    assert "第一章" in COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT
    assert "learning_sequence" in COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT
    assert "personalization_summary" in COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT


def test_course_knowledge_schema_requires_section_key_knowledge_points() -> None:
    with pytest.raises(ValueError):
        SectionItem(
            section_id="1",
            parent_section_id=None,
            depth=1,
            title="工程化导入",
            order_index=1,
            description="确认课程目标。",
            key_knowledge_points=[],
        )


def test_normalize_generated_sections_requires_chapter_and_subsection_ids() -> None:
    with pytest.raises(ValueError, match="一级章节 section_id"):
        _normalize_generated_sections(
            [
                {
                    "section_id": "chapter_1",
                    "parent_section_id": None,
                    "depth": 1,
                    "title": "工程化导入",
                    "order_index": 1,
                    "description": "确认课程目标。",
                    "key_knowledge_points": ["课程目标"],
                },
                {
                    "section_id": "chapter_1.1",
                    "parent_section_id": "chapter_1",
                    "depth": 2,
                    "title": "能力边界",
                    "order_index": 2,
                    "description": "确认能力边界。",
                    "key_knowledge_points": ["能力拆解"],
                },
                {
                    "section_id": "chapter_1.2",
                    "parent_section_id": "chapter_1",
                    "depth": 2,
                    "title": "验收方式",
                    "order_index": 3,
                    "description": "确认验收方式。",
                    "key_knowledge_points": ["验收证据"],
                },
                {
                    "section_id": "chapter_1.3",
                    "parent_section_id": "chapter_1",
                    "depth": 2,
                    "title": "验收实践",
                    "order_index": 4,
                    "description": "确认验收实践。",
                    "key_knowledge_points": ["验收实践要点"],
                },
                {
                    "section_id": "2",
                    "parent_section_id": None,
                    "depth": 1,
                    "title": "进阶实践",
                    "order_index": 5,
                    "description": "进入实践阶段。",
                    "key_knowledge_points": ["实践目标"],
                },
                {
                    "section_id": "2.1",
                    "parent_section_id": "2",
                    "depth": 2,
                    "title": "实践准备",
                    "order_index": 6,
                    "description": "准备实践材料。",
                    "key_knowledge_points": ["材料准备"],
                },
                {
                    "section_id": "2.2",
                    "parent_section_id": "2",
                    "depth": 2,
                    "title": "过程演练",
                    "order_index": 7,
                    "description": "完成过程演练。",
                    "key_knowledge_points": ["过程演练"],
                },
                {
                    "section_id": "2.3",
                    "parent_section_id": "2",
                    "depth": 2,
                    "title": "结果检查",
                    "order_index": 8,
                    "description": "检查实践结果。",
                    "key_knowledge_points": ["结果检查"],
                },
            ]
        )

    with pytest.raises(ValueError, match="1.1、1.2"):
        _normalize_generated_sections(
            [
                {
                    "section_id": "1",
                    "parent_section_id": None,
                    "depth": 1,
                    "title": "工程化导入",
                    "order_index": 1,
                    "description": "确认课程目标。",
                    "key_knowledge_points": ["课程目标"],
                },
                {
                    "section_id": "1.a",
                    "parent_section_id": "1",
                    "depth": 2,
                    "title": "能力边界",
                    "order_index": 2,
                    "description": "确认能力边界。",
                    "key_knowledge_points": ["能力拆解"],
                },
                {
                    "section_id": "1.2",
                    "parent_section_id": "1",
                    "depth": 2,
                    "title": "验收方式",
                    "order_index": 3,
                    "description": "确认验收方式。",
                    "key_knowledge_points": ["验收证据"],
                },
                {
                    "section_id": "1.3",
                    "parent_section_id": "1",
                    "depth": 2,
                    "title": "验收实践",
                    "order_index": 4,
                    "description": "确认验收实践。",
                    "key_knowledge_points": ["验收实践要点"],
                },
                {
                    "section_id": "2",
                    "parent_section_id": None,
                    "depth": 1,
                    "title": "进阶实践",
                    "order_index": 5,
                    "description": "进入实践阶段。",
                    "key_knowledge_points": ["实践目标"],
                },
                {
                    "section_id": "2.1",
                    "parent_section_id": "2",
                    "depth": 2,
                    "title": "实践准备",
                    "order_index": 6,
                    "description": "准备实践材料。",
                    "key_knowledge_points": ["材料准备"],
                },
                {
                    "section_id": "2.2",
                    "parent_section_id": "2",
                    "depth": 2,
                    "title": "过程演练",
                    "order_index": 7,
                    "description": "完成过程演练。",
                    "key_knowledge_points": ["过程演练"],
                },
                {
                    "section_id": "2.3",
                    "parent_section_id": "2",
                    "depth": 2,
                    "title": "结果检查",
                    "order_index": 8,
                    "description": "检查实践结果。",
                    "key_knowledge_points": ["结果检查"],
                },
            ]
        )


def test_normalize_generated_sections_rejects_single_top_level_chapter() -> None:
    with pytest.raises(ValueError, match="课程大纲至少需要两个一级章节"):
        _normalize_generated_sections(
            _two_chapter_outline_with_source_ids(["1.1", "1.2"])["sections"][:4]
        )


def test_normalize_generated_sections_rejects_internal_source_ids_in_visible_text() -> (
    None
):
    outline = _two_chapter_outline_with_source_ids(["sec_1_1", "sec_1_2"])
    outline["sections"][1]["title"] = "sec_1_1 教材小节"

    with pytest.raises(ValueError, match="课程大纲可见文案不能包含教材内部小节 ID"):
        _normalize_generated_sections(outline["sections"])


def test_build_analysis_input_uses_compact_course_and_profile_fields() -> None:
    query = _build_analysis_input(
        {
            "course_node_id": "year_3_course_1",
            "course_or_chapter_theme": "AI 应用开发",
            "grade_id": "year_3",
            "course_goal": "完成 AI 应用开发基础能力搭建",
            "time_arrangement": {
                "semester_scope": "上学期",
                "duration": "6 周",
                "pace_reason": "围绕平时学习安排",
            },
            "key_points": ["Prompt 设计", "前后端联调"],
            "difficult_points": ["错误处理与重试"],
            "learning_sequence": ["需求拆解", "接口接入", "最小闭环演示"],
            "prerequisite_node_ids": [],
            "chapter_nodes": [{"chapter_node_id": "unused"}],
            "core_knowledge_points": [{"knowledge_point_id": "unused"}],
            "knowledge_relations": [{"from": "a", "to": "b"}],
            "downstream_resource_direction_ids": ["resource_1"],
            "acceptance_criteria": ["完成一个可运行的 AI 功能模块并接入 Web 应用"],
            "source_textbook_id": SOURCE_TEXTBOOK_ID,
            "source_textbook_title": SOURCE_TEXTBOOK_TITLE,
            "source_outline_section_ids": ["1.1", "1.2"],
        },
        _complete_profile(),
        {
            "year_3": {
                "current_learning_course": {
                    "grade_id": "year_3",
                    "course_node_id": "year_3_course_1",
                },
                "grade_plans": {
                    "year_3": {
                        "course_nodes": [
                            _course_outline_target(),
                            {
                                **_course_outline_target(),
                                "course_node_id": "year_3_course_2",
                                "course_or_chapter_theme": "AI Agent 开发项目实战",
                            },
                        ],
                    },
                },
            },
        },
    )

    assert "输出前先完成以下分析" in query
    assert "当前课程输入" in query
    assert "同年级课程顺序" in query
    assert "学习者输入" in query
    assert "chapter_nodes" not in query
    assert "knowledge_relations" not in query
    assert "profile_summary" in query


def test_build_analysis_inputs_include_course_source_bindings() -> None:
    course = {
        **_course_outline_target(),
        "source_textbook_id": "textbook-ai-web",
        "source_textbook_title": "AI 应用开发项目教程",
        "source_outline_section_ids": ["1.1", "1.2"],
    }
    query = _build_analysis_input(
        course,
        _complete_profile(),
        {
            "year_3": {
                "current_learning_course": {
                    "grade_id": "year_3",
                    "course_node_id": "year_3_course_1",
                },
                "grade_plans": {"year_3": {"course_nodes": [course]}},
            }
        },
    )
    year_query = _build_year_analysis_input(
        "year_3",
        [course],
        "year_3_course_1",
        _complete_profile(),
    )

    course_input = _json_block_after_label(query, "当前课程输入")
    year_courses_input = _json_block_after_label(year_query, "全年课程输入")

    assert isinstance(course_input, dict)
    assert course_input["source_textbook_id"] == "textbook-ai-web"
    assert course_input["source_textbook_title"] == "AI 应用开发项目教程"
    assert course_input["source_outline_section_ids"] == ["1.1", "1.2"]
    assert isinstance(year_courses_input, list)
    assert year_courses_input[0]["source_textbook_id"] == "textbook-ai-web"
    assert year_courses_input[0]["source_textbook_title"] == "AI 应用开发项目教程"
    assert year_courses_input[0]["source_outline_section_ids"] == ["1.1", "1.2"]
    for payload in (query, year_query):
        assert "sections[] 的 source_* 字段必须来自这些绑定教材小节" in payload
        assert "不能新增未绑定来源" in payload


def test_build_analysis_inputs_declare_resource_agent_handoff_requirements() -> None:
    course = {
        **_course_outline_target(),
        "source_textbook_id": "textbook-data-structures",
        "source_textbook_title": "数据结构教程",
        "source_outline_section_ids": ["2.1", "2.2"],
    }
    query = _build_analysis_input(
        course,
        _complete_profile(),
        {
            "year_3": {
                "current_learning_course": {
                    "grade_id": "year_3",
                    "course_node_id": "year_3_course_1",
                },
                "grade_plans": {"year_3": {"course_nodes": [course]}},
            }
        },
    )
    year_query = _build_year_analysis_input(
        "year_3",
        [course],
        "year_3_course_1",
        _complete_profile(),
    )

    for payload in (query, year_query):
        assert (
            "每个二级小节必须为后续 Markdown 教学、视频检索和 HTML 动画提供具体知识点"
            in payload
        )
        assert "不得把小节写成总体性、模糊的资源主题" in payload
        assert (
            "Markdown 智能体必须使用本小节 source_section_ids 对应教材正文" in payload
        )


def test_build_analysis_input_includes_real_source_content_lengths(
    tmp_path: Path,
) -> None:
    _seed_published_textbook_sections(
        {
            "1.1": "甲" * 321,
            "1.2": "乙" * 654,
            "1.3": "丙" * 987,
        },
        tmp_path,
    )
    course = _course_with_source_sections(["1.1", "1.2", "1.3"])

    source_contexts = _source_section_contexts_for_courses([course])
    query = _build_analysis_input(
        course,
        _complete_profile(),
        {
            "year_3": {
                "current_learning_course": {
                    "grade_id": "year_3",
                    "course_node_id": "year_3_course_1",
                },
                "grade_plans": {"year_3": {"course_nodes": [course]}},
            }
        },
        source_section_contexts=source_contexts,
    )
    course_input = _json_block_after_label(query, "当前课程输入")

    assert isinstance(course_input, dict)
    assert course_input["source_outline_sections"] == [
        {
            "section_id": "1.1",
            "title": "教材小节 1.1",
            "parent_section_id": None,
            "order_index": 1,
            "content_char_count": 321,
        },
        {
            "section_id": "1.2",
            "title": "教材小节 1.2",
            "parent_section_id": None,
            "order_index": 2,
            "content_char_count": 654,
        },
        {
            "section_id": "1.3",
            "title": "教材小节 1.3",
            "parent_section_id": None,
            "order_index": 3,
            "content_char_count": 987,
        },
    ]


def test_build_analysis_input_uses_english_original_source_content_lengths(
    tmp_path: Path,
) -> None:
    engine = build_engine(postgresql_test_url(tmp_path, "course-source-english"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(enabled_source())
        row = published_textbook(
            textbook_id=SOURCE_TEXTBOOK_ID,
            title=SOURCE_TEXTBOOK_TITLE,
        )
        row.language = "en"
        row.translated_language = "zh"
        row.outline = {"sections": [{"section_id": "1.1", "title": "教材小节 1.1"}]}
        session.add(row)
        session.add(
            section(
                textbook_id=SOURCE_TEXTBOOK_ID,
                section_content_id="english-section-1-1",
                section_id="1.1",
                title="教材小节 1.1",
                content_original="Agents act in environments.",
                content_zh="",
                order_index=1,
            )
        )
        session.commit()

    course = _course_with_source_sections(["1.1"])
    source_contexts = _source_section_contexts_for_courses([course])
    query = _build_analysis_input(
        course,
        _complete_profile(),
        {
            "year_3": {
                "current_learning_course": {
                    "grade_id": "year_3",
                    "course_node_id": "year_3_course_1",
                },
                "grade_plans": {"year_3": {"course_nodes": [course]}},
            }
        },
        source_section_contexts=source_contexts,
    )
    course_input = _json_block_after_label(query, "当前课程输入")

    assert course_input["source_outline_sections"][0]["content_char_count"] == len(
        "Agents act in environments."
    )


def test_normalize_course_outline_recomputes_source_content_chars_from_textbook(
    tmp_path: Path,
) -> None:
    _seed_published_textbook_sections(
        {
            "1.1": "甲" * 100,
            "1.2": "乙" * 210,
            "1.3": "丙" * 50,
            "1.4": "丁" * 60,
        },
        tmp_path,
    )
    course = _course_with_source_sections(["1.1", "1.2", "1.3", "1.4"])

    outline = _normalize_generated_course_outline(
        course,
        _raw_outline_with_source_groups(
            ["1.1", "1.2"],
            first_child_chars=999,
        ),
    )
    first_child = outline["sections"][1]

    assert first_child["source_section_ids"] == ["1.1", "1.2"]
    assert first_child["source_section_titles"] == ["教材小节 1.1", "教材小节 1.2"]
    assert first_child["source_content_chars"] == 310


def test_normalize_course_outline_rejects_source_groups_over_8000_chars(
    tmp_path: Path,
) -> None:
    _seed_published_textbook_sections(
        {
            "1.1": "甲" * 5000,
            "1.2": "乙" * 4000,
            "1.3": "丙" * 50,
            "1.4": "丁" * 60,
        },
        tmp_path,
    )
    course = _course_with_source_sections(["1.1", "1.2", "1.3", "1.4"])

    with pytest.raises(ValueError, match="source_content_chars 不能超过 8000"):
        _normalize_generated_course_outline(
            course,
            _raw_outline_with_source_groups(["1.1", "1.2"]),
        )


def test_course_knowledge_output_contracts_show_required_source_fields() -> None:
    assert "section_texts" in COURSE_OUTLINE_NAMING_SYSTEM_PROMPT
    assert "title" in COURSE_OUTLINE_NAMING_SYSTEM_PROMPT
    assert "description" in COURSE_OUTLINE_NAMING_SYSTEM_PROMPT
    assert "key_knowledge_points" in COURSE_OUTLINE_NAMING_SYSTEM_PROMPT
    assert "不得输出 source_textbook_id" in COURSE_OUTLINE_NAMING_SYSTEM_PROMPT
    assert "source_section_ids" in COURSE_OUTLINE_NAMING_SYSTEM_PROMPT


def test_course_knowledge_naming_prompt_forbids_source_fields() -> None:
    assert "不得输出 source_textbook_id" in COURSE_OUTLINE_NAMING_SYSTEM_PROMPT
    assert "source_section_ids" in COURSE_OUTLINE_NAMING_SYSTEM_PROMPT
    assert "source_section_titles" in COURSE_OUTLINE_NAMING_SYSTEM_PROMPT
    assert "source_content_chars" in COURSE_OUTLINE_NAMING_SYSTEM_PROMPT
    assert "不得直接把英文教材标题复制到学生端可见文案" in (
        COURSE_OUTLINE_NAMING_SYSTEM_PROMPT
    )


def test_normalize_generated_sections_rejects_empty_source_fields() -> None:
    outline = _two_chapter_outline_with_source_ids(["1.1", "1.2"])
    outline["sections"][1]["source_textbook_id"] = ""

    with pytest.raises(ValueError, match="source_textbook_id"):
        _normalize_generated_sections(outline["sections"])


def test_upsert_outline_clears_section_generated_assets_when_outline_changes(
    tmp_path: Path,
) -> None:
    engine = build_engine(postgresql_test_url(tmp_path, "course-knowledge-upsert"))
    set_engine(engine)
    init_db(engine)
    original_outline = _with_section_sources(
        {
            "course_id": "year_3_course_1",
            "course_name": "AI 应用开发",
            "grade_year": "year_3",
            "personalization_summary": "旧大纲。",
            "sections": [
                {
                    "section_id": "1",
                    "parent_section_id": None,
                    "depth": 1,
                    "title": "旧章",
                    "order_index": 1,
                    "description": "旧章说明。",
                    "key_knowledge_points": ["旧知识点"],
                },
                {
                    "section_id": "1.1",
                    "parent_section_id": "1",
                    "depth": 2,
                    "title": "旧小节",
                    "order_index": 2,
                    "description": "旧小节说明。",
                    "key_knowledge_points": ["旧小节知识点"],
                },
            ],
            "learning_sequence": ["第一章：旧章"],
            "total_estimated_hours": "8 小时",
            "section_markdowns": {"1.1": {"markdown": "# 旧小节"}},
            "section_composed_markdowns": {"1.1": {"markdown": "# 旧组合"}},
            "section_video_links": {"1.1": [{"title": "旧视频"}]},
            "section_html_animations": {"1.1": [{"title": "旧动画"}]},
        }
    )
    updated_outline = {
        **original_outline,
        "personalization_summary": "新大纲。",
        "sections": [
            {
                **original_outline["sections"][0],
                "title": "新章",
            },
            {
                **original_outline["sections"][1],
                "source_section_ids": ["2.1"],
                "source_section_titles": ["新小节来源"],
            },
        ],
    }

    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        _add_default_source_material(session)
        session.commit()
        upsert_user_course_knowledge_outline(session, "user-1", original_outline)
        row = upsert_user_course_knowledge_outline(session, "user-1", updated_outline)

    assert row.outline_data["course_name"] == "AI 应用开发"
    assert row.outline_data["sections"][0]["title"] == "新章"
    assert "section_markdowns" not in row.outline_data
    assert "section_composed_markdowns" not in row.outline_data
    assert "section_video_links" not in row.outline_data
    assert "section_html_animations" not in row.outline_data


def test_upsert_outline_clears_section_generated_assets_when_content_plan_changes(
    tmp_path: Path,
) -> None:
    engine = build_engine(
        postgresql_test_url(tmp_path, "course-knowledge-upsert-content")
    )
    set_engine(engine)
    init_db(engine)
    original_outline = _with_section_sources(
        {
            "course_id": "year_3_course_1",
            "course_name": "AI 应用开发",
            "grade_year": "year_3",
            "personalization_summary": "旧大纲。",
            "sections": [
                {
                    "section_id": "1",
                    "parent_section_id": None,
                    "depth": 1,
                    "title": "需求边界",
                    "order_index": 1,
                    "description": "旧章说明。",
                    "key_knowledge_points": ["旧知识点"],
                },
                {
                    "section_id": "1.1",
                    "parent_section_id": "1",
                    "depth": 2,
                    "title": "功能边界",
                    "order_index": 2,
                    "description": "旧小节说明。",
                    "key_knowledge_points": ["旧小节知识点"],
                },
            ],
            "learning_sequence": ["第一章：需求边界"],
            "total_estimated_hours": "8 小时",
            "section_markdowns": {"1.1": {"markdown": "# 旧小节"}},
            "section_composed_markdowns": {"1.1": {"markdown": "# 旧组合"}},
            "section_video_links": {"1.1": [{"title": "旧视频"}]},
            "section_html_animations": {"1.1": [{"title": "旧动画"}]},
        }
    )
    updated_outline = {
        **original_outline,
        "sections": [
            original_outline["sections"][0],
            {
                **original_outline["sections"][1],
                "description": "新小节说明。",
                "key_knowledge_points": ["新小节知识点"],
            },
        ],
    }

    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        _add_default_source_material(session)
        session.commit()
        upsert_user_course_knowledge_outline(session, "user-1", original_outline)
        row = upsert_user_course_knowledge_outline(session, "user-1", updated_outline)

    assert row.outline_data["sections"][1]["description"] == "新小节说明。"
    assert row.outline_data["sections"][1]["key_knowledge_points"] == ["新小节知识点"]
    assert "section_markdowns" not in row.outline_data
    assert "section_composed_markdowns" not in row.outline_data
    assert "section_video_links" not in row.outline_data
    assert "section_html_animations" not in row.outline_data


def test_run_course_knowledge_agent_uses_structured_outline_and_persists(
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    class RecordingLlm:
        pass

    def designed_outline_payload() -> dict:
        payload = {
            "personalization_summary": "按项目驱动画像先建立需求边界，再完成接口联调与演示闭环。",
            "sections": [
                {
                    "section_id": "1",
                    "parent_section_id": None,
                    "depth": 1,
                    "title": "需求边界与功能验收",
                    "order_index": 1,
                    "description": "把 AI 功能目标收敛成可交付的最小闭环。",
                    "key_knowledge_points": ["用户场景拆解", "验收标准定义"],
                },
                {
                    "section_id": "1.1",
                    "parent_section_id": "1",
                    "depth": 2,
                    "title": "功能边界拆解",
                    "order_index": 2,
                    "description": "结合用户目标确认第一版必须实现的功能范围。",
                    "key_knowledge_points": ["输入输出契约"],
                },
                {
                    "section_id": "1.2",
                    "parent_section_id": "1",
                    "depth": 2,
                    "title": "验收证据设计",
                    "order_index": 3,
                    "description": "设计能够证明功能可运行的验收材料。",
                    "key_knowledge_points": ["运行截图", "接口响应样例"],
                },
                {
                    "section_id": "1.3",
                    "parent_section_id": "1",
                    "depth": 2,
                    "title": "测试验证方法",
                    "order_index": 4,
                    "description": "介绍如何编写集成测试以验证需求边界。",
                    "key_knowledge_points": ["集成测试"],
                },
                {
                    "section_id": "2",
                    "parent_section_id": None,
                    "depth": 1,
                    "title": "AI 接口接入与联调",
                    "order_index": 5,
                    "description": "把模型调用接入 Web 功能并处理关键异常。",
                    "key_knowledge_points": [
                        "OpenAI-compatible API 调用",
                        "错误处理",
                    ],
                },
                {
                    "section_id": "2.1",
                    "parent_section_id": "2",
                    "depth": 2,
                    "title": "请求结构设计",
                    "order_index": 5,
                    "description": "设计前后端之间稳定传递的请求结构。",
                    "key_knowledge_points": ["请求 payload", "响应解析"],
                },
                {
                    "section_id": "2.2",
                    "parent_section_id": "2",
                    "depth": 2,
                    "title": "异常与重试策略",
                    "order_index": 6,
                    "description": "处理调用失败、超时和用户可恢复提示。",
                    "key_knowledge_points": ["超时处理", "可恢复错误"],
                },
                {
                    "section_id": "2.3",
                    "parent_section_id": "2",
                    "depth": 2,
                    "title": "综合联调与上线准备",
                    "order_index": 7,
                    "description": "对接口调用和异常重试进行联调与上线准备。",
                    "key_knowledge_points": ["联调验证", "部署发布"],
                },
            ],
            "learning_sequence": ["1", "2"],
            "total_estimated_hours": "18 小时",
        }
        return _with_section_sources(payload)

    class DesignedOutlineChain:
        async def ainvoke(self, payload):
            captured["query"] = payload["query"]
            return AIMessage(
                content=json.dumps(
                    _naming_payload_from_outline(designed_outline_payload()),
                    ensure_ascii=False,
                )
            )

    class DesignedOutlinePrompt:
        def __or__(self, _other):
            return DesignedOutlineChain()

    engine = build_engine(
        postgresql_test_url(tmp_path, "course-knowledge-local-outline")
    )
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        _add_default_source_material(session)
        session.commit()

    state = {
        "user_id": "user-1",
        "profile": _complete_profile(),
        "year_learning_paths": {
            "year_3": {
                "current_learning_course": {
                    "grade_id": "year_3",
                    "course_node_id": "year_3_course_1",
                },
                "grade_plans": {
                    "year_3": {
                        "course_nodes": [
                            {
                                "course_node_id": "year_3_course_1",
                                "course_or_chapter_theme": "AI 应用开发",
                                "grade_id": "year_3",
                                "course_goal": "完成 AI 应用开发基础能力搭建",
                                "time_arrangement": {
                                    "semester_scope": "上学期",
                                    "duration": "6 周",
                                    "pace_reason": "围绕平时学习安排",
                                },
                                "key_points": ["Prompt 设计", "前后端联调"],
                                "difficult_points": ["错误处理与重试"],
                                "learning_sequence": [
                                    "需求拆解",
                                    "接口接入",
                                    "最小闭环演示",
                                ],
                                "prerequisite_node_ids": [],
                                "chapter_nodes": [],
                                "core_knowledge_points": [],
                                "knowledge_relations": [],
                                "downstream_resource_direction_ids": [],
                                "acceptance_criteria": [
                                    "完成一个可运行的 AI 功能模块并接入 Web 应用"
                                ],
                                "source_textbook_id": SOURCE_TEXTBOOK_ID,
                                "source_textbook_title": SOURCE_TEXTBOOK_TITLE,
                                "source_outline_section_ids": (
                                    DEFAULT_SOURCE_SECTION_IDS
                                ),
                            },
                        ],
                    },
                },
            },
        },
        "messages": _course_tool_messages("year_3_course_1"),
    }

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
        result = asyncio.run(run_course_knowledge_agent(state, RecordingLlm()))
    finally:
        module.ChatPromptTemplate = original_factory

    assert not hasattr(RecordingLlm(), "with_structured_output")
    assert "AI 应用开发" in str(captured["query"])
    assert "sections_to_name" in str(captured["query"])
    assert "JSON Schema" not in str(captured["query"])
    assert "source_section_ids" not in str(captured["query"])
    assert "需求拆解" not in str(captured["query"])
    assert "接口接入" not in str(captured["query"])
    assert "最小闭环演示" not in str(captured["query"])
    assert result["course_knowledge"]["course_id"] == "year_3_course_1"
    assert result["course_knowledge"]["course_name"] == "AI 应用开发"
    assert result["course_knowledge"]["learning_sequence"] == [
        "第一章：需求边界与功能验收",
        "第二章：AI 接口接入与联调",
    ]
    assert result["course_knowledge"]["sections"][0]["key_knowledge_points"] == [
        "用户场景拆解",
        "验收标准定义",
    ]

    with Session(engine) as session:
        row = session.get(UserCourseKnowledgeOutline, ("user-1", "year_3_course_1"))

    assert row is not None
    assert row.outline_data["course_name"] == "AI 应用开发"
    assert row.outline_data["sections"][0]["section_id"] == "1"


def test_run_course_knowledge_agent_uses_single_short_naming_call(
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {"queries": []}

    class RecordingLlm:
        pass

    naming_payload = {
        "personalization_summary": "先理解计算模型，再建立复杂度分析的判断框架。",
        "section_texts": {
            "1": {
                "title": "计算模型的基本边界",
                "description": "建立抽象机器、可计算过程和问题表达之间的关系。",
                "key_knowledge_points": ["抽象机器", "可计算过程", "问题表达"],
            },
            "1.1": {
                "title": "抽象机器与状态转换",
                "description": "理解计算模型如何用状态、输入和转换规则描述计算。",
                "key_knowledge_points": ["状态表示", "转换规则", "输入输出"],
            },
            "1.2": {
                "title": "可计算问题的表达方式",
                "description": "把实际问题转换成可以被模型处理的形式化对象。",
                "key_knowledge_points": ["问题形式化", "输入规模", "判定问题"],
            },
            "2": {
                "title": "复杂度分析的度量方法",
                "description": "建立时间、空间和增长阶之间的分析框架。",
                "key_knowledge_points": ["时间复杂度", "空间复杂度", "增长阶"],
            },
            "2.1": {
                "title": "输入规模与资源消耗",
                "description": "理解输入规模变化时算法资源消耗的变化方式。",
                "key_knowledge_points": ["输入规模", "资源消耗", "上界估计"],
            },
        },
    }

    class NamingChain:
        async def ainvoke(self, payload):
            captured["queries"].append(payload["query"])
            return AIMessage(content=json.dumps(naming_payload, ensure_ascii=False))

    class NamingPrompt:
        def __or__(self, _other):
            return NamingChain()

    engine = _seed_published_textbook_sections_with_parents(
        [
            {
                "section_id": "sec_1_1",
                "parent_section_id": "1",
                "title": "Computational Models",
                "content_zh": "计算模型用于描述算法能够执行的抽象过程。",
            },
            {
                "section_id": "sec_1_2",
                "parent_section_id": "1",
                "title": "Formal Problems",
                "content_zh": "形式化问题把真实任务转换为可分析的输入输出关系。",
            },
            {
                "section_id": "sec_2_1",
                "parent_section_id": "2",
                "title": "Complexity Measures",
                "content_zh": "复杂度度量用于分析算法运行时间和空间消耗。",
            },
        ],
        tmp_path,
        "course-knowledge-short-naming",
    )
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.commit()

    state = {
        "user_id": "user-1",
        "profile": _complete_profile(),
        "year_learning_paths": {
            "year_3": {
                "current_learning_course": {
                    "grade_id": "year_3",
                    "course_node_id": "year_3_course_1",
                },
                "grade_plans": {
                    "year_3": {
                        "course_nodes": [
                            _course_outline_target(learning_sequence=[])
                            | {
                                "course_or_chapter_theme": "计算模型与复杂度分析基础",
                                "source_outline_section_ids": [
                                    "sec_1_1",
                                    "sec_1_2",
                                    "sec_2_1",
                                ],
                            },
                        ],
                    },
                },
            },
        },
        "messages": _course_tool_messages("year_3_course_1"),
    }

    module = __import__(
        "app.orchestration.agents.course_knowledge", fromlist=["ChatPromptTemplate"]
    )
    original_factory = module.ChatPromptTemplate

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return NamingPrompt()

    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(run_course_knowledge_agent(state, RecordingLlm()))
    finally:
        module.ChatPromptTemplate = original_factory

    assert len(captured["queries"]) == 1
    query = str(captured["queries"][0])
    assert "section_texts" in query
    assert "source_section_ids" not in query
    assert "sec_1_1" not in query
    assert "Computational Models" in query
    assert "error" not in result
    outline = result["course_knowledge"]
    assert outline["course_name"] == "计算模型与复杂度分析基础"
    assert outline["total_estimated_hours"] == "6 小时"
    assert outline["learning_sequence"] == [
        "第一章：计算模型的基本边界",
        "第二章：复杂度分析的度量方法",
    ]
    assert [section["section_id"] for section in outline["sections"]] == [
        "1",
        "1.1",
        "1.2",
        "2",
        "2.1",
    ]
    assert outline["sections"][1]["source_section_ids"] == ["sec_1_1"]
    assert outline["sections"][2]["source_section_ids"] == ["sec_1_2"]
    assert outline["sections"][4]["source_section_ids"] == ["sec_2_1"]
    assert outline["sections"][1]["source_section_titles"] == ["Computational Models"]

    with Session(engine) as session:
        row = session.get(UserCourseKnowledgeOutline, ("user-1", "year_3_course_1"))

    assert row is not None


def test_run_course_knowledge_agent_infers_published_source_for_unbound_complexity_course(
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {"queries": []}

    class RecordingLlm:
        pass

    naming_payload = {
        "personalization_summary": "围绕复杂度分析主线，把数学工具、增长率和代码成本判断串成完整学习路径。",
        "section_texts": {
            "1": {
                "title": "复杂度分析的基础框架",
                "description": "建立从效率问题到增长率分析的整体学习边界。",
                "key_knowledge_points": ["效率问题", "数学工具", "复杂度判断"],
            },
            "1.1": {
                "title": "效率问题与算法选择",
                "description": "理解为什么同样功能的程序会因为输入规模产生巨大效率差异。",
                "key_knowledge_points": ["输入规模", "运行效率", "算法选择"],
            },
            "1.2": {
                "title": "数学背景与符号准备",
                "description": "补齐复杂度分析中需要反复使用的数学表达方式。",
                "key_knowledge_points": ["数学符号", "增长率比较", "证明习惯"],
            },
            "1.3": {
                "title": "指数与对数增长",
                "description": "比较指数和对数在算法运行时间中的增长速度。",
                "key_knowledge_points": ["指数增长", "对数增长", "规模变化"],
            },
            "1.4": {
                "title": "阶乘增长与组合规模",
                "description": "理解阶乘增长为什么会让朴素枚举方法快速失控。",
                "key_knowledge_points": ["阶乘", "组合数量", "枚举成本"],
            },
            "1.5": {
                "title": "正确性与时空成本",
                "description": "把正确性、时间复杂度和空间复杂度放在同一分析框架中检查。",
                "key_knowledge_points": ["正确性", "时间复杂度", "空间复杂度"],
            },
        },
    }

    class NamingChain:
        async def ainvoke(self, payload):
            captured["queries"].append(payload["query"])
            return AIMessage(content=json.dumps(naming_payload, ensure_ascii=False))

    class NamingPrompt:
        def __or__(self, _other):
            return NamingChain()

    engine = build_engine(postgresql_test_url(tmp_path, "course-source-inference"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(enabled_source())
        ai_book = published_textbook(
            textbook_id="textbook-ai-agents",
            title="Artificial Intelligence: Foundations of Computational Agents",
        )
        ai_book.description = "Agents, planning and search."
        ai_book.tags = ["人工智能", "AI Agent"]
        session.add(ai_book)
        session.add(
            section(
                textbook_id="textbook-ai-agents",
                section_content_id="ai-sec-1",
                section_id="sec_ai_1",
                title="Agents and Environments",
                content_zh="智能体与环境交互，形成感知、动作与反馈。",
                order_index=1,
            )
        )

        ods_book = published_textbook(
            textbook_id="textbook-ods-python",
            title="Open Data Structures (Python Edition)",
        )
        ods_book.description = (
            "Data structures, mathematical background and asymptotic analysis."
        )
        ods_book.tags = ["数据结构", "算法", "Python"]
        ods_book.outline = {
            "sections": [
                {"section_id": "sec_1_1", "title": "1.1 The Need for Efficiency"},
                {"section_id": "sec_1_8", "title": "1.2 Interfaces"},
                {"section_id": "sec_1_13", "title": "1.3 Mathematical Background"},
                {
                    "section_id": "sec_1_14",
                    "title": "1.3.1 Exponentials and Logarithms",
                },
                {"section_id": "sec_1_15", "title": "1.3.2 Factorials"},
                {"section_id": "sec_1_16", "title": "1.3.3 Asymptotic Notation"},
                {
                    "section_id": "sec_1_19",
                    "title": "1.5 Correctness, Time Complexity, and Space Complexity",
                },
            ]
        }
        session.add(ods_book)
        ods_sections = [
            (
                "sec_1_1",
                "1.1 The Need for Efficiency",
                "Efficiency and algorithm choice affect running time as input size grows.",
                655,
            ),
            (
                "sec_1_8",
                "1.2 Interfaces",
                "Interfaces describe operations supported by data structures.",
                1200,
            ),
            (
                "sec_1_13",
                "1.3 Mathematical Background",
                "Mathematical background prepares notation for analyzing data structures.",
                479,
            ),
            (
                "sec_1_14",
                "1.3.1 Exponentials and Logarithms",
                "Exponentials and logarithms describe different growth rates.",
                2842,
            ),
            (
                "sec_1_15",
                "1.3.2 Factorials",
                "Factorials arise when counting permutations and combinations.",
                1853,
            ),
            (
                "sec_1_16",
                "1.3.3 Asymptotic Notation",
                "Big-O, Big-Omega and Big-Theta are asymptotic notation for complexity.",
                9477,
            ),
            (
                "sec_1_19",
                "1.5 Correctness, Time Complexity, and Space Complexity",
                "Correctness, time complexity and space complexity evaluate algorithms.",
                3008,
            ),
        ]
        for index, (section_id, title, content_text, content_chars) in enumerate(
            ods_sections,
            start=1,
        ):
            session.add(
                section(
                    textbook_id="textbook-ods-python",
                    section_content_id=f"ods-{section_id}",
                    section_id=section_id,
                    title=title,
                    content_zh=content_text,
                    order_index=index,
                    content_char_count=content_chars,
                )
            )
        session.commit()

    state = {
        "user_id": "user-1",
        "profile": _complete_profile(),
        "latest_grade_year": "year_3",
        "year_learning_paths": {
            "year_3": {
                "current_learning_course": {
                    "grade_id": "year_3",
                    "course_node_id": "year_3_course_1",
                },
                "grade_plans": {
                    "year_3": {
                        "course_nodes": [
                            {
                                "course_node_id": "year_3_course_1",
                                "course_or_chapter_theme": "计算模型与复杂度分析基础",
                                "grade_id": "year_3",
                                "course_goal": "掌握 Big-O、Big-Omega、Big-Theta 的定义与区别，能准确计算简单代码片段的渐近复杂度，理解摊销成本概念。",
                                "time_arrangement": {
                                    "semester_scope": "上学期",
                                    "duration": "2 周",
                                    "pace_reason": "先建立复杂度分析基础",
                                },
                                "key_points": [
                                    "指数、对数、阶乘的增长率对比及其在算法选择中的意义",
                                    "Big-O、Big-Omega、Big-Theta 的严格数学定义与应用场景",
                                    "时间复杂度与空间复杂度",
                                ],
                                "difficult_points": ["渐近符号的物理意义"],
                                "learning_sequence": ["理解渐近符号", "计算代码复杂度"],
                                "prerequisite_node_ids": [],
                                "chapter_nodes": [],
                                "core_knowledge_points": [],
                                "knowledge_relations": [],
                                "downstream_resource_direction_ids": [],
                                "acceptance_criteria": ["能解释常见代码片段的复杂度"],
                            }
                        ],
                    },
                },
            },
        },
        "messages": _course_tool_messages("计算模型与复杂度分析基础"),
    }

    module = __import__(
        "app.orchestration.agents.course_knowledge", fromlist=["ChatPromptTemplate"]
    )
    original_factory = module.ChatPromptTemplate

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return NamingPrompt()

    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(run_course_knowledge_agent(state, RecordingLlm()))
    finally:
        module.ChatPromptTemplate = original_factory

    assert "error" not in result
    assert len(captured["queries"]) == 1
    query = str(captured["queries"][0])
    assert "source_section_ids" not in query
    assert "sec_1_1" not in query
    assert "1.1 The Need for Efficiency" in query
    assert "1.3.3 Asymptotic Notation" not in query
    outline = result["course_knowledge"]
    assert outline["course_name"] == "计算模型与复杂度分析基础"
    assert outline["total_estimated_hours"] == "10 小时"
    assert outline["learning_sequence"] == ["第一章：复杂度分析的基础框架"]
    assert [section["section_id"] for section in outline["sections"]] == [
        "1",
        "1.1",
        "1.2",
        "1.3",
        "1.4",
        "1.5",
    ]
    assert [
        section["source_section_ids"]
        for section in outline["sections"]
        if section["parent_section_id"] is not None
    ] == [
        ["sec_1_1"],
        ["sec_1_13"],
        ["sec_1_14"],
        ["sec_1_15"],
        ["sec_1_19"],
    ]

    with Session(engine) as session:
        row = session.get(UserCourseKnowledgeOutline, ("user-1", "year_3_course_1"))

    assert row is not None
    assert (
        row.outline_data["sections"][1]["source_textbook_id"] == "textbook-ods-python"
    )


def test_course_source_binding_reselects_when_existing_section_exceeds_limit(
    tmp_path: Path,
) -> None:
    engine = build_engine(postgresql_test_url(tmp_path, "course-source-reselect"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(enabled_source())
        ods_book = published_textbook(
            textbook_id="textbook-ods-python",
            title="Open Data Structures (Python Edition)",
        )
        ods_book.description = (
            "Data structures, mathematical background and model of computation."
        )
        ods_book.tags = ["数据结构", "算法", "Python"]
        session.add(ods_book)
        rows = [
            (
                "sec_1_1",
                "1.1 The Need for Efficiency",
                "Efficiency and algorithm choice affect running time.",
                655,
            ),
            (
                "sec_1_8",
                "1.2 Interfaces",
                "Interfaces describe operations.",
                1324,
            ),
            (
                "sec_1_13",
                "1.3 Mathematical Background",
                "Mathematical notation prepares analysis.",
                479,
            ),
            (
                "sec_1_16",
                "1.3.3 Asymptotic Notation",
                "Big-O, Big-Omega and Big-Theta describe asymptotic complexity.",
                9477,
            ),
            (
                "sec_1_18",
                "1.4 The Model of Computation",
                "The model of computation defines primitive operations.",
                3536,
            ),
        ]
        for index, (section_id, title, content_text, content_chars) in enumerate(
            rows,
            start=1,
        ):
            session.add(
                section(
                    textbook_id="textbook-ods-python",
                    section_content_id=f"ods-{section_id}",
                    section_id=section_id,
                    title=title,
                    content_zh=content_text,
                    order_index=index,
                    content_char_count=content_chars,
                )
            )
        session.commit()

        course = {
            "course_node_id": "year_3_course_1",
            "course_or_chapter_theme": "计算模型与复杂度分析基础",
            "course_goal": "掌握 Big-O、Big-Omega、Big-Theta 的定义与区别，能准确计算简单代码片段的渐近复杂度。",
            "key_points": ["数学背景", "算法效率", "计算模型", "时间复杂度"],
            "source_textbook_id": "textbook-ods-python",
            "source_textbook_title": "Open Data Structures (Python Edition)",
            "source_outline_section_ids": [
                "sec_1_1",
                "sec_1_8",
                "sec_1_13",
                "sec_1_16",
                "sec_1_18",
            ],
        }

        _fill_course_source_binding_from_textbook(session, course)

    assert course["source_outline_section_ids"] == [
        "sec_1_1",
        "sec_1_8",
        "sec_1_13",
        "sec_1_18",
    ]


@pytest.mark.parametrize(
    "section_text",
    [
        {
            "title": "sec_1_1 教材小节",
            "description": "这里泄露了内部教材小节编号。",
            "key_knowledge_points": ["内部编号"],
        },
        {
            "title": "Turing Machines",
            "description": "这里使用了英文教材标题。",
            "key_knowledge_points": ["自动机"],
        },
    ],
)
def test_run_course_knowledge_agent_rejects_bad_naming_output(
    tmp_path: Path,
    section_text: dict,
) -> None:
    class RecordingLlm:
        pass

    class BadNamingChain:
        async def ainvoke(self, _payload):
            return AIMessage(
                content=json.dumps(
                    {
                        "personalization_summary": "按课程目标生成中文大纲。",
                        "section_texts": {
                            "1": {
                                "title": "计算模型基础",
                                "description": "建立计算模型的学习主线。",
                                "key_knowledge_points": ["计算模型"],
                            },
                            "1.1": section_text,
                        },
                    },
                    ensure_ascii=False,
                )
            )

    class BadNamingPrompt:
        def __or__(self, _other):
            return BadNamingChain()

    engine = _seed_published_textbook_sections_with_parents(
        [
            {
                "section_id": "sec_1_1",
                "parent_section_id": "1",
                "title": "Turing Machines",
                "content_zh": "图灵机是一种刻画可计算性的经典计算模型。",
            },
        ],
        tmp_path,
        "course-knowledge-bad-naming",
    )
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.commit()

    state = {
        "user_id": "user-1",
        "profile": _complete_profile(),
        "year_learning_paths": {
            "year_3": {
                "current_learning_course": {
                    "grade_id": "year_3",
                    "course_node_id": "year_3_course_1",
                },
                "grade_plans": {
                    "year_3": {
                        "course_nodes": [
                            _course_outline_target(learning_sequence=[])
                            | {
                                "course_or_chapter_theme": "计算模型与复杂度分析基础",
                                "source_outline_section_ids": ["sec_1_1"],
                            },
                        ],
                    },
                },
            },
        },
        "messages": _course_tool_messages("year_3_course_1"),
    }

    module = __import__(
        "app.orchestration.agents.course_knowledge", fromlist=["ChatPromptTemplate"]
    )
    original_factory = module.ChatPromptTemplate

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return BadNamingPrompt()

    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(run_course_knowledge_agent(state, RecordingLlm()))
    finally:
        module.ChatPromptTemplate = original_factory

    assert result == {"error": COURSE_KNOWLEDGE_RETRY_ERROR, "hard_error": True}
    with Session(engine) as session:
        row = session.get(UserCourseKnowledgeOutline, ("user-1", "year_3_course_1"))

    assert row is None


def test_run_course_knowledge_agent_generates_all_grade_course_outlines_in_one_call(
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {"queries": [], "timeouts": []}

    class RecordingLlm:
        pass

    def outline_payload(course_id: str, title_prefix: str) -> dict:
        payload = {
            "course_id": course_id,
            "personalization_summary": f"{title_prefix} 按全年项目主线承接前后课程。",
            "sections": [
                {
                    "section_id": "1",
                    "parent_section_id": None,
                    "depth": 1,
                    "title": f"{title_prefix} 架构导入",
                    "order_index": 1,
                    "description": f"建立 {title_prefix} 的核心边界。",
                    "key_knowledge_points": ["能力边界", "验收目标"],
                },
                {
                    "section_id": "1.1",
                    "parent_section_id": "1",
                    "depth": 2,
                    "title": "目标与输入输出",
                    "order_index": 2,
                    "description": "确认本课程输入、处理和交付物。",
                    "key_knowledge_points": ["输入契约", "交付物"],
                },
                {
                    "section_id": "1.2",
                    "parent_section_id": "1",
                    "depth": 2,
                    "title": "卡点与验收",
                    "order_index": 3,
                    "description": "提前识别卡点并设计验收方式。",
                    "key_knowledge_points": ["卡点定位", "验收证据"],
                },
                {
                    "section_id": "1.3",
                    "parent_section_id": "1",
                    "depth": 2,
                    "title": "质量指标评估",
                    "order_index": 4,
                    "description": "制定验收标准的衡量指标。",
                    "key_knowledge_points": ["质量指标"],
                },
                {
                    "section_id": "2",
                    "parent_section_id": None,
                    "depth": 1,
                    "title": f"{title_prefix} 实战闭环",
                    "order_index": 5,
                    "description": f"完成 {title_prefix} 的项目闭环。",
                    "key_knowledge_points": ["工程实现", "闭环验证"],
                },
                {
                    "section_id": "2.1",
                    "parent_section_id": "2",
                    "depth": 2,
                    "title": "核心实现",
                    "order_index": 6,
                    "description": "完成最小可运行实现。",
                    "key_knowledge_points": ["最小实现", "接口联调"],
                },
                {
                    "section_id": "2.2",
                    "parent_section_id": "2",
                    "depth": 2,
                    "title": "结果复盘",
                    "order_index": 7,
                    "description": "复盘运行证据并连接下一门课。",
                    "key_knowledge_points": ["运行证据", "课程衔接"],
                },
                {
                    "section_id": "2.3",
                    "parent_section_id": "2",
                    "depth": 2,
                    "title": "发布与部署",
                    "order_index": 8,
                    "description": "打包应用程序并进行部署发布。",
                    "key_knowledge_points": ["打包配置"],
                },
            ],
            "learning_sequence": ["1", "2"],
            "total_estimated_hours": "16 小时",
        }
        return _with_section_sources(payload)

    class YearOutlineChain:
        def __init__(self):
            self.calls = 0

        async def ainvoke(self, payload):
            self.calls += 1
            captured["queries"].append(payload["query"])
            if self.calls == 1:
                outline = outline_payload("year_3_course_1", "AI 应用核心架构")
            else:
                outline = outline_payload("year_3_course_2", "RAG 实战")
            return AIMessage(
                content=json.dumps(
                    _naming_payload_from_outline(outline),
                    ensure_ascii=False,
                )
            )

    year_chain = YearOutlineChain()

    class YearOutlinePrompt:
        def __or__(self, _other):
            return year_chain

    engine = build_engine(postgresql_test_url(tmp_path, "course-knowledge-year-batch"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        _add_default_source_material(session)
        session.commit()

    state = {
        "user_id": "user-1",
        "profile": _complete_profile(),
        "latest_grade_year": "year_3",
        "year_learning_paths": {
            "year_3": {
                "current_learning_course": {
                    "grade_id": "year_3",
                    "course_node_id": "year_3_course_1",
                },
                "grade_plans": {
                    "year_3": {
                        "course_nodes": [
                            {
                                **_course_outline_target(learning_sequence=[]),
                                "course_or_chapter_theme": "AI 应用核心架构",
                            },
                            {
                                **_course_outline_target(learning_sequence=[]),
                                "course_node_id": "year_3_course_2",
                                "course_or_chapter_theme": "RAG 实战",
                            },
                        ],
                    },
                },
            },
        },
        "messages": _course_tool_messages(ALL_CURRENT_GRADE_COURSES_ID),
    }

    module = __import__(
        "app.orchestration.agents.course_knowledge", fromlist=["ChatPromptTemplate"]
    )
    original_factory = module.ChatPromptTemplate
    original_wait_for = module.asyncio.wait_for

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return YearOutlinePrompt()

    async def recording_wait_for(awaitable, *, timeout):
        captured["timeouts"].append(timeout)
        return await awaitable

    module.ChatPromptTemplate = PromptFactory
    module.asyncio.wait_for = recording_wait_for
    try:
        result = asyncio.run(run_course_knowledge_agent(state, RecordingLlm()))
    finally:
        module.ChatPromptTemplate = original_factory
        module.asyncio.wait_for = original_wait_for

    assert not hasattr(RecordingLlm(), "with_structured_output")
    assert year_chain.calls == 2
    assert captured["timeouts"] == [
        module.COURSE_OUTLINE_NAMING_TIMEOUT_SECONDS,
        module.COURSE_OUTLINE_NAMING_TIMEOUT_SECONDS,
    ]
    assert "请为后端已经确定结构的课程大纲生成中文教学命名" in captured["queries"][0]
    assert "JSON Schema" not in captured["queries"][0]
    assert "course_outlines" not in captured["queries"][0]
    assert "AI 应用核心架构" in captured["queries"][0]
    assert "RAG 实战" not in captured["queries"][0]
    assert "RAG 实战" in captured["queries"][1]
    assert result["course_knowledge"]["course_id"] == "year_3_course_1"
    assert result["course_knowledge"]["course_name"] == "AI 应用核心架构"
    assert [outline["course_id"] for outline in result["course_knowledges"]] == [
        "year_3_course_1",
        "year_3_course_2",
    ]

    with Session(engine) as session:
        first_row = session.get(
            UserCourseKnowledgeOutline, ("user-1", "year_3_course_1")
        )
        second_row = session.get(
            UserCourseKnowledgeOutline, ("user-1", "year_3_course_2")
        )

    assert first_row is not None
    assert second_row is not None
    assert first_row.outline_data["course_name"] == "AI 应用核心架构"
    assert second_row.outline_data["course_name"] == "RAG 实战"
    assert second_row.outline_data["sections"][1]["section_id"] == "1.1"


def test_run_course_knowledge_agent_empty_course_id_generates_current_course_only(
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {"queries": [], "timeouts": []}

    class RecordingLlm:
        pass

    class CurrentCourseChain:
        async def ainvoke(self, payload):
            captured["queries"].append(payload["query"])
            outline = _two_chapter_outline_with_source_ids(
                ["1.1", "2.1"],
                personalization_summary="按当前课程生成单门章节大纲。",
            )
            return AIMessage(
                content=json.dumps(
                    _naming_payload_from_outline(outline),
                    ensure_ascii=False,
                )
            )

    class CurrentCoursePrompt:
        def __or__(self, _other):
            return CurrentCourseChain()

    engine = build_engine(
        postgresql_test_url(tmp_path, "course-knowledge-empty-course-id")
    )
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        _add_default_source_material(session)
        session.commit()

    state = {
        "user_id": "user-1",
        "profile": _complete_profile(),
        "latest_grade_year": "year_3",
        "year_learning_paths": {
            "year_3": {
                "current_learning_course": {
                    "grade_id": "year_3",
                    "course_node_id": "year_3_course_1",
                },
                "grade_plans": {
                    "year_3": {
                        "course_nodes": [
                            _course_outline_target(learning_sequence=[]),
                            {
                                **_course_outline_target(learning_sequence=[]),
                                "course_node_id": "year_3_course_2",
                                "course_or_chapter_theme": "RAG 实战",
                            },
                        ],
                    },
                },
            },
        },
        "messages": [],
    }

    module = __import__(
        "app.orchestration.agents.course_knowledge", fromlist=["ChatPromptTemplate"]
    )
    original_factory = module.ChatPromptTemplate
    original_wait_for = module.asyncio.wait_for

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return CurrentCoursePrompt()

    async def recording_wait_for(awaitable, *, timeout):
        captured["timeouts"].append(timeout)
        return await awaitable

    module.ChatPromptTemplate = PromptFactory
    module.asyncio.wait_for = recording_wait_for
    try:
        result = asyncio.run(run_course_knowledge_agent(state, RecordingLlm()))
    finally:
        module.ChatPromptTemplate = original_factory
        module.asyncio.wait_for = original_wait_for

    assert len(captured["queries"]) == 1
    assert captured["timeouts"] == [module.COURSE_OUTLINE_NAMING_TIMEOUT_SECONDS]
    assert "请为后端已经确定结构的课程大纲生成中文教学命名" in captured["queries"][0]
    assert "请一次性为当前年级的全部课程生成详细章节大纲" not in captured["queries"][0]
    assert "course_outlines" not in captured["queries"][0]
    assert result["course_knowledge"]["course_id"] == "year_3_course_1"
    assert "course_knowledges" not in result

    with Session(engine) as session:
        first_row = session.get(
            UserCourseKnowledgeOutline, ("user-1", "year_3_course_1")
        )
        second_row = session.get(
            UserCourseKnowledgeOutline, ("user-1", "year_3_course_2")
        )

    assert first_row is not None
    assert second_row is None


def test_run_course_knowledge_agent_rejects_incomplete_basic_profile(
    tmp_path: Path,
) -> None:
    engine = build_engine(
        postgresql_test_url(tmp_path, "course-knowledge-incomplete-profile")
    )
    set_engine(engine)
    init_db(engine)

    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        _add_default_source_material(session)
        session.commit()

    result = asyncio.run(
        run_course_knowledge_agent(
            {
                "user_id": "user-1",
                "profile": {"type": "basic_profile", "summary_text": "旧画像摘要"},
                "year_learning_paths": {
                    "year_3": {
                        "current_learning_course": {
                            "grade_id": "year_3",
                            "course_node_id": "year_3_course_1",
                        },
                        "grade_plans": {
                            "year_3": {
                                "course_nodes": [
                                    {
                                        "course_node_id": "year_3_course_1",
                                        "course_or_chapter_theme": "AI 应用开发",
                                        "grade_id": "year_3",
                                        "course_goal": "完成 AI 应用开发基础能力搭建",
                                        "time_arrangement": {
                                            "semester_scope": "上学期",
                                            "duration": "6 周",
                                            "pace_reason": "围绕平时学习安排",
                                        },
                                        "key_points": ["Prompt 设计", "前后端联调"],
                                        "difficult_points": ["错误处理与重试"],
                                        "learning_sequence": [
                                            "需求拆解",
                                            "接口接入",
                                            "最小闭环演示",
                                        ],
                                        "prerequisite_node_ids": [],
                                        "chapter_nodes": [],
                                        "core_knowledge_points": [],
                                        "knowledge_relations": [],
                                        "downstream_resource_direction_ids": [],
                                        "acceptance_criteria": [
                                            "完成一个可运行的 AI 功能模块并接入 Web 应用"
                                        ],
                                    },
                                ],
                            },
                        },
                    },
                },
                "messages": [],
            },
            object(),
        )
    )

    assert result == {"error": "请先完成基础画像。"}


def test_run_course_knowledge_agent_returns_hard_error_after_json_output_failure(
    tmp_path: Path,
) -> None:
    class ExplodingLlm:
        pass

    class ExplodingChain:
        async def ainvoke(self, _payload):
            raise RuntimeError("json mode failed")

    class ExplodingPrompt:
        def __or__(self, _other):
            return ExplodingChain()

    engine = build_engine(postgresql_test_url(tmp_path, "course-knowledge-fallback"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        _add_default_source_material(session)
        session.commit()

    state = {
        "user_id": "user-1",
        "profile": _complete_profile(),
        "year_learning_paths": {
            "year_3": {
                "current_learning_course": {
                    "grade_id": "year_3",
                    "course_node_id": "year_3_course_1",
                },
                "grade_plans": {
                    "year_3": {
                        "course_nodes": [
                            {
                                **_course_outline_target(learning_sequence=[]),
                            },
                        ],
                    },
                },
            },
        },
        "messages": _course_tool_messages("year_3_course_1"),
    }

    original_prompt = __import__(
        "app.orchestration.agents.course_knowledge", fromlist=["ChatPromptTemplate"]
    )
    original_factory = original_prompt.ChatPromptTemplate

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return ExplodingPrompt()

    original_prompt.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(run_course_knowledge_agent(state, ExplodingLlm()))
    finally:
        original_prompt.ChatPromptTemplate = original_factory

    assert result == {"error": COURSE_KNOWLEDGE_RETRY_ERROR, "hard_error": True}

    with Session(engine) as session:
        row = session.get(UserCourseKnowledgeOutline, ("user-1", "year_3_course_1"))

    assert row is None


def test_run_course_knowledge_agent_does_not_repair_invalid_naming_output(
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {"queries": []}

    class RecordingLlm:
        pass

    class InvalidNamingChain:
        def __init__(self):
            self.calls = 0

        async def ainvoke(self, payload):
            self.calls += 1
            captured["queries"].append(payload["query"])
            return AIMessage(
                content=json.dumps({"section_texts": {}}, ensure_ascii=False)
            )

    invalid_chain = InvalidNamingChain()

    class InvalidNamingPrompt:
        def __or__(self, _other):
            return invalid_chain

    engine = _seed_published_textbook_sections(
        {
            "sec_1_1": "计算模型用于定义算法可执行的抽象机器与计算过程。",
            "sec_1_2": "复杂度分析用于衡量算法所需的时间、空间与增长阶。",
        },
        tmp_path,
    )
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.commit()

    state = {
        "user_id": "user-1",
        "profile": _complete_profile(),
        "year_learning_paths": {
            "year_3": {
                "current_learning_course": {
                    "grade_id": "year_3",
                    "course_node_id": "year_3_course_1",
                },
                "grade_plans": {
                    "year_3": {
                        "course_nodes": [
                            _course_outline_target(
                                learning_sequence=[],
                            )
                            | {
                                "course_or_chapter_theme": "计算模型与复杂度分析基础",
                                "source_outline_section_ids": [
                                    "sec_1_1",
                                    "sec_1_2",
                                ],
                            },
                        ],
                    },
                },
            },
        },
        "messages": _course_tool_messages("year_3_course_1"),
    }

    module = __import__(
        "app.orchestration.agents.course_knowledge", fromlist=["ChatPromptTemplate"]
    )
    original_factory = module.ChatPromptTemplate

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return InvalidNamingPrompt()

    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(run_course_knowledge_agent(state, RecordingLlm()))
    finally:
        module.ChatPromptTemplate = original_factory

    assert invalid_chain.calls == 1
    assert len(captured["queries"]) == 1
    assert "上一次输出没有通过课程大纲结构校验" not in captured["queries"][0]
    assert result == {"error": COURSE_KNOWLEDGE_RETRY_ERROR, "hard_error": True}

    with Session(engine) as session:
        row = session.get(UserCourseKnowledgeOutline, ("user-1", "year_3_course_1"))

    assert row is None


def test_run_course_knowledge_agent_returns_hard_error_after_invalid_naming(
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {"queries": []}

    class RecordingLlm:
        pass

    class InvalidChain:
        def __init__(self):
            self.calls = 0

        async def ainvoke(self, payload):
            self.calls += 1
            captured["queries"].append(payload["query"])
            return AIMessage(
                content=json.dumps(
                    {
                        "personalization_summary": "一直只返回不完整命名。",
                        "section_texts": {},
                    },
                    ensure_ascii=False,
                )
            )

    invalid_chain = InvalidChain()

    class InvalidPrompt:
        def __or__(self, _other):
            return invalid_chain

    engine = _seed_published_textbook_sections(
        {
            "sec_1_1": "计算模型用于定义算法可执行的抽象机器与计算过程。",
            "sec_1_2": "复杂度分析用于衡量算法所需的时间、空间与增长阶。",
        },
        tmp_path,
    )
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.commit()

    state = {
        "user_id": "user-1",
        "profile": _complete_profile(),
        "year_learning_paths": {
            "year_3": {
                "current_learning_course": {
                    "grade_id": "year_3",
                    "course_node_id": "year_3_course_1",
                },
                "grade_plans": {
                    "year_3": {
                        "course_nodes": [
                            _course_outline_target(
                                learning_sequence=[],
                            )
                            | {
                                "course_or_chapter_theme": "计算模型与复杂度分析基础",
                                "source_outline_section_ids": [
                                    "sec_1_1",
                                    "sec_1_2",
                                ],
                            },
                        ],
                    },
                },
            },
        },
        "messages": _course_tool_messages("year_3_course_1"),
    }

    module = __import__(
        "app.orchestration.agents.course_knowledge", fromlist=["ChatPromptTemplate"]
    )
    original_factory = module.ChatPromptTemplate

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return InvalidPrompt()

    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(run_course_knowledge_agent(state, RecordingLlm()))
    finally:
        module.ChatPromptTemplate = original_factory

    assert invalid_chain.calls == 1
    assert len(captured["queries"]) == 1
    assert result == {"error": COURSE_KNOWLEDGE_RETRY_ERROR, "hard_error": True}

    with Session(engine) as session:
        row = session.get(UserCourseKnowledgeOutline, ("user-1", "year_3_course_1"))

    assert row is None


def test_run_course_knowledge_agent_returns_hard_error_after_timeout(
    tmp_path: Path,
) -> None:
    class HangingLlm:
        pass

    class HangingChain:
        async def ainvoke(self, _payload):
            await asyncio.sleep(0.1)
            raise AssertionError(
                "timeout fallback should return before the chain finishes"
            )

    class HangingPrompt:
        def __or__(self, _other):
            return HangingChain()

    engine = build_engine(postgresql_test_url(tmp_path, "course-knowledge-timeout"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        _add_default_source_material(session)
        session.commit()

    state = {
        "user_id": "user-1",
        "profile": _complete_profile(),
        "year_learning_paths": {
            "year_3": {
                "current_learning_course": {
                    "grade_id": "year_3",
                    "course_node_id": "year_3_course_1",
                },
                "grade_plans": {
                    "year_3": {
                        "course_nodes": [
                            {
                                **_course_outline_target(learning_sequence=[]),
                            },
                        ],
                    },
                },
            },
        },
        "messages": _course_tool_messages("year_3_course_1"),
    }

    module = __import__(
        "app.orchestration.agents.course_knowledge", fromlist=["ChatPromptTemplate"]
    )
    original_factory = module.ChatPromptTemplate
    original_timeout = module.COURSE_OUTLINE_NAMING_TIMEOUT_SECONDS

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return HangingPrompt()

    module.ChatPromptTemplate = PromptFactory
    module.COURSE_OUTLINE_NAMING_TIMEOUT_SECONDS = 0.01
    try:
        result = asyncio.run(run_course_knowledge_agent(state, HangingLlm()))
    finally:
        module.ChatPromptTemplate = original_factory
        module.COURSE_OUTLINE_NAMING_TIMEOUT_SECONDS = original_timeout

    assert result == {"error": COURSE_KNOWLEDGE_RETRY_ERROR, "hard_error": True}

    with Session(engine) as session:
        row = session.get(UserCourseKnowledgeOutline, ("user-1", "year_3_course_1"))

    assert row is None


def test_run_course_knowledge_agent_normalizes_partial_json_outline(
    tmp_path: Path,
) -> None:
    class RecordingLlm:
        pass

    def partial_outline_payload() -> dict:
        payload = {
            "personalization_summary": "先完成架构设计，再推进联调与部署。",
            "sections": [
                {
                    "section_id": "1",
                    "title": "架构设计",
                    "description": "确认多智能体主流程与状态边界。",
                    "key_knowledge_points": ["LangGraph 编排"],
                },
                {
                    "section_id": "1.1",
                    "parent_section_id": "1",
                    "title": "学习目标",
                    "description": "明确架构设计的章节目标。",
                    "key_knowledge_points": ["状态边界"],
                },
                {
                    "section_id": "1.2",
                    "parent_section_id": "1",
                    "title": "任务拆解",
                    "description": "拆分架构设计的阶段任务。",
                    "key_knowledge_points": ["编排设计"],
                },
                {
                    "section_id": "1.3",
                    "parent_section_id": "1",
                    "title": "检查点",
                    "description": "验证架构设计是否可进入联调。",
                    "key_knowledge_points": ["边界确认"],
                },
                {
                    "section_id": "2",
                    "title": "多智能体联调",
                    "description": "打通事件流、状态流与错误回传。",
                    "key_knowledge_points": ["SSE 流式交互"],
                },
                {
                    "section_id": "2.1",
                    "parent_section_id": "2",
                    "title": "学习目标",
                    "description": "明确联调阶段要达到的能力目标。",
                    "key_knowledge_points": ["错误回传"],
                },
                {
                    "section_id": "2.2",
                    "parent_section_id": "2",
                    "title": "任务拆解",
                    "description": "验证事件流与错误回传。",
                    "key_knowledge_points": ["事件流验证"],
                },
                {
                    "section_id": "2.3",
                    "parent_section_id": "2",
                    "title": "检查点",
                    "description": "确认联调结果可以进入部署阶段。",
                    "key_knowledge_points": ["错误回传"],
                },
            ],
            "learning_sequence": ["1", "2"],
            "total_estimated_hours": 72,
        }
        return _with_section_sources(payload)

    class PartialOutlineChain:
        async def ainvoke(self, payload):
            captured["query"] = payload["query"]
            return AIMessage(
                content=json.dumps(
                    _naming_payload_from_outline(partial_outline_payload()),
                    ensure_ascii=False,
                )
            )

    class PartialOutlinePrompt:
        def __or__(self, _other):
            return PartialOutlineChain()

    captured: dict[str, object] = {}
    engine = build_engine(postgresql_test_url(tmp_path, "course-knowledge-normalize"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        _add_default_source_material(session)
        session.commit()

    module = __import__(
        "app.orchestration.agents.course_knowledge", fromlist=["ChatPromptTemplate"]
    )
    original_factory = module.ChatPromptTemplate

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return PartialOutlinePrompt()

    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_course_knowledge_agent(
                {
                    "user_id": "user-1",
                    "profile": _complete_profile(
                        "【基础学习画像总结】大三软件工程，当前重点是补齐项目练习。"
                    ),
                    "year_learning_paths": {
                        "year_3": {
                            "current_learning_course": {
                                "grade_id": "year_3",
                                "course_node_id": "year_3_course_2",
                            },
                            "grade_plans": {
                                "year_3": {
                                    "course_nodes": [
                                        {
                                            "course_node_id": "year_3_course_1",
                                            "course_or_chapter_theme": "AI Agent 开发基础能力搭建",
                                            "grade_id": "year_3",
                                            "course_goal": "完成最小闭环",
                                            "time_arrangement": {
                                                "semester_scope": "上学期",
                                                "duration": "6 周",
                                                "pace_reason": "围绕平时学习安排",
                                            },
                                            "key_points": ["Prompt 设计", "前后端联调"],
                                            "difficult_points": ["错误处理与重试"],
                                            "learning_sequence": [
                                                "需求拆解",
                                                "接口接入",
                                                "最小闭环演示",
                                            ],
                                            "prerequisite_node_ids": [],
                                            "chapter_nodes": [],
                                            "core_knowledge_points": [],
                                            "knowledge_relations": [],
                                            "downstream_resource_direction_ids": [],
                                            "acceptance_criteria": [
                                                "完成一个可运行的 AI 功能模块并接入 Web 应用"
                                            ],
                                            "source_textbook_id": SOURCE_TEXTBOOK_ID,
                                            "source_textbook_title": (
                                                SOURCE_TEXTBOOK_TITLE
                                            ),
                                            "source_outline_section_ids": (
                                                DEFAULT_SOURCE_SECTION_IDS
                                            ),
                                        },
                                        {
                                            "course_node_id": "year_3_course_2",
                                            "course_or_chapter_theme": "AI Agent 开发项目实战",
                                            "grade_id": "year_3",
                                            "course_goal": "完成真实交互与部署演示",
                                            "time_arrangement": {
                                                "semester_scope": "下学期",
                                                "duration": "8 周",
                                                "pace_reason": "项目实战需要完整联调与部署周期",
                                            },
                                            "key_points": [
                                                "LangGraph 编排",
                                                "SSE 流式交互",
                                                "部署与监控",
                                            ],
                                            "difficult_points": [
                                                "多智能体状态管理",
                                                "线上稳定性",
                                            ],
                                            "learning_sequence": [],
                                            "prerequisite_node_ids": [
                                                "year_3_course_1"
                                            ],
                                            "chapter_nodes": [],
                                            "core_knowledge_points": [],
                                            "knowledge_relations": [],
                                            "downstream_resource_direction_ids": [],
                                            "acceptance_criteria": [
                                                "项目支持真实用户流程与部署演示"
                                            ],
                                            "source_textbook_id": SOURCE_TEXTBOOK_ID,
                                            "source_textbook_title": (
                                                SOURCE_TEXTBOOK_TITLE
                                            ),
                                            "source_outline_section_ids": (
                                                DEFAULT_SOURCE_SECTION_IDS
                                            ),
                                        },
                                    ],
                                },
                            },
                        },
                    },
                    "messages": _course_tool_messages("year_3_course_2"),
                },
                RecordingLlm(),
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    outline = result["course_knowledge"]
    assert captured["query"]
    assert outline["course_id"] == "year_3_course_2"
    assert outline["course_name"] == "AI Agent 开发项目实战"
    assert outline["grade_year"] == "year_3"
    assert outline["total_estimated_hours"] == "12 小时"
    assert outline["sections"][0]["parent_section_id"] is None
    assert outline["sections"][0]["depth"] == 1
    assert outline["sections"][0]["order_index"] == 1
    assert outline["sections"][1]["order_index"] == 2
    assert outline["learning_sequence"] == ["第一章：架构设计", "第二章：多智能体联调"]


def test_run_course_knowledge_agent_uses_llm_even_when_textbook_mapped(
    tmp_path: Path,
) -> None:
    from app.models import Textbook, TextbookSectionContent

    captured: dict[str, object] = {"queries": []}
    source_ids = ["sec_1_1", "sec_1_2"]

    class RecordingLlm:
        pass

    class DesignedOutlineChain:
        async def ainvoke(self, payload):
            captured["queries"].append(payload["query"])
            return AIMessage(
                content=json.dumps(
                    _naming_payload_from_outline(
                        _two_chapter_outline_with_source_ids(source_ids)
                    ),
                    ensure_ascii=False,
                )
            )

    class DesignedOutlinePrompt:
        def __or__(self, _other):
            return DesignedOutlineChain()

    engine = build_engine(postgresql_test_url(tmp_path, "course-knowledge-mapped-llm"))
    set_engine(engine)
    init_db(engine)

    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        outline = {
            "chapters": [
                {
                    "chapter_number": 1,
                    "title": "第一章 AI开发入门",
                    "sections": [
                        {"section_id": "sec_1_1", "title": "1.1 什么是人工智能"},
                        {"section_id": "sec_1_2", "title": "1.2 Python环境配置"},
                    ],
                }
            ]
        }
        tb = Textbook(
            textbook_id="tb-bypass-test",
            source_id="src-1",
            title="AI开发入门教程",
            outline=outline,
            student_availability_status="published",
            outline_review_status="approved",
            ingestion_status="completed",
        )
        session.add(tb)

        sec1 = TextbookSectionContent(
            section_content_id="content_1",
            textbook_id="tb-bypass-test",
            section_id="sec_1_1",
            parent_section_id="1",
            order_index=1,
            title="1.1 什么是人工智能",
            content_zh="人工智能（AI）是计算机科学的一个分支，旨在创造能够模拟人类智能的系统。",
        )
        sec2 = TextbookSectionContent(
            section_content_id="content_2",
            textbook_id="tb-bypass-test",
            section_id="sec_1_2",
            parent_section_id="1",
            order_index=2,
            title="1.2 Python环境配置",
            content_zh="配置Python开发环境是学习AI的第一步，推荐使用Anaconda。",
        )
        session.add(sec1)
        session.add(sec2)
        session.commit()

    state = {
        "user_id": "user-1",
        "profile": _complete_profile(),
        "latest_grade_year": "year_3",
        "year_learning_paths": {
            "year_3": {
                "current_learning_course": {
                    "grade_id": "year_3",
                    "course_node_id": "year_3_course_1",
                },
                "grade_plans": {
                    "year_3": {
                        "course_nodes": [
                            {
                                "course_node_id": "year_3_course_1",
                                "course_or_chapter_theme": "AI开发入门教程",
                                "source_textbook_id": "tb-bypass-test",
                                "source_textbook_title": "AI开发入门教程",
                                "source_outline_section_ids": ["sec_1_1", "sec_1_2"],
                                "grade_id": "year_3",
                                "course_goal": "完成入门学习",
                                "time_arrangement": {
                                    "semester_scope": "上学期",
                                    "duration": "2 周",
                                    "pace_reason": "入门",
                                },
                                "key_points": ["什么是AI"],
                                "difficult_points": ["配置环境"],
                                "learning_sequence": ["什么是AI", "配置环境"],
                                "prerequisite_node_ids": [],
                                "chapter_nodes": [],
                                "core_knowledge_points": [],
                                "knowledge_relations": [],
                                "downstream_resource_direction_ids": [],
                                "acceptance_criteria": ["环境配置成功"],
                            }
                        ],
                    },
                },
            },
        },
        "messages": _course_tool_messages("year_3_course_1"),
    }

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
        result = asyncio.run(run_course_knowledge_agent(state, RecordingLlm()))
    finally:
        module.ChatPromptTemplate = original_factory

    assert len(captured["queries"]) == 1
    assert "source_outline_sections" not in str(captured["queries"][0])
    assert "sec_1_1" not in str(captured["queries"][0])
    assert "sec_1_2" not in str(captured["queries"][0])
    assert "1.1 什么是人工智能" in str(captured["queries"][0])
    assert "error" not in result
    outline_data = result["course_knowledge"]
    assert outline_data["course_id"] == "year_3_course_1"
    assert outline_data["course_name"] == "AI开发入门教程"
    assert len(outline_data["sections"]) == 3

    ch = outline_data["sections"][0]
    assert ch["section_id"] == "1"
    assert ch["depth"] == 1
    assert ch["title"] == "概念定义与学习边界"
    assert ch["parent_section_id"] is None

    s1 = outline_data["sections"][1]
    assert s1["section_id"] == "1.1"
    assert s1["depth"] == 2
    assert s1["title"] == "核心概念辨析"
    assert s1["parent_section_id"] == "1"
    assert s1["source_content_chars"] == len(
        "人工智能（AI）是计算机科学的一个分支，旨在创造能够模拟人类智能的系统。"
    )

    s2 = outline_data["sections"][2]
    assert s2["section_id"] == "1.2"
    assert s2["depth"] == 2
    assert s2["title"] == "使用场景拆解"
    assert s2["parent_section_id"] == "1"
    assert s2["source_content_chars"] == len(
        "配置Python开发环境是学习AI的第一步，推荐使用Anaconda。"
    )


def test_run_course_knowledge_agent_fallback_title_mapping(
    tmp_path: Path,
) -> None:
    from app.models import Textbook, TextbookSectionContent

    captured: dict[str, object] = {"queries": []}

    class RecordingLlm:
        pass

    class DesignedOutlineChain:
        async def ainvoke(self, payload):
            captured["queries"].append(payload["query"])
            return AIMessage(
                content=json.dumps(
                    _naming_payload_from_outline(
                        _two_chapter_outline_with_source_ids(["sec_1_1"])
                    ),
                    ensure_ascii=False,
                )
            )

    class DesignedOutlinePrompt:
        def __or__(self, _other):
            return DesignedOutlineChain()

    engine = build_engine(postgresql_test_url(tmp_path, "course-knowledge-fallback"))
    set_engine(engine)
    init_db(engine)

    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        outline = {
            "chapters": [
                {
                    "chapter_number": 1,
                    "title": "第一章 AI开发入门",
                    "sections": [
                        {"section_id": "sec_1_1", "title": "1.1 什么是人工智能"}
                    ],
                }
            ]
        }
        tb = Textbook(
            textbook_id="tb-bypass-test",
            source_id="src-1",
            title="AI开发入门教程",
            outline=outline,
            student_availability_status="published",
            outline_review_status="approved",
            ingestion_status="completed",
        )
        session.add(tb)

        sec1 = TextbookSectionContent(
            section_content_id="content_1",
            textbook_id="tb-bypass-test",
            section_id="sec_1_1",
            parent_section_id="1",
            order_index=1,
            title="1.1 什么是人工智能",
            content_zh="人工智能（AI）是计算机科学的一个分支，旨在创造能够模拟人类智能的系统。",
        )
        session.add(sec1)
        session.commit()

    state = {
        "user_id": "user-1",
        "profile": _complete_profile(),
        "latest_grade_year": "year_3",
        "year_learning_paths": {
            "year_3": {
                "current_learning_course": {
                    "grade_id": "year_3",
                    "course_node_id": "year_3_course_1",
                },
                "grade_plans": {
                    "year_3": {
                        "course_nodes": [
                            {
                                "course_node_id": "year_3_course_1",
                                "course_or_chapter_theme": "  AI开发入门教程  ",
                                "grade_id": "year_3",
                                "course_goal": "完成入门学习",
                                "time_arrangement": {
                                    "semester_scope": "上学期",
                                    "duration": "2 周",
                                    "pace_reason": "入门",
                                },
                                "key_points": ["什么是AI"],
                                "difficult_points": ["配置环境"],
                                "learning_sequence": ["什么是AI"],
                                "prerequisite_node_ids": [],
                                "chapter_nodes": [],
                                "core_knowledge_points": [],
                                "knowledge_relations": [],
                                "downstream_resource_direction_ids": [],
                                "acceptance_criteria": ["环境配置成功"],
                            }
                        ],
                    },
                },
            },
        },
        "messages": _course_tool_messages("year_3_course_1"),
    }

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
        result = asyncio.run(run_course_knowledge_agent(state, RecordingLlm()))
    finally:
        module.ChatPromptTemplate = original_factory

    assert len(captured["queries"]) == 1
    assert "tb-bypass-test" not in str(captured["queries"][0])
    assert "sec_1_1" not in str(captured["queries"][0])
    assert "1.1 什么是人工智能" in str(captured["queries"][0])
    assert "error" not in result
    outline_data = result["course_knowledge"]
    assert outline_data["course_id"] == "year_3_course_1"
    assert outline_data["course_name"] == "AI开发入门教程"
    assert len(outline_data["sections"]) == 2
    assert outline_data["sections"][0]["title"] == "概念定义与学习边界"
