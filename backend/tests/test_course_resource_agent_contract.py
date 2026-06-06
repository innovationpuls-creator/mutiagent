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


def test_run_section_video_search_agent_retries_transient_failure(tmp_path) -> None:
    class RecordingLlm:
        def with_structured_output(self, schema, *_args, **_kwargs):
            captured["schema"] = schema
            return object()

    class VideoChain:
        async def ainvoke(self, payload):
            captured["queries"].append(payload["query"])
            captured["attempts"] += 1
            if captured["attempts"] == 1:
                raise RuntimeError("临时失败")
            return SectionVideoSearchOutput(
                section_id="1.1",
                query="AI 应用开发 学习目标 视频教程",
                videos=[
                    {
                        "title": "重试后的视频",
                        "url": "https://example.com/retried-video",
                        "cover_url": "https://example.com/cover.png",
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
    captured = {"schema": None, "queries": [], "attempts": 0}
    engine = build_engine(f"sqlite:///{tmp_path / 'section-video-retry.db'}")
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
    assert captured["attempts"] == 2
    videos = result["course_knowledge"]["section_video_links"]["1.1"]["videos"]
    assert videos[0]["url"] == "https://example.com/retried-video"


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


from app.orchestration.agents.course_resources import (
    _compose_section_content,
    _extract_brief_ids_from_markdown,
    _run_with_retries,
)


def test_extract_brief_ids_from_markdown_reads_video_and_animation_ids() -> None:
    markdown = "\n".join([
        "# 学习目标",
        "<!-- video:id=video_1 -->",
        "正文继续。",
        "<!-- animation:id=anim_1 -->",
    ])

    assert _extract_brief_ids_from_markdown(markdown, "video") == ["video_1"]
    assert _extract_brief_ids_from_markdown(markdown, "animation") == ["anim_1"]


def test_compose_section_content_replaces_video_and_animation_placeholders() -> None:
    section_markdown = {
        "section_id": "1.1",
        "parent_section_id": "1",
        "title": "学习目标",
        "markdown": "# 学习目标\n\n<!-- video:id=video_1 -->\n\n<!-- animation:id=anim_1 -->",
        "video_briefs": [
            {
                "video_id": "video_1",
                "title": "学习目标导入",
                "purpose": "用 5 分钟帮助用户建立直觉",
            }
        ],
        "animation_briefs": [
            {
                "animation_id": "anim_1",
                "title": "目标收敛动画",
                "concept": "展示目标如何收敛为验收标准",
                "visual_elements": ["目标卡片", "验收卡片"],
                "motion": "目标卡片从左向右滑入并与验收卡片连接",
                "space": "正文宽度的 100%，高度 320px",
                "placement_hint": "学习目标之后",
            }
        ],
    }
    video_links = {
        "videos": [
            {
                "brief_id": "video_1",
                "title": "学习目标导入",
                "url": "https://example.com/video",
                "cover_url": "https://example.com/cover.png",
                "cover_status": "provided",
                "source": "example.com",
            }
        ]
    }
    animations = {
        "animations": [
            {
                "brief_id": "anim_1",
                "animation_id": "anim_1",
                "title": "目标收敛动画",
                "html": "<section class=\"section-animation\"></section>",
            }
        ]
    }

    composed = _compose_section_content(section_markdown, video_links, animations)

    assert composed["section_id"] == "1.1"
    assert composed["blocks"][0]["type"] == "markdown"
    assert composed["blocks"][1]["type"] == "video"
    assert composed["blocks"][1]["status"] == "available"
    assert composed["blocks"][2]["type"] == "animation"
    assert composed["blocks"][2]["status"] == "available"


def test_compose_section_content_downgrades_missing_video_and_animation() -> None:
    section_markdown = {
        "section_id": "1.1",
        "parent_section_id": "1",
        "title": "学习目标",
        "markdown": "# 学习目标\n\n<!-- video:id=video_1 -->\n\n<!-- animation:id=anim_1 -->",
        "video_briefs": [{"video_id": "video_1", "title": "学习目标导入", "purpose": "建立直觉"}],
        "animation_briefs": [
            {
                "animation_id": "anim_1",
                "title": "目标动画",
                "concept": "目标收敛",
                "visual_elements": ["目标卡片"],
                "motion": "淡入",
                "space": "高度 320px",
                "placement_hint": "正文中段",
            }
        ],
    }

    composed = _compose_section_content(section_markdown, {"videos": []}, {"animations": []})

    assert composed["blocks"][1]["type"] == "video"
    assert composed["blocks"][1]["status"] == "unavailable"
    assert composed["blocks"][2]["type"] == "animation"
    assert composed["blocks"][2]["status"] == "unavailable"


def test_run_with_retries_retries_three_times_then_returns_fallback() -> None:
    attempts = {"count": 0}

    async def failing_action():
        attempts["count"] += 1
        raise RuntimeError("生成失败")

    result = asyncio.run(_run_with_retries(failing_action, fallback={"ok": False}, attempts=3))

    assert attempts["count"] == 3
    assert result == {"ok": False}


def test_stream_chapter_resource_generation_stops_when_video_step_fails() -> None:
    import app.orchestration.agents.course_resources as module

    calls = {"animation": 0}
    outline = _outline()

    async def markdown_agent(state, _llm, explicit_args=None):
        return {
            "course_knowledge": outline,
            "course_resource_plan": {
                "course_id": "year_3_course_1",
                "target_section_ids": ["1.1", "1.2", "1.3"],
                "markdown_section_ids": ["1.1", "1.2", "1.3"],
                "video_section_ids": [],
                "animation_section_ids": [],
            },
        }

    async def video_agent(state, _search_llm, explicit_args=None):
        return {"error": "视频资源生成失败，请稍后重试。", "hard_error": True}

    async def animation_agent(state, _llm, explicit_args=None):
        calls["animation"] += 1
        return {"course_knowledge": state["course_knowledge"]}

    original_markdown_agent = module.run_section_markdown_agent
    original_video_agent = module.run_section_video_search_agent
    original_animation_agent = module.run_section_html_animation_agent
    module.run_section_markdown_agent = markdown_agent
    module.run_section_video_search_agent = video_agent
    module.run_section_html_animation_agent = animation_agent
    try:
        async def collect_events():
            return [
                event
                async for event in module.stream_chapter_resource_generation(
                    {
                        "user_id": "user-1",
                        "session_id": "session-1",
                        "course_knowledge": outline,
                        "profile": {},
                        "year_learning_paths": {},
                    },
                    object(),
                    object(),
                    course_id="year_3_course_1",
                    chapter_section_id="1",
                )
            ]

        events = asyncio.run(collect_events())
    finally:
        module.run_section_markdown_agent = original_markdown_agent
        module.run_section_video_search_agent = original_video_agent
        module.run_section_html_animation_agent = original_animation_agent

    assert calls["animation"] == 0
    assert events[-1] == {
        "event": "error",
        "message": "视频资源生成失败，请稍后重试。",
        "recoverable": True,
    }
    assert not any(event["event"] == "message_completed" for event in events)
    assert not any(event["event"] == "session_completed" for event in events)
