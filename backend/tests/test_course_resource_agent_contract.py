from __future__ import annotations

from datetime import datetime

from app.orchestration.agents.course_resources import (
    _fallback_cover_data_url,
    _merge_course_resource_data,
    _target_sections_for_scope,
)


def _outline() -> dict:
    return {
        "course_id": "year_3_course_1",
        "course_name": "AI 应用开发",
        "grade_year": "year_3",
        "personalization_summary": "先完成需求拆解，再进入接口接入。",
        "sections": [
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
                "order_index": 2,
                "description": "明确本节学习目标。",
                "key_knowledge_points": ["功能边界"],
            },
            {
                "section_id": "1.2",
                "parent_section_id": "1",
                "depth": 2,
                "title": "任务拆解",
                "order_index": 3,
                "description": "把目标拆成任务。",
                "key_knowledge_points": ["任务拆分"],
            },
            {
                "section_id": "1.3",
                "parent_section_id": "1",
                "depth": 2,
                "title": "检查点",
                "order_index": 4,
                "description": "确认完成标准。",
                "key_knowledge_points": ["验收标准"],
            },
            {
                "section_id": "2",
                "parent_section_id": None,
                "depth": 1,
                "title": "接口接入",
                "order_index": 5,
                "description": "接入 LLM API。",
                "key_knowledge_points": ["API 调用"],
            },
            {
                "section_id": "2.1",
                "parent_section_id": "2",
                "depth": 2,
                "title": "学习目标",
                "order_index": 6,
                "description": "掌握接口接入目标。",
                "key_knowledge_points": ["API 调用"],
            },
        ],
        "learning_sequence": ["第一章：需求拆解", "第二章：接口接入"],
        "total_estimated_hours": "8 小时",
    }


def test_target_sections_for_chapter_scope_expands_child_sections() -> None:
    targets = _target_sections_for_scope(_outline(), "1", "chapter_sections")

    assert [section["section_id"] for section in targets] == ["1.1", "1.2", "1.3"]


def test_target_sections_default_first_chapter_uses_child_sections_not_parent() -> None:
    targets = _target_sections_for_scope(_outline(), "", "default_first_chapter")

    assert [section["section_id"] for section in targets] == ["1.1", "1.2", "1.3"]


def test_target_sections_course_scope_uses_all_non_root_sections() -> None:
    targets = _target_sections_for_scope(_outline(), "", "course_sections")

    assert [section["section_id"] for section in targets] == ["1.1", "1.2", "1.3", "2.1"]


def test_merge_course_resource_data_preserves_outline_fields() -> None:
    outline = _outline()
    merged = _merge_course_resource_data(
        outline,
        "section_markdowns",
        {
            "1.1": {
                "section_id": "1.1",
                "parent_section_id": "1",
                "title": "学习目标",
                "markdown": "# 学习目标",
                "animation_briefs": [],
                "generated_at": "2026-06-06T00:00:00Z",
            }
        },
    )

    assert merged["course_id"] == "year_3_course_1"
    assert merged["sections"] == outline["sections"]
    assert merged["section_markdowns"]["1.1"]["markdown"] == "# 学习目标"


def test_fallback_cover_data_url_is_stable_svg_data_url() -> None:
    value = _fallback_cover_data_url("学习目标")

    assert value.startswith("data:image/svg+xml;utf8,")
    assert "学习目标" in value


import asyncio

from sqlmodel import Session

from app.database import build_engine, init_db, set_engine
from app.models import User, UserCourseKnowledgeOutline
from app.orchestration.agents.course_resources import run_section_markdown_agent
from app.orchestration.agents.models import SectionMarkdownOutput


def test_run_section_markdown_agent_writes_each_first_chapter_child_section(tmp_path) -> None:
    class RecordingLlm:
        def with_structured_output(self, schema, *_args, **_kwargs):
            captured["schema"] = schema
            return object()

    class MarkdownChain:
        async def ainvoke(self, payload):
            captured["queries"].append(payload["query"])
            section_id = "1.1" if "学习目标" in payload["query"] else "1.2" if "任务拆解" in payload["query"] else "1.3"
            title = "学习目标" if section_id == "1.1" else "任务拆解" if section_id == "1.2" else "检查点"
            return SectionMarkdownOutput(
                section_id=section_id,
                parent_section_id="1",
                title=title,
                markdown=f"# {title}\n\n完整教学内容",
                animation_briefs=[],
            )

    class MarkdownPrompt:
        def __or__(self, _other):
            return MarkdownChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return MarkdownPrompt()

    captured = {"schema": None, "queries": []}
    engine = build_engine(f"sqlite:///{tmp_path / 'section-markdown.db'}")
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(User(uid="user-1", username="课程用户", identifier="course@example.com"))
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=_outline(),
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module
    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_section_markdown_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": _outline(),
                    "messages": [],
                },
                RecordingLlm(),
                {"course_id": "year_3_course_1", "section_id": "1", "scope": "chapter_sections"},
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert captured["schema"] is SectionMarkdownOutput
    assert len(captured["queries"]) == 3
    assert result["course_resource_plan"]["target_section_ids"] == ["1.1", "1.2", "1.3"]
    assert set(result["course_knowledge"]["section_markdowns"]) == {"1.1", "1.2", "1.3"}
    assert "1" not in result["course_knowledge"]["section_markdowns"]
    with Session(engine) as session:
        row = session.get(UserCourseKnowledgeOutline, ("user-1", "year_3_course_1"))
    assert row is not None
    assert set(row.outline_data["section_markdowns"]) == {"1.1", "1.2", "1.3"}


from app.orchestration.agents.course_resources import run_section_video_search_agent
from app.orchestration.agents.models import SectionVideoSearchOutput


def test_run_section_video_search_agent_writes_url_and_fallback_cover(tmp_path) -> None:
    class RecordingLlm:
        def with_structured_output(self, schema, *_args, **_kwargs):
            captured["schema"] = schema
            return object()

    class VideoChain:
        async def ainvoke(self, payload):
            captured["queries"].append(payload["query"])
            return SectionVideoSearchOutput(
                section_id="1.1",
                query="AI 应用开发 学习目标 视频教程",
                videos=[
                    {
                        "title": "学习目标视频",
                        "url": "https://example.com/video",
                        "cover_url": "",
                        "source": "example.com",
                    }
                ],
            )

    class VideoPrompt:
        def __or__(self, _other):
            return VideoChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return VideoPrompt()

    outline = _outline()
    outline["section_markdowns"] = {
        "1.1": {
            "section_id": "1.1",
            "parent_section_id": "1",
            "title": "学习目标",
            "markdown": "# 学习目标\n\n完整教学内容",
            "animation_briefs": [],
            "generated_at": "2026-06-06T00:00:00Z",
        }
    }
    captured = {"schema": None, "queries": []}
    engine = build_engine(f"sqlite:///{tmp_path / 'section-video.db'}")
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(User(uid="user-1", username="课程用户", identifier="course@example.com"))
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=outline,
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module
    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_section_video_search_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": outline,
                    "course_resource_plan": {
                        "course_id": "year_3_course_1",
                        "target_section_ids": ["1.1"],
                    },
                    "messages": [],
                },
                RecordingLlm(),
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert captured["schema"] is SectionVideoSearchOutput
    videos = result["course_knowledge"]["section_video_links"]["1.1"]["videos"]
    assert videos[0]["url"] == "https://example.com/video"
    assert videos[0]["cover_status"] == "fallback"
    assert videos[0]["cover_url"].startswith("data:image/svg+xml;utf8,")


from app.orchestration.agents.course_resources import run_section_html_animation_agent
from app.orchestration.agents.models import SectionHtmlAnimationOutput


def test_run_section_html_animation_agent_uses_animation_briefs(tmp_path) -> None:
    class RecordingLlm:
        def with_structured_output(self, schema, *_args, **_kwargs):
            captured["schema"] = schema
            return object()

    class AnimationChain:
        async def ainvoke(self, payload):
            captured["queries"].append(payload["query"])
            return SectionHtmlAnimationOutput(
                section_id="1.1",
                animations=[
                    {
                        "animation_id": "section-1-1-animation-1",
                        "title": "目标到验收标准",
                        "html": "<section class=\"section-animation\" data-animation-id=\"section-1-1-animation-1\"></section>",
                    }
                ],
            )

    class AnimationPrompt:
        def __or__(self, _other):
            return AnimationChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return AnimationPrompt()

    outline = _outline()
    outline["section_markdowns"] = {
        "1.1": {
            "section_id": "1.1",
            "parent_section_id": "1",
            "title": "学习目标",
            "markdown": "# 学习目标\n\n完整教学内容",
            "animation_briefs": [
                {
                    "animation_id": "section-1-1-animation-1",
                    "title": "目标到验收标准",
                    "concept": "展示学习目标如何收敛为验收标准",
                    "placement_hint": "核心概念之后",
                }
            ],
            "generated_at": "2026-06-06T00:00:00Z",
        }
    }
    captured = {"schema": None, "queries": []}
    engine = build_engine(f"sqlite:///{tmp_path / 'section-animation.db'}")
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(User(uid="user-1", username="课程用户", identifier="course@example.com"))
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=outline,
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module
    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_section_html_animation_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": outline,
                    "course_resource_plan": {
                        "course_id": "year_3_course_1",
                        "target_section_ids": ["1.1"],
                    },
                    "messages": [],
                },
                RecordingLlm(),
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert captured["schema"] is SectionHtmlAnimationOutput
    animations = result["course_knowledge"]["section_html_animations"]["1.1"]["animations"]
    assert animations[0]["animation_id"] == "section-1-1-animation-1"
    assert "section-animation" in animations[0]["html"]
    assert result["course_resource_result"]["markdown_count"] == 1
    assert result["response"].startswith("《AI 应用开发》的 1.1 教学内容已生成")
