# ruff: noqa: C901, E501
from __future__ import annotations

import json
import logging
from typing import AsyncGenerator

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage

from app.orchestration.agents.course_resources.animation import (
    run_section_html_animation_agent,
)
from app.orchestration.agents.course_resources.common import (
    _chapter_resource_error_event,
    _clean_text,
    _target_sections_for_scope,
)
from app.orchestration.agents.course_resources.markdown import (
    run_section_markdown_agent,
)
from app.orchestration.agents.course_resources.video import (
    run_section_video_search_agent,
)
from app.orchestration.agents.utils import extract_last_tool_call_id
from app.orchestration.contracts import quality_passed
from app.orchestration.events import build_agent_event
from app.orchestration.observability import build_trace
from app.orchestration.recovery import update_section_phase_checkpoint
from app.orchestration.state import OrchestrationState

logger = logging.getLogger(__name__)


def _section_input_refs(
    *, course_id: str, chapter_section_id: str, section: dict
) -> dict[str, object]:
    return {
        "course_id": course_id,
        "chapter_section_id": chapter_section_id,
        "section_id": _clean_text(section.get("section_id")),
        "source_textbook_id": _clean_text(section.get("source_textbook_id")),
        "source_section_ids": section.get("source_section_ids")
        if isinstance(section.get("source_section_ids"), list)
        else [],
    }


def _section_markdown_output_refs(outline: dict, section_id: str) -> dict[str, object]:
    section_markdowns = outline.get("section_markdowns")
    value = (
        section_markdowns.get(section_id) if isinstance(section_markdowns, dict) else {}
    )
    markdown_value = value if isinstance(value, dict) else {}
    video_briefs = markdown_value.get("video_briefs")
    animation_briefs = markdown_value.get("animation_briefs")
    source_references = markdown_value.get("source_references")
    return {
        "section_markdown_id": section_id,
        "source_reference_count": len(source_references)
        if isinstance(source_references, list)
        else 0,
        "video_brief_ids": [
            _clean_text(brief.get("video_id"))
            for brief in video_briefs
            if isinstance(brief, dict) and _clean_text(brief.get("video_id"))
        ]
        if isinstance(video_briefs, list)
        else [],
        "animation_brief_ids": [
            _clean_text(brief.get("animation_id"))
            for brief in animation_briefs
            if isinstance(brief, dict) and _clean_text(brief.get("animation_id"))
        ]
        if isinstance(animation_briefs, list)
        else [],
    }


def _section_video_output_refs(outline: dict, section_id: str) -> dict[str, object]:
    section_video_links = outline.get("section_video_links")
    value = (
        section_video_links.get(section_id)
        if isinstance(section_video_links, dict)
        else {}
    )
    video_value = value if isinstance(value, dict) else {}
    videos = video_value.get("videos")
    unavailable = video_value.get("unavailable_videos")
    return {
        "section_video_id": section_id,
        "available_video_count": len(videos) if isinstance(videos, list) else 0,
        "unavailable_video_count": len(unavailable)
        if isinstance(unavailable, list)
        else 0,
    }


def _section_animation_output_refs(outline: dict, section_id: str) -> dict[str, object]:
    section_html_animations = outline.get("section_html_animations")
    value = (
        section_html_animations.get(section_id)
        if isinstance(section_html_animations, dict)
        else {}
    )
    animation_value = value if isinstance(value, dict) else {}
    animations = animation_value.get("animations")
    return {
        "section_animation_id": section_id,
        "animation_count": len(animations) if isinstance(animations, list) else 0,
    }


def _section_compose_output_refs(outline: dict, section_id: str) -> dict[str, object]:
    section_composed_markdowns = outline.get("section_composed_markdowns")
    value = (
        section_composed_markdowns.get(section_id)
        if isinstance(section_composed_markdowns, dict)
        else {}
    )
    composed_value = value if isinstance(value, dict) else {}
    blocks = composed_value.get("blocks")
    source_references = composed_value.get("source_references")
    return {
        "section_composed_markdown_id": section_id,
        "block_count": len(blocks) if isinstance(blocks, list) else 0,
        "source_reference_count": len(source_references)
        if isinstance(source_references, list)
        else 0,
    }


def _record_section_checkpoint(
    state: OrchestrationState,
    *,
    section_id: str,
    phase: str,
    status: str,
    output_refs: dict[str, object],
) -> None:
    outline = state.get("course_knowledge")
    if not isinstance(outline, dict):
        return
    state["course_knowledge"] = update_section_phase_checkpoint(
        outline,
        section_id=section_id,
        phase=phase,
        status=status,
        output_refs=output_refs,
        quality_result=quality_passed().to_dict(),
    )


def create_section_markdown_agent_node(llm: BaseChatModel):
    async def section_markdown_node(state: OrchestrationState) -> dict:
        agent_result = await run_section_markdown_agent(state, llm)

        tool_call_id = extract_last_tool_call_id(state)
        tool_message = ToolMessage(
            content=json.dumps(agent_result, ensure_ascii=False),
            tool_call_id=tool_call_id or "unknown",
        )

        result = {"messages": [tool_message]}
        if agent_result.get("course_knowledge") is not None:
            result["course_knowledge"] = agent_result["course_knowledge"]
        if agent_result.get("course_resource_plan") is not None:
            result["course_resource_plan"] = agent_result["course_resource_plan"]
        if agent_result.get("response") is not None:
            result["response"] = agent_result["response"]
        if agent_result.get("error") is not None:
            result["response"] = agent_result["error"]
        return result

    return section_markdown_node


def create_section_video_search_agent_node(llm: BaseChatModel):
    async def section_video_search_node(state: OrchestrationState) -> dict:
        agent_result = await run_section_video_search_agent(state, llm)

        tool_call_id = extract_last_tool_call_id(state)
        tool_message = ToolMessage(
            content=json.dumps(agent_result, ensure_ascii=False),
            tool_call_id=tool_call_id or "unknown",
        )

        result = {"messages": [tool_message]}
        if agent_result.get("course_knowledge") is not None:
            result["course_knowledge"] = agent_result["course_knowledge"]
        if agent_result.get("course_resource_plan") is not None:
            result["course_resource_plan"] = agent_result["course_resource_plan"]
        if agent_result.get("response") is not None:
            result["response"] = agent_result["response"]
        if agent_result.get("error") is not None:
            result["response"] = agent_result["error"]
        return result

    return section_video_search_node


def create_section_html_animation_agent_node(llm: BaseChatModel):
    async def section_html_animation_node(state: OrchestrationState) -> dict:
        agent_result = await run_section_html_animation_agent(state, llm)

        tool_call_id = extract_last_tool_call_id(state)
        tool_message = ToolMessage(
            content=json.dumps(agent_result, ensure_ascii=False),
            tool_call_id=tool_call_id or "unknown",
        )

        result = {"messages": [tool_message]}
        if agent_result.get("course_knowledge") is not None:
            result["course_knowledge"] = agent_result["course_knowledge"]
        if agent_result.get("course_resource_result") is not None:
            result["course_resource_result"] = agent_result["course_resource_result"]
        if agent_result.get("response") is not None:
            result["response"] = agent_result["response"]
        if agent_result.get("error") is not None:
            result["response"] = agent_result["error"]
        return result

    return section_html_animation_node


async def stream_chapter_resource_generation(
    state: OrchestrationState,
    llm,
    search_llm,
    *,
    course_id: str,
    chapter_section_id: str,
    regeneration_focus: str = "",
) -> AsyncGenerator[dict, None]:
    outline = state.get("course_knowledge")
    if not isinstance(outline, dict):
        yield _chapter_resource_error_event(
            "请先生成课程大纲。",
            course_id=course_id,
            chapter_section_id=chapter_section_id,
            phase="outline",
            step_id=f"leaf-chapter-{chapter_section_id}",
            agent="leaf_resource_orchestrator",
            label="章节资源调度智能体",
        )
        return

    try:
        target_sections = _target_sections_for_scope(
            outline, chapter_section_id, "chapter_sections"
        )
    except ValueError as exc:
        yield _chapter_resource_error_event(
            str(exc),
            course_id=course_id,
            chapter_section_id=chapter_section_id,
            phase="outline",
            step_id=f"leaf-chapter-{chapter_section_id}",
            agent="leaf_resource_orchestrator",
            label="章节资源调度智能体",
        )
        return

    section_ids = [
        _clean_text(section.get("section_id"))
        for section in target_sections
        if _clean_text(section.get("section_id"))
    ]
    sections_by_id = {
        _clean_text(section.get("section_id")): section for section in target_sections
    }
    yield build_agent_event(
        event="agent_calling",
        agent="section_markdown_agent",
        phase="markdown",
        status="queued",
        step_id=f"leaf-chapter-{chapter_section_id}",
        message=f"正在为第 {chapter_section_id} 章准备 {len(section_ids)} 个小节智能体",
        depends_on=["course_knowledge_agent"],
        input_refs={
            "course_id": course_id,
            "chapter_section_id": chapter_section_id,
            "section_ids": section_ids,
        },
        extra={
            "kind": "course_resource_chapter",
            "label": "章节资源调度智能体",
        },
    )

    for section_id in section_ids:
        section = sections_by_id.get(section_id, {})
        yield build_agent_event(
            event="agent_progress",
            agent="section_markdown_agent",
            phase="markdown",
            status="running",
            step_id=f"leaf-section-{section_id}",
            message="正在生成文案，并写入视频与动画占位要求",
            depends_on=["course_knowledge_agent"],
            input_refs=_section_input_refs(
                course_id=course_id,
                chapter_section_id=chapter_section_id,
                section=section,
            ),
            extra={
                "kind": "course_resource_section",
                "label": f"{section_id} 小节智能体",
            },
        )

    markdown_args = {
        "course_id": course_id,
        "section_id": chapter_section_id,
        "scope": "chapter_sections",
    }
    if regeneration_focus:
        markdown_args["regeneration_focus"] = regeneration_focus
    import app.orchestration.agents.course_resources as cr_pkg

    markdown_result = await cr_pkg.run_section_markdown_agent(state, llm, markdown_args)
    if markdown_result.get("error"):
        yield _chapter_resource_error_event(
            str(markdown_result["error"]),
            course_id=course_id,
            chapter_section_id=chapter_section_id,
            phase="markdown",
            step_id=f"leaf-chapter-{chapter_section_id}-markdown",
            agent="section_markdown_agent",
            label="章节文案生成失败",
            section_ids=section_ids,
        )
        return

    state.update(markdown_result)
    for section_id in section_ids:
        outline_after_markdown = state.get("course_knowledge")
        output_refs = (
            _section_markdown_output_refs(outline_after_markdown, section_id)
            if isinstance(outline_after_markdown, dict)
            else {}
        )
        _record_section_checkpoint(
            state,
            section_id=section_id,
            phase="markdown",
            status="completed",
            output_refs=output_refs,
        )
        section = sections_by_id.get(section_id, {})
        yield build_agent_event(
            event="agent_result",
            agent="section_markdown_agent",
            phase="markdown",
            status="completed",
            step_id=f"leaf-section-{section_id}-markdown",
            message="文案与资源 brief 已生成，正在交接给视频和动画智能体",
            depends_on=["course_knowledge_agent"],
            input_refs=_section_input_refs(
                course_id=course_id,
                chapter_section_id=chapter_section_id,
                section=section,
            ),
            output_refs=output_refs,
            quality_result=quality_passed(),
            extra={
                "kind": "course_resource_section",
                "label": f"{section_id} 文案",
                "success": True,
                "trace": build_trace(
                    agent="section_markdown_agent",
                    phase="markdown",
                    section_id=section_id,
                    input_refs={"course_id": course_id},
                    output_refs=output_refs,
                    quality_result=quality_passed().to_dict(),
                ),
            },
        )

    for section_id in section_ids:
        section = sections_by_id.get(section_id, {})
        yield build_agent_event(
            event="agent_progress",
            agent="section_video_search_agent",
            phase="video",
            status="running",
            step_id=f"leaf-section-{section_id}-video",
            message="正在按 Markdown 中的 video_briefs 检索具体视频",
            depends_on=["section_markdown_agent"],
            input_refs=_section_input_refs(
                course_id=course_id,
                chapter_section_id=chapter_section_id,
                section=section,
            ),
            extra={
                "kind": "course_resource_section",
                "label": f"{section_id} 视频",
            },
        )

    video_result = await cr_pkg.run_section_video_search_agent(state, search_llm)
    if video_result.get("error"):
        yield _chapter_resource_error_event(
            str(video_result["error"]),
            course_id=course_id,
            chapter_section_id=chapter_section_id,
            phase="video",
            step_id=f"leaf-chapter-{chapter_section_id}-video",
            agent="section_video_search_agent",
            label="章节视频资源生成失败",
            section_ids=section_ids,
        )
        return
    state.update(video_result)
    for section_id in section_ids:
        outline_after_video = state.get("course_knowledge")
        output_refs = (
            _section_video_output_refs(outline_after_video, section_id)
            if isinstance(outline_after_video, dict)
            else {}
        )
        _record_section_checkpoint(
            state,
            section_id=section_id,
            phase="video",
            status="completed",
            output_refs=output_refs,
        )
        section = sections_by_id.get(section_id, {})
        yield build_agent_event(
            event="agent_result",
            agent="section_video_search_agent",
            phase="video",
            status="completed",
            step_id=f"leaf-section-{section_id}-video",
            message="视频检索已完成，正在交接给 HTML 动画智能体",
            depends_on=["section_markdown_agent"],
            input_refs=_section_input_refs(
                course_id=course_id,
                chapter_section_id=chapter_section_id,
                section=section,
            ),
            output_refs=output_refs,
            quality_result=quality_passed(),
            extra={
                "kind": "course_resource_section",
                "label": f"{section_id} 视频",
                "success": True,
                "trace": build_trace(
                    agent="section_video_search_agent",
                    phase="video",
                    section_id=section_id,
                    input_refs={"course_id": course_id},
                    output_refs=output_refs,
                    quality_result=quality_passed().to_dict(),
                ),
            },
        )

    for section_id in section_ids:
        section = sections_by_id.get(section_id, {})
        yield build_agent_event(
            event="agent_progress",
            agent="section_html_animation_agent",
            phase="animation",
            status="running",
            step_id=f"leaf-section-{section_id}-animation",
            message="正在按 Markdown 中的 animation_briefs 生成具体交互动画",
            depends_on=["section_video_search_agent"],
            input_refs=_section_input_refs(
                course_id=course_id,
                chapter_section_id=chapter_section_id,
                section=section,
            ),
            extra={
                "kind": "course_resource_section",
                "label": f"{section_id} 动画",
            },
        )

    animation_result = await cr_pkg.run_section_html_animation_agent(state, llm)
    if animation_result.get("error"):
        yield _chapter_resource_error_event(
            str(animation_result["error"]),
            course_id=course_id,
            chapter_section_id=chapter_section_id,
            phase="animation",
            step_id=f"leaf-chapter-{chapter_section_id}-animation",
            agent="section_html_animation_agent",
            label="章节 HTML 动画生成失败",
            section_ids=section_ids,
        )
        return
    state.update(animation_result)

    for section_id in section_ids:
        outline_after_animation = state.get("course_knowledge")
        animation_output_refs = (
            _section_animation_output_refs(outline_after_animation, section_id)
            if isinstance(outline_after_animation, dict)
            else {}
        )
        _record_section_checkpoint(
            state,
            section_id=section_id,
            phase="animation",
            status="completed",
            output_refs=animation_output_refs,
        )
        section = sections_by_id.get(section_id, {})
        yield build_agent_event(
            event="agent_result",
            agent="section_html_animation_agent",
            phase="animation",
            status="completed",
            step_id=f"leaf-section-{section_id}-animation",
            message="动画生成已保存，正在记录正文拼装结果",
            depends_on=["section_video_search_agent"],
            input_refs=_section_input_refs(
                course_id=course_id,
                chapter_section_id=chapter_section_id,
                section=section,
            ),
            output_refs=animation_output_refs,
            quality_result=quality_passed(),
            extra={
                "kind": "course_resource_section",
                "label": f"{section_id} 动画",
                "success": True,
                "trace": build_trace(
                    agent="section_html_animation_agent",
                    phase="animation",
                    section_id=section_id,
                    input_refs={"course_id": course_id},
                    output_refs=animation_output_refs,
                    quality_result=quality_passed().to_dict(),
                ),
            },
        )

        outline_after_compose = state.get("course_knowledge")
        compose_output_refs = (
            _section_compose_output_refs(outline_after_compose, section_id)
            if isinstance(outline_after_compose, dict)
            else {}
        )
        _record_section_checkpoint(
            state,
            section_id=section_id,
            phase="compose",
            status="completed",
            output_refs=compose_output_refs,
        )
        yield build_agent_event(
            event="agent_result",
            agent="compose_resource",
            phase="compose",
            status="completed",
            step_id=f"leaf-section-{section_id}-compose",
            message="正文、视频与动画资源已按占位符拼装完成",
            depends_on=["section_html_animation_agent"],
            input_refs={
                "course_id": course_id,
                "chapter_section_id": chapter_section_id,
                "section_id": section_id,
            },
            output_refs=compose_output_refs,
            quality_result=quality_passed(),
            extra={
                "kind": "course_resource_section",
                "label": f"{section_id} 拼装",
                "success": True,
                "trace": build_trace(
                    agent="compose_resource",
                    phase="compose",
                    section_id=section_id,
                    input_refs={"course_id": course_id},
                    output_refs=compose_output_refs,
                    quality_result=quality_passed().to_dict(),
                ),
            },
        )

    yield {
        "event": "message_completed",
        "full_text": "本章教学内容已生成。",
    }
    yield {
        "event": "session_completed",
        "session_id": str(state.get("session_id", "")),
        "has_profile": isinstance(state.get("profile"), dict),
        "has_paths": isinstance(state.get("year_learning_paths"), dict),
        "has_outline": True,
    }
