# ruff: noqa: C901, E501
from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session

from app.database import get_engine
from app.orchestration.agents.models import (
    SectionHtmlAnimationOutput,
    SectionMarkdownOutput,
    SectionVideoSearchOutput,
)
from app.services.course_knowledge_service import upsert_user_course_knowledge_outline
from app.services.knowledge_base_service import (
    get_textbook_evidence_pack,
    require_student_visible_textbooks,
)

logger = logging.getLogger(__name__)

# Constants
_RESOURCE_TIMEOUT_SECONDS = 180.0
_MARKDOWN_TIMEOUT_SECONDS = 180.0
_MARKDOWN_SECTION_BODY_ATTEMPTS = 3
_VIDEO_TIMEOUT_SECONDS = 180.0
_ANIMATION_TIMEOUT_SECONDS = 180.0
_VIDEO_METADATA_TIMEOUT_SECONDS = 8.0
_VIDEO_VERIFIED_QUERY_LIMIT = 6
_SECTION_CONCURRENCY_LIMIT = 3

SECTION_MARKDOWN_EXPANSION_SYSTEM_PROMPT = """\
你是课程 Markdown 章节正文扩写智能体。

你只生成输入中 markdown_expansion_section 指定的单个章节正文。
禁止输出 JSON。
禁止输出完整 Markdown 文档。
禁止输出 `#` 或 `##` 标题。
禁止输出视频或动画占位符。

你的输入中包含 `textbook_evidence_pack`，它保存了从数据库检索到的真实教材正文（包含 `evidence_text` 等字段）。
你必须严格基于 `textbook_evidence_pack` 提供的教材正文内容来生成本节所有的 Markdown 内容（如概念定义、公式、代码片段、原理解释等），绝对不能脱离教材虚构无关事实或引入无关的外部概念。

内容必须绑定 target_section.title、target_section.description 和 target_section.key_knowledge_points。
如果 markdown_expansion_section 是 步骤讲解，必须包含 Markdown 表格或 fenced code block。
如果 markdown_expansion_section 是 检查标准，必须输出至少 4 条 `- [ ]` 可验收清单。
其他章节输出可直接拼入教学文档的 Markdown 正文。

如果输入中包含【用户画像摘要】，你必须在正文末尾另起一行，以 `<!-- recommendation_reason: ... -->` 格式输出推荐理由。
推荐理由必须具体引用画像中的 1-2 个维度（如薄弱点、学习风格、内容偏好），说明为什么这个章节内容适合该用户。
示例：`<!-- recommendation_reason: 因为你标记"数据结构"为薄弱点，且偏好"项目驱动学习"，本节重点通过实际案例讲解核心概念。 -->`
如果输入中没有【用户画像摘要】，则不输出推荐理由。
"""

_RESOURCE_PLACEHOLDER_PATTERN = re.compile(
    r"<!--\s*(?P<kind>video|animation):id=(?P<id>[A-Za-z0-9_.:-]+)\s*-->"
)
_JSON_CODE_BLOCK_PATTERN = re.compile(
    r"```json\s*(?P<body>.*?)```", re.DOTALL | re.IGNORECASE
)
_MARKDOWN_CODE_BLOCK_PATTERN = re.compile(
    r"^```(?:markdown|md)?\s*(?P<body>.*?)```\s*$", re.DOTALL | re.IGNORECASE
)
_RECOMMENDATION_REASON_PATTERN = re.compile(
    r"<!--\s*recommendation_reason:\s*(?P<reason>.*?)\s*-->"
)

_REQUIRED_MARKDOWN_HEADING_TITLES = (
    "学习目标",
    "核心概念",
    "步骤讲解",
    "练习任务",
    "检查标准",
)

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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_text(value: object) -> str:
    text = str(value).strip()
    if not text or text.lower() in {"none", "null"}:
        return ""
    return text


def _profile_summary_for_prompt(profile: dict | None) -> str:
    """Build a concise profile summary string for LLM prompt injection."""
    if not profile or not isinstance(profile, dict):
        return ""

    parts: list[str] = []

    weaknesses = profile.get("weaknesses", "")
    if isinstance(weaknesses, str) and weaknesses.strip():
        parts.append(f"薄弱方向：{weaknesses.strip()}")

    strengths = profile.get("strengths", "")
    if isinstance(strengths, str) and strengths.strip():
        parts.append(f"擅长方向：{strengths.strip()}")

    method = profile.get("learning_method_preference", "")
    if isinstance(method, str) and method.strip():
        parts.append(f"学习方式偏好：{method.strip()}")

    content_pref = profile.get("content_preference", [])
    if isinstance(content_pref, list) and content_pref:
        parts.append(f"内容形式偏好：{'、'.join(str(p) for p in content_pref if p)}")

    foundation = profile.get("knowledge_foundation", "")
    if isinstance(foundation, str) and foundation.strip():
        parts.append(f"知识基础：{foundation.strip()}")

    pace = profile.get("learning_pace_preference", "")
    if isinstance(pace, str) and pace.strip():
        parts.append(f"学习节奏偏好：{pace.strip()}")

    goal = profile.get("short_term_goal", "")
    if isinstance(goal, str) and goal.strip():
        parts.append(f"近期目标：{goal.strip()}")

    if not parts:
        return ""

    return "【用户画像摘要】\n" + "\n".join(f"- {p}" for p in parts)


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


def _extract_brief_ids_from_markdown(markdown: str, kind: str) -> list[str]:
    ids: list[str] = []
    for match in _RESOURCE_PLACEHOLDER_PATTERN.finditer(markdown):
        if match.group("kind") != kind:
            continue
        ids.append(match.group("id"))
    return ids


def _extract_recommendation_reason(markdown: str) -> tuple[str, str]:
    """Extract recommendation_reason from markdown comment, return (cleaned_markdown, reason)."""
    match = _RECOMMENDATION_REASON_PATTERN.search(markdown)
    if not match:
        return markdown, ""
    reason = match.group("reason").strip()
    cleaned = markdown[: match.start()].rstrip() + markdown[match.end() :]
    return cleaned.strip(), reason


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


def _extract_json_object_text(text: str) -> str:
    clean_text = text.strip()
    if not clean_text:
        return ""
    code_block_match = re.search(
        r"```json\s*(?P<body>.*?)```", clean_text, re.DOTALL | re.IGNORECASE
    )
    if code_block_match:
        body = code_block_match.group("body").strip()
        if body.startswith("{") and body.endswith("}"):
            return body
    start = clean_text.find("{")
    end = clean_text.rfind("}")
    if start == 0 and end > start:
        return clean_text[start : end + 1]
    if start > 0 and end > start and "<" not in clean_text[:start]:
        return clean_text[start : end + 1]
    return ""


def _plain_markdown_text(text: str) -> str:
    clean_text = text.strip()
    match = _MARKDOWN_CODE_BLOCK_PATTERN.match(clean_text)
    if match:
        return match.group("body").strip()
    return clean_text


def _plain_html_text(text: str) -> str:
    clean_text = text.strip()
    match = re.match(
        r"^```(?:html)?\s*(?P<body>.*?)```\s*$", clean_text, re.DOTALL | re.IGNORECASE
    )
    if match:
        return match.group("body").strip()
    return clean_text


def _persist_outline(user_id: str, outline: dict) -> None:
    with Session(get_engine()) as db_session:
        upsert_user_course_knowledge_outline(db_session, user_id, outline)
        from sqlmodel import select

        from app.models import ChapterWeakness

        course_id = outline.get("course_id", "")
        if course_id:
            stmt = select(ChapterWeakness).where(
                ChapterWeakness.user_uid == user_id,
                ChapterWeakness.course_node_id == course_id,
                ChapterWeakness.consumed.is_(False),
            )
            unconsumed = db_session.exec(stmt).all()
            for w in unconsumed:
                w.consumed = True
                db_session.add(w)
            db_session.commit()
    logger.info(
        "Course resource outline persisted for user %s, course %s",
        user_id,
        outline.get("course_id", ""),
    )


def _resource_payload_from_query(query: str) -> dict:
    _prefix, separator, raw_payload = query.partition("输入：")
    if not separator:
        return {}
    try:
        payload = json.loads(raw_payload)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


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
    return {
        "section_id": section_id,
        "animations": animations,
    }


def _normalize_section_markdown_output(output: object, query: str) -> dict:
    data = dict(output) if isinstance(output, dict) else {}
    if not _clean_text(data.get("section_id")):
        try:
            args = json.loads(query)
            data["section_id"] = _clean_text(args.get("section_id", ""))
        except Exception:
            pass

    data["markdown"] = _plain_markdown_text(_clean_text(data.get("markdown")))

    video_briefs = data.get("video_briefs")
    normalized_videos: list[dict] = []
    if isinstance(video_briefs, list):
        for item in video_briefs:
            if not isinstance(item, dict):
                continue
            brief_id = _clean_text(item.get("video_id") or item.get("brief_id"))
            title = _clean_text(item.get("title") or item.get("brief_title"))
            if brief_id and title:
                normalized_videos.append({"brief_id": brief_id, "brief_title": title})
    data["video_briefs"] = normalized_videos

    animation_briefs = data.get("animation_briefs")
    normalized_animations: list[dict] = []
    if isinstance(animation_briefs, list):
        for item in animation_briefs:
            if not isinstance(item, dict):
                continue
            brief_id = _clean_text(item.get("animation_id") or item.get("brief_id"))
            title = _clean_text(item.get("title") or item.get("brief_title"))
            if brief_id and title:
                normalized_animations.append(
                    {"brief_id": brief_id, "brief_title": title}
                )
    data["animation_briefs"] = normalized_animations

    return data


def _normalize_section_video_output(output: object, query: str) -> dict:
    data = dict(output) if isinstance(output, dict) else {}
    if not _clean_text(data.get("section_id")):
        try:
            args = json.loads(query)
            data["section_id"] = _clean_text(args.get("section_id", ""))
        except Exception:
            pass

    video_links = data.get("video_links")
    normalized_links: list[dict] = []
    if isinstance(video_links, list):
        for item in video_links:
            if not isinstance(item, dict):
                continue
            brief_id = _clean_text(item.get("video_id") or item.get("brief_id"))
            url = _clean_text(item.get("url"))
            title = _clean_text(item.get("title"))
            if brief_id and url:
                normalized_links.append(
                    {"brief_id": brief_id, "url": url, "title": title}
                )
    data["video_links"] = normalized_links

    return data


def _normalize_section_animation_output(output: object, query: str) -> dict:
    data = dict(output) if isinstance(output, dict) else {}
    if not _clean_text(data.get("section_id")):
        try:
            args = json.loads(query)
            data["section_id"] = _clean_text(args.get("section_id", ""))
        except Exception:
            pass

    animations = data.get("animations")
    normalized_animations: list[dict] = []
    if isinstance(animations, list):
        for item in animations:
            if not isinstance(item, dict):
                continue
            animation_id = _clean_text(item.get("animation_id"))
            title = _clean_text(item.get("title"))
            html_val = _plain_html_text(_clean_text(item.get("html")))
            if animation_id and html_val:
                normalized_animations.append(
                    {"animation_id": animation_id, "title": title, "html": html_val}
                )
    data["animations"] = normalized_animations

    return data


def _normalize_resource_chain_output(
    output: object, output_schema: Any, query: str
) -> dict:
    if output_schema is SectionMarkdownOutput:
        return _normalize_section_markdown_output(output, query)
    if output_schema is SectionVideoSearchOutput:
        return _normalize_section_video_output(output, query)
    if output_schema is SectionHtmlAnimationOutput:
        return _normalize_section_animation_output(output, query)
    return dict(output) if isinstance(output, dict) else {}


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
    if hasattr(output, "content"):
        output = output.content
    if hasattr(output, "model_dump"):
        return output.model_dump()
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


async def _invoke_markdown_expansion_chain(
    chain: Any,
    query: str,
    *,
    timeout_seconds: float = _MARKDOWN_TIMEOUT_SECONDS,
) -> str:
    output = await asyncio.wait_for(
        chain.ainvoke({"query": query}),
        timeout=timeout_seconds,
    )
    if hasattr(output, "content"):
        output = output.content
    return _plain_markdown_text(_clean_text(output))


def _tool_args(state: dict[str, Any], explicit_args: dict | None) -> dict:
    if explicit_args is not None:
        return explicit_args
    from app.orchestration.agents.utils import extract_last_tool_call_args

    args = extract_last_tool_call_args(state)
    return args if isinstance(args, dict) else {}


def _section_title(outline: dict, section: dict) -> str:
    title = _clean_text(section.get("title"))
    if title:
        return title
    section_id = _clean_text(section.get("section_id"))
    orig = _section_by_id(outline, section_id) if section_id else None
    if isinstance(orig, dict):
        return _clean_text(orig.get("title")) or "未命名小节"
    return "未命名小节"


def _sections(outline: dict) -> list[dict]:
    value = outline.get("sections")
    if not isinstance(value, list):
        return []
    return [section for section in value if isinstance(section, dict)]


def _section_by_id(outline: dict, section_id: str) -> dict | None:
    for s in _sections(outline):
        if _clean_text(s.get("section_id")) == section_id:
            return s
    return None


def _parent_section(outline: dict, section: dict) -> dict | None:
    parent_id = _clean_text(section.get("parent_section_id"))
    if not parent_id:
        return None
    return _section_by_id(outline, parent_id)


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
        return markdown.replace(
            exercise_heading, f"{placeholder}\n\n{exercise_heading}", 1
        )
    return f"{markdown.rstrip()}\n\n{placeholder}"


def _rewrite_resource_placeholders(
    markdown: str, kind: str, brief_ids: list[str]
) -> str:
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


def _resource_context(state: dict[str, Any], outline: dict, section: dict) -> dict:
    profile = state.get("profile")
    if isinstance(profile, dict):
        confirmed = profile.get("confirmed_info")
        slim_profile = dict(confirmed) if isinstance(confirmed, dict) else {}
        summary = profile.get("summary_text")
        if isinstance(summary, str) and summary.strip():
            slim_profile["summary_text"] = summary.strip()
    else:
        slim_profile = {}
    textbook_evidence_pack = _textbook_evidence_pack(outline, section)
    return {
        "profile": slim_profile,
        "year_learning_paths": _year_learning_paths_context(state, outline, section),
        "course_knowledge": _chapter_course_knowledge_context(outline, section),
        "textbook_evidence_pack": textbook_evidence_pack,
    }


def _textbook_evidence_pack(outline: dict, section: dict) -> dict:
    source_textbook_id = _clean_text(section.get("source_textbook_id"))
    if not source_textbook_id:
        source_textbook_id = _clean_text(outline.get("source_textbook_id"))

    section_ids = _text_items(section.get("source_section_ids"))
    if not section_ids:
        section_ids = _text_items(outline.get("source_outline_section_ids"))
    if not section_ids:
        section_ids = _text_items(outline.get("source_section_ids"))

    source_textbook_title = _clean_text(section.get("source_textbook_title"))
    if not source_textbook_title:
        source_textbook_title = _clean_text(outline.get("source_textbook_title"))

    if not source_textbook_id or not section_ids:
        return {}

    with Session(get_engine()) as db_session:
        try:
            require_student_visible_textbooks(
                db_session,
                {
                    "source_textbook_id": source_textbook_id,
                },
            )
            evidence_pack = get_textbook_evidence_pack(
                db_session, source_textbook_id, section_ids
            )
        except Exception as exc:
            if str(exc) == "教材未发布。":
                raise
            logger.warning(
                "Failed to load textbook evidence pack for textbook %s: %s",
                source_textbook_id,
                exc,
            )
            return {}

    evidence_sections = evidence_pack.get("sections")
    if not isinstance(evidence_sections, list):
        evidence_sections = []

    return {
        "textbook_id": evidence_pack.get("textbook_id", source_textbook_id),
        "title": evidence_pack.get("title", source_textbook_title),
        "sections": evidence_sections,
        "total_chars": evidence_pack.get("total_chars", 0),
        "evidence_text": evidence_pack.get("evidence_text", ""),
    }


def _current_learning_course_context(state: dict[str, Any], outline: dict) -> dict:
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


def _markdown_input(state: dict[str, Any], outline: dict, section: dict) -> str:
    context = _resource_context(state, outline, section)
    payload = {
        **context,
        "parent_section": _parent_section(outline, section),
        "target_section": section,
        "video_briefs": [],
        "animation_briefs": [],
    }
    query = (
        "请基于输入大纲、关联学习路径与用户画像，为此小节生成完整的 Markdown 教学设计初稿。"
        "必须严格采用 JSON 输出格式。\n\n"
        "教材证据包是本节唯一的正文事实来源，必须优先依据其中的 evidence_text、sections、total_chars 生成内容。\n"
        "不要只根据章节标题写摘要式内容，也不要脱离教材正文自行补充事实。\n\n"
        "字段约定：\n"
        "- section_id: 小节ID字符串 (必须等于输入中的 target_section.section_id)\n"
        "- markdown: 完整的教学文档正文 (支持标准 Markdown 语法，使用各级标题建立教学结构)\n"
        "- video_briefs: 数组。每个小节建议规划 1-2 个重难点视频或拓展视频。每个元素为包含 video_id (BV...-video 或 拼写符合 [A-Za-z0-9_.-]+)、title (说明想要讲解的概念) 的字典。\n"
        '- animation_briefs: 数组。规划 1-2 个核心逻辑交互式动效。每个元素为包含 animation_id、title (动效演示主题，如"单链表反转") 的字典。\n\n'
        "教学内容必备章节格式：\n"
        "## 学习目标\n(写出明确的学习与能力目标，建议使用有序列表)\n\n"
        "## 核心概念\n(讲解核心概念，配有通俗的比喻或表格说明)\n\n"
        "## 步骤讲解\n(详细的推演或实现步骤。必须包含 Markdown 表格或 fenced code block 作为核心教学支架)\n\n"
        "## 练习任务\n(为了实现学习目标，设计的一个独立实践任务。提示：请在此章节正文开头前放置视频/动画占位符)\n\n"
        "## 检查标准\n(提供自测和交付验收单，必须提供至少 4 条 `- [ ]` 的清单格式)\n\n"
        "关于占位符要求：\n"
        "你必须在正文适当的位置写入视频占位符 `<!-- video:id=xxx -->` 引导学生观看；"
        "并在练习任务前写入交互动效占位符 `<!-- animation:id=yyy -->` 引导实践。"
        "占位符中引用的 id 必须与 video_briefs 或 animation_briefs 中的定义完全一致。\n\n"
        f"输入：{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )

    profile = state.get("profile")
    profile_summary = _profile_summary_for_prompt(profile)
    if profile_summary:
        query = f"{query}\n\n{profile_summary}"

    return query


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
        for section_id in (
            _clean_text(item.get("section_id")) for item in chapter_sections
        )
        if section_id
    }
    root_section = next(
        (
            item
            for item in chapter_sections
            if isinstance(item, dict) and item.get("parent_section_id") is None
        ),
        chapter_sections[0] if chapter_sections else None,
    )
    root_title = (
        _clean_text(root_section.get("title")) if isinstance(root_section, dict) else ""
    )
    root_description = (
        _clean_text(root_section.get("description"))
        if isinstance(root_section, dict)
        else ""
    )
    target_id = _clean_text(section.get("section_id"))
    slim_sections = []
    for s in chapter_sections:
        sid = _clean_text(s.get("section_id"))
        if sid == target_id:
            continue
        slim_sections.append(
            {
                "section_id": sid,
                "title": s.get("title"),
                "depth": s.get("depth"),
                "parent_section_id": s.get("parent_section_id"),
            }
        )
    context: dict = {
        "course_name": outline.get("course_name", ""),
        "personalization_summary": (
            f"当前只生成「{root_title}」这一章的具体教学内容。{root_description}"
            if root_title
            else "当前只生成指定章节的具体教学内容。"
        ),
        "sections": slim_sections,
        "learning_sequence": _chapter_learning_sequence(outline, root_section),
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
        existing_ids = [sid for sid in values if sid in chapter_ids]
        if existing_ids:
            context[f"existing_{field_name}_ids"] = existing_ids
    return context


def _year_learning_paths_context(
    state: dict[str, Any], outline: dict, section: dict
) -> dict:
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
            "course_or_chapter_theme": current.get(
                "course_or_chapter_theme", outline.get("course_name", "")
            ),
            "course_goal": current.get("course_goal", ""),
            "current_focus": "",
            "next_action": "",
        }

    root_id = _root_section_id_for_section(outline, section)
    root_section = _section_by_id(outline, root_id) if root_id else None
    root_title = (
        _clean_text(root_section.get("title")) if isinstance(root_section, dict) else ""
    )
    root_description = (
        _clean_text(root_section.get("description"))
        if isinstance(root_section, dict)
        else ""
    )
    if current_course:
        current_course["current_focus"] = (
            root_description or f"围绕「{root_title}」完成当前章内容。"
        )
        current_course["next_action"] = (
            f"生成并验收「{root_title}」这一章的叶子小节教学内容。"
            if root_title
            else "生成并验收当前章叶子小节教学内容。"
        )

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
        "current_learning_course": current_course,
        "resource_generation_contract": resource_contract,
    }


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


def _merge_course_resource_data(
    outline: dict, field_name: str, values: dict[str, dict]
) -> dict:
    merged = {**outline}
    existing = dict(merged.get(field_name) or {})
    existing.update(values)
    merged[field_name] = existing
    return merged


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
        brief_id = _clean_text(video.get("brief_id")) or _clean_text(
            video.get("video_id")
        )
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
        brief_id = _clean_text(animation.get("brief_id")) or _clean_text(
            animation.get("animation_id")
        )
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
    animation_title = (
        _clean_text(animation.get("title")) if isinstance(animation, dict) else ""
    )
    return {
        "type": "animation",
        "brief_id": brief_id,
        "title": _clean_text(brief.get("title")) or animation_title,
        "status": "available" if isinstance(animation, dict) else "unavailable",
        "html": _clean_text(animation.get("html"))
        if isinstance(animation, dict)
        else "",
    }


def _compose_section_content(
    section_markdown: dict,
    video_links: dict,
    animation_data: dict,
) -> dict:
    markdown = _clean_text(section_markdown.get("markdown"))
    video_briefs = _brief_by_id(section_markdown.get("video_briefs"), "video_id")
    animation_briefs = _brief_by_id(
        section_markdown.get("animation_briefs"), "animation_id"
    )
    videos = _video_by_brief_id(video_links)
    animations = _animation_by_brief_id(animation_data)

    blocks: list[dict] = []
    cursor = 0
    for match in _RESOURCE_PLACEHOLDER_PATTERN.finditer(markdown):
        _append_markdown_block(blocks, markdown[cursor : match.start()])
        brief_id = match.group("id")
        if match.group("kind") == "video":
            blocks.append(
                _video_block(
                    brief_id, video_briefs.get(brief_id, {}), videos.get(brief_id)
                )
            )
        else:
            blocks.append(
                _animation_block(
                    brief_id,
                    animation_briefs.get(brief_id, {}),
                    animations.get(brief_id),
                )
            )
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


def _root_sections(outline: dict) -> list[dict]:
    return sorted(
        [
            section
            for section in _sections(outline)
            if int(section.get("depth", 1)) == 1
        ],
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
    sections = sorted(
        _sections(outline), key=lambda item: int(item.get("order_index", 0))
    )
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
    return [
        item for item in sections if _clean_text(item.get("section_id")) in included_ids
    ]


def _target_sections_for_scope(
    outline: dict, section_id: str, scope: str
) -> list[dict]:
    sections = sorted(
        _sections(outline), key=lambda item: int(item.get("order_index", 0))
    )
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
            section
            for section in sections
            if section.get("parent_section_id") == parent_id
            and int(section.get("depth", 1)) > 1
        ]
    if scope == "course_sections":
        raise ValueError("系统一次只能生成一章的具体内容。")

    root_sections = [
        section for section in sections if int(section.get("depth", 1)) == 1
    ]
    if not root_sections:
        raise ValueError("课程大纲缺少一级章节。")
    first_root_id = _clean_text(root_sections[0].get("section_id"))
    return [
        section
        for section in sections
        if section.get("parent_section_id") == first_root_id
        and int(section.get("depth", 1)) > 1
    ]


def _contains_chinese(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _normalize_markdown_heading_variants(markdown: str) -> str:
    normalized_lines: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        replacement = ""
        is_heading = bool(re.match(r"^#{2,6}\s+", stripped))
        is_bold_title = bool(re.match(r"^\*\*.+\*\*\s*(?:[：:].*)?$", stripped))
        is_plain_required_title = any(
            stripped.startswith(title) for title in _REQUIRED_MARKDOWN_HEADING_TITLES
        )
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
        if not body:
            return markdown

        cleaned_body = re.sub(
            r"^#{1,6}\s*(?=" + _STEP_MARKER_PATTERN.pattern + ")",
            "",
            body,
            flags=re.MULTILINE | re.IGNORECASE,
        )

        if _STEP_MARKER_PATTERN.search(cleaned_body):
            return f"{markdown[:start]}{cleaned_body}\n\n{markdown[end:].lstrip()}"

        blocks = [
            block.strip()
            for block in re.split(r"\n\s*\n", cleaned_body)
            if block.strip()
        ]
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
            cleaned_block = re.sub(r"^#{1,6}\s*", "", block).strip()
            normalized_blocks.append(
                f"{_chinese_step_label(step_index)}：{cleaned_block}"
            )
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
                normalized.append(
                    {"video_id": video_id, "title": title, "purpose": purpose}
                )

    if normalized:
        return normalized

    return []


def _normalize_markdown_animation_briefs(
    section: dict, animation_briefs: object
) -> list[dict]:
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


def _generated_markdown_video_briefs(section: dict) -> list[dict]:
    title = (
        _clean_text(section.get("title"))
        or _clean_text(section.get("section_id"))
        or "本节"
    )
    knowledge_points = _text_items(section.get("key_knowledge_points"))
    focus = "、".join(knowledge_points[:2]) or title
    return [
        {
            "video_id": "video_1",
            "title": f"{title}导入视频",
            "purpose": f"帮助学习者理解{focus}，并把本节内容落到可验收任务。",
        }
    ]


def _generated_markdown_animation_briefs(section: dict) -> list[dict]:
    title = (
        _clean_text(section.get("title"))
        or _clean_text(section.get("section_id"))
        or "本节"
    )
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
            "placement_hint": "练习任务之前。",
        }
    ]


def _generated_markdown_seed_data(section: dict) -> dict:
    section_id = _clean_text(section.get("section_id"))
    title = _clean_text(section.get("title")) or section_id
    return {
        "section_id": section_id,
        "parent_section_id": section.get("parent_section_id"),
        "title": title,
        "markdown": "",
        "video_briefs": _generated_markdown_video_briefs(section),
        "animation_briefs": _generated_markdown_animation_briefs(section),
    }
