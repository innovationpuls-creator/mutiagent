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
    _SINGLE_COURSE_JSON_CONTRACT,
    _YEAR_COURSES_JSON_CONTRACT,
    ALL_CURRENT_GRADE_COURSES_ID,
    COURSE_KNOWLEDGE_RETRY_ERROR,
    _build_analysis_input,
    _build_repair_input,
    _build_year_analysis_input,
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
        ],
        "learning_sequence": ["1"],
        "total_estimated_hours": "12 小时",
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
            ]
        )


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
    for contract in (_SINGLE_COURSE_JSON_CONTRACT, _YEAR_COURSES_JSON_CONTRACT):
        assert '"source_textbook_id"' in contract
        assert '"source_textbook_title"' in contract
        assert '"source_section_ids"' in contract
        assert '"source_section_titles"' in contract
        assert '"source_content_chars"' in contract


def test_course_knowledge_repair_input_requires_section_source_fields() -> None:
    repair_input = _build_repair_input(
        "原始输入", "source_textbook_id must not be empty"
    )

    assert "source_textbook_id" in repair_input
    assert "source_textbook_title" in repair_input
    assert "source_section_ids" in repair_input
    assert "source_section_titles" in repair_input
    assert "source_content_chars" in repair_input
    assert "这些绑定教材小节" in repair_input


def test_normalize_generated_sections_rejects_empty_source_fields() -> None:
    outline = _with_section_sources(
        {
            "sections": [
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
                    "section_id": "1.1",
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
            ]
        }
    )
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
                content=json.dumps(designed_outline_payload(), ensure_ascii=False)
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
    assert "同年级课程顺序" in str(captured["query"])
    assert "JSON Schema" not in str(captured["query"])
    assert "learning_sequence" in str(captured["query"])
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

    def year_outline_payload() -> dict:
        return {
            "grade_year": "year_3",
            "year_summary": "全年按 AI 应用到 RAG 实战的顺序生成大纲。",
            "course_outlines": [
                outline_payload("year_3_course_1", "AI 应用核心架构"),
                outline_payload("year_3_course_2", "RAG 实战"),
            ],
        }

    class YearOutlineChain:
        def __init__(self):
            self.calls = 0

        async def ainvoke(self, payload):
            self.calls += 1
            captured["queries"].append(payload["query"])
            return AIMessage(
                content=f"```json\n{json.dumps(year_outline_payload(), ensure_ascii=False)}\n```"
            )

    year_chain = YearOutlineChain()

    class YearOutlinePrompt:
        def __or__(self, _other):
            return year_chain

    engine = build_engine(
        postgresql_test_url(tmp_path, "course-knowledge-year-batch")
    )
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
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
    assert year_chain.calls == 1
    assert captured["timeouts"] == [module.YEAR_COURSE_OUTLINE_TIMEOUT_SECONDS]
    assert "请一次性为当前年级的全部课程生成详细章节大纲" in captured["queries"][0]
    assert "JSON Schema" not in captured["queries"][0]
    assert "course_outlines" in captured["queries"][0]
    assert "AI 应用核心架构" in captured["queries"][0]
    assert "RAG 实战" in captured["queries"][0]
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
            outline = _with_section_sources(
                {
                    "personalization_summary": "按当前课程生成单门章节大纲。",
                    "sections": [
                        {
                            "section_id": "1",
                            "parent_section_id": None,
                            "depth": 1,
                            "title": "架构入口",
                            "order_index": 1,
                            "description": "建立课程主线。",
                            "key_knowledge_points": ["架构边界", "目标验收"],
                        },
                        {
                            "section_id": "1.1",
                            "parent_section_id": "1",
                            "depth": 2,
                            "title": "目标边界",
                            "order_index": 2,
                            "description": "确认输入输出。",
                            "key_knowledge_points": ["输入输出"],
                        },
                        {
                            "section_id": "1.2",
                            "parent_section_id": "1",
                            "depth": 2,
                            "title": "验收方式",
                            "order_index": 3,
                            "description": "定义可验证结果。",
                            "key_knowledge_points": ["验收标准"],
                        },
                        {
                            "section_id": "1.3",
                            "parent_section_id": "1",
                            "depth": 2,
                            "title": "验收证据",
                            "order_index": 4,
                            "description": "设计验收证据和示例。",
                            "key_knowledge_points": ["验收证据要点"],
                        },
                    ],
                    "learning_sequence": ["1"],
                    "total_estimated_hours": "8 小时",
                }
            )
            return AIMessage(content=json.dumps(outline, ensure_ascii=False))

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
    assert captured["timeouts"] == [module.SINGLE_COURSE_OUTLINE_TIMEOUT_SECONDS]
    assert "请为以下课程生成详细的章节大纲" in captured["queries"][0]
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


def test_run_course_knowledge_agent_repairs_invalid_json_outline_once(
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {"queries": []}

    class RecordingLlm:
        pass

    def invalid_outline_payload() -> dict:
        return {
            "personalization_summary": "先从 RAG 主链路入手。",
            "sections": [
                {
                    "section_id": "1",
                    "parent_section_id": None,
                    "depth": 1,
                    "title": "RAG 主链路",
                    "order_index": 1,
                    "description": "只返回了一级章节，缺少二级小节。",
                    "key_knowledge_points": ["检索增强生成"],
                },
            ],
            "learning_sequence": ["1"],
            "total_estimated_hours": "12 小时",
        }

    def repaired_outline_payload() -> dict:
        payload = {
            "personalization_summary": "按项目驱动画像先理解 RAG 架构，再完成检索链路验收。",
            "sections": [
                {
                    "section_id": "1",
                    "parent_section_id": None,
                    "depth": 1,
                    "title": "AI 应用核心架构",
                    "order_index": 1,
                    "description": "建立 AI 应用从输入到输出的核心分层。",
                    "key_knowledge_points": ["应用分层", "模型调用边界"],
                },
                {
                    "section_id": "1.1",
                    "parent_section_id": "1",
                    "depth": 2,
                    "title": "请求入口与状态边界",
                    "order_index": 2,
                    "description": "确认用户输入、会话状态和模型调用之间的边界。",
                    "key_knowledge_points": ["输入契约", "状态隔离"],
                },
                {
                    "section_id": "1.2",
                    "parent_section_id": "1",
                    "depth": 2,
                    "title": "模型调用与错误回传",
                    "order_index": 3,
                    "description": "设计可恢复的模型调用与错误提示。",
                    "key_knowledge_points": ["调用超时", "错误提示"],
                },
                {
                    "section_id": "1.3",
                    "parent_section_id": "1",
                    "depth": 2,
                    "title": "测试调试方法",
                    "order_index": 4,
                    "description": "说明如何进行调试测试。",
                    "key_knowledge_points": ["调试技巧"],
                },
                {
                    "section_id": "2",
                    "parent_section_id": None,
                    "depth": 1,
                    "title": "RAG 检索增强实战",
                    "order_index": 5,
                    "description": "完成从文档切分到答案引用的 RAG 主链路。",
                    "key_knowledge_points": ["向量检索", "引用归因"],
                },
                {
                    "section_id": "2.1",
                    "parent_section_id": "2",
                    "depth": 2,
                    "title": "知识切分与向量化",
                    "order_index": 6,
                    "description": "把课程资料处理成可检索的知识片段。",
                    "key_knowledge_points": ["chunk 设计", "embedding 生成"],
                },
                {
                    "section_id": "2.2",
                    "parent_section_id": "2",
                    "depth": 2,
                    "title": "检索召回与答案验收",
                    "order_index": 7,
                    "description": "验证检索结果是否真正支撑最终回答。",
                    "key_knowledge_points": ["top_k 召回", "答案证据"],
                },
                {
                    "section_id": "2.3",
                    "parent_section_id": "2",
                    "depth": 2,
                    "title": "系统评估与优化",
                    "order_index": 8,
                    "description": "分析并优化检索系统的整体准确度。",
                    "key_knowledge_points": ["系统评估"],
                },
            ],
            "learning_sequence": ["1", "2"],
            "total_estimated_hours": "20 小时",
        }
        return _with_section_sources(payload)

    class RepairingChain:
        def __init__(self):
            self.calls = 0

        async def ainvoke(self, payload):
            self.calls += 1
            captured["queries"].append(payload["query"])
            if self.calls == 1:
                return AIMessage(
                    content=json.dumps(invalid_outline_payload(), ensure_ascii=False)
                )
            return AIMessage(
                content=json.dumps(repaired_outline_payload(), ensure_ascii=False)
            )

    repairing_chain = RepairingChain()

    class RepairingPrompt:
        def __or__(self, _other):
            return repairing_chain

    engine = build_engine(postgresql_test_url(tmp_path, "course-knowledge-repair"))
    set_engine(engine)
    init_db(engine)
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
                            {
                                **_course_outline_target(learning_sequence=[]),
                                "course_or_chapter_theme": "AI应用核心架构与RAG实战",
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
            return RepairingPrompt()

    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(run_course_knowledge_agent(state, RecordingLlm()))
    finally:
        module.ChatPromptTemplate = original_factory

    assert not hasattr(RecordingLlm(), "with_structured_output")
    assert repairing_chain.calls == 2
    assert "JSON Schema" not in captured["queries"][0]
    assert "sections" in captured["queries"][0]
    assert "上一次输出没有通过课程大纲结构校验" in captured["queries"][1]
    assert "课程大纲必须包含章内小节" in captured["queries"][1]
    assert result["course_knowledge"]["course_name"] == "AI应用核心架构与RAG实战"
    assert result["course_knowledge"]["learning_sequence"] == [
        "第一章：AI 应用核心架构",
        "第二章：RAG 检索增强实战",
    ]

    with Session(engine) as session:
        row = session.get(UserCourseKnowledgeOutline, ("user-1", "year_3_course_1"))

    assert row is not None
    assert row.outline_data["sections"][1]["section_id"] == "1.1"


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
    original_timeout = module.SINGLE_COURSE_OUTLINE_TIMEOUT_SECONDS

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return HangingPrompt()

    module.ChatPromptTemplate = PromptFactory
    module.SINGLE_COURSE_OUTLINE_TIMEOUT_SECONDS = 0.01
    try:
        result = asyncio.run(run_course_knowledge_agent(state, HangingLlm()))
    finally:
        module.ChatPromptTemplate = original_factory
        module.SINGLE_COURSE_OUTLINE_TIMEOUT_SECONDS = original_timeout

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
                content=json.dumps(partial_outline_payload(), ensure_ascii=False)
            )

    class PartialOutlinePrompt:
        def __or__(self, _other):
            return PartialOutlineChain()

    captured: dict[str, object] = {}
    engine = build_engine(
        postgresql_test_url(tmp_path, "course-knowledge-normalize")
    )
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
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
    assert outline["total_estimated_hours"] == "72 小时"
    assert outline["sections"][0]["parent_section_id"] is None
    assert outline["sections"][0]["depth"] == 1
    assert outline["sections"][0]["order_index"] == 1
    assert outline["sections"][1]["order_index"] == 2
    assert outline["learning_sequence"] == ["第一章：架构设计", "第二章：多智能体联调"]


def test_run_course_knowledge_agent_bypasses_llm_if_textbook_mapped(
    tmp_path: Path,
) -> None:
    from app.models import Textbook, TextbookSectionContent

    engine = build_engine(
        postgresql_test_url(tmp_path, "course-knowledge-bypass-llm")
    )
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

    class ExplodingLlm:
        async def ainvoke(self, *args, **kwargs):
            raise AssertionError(
                "LLM should not be called when textbook outline is translated from DB directly!"
            )

    result = asyncio.run(run_course_knowledge_agent(state, ExplodingLlm()))

    assert "error" not in result
    outline_data = result["course_knowledge"]
    assert outline_data["course_id"] == "year_3_course_1"
    assert outline_data["course_name"] == "AI开发入门教程"
    assert len(outline_data["sections"]) == 3

    ch = outline_data["sections"][0]
    assert ch["section_id"] == "1"
    assert ch["depth"] == 1
    assert ch["title"] == "第一章 AI开发入门"
    assert ch["parent_section_id"] is None

    s1 = outline_data["sections"][1]
    assert s1["section_id"] == "sec_1_1"
    assert s1["depth"] == 2
    assert s1["title"] == "1.1 什么是人工智能"
    assert s1["parent_section_id"] == "1"
    assert s1["source_content_chars"] == len(
        "人工智能（AI）是计算机科学的一个分支，旨在创造能够模拟人类智能的系统。"
    )

    s2 = outline_data["sections"][2]
    assert s2["section_id"] == "sec_1_2"
    assert s2["depth"] == 2
    assert s2["title"] == "1.2 Python环境配置"
    assert s2["parent_section_id"] == "1"
    assert s2["source_content_chars"] == len(
        "配置Python开发环境是学习AI的第一步，推荐使用Anaconda。"
    )


def test_run_course_knowledge_agent_fallback_title_mapping(
    tmp_path: Path,
) -> None:
    from app.models import Textbook, TextbookSectionContent

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

    class ExplodingLlm:
        async def ainvoke(self, *args, **kwargs):
            raise AssertionError(
                "LLM should not be called when textbook outline is translated from DB directly!"
            )

    result = asyncio.run(run_course_knowledge_agent(state, ExplodingLlm()))

    assert "error" not in result
    outline_data = result["course_knowledge"]
    assert outline_data["course_id"] == "year_3_course_1"
    assert outline_data["course_name"] == "  AI开发入门教程  "
    assert len(outline_data["sections"]) == 2
