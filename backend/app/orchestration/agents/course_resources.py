from __future__ import annotations

import asyncio
import html
import json
import logging
import re
from collections.abc import AsyncGenerator, Awaitable, Callable
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote
from urllib.parse import urlparse

import httpx
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, ToolMessage
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

_RESOURCE_TIMEOUT_SECONDS = 180.0
_MARKDOWN_TIMEOUT_SECONDS = 180.0
_MARKDOWN_ATTEMPTS = 3
_VIDEO_TIMEOUT_SECONDS = 180.0
_ANIMATION_TIMEOUT_SECONDS = 180.0
_VIDEO_METADATA_TIMEOUT_SECONDS = 8.0
_VIDEO_VERIFIED_QUERY_LIMIT = 6


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_text(value: object) -> str:
    text = str(value).strip()
    if not text or text.lower() in {"none", "null"}:
        return ""
    return text


def _chapter_resource_error_event(
    message: str,
    *,
    course_id: str,
    chapter_section_id: str,
    phase: str,
    step_id: str | None = None,
    agent: str | None = None,
    label: str | None = None,
    section_ids: list[str] | None = None,
) -> dict:
    event: dict[str, Any] = {
        "event": "error",
        "message": message,
        "recoverable": True,
        "course_id": course_id,
        "chapter_section_id": chapter_section_id,
        "kind": "course_resource_chapter",
        "phase": phase,
        "status": "error",
    }
    if step_id:
        event["stepId"] = step_id
    if agent:
        event["agent"] = agent
    if label:
        event["label"] = label
    if section_ids:
        event["section_ids"] = section_ids
    return event


_RESOURCE_PLACEHOLDER_PATTERN = re.compile(
    r"<!--\s*(?P<kind>video|animation):id=(?P<id>[A-Za-z0-9_.:-]+)\s*-->"
)
_JSON_CODE_BLOCK_PATTERN = re.compile(r"^```(?:json)?\s*(?P<body>.*?)```\s*$", re.DOTALL | re.IGNORECASE)
_MARKDOWN_CODE_BLOCK_PATTERN = re.compile(r"^```(?:markdown|md)?\s*(?P<body>.*?)```\s*$", re.DOTALL | re.IGNORECASE)


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
                logger.warning(
                    "Resource action failed after %s attempts: %s: %r",
                    attempts,
                    type(exc).__name__,
                    exc,
                )
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
    if hasattr(output, "content"):
        output = output.content
    if isinstance(output, str):
        text = output.strip()
        json_text = _extract_json_object_text(text)
        if json_text:
            output = json.loads(json_text)
        elif output_schema is SectionMarkdownOutput:
            output = _section_markdown_data_from_plain_text(text, query)
        elif output_schema is SectionHtmlAnimationOutput:
            output = _section_animation_data_from_plain_text(text, query)
        else:
            output = json.loads(text)
    return _normalize_resource_chain_output(output, output_schema, query)


def _extract_json_object_text(text: str) -> str:
    clean_text = text.strip()
    if not clean_text:
        return ""
    code_block_match = re.search(r"```json\s*(?P<body>.*?)```", clean_text, re.DOTALL | re.IGNORECASE)
    if code_block_match:
        body = code_block_match.group("body").strip()
        if body.startswith("{") and body.endswith("}"):
            return body
    start = clean_text.find("{")
    end = clean_text.rfind("}")
    if start == 0 and end > start:
        return clean_text[start:end + 1]
    if start > 0 and end > start and "<" not in clean_text[:start]:
        return clean_text[start:end + 1]
    return ""


def _resource_payload_from_query(query: str) -> dict:
    _prefix, separator, raw_payload = query.partition("输入：")
    if not separator:
        return {}
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _plain_markdown_text(text: str) -> str:
    clean_text = text.strip()
    code_block_match = _MARKDOWN_CODE_BLOCK_PATTERN.match(clean_text)
    if code_block_match:
        return code_block_match.group("body").strip()
    heading_match = re.search(r"(?m)^#\s+", clean_text)
    if heading_match:
        return clean_text[heading_match.start():].strip()
    return clean_text


def _plain_html_text(text: str) -> str:
    clean_text = text.strip()
    code_block_match = _MARKDOWN_CODE_BLOCK_PATTERN.match(clean_text)
    if code_block_match:
        return code_block_match.group("body").strip()
    html_start = clean_text.lower().find("<!doctype")
    if html_start < 0:
        html_start = clean_text.lower().find("<html")
    if html_start < 0:
        html_start = clean_text.lower().find("<section")
    if html_start >= 0:
        return clean_text[html_start:].strip()
    return clean_text


def _section_markdown_data_from_plain_text(text: str, query: str) -> dict:
    markdown = _plain_markdown_text(text)
    payload = _resource_payload_from_query(query)
    section = payload.get("target_section")
    section_data = section if isinstance(section, dict) else {}
    section_id = _clean_text(section_data.get("section_id"))
    parent_section_id = section_data.get("parent_section_id")
    parent_id = parent_section_id if isinstance(parent_section_id, str) else None
    title = _clean_text(section_data.get("title")) or section_id
    description = _clean_text(section_data.get("description"))
    knowledge_points = _text_items(section_data.get("key_knowledge_points"))
    topic_text = "、".join([item for item in [title, *knowledge_points] if item])
    purpose_topic = topic_text or description or title

    video_briefs = [
        {
            "video_id": video_id,
            "title": f"{title}教学视频",
            "purpose": f"帮助学习者理解{purpose_topic}，并把本节内容落到可验收任务。",
        }
        for video_id in _extract_brief_ids_from_markdown(markdown, "video")
    ]
    visual_elements = knowledge_points[:3] or [title, "练习任务", "检查标准"]
    animation_briefs = [
        {
            "animation_id": animation_id,
            "title": f"{title}流程动画",
            "concept": f"展示{purpose_topic}如何转成步骤、练习任务和检查标准。",
            "visual_elements": visual_elements,
            "motion": "关键节点依次通过 opacity 淡入，并用 transform 表现轻微位移。",
            "space": "正文宽度 100%，高度 320px。",
            "placement_hint": "练习任务之前或之后。",
        }
        for animation_id in _extract_brief_ids_from_markdown(markdown, "animation")
    ]

    return {
        "section_id": section_id,
        "parent_section_id": parent_id,
        "title": title,
        "markdown": markdown,
        "video_briefs": video_briefs,
        "animation_briefs": animation_briefs,
    }


def _normalize_section_markdown_output(output: object, query: str) -> dict:
    if hasattr(output, "model_dump"):
        output = output.model_dump()
    if not isinstance(output, dict):
        return _section_markdown_data_from_plain_text(_clean_text(output), query)

    payload = _resource_payload_from_query(query)
    section = payload.get("target_section")
    section_data = section if isinstance(section, dict) else {}
    markdown = _clean_text(output.get("markdown"))
    plain_data = _section_markdown_data_from_plain_text(markdown, query)
    parent_section_id = output.get("parent_section_id")
    plain_data.update(
        {
            "section_id": _clean_text(output.get("section_id")) or plain_data["section_id"],
            "parent_section_id": parent_section_id if isinstance(parent_section_id, str) else plain_data["parent_section_id"],
            "title": _clean_text(output.get("title")) or _clean_text(section_data.get("title")) or plain_data["title"],
            "markdown": markdown,
        }
    )

    video_briefs = _normalize_markdown_video_briefs(section_data, output.get("video_briefs"))
    if video_briefs:
        plain_data["video_briefs"] = video_briefs
    animation_briefs = _normalize_markdown_animation_briefs(section_data, output.get("animation_briefs"))
    if animation_briefs:
        plain_data["animation_briefs"] = animation_briefs
    return plain_data


def _section_animation_data_from_plain_text(text: str, query: str) -> dict:
    html_text = _plain_html_text(text)
    payload = _resource_payload_from_query(query)
    section = payload.get("target_section")
    section_data = section if isinstance(section, dict) else {}
    section_id = _clean_text(section_data.get("section_id"))
    animation_briefs = payload.get("animation_briefs")
    if not isinstance(animation_briefs, list):
        animation_briefs = []

    animations = []
    for brief in animation_briefs:
        if not isinstance(brief, dict):
            continue
        animation_id = _clean_text(brief.get("animation_id"))
        if not animation_id:
            continue
        animations.append(
            {
                "animation_id": animation_id,
                "title": _clean_text(brief.get("title")),
                "html": html_text,
            }
        )
        break

    return {
        "section_id": section_id,
        "animations": animations,
    }


def _normalize_section_video_output(output: object, query: str) -> dict:
    if hasattr(output, "model_dump"):
        output = output.model_dump()
    if not isinstance(output, dict):
        output = {"videos": []}
    payload = _resource_payload_from_query(query)
    section = payload.get("target_section")
    section_data = section if isinstance(section, dict) else {}
    return {
        "section_id": _clean_text(output.get("section_id")) or _clean_text(section_data.get("section_id")),
        "query": _clean_text(output.get("query")),
        "videos": output.get("videos") if isinstance(output.get("videos"), list) else [],
    }


def _normalize_section_animation_output(output: object, query: str) -> dict:
    if hasattr(output, "model_dump"):
        output = output.model_dump()
    if not isinstance(output, dict):
        return _section_animation_data_from_plain_text(_clean_text(output), query)
    payload = _resource_payload_from_query(query)
    section = payload.get("target_section")
    section_data = section if isinstance(section, dict) else {}
    animations = output.get("animations")
    if not isinstance(animations, list):
        html_value = _clean_text(output.get("html"))
        if html_value:
            return _section_animation_data_from_plain_text(html_value, query)
        animations = []
    return {
        "section_id": _clean_text(output.get("section_id")) or _clean_text(section_data.get("section_id")),
        "animations": animations,
    }


def _normalize_resource_chain_output(output: object, output_schema: Any, query: str) -> dict:
    if output_schema is SectionMarkdownOutput:
        return _normalize_section_markdown_output(output, query)
    if output_schema is SectionVideoSearchOutput:
        return _normalize_section_video_output(output, query)
    if output_schema is SectionHtmlAnimationOutput:
        return _normalize_section_animation_output(output, query)
    if hasattr(output, "model_dump"):
        return output.model_dump()
    return output if isinstance(output, dict) else {}


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


_CHINESE_CHAPTER_NUMBERS = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}
_CHINESE_CHAPTER_PATTERN = re.compile(r"第\s*([一二三四五六七八九十\d]+)\s*章")
_ENGLISH_CHAPTER_PATTERN = re.compile(r"\bchapter\s*(\d+)\b", re.IGNORECASE)


def _root_sections(outline: dict) -> list[dict]:
    return sorted(
        [section for section in _sections(outline) if int(section.get("depth", 1)) == 1],
        key=lambda item: int(item.get("order_index", 0)),
    )


def _normalized_section_text(value: object) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", _clean_text(value).lower())


def _chapter_index_from_reference(reference: str) -> int | None:
    chinese_match = _CHINESE_CHAPTER_PATTERN.search(reference)
    if chinese_match:
        raw = chinese_match.group(1).strip()
        if raw.isdigit():
            return int(raw)
        return _CHINESE_CHAPTER_NUMBERS.get(raw)

    english_match = _ENGLISH_CHAPTER_PATTERN.search(reference)
    if english_match:
        return int(english_match.group(1))

    return None


def _resolve_root_section_for_reference(outline: dict, reference: str) -> dict | None:
    reference_text = _clean_text(reference)
    if not reference_text:
        return None

    direct_section = _section_by_id(outline, reference_text)
    if isinstance(direct_section, dict):
        if int(direct_section.get("depth", 1)) == 1:
            return direct_section
        root_id = _root_section_id_for_section(outline, direct_section)
        return _section_by_id(outline, root_id)

    roots = _root_sections(outline)
    chapter_index = _chapter_index_from_reference(reference_text)
    if chapter_index is not None and 1 <= chapter_index <= len(roots):
        return roots[chapter_index - 1]

    normalized_reference = _normalized_section_text(reference_text)
    if not normalized_reference:
        return None

    for root in roots:
        root_id = _clean_text(root.get("section_id"))
        root_title = _clean_text(root.get("title"))
        title_key = _normalized_section_text(root_title)
        labeled_key = _normalized_section_text(f"{root_id} {root_title}")
        if title_key and title_key in normalized_reference:
            return root
        if labeled_key and labeled_key in normalized_reference:
            return root

    return None


def _target_sections_for_scope(outline: dict, section_id: str, scope: str) -> list[dict]:
    sections = sorted(_sections(outline), key=lambda item: int(item.get("order_index", 0)))
    if scope == "single_section":
        section = _section_by_id(outline, section_id)
        if not section or int(section.get("depth", 1)) <= 1:
            raise ValueError("指定小节无法定位。")
        return [section]
    if scope == "chapter_sections":
        parent = _resolve_root_section_for_reference(outline, section_id)
        if not parent or int(parent.get("depth", 1)) != 1:
            raise ValueError("指定章节无法定位。")
        parent_id = _clean_text(parent.get("section_id"))
        return [
            section for section in sections
            if section.get("parent_section_id") == parent_id and int(section.get("depth", 1)) > 1
        ]
    if scope == "course_sections":
        raise ValueError("系统一次只能生成一章的具体内容。")

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


def _root_section_id_for_section(outline: dict, section: dict) -> str:
    current = section
    visited: set[str] = set()
    while isinstance(current, dict):
        current_id = _clean_text(current.get("section_id"))
        parent_id = current.get("parent_section_id")
        if not isinstance(parent_id, str) or not parent_id.strip():
            return current_id
        parent_key = parent_id.strip()
        if parent_key in visited:
            return current_id
        visited.add(parent_key)
        parent = _section_by_id(outline, parent_key)
        if parent is None:
            return parent_key
        current = parent
    return ""


def _chapter_sections_for_section(outline: dict, section: dict) -> list[dict]:
    root_id = _root_section_id_for_section(outline, section)
    if not root_id:
        return [section]
    sections = sorted(_sections(outline), key=lambda item: int(item.get("order_index", 0)))
    included_ids = {root_id}
    changed = True
    while changed:
        changed = False
        for item in sections:
            section_id = _clean_text(item.get("section_id"))
            parent_id = item.get("parent_section_id")
            if not section_id or not isinstance(parent_id, str):
                continue
            if parent_id in included_ids and section_id not in included_ids:
                included_ids.add(section_id)
                changed = True
    return [item for item in sections if _clean_text(item.get("section_id")) in included_ids]


def _chapter_learning_sequence(outline: dict, root_section: dict | None) -> list[str]:
    if not isinstance(root_section, dict):
        return []
    root_title = _clean_text(root_section.get("title"))
    learning_sequence = _text_items(outline.get("learning_sequence"))
    filtered = [item for item in learning_sequence if root_title and root_title in item]
    if filtered:
        return filtered[:1]
    if root_title:
        return [root_title]
    return []


def _chapter_course_knowledge_context(outline: dict, section: dict) -> dict:
    chapter_sections = _chapter_sections_for_section(outline, section)
    chapter_ids = {
        section_id
        for section_id in (_clean_text(item.get("section_id")) for item in chapter_sections)
        if section_id
    }
    root_section = next(
        (
            item for item in chapter_sections
            if isinstance(item, dict) and item.get("parent_section_id") is None
        ),
        chapter_sections[0] if chapter_sections else None,
    )
    root_title = _clean_text(root_section.get("title")) if isinstance(root_section, dict) else ""
    root_description = _clean_text(root_section.get("description")) if isinstance(root_section, dict) else ""
    context = {
        "course_id": outline.get("course_id", ""),
        "course_name": outline.get("course_name", ""),
        "grade_year": outline.get("grade_year", ""),
        "personalization_summary": (
            f"当前只生成「{root_title}」这一章的具体教学内容。{root_description}"
            if root_title
            else "当前只生成指定章节的具体教学内容。"
        ),
        "sections": chapter_sections,
        "learning_sequence": _chapter_learning_sequence(outline, root_section),
        "total_estimated_hours": outline.get("total_estimated_hours", ""),
    }
    for field_name in (
        "section_markdowns",
        "section_video_links",
        "section_html_animations",
        "section_composed_markdowns",
    ):
        values = outline.get(field_name)
        if not isinstance(values, dict):
            continue
        context[field_name] = {
            section_id: value
            for section_id, value in values.items()
            if section_id in chapter_ids
        }
    return context


def _year_learning_paths_context(state: OrchestrationState, outline: dict, section: dict) -> dict:
    year_learning_paths = state.get("year_learning_paths")
    if not isinstance(year_learning_paths, dict):
        return {}
    grade_year = _clean_text(outline.get("grade_year"))
    course_id = _clean_text(outline.get("course_id"))
    path = year_learning_paths.get(grade_year)
    if not isinstance(path, dict):
        return {}

    current = path.get("current_learning_course")
    current_course: dict = {}
    if isinstance(current, dict) and current.get("course_node_id") == course_id:
        current_course = {
            "grade_id": current.get("grade_id", grade_year),
            "course_node_id": current.get("course_node_id", course_id),
            "course_or_chapter_theme": current.get("course_or_chapter_theme", outline.get("course_name", "")),
            "course_goal": current.get("course_goal", ""),
            "current_focus": "",
            "next_action": "",
            "progress_state": current.get("progress_state", ""),
        }

    root_id = _root_section_id_for_section(outline, section)
    root_section = _section_by_id(outline, root_id) if root_id else None
    root_title = _clean_text(root_section.get("title")) if isinstance(root_section, dict) else ""
    root_description = _clean_text(root_section.get("description")) if isinstance(root_section, dict) else ""
    if current_course:
        current_course["current_focus"] = root_description or f"围绕「{root_title}」完成当前章内容。"
        current_course["next_action"] = f"生成并验收「{root_title}」这一章的叶子小节教学内容。" if root_title else "生成并验收当前章叶子小节教学内容。"

    resource_contract = {}
    contract = path.get("resource_generation_contract")
    if isinstance(contract, dict):
        resource_contract = dict(contract)
        directions = contract.get("resource_directions")
        if isinstance(directions, list):
            resource_contract["resource_directions"] = [
                direction
                for direction in directions
                if isinstance(direction, dict)
                and course_id in _text_items(direction.get("target_node_ids"))
            ]

    return {
        grade_year: {
            "schema_version": path.get("schema_version", ""),
            "current_learning_course": current_course,
            "resource_generation_contract": resource_contract,
        }
    }


def _resource_context(state: OrchestrationState, outline: dict, section: dict) -> dict:
    profile = state.get("profile")
    return {
        "profile": profile if isinstance(profile, dict) else {},
        "year_learning_paths": _year_learning_paths_context(state, outline, section),
        "course_knowledge": _chapter_course_knowledge_context(outline, section),
    }


def _current_learning_course_context(state: OrchestrationState, outline: dict) -> dict:
    year_learning_paths = state.get("year_learning_paths")
    if not isinstance(year_learning_paths, dict):
        return {}
    grade_year = _clean_text(outline.get("grade_year"))
    course_id = _clean_text(outline.get("course_id"))
    path = year_learning_paths.get(grade_year)
    if not isinstance(path, dict):
        return {}
    current = path.get("current_learning_course")
    if isinstance(current, dict) and current.get("course_node_id") == course_id:
        return current
    return {}


def _markdown_input(state: OrchestrationState, outline: dict, section: dict) -> str:
    context = _resource_context(state, outline, section)
    payload = {
        **context,
        "parent_section": _parent_section(outline, section),
        "target_section": section,
    }
    return (
        "请为输入小节生成完整 Markdown 教学文档，不要写摘要，不要压缩为提纲。"
        "markdown 字段必须写到不少于 1800 个中文字符；"
        "如果一次想到的内容不够长，就继续补充概念解释、步骤细节、练习验收和常见误区，直到达到长度。"
        "最终只输出一个 JSON 对象。\n\n"
        f"输入：{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def _markdown_repair_input(
    state: OrchestrationState,
    outline: dict,
    section: dict,
    quality_issue: str,
    previous_markdown: str,
) -> str:
    context = _resource_context(state, outline, section)
    payload = {
        **context,
        "parent_section": _parent_section(outline, section),
        "target_section": section,
        "markdown_quality_issue": quality_issue,
        "previous_markdown": previous_markdown[:3000],
    }
    return (
        "上一版 Markdown 教学文档未通过质量检查。请基于同一个小节重新生成，"
        "必须修正 markdown_quality_issue 指出的具体问题。"
        "不要复述上一版，不要补几句话了事；请完整重写一份长文档 JSON。\n\n"
        "硬性要求：必须包含 ## 学习目标、## 核心概念、## 步骤讲解、## 练习任务、## 检查标准；"
        "正文不少于 1800 个中文字符；"
        "核心概念必须覆盖 target_section.key_knowledge_points 的每一个知识点；"
        "步骤讲解必须包含 Markdown 表格或 fenced code block 作为教学支架；"
        "必须包含与 video_briefs.video_id 完全一致的视频占位符；"
        "必须包含与 animation_briefs.animation_id 完全一致的动画占位符；"
        "禁止输出旧兜底文案、英文占位说明或资源不可用提示。\n\n"
        f"输入：{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def _text_items(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_clean_text(item) for item in value if _clean_text(item)]


def _ensure_resource_placeholder(markdown: str, kind: str, brief_id: str) -> str:
    placeholder = f"<!-- {kind}:id={brief_id} -->"
    if placeholder in markdown:
        return markdown
    exercise_heading = "## 练习任务"
    if exercise_heading in markdown:
        return markdown.replace(exercise_heading, f"{placeholder}\n\n{exercise_heading}", 1)
    return f"{markdown.rstrip()}\n\n{placeholder}"


def _rewrite_resource_placeholders(markdown: str, kind: str, brief_ids: list[str]) -> str:
    if not brief_ids:
        return markdown

    index = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal index
        if match.group("kind") != kind:
            return match.group(0)
        if index >= len(brief_ids):
            return ""
        brief_id = brief_ids[index]
        index += 1
        return f"<!-- {kind}:id={brief_id} -->"

    rewritten = _RESOURCE_PLACEHOLDER_PATTERN.sub(replace, markdown)
    for brief_id in brief_ids[index:]:
        rewritten = _ensure_resource_placeholder(rewritten, kind, brief_id)
    return rewritten


_REQUIRED_MARKDOWN_HEADING_TITLES = ("学习目标", "核心概念", "步骤讲解", "练习任务", "检查标准")
_MARKDOWN_HEADING_ALIASES = {
    "学习目标": ("学习目标", "本节目标"),
    "核心概念": ("核心概念",),
    "步骤讲解": ("步骤讲解", "实践步骤"),
    "练习任务": ("练习任务",),
    "检查标准": ("检查标准",),
}
_STEP_MARKER_PATTERN = re.compile(
    r"(第[一二三四五六七八九十]+步|步骤\s*\d+|^\s*\d+[.、]|step\s*\d+)",
    re.MULTILINE | re.IGNORECASE,
)


def _chinese_step_label(index: int) -> str:
    labels = {
        1: "一",
        2: "二",
        3: "三",
        4: "四",
        5: "五",
        6: "六",
        7: "七",
        8: "八",
        9: "九",
        10: "十",
    }
    if index in labels:
        return f"第{labels[index]}步"
    return f"步骤 {index}"


def _strip_markdown_heading_marker(line: str) -> str:
    text = line.strip()
    markdown_heading = re.match(r"^#{2,6}\s+(?P<title>.+)$", text)
    if markdown_heading:
        return markdown_heading.group("title").strip()
    return text


def _strip_markdown_title_decoration(text: str) -> str:
    value = text.strip()
    if value.startswith("**") and value.endswith("**"):
        value = value[2:-2].strip()
    return re.sub(r"^[^\w\u4e00-\u9fff]+", "", value).strip()


def _normalize_markdown_heading_line(line: str) -> str:
    heading_text = _strip_markdown_heading_marker(line)
    heading_text = _strip_markdown_title_decoration(heading_text)
    if not heading_text:
        return ""

    heading_title, separator, suffix = heading_text.partition("：")
    if not separator:
        heading_title, separator, suffix = heading_text.partition(":")
    heading_title = heading_title.strip()
    suffix = suffix.strip() if separator else ""

    for canonical_title, aliases in _MARKDOWN_HEADING_ALIASES.items():
        matched_alias = next((alias for alias in aliases if alias in heading_title), "")
        if not matched_alias:
            continue
        if not suffix:
            suffix = heading_title.split(matched_alias, 1)[1].strip(" ：:-—、")
        replacement = f"## {canonical_title}"
        return replacement + (f"\n{suffix}" if suffix else "")

    return ""


def _normalize_markdown_heading_variants(markdown: str) -> str:
    normalized_lines: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        replacement = ""
        is_heading = bool(re.match(r"^#{2,6}\s+", stripped))
        is_bold_title = bool(re.match(r"^\*\*.+\*\*\s*(?:[：:].*)?$", stripped))
        is_plain_required_title = any(stripped.startswith(title) for title in _REQUIRED_MARKDOWN_HEADING_TITLES)
        if is_heading or is_bold_title or is_plain_required_title:
            replacement = _normalize_markdown_heading_line(stripped)
        normalized_lines.append(replacement or line)
    return "\n".join(normalized_lines)


def _normalize_markdown_step_blocks(markdown: str) -> str:
    heading_pattern = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
    matches = list(heading_pattern.finditer(markdown))
    for index, match in enumerate(matches):
        if not match.group(1).strip().startswith("步骤讲解"):
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        body = markdown[start:end].strip()
        if not body or _STEP_MARKER_PATTERN.search(body):
            return markdown

        blocks = [block.strip() for block in re.split(r"\n\s*\n", body) if block.strip()]
        if not blocks:
            return markdown

        normalized_blocks: list[str] = []
        step_index = 1
        for block in blocks:
            if (
                block.startswith("```")
                or block.startswith("|")
                or block.startswith("<!--")
            ):
                normalized_blocks.append(block)
                continue
            normalized_blocks.append(f"{_chinese_step_label(step_index)}：{block}")
            step_index += 1

        normalized_body = "\n\n".join(normalized_blocks)
        return f"{markdown[:start]}{normalized_body}\n\n{markdown[end:].lstrip()}"
    return markdown


def _normalize_markdown_video_briefs(section: dict, video_briefs: object) -> list[dict]:
    normalized: list[dict] = []
    if isinstance(video_briefs, list):
        for brief in video_briefs:
            if hasattr(brief, "model_dump"):
                brief_data = brief.model_dump()
            elif isinstance(brief, dict):
                brief_data = dict(brief)
            else:
                continue
            video_id = _clean_text(brief_data.get("video_id"))
            title = _clean_text(brief_data.get("title"))
            purpose = _clean_text(brief_data.get("purpose"))
            if video_id and title and purpose:
                normalized.append({"video_id": video_id, "title": title, "purpose": purpose})

    if normalized:
        return normalized

    return []


def _normalize_markdown_animation_briefs(section: dict, animation_briefs: object) -> list[dict]:
    normalized: list[dict] = []
    if isinstance(animation_briefs, list):
        for brief in animation_briefs:
            if hasattr(brief, "model_dump"):
                brief_data = brief.model_dump()
            elif isinstance(brief, dict):
                brief_data = dict(brief)
            else:
                continue
            animation_id = _clean_text(brief_data.get("animation_id"))
            title = _clean_text(brief_data.get("title"))
            concept = _clean_text(brief_data.get("concept"))
            if not animation_id or not title or not concept:
                continue
            visual_elements = _text_items(brief_data.get("visual_elements"))
            normalized.append(
                {
                    "animation_id": animation_id,
                    "title": title,
                    "concept": concept,
                    "visual_elements": visual_elements,
                    "motion": _clean_text(brief_data.get("motion")),
                    "space": _clean_text(brief_data.get("space")),
                    "placement_hint": _clean_text(brief_data.get("placement_hint")),
                }
            )

    if normalized:
        return normalized

    return []


def _normalize_markdown_resources(markdown_data: dict, section: dict) -> dict:
    normalized = dict(markdown_data)
    markdown = _clean_text(normalized.get("markdown"))
    if not markdown:
        return normalized

    video_briefs = _normalize_markdown_video_briefs(section, normalized.get("video_briefs"))
    animation_briefs = _normalize_markdown_animation_briefs(section, normalized.get("animation_briefs"))
    markdown = _normalize_markdown_heading_variants(markdown)
    markdown = _normalize_markdown_step_blocks(markdown)
    markdown = _rewrite_resource_placeholders(
        markdown,
        "video",
        [brief["video_id"] for brief in video_briefs],
    )
    markdown = _rewrite_resource_placeholders(
        markdown,
        "animation",
        [brief["animation_id"] for brief in animation_briefs],
    )

    normalized["markdown"] = markdown
    normalized["video_briefs"] = video_briefs
    normalized["animation_briefs"] = animation_briefs
    return normalized


def _profile_learning_context_text(state: OrchestrationState) -> str:
    profile = state.get("profile")
    if not isinstance(profile, dict):
        return "本节采用项目实践驱动的教学设计，侧重动手实践与运行结果校验，以帮助学习者快速上手。"
    
    confirmed = profile.get("confirmed_info")
    confirmed_info = confirmed if isinstance(confirmed, dict) else {}
    
    grade = _clean_text(confirmed_info.get("current_grade"))
    major = _clean_text(confirmed_info.get("major"))
    preference = _clean_text(confirmed_info.get("learning_method_preference"))
    
    if grade in ("未知", "无", "暂无", "none", "null"):
        grade = ""
    if major in ("未知", "无", "暂无", "none", "null"):
        major = ""
    if preference in ("未知", "无", "暂无", "没有", "无偏好", "none", "null"):
        preference = ""
        
    background = ""
    if grade and major:
        background = f"{grade}{major}专业"
    elif grade:
        background = f"{grade}阶段"
    elif major:
        background = f"{major}专业"

    if background:
        if preference:
            return f"根据您{background}的背景，本节针对您偏好的{preference}方法进行教学设计，重点关注实战应用与运行证据留存。"
        else:
            return f"针对{background}的学习特点，本节采用项目实战设计，侧重实践与运行结果校验。"
    else:
        if preference:
            return f"根据您偏好的{preference}方法，本节采用项目实践驱动的教学设计，重点关注实战应用与运行证据留存。"
        else:
            return "本节采用项目实践驱动的教学设计，侧重动手实践与运行结果校验，以便快速掌握核心技能。"


def _deterministic_video_briefs(section: dict) -> list[dict]:
    title = _clean_text(section.get("title")) or _clean_text(section.get("section_id")) or "本节"
    knowledge_points = _text_items(section.get("key_knowledge_points"))
    focus = "、".join(knowledge_points[:2]) or title
    return [
        {
            "video_id": "video_1",
            "title": f"{title}实战讲解视频",
            "purpose": f"帮助学习者通过相近主题视频理解{focus}，并把本节内容转成可验收产出。",
        }
    ]


def _deterministic_animation_briefs(section: dict) -> list[dict]:
    title = _clean_text(section.get("title")) or _clean_text(section.get("section_id")) or "本节"
    knowledge_points = _text_items(section.get("key_knowledge_points"))
    visual_elements = knowledge_points[:3] or [title, "输入材料", "验收证据"]
    return [
        {
            "animation_id": "anim_1",
            "title": f"{title}流程动画",
            "concept": f"展示{title}如何从输入材料、处理步骤推进到验收证据。",
            "visual_elements": visual_elements,
            "motion": "关键节点依次通过 opacity 淡入，并只用 transform 表现轻微位移。",
            "space": "正文宽度 100%，高度 320px。",
            "placement_hint": "步骤讲解之后或练习任务之前。",
        }
    ]


def _deterministic_concept_block(point: str, section: dict, index: int) -> str:
    title = _clean_text(section.get("title")) or "本节"
    description = _clean_text(section.get("description")) or f"围绕{title}完成可验收学习任务。"
    
    mod = index % 3
    if mod == 1:
        return (
            f"### {point}\n"
            f"**定义**：{point}是「{title}」里用于明确数据边界的关键机制。\n\n"
            f"为了理清其在 RAG 系统中的作用，以下是其与其他常见方案的横向对比：\n\n"
            f"| 比较维度 | {point} 方案 | 传统/基础方案 | 核心优势 |\n"
            f"| --- | --- | --- | --- |\n"
            f"| 数据吞吐 | 适合高并发写入 | 单点写入瓶颈 | 降低资源阻塞率 |\n"
            f"| 检索相关性 | 稠密向量语义对齐 | 关键词匹配 | 提升复杂 Query 召回率 |\n\n"
            f"**适用场景**：在大规模非结构化文档导入和召回退化场景下，优先配置本机制以确保召回的准确性。\n\n"
            f"**如何验证**：通过运行后检查向量数据库的索引一致性日志进行掌握验收。"
        )
    elif mod == 2:
        return (
            f"### {point}\n"
            f"**概念解析**：{point}在工程落地上通常对应特定的初始化参数配置与资源分配。\n\n"
            f"在实际开发中，可以通过如下典型的 Python 伪代码来进行组件初始化与高并发配置：\n\n"
            f"```python\n"
            f"# {point} 核心配置与并发限制初始化\n"
            f"import asyncio\n\n"
            f"class VectorIngestionPipeline:\n"
            f"    def __init__(self, batch_size: int = 64, max_concurrency: int = 5):\n"
            f"        self.batch_size = batch_size\n"
            f"        self.semaphore = asyncio.Semaphore(max_concurrency)\n"
            f"        # 初始化映射维度\n"
            f"        self.dimension = 1024  # 对齐 BGE-large-zh 维度\n"
            f"```\n\n"
            f"**常见边界**：注意在高并发写入时控制 Batch Size，以防止 API 触发 429 限流或本地 PyTorch 显存溢出 (OOM)。"
        )
    else:
        return (
            f"### {point}\n"
            f"**基本概念**：{point}是保证本地问答系统最终召回结果连续性不可或缺的一环，直指「{description}」的底层落地。\n\n"
            f"**常见错误与排查步骤**：\n"
            f"1. **维度不匹配错误 (Dimension Mismatch)**：通常表现为后端报错 `ValueError`。请打印 Query 向量与 Doc 向量的 `.shape` 确认是否完全对齐。\n"
            f"2. **上下文断裂**：分块块间重叠率 (Overlap) 设置过低。建议将 overlap 调整在 10% - 20% 之间。\n\n"
            f"**验收标准**：通过运行测试问题，确认召回的 Chunk 没有出现文本截断，并且能被下游大模型解析。"
        )


def _deterministic_section_markdown_data(
    state: OrchestrationState,
    outline: dict,
    section: dict,
) -> dict:
    section_id = _clean_text(section.get("section_id"))
    title = _clean_text(section.get("title")) or section_id or "本节"
    parent = _parent_section(outline, section) or {}
    parent_title = _clean_text(parent.get("title")) or "当前章节"
    description = _clean_text(section.get("description")) or f"围绕{title}建立可执行学习产出。"
    course_name = _clean_text(outline.get("course_name")) or "构建本地知识库问答系统 (RAG基础)"
    profile_text = _profile_learning_context_text(state)
    knowledge_points = _text_items(section.get("key_knowledge_points")) or [title]
    video_briefs = _deterministic_video_briefs(section)
    animation_briefs = _deterministic_animation_briefs(section)

    concept_blocks = [
        _deterministic_concept_block(point, section, index + 1)
        for index, point in enumerate(knowledge_points)
    ]
    first_point = knowledge_points[0]
    second_point = knowledge_points[1] if len(knowledge_points) > 1 else first_point
    third_point = knowledge_points[2] if len(knowledge_points) > 2 else second_point

    markdown = "\n\n".join([
        f"# {section_id} {title}",
        (
            "## 学习目标\n"
            f"本节属于《{course_name}》第一章「{parent_title}」，目标不是泛泛了解概念，而是把「{title}」变成能在本地 RAG 项目中复用的工作方法。"
            f"学习者需要围绕「{description}」完成三类结果：一份可解释的处理规则、一组能复查的样例输出，以及一张说明后续检索质量如何受影响的检查表。\n\n"
            f"结合当前画像：{profile_text}。因此本节安排会偏向项目驱动和证据留存，每一步都要求留下表格、日志、截图或口头解释，避免只读完文档却不知道自己是否真正掌握。完成后，学习者应该能把任意一份 PDF、Markdown 或技术文档放进处理流程，说明每个清洗和分块决策的依据。"
        ),
        "## 核心概念\n" + "\n\n".join(concept_blocks),
        (
            "## 步骤讲解\n"
            f"第一步：准备输入样本。输入材料是一份包含标题、正文、列表、代码块或页码信息的非结构化文档；具体动作是记录文件来源、格式、页数、编码和明显噪声；判断依据是样本能覆盖「{first_point}」会遇到的正常情况与异常情况；产出物是一张输入登记表。\n\n"
            f"第二步：设计处理规则。输入材料是登记表和本节关键知识点；具体动作是为「{first_point}」「{second_point}」分别写出处理前、处理后、失败条件和人工复查方式；判断依据是规则是否能被另一个人照着执行；产出物是一份 cleaning_and_chunking_rules.md。\n\n"
            f"第三步：运行小样本验证。输入材料是 3 到 5 段真实文本；具体动作是按规则完成清洗、分块、重叠率或元数据处理；判断依据是每个 chunk 都能追溯到原文位置，并且没有明显乱码、空白或上下文断裂；产出物是一份分块样例表。\n\n"
            f"第四步：连接后续 RAG 检索。输入材料是分块样例表；具体动作是标注哪些 chunk 适合进入向量化，哪些应该剔除或合并，并解释「{third_point}」对召回率、答案完整性或上下文连续性的影响；判断依据是能用一个测试问题说明为什么这些 chunk 会被召回；产出物是一份检索影响说明。\n\n"
            "| 步骤 | 输入材料 | 具体动作 | 产出物 | 验收方式 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 输入登记 | 原始文档 | 记录来源、格式、页数、编码和噪声 | 输入登记表 | 能说明样本覆盖哪些场景 |\n"
            "| 规则设计 | 登记表与关键知识点 | 写出处理前后、失败条件和复查方式 | cleaning_and_chunking_rules.md | 同伴能照规则复现 |\n"
            "| 小样本验证 | 3 到 5 段真实文本 | 执行清洗、分块和元数据处理 | 分块样例表 | chunk 可追溯、无明显断裂 |\n"
            "| 检索连接 | 分块样例表 | 标注保留、剔除、合并和召回影响 | 检索影响说明 | 能用测试问题解释召回依据 |"
        ),
        "<!-- video:id=video_1 -->",
        (
            "## 练习任务\n"
            f"预计耗时 25 到 40 分钟。输入：一份你准备放进本地知识库的 PDF、Markdown 或技术说明文档，以及本节小节目标「{title}」。"
            "操作步骤：先填写输入登记表，再写清洗与分块规则，然后选取 3 到 5 段文本手动跑一遍处理流程，最后写出每个 chunk 为什么保留、剔除或合并。"
            "输出：一份 markdown 记录，至少包含输入登记表、规则说明、分块样例表和检索影响说明。"
            "提交物：文档截图、终端运行日志或整理后的 markdown 文件。"
            "完成标准：别人只看你的提交物，就能判断你的非结构化文档是否已经被整理成适合后续向量化和语义检索的语料。"
        ),
        "<!-- animation:id=anim_1 -->",
        (
            "## 检查标准\n"
            f"- [ ] 能用自己的话解释「{title}」在《{course_name}》中的作用，并说明它和后续向量化、检索召回的关系。\n"
            f"- [ ] 能逐条解释 {', '.join(knowledge_points)}，每条都能给出输入、处理动作、输出和失败边界。\n"
            "- [ ] 能提交一张分块样例表，表里至少包含原文片段、处理后文本、元数据、保留或剔除理由。\n"
            "- [ ] 能通过运行结果、截图、表格或口头解释证明清洗和分块规则不是随意写的，而是能复查、能复现。\n"
            "- [ ] 能说明视频资源和 HTML 动画分别服务哪个理解难点，并确认占位符 ID 与 brief 完全一致。"
        ),
        (
            "补充说明：这份文档由资源生成链路在模型短输出后进行确定性重写，并且仍然要通过同一套质量检查才能保存。"
            "它不会把不可用模型调用、空结果或低质量占位内容当成完成；只有当 Markdown 具备完整标题、核心概念展开、步骤表格、练习任务、检查清单、视频 brief 和动画 brief 时，才会进入视频搜索与 HTML 动画阶段。"
        ),
    ])

    return {
        "section_id": section_id,
        "parent_section_id": section.get("parent_section_id"),
        "title": title,
        "markdown": markdown,
        "video_briefs": video_briefs,
        "animation_briefs": animation_briefs,
    }


def _deterministic_animation_html(
    animation_id: str,
    title: str,
    concept: str,
    visual_elements: list[str],
) -> str:
    clean_title = _clean_text(title) or "流程动画"
    clean_concept = _clean_text(concept) or f"展示{clean_title}的关键步骤。"
    elements = [_clean_text(item) for item in visual_elements if _clean_text(item)]
    if not elements:
        elements = [clean_title, "处理步骤", "验收证据"]
    nodes = "\n".join(
        (
            f'<div class="node" data-step="{index}">'
            f'<span class="step-label">第 {index} 步</span>'
            f'<strong>{html.escape(element)}</strong>'
            "</div>"
            f'<div class="connector" aria-hidden="true"></div>'
        )
        for index, element in enumerate(elements, start=1)
    )
    return (
        '<!doctype html><html><head><meta charset="utf-8"></head><body>'
        '<section class="section-animation">'
        "<style>"
        ":root{--space-xs:4px;--space-sm:8px;--space-md:16px;--space-lg:24px;"
        "--surface:oklch(96% 0.025 92);--panel:oklch(99% 0.012 96);"
        "--text:oklch(29% 0.045 245);--muted:oklch(48% 0.035 245);"
        "--accent:oklch(70% 0.11 185);--line:oklch(82% 0.055 185);"
        "--shadow-sm:0 2px 4px oklch(0% 0 0 / 0.05),0 10px 24px oklch(0% 0 0 / 0.07);}"
        ".section-animation{font-family:'LXGW WenKai',serif;background:var(--surface);color:var(--text);"
        "padding:var(--space-lg);box-shadow:var(--shadow-sm);border-radius:16px;overflow:hidden;}"
        ".animation-context{margin-bottom:var(--space-md);line-height:1.8;color:var(--muted);}"
        ".animation-title{font-size:20px;font-weight:500;margin:0 0 var(--space-sm);color:var(--text);}"
        ".stage{display:flex;gap:var(--space-sm);align-items:stretch;justify-content:space-between;}"
        ".node{opacity: 1 !important;transform: none !important;background:var(--panel);border:1px solid var(--line);"
        "border-radius:12px;padding:var(--space-md);min-width:120px;flex:1;text-align:center;line-height:1.6;}"
        ".node strong{font-weight:500;display:block;}.step-label{display:block;color:var(--accent);margin-bottom:var(--space-xs);}"
        ".connector{opacity: 1 !important;transform: none !important;align-self:center;flex:0 0 28px;height:2px;background:var(--accent);}"
        ".connector:last-child{display:none;}"
        "@media (max-width: 640px){.stage{flex-direction:column}.connector{width:2px;height:20px;margin:auto;}}"
        "@media (prefers-reduced-motion: reduce){.section-animation *{animation:none !important;transition:none !important;}}"
        "</style>"
        f'<h3 class="animation-title">{html.escape(clean_title)}</h3>'
        f'<div class="animation-context">{html.escape(clean_concept)}</div>'
        f'<div class="stage" data-animation-id="{html.escape(animation_id)}">{nodes}</div>'
        "</section></body></html>"
    )


def _deterministic_animation_data(animation_briefs: object, section: dict) -> list[dict]:
    if not isinstance(animation_briefs, list):
        return []
    animations: list[dict] = []
    for brief in animation_briefs:
        if not isinstance(brief, dict):
            continue
        animation_id = _clean_text(brief.get("animation_id"))
        if not animation_id:
            continue
        title = _clean_text(brief.get("title")) or _clean_text(section.get("title")) or "流程动画"
        concept = _clean_text(brief.get("concept")) or f"展示{title}的关键步骤。"
        visual_elements = _text_items(brief.get("visual_elements"))
        animations.append(
            {
                "animation_id": animation_id,
                "title": title,
                "html": _deterministic_animation_html(animation_id, title, concept, visual_elements),
            }
        )
    return animations


_LOW_QUALITY_MARKERS = (
    "Key Concept",
    "This section explores foundational concepts",
    "视频资源暂时不可用",
    "动画暂时不可用",
    "Lesson Quiz",
    "Question 1 of 3",
)
_DISALLOWED_ANIMATION_COLOR_PATTERN = re.compile(
    r"(#[0-9A-Fa-f]{3,8}\b|\brgba?\s*\(|\bhsla?\s*\()"
)
_MARKDOWN_HEADING_PATTERN = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_ENGLISH_KNOWLEDGE_POINT_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+(?:[./_-][A-Za-z0-9]+)*")
_ENGLISH_KNOWLEDGE_POINT_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "between",
    "by",
    "during",
    "for",
    "from",
    "given",
    "in",
    "into",
    "is",
    "of",
    "on",
    "or",
    "returns",
    "return",
    "that",
    "the",
    "their",
    "this",
    "to",
    "using",
    "with",
    "without",
}


def _contains_chinese(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _normalized_english_knowledge_anchor(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", _clean_text(value).lower())


def _english_knowledge_anchor_variants(anchor: str) -> set[str]:
    variants = {anchor}
    if anchor.endswith("ies") and len(anchor) > 4:
        variants.add(anchor[:-3] + "y")
    for suffix in ("ing", "ed", "es", "s"):
        if anchor.endswith(suffix) and len(anchor) - len(suffix) >= 4:
            variants.add(anchor[: -len(suffix)])
    return {variant for variant in variants if variant}


def _english_knowledge_point_anchors(point: str) -> list[str]:
    anchors: list[str] = []
    seen: set[str] = set()
    for token in _ENGLISH_KNOWLEDGE_POINT_TOKEN_PATTERN.findall(point):
        for piece in [token, *re.split(r"[./_-]+", token)]:
            normalized = _normalized_english_knowledge_anchor(piece)
            if (
                not normalized
                or normalized in seen
                or normalized in _ENGLISH_KNOWLEDGE_POINT_STOPWORDS
            ):
                continue
            if len(normalized) < 3 and not any(char.isdigit() for char in normalized):
                continue
            anchors.append(normalized)
            seen.add(normalized)
    return anchors


def _knowledge_point_covered_in_markdown(concept_body: str, point: str) -> bool:
    point_text = _clean_text(point)
    if not point_text:
        return True
    if point_text in concept_body:
        return True
    if _contains_chinese(point_text):
        return False

    anchors = _english_knowledge_point_anchors(point_text)
    if not anchors:
        return False

    normalized_body = _normalized_english_knowledge_anchor(_strip_html_tags(concept_body))
    matched_anchors = [
        anchor
        for anchor in anchors
        if any(variant in normalized_body for variant in _english_knowledge_anchor_variants(anchor))
    ]
    required_matches = max(2, min(4, (len(anchors) + 1) // 2))
    has_strong_anchor = any(
        len(anchor) >= 6 or any(char.isdigit() for char in anchor)
        for anchor in matched_anchors
    )
    return len(matched_anchors) >= required_matches and has_strong_anchor


def _markdown_section_body(markdown: str, heading: str) -> str:
    matches = list(_MARKDOWN_HEADING_PATTERN.finditer(markdown))
    for index, match in enumerate(matches):
        if match.group(1).strip().startswith(heading):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
            return markdown[start:end].strip()
    return ""


def _markdown_teaching_depth_issue(markdown: str, section: dict) -> str | None:
    concept_body = _markdown_section_body(markdown, "核心概念")
    steps_body = _markdown_section_body(markdown, "步骤讲解")
    check_body = _markdown_section_body(markdown, "检查标准")

    if len(markdown) < 1800:
        return "Markdown 教学深度不足：正文整体过短。"
    if len(concept_body) < 260:
        return "Markdown 教学深度不足：核心概念解释过短。"
    if len(steps_body) < 360:
        return "Markdown 教学深度不足：步骤讲解缺少展开。"
    has_table = "|" in steps_body and re.search(r"^\s*\|.*\|\s*$", steps_body, re.MULTILINE)
    has_code_block = "```" in steps_body
    if not has_table and not has_code_block:
        return "Markdown 教学支架不足：步骤讲解缺少表格、伪代码或代码块。"
    check_items = re.findall(r"^\s*-\s+\[\s*[ xX]?\s*\]", check_body, re.MULTILINE)
    if len(check_items) < 4:
        return "Markdown 教学深度不足：检查标准少于 4 条。"
    if len(check_body) < 160:
        return "Markdown 教学深度不足：检查标准不可验收。"
    return None



def _markdown_quality_issue(
    markdown: str,
    section: dict,
    video_briefs: object,
    animation_briefs: object,
) -> str | None:
    text = _clean_text(markdown)
    if any(marker in text for marker in _LOW_QUALITY_MARKERS):
        return "Markdown 含旧兜底内容。"
    if len(text) < 700:
        return "Markdown 内容过短。"
    required_headings = ("## 学习目标", "## 核心概念", "## 步骤讲解", "## 练习任务", "## 检查标准")
    missing_headings = [heading for heading in required_headings if heading not in text]
    if missing_headings:
        return f"Markdown 缺少必备章节：{', '.join(missing_headings)}。"
    teaching_depth_issue = _markdown_teaching_depth_issue(text, section)
    if teaching_depth_issue:
        return teaching_depth_issue
    title = _clean_text(section.get("title"))
    description = _clean_text(section.get("description"))
    knowledge_points = _text_items(section.get("key_knowledge_points"))
    required_terms = [item for item in [title, description, *knowledge_points] if item]
    if required_terms and not any(term in text for term in required_terms):
        return "Markdown 未绑定目标小节内容。"

    video_ids = _extract_brief_ids_from_markdown(text, "video")
    animation_ids = _extract_brief_ids_from_markdown(text, "animation")
    expected_video_ids = {
        _clean_text(brief.get("video_id"))
        for brief in video_briefs
        if isinstance(brief, dict) and _clean_text(brief.get("video_id"))
    }
    expected_animation_ids = {
        _clean_text(brief.get("animation_id"))
        for brief in animation_briefs
        if isinstance(brief, dict) and _clean_text(brief.get("animation_id"))
    }
    if not video_ids or set(video_ids) != expected_video_ids:
        return "Markdown 视频占位符与 brief 不一致。"
    if not animation_ids or set(animation_ids) != expected_animation_ids:
        return "Markdown 动画占位符与 brief 不一致。"
    return None


def _video_topic_terms(video_briefs: object, section: dict, outline: dict | None = None) -> list[str]:
    terms = [_clean_text(section.get("title"))]
    if isinstance(outline, dict):
        terms.append(_clean_text(outline.get("course_name")))
        parent_section = _parent_section(outline, section)
        if isinstance(parent_section, dict):
            terms.append(_clean_text(parent_section.get("title")))
    terms.extend(_text_items(section.get("key_knowledge_points")))
    if isinstance(video_briefs, list):
        for brief in video_briefs:
            if not isinstance(brief, dict):
                continue
            terms.append(_clean_text(brief.get("title")))
            terms.append(_clean_text(brief.get("purpose")))
    return [term for term in terms if term]


_VIDEO_TOPIC_STOPWORDS = {
    "视频",
    "教程",
    "导入",
    "导入视频",
    "学习目标",
    "学习",
    "学习者",
    "帮助",
    "理解",
    "建立",
    "直觉",
    "本节",
    "小节",
    "目的",
    "实战",
    "讲解",
    "课程",
    "任务拆解",
    "检查点",
}
_VIDEO_QUALITY_GENERIC_KEYWORDS = {
    "ai",
    "agent",
    "openaiapi",
    "openai",
    "智能体",
    "大模型",
    "llm",
    "api",
    "apikey",
    "测试",
    "评测",
    "标准",
    "测试用例",
    "可靠性",
    "验收标准",
}
_VIDEO_DOMAIN_KEYWORDS = ("AI", "Agent", "OpenAI", "智能体", "大模型", "LLM", "API")
_VIDEO_TOPIC_SYNONYMS = {
    "检查点": ["测试", "评测", "检查", "测试用例"],
    "验收标准": ["测试", "评测", "标准", "可靠性", "测试用例"],
    "质量检查": ["测试", "评测", "质量", "可靠性", "测试用例"],
    "运行证据": ["日志", "测试", "报告", "证据", "调试"],
    "任务拆解": ["拆解", "任务", "需求"],
    "需求拆解": ["拆解", "需求", "任务"],
    "接口契约": ["接口", "契约", "API", "Schema"],
    "功能边界": ["功能", "边界", "范围"],
    "环境变量配置": ["Python"],
    "SDK初始化": ["Python", "SDK"],
    "异步编程中": ["asyncio", "异步编程"],
    "稳定性陷阱": ["event loop", "asyncio"],
    "阻塞事件循环": ["event loop", "asyncio"],
    "异步调用至关重要": ["asyncio", "event loop"],
    "文本分块": ["chunk", "chunking", "chunk_size", "chunk_overlap", "overlap", "切分"],
    "分块策略": ["文本分块", "chunk", "chunking", "chunk_size", "chunk_overlap", "overlap"],
    "Embedding": ["向量化", "文本到向量", "向量", "嵌入"],
    "文本到向量": ["Embedding", "向量化", "向量"],
    "维度映射": ["向量维度", "向量空间"],
    "语义检索": ["检索", "召回", "RAG"],
    "RAG": ["检索增强生成", "检索", "召回"],
    "上下文丢失": ["上下文", "overlap"],
    "chunk": ["文本分块", "chunking", "chunk_size", "chunk_overlap", "overlap"],
    "chunking": ["文本分块", "chunk", "chunk_size", "chunk_overlap", "overlap"],
    "overlap": ["文本分块", "chunk", "chunking", "chunk_overlap"],
}
_VIDEO_TOPIC_SUBTERMS = (
    "文本分块",
    "分块策略",
    "chunk_size",
    "chunk_overlap",
    "chunking",
    "chunk",
    "overlap",
    "向量数据库",
    "向量存储",
    "文本到向量",
    "向量化",
    "维度映射",
    "向量空间",
    "语义检索",
    "检索",
    "召回",
    "Embedding",
    "RAG",
    "上下文",
)


def _video_topic_keywords(topic_terms: list[str]) -> list[str]:
    keywords: list[str] = []
    for term in topic_terms:
        compact = re.sub(r"\s+", "", _clean_text(term))
        if compact and compact not in _VIDEO_TOPIC_STOPWORDS and len(compact) >= 2:
            keywords.append(compact)
            keywords.extend(_VIDEO_TOPIC_SYNONYMS.get(compact, []))
        for fragment in _video_term_fragments(term):
            if fragment in _VIDEO_TOPIC_STOPWORDS or len(fragment) < 2:
                continue
            keywords.append(fragment)
            keywords.extend(_VIDEO_TOPIC_SYNONYMS.get(fragment, []))
        for token in re.findall(r"[A-Za-z][A-Za-z0-9.+_-]*|[\u4e00-\u9fff]{2,}", term):
            clean_token = _clean_text(token)
            if clean_token in _VIDEO_TOPIC_STOPWORDS or len(clean_token) < 2:
                continue
            keywords.append(clean_token)
            keywords.extend(_VIDEO_TOPIC_SYNONYMS.get(clean_token, []))
    seen: set[str] = set()
    unique_keywords: list[str] = []
    for keyword in keywords:
        lowered = keyword.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique_keywords.append(keyword)
    return unique_keywords


def _video_quality_keywords(keywords: list[str]) -> list[str]:
    filtered: list[str] = []
    seen: set[str] = set()
    for keyword in keywords:
        clean_keyword = _clean_text(keyword)
        lowered = clean_keyword.lower()
        if not clean_keyword or lowered in seen:
            continue
        if lowered in _VIDEO_QUALITY_GENERIC_KEYWORDS:
            continue
        filtered.append(clean_keyword)
        seen.add(lowered)
    return filtered


def _video_term_fragments(term: str) -> list[str]:
    clean_term = _clean_text(term)
    if not clean_term:
        return []
    fragments: list[str] = []
    compact = re.sub(r"\s+", "", clean_term)
    compact_lower = compact.lower()
    for topic_subterm in _VIDEO_TOPIC_SUBTERMS:
        if topic_subterm.lower() in compact_lower and topic_subterm not in fragments:
            fragments.append(topic_subterm)
    for piece in re.split(r"[与和及、/（）()：:，,。·\-\s]+|的", clean_term):
        normalized = _clean_text(piece)
        if len(normalized) >= 2 and normalized not in fragments:
            fragments.append(normalized)
    return fragments


def _video_focus_query_terms(keywords: list[str]) -> list[str]:
    joined = " ".join(keywords)
    compact = re.sub(r"\s+", "", joined)
    lowered = compact.lower()
    focus_terms: list[str] = []

    def add(term: str) -> None:
        if term not in focus_terms:
            focus_terms.append(term)

    if "rag" in lowered or "检索增强生成" in compact:
        add("RAG")
    if "embedding" in lowered or "文本到向量" in compact or "向量化" in compact:
        add("Embedding")
    if "文本分块" in compact or "chunk" in lowered or "切分" in compact:
        add("文本分块")
    if "向量数据库" in compact or "向量存储" in compact:
        add("向量数据库")
    if "语义检索" in compact or "检索" in compact or "召回" in compact:
        add("语义检索")
    if "上下文" in compact or "overlap" in lowered:
        add("上下文")
    return focus_terms


def _video_domain_keywords(topic_terms: list[str]) -> list[str]:
    keywords = list(_VIDEO_DOMAIN_KEYWORDS)
    for term in topic_terms:
        clean_term = _clean_text(term)
        if clean_term and len(clean_term) >= 2:
            keywords.append(clean_term)
    return _video_topic_keywords(keywords)


def _video_domain_anchor_terms(section: dict, outline: dict | None = None) -> list[str]:
    terms: list[str] = []
    if isinstance(outline, dict):
        terms.append(_clean_text(outline.get("course_name")))
        parent_section = _parent_section(outline, section)
        if isinstance(parent_section, dict):
            terms.append(_clean_text(parent_section.get("title")))
            terms.extend(_text_items(parent_section.get("key_knowledge_points")))
    terms.extend(_text_items(section.get("key_knowledge_points")))
    return _video_topic_keywords([term for term in terms if term])


def _video_brief_anchor_terms(video_briefs: object) -> list[str]:
    if not isinstance(video_briefs, list):
        return []
    terms: list[str] = []
    for brief in video_briefs:
        if not isinstance(brief, dict):
            continue
        terms.append(_clean_text(brief.get("title")))
        terms.append(_clean_text(brief.get("purpose")))
    return _video_topic_keywords([term for term in terms if term])


def _matched_video_keywords(text: str, keywords: list[str]) -> list[str]:
    compact_text = re.sub(r"\s+", "", _strip_html_tags(text))
    lower_text = compact_text.lower()
    matches: list[str] = []
    seen: set[str] = set()
    for keyword in keywords:
        clean_keyword = _clean_text(keyword)
        lowered = clean_keyword.lower()
        if not clean_keyword or lowered in seen:
            continue
        if clean_keyword in compact_text or lowered in lower_text:
            matches.append(clean_keyword)
            seen.add(lowered)
    return matches


def _is_generic_video_term(term: str) -> bool:
    compact = re.sub(r"\s+", "", _clean_text(term))
    if not compact:
        return True
    remainder = compact
    for stopword in _VIDEO_TOPIC_STOPWORDS:
        remainder = remainder.replace(stopword, "")
    return len(remainder) < 2


def _strip_video_stopwords(term: str) -> str:
    compact = re.sub(r"\s+", "", _clean_text(term))
    for stopword in sorted(_VIDEO_TOPIC_STOPWORDS, key=len, reverse=True):
        compact = compact.replace(stopword, "")
    return compact


_VIDEO_SPECIFIC_TERM_MARKERS = (
    "chunk",
    "pdf",
    "vector",
    "loader",
    "splitter",
    "embedder",
    "valueerror",
    "mismatch",
    "shape",
    "dimension",
    "debug",
    "query",
    "document",
)


def _video_specific_brief_terms(
    video_briefs: object,
    section: dict,
    outline: dict | None = None,
) -> list[str]:
    if not isinstance(video_briefs, list):
        return []
    domain_terms = {
        _clean_text(term).lower()
        for term in _video_domain_anchor_terms(section, outline)
        if _clean_text(term)
    }
    specific_terms: list[str] = []
    seen: set[str] = set()

    def overlaps_domain(term: str) -> bool:
        compact = re.sub(r"\s+", "", _clean_text(term)).lower()
        if not compact:
            return False
        if compact in domain_terms:
            return True
        pieces = [
            _clean_text(piece).lower()
            for piece in re.split(r"[./_:+\-]+", compact)
            if _clean_text(piece)
        ]
        if any(piece in domain_terms for piece in pieces):
            return True
        return any(
            len(domain_term) >= 3 and (domain_term in compact or compact in domain_term)
            for domain_term in domain_terms
        )

    def add(term: str, *, allow_domain_overlap: bool = False) -> None:
        clean_term = _clean_text(term)
        lowered = clean_term.lower()
        if not clean_term or lowered in seen or _is_generic_video_term(clean_term):
            return
        if (
            re.fullmatch(r"[A-Za-z][A-Za-z0-9.+_-]*", clean_term)
            and not allow_domain_overlap
            and not overlaps_domain(clean_term)
        ):
            return
        if lowered in domain_terms and not allow_domain_overlap:
            return
        has_enough_length = len(clean_term) >= 4 or bool(re.fullmatch(r"[A-Za-z]{3,}", clean_term))
        if not has_enough_length:
            return
        specific_terms.append(clean_term)
        seen.add(lowered)

    for brief in video_briefs:
        if not isinstance(brief, dict):
            continue
        title = _clean_text(brief.get("title"))
        purpose = _clean_text(brief.get("purpose"))
        stripped_title = _strip_video_stopwords(title)
        stripped_purpose = _strip_video_stopwords(purpose)
        add(stripped_title)
        for fragment in _video_term_fragments(stripped_title):
            add(fragment)
        for fragment in _video_term_fragments(stripped_purpose):
            add(fragment)
        for token in re.findall(r"[A-Za-z][A-Za-z0-9.+_-]*", " ".join([title, purpose])):
            allow_domain_overlap = any(marker in token.lower() for marker in _VIDEO_SPECIFIC_TERM_MARKERS)
            add(token, allow_domain_overlap=allow_domain_overlap)
    return specific_terms


def _video_specific_brief_technical_tokens(
    video_briefs: object,
    section: dict,
    outline: dict | None = None,
) -> list[str]:
    return [
        term
        for term in _video_specific_brief_terms(video_briefs, section, outline)
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9.+_-]*", term)
    ]


def _requires_specific_video_brief_match(
    video_briefs: object,
    section: dict,
    outline: dict | None = None,
) -> bool:
    technical_tokens = _video_specific_brief_technical_tokens(video_briefs, section, outline)
    if len(technical_tokens) >= 2:
        return True
    specific_terms = _video_specific_brief_terms(video_briefs, section, outline)
    technical_markers = (
        "环境变量",
        "初始化",
        "api key",
        "apikey",
        "异步调用",
        "阻塞事件循环",
        "排查",
        "维度不匹配",
        "Chunking",
        "PDF",
        "Vector",
        "Loader",
        "Splitter",
        "Embedder",
    )
    return any(
        marker.lower() in term.lower()
        for term in specific_terms
        for marker in technical_markers
    )


def _has_strong_video_keyword_match(text: str, keywords: list[str]) -> bool:
    matches = _matched_video_keywords(text, keywords)
    if not matches:
        return False
    if any(len(match) >= 6 for match in matches):
        return True
    return len(matches) >= 2


def _has_strong_video_brief_match(
    text: str,
    video_briefs: object,
    section: dict,
    outline: dict | None = None,
) -> bool:
    specific_terms = _video_specific_brief_terms(video_briefs, section, outline)
    if not specific_terms:
        return False
    specific_keywords = _video_quality_keywords(_video_topic_keywords(specific_terms))
    return _has_strong_video_keyword_match(text, specific_keywords or specific_terms)


def _has_related_video_topic(
    text: str,
    video_briefs: object,
    section: dict,
    outline: dict | None = None,
) -> bool:
    domain_keywords = _video_quality_keywords(_video_domain_anchor_terms(section, outline))
    brief_keywords = _video_quality_keywords(_video_brief_anchor_terms(video_briefs))
    topic_keywords = _video_quality_keywords(_video_topic_keywords(_video_topic_terms(video_briefs, section, outline)))
    matched_domain = _matched_video_keywords(text, domain_keywords)
    matched_brief = _matched_video_keywords(text, brief_keywords)
    matched_topic = _matched_video_keywords(text, topic_keywords)
    matched_focus = _matched_video_keywords(
        text,
        _video_focus_query_terms([*domain_keywords, *brief_keywords, *topic_keywords]),
    )
    return (
        len(matched_domain) >= 2
        or len(matched_topic) >= 3
        or (bool(matched_focus) and (bool(matched_domain) or bool(matched_brief) or len(matched_topic) >= 2))
    )


def _contains_any_video_keyword(text: str, keywords: list[str]) -> bool:
    return bool(_matched_video_keywords(text, keywords))


def _is_bilibili_search_placeholder_title(title: str) -> bool:
    cleaned = _clean_text(title)
    return cleaned.startswith("Bilibili 搜索结果 BV")


def _video_domain_issue(metadata_text: str, topic_terms: list[str]) -> str | None:
    normalized_text = re.sub(r"<[^>]+>", "", metadata_text)
    normalized_compact = re.sub(r"\s+", "", normalized_text)
    normalized_lower = normalized_text.lower()
    domain_keywords = _video_quality_keywords(_video_domain_keywords(topic_terms))
    if any(
        keyword in normalized_compact or keyword.lower() in normalized_lower
        for keyword in domain_keywords
    ):
        return None
    return "视频平台真实标题或简介未体现当前课程主题。"


_BILIBILI_BVID_PATTERN = re.compile(r"\b(BV[0-9A-Za-z]{10})\b")


def _bilibili_bvid_from_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.netloc.endswith("bilibili.com"):
        return ""
    match = _BILIBILI_BVID_PATTERN.search(parsed.path)
    return match.group(1) if match else ""


async def _verify_bilibili_video_metadata(url: str) -> dict:
    bvid = _bilibili_bvid_from_url(url)
    if not bvid:
        return {"status": "skip"}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.bilibili.com/",
    }
    api_url = "https://api.bilibili.com/x/web-interface/view"
    try:
        async with httpx.AsyncClient(timeout=_VIDEO_METADATA_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.get(api_url, params={"bvid": bvid}, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.warning("Bilibili metadata validation failed for %s: %s", url, exc)
        return await _verify_bilibili_video_page(url, bvid, headers)

    if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
        message = _clean_text(payload.get("message")) or "稿件不可见"
        return {"status": "invalid", "reason": f"Bilibili 视频不可见：{message}。"}
    data = payload["data"]
    metadata_text = " ".join(
        item
        for item in [
            _clean_text(data.get("title")),
            _clean_text(data.get("desc")),
            _clean_text(data.get("tname")),
            _clean_text((data.get("owner") or {}).get("name") if isinstance(data.get("owner"), dict) else ""),
        ]
        if item
    )
    return {"status": "ok", "text": metadata_text, "title": _clean_text(data.get("title"))}


async def _verify_bilibili_video_page(url: str, bvid: str, headers: dict[str, str]) -> dict:
    try:
        async with httpx.AsyncClient(timeout=_VIDEO_METADATA_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            page_text = response.text
    except Exception as exc:
        logger.warning("Bilibili page validation failed for %s: %s", url, exc)
        return {"status": "error", "reason": "视频平台页面校验失败。"}

    if "啊叻？视频不见了？" in page_text or "稿件不可见" in page_text or "视频去哪了呢？" in page_text:
        return {"status": "invalid", "reason": "Bilibili 视频不可见。"}
    if bvid and bvid not in page_text:
        return {"status": "invalid", "reason": "Bilibili 页面未匹配目标稿件。"}

    title_match = re.search(r"<title[^>]*>(.*?)</title>", page_text, re.S | re.I)
    state_title_match = re.search(r'"title":"([^"]+)"', page_text)
    title = _clean_text(state_title_match.group(1) if state_title_match else "")
    page_title = _clean_text(re.sub(r"\s+", " ", title_match.group(1)) if title_match else "")
    metadata_text = " ".join(item for item in [title, page_title] if item)
    if not metadata_text:
        return {"status": "error", "reason": "视频平台页面缺少可校验标题。"}
    return {"status": "ok", "text": metadata_text, "title": title or page_title}


def _video_metadata_topic_issue(
    metadata_text: str,
    topic_terms: list[str],
    section: dict,
    video_briefs: object,
    outline: dict | None = None,
) -> str | None:
    specific_brief_terms = _video_specific_brief_terms(video_briefs, section, outline)
    if specific_brief_terms and _requires_specific_video_brief_match(video_briefs, section, outline):
        if not _has_strong_video_brief_match(metadata_text, video_briefs, section, outline):
            if _has_related_video_topic(metadata_text, video_briefs, section, outline):
                return None
            return "视频平台真实标题或简介未体现小节主题。"
        return None
    domain_issue = _video_domain_issue(metadata_text, topic_terms)
    if domain_issue:
        return domain_issue
    domain_anchor_terms = _video_domain_anchor_terms(section, outline)
    if domain_anchor_terms and not _contains_any_video_keyword(metadata_text, domain_anchor_terms):
        return "视频平台真实标题或简介未体现当前课程主题。"
    brief_anchor_terms = _video_brief_anchor_terms(video_briefs)
    if brief_anchor_terms and not _contains_any_video_keyword(metadata_text, brief_anchor_terms):
        return "视频平台真实标题或简介未体现小节主题。"
    topic_keywords = _video_topic_keywords(topic_terms)
    if not topic_keywords:
        return None
    if _contains_any_video_keyword(metadata_text, topic_keywords):
        return None
    return "视频平台真实标题或简介未体现小节主题。"


def _normalized_video_quality_issue(
    videos: list[dict],
    video_briefs: object,
    section: dict,
    outline: dict | None = None,
) -> str | None:
    if not videos:
        return "视频资源为空。"
    expected_ids = {
        _clean_text(brief.get("video_id"))
        for brief in video_briefs
        if isinstance(brief, dict) and _clean_text(brief.get("video_id"))
    }
    video_ids = {_clean_text(video.get("brief_id")) for video in videos if _clean_text(video.get("brief_id"))}
    if expected_ids and video_ids != expected_ids:
        return "视频资源未完整绑定 brief。"
    topic_terms = _video_topic_terms(video_briefs, section, outline)
    for video in videos:
        url = _clean_text(video.get("url"))
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return "视频 URL 必须是可直接打开的 HTTP(S) 地址。"
        bilibili_bvid = _bilibili_bvid_from_url(url)
        title = _clean_text(video.get("title"))
        specific_brief_terms = _video_specific_brief_terms(video_briefs, section, outline)
        if not bilibili_bvid:
            title_source = f"{_clean_text(video.get('title'))} {_clean_text(video.get('source'))}"
            if specific_brief_terms and _requires_specific_video_brief_match(video_briefs, section, outline):
                if not _has_strong_video_brief_match(title_source, video_briefs, section, outline):
                    if _has_related_video_topic(title_source, video_briefs, section, outline):
                        continue
                    return "视频标题未体现小节主题或 brief 目的。"
                continue
            title_source = f"{_clean_text(video.get('title'))} {_clean_text(video.get('source'))}"
            title_keywords = _video_quality_keywords(_video_topic_keywords(topic_terms))
            if title_keywords and not _contains_any_video_keyword(title_source, title_keywords):
                return "视频标题未体现小节主题或 brief 目的。"
        if bilibili_bvid and _is_bilibili_search_placeholder_title(title):
            continue
        title_source = f"{title} {_clean_text(video.get('source'))}"
        if specific_brief_terms and _requires_specific_video_brief_match(video_briefs, section, outline):
            if not _has_strong_video_brief_match(title_source, video_briefs, section, outline):
                if _has_related_video_topic(title_source, video_briefs, section, outline):
                    continue
                return "视频标题未体现小节主题或 brief 目的。"
            continue
        domain_anchor_terms = _video_quality_keywords(_video_domain_anchor_terms(section, outline))
        section_terms = _video_quality_keywords(
            _video_topic_keywords([_clean_text(section.get("title")), *_text_items(section.get("key_knowledge_points"))])
        )
        if domain_anchor_terms and not _contains_any_video_keyword(title_source, domain_anchor_terms):
            return "视频标题未体现当前课程领域或小节主题。"
        if section_terms and not _contains_any_video_keyword(title_source, section_terms):
            return "视频标题未体现当前课程领域或小节主题。"
    return None


async def _normalized_video_quality_issue_async(
    videos: list[dict],
    video_briefs: object,
    section: dict,
    outline: dict | None = None,
) -> str | None:
    issue = _normalized_video_quality_issue(videos, video_briefs, section, outline)
    if issue:
        return issue
    topic_terms = _video_topic_terms(video_briefs, section, outline)
    for video in videos:
        url = _clean_text(video.get("url"))
        metadata = await _verify_bilibili_video_metadata(url)
        status = metadata.get("status")
        if status == "skip":
            continue
        if status != "ok":
            return _clean_text(metadata.get("reason")) or "视频平台元数据校验失败。"
        metadata_issue = _video_metadata_topic_issue(
            _clean_text(metadata.get("text")),
            topic_terms,
            section,
            video_briefs,
            outline,
        )
        if metadata_issue:
            return metadata_issue
        metadata_title = _clean_text(metadata.get("title"))
        if metadata_title:
            video["title"] = metadata_title
    return None


def _strip_html_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", _clean_text(text))


def _compact_video_query_parts(
    parts: list[str],
    *,
    max_parts: int = 6,
    max_chars: int = 120,
) -> str:
    query_parts: list[str] = []
    seen: set[str] = set()
    for part in parts:
        clean_part = _clean_text(part)
        if not clean_part:
            continue
        lowered = clean_part.lower()
        if lowered in seen:
            continue
        joined_query = " ".join([*query_parts, clean_part])
        if query_parts and len(joined_query) > max_chars:
            continue
        query_parts.append(clean_part)
        seen.add(lowered)
        if len(query_parts) >= max_parts:
            break
    return " ".join(query_parts)


def _english_video_focus_queries(
    specific_terms: list[str],
    focus_terms: list[str],
) -> list[str]:
    lowered_terms = {term.lower() for term in specific_terms}
    queries: list[str] = []

    def add(query: str) -> None:
        clean_query = _clean_text(query)
        if clean_query and clean_query not in queries:
            queries.append(clean_query)

    if any(term in lowered_terms for term in ("dimension", "mismatch", "valueerror", "shape")):
        add("RAG embedding dimension mismatch error tutorial")
        add("vector dimension mismatch embedding error")
        add("query document embedding mismatch debug")
    if any(term in lowered_terms for term in ("query", "question", "chunks", "top-3", "top3", "retrieval")):
        add("RAG query function retrieval tutorial")
        add("RAG top k chunks retrieval tutorial")
    if any("chunk" in term for term in lowered_terms):
        add("RAG chunking strategy tutorial")
        add("RAG preprocessing chunking embeddings vector databases")
    if any(term in lowered_terms for term in ("pdf", "loader", "splitter", "embedder")) or {
        "vector",
        "store",
    }.issubset(lowered_terms):
        add("RAG PDF to vector store tutorial")
        add("RAG loader splitter embedder vector database")
        add("LangChain PDF vector database tutorial")
    if "embedding" in {term.lower() for term in focus_terms} and not queries:
        add("Embedding tutorial for RAG")
    return queries


def _is_high_confidence_video_candidate(
    video: dict,
    brief: dict,
    section: dict,
    outline: dict | None = None,
) -> bool:
    title_source = " ".join(
        item
        for item in [
            _clean_text(video.get("title")),
            _clean_text(video.get("source")),
        ]
        if item
    )
    return _has_strong_video_brief_match(title_source, [brief], section, outline)


_VIDEO_QUERY_TERM_MARKERS = (
    "环境变量",
    "初始化",
    "sdk",
    "api key",
    "apikey",
    "asyncio",
    "异步",
    "阻塞事件循环",
    "阻塞",
    "事件循环",
    "错误处理",
    "重试",
)


def _prioritize_video_query_terms(terms: list[str]) -> list[str]:
    unique_terms: list[str] = []
    seen: set[str] = set()
    for term in terms:
        clean_term = _clean_text(term)
        lowered = clean_term.lower()
        if not clean_term or lowered in seen:
            continue
        seen.add(lowered)
        unique_terms.append(clean_term)

    def score(term: str) -> tuple[int, int, int]:
        lowered = term.lower()
        marker_score = 1 if any(marker in lowered for marker in _VIDEO_QUERY_TERM_MARKERS) else 0
        sentence_penalty = -1 if any(punct in term for punct in "，。；！？,.!?") else 0
        length_score = 0
        if len(term) <= 12:
            length_score = 2
        elif len(term) <= 20:
            length_score = 1
        return (marker_score, length_score, sentence_penalty)

    return sorted(unique_terms, key=score, reverse=True)


def _video_search_queries(video_briefs: object, section: dict, outline: dict | None = None) -> list[str]:
    title = _clean_text(section.get("title"))
    knowledge_points = _text_items(section.get("key_knowledge_points"))
    topic_terms = _video_topic_terms(video_briefs, section, outline)
    topic_keywords = _video_topic_keywords(topic_terms)
    brief_keywords = _video_brief_anchor_terms(video_briefs)
    specific_brief_terms = _video_specific_brief_terms(video_briefs, section, outline)
    prioritized_specific_terms = _prioritize_video_query_terms(specific_brief_terms)
    knowledge_keywords = _video_topic_keywords(knowledge_points)
    domain_keywords = _video_domain_anchor_terms(section, outline)
    focus_terms = _video_focus_query_terms([*brief_keywords, *domain_keywords])
    section_keywords = _video_topic_keywords([title, *knowledge_points])
    domain_query_terms = domain_keywords[:3] or section_keywords[:3] or topic_keywords[:3]
    queries = [
        *_english_video_focus_queries([*prioritized_specific_terms, *knowledge_keywords], focus_terms),
        _compact_video_query_parts([*prioritized_specific_terms[:2], *focus_terms[:2], "教程"]),
        _compact_video_query_parts([*knowledge_keywords[:4], *focus_terms[:2], "教程"]),
        _compact_video_query_parts([*prioritized_specific_terms[:2], *domain_query_terms[:2], "教程"]),
        _compact_video_query_parts([*brief_keywords[:3], *focus_terms[:2], "教程"]),
        _compact_video_query_parts([*section_keywords[:4], *focus_terms[:2], "教程"]),
        _compact_video_query_parts([*domain_query_terms[:3], *section_keywords[:2], "教程"]),
        _compact_video_query_parts([*topic_keywords[:4], *focus_terms[:2], "教程"]),
        _compact_video_query_parts([*prioritized_specific_terms[:2], *section_keywords[:2], "视频"]),
        _compact_video_query_parts([*domain_query_terms[:2], "实战", "教程"]),
        _compact_video_query_parts([*domain_query_terms[:2], "原理", "讲解"]),
    ]
    joined_specific_terms = " ".join(prioritized_specific_terms).lower()
    if any(marker in joined_specific_terms for marker in ("环境变量", "初始化", "sdk", "api key", "apikey")):
        queries.extend([
            _compact_video_query_parts(["Python", "OpenAI", "环境变量配置", "SDK初始化", "教程"]),
            _compact_video_query_parts(["Python", "OpenAI", "API", "环境变量", "初始化", "教程"]),
        ])
    if any(marker in joined_specific_terms for marker in ("asyncio", "异步", "阻塞事件循环", "阻塞")):
        queries.extend([
            _compact_video_query_parts(["Python", "asyncio", "阻塞事件循环", "最佳实践", "教程"]),
            _compact_video_query_parts(["Python", "异步编程", "阻塞事件循环", "稳定性", "教程"]),
        ])
    if "Embedding" in focus_terms:
        queries.append("Embedding 原理 文本到向量 教程")
    if "文本分块" in focus_terms:
        queries.append("RAG 文本分块 chunk overlap 教程")
    if {"RAG", "Embedding"}.issubset(set(focus_terms)):
        queries.append("RAG 架构 Embedding 教程")
    joined_keywords = " ".join([title, *knowledge_points])
    if any(term in joined_keywords for term in ("检查", "验收", "质量", "运行证据")):
        queries.extend([
            _compact_video_query_parts([*prioritized_specific_terms[:2], *section_keywords[:2], "测试", "验收标准"]),
            _compact_video_query_parts([*domain_query_terms[:2], *section_keywords[:2], "质量检查"]),
            _compact_video_query_parts([*domain_query_terms[:2], *prioritized_specific_terms[:2], "评测"]),
        ])
    if any(term in joined_keywords for term in ("任务", "拆解", "需求", "接口契约")):
        queries.extend([
            _compact_video_query_parts([*prioritized_specific_terms[:2], *domain_query_terms[:2], "任务拆解"]),
            _compact_video_query_parts([*prioritized_specific_terms[:2], *domain_query_terms[:2], "需求拆解"]),
        ])
    if any(term in joined_keywords for term in ("OpenAI", "API", "功能边界")):
        queries.extend([
            _compact_video_query_parts([*prioritized_specific_terms[:2], *domain_query_terms[:2], "API", "调用", "教程"]),
            _compact_video_query_parts([*prioritized_specific_terms[:2], *domain_query_terms[:2], "API", "接入"]),
        ])
    seen: set[str] = set()
    unique_queries: list[str] = []
    for query in queries:
        clean_query = _clean_text(query)
        if not clean_query or clean_query in seen:
            continue
        seen.add(clean_query)
        unique_queries.append(clean_query)
    return unique_queries


async def _search_bilibili_video_results(query: str) -> list[dict]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.bilibili.com/",
    }
    return await _search_bilibili_video_page_results(query, headers)


async def _search_bilibili_video_page_results(query: str, headers: dict[str, str]) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=_VIDEO_METADATA_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.get(
                "https://search.bilibili.com/video",
                params={"keyword": query},
                headers=headers,
            )
            response.raise_for_status()
            page_text = response.text
    except Exception as exc:
        logger.warning("Bilibili search page failed for query %s: %s", query, exc)
        return []

    bvids: list[str] = []
    for bvid in _BILIBILI_BVID_PATTERN.findall(page_text):
        if bvid not in bvids:
            bvids.append(bvid)
        if len(bvids) >= 12:
            break
    return [
        {
            "title": f"Bilibili 搜索结果 {bvid}",
            "url": f"https://www.bilibili.com/video/{bvid}",
            "cover_url": "",
            "source": "Bilibili",
        }
        for bvid in bvids
    ]


async def _search_youtube_video_results(query: str) -> list[dict]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    try:
        async with httpx.AsyncClient(timeout=_VIDEO_METADATA_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.get(
                "https://www.youtube.com/results",
                params={"search_query": query},
                headers=headers,
            )
            response.raise_for_status()
            page_text = response.text
    except Exception as exc:
        logger.warning("YouTube search failed for query %s: %s", query, exc)
        return []

    initial_data_match = re.search(r"var ytInitialData = (\{.*?\});</script>", page_text, re.S)
    if not initial_data_match:
        return []
    try:
        initial_data = json.loads(initial_data_match.group(1))
    except Exception as exc:
        logger.warning("YouTube initial data parse failed for query %s: %s", query, exc)
        return []

    search_results: list[dict] = []

    def collect(node: object) -> None:
        if len(search_results) >= 12:
            return
        if isinstance(node, dict):
            video_renderer = node.get("videoRenderer")
            if isinstance(video_renderer, dict):
                video_id = _clean_text(video_renderer.get("videoId"))
                title_runs = (video_renderer.get("title") or {}).get("runs")
                title = ""
                if isinstance(title_runs, list):
                    title = "".join(_clean_text(run.get("text")) for run in title_runs if isinstance(run, dict))
                if video_id and title:
                    search_results.append(
                        {
                            "title": title,
                            "url": f"https://www.youtube.com/watch?v={video_id}",
                            "cover_url": "",
                            "source": "YouTube",
                        }
                    )
                    return
            for value in node.values():
                collect(value)
            return
        if isinstance(node, list):
            for item in node:
                collect(item)

    collect(initial_data)
    return search_results


async def _find_verified_video_from_search(
    video_briefs: object,
    section: dict,
    outline: dict | None = None,
) -> list[dict]:
    if not isinstance(video_briefs, list):
        return []
    verified: list[dict] = []
    for brief in video_briefs:
        if not isinstance(brief, dict):
            continue
        brief_id = _clean_text(brief.get("video_id"))
        if not brief_id:
            continue
        best_video: dict | None = None
        best_score = -1
        seen_urls: set[str] = set()
        for query in _video_search_queries([brief], section, outline)[:_VIDEO_VERIFIED_QUERY_LIMIT]:
            bilibili_results, youtube_results = await asyncio.gather(
                _search_bilibili_video_results(query),
                _search_youtube_video_results(query),
            )
            search_results = [*bilibili_results, *youtube_results]
            for search_result in search_results:
                url = _clean_text(search_result.get("url"))
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                video = {"brief_id": brief_id, **search_result}
                if await _normalized_video_quality_issue_async([video], [brief], section, outline) is None:
                    score = _video_candidate_score(
                        " ".join([
                            _clean_text(video.get("title")),
                            _clean_text(video.get("source")),
                        ]),
                        section,
                        [brief],
                        outline,
                    )
                    if score > best_score:
                        best_score = score
                        best_video = video
                        if score >= 40 and _is_high_confidence_video_candidate(video, brief, section, outline):
                            verified.append(best_video)
                            break
            if best_video is not None and brief_id in {_clean_text(video.get("brief_id")) for video in verified}:
                break
        if best_video is not None:
            if brief_id not in {_clean_text(video.get("brief_id")) for video in verified}:
                verified.append(best_video)
    return verified


def _video_relevance_score(text: str, topic_terms: list[str]) -> int:
    keywords = _video_topic_keywords(topic_terms)
    compact_text = re.sub(r"\s+", "", _strip_html_tags(text))
    lower_text = compact_text.lower()
    score = 0
    for keyword in keywords:
        matched = keyword in compact_text or keyword.lower() in lower_text
        if not matched:
            continue
        if len(keyword) >= 12:
            score += 5
        elif len(keyword) >= 6:
            score += 2
        else:
            score += 1
    return score


def _video_candidate_score(
    text: str,
    section: dict,
    video_briefs: object,
    outline: dict | None = None,
) -> int:
    topic_score = _video_relevance_score(text, _video_topic_terms(video_briefs, section, outline))
    brief_score = _video_relevance_score(text, _video_brief_anchor_terms(video_briefs))
    domain_score = _video_relevance_score(text, _video_domain_anchor_terms(section, outline))
    focus_terms = _video_focus_query_terms(_video_brief_anchor_terms(video_briefs))
    focus_score = _video_relevance_score(text, focus_terms)
    focus_match_count = sum(
        1
        for keyword in focus_terms
        if keyword in re.sub(r"\s+", "", _strip_html_tags(text))
        or keyword.lower() in re.sub(r"\s+", "", _strip_html_tags(text)).lower()
    )
    focus_bonus = focus_match_count * 5
    if focus_match_count >= 2:
        focus_bonus += 5
    return topic_score + (brief_score * 2) + domain_score + (focus_score * 2) + focus_bonus


def _normalized_animation_quality_issue(
    animations: list[dict],
    animation_briefs: object,
    section: dict,
) -> str | None:
    if not animations:
        return "动画资源为空。"
    expected_ids = {
        _clean_text(brief.get("animation_id"))
        for brief in animation_briefs
        if isinstance(brief, dict) and _clean_text(brief.get("animation_id"))
    }
    animation_ids = {
        _clean_text(animation.get("animation_id")) or _clean_text(animation.get("brief_id"))
        for animation in animations
        if _clean_text(animation.get("animation_id")) or _clean_text(animation.get("brief_id"))
    }
    if expected_ids and animation_ids != expected_ids:
        return "动画资源未完整绑定 brief。"

    brief_terms: list[str] = [_clean_text(section.get("title"))]
    if isinstance(animation_briefs, list):
        for brief in animation_briefs:
            if not isinstance(brief, dict):
                continue
            brief_terms.append(_clean_text(brief.get("title")))
            brief_terms.append(_clean_text(brief.get("concept")))
            brief_terms.extend(_text_items(brief.get("visual_elements")))
    brief_terms = [term for term in brief_terms if term]
    for animation in animations:
        html_text = _clean_text(animation.get("html"))
        if "<meta charset=\"utf-8\"" not in html_text.lower():
            return "动画 HTML 缺少 UTF-8 声明。"
        if "section-animation" not in html_text:
            return "动画 HTML 缺少 section-animation 根节点。"
        if "animation-context" not in html_text or not _contains_chinese(html_text):
            return "动画 HTML 缺少中文上下文。"
        if "opacity: 1 !important" not in html_text or "transform: none !important" not in html_text:
            return "动画 HTML 缺少可见兜底样式。"
        if _DISALLOWED_ANIMATION_COLOR_PATTERN.search(html_text):
            return "动画 HTML 使用了 HEX/RGB/HSL 硬编码颜色。"
        if brief_terms and not any(term in html_text for term in brief_terms):
            return "动画 HTML 未体现 brief 内容。"
    return None


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


def _video_input(state: OrchestrationState, outline: dict, section: dict) -> str:
    section_id = _clean_text(section.get("section_id"))
    section_markdowns = outline.get("section_markdowns")
    target_markdowns = {}
    if isinstance(section_markdowns, dict):
        section_markdown = section_markdowns.get(section_id)
        if isinstance(section_markdown, dict):
            target_markdowns[section_id] = section_markdown

    context = _resource_context(state, outline, section)
    payload = {
        **context,
        "parent_section": _parent_section(outline, section),
        "target_section": section,
        "section_markdowns": target_markdowns,
    }
    return (
        "请为输入小节联网搜索可直接打开的视频教程资源。\n\n"
        f"输入：{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def _video_repair_input(
    state: OrchestrationState,
    outline: dict,
    section: dict,
    quality_issue: str,
    previous_videos: object,
) -> str:
    section_id = _clean_text(section.get("section_id"))
    section_markdowns = outline.get("section_markdowns")
    target_markdowns = {}
    if isinstance(section_markdowns, dict):
        section_markdown = section_markdowns.get(section_id)
        if isinstance(section_markdown, dict):
            target_markdowns[section_id] = section_markdown

    context = _resource_context(state, outline, section)
    payload = {
        **context,
        "parent_section": _parent_section(outline, section),
        "target_section": section,
        "section_markdowns": target_markdowns,
        "video_quality_issue": quality_issue,
        "previous_videos": previous_videos if isinstance(previous_videos, list) else [],
    }
    return (
        "上一版视频资源未通过质量检查。请只基于同一个小节和 video_briefs 重新搜索视频资源。\n\n"
        "硬性要求：每条 videos.brief_id 必须等于对应 video_briefs.video_id；"
        "title 必须包含小节主题、关键知识点或 brief 目的中的具体词；"
        "url 必须来自联网搜索结果中已经存在的视频页面 HTTP(S) 地址；"
        "禁止编造 BV 号、av 号、YouTube ID 或任何看似合法的 URL；"
        "如果使用 Bilibili，url 必须是 https://www.bilibili.com/video/BV... 形式的真实可见稿件页面，"
        "平台真实标题或简介必须体现当前小节主题；"
        "不要返回课程首页、搜索页、泛泛合集首页、短链、缺少 BV 号的 Bilibili 页面或与当前小节无关的视频。\n\n"
        f"输入：{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def _normalize_videos(videos: object, video_briefs: object) -> list[dict]:
    if not isinstance(videos, list) or not isinstance(video_briefs, list):
        return []

    brief_ids = {
        _clean_text(brief.get("video_id"))
        for brief in video_briefs
        if isinstance(brief, dict) and _clean_text(brief.get("video_id"))
    }
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
        brief_id = _clean_text(video_data.get("brief_id")) or _clean_text(video_data.get("video_id"))
        if not brief_id or brief_id not in brief_ids:
            continue

        cover_url = _clean_text(video_data.get("cover_url"))
        cover_status = "provided" if cover_url else "fallback"
        if not cover_url:
            cover_url = _fallback_cover_data_url(title)

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


def _animation_input(state: OrchestrationState, outline: dict, section: dict) -> str:
    section_id = _clean_text(section.get("section_id"))
    section_markdowns = outline.get("section_markdowns")
    section_markdown = {}
    if isinstance(section_markdowns, dict):
        value = section_markdowns.get(section_id)
        if isinstance(value, dict):
            section_markdown = value

    animation_briefs = section_markdown.get("animation_briefs")
    context = _resource_context(state, outline, section)
    payload = {
        **context,
        "parent_section": _parent_section(outline, section),
        "target_section": section,
        "section_markdown": section_markdown,
        "animation_briefs": animation_briefs if isinstance(animation_briefs, list) else [],
    }
    return (
        "请为输入小节的 animation_briefs 生成可嵌入 HTML 动画片段。\n\n"
        f"输入：{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def _animation_repair_input(
    state: OrchestrationState,
    outline: dict,
    section: dict,
    quality_issue: str,
    previous_html: str,
) -> str:
    section_id = _clean_text(section.get("section_id"))
    section_markdowns = outline.get("section_markdowns")
    section_markdown = {}
    if isinstance(section_markdowns, dict):
        value = section_markdowns.get(section_id)
        if isinstance(value, dict):
            section_markdown = value

    animation_briefs = section_markdown.get("animation_briefs")
    context = _resource_context(state, outline, section)
    payload = {
        **context,
        "parent_section": _parent_section(outline, section),
        "target_section": section,
        "section_markdown": section_markdown,
        "animation_briefs": animation_briefs if isinstance(animation_briefs, list) else [],
        "animation_quality_issue": quality_issue,
        "previous_html": previous_html[:2500],
    }
    return (
        "上一版 HTML 动画未通过质量检查。请只基于同一个小节和 animation_briefs 重新生成 HTML 动画。\n\n"
        "硬性要求：根节点必须包含 class=\"section-animation\"；必须包含 <meta charset=\"utf-8\">；"
        "必须包含中文 animation-context；颜色只能使用 OKLCH 或 CSS 变量，禁止 HEX/RGB/HSL；"
        "可见性兜底必须包含 opacity: 1 !important 和 transform: none !important；"
        "动效只能改变 transform 与 opacity，并提供 prefers-reduced-motion 降级。\n\n"
        f"输入：{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def _animation_context_html(brief: dict | None) -> str:
    if not isinstance(brief, dict):
        return ""
    title = _clean_text(brief.get("title"))
    concept = _clean_text(brief.get("concept"))
    visual_elements = "、".join(_text_items(brief.get("visual_elements")))
    if not title and not concept and not visual_elements:
        return ""
    return (
        "<div class=\"animation-context\">"
        f"<div class=\"animation-context-title\">{html.escape(title or '动画说明')}</div>"
        f"<div class=\"animation-context-concept\">{html.escape(concept)}</div>"
        f"<div class=\"animation-context-elements\">{html.escape(visual_elements)}</div>"
        "</div>"
    )


def _inject_animation_context(normalized: str, brief: dict | None) -> str:
    context_html = _animation_context_html(brief)
    if not context_html or "animation-context" in normalized:
        return normalized
    root_match = re.search(r"<(?P<tag>[a-zA-Z][\w:-]*)(?P<attrs>[^>]*class=[\"'][^\"']*\bsection-animation\b[^\"']*[\"'][^>]*)>", normalized)
    if not root_match:
        return f"{context_html}\n{normalized}"
    return f"{normalized[:root_match.end()]}\n{context_html}{normalized[root_match.end():]}"


def _normalize_animation_html(html: str, brief: dict | None = None) -> str:
    normalized = _clean_text(html)
    if not normalized:
        return ""
    visible_fallback = (
        "<style>"
        "@media (prefers-reduced-motion: reduce) {"
        "  .section-animation .node,.section-animation .connector,"
        "  .section-animation [data-node],.section-animation [data-step]{"
        "    opacity: 1 !important;"
        "    transform: none !important;"
        "  }"
        "}"
        ".section-animation .animation-context{"
        "width:100%;"
        "box-sizing:border-box;"
        "margin:0 0 var(--space-md,16px);"
        "padding:var(--space-md,16px);"
        "border-radius:12px;"
        "background:oklch(96% 0.02 90);"
        "color:oklch(28% 0.04 240);"
        "box-shadow:var(--shadow-sm,0 2px 4px oklch(0% 0 0 / 0.05));"
        "}"
        ".section-animation .animation-context-title{font-weight:500;margin-bottom:6px;}"
        ".section-animation .animation-context-concept,"
        ".section-animation .animation-context-elements{font-size:13px;line-height:1.6;}"
        "</style>"
    )
    normalized = _inject_animation_context(normalized, brief)
    if visible_fallback not in normalized:
        normalized = f"{visible_fallback}\n{normalized}"
    if "<meta charset=" not in normalized.lower():
        normalized = f"<!doctype html><html><head><meta charset=\"utf-8\"></head><body>{normalized}</body></html>"
    return normalized


def _animation_stage_labels(brief: dict | None, section: dict) -> list[str]:
    labels: list[str] = []
    if isinstance(brief, dict):
        labels.extend(_text_items(brief.get("visual_elements")))
        labels.append(_clean_text(brief.get("title")))
    labels.append(_clean_text(section.get("title")))
    labels.append("完成证据")

    unique_labels: list[str] = []
    seen: set[str] = set()
    for label in labels:
        clean_label = _clean_text(label)
        if not clean_label or clean_label in seen:
            continue
        seen.add(clean_label)
        unique_labels.append(clean_label)
        if len(unique_labels) >= 4:
            break
    if len(unique_labels) < 3:
        unique_labels.extend(["学习目标", "练习任务", "检查标准"])
    return unique_labels[:4]


def _normalize_animations(animations: object, animation_briefs: object) -> list[dict]:
    if not isinstance(animations, list) or not isinstance(animation_briefs, list):
        return []

    brief_titles = {}
    animation_briefs_by_id = {}
    for brief in animation_briefs:
        if not isinstance(brief, dict):
            continue
        animation_id = _clean_text(brief.get("animation_id"))
        if animation_id:
            brief_titles[animation_id] = _clean_text(brief.get("title"))
            animation_briefs_by_id[animation_id] = brief

    normalized = []
    for animation in animations:
        if hasattr(animation, "model_dump"):
            animation_data = animation.model_dump()
        elif isinstance(animation, dict):
            animation_data = dict(animation)
        else:
            continue

        animation_id = _clean_text(animation_data.get("animation_id"))
        brief = animation_briefs_by_id.get(animation_id)
        html = _normalize_animation_html(_clean_text(animation_data.get("html")), brief)
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


def _existing_markdown_value(outline: dict, section: dict) -> dict | None:
    section_id = _clean_text(section.get("section_id"))
    section_markdowns = outline.get("section_markdowns")
    if not isinstance(section_markdowns, dict):
        return None
    value = section_markdowns.get(section_id)
    if not isinstance(value, dict):
        return None
    issue = _markdown_quality_issue(
        _clean_text(value.get("markdown")),
        section,
        value.get("video_briefs"),
        value.get("animation_briefs"),
    )
    return None if issue else value


def _existing_video_value(outline: dict, section: dict, video_briefs: object) -> dict | None:
    section_id = _clean_text(section.get("section_id"))
    section_video_links = outline.get("section_video_links")
    if not isinstance(section_video_links, dict):
        return None
    value = section_video_links.get(section_id)
    if not isinstance(value, dict):
        return None
    videos = _normalize_videos(value.get("videos"), video_briefs)
    issue = _normalized_video_quality_issue(videos, video_briefs, section, outline)
    if issue:
        return None
    existing_value = dict(value)
    existing_value["videos"] = videos
    return existing_value


def _existing_animation_value(outline: dict, section: dict, animation_briefs: object) -> dict | None:
    section_id = _clean_text(section.get("section_id"))
    section_html_animations = outline.get("section_html_animations")
    if not isinstance(section_html_animations, dict):
        return None
    value = section_html_animations.get(section_id)
    if not isinstance(value, dict):
        return None
    animations = _normalize_animations(value.get("animations"), animation_briefs)
    issue = _normalized_animation_quality_issue(animations, animation_briefs, section)
    if issue:
        return None
    existing_value = dict(value)
    existing_value["animations"] = animations
    return existing_value


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

    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content=SECTION_MARKDOWN_AGENT_SYSTEM_PROMPT),
        ("human", "{query}"),
    ])
    chain = prompt | llm

    target_section_ids = [
        _clean_text(section.get("section_id"))
        for section in target_sections
    ]
    async def generate_markdown(section: dict) -> tuple[str, dict]:
        target_section_id = _clean_text(section.get("section_id"))
        if not target_section_id:
            return "", {}
        existing_markdown = _existing_markdown_value(outline, section)
        if existing_markdown is not None:
            return target_section_id, existing_markdown
        query = _markdown_input(state, outline, section)
        markdown_data: dict = {}
        quality_issue = ""

        def deterministic_markdown(reason: str) -> dict:
            repaired_data = _normalize_markdown_resources(
                _deterministic_section_markdown_data(state, outline, section),
                section,
            )
            repaired_issue = _markdown_quality_issue(
                _clean_text(repaired_data.get("markdown")),
                section,
                repaired_data.get("video_briefs"),
                repaired_data.get("animation_briefs"),
            ) or ""
            if repaired_issue:
                logger.warning(
                    "Deterministic markdown rewrite after %s failed for section %s: %s",
                    reason,
                    target_section_id,
                    repaired_issue,
                )
                return {"error": f"{target_section_id} Markdown 文档质量不合格。"}
            return repaired_data

        for attempt in range(_MARKDOWN_ATTEMPTS):
            try:
                markdown_data = await _invoke_resource_chain(
                    chain,
                    query,
                    SectionMarkdownOutput,
                    timeout_seconds=_MARKDOWN_TIMEOUT_SECONDS,
                )
            except Exception as exc:
                logger.warning(
                    "Markdown generation failed for section %s on attempt %s: %s: %r",
                    target_section_id,
                    attempt + 1,
                    type(exc).__name__,
                    exc,
                )
                if attempt + 1 < _MARKDOWN_ATTEMPTS:
                    query = _markdown_repair_input(
                        state,
                        outline,
                        section,
                        "Markdown JSON 文本无法通过校验或生成过程超时，请严格按要求重写。",
                        "",
                    )
                    continue
                markdown_data = deterministic_markdown("generation failure")
                if _clean_text(markdown_data.get("error")):
                    return target_section_id, markdown_data
                quality_issue = ""
                break

            if _clean_text(markdown_data.get("error")):
                logger.warning(
                    "Markdown generation returned explicit error for section %s: %s",
                    target_section_id,
                    _clean_text(markdown_data.get("error")),
                )
                markdown_data = deterministic_markdown("explicit model error")
                if _clean_text(markdown_data.get("error")):
                    return target_section_id, markdown_data
                quality_issue = ""
                break

            markdown_data = _normalize_markdown_resources(markdown_data, section)
            quality_issue = _markdown_quality_issue(
                _clean_text(markdown_data.get("markdown")),
                section,
                markdown_data.get("video_briefs"),
                markdown_data.get("animation_briefs"),
            ) or ""
            if not quality_issue:
                break
            logger.warning("Markdown quality issue for section %s: %s", target_section_id, quality_issue)
            if attempt + 1 < _MARKDOWN_ATTEMPTS:
                query = _markdown_repair_input(
                    state,
                    outline,
                    section,
                    f"Markdown 质量问题：{quality_issue}",
                    _clean_text(markdown_data.get("markdown")),
                )
                continue
            markdown_data = deterministic_markdown("quality failure")
            if _clean_text(markdown_data.get("error")):
                return target_section_id, markdown_data
            quality_issue = ""
            break

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
    failed_sections: list[dict] = []
    markdown_results = await asyncio.gather(*(generate_markdown(section) for section in target_sections))
    for section, (target_section_id, markdown_value) in zip(target_sections, markdown_results, strict=True):
        if not target_section_id:
            continue
        if _clean_text(markdown_value.get("error")):
            failed_sections.append(section)
            continue
        section_markdowns[target_section_id] = markdown_value

    if failed_sections and len(target_sections) > 1:
        logger.warning(
            "Retrying %s failed section markdown(s) sequentially after batch generation: %s",
            len(failed_sections),
            ", ".join(_clean_text(section.get("section_id")) for section in failed_sections),
        )
        for section in failed_sections:
            target_section_id, markdown_value = await generate_markdown(section)
            if not target_section_id or _clean_text(markdown_value.get("error")):
                return {"error": "课程资源生成失败：Markdown 文档未生成，请稍后重试。", "hard_error": True}
            section_markdowns[target_section_id] = markdown_value
    elif failed_sections:
        return {"error": "课程资源生成失败：Markdown 文档未生成，请稍后重试。", "hard_error": True}

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
    _ = llm
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

    section_markdowns = outline.get("section_markdowns")

    async def generate_video_links(section: dict) -> tuple[str, dict]:
        target_section_id = _clean_text(section.get("section_id"))
        if not target_section_id:
            return "", {}
        section_markdown = {}
        if isinstance(section_markdowns, dict):
            value = section_markdowns.get(target_section_id)
            if isinstance(value, dict):
                section_markdown = value
        video_briefs = section_markdown.get("video_briefs")
        existing_video = _existing_video_value(outline, section, video_briefs)
        if existing_video is not None:
            return target_section_id, existing_video

        query = " | ".join(_video_search_queries(video_briefs, section, outline)[:3])
        videos: list[dict] = []
        quality_issue = "视频资源为空或未绑定 brief。"
        for _verified_attempt in range(2):
            try:
                verified_videos = await _find_verified_video_from_search(video_briefs, section, outline)
            except Exception as exc:
                logger.warning(
                    "Verified video search failed for section %s: %s",
                    target_section_id,
                    exc,
                )
                continue
            if not verified_videos:
                continue
            videos = _normalize_videos(verified_videos, video_briefs)
            quality_issue = await _normalized_video_quality_issue_async(videos, video_briefs, section, outline)
            if not quality_issue:
                break

        if quality_issue:
            logger.warning("Video quality issue for section %s: %s", target_section_id, quality_issue)
            return target_section_id, {"error": f"{target_section_id} 视频资源质量不合格。"}

        return target_section_id, {
            "section_id": target_section_id,
            "parent_section_id": section.get("parent_section_id"),
            "title": _section_title(outline, section),
            "query": query,
            "videos": videos,
            "generated_at": _now_iso(),
        }

    section_video_links: dict[str, dict] = {}
    video_results = await asyncio.gather(*(generate_video_links(section) for section in target_sections))
    for target_section_id, video_value in video_results:
        if not target_section_id:
            continue
        if _clean_text(video_value.get("error")):
            return {"error": "课程资源生成失败：视频资源未生成，请稍后重试。", "hard_error": True}
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

    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content=SECTION_HTML_ANIMATION_AGENT_SYSTEM_PROMPT),
        ("human", "{query}"),
    ])
    chain = prompt | llm

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
        existing_animation = _existing_animation_value(outline, section, animation_briefs)
        if existing_animation is not None:
            return target_section_id, existing_animation

        animation_data = {"animations": []}
        animations: list[dict] = []
        if isinstance(animation_briefs, list) and animation_briefs:
            query = _animation_input(state, outline, section)
            for attempt in range(2):
                animation_data = await _run_with_retries(
                    lambda: _invoke_resource_chain(
                        chain,
                        query,
                        SectionHtmlAnimationOutput,
                        timeout_seconds=_ANIMATION_TIMEOUT_SECONDS,
                    ),
                    fallback={"animations": []},
                    attempts=3,
                )
                animations = _normalize_animations(animation_data.get("animations"), animation_briefs)
                quality_issue = _normalized_animation_quality_issue(animations, animation_briefs, section)
                if not quality_issue:
                    break
                logger.warning("Animation quality issue for section %s: %s", target_section_id, quality_issue)
                if attempt == 0:
                    previous_html = ""
                    if animations:
                        previous_html = _clean_text(animations[0].get("html"))
                    query = _animation_repair_input(state, outline, section, quality_issue, previous_html)
                    continue
                break
            if animation_briefs and (
                not animations
                or _normalized_animation_quality_issue(animations, animation_briefs, section)
            ):
                animations = _deterministic_animation_data(animation_briefs, section)
                quality_issue = _normalized_animation_quality_issue(animations, animation_briefs, section)
                if quality_issue:
                    logger.warning(
                        "Deterministic animation quality issue for section %s: %s",
                        target_section_id,
                        quality_issue,
                    )
                    return target_section_id, {"error": f"{target_section_id} HTML 动画未生成。"}
        if isinstance(animation_briefs, list) and animation_briefs and not animations:
            animations = _deterministic_animation_data(animation_briefs, section)
            quality_issue = _normalized_animation_quality_issue(animations, animation_briefs, section)
            if quality_issue:
                logger.warning(
                    "Deterministic animation quality issue for section %s: %s",
                    target_section_id,
                    quality_issue,
                )
                return target_section_id, {"error": f"{target_section_id} HTML 动画生成失败。"}
        quality_issue = _normalized_animation_quality_issue(animations, animation_briefs, section)
        if quality_issue:
            logger.warning("Animation quality issue for section %s: %s", target_section_id, quality_issue)
            return target_section_id, {"error": f"{target_section_id} HTML 动画质量不合格。"}

        return target_section_id, {
            "section_id": target_section_id,
            "parent_section_id": section.get("parent_section_id"),
            "title": _section_title(outline, section),
            "animations": animations,
            "generated_at": _now_iso(),
        }

    section_html_animations: dict[str, dict] = {}
    failed_sections: list[dict] = []
    animation_results = await asyncio.gather(
        *(generate_html_animations(section) for section in target_sections)
    )
    for section, (target_section_id, animation_value) in zip(target_sections, animation_results, strict=True):
        if not target_section_id:
            continue
        if _clean_text(animation_value.get("error")):
            failed_sections.append(section)
            continue
        section_html_animations[target_section_id] = animation_value

    if failed_sections and len(target_sections) > 1:
        logger.warning(
            "Retrying %s failed section animation(s) sequentially after batch generation: %s",
            len(failed_sections),
            ", ".join(_clean_text(section.get("section_id")) for section in failed_sections),
        )
        for section in failed_sections:
            target_section_id, animation_value = await generate_html_animations(section)
            if not target_section_id or _clean_text(animation_value.get("error")):
                return {"error": "课程资源生成失败：HTML 动画未生成，请稍后重试。", "hard_error": True}
            section_html_animations[target_section_id] = animation_value
    elif failed_sections:
        return {"error": "课程资源生成失败：HTML 动画未生成，请稍后重试。", "hard_error": True}

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
        target_sections = _target_sections_for_scope(outline, chapter_section_id, "chapter_sections")
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

    markdown_args = {"course_id": course_id, "section_id": chapter_section_id, "scope": "chapter_sections"}
    if regeneration_focus:
        markdown_args["regeneration_focus"] = regeneration_focus
    markdown_result = await run_section_markdown_agent(state, llm, markdown_args)
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
            "label": f"{section_id} 资源",
            "message": "视频检索和 HTML 动画生成正在推进",
            "course_id": course_id,
            "chapter_section_id": chapter_section_id,
            "section_id": section_id,
            "phase": "resources",
            "status": "running",
        }

    video_result = await run_section_video_search_agent(state, search_llm)
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
    state = {**state, **video_result}
    animation_result = await run_section_html_animation_agent(state, llm)
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
