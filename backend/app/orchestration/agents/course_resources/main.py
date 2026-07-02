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
from app.orchestration.recovery import update_section_phase_checkpoint
from app.orchestration.state import OrchestrationState

logger = logging.getLogger(__name__)


def _section_by_clean_id(sections: list[dict]) -> dict[str, dict]:
    return {
        section_id: section
        for section in sections
        if (section_id := _clean_text(section.get("section_id")))
    }


def _section_input_refs(course_id: str, section: dict) -> dict:
    refs = {
        "course_id": course_id,
        "section_id": _clean_text(section.get("section_id")),
    }
    source_textbook_id = _clean_text(section.get("source_textbook_id"))
    if source_textbook_id:
        refs["source_textbook_id"] = source_textbook_id
    source_section_ids = section.get("source_section_ids")
    if isinstance(source_section_ids, list):
        refs["source_section_ids"] = source_section_ids
    return refs


def _text_ids(items: object, key: str) -> list[str]:
    if not isinstance(items, list):
        return []
    return [
        item_id
        for item in items
        if isinstance(item, dict) and (item_id := _clean_text(item.get(key)))
    ]


def _markdown_output_refs(outline: dict, section_id: str) -> dict:
    section_markdowns = outline.get("section_markdowns")
    markdown_value = (
        section_markdowns.get(section_id) if isinstance(section_markdowns, dict) else {}
    )
    if not isinstance(markdown_value, dict):
        markdown_value = {}
    return {
        "section_markdown_id": section_id,
        "video_brief_ids": _text_ids(markdown_value.get("video_briefs"), "video_id"),
        "animation_brief_ids": _text_ids(
            markdown_value.get("animation_briefs"), "animation_id"
        ),
    }


def _video_output_refs(outline: dict, section_id: str) -> dict:
    section_video_links = outline.get("section_video_links")
    video_value = (
        section_video_links.get(section_id)
        if isinstance(section_video_links, dict)
        else {}
    )
    if not isinstance(video_value, dict):
        video_value = {}
    return {
        "section_video_link_id": section_id,
        "video_brief_ids": _text_ids(video_value.get("videos"), "brief_id"),
    }


def _animation_output_refs(outline: dict, section_id: str) -> dict:
    section_html_animations = outline.get("section_html_animations")
    animation_value = (
        section_html_animations.get(section_id)
        if isinstance(section_html_animations, dict)
        else {}
    )
    if not isinstance(animation_value, dict):
        animation_value = {}
    return {
        "section_animation_id": section_id,
        "animation_brief_ids": _text_ids(
            animation_value.get("animations"), "animation_id"
        ),
    }


def _video_phase_status(outline: dict, section_id: str) -> str:
    section_video_links = outline.get("section_video_links")
    video_value = (
        section_video_links.get(section_id)
        if isinstance(section_video_links, dict)
        else {}
    )
    if isinstance(video_value, dict) and video_value.get("status") == "unavailable":
        return "unavailable"
    return "completed"


def _video_failure_reason(outline: dict, section_id: str) -> str:
    section_video_links = outline.get("section_video_links")
    video_value = (
        section_video_links.get(section_id)
        if isinstance(section_video_links, dict)
        else {}
    )
    if not isinstance(video_value, dict):
        return ""
    return _clean_text(video_value.get("failure_reason"))


def _quality_payload_for_status(status: str, failure_reason: str = "") -> dict:
    if status == "unavailable":
        return {
            "passed": False,
            "severity": "informational",
            "reason": failure_reason,
            "checks": [],
        }
    return quality_passed().to_dict()


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
    sections_by_id = _section_by_clean_id(target_sections)
    yield {
        "event": "agent_calling",
        "stepId": f"leaf-chapter-{chapter_section_id}",
        "kind": "course_resource_chapter",
        "agent": "leaf_resource_orchestrator",
        "label": "章节资源调度智能体",
        "message": f"正在为第 {chapter_section_id} 章准备 {len(section_ids)} 个小节智能体",
        "course_id": course_id,
        "chapter_section_id": chapter_section_id,
        "section_ids": section_ids,
    }

    for section_id in section_ids:
        yield build_agent_event(
            event="agent_progress",
            agent="section_markdown_agent",
            phase="markdown",
            status="running",
            step_id=f"leaf-section-{section_id}-markdown",
            message="正在基于教材证据生成小节 Markdown 与资源规划",
            depends_on=["course_knowledge_agent"],
            input_refs=_section_input_refs(
                course_id, sections_by_id.get(section_id, {})
            ),
            extra={
                "kind": "course_resource_section",
                "label": f"{section_id} 文案",
                "course_id": course_id,
                "chapter_section_id": chapter_section_id,
                "section_id": section_id,
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
        output_refs = _markdown_output_refs(state["course_knowledge"], section_id)
        updated_outline = update_section_phase_checkpoint(
            state["course_knowledge"],
            section_id=section_id,
            phase="markdown",
            status="completed",
            output_refs=output_refs,
            quality_result=quality_passed().to_dict(),
        )
        state["course_knowledge"] = updated_outline
        yield build_agent_event(
            event="agent_result",
            agent="section_markdown_agent",
            phase="markdown",
            status="completed",
            step_id=f"leaf-section-{section_id}-markdown",
            message="文案与资源 brief 已生成，正在交接给视频和动画智能体",
            depends_on=["course_knowledge_agent"],
            input_refs=_section_input_refs(
                course_id, sections_by_id.get(section_id, {})
            ),
            output_refs=output_refs,
            quality_result=quality_passed(),
            extra={
                "kind": "course_resource_section",
                "label": f"{section_id} 文案",
                "summary": "文案与资源 brief 已生成，正在交接给视频和动画智能体",
                "course_id": course_id,
                "chapter_section_id": chapter_section_id,
                "section_id": section_id,
                "success": True,
            },
        )

    for section_id in section_ids:
        yield build_agent_event(
            event="agent_progress",
            agent="section_video_search_agent",
            phase="video",
            status="running",
            step_id=f"leaf-section-{section_id}-video",
            message="正在按 Markdown 中的 video_briefs 检索具体视频",
            depends_on=["section_markdown_agent"],
            input_refs=_section_input_refs(
                course_id, sections_by_id.get(section_id, {})
            ),
            extra={
                "kind": "course_resource_section",
                "label": f"{section_id} 视频",
                "course_id": course_id,
                "chapter_section_id": chapter_section_id,
                "section_id": section_id,
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
        output_refs = _video_output_refs(state["course_knowledge"], section_id)
        status = _video_phase_status(state["course_knowledge"], section_id)
        failure_reason = _video_failure_reason(state["course_knowledge"], section_id)
        quality_result = _quality_payload_for_status(status, failure_reason)
        updated_outline = update_section_phase_checkpoint(
            state["course_knowledge"],
            section_id=section_id,
            phase="video",
            status=status,
            output_refs=output_refs,
            quality_result=quality_result,
            failure_reason=failure_reason,
        )
        state["course_knowledge"] = updated_outline
        yield build_agent_event(
            event="agent_result",
            agent="section_video_search_agent",
            phase="video",
            status=status,
            step_id=f"leaf-section-{section_id}-video",
            message="视频检索已完成，正在交接给 HTML 动画智能体",
            depends_on=["section_markdown_agent"],
            input_refs=_section_input_refs(
                course_id, sections_by_id.get(section_id, {})
            ),
            output_refs=output_refs,
            quality_result=quality_result,
            extra={
                "kind": "course_resource_section",
                "label": f"{section_id} 视频",
                "summary": "视频检索已完成，正在交接给 HTML 动画智能体",
                "course_id": course_id,
                "chapter_section_id": chapter_section_id,
                "section_id": section_id,
                "success": status == "completed",
            },
        )

    for section_id in section_ids:
        yield build_agent_event(
            event="agent_progress",
            agent="section_html_animation_agent",
            phase="animation",
            status="running",
            step_id=f"leaf-section-{section_id}-animation",
            message="正在按 Markdown 中的 animation_briefs 生成具体交互动画",
            depends_on=["section_markdown_agent", "section_video_search_agent"],
            input_refs=_section_input_refs(
                course_id, sections_by_id.get(section_id, {})
            ),
            extra={
                "kind": "course_resource_section",
                "label": f"{section_id} 动画",
                "course_id": course_id,
                "chapter_section_id": chapter_section_id,
                "section_id": section_id,
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
        output_refs = _animation_output_refs(state["course_knowledge"], section_id)
        updated_outline = update_section_phase_checkpoint(
            state["course_knowledge"],
            section_id=section_id,
            phase="animation",
            status="completed",
            output_refs=output_refs,
            quality_result=quality_passed().to_dict(),
        )
        state["course_knowledge"] = updated_outline
        yield build_agent_event(
            event="agent_result",
            agent="section_html_animation_agent",
            phase="animation",
            status="completed",
            step_id=f"leaf-section-{section_id}-animation",
            message="动画生成与正文拼装已保存",
            depends_on=["section_markdown_agent", "section_video_search_agent"],
            input_refs=_section_input_refs(
                course_id, sections_by_id.get(section_id, {})
            ),
            output_refs=output_refs,
            quality_result=quality_passed(),
            extra={
                "kind": "course_resource_section",
                "label": f"{section_id} 动画",
                "summary": "动画生成与正文拼装已保存",
                "course_id": course_id,
                "chapter_section_id": chapter_section_id,
                "section_id": section_id,
                "success": True,
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
