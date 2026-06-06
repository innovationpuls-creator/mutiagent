from __future__ import annotations

import asyncio
import json
import logging
from copy import deepcopy
from datetime import datetime, timezone
from urllib.parse import quote

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_core.prompts import ChatPromptTemplate
from sqlmodel import Session

from app.database import get_engine
from app.orchestration.agents.models import (
    SectionHtmlAnimationOutput,
    SectionMarkdownOutput,
    SectionVideoSearchOutput,
)
from app.orchestration.agents.prompts import (
    SECTION_HTML_ANIMATION_AGENT_SYSTEM_PROMPT,
    SECTION_MARKDOWN_AGENT_SYSTEM_PROMPT,
    SECTION_VIDEO_SEARCH_AGENT_SYSTEM_PROMPT,
)
from app.orchestration.agents.utils import extract_last_tool_call_args, extract_last_tool_call_id
from app.orchestration.state import OrchestrationState
from app.services.course_knowledge_service import upsert_user_course_knowledge_outline

logger = logging.getLogger(__name__)

_RESOURCE_TIMEOUT_SECONDS = 60.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_text(value: object) -> str:
    text = str(value).strip()
    if not text or text.lower() in {"none", "null"}:
        return ""
    return text


def _sections(outline: dict) -> list[dict]:
    value = outline.get("sections")
    if not isinstance(value, list):
        return []
    return [section for section in value if isinstance(section, dict)]


def _section_by_id(outline: dict, section_id: str) -> dict | None:
    for section in _sections(outline):
        if section.get("section_id") == section_id:
            return section
    return None


def _target_sections_for_scope(outline: dict, section_id: str, scope: str) -> list[dict]:
    sections = sorted(_sections(outline), key=lambda item: int(item.get("order_index", 0)))
    if scope == "single_section":
        section = _section_by_id(outline, section_id)
        if not section or int(section.get("depth", 1)) <= 1:
            raise ValueError("指定小节无法定位。")
        return [section]
    if scope == "chapter_sections":
        parent = _section_by_id(outline, section_id)
        if not parent or int(parent.get("depth", 1)) != 1:
            raise ValueError("指定章节无法定位。")
        return [
            section for section in sections
            if section.get("parent_section_id") == section_id and int(section.get("depth", 1)) > 1
        ]
    if scope == "course_sections":
        return [section for section in sections if int(section.get("depth", 1)) > 1]

    root_sections = [section for section in sections if int(section.get("depth", 1)) == 1]
    if not root_sections:
        raise ValueError("课程大纲缺少一级章节。")
    first_root_id = _clean_text(root_sections[0].get("section_id"))
    return [
        section for section in sections
        if section.get("parent_section_id") == first_root_id and int(section.get("depth", 1)) > 1
    ]


def _parent_section(outline: dict, section: dict) -> dict | None:
    parent_id = section.get("parent_section_id")
    if not isinstance(parent_id, str):
        return None
    return _section_by_id(outline, parent_id)


def _merge_course_resource_data(outline: dict, field_name: str, values: dict[str, dict]) -> dict:
    merged = deepcopy(outline)
    existing = merged.get(field_name)
    if not isinstance(existing, dict):
        existing = {}
    existing.update(values)
    merged[field_name] = existing
    return merged


def _fallback_cover_data_url(title: str) -> str:
    safe_title = _clean_text(title) or "课程视频"
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='640' height='360' viewBox='0 0 640 360'>"
        "<rect width='640' height='360' fill='oklch(22% 0.04 220)'/>"
        "<circle cx='320' cy='150' r='54' fill='oklch(70% 0.12 190)' opacity='0.85'/>"
        "<polygon points='305,122 305,178 352,150' fill='oklch(96% 0.02 90)'/>"
        f"<text x='320' y='255' text-anchor='middle' font-size='28' fill='oklch(92% 0.02 90)'>{safe_title}</text>"
        "</svg>"
    )
    encoded_svg = quote(svg, safe="/:=;,%#?&'() ")
    return "data:image/svg+xml;utf8," + encoded_svg.replace(quote(safe_title), safe_title)


def _tool_args(state: OrchestrationState, explicit_args: dict | None) -> dict:
    if isinstance(explicit_args, dict):
        return explicit_args
    return extract_last_tool_call_args(state)


def _markdown_input(outline: dict, section: dict) -> str:
    payload = {
        "course": {
            "course_id": outline.get("course_id", ""),
            "course_name": outline.get("course_name", ""),
            "grade_year": outline.get("grade_year", ""),
            "personalization_summary": outline.get("personalization_summary", ""),
            "learning_sequence": outline.get("learning_sequence", []),
            "total_estimated_hours": outline.get("total_estimated_hours", ""),
        },
        "parent_section": _parent_section(outline, section),
        "target_section": section,
    }
    return (
        "请为输入小节生成完整 Markdown 教学文档。\n\n"
        f"输入：{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def _section_title(outline: dict, section: dict) -> str:
    section_id = _clean_text(section.get("section_id"))
    section_markdowns = outline.get("section_markdowns")
    if isinstance(section_markdowns, dict):
        section_markdown = section_markdowns.get(section_id)
        if isinstance(section_markdown, dict):
            markdown_title = _clean_text(section_markdown.get("title"))
            if markdown_title:
                return markdown_title
    return _clean_text(section.get("title")) or section_id


def _video_input(outline: dict, section: dict) -> str:
    section_id = _clean_text(section.get("section_id"))
    section_markdowns = outline.get("section_markdowns")
    target_markdowns = {}
    if isinstance(section_markdowns, dict):
        section_markdown = section_markdowns.get(section_id)
        if isinstance(section_markdown, dict):
            target_markdowns[section_id] = section_markdown

    payload = {
        "course": {
            "course_id": outline.get("course_id", ""),
            "course_name": outline.get("course_name", ""),
            "grade_year": outline.get("grade_year", ""),
            "personalization_summary": outline.get("personalization_summary", ""),
            "learning_sequence": outline.get("learning_sequence", []),
            "total_estimated_hours": outline.get("total_estimated_hours", ""),
        },
        "parent_section": _parent_section(outline, section),
        "target_section": section,
        "section_markdowns": target_markdowns,
    }
    return (
        "请为输入小节联网搜索可直接打开的视频教程资源。\n\n"
        f"输入：{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def _normalize_videos(videos: object) -> list[dict]:
    if not isinstance(videos, list):
        return []

    normalized = []
    for video in videos:
        if hasattr(video, "model_dump"):
            video_data = video.model_dump()
        elif isinstance(video, dict):
            video_data = dict(video)
        else:
            continue

        title = _clean_text(video_data.get("title"))
        url = _clean_text(video_data.get("url"))
        if not title or not url:
            continue

        cover_url = _clean_text(video_data.get("cover_url"))
        cover_status = "provided" if cover_url else "fallback"
        if not cover_url:
            cover_url = _fallback_cover_data_url(title)

        normalized.append(
            {
                "title": title,
                "url": url,
                "cover_url": cover_url,
                "cover_status": cover_status,
                "source": _clean_text(video_data.get("source")),
            }
        )
    return normalized


def _animation_input(outline: dict, section: dict) -> str:
    section_id = _clean_text(section.get("section_id"))
    section_markdowns = outline.get("section_markdowns")
    section_markdown = {}
    if isinstance(section_markdowns, dict):
        value = section_markdowns.get(section_id)
        if isinstance(value, dict):
            section_markdown = value

    animation_briefs = section_markdown.get("animation_briefs")
    payload = {
        "course": {
            "course_id": outline.get("course_id", ""),
            "course_name": outline.get("course_name", ""),
            "grade_year": outline.get("grade_year", ""),
            "personalization_summary": outline.get("personalization_summary", ""),
            "learning_sequence": outline.get("learning_sequence", []),
            "total_estimated_hours": outline.get("total_estimated_hours", ""),
        },
        "parent_section": _parent_section(outline, section),
        "target_section": section,
        "section_markdown": section_markdown,
        "animation_briefs": animation_briefs if isinstance(animation_briefs, list) else [],
    }
    return (
        "请为输入小节的 animation_briefs 生成可嵌入 HTML 动画片段。\n\n"
        f"输入：{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def _normalize_animations(animations: object, animation_briefs: object) -> list[dict]:
    if not isinstance(animations, list) or not isinstance(animation_briefs, list):
        return []

    brief_titles = {}
    for brief in animation_briefs:
        if not isinstance(brief, dict):
            continue
        animation_id = _clean_text(brief.get("animation_id"))
        if animation_id:
            brief_titles[animation_id] = _clean_text(brief.get("title"))

    normalized = []
    for animation in animations:
        if hasattr(animation, "model_dump"):
            animation_data = animation.model_dump()
        elif isinstance(animation, dict):
            animation_data = dict(animation)
        else:
            continue

        animation_id = _clean_text(animation_data.get("animation_id"))
        html = _clean_text(animation_data.get("html"))
        if not animation_id or animation_id not in brief_titles or not html:
            continue

        normalized.append(
            {
                "animation_id": animation_id,
                "title": _clean_text(animation_data.get("title")) or brief_titles[animation_id],
                "html": html,
            }
        )
    return normalized


def _persist_outline(user_id: str, outline: dict) -> None:
    with Session(get_engine()) as db_session:
        upsert_user_course_knowledge_outline(db_session, user_id, outline)
    logger.info(
        "Course resource outline persisted for user %s, course %s",
        user_id,
        outline.get("course_id", ""),
    )


async def run_section_markdown_agent(
    state: OrchestrationState,
    llm: BaseChatModel,
    explicit_args: dict | None = None,
) -> dict:
    outline = state.get("course_knowledge")
    if not isinstance(outline, dict):
        return {"error": "请先生成课程大纲。", "hard_error": True}

    args = _tool_args(state, explicit_args)
    section_id = _clean_text(args.get("section_id", ""))
    scope = _clean_text(args.get("scope", "")) or "default_first_chapter"

    try:
        target_sections = _target_sections_for_scope(outline, section_id, scope)
    except ValueError as exc:
        return {"error": str(exc), "hard_error": True}

    structured_llm = llm.with_structured_output(SectionMarkdownOutput)
    prompt = ChatPromptTemplate.from_messages([
        ("system", SECTION_MARKDOWN_AGENT_SYSTEM_PROMPT),
        ("human", "{query}"),
    ])
    chain = prompt | structured_llm

    target_section_ids = [
        _clean_text(section.get("section_id"))
        for section in target_sections
    ]
    section_markdowns: dict[str, dict] = {}
    for section in target_sections:
        target_section_id = _clean_text(section.get("section_id"))
        if not target_section_id:
            continue
        try:
            markdown_output = await asyncio.wait_for(
                chain.ainvoke({"query": _markdown_input(outline, section)}),
                timeout=_RESOURCE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "SectionMarkdownAgent timed out after %.1fs for section %s",
                _RESOURCE_TIMEOUT_SECONDS,
                target_section_id,
            )
            return {"error": "小节文档生成超时，请稍后重试。", "hard_error": True}
        except Exception as exc:
            logger.warning("SectionMarkdownAgent failed for section %s: %s", target_section_id, exc)
            return {"error": "小节文档生成失败，请稍后重试。", "hard_error": True}

        if hasattr(markdown_output, "model_dump"):
            markdown_data = markdown_output.model_dump()
        elif isinstance(markdown_output, dict):
            markdown_data = dict(markdown_output)
        else:
            markdown_data = SectionMarkdownOutput.model_validate(markdown_output).model_dump()

        animation_briefs = markdown_data.get("animation_briefs")
        section_markdowns[target_section_id] = {
            "section_id": target_section_id,
            "parent_section_id": section.get("parent_section_id"),
            "title": _clean_text(section.get("title")) or _clean_text(markdown_data.get("title")),
            "markdown": _clean_text(markdown_data.get("markdown")),
            "animation_briefs": animation_briefs if isinstance(animation_briefs, list) else [],
            "generated_at": _now_iso(),
        }

    updated_outline = _merge_course_resource_data(outline, "section_markdowns", section_markdowns)
    try:
        _persist_outline(str(state.get("user_id", "")), updated_outline)
    except Exception as exc:
        logger.error("Failed to persist course resources for user %s: %s", state.get("user_id", ""), exc)
        return {"error": "课程资源保存失败，请稍后重试。", "hard_error": True}

    markdown_section_ids = list(section_markdowns.keys())
    return {
        "course_knowledge": updated_outline,
        "course_resource_plan": {
            "course_id": updated_outline.get("course_id", ""),
            "target_section_ids": target_section_ids,
            "markdown_section_ids": markdown_section_ids,
            "video_section_ids": [],
            "animation_section_ids": [],
        },
    }


async def run_section_video_search_agent(
    state: OrchestrationState,
    llm: BaseChatModel,
    explicit_args: dict | None = None,
) -> dict:
    outline = state.get("course_knowledge")
    if not isinstance(outline, dict):
        return {"error": "请先生成课程大纲。", "hard_error": True}

    resource_plan = state.get("course_resource_plan")
    plan_target_ids = None
    if isinstance(resource_plan, dict):
        plan_target_ids = resource_plan.get("target_section_ids")

    if isinstance(plan_target_ids, list):
        target_section_ids = [
            section_id
            for section_id in (_clean_text(value) for value in plan_target_ids)
            if section_id
        ]
        target_sections = [
            section
            for section_id in target_section_ids
            if (section := _section_by_id(outline, section_id)) is not None
        ]
    else:
        args = _tool_args(state, explicit_args)
        section_id = _clean_text(args.get("section_id", ""))
        scope = _clean_text(args.get("scope", "")) or "default_first_chapter"
        try:
            target_sections = _target_sections_for_scope(outline, section_id, scope)
        except ValueError as exc:
            return {"error": str(exc), "hard_error": True}
        target_section_ids = [
            _clean_text(section.get("section_id"))
            for section in target_sections
        ]

    structured_llm = llm.with_structured_output(SectionVideoSearchOutput)
    prompt = ChatPromptTemplate.from_messages([
        ("system", SECTION_VIDEO_SEARCH_AGENT_SYSTEM_PROMPT),
        ("human", "{query}"),
    ])
    chain = prompt | structured_llm

    section_video_links: dict[str, dict] = {}
    for section in target_sections:
        target_section_id = _clean_text(section.get("section_id"))
        if not target_section_id:
            continue

        video_data = {"query": "", "videos": []}
        try:
            video_output = await asyncio.wait_for(
                chain.ainvoke({"query": _video_input(outline, section)}),
                timeout=_RESOURCE_TIMEOUT_SECONDS,
            )
            if hasattr(video_output, "model_dump"):
                video_data = video_output.model_dump()
            elif isinstance(video_output, dict):
                video_data = dict(video_output)
            else:
                video_data = SectionVideoSearchOutput.model_validate(video_output).model_dump()
        except Exception as exc:
            logger.warning("SectionVideoSearchAgent failed for section %s: %s", target_section_id, exc)

        section_video_links[target_section_id] = {
            "section_id": target_section_id,
            "parent_section_id": section.get("parent_section_id"),
            "title": _section_title(outline, section),
            "query": _clean_text(video_data.get("query")),
            "videos": _normalize_videos(video_data.get("videos")),
            "generated_at": _now_iso(),
        }

    updated_outline = _merge_course_resource_data(outline, "section_video_links", section_video_links)
    try:
        _persist_outline(str(state.get("user_id", "")), updated_outline)
    except Exception as exc:
        logger.error("Failed to persist course resources for user %s: %s", state.get("user_id", ""), exc)
        return {"error": "课程资源保存失败，请稍后重试。", "hard_error": True}

    updated_plan = dict(resource_plan) if isinstance(resource_plan, dict) else {}
    updated_plan["target_section_ids"] = target_section_ids
    updated_plan["video_section_ids"] = list(section_video_links.keys())

    return {
        "course_knowledge": updated_outline,
        "course_resource_plan": updated_plan,
    }


async def run_section_html_animation_agent(
    state: OrchestrationState,
    llm: BaseChatModel,
    explicit_args: dict | None = None,
) -> dict:
    outline = state.get("course_knowledge")
    if not isinstance(outline, dict):
        return {"error": "请先生成课程大纲。", "hard_error": True}

    resource_plan = state.get("course_resource_plan")
    plan_target_ids = None
    if isinstance(resource_plan, dict):
        plan_target_ids = resource_plan.get("target_section_ids")

    if isinstance(plan_target_ids, list):
        target_section_ids = [
            section_id
            for section_id in (_clean_text(value) for value in plan_target_ids)
            if section_id
        ]
        target_sections = [
            section
            for section_id in target_section_ids
            if (section := _section_by_id(outline, section_id)) is not None
        ]
    else:
        args = _tool_args(state, explicit_args)
        section_id = _clean_text(args.get("section_id", ""))
        scope = _clean_text(args.get("scope", "")) or "default_first_chapter"
        try:
            target_sections = _target_sections_for_scope(outline, section_id, scope)
        except ValueError as exc:
            return {"error": str(exc), "hard_error": True}
        target_section_ids = [
            _clean_text(section.get("section_id"))
            for section in target_sections
        ]

    structured_llm = llm.with_structured_output(SectionHtmlAnimationOutput)
    prompt = ChatPromptTemplate.from_messages([
        ("system", SECTION_HTML_ANIMATION_AGENT_SYSTEM_PROMPT),
        ("human", "{query}"),
    ])
    chain = prompt | structured_llm

    section_html_animations: dict[str, dict] = {}
    section_markdowns = outline.get("section_markdowns")
    for section in target_sections:
        target_section_id = _clean_text(section.get("section_id"))
        if not target_section_id:
            continue

        section_markdown = {}
        if isinstance(section_markdowns, dict):
            value = section_markdowns.get(target_section_id)
            if isinstance(value, dict):
                section_markdown = value
        animation_briefs = section_markdown.get("animation_briefs")

        animation_data = {"animations": []}
        if isinstance(animation_briefs, list) and animation_briefs:
            try:
                animation_output = await asyncio.wait_for(
                    chain.ainvoke({"query": _animation_input(outline, section)}),
                    timeout=_RESOURCE_TIMEOUT_SECONDS,
                )
                if hasattr(animation_output, "model_dump"):
                    animation_data = animation_output.model_dump()
                elif isinstance(animation_output, dict):
                    animation_data = dict(animation_output)
                else:
                    animation_data = SectionHtmlAnimationOutput.model_validate(animation_output).model_dump()
            except Exception as exc:
                logger.warning("SectionHtmlAnimationAgent failed for section %s: %s", target_section_id, exc)

        section_html_animations[target_section_id] = {
            "section_id": target_section_id,
            "parent_section_id": section.get("parent_section_id"),
            "title": _section_title(outline, section),
            "animations": _normalize_animations(animation_data.get("animations"), animation_briefs),
            "generated_at": _now_iso(),
        }

    updated_outline = _merge_course_resource_data(outline, "section_html_animations", section_html_animations)
    try:
        _persist_outline(str(state.get("user_id", "")), updated_outline)
    except Exception as exc:
        logger.error("Failed to persist course resources for user %s: %s", state.get("user_id", ""), exc)
        return {"error": "课程资源保存失败，请稍后重试。", "hard_error": True}

    updated_plan = dict(resource_plan) if isinstance(resource_plan, dict) else {}
    updated_plan["target_section_ids"] = target_section_ids
    updated_plan["animation_section_ids"] = list(section_html_animations.keys())

    markdown_count = 0
    if isinstance(section_markdowns, dict):
        markdown_count = sum(
            1 for section_id in target_section_ids
            if isinstance(section_markdowns.get(section_id), dict)
        )
    section_video_links = updated_outline.get("section_video_links")
    video_count = 0
    if isinstance(section_video_links, dict):
        for section_id in target_section_ids:
            value = section_video_links.get(section_id)
            if not isinstance(value, dict):
                continue
            videos = value.get("videos")
            if isinstance(videos, list):
                video_count += len(videos)
    animation_count = sum(
        len(value.get("animations", []))
        for value in section_html_animations.values()
    )
    section_ids_text = "、".join(section_html_animations.keys()) or "指定小节"
    course_name = _clean_text(updated_outline.get("course_name")) or "课程"

    return {
        "course_knowledge": updated_outline,
        "course_resource_plan": updated_plan,
        "course_resource_result": {
            "course_id": updated_outline.get("course_id", ""),
            "generated_section_ids": list(section_html_animations.keys()),
            "markdown_count": markdown_count,
            "video_count": video_count,
            "animation_count": animation_count,
        },
        "response": (
            f"《{course_name}》的 {section_ids_text} 教学内容已生成，"
            f"包含 {markdown_count} 篇文档、{video_count} 个视频资源、"
            f"{animation_count} 个 HTML 动画。"
        ),
    }


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
