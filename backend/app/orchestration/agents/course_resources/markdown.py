# ruff: noqa: C901, E501
from __future__ import annotations

import asyncio
import json
import logging
import re

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage
from sqlmodel import Session

from app.database import get_engine
from app.orchestration.agents.course_resources.common import (
    _LOW_QUALITY_MARKERS,
    _MARKDOWN_HEADING_PATTERN,
    _MARKDOWN_SECTION_BODY_ATTEMPTS,
    _MARKDOWN_TIMEOUT_SECONDS,
    _REQUIRED_MARKDOWN_HEADING_TITLES,
    _SECTION_CONCURRENCY_LIMIT,
    SECTION_MARKDOWN_EXPANSION_SYSTEM_PROMPT,
    _clean_text,
    _compose_section_content,
    _extract_brief_ids_from_markdown,
    _extract_recommendation_reason,
    _invoke_markdown_expansion_chain,
    _merge_course_resource_data,
    _now_iso,
    _parent_section,
    _persist_outline,
    _plain_markdown_text,
    _profile_summary_for_prompt,
    _resource_context,
    _rewrite_resource_placeholders,
    _target_sections_for_scope,
    _text_items,
    _tool_args,
)
from app.orchestration.state import OrchestrationState

logger = logging.getLogger(__name__)


def _markdown_teaching_depth_issue(markdown: str, section: dict) -> str | None:
    steps_body = _markdown_section_body(markdown, "步骤讲解")
    check_body = _markdown_section_body(markdown, "检查标准")

    has_table = "|" in steps_body and re.search(
        r"^\s*\|.*\|\s*$", steps_body, re.MULTILINE
    )
    has_code_block = "```" in steps_body
    if not has_table and not has_code_block:
        return "Markdown 教学支架不足：步骤讲解缺少表格、伪代码或代码块。"
    check_items = re.findall(r"^\s*-\s+\[\s*[ xX]?\s*\]", check_body, re.MULTILINE)
    if len(check_items) < 4:
        return "Markdown 教学深度不足：检查标准少于 4 条。"
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
    required_headings = (
        "## 学习目标",
        "## 核心概念",
        "## 步骤讲解",
        "## 练习任务",
        "## 检查标准",
    )
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


def _markdown_section_body(markdown: str, heading: str) -> str:
    matches = list(_MARKDOWN_HEADING_PATTERN.finditer(markdown))
    for index, match in enumerate(matches):
        if match.group(1).strip().startswith(heading):
            start = match.end()
            end = (
                matches[index + 1].start()
                if index + 1 < len(matches)
                else len(markdown)
            )
            body = markdown[start:end].strip()
            # 剥离内容开头可能与当前小节标题同名的冗余行
            while True:
                lines = body.splitlines()
                if not lines:
                    break
                first_line = lines[0].strip()
                # 去除 #、*、_、空格等标记符号
                cleaned_line = re.sub(
                    r"^(?:#{1,6}\s+|\*+|_+)\s*", "", first_line
                ).strip()
                # 去除尾部可能存在的 :、：、*、_ 等
                cleaned_line = re.sub(
                    r"\s*(?:\*+|_+|：|:).*$", "", cleaned_line
                ).strip()
                if cleaned_line == heading:
                    body = "\n".join(lines[1:]).strip()
                else:
                    break
            return body
    return ""


def _markdown_needs_expansion(issue: str) -> bool:
    text = _clean_text(issue)
    return (
        "Markdown 内容过短" in text
        or "Markdown 教学深度不足" in text
        or "Markdown 教学支架不足" in text
    )


def _markdown_expansion_sections_for_issue(markdown: str, issue: str) -> list[str]:
    text = _clean_text(issue)
    if "核心概念解释过短" in text:
        return ["核心概念"]
    if "步骤讲解" in text or "教学支架不足" in text:
        return ["步骤讲解"]
    if "检查标准" in text:
        return ["检查标准"]

    sections: list[str] = []
    for heading in _REQUIRED_MARKDOWN_HEADING_TITLES:
        body = _markdown_section_body(markdown, heading)
        if heading == "核心概念" and len(body) < 420:
            sections.append(heading)
        elif heading == "步骤讲解" and (
            len(body) < 520 or "|" not in body and "```" not in body
        ):
            sections.append(heading)
        elif heading == "检查标准" and len(body) < 220:
            sections.append(heading)
        elif heading in {"学习目标", "练习任务"} and len(body) < 260:
            sections.append(heading)
    return sections or list(_REQUIRED_MARKDOWN_HEADING_TITLES)


def _insert_markdown_expansion(markdown: str, heading: str, expansion: str) -> str:
    expansion_text = _clean_text(_plain_markdown_text(expansion))
    if not expansion_text:
        return markdown
    expansion_text = re.sub(
        rf"^##\s+{re.escape(heading)}\s*", "", expansion_text
    ).strip()
    if not expansion_text:
        return markdown

    matches = list(_MARKDOWN_HEADING_PATTERN.finditer(markdown))
    for index, match in enumerate(matches):
        if not match.group(1).strip().startswith(heading):
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        body = markdown[start:end].rstrip()
        suffix = markdown[end:].lstrip()
        expanded_body = f"{body}\n\n{expansion_text}".strip()
        return f"{markdown[:start]}\n{expanded_body}\n\n{suffix}".rstrip()
    return f"{markdown.rstrip()}\n\n## {heading}\n{expansion_text}"


def _section_body_from_expansion_text(text: str, heading: str) -> str:
    clean_text = _clean_text(text)
    if not clean_text:
        return ""

    from app.orchestration.agents.course_resources.common import (
        _extract_json_object_text,
    )

    json_text = _extract_json_object_text(clean_text)
    if json_text:
        try:
            payload = json.loads(json_text)
        except json.JSONDecodeError:
            return ""
        if isinstance(payload, dict):
            markdown = _clean_text(payload.get("markdown"))
            section_body = _markdown_section_body(markdown, heading)
            if section_body:
                return section_body
            return ""
    elif clean_text.startswith("{") and clean_text.endswith("}"):
        return ""

    section_body = _markdown_section_body(clean_text, heading)
    if section_body:
        return section_body

    return _clean_text(_plain_markdown_text(clean_text))


def _compose_llm_section_markdown(
    markdown_data: dict,
    section: dict,
    section_bodies: dict[str, str],
) -> dict:
    normalized = dict(markdown_data)
    video_briefs = _normalize_markdown_video_briefs(
        section, normalized.get("video_briefs")
    )
    animation_briefs = _normalize_markdown_animation_briefs(
        section, normalized.get("animation_briefs")
    )
    if not video_briefs or not animation_briefs:
        return normalized

    section_id = _clean_text(section.get("section_id"))
    title = _clean_text(section.get("title")) or _clean_text(normalized.get("title"))
    blocks = [f"# {section_id} {title}"]
    for heading in ("学习目标", "核心概念", "步骤讲解"):
        blocks.append(f"## {heading}\n{_clean_text(section_bodies.get(heading))}")
    for brief in video_briefs:
        blocks.append(f"<!-- video:id={brief['video_id']} -->")
    blocks.append(f"## 练习任务\n{_clean_text(section_bodies.get('练习任务'))}")
    for brief in animation_briefs:
        blocks.append(f"<!-- animation:id={brief['animation_id']} -->")
    blocks.append(
        f"## 检查标准\n{_normalize_checklist_body(section_bodies.get('检查标准'))}"
    )

    normalized.update(
        {
            "section_id": section_id,
            "parent_section_id": section.get("parent_section_id"),
            "title": title,
            "markdown": "\n\n".join(block for block in blocks if block.strip()),
            "video_briefs": video_briefs,
            "animation_briefs": animation_briefs,
        }
    )
    return normalized


def _normalize_checklist_body(body: object) -> str:
    text = _clean_text(_plain_markdown_text(_clean_text(body)))
    if not text:
        return ""
    if re.search(r"^\s*-\s+\[\s*[ xX]?\s*\]", text, re.MULTILINE):
        return text

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("##")
    ]
    if len(lines) < 4:
        lines = [
            part.strip()
            for part in re.split(r"[。；;]\s*", text)
            if part.strip() and not part.strip().startswith("##")
        ]
    cleaned_items: list[str] = []
    for line in lines:
        item = re.sub(
            r"^\s*(?:[-*+]\s+|\d+[.、]\s*|[（(]?\d+[）)]\s*)", "", line
        ).strip()
        item = re.sub(r"^\[\s*[ xX]?\]\s*", "", item).strip()
        if item:
            cleaned_items.append(item)
    return "\n".join(f"- [ ] {item}" for item in cleaned_items)


def _markdown_section_body_issue(heading: str, body: str) -> str | None:
    text = (
        _normalize_checklist_body(body) if heading == "检查标准" else _clean_text(body)
    )
    if not text:
        return f"{heading}正文为空。"
    if heading == "步骤讲解":
        has_table = "|" in text and re.search(r"^\s*\|.*\|\s*$", text, re.MULTILINE)
        has_code_block = "```" in text
        if not has_table and not has_code_block:
            return "步骤讲解缺少表格或代码块。"
    if heading == "检查标准":
        check_items = re.findall(r"^\s*-\s+\[\s*[ xX]?\s*\]", text, re.MULTILINE)
        if len(check_items) < 4:
            return "检查标准少于 4 条。"
    return None


def _scaffolded_markdown_section_body(section: dict, heading: str, body: str) -> str:
    text = _clean_text(body)
    if heading not in {"步骤讲解", "练习任务", "检查标准"}:
        return text

    section_id = _clean_text(section.get("section_id"))
    title = _clean_text(section.get("title")) or section_id
    description = _clean_text(section.get("description")) or title
    knowledge_points = _text_items(section.get("key_knowledge_points"))
    knowledge_text = "、".join(knowledge_points) if knowledge_points else title

    if heading == "步骤讲解":
        has_table = "|" in text and re.search(r"^\s*\|.*\|\s*$", text, re.MULTILINE)
        has_code_block = "```" in text
        if has_table or has_code_block:
            return text
        rows = [
            (
                "定位目标",
                f"{title}、{description}",
                f"圈出本节要解决的知识点：{knowledge_text}",
                "目标说明",
                "能用一句话说清本节要学会什么",
            ),
            (
                "建立结构",
                f"{title} 的示例材料",
                "把概念拆成关键对象、状态变化、边界条件和操作结果",
                "结构拆解表",
                "每个字段都有明确含义",
            ),
            (
                "编写逻辑",
                "包含关键处理步骤的代码",
                "必须提供代码的详细说明，并编写对关键流程的解释说明",
                "核心逻辑代码块",
                "确保提供运行证据与结果校验说明",
            ),
        ]
        lines = [
            "| 步骤 | 输入材料 | 具体动作 | 产出物 | 验收方式 |",
            "| --- | --- | --- | --- | --- |",
        ]
        for row in rows:
            lines.append(f"| {' | '.join(row)} |")
        return "\n".join(lines)

    if heading == "练习任务":
        if text:
            return text
        return "\n".join(
            [
                f"任务卡：围绕「{title}」完成一次可复查的小练习。",
                "预计耗时：20 到 30 分钟。",
                f"输入：本小节说明「{description}」以及关键知识点「{knowledge_text}」。",
                "操作步骤：先写出你最容易混淆的点，再按步骤讲解表复盘一次完整过程，随后补充一个边界情况，最后用检查标准逐条自查。",
                "输出：一份 Markdown 练习记录，包含输入材料、过程表、边界情况说明和最终结论。",
                "提交物：练习记录、关键步骤截图或手写过程表、以及一段能复述本节难点的说明。",
                f"完成标准：别人只看你的提交物，就能判断你是否真正理解「{knowledge_text}」并能完成「{title}」对应的操作。",
            ]
        )

    checklist_body = _normalize_checklist_body(text)
    check_items = re.findall(r"^\s*-\s+\[\s*[ xX]?\s*\]", checklist_body, re.MULTILINE)
    if len(check_items) >= 4:
        return checklist_body

    supplements = [
        f"能提交一份围绕「{title}」的笔记，笔记中明确写出本节目标、输入材料、操作结果和验收证据。",
        f"能解释「{knowledge_text}」与「{description}」之间的关系，并给出一个本节专属例子。",
        "能用表格或伪代码复盘一次完整操作，标出每一步的输入、动作、产出物和判断依据。",
        "能完成练习任务并留下可检查产出，例如运行结果、截图、手写过程表或同伴复述记录。",
    ]
    lines = [line for line in checklist_body.splitlines() if line.strip()]
    for item in supplements:
        if (
            len(re.findall(r"^\s*-\s+\[\s*[ xX]?\s*\]", "\n".join(lines), re.MULTILINE))
            >= 4
        ):
            break
        lines.append(f"- [ ] {item}")
    return "\n".join(lines)


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


def _normalize_markdown_resources(markdown_data: dict, section: dict) -> dict:
    normalized = dict(markdown_data)
    markdown = _clean_text(normalized.get("markdown"))
    if not markdown:
        return normalized

    video_briefs = _normalize_markdown_video_briefs(
        section, normalized.get("video_briefs")
    )
    animation_briefs = _normalize_markdown_animation_briefs(
        section, normalized.get("animation_briefs")
    )
    from app.orchestration.agents.course_resources.common import (
        _normalize_markdown_heading_variants,
        _normalize_markdown_step_blocks,
    )

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


def _existing_markdown_value(outline: dict, section: dict) -> dict | None:
    section_id = _clean_text(section.get("section_id"))
    section_markdowns = outline.get("section_markdowns")
    if not isinstance(section_markdowns, dict):
        return None
    value = section_markdowns.get(section_id)
    if not isinstance(value, dict):
        return None
    import app.orchestration.agents.course_resources as cr_pkg

    issue = cr_pkg._markdown_quality_issue(
        _clean_text(value.get("markdown")),
        section,
        value.get("video_briefs"),
        value.get("animation_briefs"),
    )
    return None if issue else value


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

    try:
        for section in target_sections:
            _resource_context(state, outline, section)
    except ValueError as exc:
        return {"error": str(exc), "hard_error": True}

    import app.orchestration.agents.course_resources as cr_pkg

    expansion_prompt = cr_pkg.ChatPromptTemplate.from_messages(
        [
            SystemMessage(content=SECTION_MARKDOWN_EXPANSION_SYSTEM_PROMPT),
            ("human", "{query}"),
        ]
    )
    expansion_chain = expansion_prompt | llm

    target_section_ids = [
        _clean_text(section.get("section_id")) for section in target_sections
    ]

    async def generate_markdown(section: dict) -> tuple[str, dict]:
        target_section_id = _clean_text(section.get("section_id"))
        if not target_section_id:
            return "", {}
        existing_markdown = _existing_markdown_value(outline, section)
        if existing_markdown is not None:
            return target_section_id, existing_markdown
        markdown_data = _generated_markdown_seed_data(section)

        async def generate_section_body(expansion_section: str) -> tuple[str, str]:
            body = ""
            section_issue = "请生成该教学点正文。"
            for attempt in range(_MARKDOWN_SECTION_BODY_ATTEMPTS):
                query = _markdown_expansion_input(
                    state,
                    outline,
                    section,
                    section_issue,
                    "",
                    expansion_section,
                )
                try:
                    raw_body = await _invoke_markdown_expansion_chain(
                        expansion_chain,
                        query,
                        timeout_seconds=_MARKDOWN_TIMEOUT_SECONDS,
                    )
                except Exception as exc:
                    logger.warning(
                        "Markdown section body generation failed for section %s / %s on attempt %s: %s: %r",
                        target_section_id,
                        expansion_section,
                        attempt + 1,
                        type(exc).__name__,
                        exc,
                    )
                    section_issue = "章节正文生成失败或超时，请重新生成该教学点正文。"
                    continue
                body = _section_body_from_expansion_text(raw_body, expansion_section)
                issue = _markdown_section_body_issue(expansion_section, body)
                if not issue:
                    return expansion_section, body
                logger.warning(
                    "Markdown section body issue for section %s / %s on attempt %s: %s",
                    target_section_id,
                    expansion_section,
                    attempt + 1,
                    issue,
                )
                section_issue = issue
            scaffolded_body = _scaffolded_markdown_section_body(
                section, expansion_section, body
            )
            return expansion_section, scaffolded_body

        body_results = await asyncio.gather(
            *(
                generate_section_body(heading)
                for heading in _REQUIRED_MARKDOWN_HEADING_TITLES
            )
        )
        section_bodies = {
            heading: _scaffolded_markdown_section_body(section, heading, body)
            for heading, body in body_results
        }
        body_issues = [
            issue
            for heading in _REQUIRED_MARKDOWN_HEADING_TITLES
            if (
                issue := _markdown_section_body_issue(
                    heading, _clean_text(section_bodies.get(heading))
                )
            )
        ]
        if body_issues:
            return target_section_id, {
                "error": f"{target_section_id} Markdown 教学点生成失败：{'；'.join(body_issues)}"
            }

        markdown_data = _compose_llm_section_markdown(
            markdown_data, section, section_bodies
        )
        markdown_data = _normalize_markdown_resources(markdown_data, section)
        import app.orchestration.agents.course_resources as cr_pkg

        quality_issue = cr_pkg._markdown_quality_issue(
            _clean_text(markdown_data.get("markdown")),
            section,
            markdown_data.get("video_briefs"),
            markdown_data.get("animation_briefs"),
        )
        if quality_issue:
            logger.warning(
                "Markdown quality issue for section %s: %s",
                target_section_id,
                quality_issue,
            )
            return target_section_id, {
                "error": f"{target_section_id} Markdown 文档质量不合格：{quality_issue}"
            }

        animation_briefs = markdown_data.get("animation_briefs")
        video_briefs = markdown_data.get("video_briefs")
        raw_markdown = _clean_text(markdown_data.get("markdown"))
        cleaned_markdown, recommendation_reason = _extract_recommendation_reason(
            raw_markdown
        )
        return target_section_id, {
            "section_id": target_section_id,
            "parent_section_id": section.get("parent_section_id"),
            "title": _clean_text(section.get("title"))
            or _clean_text(markdown_data.get("title")),
            "markdown": cleaned_markdown,
            "video_briefs": video_briefs if isinstance(video_briefs, list) else [],
            "animation_briefs": animation_briefs
            if isinstance(animation_briefs, list)
            else [],
            "recommendation_reason": recommendation_reason,
            "generated_at": _now_iso(),
        }

    section_markdowns: dict[str, dict] = {}
    failed_sections: list[dict] = []
    _sem = asyncio.Semaphore(_SECTION_CONCURRENCY_LIMIT)

    async def _limited_markdown(section: dict) -> tuple[str, dict]:
        async with _sem:
            return await generate_markdown(section)

    markdown_results = await asyncio.gather(
        *(_limited_markdown(section) for section in target_sections)
    )
    for section, (target_section_id, markdown_value) in zip(
        target_sections, markdown_results, strict=True
    ):
        if not target_section_id:
            continue
        if _clean_text(markdown_value.get("error")):
            failed_sections.append(section)
            continue
        section_markdowns[target_section_id] = markdown_value

    def persist_markdown_error(section: dict, message: str) -> None:
        section_id = _clean_text(section.get("section_id"))
        if not section_id:
            return
        section_error = {
            "section_id": section_id,
            "phase": "markdown",
            "message": message,
            "retryable": True,
            "updated_at": _now_iso(),
        }
        updated_outline = _merge_course_resource_data(
            outline,
            "section_resource_errors",
            {section_id: section_error},
        )
        _persist_outline(str(state.get("user_id", "")), updated_outline)

    if failed_sections and len(target_sections) > 1:
        logger.warning(
            "Retrying %s failed section markdown(s) sequentially after batch generation: %s",
            len(failed_sections),
            ", ".join(
                _clean_text(section.get("section_id")) for section in failed_sections
            ),
        )
        for section in failed_sections:
            target_section_id, markdown_value = await generate_markdown(section)
            if not target_section_id or _clean_text(markdown_value.get("error")):
                error_message = "课程资源生成失败：Markdown 文档未生成，请稍后重试。"
                persist_markdown_error(section, error_message)
                return {
                    "error": error_message,
                    "hard_error": True,
                }
            section_markdowns[target_section_id] = markdown_value
    elif failed_sections:
        error_message = "课程资源生成失败：Markdown 文档未生成，请稍后重试。"
        persist_markdown_error(failed_sections[0], error_message)
        return {
            "error": error_message,
            "hard_error": True,
        }

    updated_outline = _merge_course_resource_data(
        outline, "section_markdowns", section_markdowns
    )
    section_composed_markdowns = {
        section_id: _compose_section_content(markdown_value, {}, {})
        for section_id, markdown_value in section_markdowns.items()
    }
    updated_outline = _merge_course_resource_data(
        updated_outline,
        "section_composed_markdowns",
        section_composed_markdowns,
    )
    try:
        _persist_outline(str(state.get("user_id", "")), updated_outline)
    except Exception as exc:
        logger.error(
            "Failed to persist course resources for user %s: %s",
            state.get("user_id", ""),
            exc,
        )
        return {"error": "课程资源保存失败，请稍后重试。", "hard_error": True}

    try:
        from app.models import UserProfile
        from app.services.resource_quality_service import score_course_resources

        user_id = str(state.get("user_id", ""))
        course_id = updated_outline.get("course_id", "")
        with Session(get_engine()) as quality_session:
            profile_row = quality_session.get(UserProfile, user_id)
            profile_data = (
                profile_row.profile_data
                if profile_row and isinstance(profile_row.profile_data, dict)
                else None
            )
            score_course_resources(
                quality_session, user_id, course_id, updated_outline, profile_data
            )
    except Exception as exc:
        logger.warning(
            "Quality scoring failed for user %s, course %s: %s",
            state.get("user_id", ""),
            updated_outline.get("course_id", ""),
            exc,
        )

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


def _markdown_expansion_input(
    state: OrchestrationState,
    outline: dict,
    section: dict,
    quality_issue: str,
    previous_markdown: str,
    expansion_section: str,
) -> str:
    context = _resource_context(state, outline, section)
    existing_section_lengths = {
        heading: len(_markdown_section_body(previous_markdown, heading))
        for heading in _REQUIRED_MARKDOWN_HEADING_TITLES
    }
    video_ids = _extract_brief_ids_from_markdown(previous_markdown, "video")
    animation_ids = _extract_brief_ids_from_markdown(previous_markdown, "animation")
    payload = {
        **context,
        "parent_section": _parent_section(outline, section),
        "target_section": section,
        "markdown_quality_issue": quality_issue,
        "markdown_expansion_section": expansion_section,
        "existing_section_lengths": existing_section_lengths,
        "existing_video_placeholder_ids": video_ids,
        "existing_animation_placeholder_ids": animation_ids,
    }
    query = (
        "请为 markdown_expansion_section 生成可直接放入完整教学文档的 Markdown 章节正文。"
        "不要输出 JSON，不要输出章节标题，不要输出视频或动画占位符。"
        "教材证据包 (textbook_evidence_pack) 是本节唯一的正文事实来源，你必须优先且严格依据其中的真实内容生成内容，绝对不能脱离教材虚构事实或自行补充外部无关概念。\n"
        "补充内容必须绑定 target_section.title、target_section.description 和 target_section.key_knowledge_points，"
        "并结合 profile、year_learning_paths、course_knowledge 写成本小节专属教学内容。"
        "如果 markdown_expansion_section 是 步骤讲解，必须包含 Markdown 表格或 fenced code block；"
        "如果 markdown_expansion_section 是 检查标准，必须输出至少 4 条 `- [ ]` 可验收清单；"
        "学习目标、练习任务请输出 450 到 800 个中文字释；"
        "核心概念、步骤讲解请输出 650 到 1000 个中文字符。\n\n"
        f"输入：{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )

    profile = state.get("profile")
    profile_summary = _profile_summary_for_prompt(profile)
    if profile_summary:
        query = f"{query}\n\n{profile_summary}"

    return query
