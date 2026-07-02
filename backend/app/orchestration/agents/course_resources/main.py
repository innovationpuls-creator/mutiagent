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
from app.orchestration.state import OrchestrationState

logger = logging.getLogger(__name__)


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
        yield {
            "event": "agent_progress",
            "stepId": f"leaf-section-{section_id}",
            "kind": "course_resource_section",
            "agent": "section_markdown_agent",
            "label": f"{section_id} 小节智能体",
            "message": "正在生成文案，并写入视频与动画占位要求",
            "course_id": course_id,
            "chapter_section_id": chapter_section_id,
            "section_id": section_id,
            "phase": "markdown",
            "status": "running",
        }

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
        yield {
            "event": "agent_result",
            "stepId": f"leaf-section-{section_id}-markdown",
            "kind": "course_resource_section",
            "agent": "section_markdown_agent",
            "label": f"{section_id} 文案",
            "summary": "文案与资源 brief 已生成，正在交接给视频和动画智能体",
            "course_id": course_id,
            "chapter_section_id": chapter_section_id,
            "section_id": section_id,
            "phase": "markdown",
            "status": "completed",
            "success": True,
        }

    for section_id in section_ids:
        yield {
            "event": "agent_progress",
            "stepId": f"leaf-section-{section_id}-video",
            "kind": "course_resource_section",
            "agent": "section_video_search_agent",
            "label": f"{section_id} 视频",
            "message": "正在按 Markdown 中的 video_briefs 检索具体视频",
            "course_id": course_id,
            "chapter_section_id": chapter_section_id,
            "section_id": section_id,
            "phase": "video",
            "status": "running",
        }

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
        yield {
            "event": "agent_result",
            "stepId": f"leaf-section-{section_id}-video",
            "kind": "course_resource_section",
            "agent": "section_video_search_agent",
            "label": f"{section_id} 视频",
            "summary": "视频检索已完成，正在交接给 HTML 动画智能体",
            "course_id": course_id,
            "chapter_section_id": chapter_section_id,
            "section_id": section_id,
            "phase": "video",
            "status": "completed",
            "success": True,
        }

    for section_id in section_ids:
        yield {
            "event": "agent_progress",
            "stepId": f"leaf-section-{section_id}-animation",
            "kind": "course_resource_section",
            "agent": "section_html_animation_agent",
            "label": f"{section_id} 动画",
            "message": "正在按 Markdown 中的 animation_briefs 生成具体交互动画",
            "course_id": course_id,
            "chapter_section_id": chapter_section_id,
            "section_id": section_id,
            "phase": "animation",
            "status": "running",
        }

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
        yield {
            "event": "agent_result",
            "stepId": f"leaf-section-{section_id}-animation",
            "kind": "course_resource_section",
            "agent": "section_html_animation_agent",
            "label": f"{section_id} 动画",
            "summary": "动画生成与正文拼装已保存",
            "course_id": course_id,
            "chapter_section_id": chapter_section_id,
            "section_id": section_id,
            "phase": "animation",
            "status": "completed",
            "success": True,
        }

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
