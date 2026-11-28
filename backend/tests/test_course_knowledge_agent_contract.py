"""Contract tests for the course knowledge agent."""

# ruff: noqa: E501

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from sqlmodel import Session

from app.database import build_engine, init_db, set_engine
from app.models import User
from app.orchestration.agents.course_knowledge import (
    _select_course_for_outline,
)
from app.orchestration.agents.models import (
    SectionItem,
)
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
    init_db(engine, seed_users=False)
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
    init_db(engine, seed_users=False)
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


def test_upsert_outline_clears_section_generated_assets_when_outline_changes(
    tmp_path: Path,
) -> None:
    engine = build_engine(postgresql_test_url(tmp_path, "course-knowledge-upsert"))
    set_engine(engine)
    init_db(engine, seed_users=False)
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
    init_db(engine, seed_users=False)
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
