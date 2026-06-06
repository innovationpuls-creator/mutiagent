from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncGenerator, Awaitable, Callable
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
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
_MARKDOWN_TIMEOUT_SECONDS = 30.0
_VIDEO_TIMEOUT_SECONDS = 20.0
_ANIMATION_TIMEOUT_SECONDS = 20.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_text(value: object) -> str:
    text = str(value).strip()
    if not text or text.lower() in {"none", "null"}:
        return ""
    return text


_RESOURCE_PLACEHOLDER_PATTERN = re.compile(
    r"<!--\s*(?P<kind>video|animation):id=(?P<id>[A-Za-z0-9_.:-]+)\s*-->"
)


def _extract_brief_ids_from_markdown(markdown: str, kind: str) -> list[str]:
    ids: list[str] = []
    for match in _RESOURCE_PLACEHOLDER_PATTERN.finditer(markdown):
        if match.group("kind") != kind:
            continue
        ids.append(match.group("id"))
    return ids


async def _run_with_retries(
    action: Callable[[], Awaitable[dict]],
    *,
    fallback: dict,
    attempts: int = 3,
) -> dict:
    for attempt in range(attempts):
        try:
            return await action()
        except Exception as exc:
            if attempt + 1 >= attempts:
                logger.warning("Resource action failed after %s attempts: %s", attempts, exc)
    return fallback


async def _invoke_resource_chain(
    chain: Any,
    query: str,
    output_schema: Any,
    *,
    timeout_seconds: float = _RESOURCE_TIMEOUT_SECONDS,
) -> dict:
    output = await asyncio.wait_for(
        chain.ainvoke({"query": query}),
        timeout=timeout_seconds,
    )
    if hasattr(output, "model_dump"):
        return output.model_dump()
    if isinstance(output, dict):
        return dict(output)
    return output_schema.model_validate(output).model_dump()


def _brief_by_id(briefs: object, id_field: str) -> dict[str, dict]:
    if not isinstance(briefs, list):
        return {}
    result: dict[str, dict] = {}
    for brief in briefs:
        if not isinstance(brief, dict):
            continue
        brief_id = _clean_text(brief.get(id_field))
        if brief_id:
            result[brief_id] = brief
    return result


def _video_by_brief_id(video_links: dict) -> dict[str, dict]:
    videos = video_links.get("videos")
    if not isinstance(videos, list):
        return {}
    result: dict[str, dict] = {}
    for video in videos:
        if not isinstance(video, dict):
            continue
        brief_id = _clean_text(video.get("brief_id")) or _clean_text(video.get("video_id"))
        title = _clean_text(video.get("title"))
        if brief_id and title:
            result[brief_id] = video
    return result


def _animation_by_brief_id(animation_data: dict) -> dict[str, dict]:
    animations = animation_data.get("animations")
    if not isinstance(animations, list):
        return {}
    result: dict[str, dict] = {}
    for animation in animations:
        if not isinstance(animation, dict):
            continue
        brief_id = _clean_text(animation.get("brief_id")) or _clean_text(animation.get("animation_id"))
        html = _clean_text(animation.get("html"))
        if brief_id and html:
            result[brief_id] = animation
    return result


def _append_markdown_block(blocks: list[dict], markdown: str) -> None:
    text = markdown.strip()
    if text:
        blocks.append({"type": "markdown", "markdown": text})


def _video_block(brief_id: str, brief: dict, video: dict | None) -> dict:
    video_title = _clean_text(video.get("title")) if isinstance(video, dict) else ""
    return {
        "type": "video",
        "brief_id": brief_id,
        "title": _clean_text(brief.get("title")) or video_title,
        "purpose": _clean_text(brief.get("purpose")),
        "status": "available" if isinstance(video, dict) else "unavailable",
        "videos": [video] if isinstance(video, dict) else [],
    }


def _animation_block(brief_id: str, brief: dict, animation: dict | None) -> dict:
    animation_title = _clean_text(animation.get("title")) if isinstance(animation, dict) else ""
    return {
        "type": "animation",
        "brief_id": brief_id,
        "title": _clean_text(brief.get("title")) or animation_title,
        "status": "available" if isinstance(animation, dict) else "unavailable",
        "html": _clean_text(animation.get("html")) if isinstance(animation, dict) else "",
    }


def _compose_section_content(
    section_markdown: dict,
    video_links: dict,
    animation_data: dict,
) -> dict:
    markdown = _clean_text(section_markdown.get("markdown"))
    video_briefs = _brief_by_id(section_markdown.get("video_briefs"), "video_id")
    animation_briefs = _brief_by_id(section_markdown.get("animation_briefs"), "animation_id")
    videos = _video_by_brief_id(video_links)
    animations = _animation_by_brief_id(animation_data)

    blocks: list[dict] = []
    cursor = 0
    for match in _RESOURCE_PLACEHOLDER_PATTERN.finditer(markdown):
        _append_markdown_block(blocks, markdown[cursor:match.start()])
        brief_id = match.group("id")
        if match.group("kind") == "video":
            blocks.append(_video_block(brief_id, video_briefs.get(brief_id, {}), videos.get(brief_id)))
        else:
            blocks.append(_animation_block(brief_id, animation_briefs.get(brief_id, {}), animations.get(brief_id)))
        cursor = match.end()
    _append_markdown_block(blocks, markdown[cursor:])

    return {
        "section_id": _clean_text(section_markdown.get("section_id")),
        "parent_section_id": section_markdown.get("parent_section_id"),
        "title": _clean_text(section_markdown.get("title")),
        "markdown": markdown,
        "blocks": blocks,
        "generated_at": _now_iso(),
    }


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


def _text_items(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_clean_text(item) for item in value if _clean_text(item)]


def _local_section_markdown(outline: dict, section: dict) -> dict:
    section_id = _clean_text(section.get("section_id"))
    title = _clean_text(section.get("title")) or section_id
    course_name = _clean_text(outline.get("course_name")) or "当前课程"
    description = _clean_text(section.get("description")) or f"围绕「{title}」完成本小节学习。"
    knowledge_points = _text_items(section.get("key_knowledge_points"))
    knowledge_lines = "\n".join(f"- {item}" for item in knowledge_points) or "- 明确核心概念\n- 完成可检查的学习产出"
    markdown = "\n\n".join([
        f"# {title}",
        f"## 学习目标\n围绕《{course_name}》的 {section_id} 小节，先理解本节目标，再把目标落到可执行任务。",
        f"## 核心概念\n{knowledge_lines}",
        f"## 步骤讲解\n1. 阅读小节说明：{description}\n2. 对照核心概念整理自己的理解。\n3. 把理解转成一个最小练习或交付物。",
        "<!-- video:id=video_1 -->",
        "## 练习任务\n用 10 到 15 分钟写下本节的输入、输出、完成标准，并补充一个你最容易卡住的问题。",
        "<!-- animation:id=anim_1 -->",
        "## 检查标准\n- 能用自己的话解释本节目标。\n- 能列出本节至少 2 个关键知识点。\n- 能给出一个可以验证完成度的小产出。",
    ])
    return {
        "section_id": section_id,
        "parent_section_id": section.get("parent_section_id"),
        "title": title,
        "markdown": markdown,
        "video_briefs": [
            {
                "video_id": "video_1",
                "title": f"{title}导入视频",
                "purpose": "用短视频建立本节直觉，再回到文档完成练习。",
            }
        ],
        "animation_briefs": [
            {
                "animation_id": "anim_1",
                "title": f"{title}流程动画",
                "concept": f"展示「{title}」从目标到练习再到检查标准的推进关系。",
                "visual_elements": ["学习目标", "练习任务", "检查标准"],
                "motion": "三个节点依次淡入，并用连线表示递进关系。",
                "space": "正文宽度的 100%，高度 320px。",
                "placement_hint": "练习任务之后",
            }
        ],
    }


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
        brief_id = _clean_text(video_data.get("brief_id")) or _clean_text(video_data.get("video_id"))

        normalized.append(
            {
                "brief_id": brief_id,
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
                "brief_id": animation_id,
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
    async def generate_markdown(section: dict) -> tuple[str, dict]:
        target_section_id = _clean_text(section.get("section_id"))
        if not target_section_id:
            return "", {}
        markdown_data = await _run_with_retries(
            lambda: _invoke_resource_chain(
                chain,
                _markdown_input(outline, section),
                SectionMarkdownOutput,
                timeout_seconds=_MARKDOWN_TIMEOUT_SECONDS,
            ),
            fallback=_local_section_markdown(outline, section),
            attempts=1,
        )
        if _clean_text(markdown_data.get("error")):
            return target_section_id, {"error": _clean_text(markdown_data.get("error"))}
        if not _clean_text(markdown_data.get("markdown")):
            markdown_data = _local_section_markdown(outline, section)

        animation_briefs = markdown_data.get("animation_briefs")
        video_briefs = markdown_data.get("video_briefs")
        return target_section_id, {
            "section_id": target_section_id,
            "parent_section_id": section.get("parent_section_id"),
            "title": _clean_text(section.get("title")) or _clean_text(markdown_data.get("title")),
            "markdown": _clean_text(markdown_data.get("markdown")),
            "video_briefs": video_briefs if isinstance(video_briefs, list) else [],
            "animation_briefs": animation_briefs if isinstance(animation_briefs, list) else [],
            "generated_at": _now_iso(),
        }

    section_markdowns: dict[str, dict] = {}
    markdown_results = await asyncio.gather(*(generate_markdown(section) for section in target_sections))
    for target_section_id, markdown_value in markdown_results:
        if not target_section_id:
            continue
        if _clean_text(markdown_value.get("error")):
            return {"error": _clean_text(markdown_value.get("error")), "hard_error": True}
        section_markdowns[target_section_id] = markdown_value

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

    async def generate_video_links(section: dict) -> tuple[str, dict]:
        target_section_id = _clean_text(section.get("section_id"))
        if not target_section_id:
            return "", {}

        video_data = await _run_with_retries(
            lambda: _invoke_resource_chain(
                chain,
                _video_input(outline, section),
                SectionVideoSearchOutput,
                timeout_seconds=_VIDEO_TIMEOUT_SECONDS,
            ),
            fallback={"query": "", "videos": []},
            attempts=2,
        )

        return target_section_id, {
            "section_id": target_section_id,
            "parent_section_id": section.get("parent_section_id"),
            "title": _section_title(outline, section),
            "query": _clean_text(video_data.get("query")),
            "videos": _normalize_videos(video_data.get("videos")),
            "generated_at": _now_iso(),
        }

    section_video_links: dict[str, dict] = {}
    video_results = await asyncio.gather(*(generate_video_links(section) for section in target_sections))
    for target_section_id, video_value in video_results:
        if target_section_id:
            section_video_links[target_section_id] = video_value

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

    section_markdowns = outline.get("section_markdowns")
    async def generate_html_animations(section: dict) -> tuple[str, dict]:
        target_section_id = _clean_text(section.get("section_id"))
        if not target_section_id:
            return "", {}

        section_markdown = {}
        if isinstance(section_markdowns, dict):
            value = section_markdowns.get(target_section_id)
            if isinstance(value, dict):
                section_markdown = value
        animation_briefs = section_markdown.get("animation_briefs")

        animation_data = {"animations": []}
        if isinstance(animation_briefs, list) and animation_briefs:
            animation_data = await _run_with_retries(
                lambda: _invoke_resource_chain(
                    chain,
                    _animation_input(outline, section),
                    SectionHtmlAnimationOutput,
                    timeout_seconds=_ANIMATION_TIMEOUT_SECONDS,
                ),
                fallback={"animations": []},
                attempts=1,
            )

        return target_section_id, {
            "section_id": target_section_id,
            "parent_section_id": section.get("parent_section_id"),
            "title": _section_title(outline, section),
            "animations": _normalize_animations(animation_data.get("animations"), animation_briefs),
            "generated_at": _now_iso(),
        }

    section_html_animations: dict[str, dict] = {}
    animation_results = await asyncio.gather(*(generate_html_animations(section) for section in target_sections))
    for target_section_id, animation_value in animation_results:
        if target_section_id:
            section_html_animations[target_section_id] = animation_value

    updated_outline = _merge_course_resource_data(outline, "section_html_animations", section_html_animations)
    section_composed_markdowns: dict[str, dict] = {}
    section_video_links = updated_outline.get("section_video_links")
    if isinstance(section_markdowns, dict):
        for section_id in target_section_ids:
            markdown_value = section_markdowns.get(section_id)
            video_value = section_video_links.get(section_id) if isinstance(section_video_links, dict) else {}
            animation_value = section_html_animations.get(section_id, {})
            if isinstance(markdown_value, dict):
                section_composed_markdowns[section_id] = _compose_section_content(
                    markdown_value,
                    video_value if isinstance(video_value, dict) else {},
                    animation_value if isinstance(animation_value, dict) else {},
                )
    if section_composed_markdowns:
        updated_outline = _merge_course_resource_data(
            updated_outline,
            "section_composed_markdowns",
            section_composed_markdowns,
        )
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
        yield {"event": "error", "message": "请先生成课程大纲。", "recoverable": True}
        return

    try:
        target_sections = _target_sections_for_scope(outline, chapter_section_id, "chapter_sections")
    except ValueError as exc:
        yield {"event": "error", "message": str(exc), "recoverable": True}
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

    markdown_args = {"course_id": course_id, "section_id": chapter_section_id, "scope": "chapter_sections"}
    if regeneration_focus:
        markdown_args["regeneration_focus"] = regeneration_focus
    markdown_result = await run_section_markdown_agent(state, llm, markdown_args)
    if markdown_result.get("error"):
        yield {"event": "error", "message": str(markdown_result["error"]), "recoverable": True}
        return

    state = {**state, **markdown_result}
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
            "stepId": f"leaf-section-{section_id}-resources",
            "kind": "course_resource_section",
            "agent": "section_resource_agents",
            "label": f"{section_id} 资源并行",
            "message": "视频检索和 HTML 动画生成正在并行推进",
            "course_id": course_id,
            "chapter_section_id": chapter_section_id,
            "section_id": section_id,
            "phase": "resources",
            "status": "running",
            "parallelGroup": f"leaf-section-{section_id}-resources",
        }

    video_result = await run_section_video_search_agent(state, search_llm)
    if video_result.get("error"):
        yield {"event": "error", "message": str(video_result["error"]), "recoverable": True}
        return
    state = {**state, **video_result}
    animation_result = await run_section_html_animation_agent(state, llm)
    if animation_result.get("error"):
        yield {"event": "error", "message": str(animation_result["error"]), "recoverable": True}
        return
    state = {**state, **animation_result}

    for section_id in section_ids:
        yield {
            "event": "agent_result",
            "stepId": f"leaf-section-{section_id}-resources",
            "kind": "course_resource_section",
            "agent": "section_resource_agents",
            "label": f"{section_id} 资源",
            "summary": "视频、动画与正文已拼装保存",
            "course_id": course_id,
            "chapter_section_id": chapter_section_id,
            "section_id": section_id,
            "phase": "compose",
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
