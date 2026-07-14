# ruff: noqa: C901, E501
from __future__ import annotations

import asyncio
import html
import logging
import re

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage

from app.orchestration.agents.course_resources.common import (
    _ANIMATION_TIMEOUT_SECONDS,
    _DISALLOWED_ANIMATION_COLOR_PATTERN,
    _SECTION_CONCURRENCY_LIMIT,
    _clean_text,
    _compose_section_content,
    _contains_chinese,
    _invoke_resource_chain,
    _merge_course_resource_data,
    _normalize_markdown_animation_briefs,
    _now_iso,
    _parent_section,
    _persist_outline,
    _resource_context,
    _resource_query_with_prompt_budget,
    _run_with_retries,
    _section_by_id,
    _section_title,
    _target_sections_for_scope,
    _text_items,
    _tool_args,
)
from app.orchestration.agents.models import SectionHtmlAnimationOutput
from app.orchestration.agents.prompts import SECTION_HTML_ANIMATION_AGENT_SYSTEM_PROMPT
from app.orchestration.state import OrchestrationState

logger = logging.getLogger(__name__)

_ENCODED_COLOR_TEXT_PATTERN = re.compile(
    r"&(?:oklch|rgba?|hsla?)\s*\([^)]*\)", re.IGNORECASE
)
_ANIMATION_COLOR_TOKEN_PATTERN = re.compile(r"(?i)\boklch\s*\(|var\(\s*--")


def _animation_resource_context(
    state: OrchestrationState,
    outline: dict,
    section: dict,
) -> dict:
    try:
        return _resource_context(state, outline, section)
    except ValueError:
        return _resource_context(
            state,
            outline,
            section,
            include_textbook_evidence=False,
        )


def _raw_animation_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _deterministic_animation_html(
    animation_id: str,
    title: str,
    concept: str,
    visual_elements: list[str],
    brief: dict | None = None,
) -> str:
    clean_title = _clean_text(title) or "流程动画"
    clean_concept = _clean_text(concept) or f"展示{clean_title}的关键步骤。"
    elements = [_clean_text(item) for item in visual_elements if _clean_text(item)]
    if not elements:
        elements = [clean_title, "处理步骤", "验收证据"]
    visual_model = brief.get("visual_model") if isinstance(brief, dict) else None
    entities = (
        visual_model.get("entities")
        if isinstance(visual_model, dict)
        and isinstance(visual_model.get("entities"), list)
        else []
    )
    relations = (
        visual_model.get("relations")
        if isinstance(visual_model, dict)
        and isinstance(visual_model.get("relations"), list)
        else []
    )
    timeline = brief.get("timeline") if isinstance(brief, dict) else []
    if not isinstance(timeline, list) or not timeline:
        timeline = [
            {"step": index, "action": "show_entity", "target": f"entity_{index}"}
            for index, _element in enumerate(elements, start=1)
        ]
    if not entities:
        entities = [
            {"id": f"entity_{index}", "kind": "concept", "label": element}
            for index, element in enumerate(elements, start=1)
        ]
    if not relations and len(entities) > 1:
        relations = [
            {
                "from": _clean_text(entities[index].get("id")),
                "to": _clean_text(entities[index + 1].get("id")),
                "kind": "flows_to",
            }
            for index in range(len(entities) - 1)
            if isinstance(entities[index], dict)
            and isinstance(entities[index + 1], dict)
        ]

    entity_cards: list[str] = []
    for index, entity in enumerate(entities, start=1):
        if not isinstance(entity, dict):
            continue
        entity_id = _clean_text(entity.get("id")) or f"entity_{index}"
        label = _clean_text(entity.get("label")) or entity_id
        fields = _text_items(entity.get("fields"))
        field_html = "".join(
            f'<span class="field" data-field="{html.escape(field)}">{html.escape(field)}</span>'
            for field in fields
        )
        entity_cards.append(
            f'<div class="node" data-node="true" data-entity-id="{html.escape(entity_id)}" data-step="{index}">'
            f'<span class="step-label">{html.escape(entity_id)}</span>'
            f"<strong>{html.escape(label)}</strong>"
            f'<div class="fields">{field_html}</div>'
            "</div>"
        )

    relation_lines = "\n".join(
        (
            '<g class="relation" data-relation="true" '
            f'data-from="{html.escape(_clean_text(relation.get("from")))}" '
            f'data-to="{html.escape(_clean_text(relation.get("to")))}" '
            f'data-kind="{html.escape(_clean_text(relation.get("kind")))}">'
            f'<line x1="{40 + index * 120}" y1="42" x2="{120 + index * 120}" y2="42" />'
            f'<text x="{80 + index * 120}" y="30">{html.escape(_clean_text(relation.get("from")))} -> {html.escape(_clean_text(relation.get("to")))}</text>'
            "</g>"
        )
        for index, relation in enumerate(relations)
        if isinstance(relation, dict)
    )
    timeline_steps = "\n".join(
        (
            '<button type="button" class="timeline-step" '
            f'data-timeline="{html.escape(str(item.get("step", index)))}" '
            f'data-action="{html.escape(_clean_text(item.get("action")))}">'
            f"{html.escape(str(item.get('step', index)))}. "
            f"{html.escape(_clean_text(item.get('target') or item.get('to') or item.get('from') or clean_title))}"
            "</button>"
        )
        for index, item in enumerate(timeline, start=1)
        if isinstance(item, dict)
    )
    has_linked_list = (
        isinstance(brief, dict)
        and _clean_text(brief.get("simulation_type")) == "data_structure_linked_list"
    )
    linked_list_terms = (
        '<div class="linked-list-contract" data-entity-id="linked-list-contract">'
        "<span>head</span><span>data</span><span>next</span><span>None</span>"
        "</div>"
        if has_linked_list
        else ""
    )

    return (
        '<!doctype html><html><head><meta charset="utf-8"></head><body>'
        '<section class="section-animation">'
        "<style>"
        ":root{--space-xs:4px;--space-sm:8px;--space-md:16px;--space-lg:24px;"
        "--surface:oklch(96% 0.025 92);--panel:oklch(100% 0 0 / 0.85);"
        "--text:oklch(29% 0.045 245);--muted:oklch(48% 0.035 245);"
        "--accent:oklch(65% 0.12 240);--line:oklch(85% 0.03 240);"
        "--shadow-sm:0 2px 4px oklch(0% 0 0 / 0.02),0 10px 24px oklch(10% 0.03 240 / 0.05);}"
        "@media (prefers-color-scheme: dark) {"
        ":root {"
        "--surface:oklch(16% 0.01 240);--panel:oklch(22% 0.015 240 / 0.85);"
        "--text:oklch(92% 0.01 240);--muted:oklch(65% 0.02 240);"
        "--accent:oklch(70% 0.12 240);--line:oklch(30% 0.02 240);"
        "--shadow-sm:0 2px 4px oklch(0% 0 0 / 0.2),0 10px 24px oklch(0% 0 0 / 0.4);}"
        "}"
        ".section-animation{font-family:'LXGW WenKai',serif;background:var(--surface);color:var(--text);"
        "padding:var(--space-lg);box-shadow:var(--shadow-sm);border-radius:16px;overflow:hidden;"
        "border: 1px solid var(--line);}"
        ".animation-context{margin-bottom:var(--space-md);line-height:1.8;color:var(--muted);}"
        ".animation-title{font-size:20px;font-weight:500;margin:0 0 var(--space-sm);color:var(--text);}"
        ".stage{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:var(--space-sm);align-items:stretch;margin-bottom:var(--space-md);}"
        ".node{cursor:pointer;background:var(--panel);border:1px solid var(--line);"
        "border-radius:12px;padding:var(--space-md);min-width:120px;flex:1;text-align:center;line-height:1.6;"
        "backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);"
        "transition: transform 0.4s cubic-bezier(0.25, 1, 0.5, 1), border-color 0.4s, background-color 0.4s, box-shadow 0.4s; position: relative;}"
        ".node:hover{transform: translateY(-2px); border-color: var(--accent);}"
        ".node.active{border-color: var(--accent); background: var(--panel); animation: pulse 2.5s infinite ease-in-out;}"
        "@media (prefers-color-scheme: dark) { .node.active{ background: oklch(25% 0.02 240); } }"
        ".node strong{font-weight:500;display:block;}.step-label{display:block;color:var(--accent);margin-bottom:var(--space-xs); font-size:12px;}"
        ".fields{display:flex;gap:var(--space-xs);justify-content:center;flex-wrap:wrap;margin-top:var(--space-xs);}"
        ".field{border:1px solid var(--line);border-radius:8px;padding:2px 6px;color:var(--muted);}"
        ".relation-map{width:100%;height:96px;margin:var(--space-sm) 0;overflow:visible;}"
        ".relation line{stroke:var(--accent);stroke-width:2;opacity:.9;}"
        ".relation text{fill:var(--muted);font-size:11px;}"
        ".timeline{display:flex;gap:var(--space-xs);flex-wrap:wrap;margin:var(--space-md) 0;}"
        ".timeline-step{border:1px solid var(--line);background:var(--panel);color:var(--text);border-radius:10px;padding:6px 10px;}"
        ".linked-list-contract{display:flex;gap:var(--space-xs);margin:var(--space-sm) 0;color:var(--accent);}"
        ".linked-list-contract span{border:1px solid var(--line);border-radius:8px;padding:4px 8px;}"
        ".detail-panel{background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: var(--space-md);"
        "backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);"
        "box-shadow: var(--shadow-sm); transition: transform 0.4s cubic-bezier(0.25, 1, 0.5, 1), border-color 0.4s, background-color 0.4s;}"
        ".detail-title{font-weight: 500; margin-bottom: var(--space-xs); color: var(--accent);}"
        ".detail-desc{font-size: 14px; line-height: 1.6; color: var(--text); margin-bottom: 6px;}"
        ".detail-io{font-size: 12px; color: var(--muted); font-family: monospace;}"
        "@keyframes pulse { 0%, 100% { box-shadow: 0 0 0 0 oklch(65% 0.12 240 / 0.3); } 50% { box-shadow: 0 0 10px 3px oklch(65% 0.12 240 / 0.15); } }"
        "@media (max-width: 640px){.stage{grid-template-columns:1fr}.relation-map{height:140px;}}"
        "@media (prefers-reduced-motion: reduce){.section-animation *{animation:none !important;transition:none !important;opacity: 1 !important;}"
        ".node,.connector,[data-node],[data-step]{transform: none !important;}}"
        "</style>"
        f'<h3 class="animation-title">{html.escape(clean_title)}</h3>'
        '<div class="animation-context">'
        f'<div class="animation-context-title">{html.escape(clean_title)}</div>'
        f'<div class="animation-context-concept">{html.escape(clean_concept)}</div>'
        f'<div class="animation-context-elements">{html.escape("、".join(elements))}</div>'
        "</div>"
        f'<div class="stage" data-animation-id="{html.escape(animation_id)}">{"".join(entity_cards)}</div>'
        '<svg class="relation-map" role="img" aria-label="visual_model.relations">'
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="var(--accent)"></path></marker></defs>'
        f"{relation_lines}</svg>"
        f'<div class="timeline">{timeline_steps}</div>'
        f"{linked_list_terms}"
        f'<div class="detail-panel" id="detailPanel-{html.escape(animation_id)}">'
        f'<div class="detail-title" id="detailTitle-{html.escape(animation_id)}">visual_model.entities 与 timeline 已按 brief 展示</div>'
        f'<div class="detail-desc" id="detailDesc-{html.escape(animation_id)}">{html.escape(clean_concept)}</div>'
        "</div>"
        "<script>"
        "(function(){"
        f'const root=document.querySelector(".stage[data-animation-id=\\"{html.escape(animation_id)}\\"]");'
        f'const panel=document.getElementById("detailTitle-{html.escape(animation_id)}");'
        "function selectStep(step){"
        "if(!root){return;}"
        'root.querySelectorAll("[data-step]").forEach(function(node){'
        'node.classList.toggle("active",node.getAttribute("data-step")===String(step));'
        "});"
        "if(panel){panel.textContent='当前步骤 '+step+' 已高亮';}"
        "}"
        'document.querySelectorAll(".timeline-step").forEach(function(button){'
        'button.addEventListener("click",function(){selectStep(button.getAttribute("data-timeline"));});'
        "});"
        "selectStep(1);"
        "})();"
        "</script>"
        "</section></body></html>"
    )


def _deterministic_animation_data(
    animation_briefs: object, section: dict
) -> list[dict]:
    if not isinstance(animation_briefs, list):
        return []
    animations: list[dict] = []
    for brief in animation_briefs:
        if not isinstance(brief, dict):
            continue
        animation_id = _clean_text(brief.get("animation_id"))
        if not animation_id:
            continue
        title = (
            _clean_text(brief.get("title"))
            or _clean_text(section.get("title"))
            or "流程动画"
        )
        concept = _clean_text(brief.get("concept")) or f"展示{title}的关键步骤。"
        visual_elements = _text_items(brief.get("visual_elements"))
        animations.append(
            {
                "animation_id": animation_id,
                "title": title,
                "html": (
                    __import__(
                        "app.orchestration.agents.course_resources",
                        fromlist=["_deterministic_animation_html"],
                    )._deterministic_animation_html(
                        animation_id, title, concept, visual_elements, brief
                    )
                ),
            }
        )
    return animations


def _html_contains_visual_entity(html_text: str, entity: dict) -> bool:
    entity_id = _raw_animation_text(entity.get("id"))
    label = _raw_animation_text(entity.get("label"))
    if entity_id and (
        f'data-entity-id="{entity_id}"' in html_text
        or f"data-entity-id='{entity_id}'" in html_text
    ):
        return True
    return bool(label and label in html_text)


def _html_contains_visual_relation(html_text: str, relation: dict) -> bool:
    source = _raw_animation_text(relation.get("from"))
    target = _raw_animation_text(relation.get("to"))
    has_connector = (
        "<line" in html_text or "connector" in html_text or "arrow" in html_text
    )
    return bool(
        source
        and target
        and source in html_text
        and target in html_text
        and has_connector
    )


def _animation_simulation_issue(html_text: str, brief: dict) -> str | None:
    visual_model = brief.get("visual_model")
    if not isinstance(visual_model, dict):
        return "动画 brief 缺少 visual_model。"
    entities = visual_model.get("entities")
    if not isinstance(entities, list) or not entities:
        return "动画 brief 缺少 visual_model.entities。"
    if not all(
        isinstance(entity, dict) and _html_contains_visual_entity(html_text, entity)
        for entity in entities
    ):
        return "动画 HTML 未实现 visual_model.entities。"
    relations = visual_model.get("relations")
    if isinstance(relations, list) and relations:
        if not all(
            isinstance(relation, dict)
            and _html_contains_visual_relation(html_text, relation)
            for relation in relations
        ):
            return "动画 HTML 未实现 visual_model.relations。"
    timeline = brief.get("timeline")
    if not isinstance(timeline, list) or not timeline:
        return "动画 brief 缺少 timeline。"
    for index, item in enumerate(timeline, start=1):
        if not isinstance(item, dict):
            return "动画 HTML 未实现 timeline 或步骤状态。"
        step = _clean_text(item.get("step")) or str(index)
        if not (
            f'data-step="{step}"' in html_text
            or f"data-step='{step}'" in html_text
            or f'data-timeline="{step}"' in html_text
            or f"data-timeline='{step}'" in html_text
        ):
            return "动画 HTML 未实现 timeline 或步骤状态。"
    if _clean_text(brief.get("simulation_type")) == "data_structure_linked_list":
        required_terms = ("head", "data", "next", "None")
        if not all(
            term in html_text or (term == "head" and "头指针" in html_text)
            for term in required_terms
        ):
            return "链表动画缺少头指针、data、next 或 None。"
        if (
            "line" not in html_text
            and "connector" not in html_text
            and "arrow" not in html_text
        ):
            return "链表动画缺少指针连线。"
    return None


def _normalized_animation_quality_issue(
    animations: list[dict],
    animation_briefs: object,
    section: dict,
) -> str | None:
    if not animations:
        return "动画资源为空。"
    normalized_briefs = _normalize_markdown_animation_briefs(section, animation_briefs)
    original_briefs_by_id = {}
    if isinstance(animation_briefs, list):
        original_briefs_by_id = {
            _clean_text(brief.get("animation_id")): brief
            for brief in animation_briefs
            if isinstance(brief, dict) and _clean_text(brief.get("animation_id"))
        }
    expected_ids = {
        _clean_text(brief.get("animation_id"))
        for brief in normalized_briefs
        if isinstance(brief, dict) and _clean_text(brief.get("animation_id"))
    }
    animation_ids = {
        _clean_text(animation.get("animation_id"))
        or _clean_text(animation.get("brief_id"))
        for animation in animations
        if _clean_text(animation.get("animation_id"))
        or _clean_text(animation.get("brief_id"))
    }
    if expected_ids and animation_ids != expected_ids:
        return "动画资源未完整绑定 brief。"
    briefs_by_id = {
        _clean_text(brief.get("animation_id")): brief
        for brief in normalized_briefs
        if isinstance(brief, dict) and _clean_text(brief.get("animation_id"))
    }

    brief_terms: list[str] = [_clean_text(section.get("title"))]
    for brief in normalized_briefs:
        if not isinstance(brief, dict):
            continue
        brief_terms.append(_clean_text(brief.get("title")))
        brief_terms.append(_clean_text(brief.get("concept")))
        brief_terms.extend(_text_items(brief.get("visual_elements")))
    brief_terms = [term for term in brief_terms if term]
    for animation in animations:
        html_text = _clean_text(animation.get("html"))
        if '<meta charset="utf-8"' not in html_text.lower():
            return "动画 HTML 缺少 UTF-8 声明。"
        if "section-animation" not in html_text:
            return "动画 HTML 缺少 section-animation 根节点。"
        if "animation-context" not in html_text or not _contains_chinese(html_text):
            return "动画 HTML 缺少中文上下文。"
        if _ENCODED_COLOR_TEXT_PATTERN.search(html_text):
            return "动画 HTML 包含编码颜色文本。"
        if _DISALLOWED_ANIMATION_COLOR_PATTERN.search(html_text):
            return "动画 HTML 使用了 HEX/RGB/HSL 硬编码颜色。"
        if (
            "opacity: 1 !important" not in html_text
            or "transform: none !important" not in html_text
        ):
            return "动画 HTML 缺少可见兜底样式。"
        if "prefers-reduced-motion" not in html_text:
            return "动画 HTML 缺少 prefers-reduced-motion 降级。"
        if brief_terms and not any(term in html_text for term in brief_terms):
            return "动画 HTML 未体现 brief 内容。"
        brief = briefs_by_id.get(
            _clean_text(animation.get("animation_id"))
            or _clean_text(animation.get("brief_id"))
        )
        if isinstance(brief, dict):
            original_brief = original_briefs_by_id.get(
                _clean_text(animation.get("animation_id"))
                or _clean_text(animation.get("brief_id"))
            )
            if isinstance(original_brief, dict) and isinstance(
                original_brief.get("visual_model"), dict
            ):
                simulation_issue = _animation_simulation_issue(html_text, brief)
                if simulation_issue:
                    return simulation_issue
        if not _ANIMATION_COLOR_TOKEN_PATTERN.search(html_text):
            return "动画 HTML 缺少 OKLCH/CSS 变量颜色。"
    return None


def _animation_input(state: OrchestrationState, outline: dict, section: dict) -> str:
    section_id = _clean_text(section.get("section_id"))
    section_markdowns = outline.get("section_markdowns")
    section_markdown = {}
    if isinstance(section_markdowns, dict):
        value = section_markdowns.get(section_id)
        if isinstance(value, dict):
            section_markdown = value

    animation_briefs = _normalize_markdown_animation_briefs(
        section, section_markdown.get("animation_briefs")
    )
    context = _animation_resource_context(state, outline, section)
    payload = {
        **context,
        "parent_section": _parent_section(outline, section),
        "target_section": section,
        "section_markdown": section_markdown,
        "animation_briefs": animation_briefs,
    }
    instruction = (
        "请为输入小节的 animation_briefs 生成可嵌入 HTML 动画片段。\n"
        "你必须实现 animation_briefs 中的 visual_model.entities、"
        "visual_model.relations 和 timeline。\n"
        "禁止做成文字卡片轮播、PPT 式说明、只有中文解释段落的动画。\n"
        "链表必须画出 head、节点 data/next 字段、next 指针连线、None 终点和步骤状态。"
    )
    return _resource_query_with_prompt_budget(
        instruction,
        payload,
        phase="animation",
        protected_fragments=[
            _clean_text(section.get("source_textbook_id")),
            "、".join(_text_items(section.get("source_section_ids"))),
        ],
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

    animation_briefs = _normalize_markdown_animation_briefs(
        section, section_markdown.get("animation_briefs")
    )
    context = _animation_resource_context(state, outline, section)
    payload = {
        **context,
        "parent_section": _parent_section(outline, section),
        "target_section": section,
        "section_markdown": section_markdown,
        "animation_briefs": animation_briefs,
        "animation_quality_issue": quality_issue,
        "previous_html": previous_html[:2500],
    }
    instruction = (
        "上一版 HTML 动画未通过质量检查。请只基于同一个小节和 animation_briefs 重新生成 HTML 动画。\n\n"
        '硬性要求：根节点必须包含 class="section-animation"；必须包含 <meta charset="utf-8">；'
        "必须包含中文 animation-context；颜色只能使用 OKLCH 或 CSS 变量，禁止 HEX/RGB/HSL；"
        "可见性兜底必须包含 opacity: 1 !important 和 transform: none !important；"
        "动效只能改变 transform 与 opacity，并提供 prefers-reduced-motion 降级。\n\n"
        "你必须实现 animation_briefs 中的 visual_model.entities、visual_model.relations 和 timeline。"
        "禁止做成文字卡片轮播、PPT 式说明、只有中文解释段落的动画。"
        "链表必须画出 head、节点 data/next 字段、next 指针连线、None 终点和步骤状态。"
    )
    return _resource_query_with_prompt_budget(
        instruction,
        payload,
        phase="animation",
        protected_fragments=[
            _clean_text(section.get("source_textbook_id")),
            "、".join(_text_items(section.get("source_section_ids"))),
        ],
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
        '<div class="animation-context">'
        f'<div class="animation-context-title">{html.escape(title or "动画说明")}</div>'
        f'<div class="animation-context-concept">{html.escape(concept)}</div>'
        f'<div class="animation-context-elements">{html.escape(visual_elements)}</div>'
        "</div>"
    )


def _inject_animation_context(normalized: str, brief: dict | None) -> str:
    context_html = _animation_context_html(brief)
    if not context_html or "animation-context" in normalized:
        return normalized
    root_match = re.search(
        r"<(?P<tag>[a-zA-Z][\w:-]*)(?P<attrs>[^>]*class=[\"'][^\"']*\bsection-animation\b[^\"']*[\"'][^>]*)>",
        normalized,
    )
    if not root_match:
        return f"{context_html}\n{normalized}"
    return f"{normalized[: root_match.end()]}\n{context_html}{normalized[root_match.end() :]}"


def _normalize_animation_colors(html_text: str) -> str:
    normalized = re.sub(
        r"#[0-9A-Fa-f]{3,8}\b",
        "oklch(72% 0.08 240)",
        html_text,
    )
    normalized = re.sub(
        r"\brgba?\s*\([^)]*\)",
        "oklch(0% 0 0 / 0.12)",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"\bhsla?\s*\([^)]*\)",
        "oklch(72% 0.08 240)",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"(?i)(background(?:-color)?\s*:\s*)white\b",
        r"\1oklch(98% 0.01 90)",
        normalized,
    )
    normalized = re.sub(
        r"(?i)(color\s*:\s*)white\b", r"\1oklch(98% 0.01 90)", normalized
    )
    normalized = re.sub(
        r"(?i)(background(?:-color)?\s*:\s*)black\b",
        r"\1oklch(18% 0.01 240)",
        normalized,
    )
    normalized = re.sub(
        r"(?i)(color\s*:\s*)black\b", r"\1oklch(18% 0.01 240)", normalized
    )
    return normalized


def _normalize_animation_html(html_str: str, brief: dict | None = None) -> str:
    normalized = _clean_text(html_str)
    if not normalized:
        return ""
    if _ENCODED_COLOR_TEXT_PATTERN.search(normalized):
        return ""
    normalized = _normalize_animation_colors(normalized)
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
        normalized = f'<!doctype html><html><head><meta charset="utf-8"></head><body>{normalized}</body></html>'
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
        html_val = _normalize_animation_html(
            _clean_text(animation_data.get("html")), brief
        )
        if not animation_id or animation_id not in brief_titles or not html_val:
            continue

        normalized.append(
            {
                "brief_id": animation_id,
                "animation_id": animation_id,
                "title": _clean_text(animation_data.get("title"))
                or brief_titles[animation_id],
                "html": html_val,
            }
        )
    return normalized


def _existing_animation_value(
    outline: dict, section: dict, animation_briefs: object
) -> dict | None:
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
            _clean_text(section.get("section_id")) for section in target_sections
        ]

    try:
        for section in target_sections:
            _resource_context(state, outline, section)
    except ValueError as exc:
        return {"error": str(exc), "hard_error": True}

    import app.orchestration.agents.course_resources as cr_pkg

    prompt = cr_pkg.ChatPromptTemplate.from_messages(
        [
            SystemMessage(content=SECTION_HTML_ANIMATION_AGENT_SYSTEM_PROMPT),
            ("human", "{query}"),
        ]
    )
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
        raw_animation_briefs = section_markdown.get("animation_briefs")
        animation_briefs = _normalize_markdown_animation_briefs(
            section, raw_animation_briefs
        )
        existing_animation = _existing_animation_value(
            outline, section, animation_briefs
        )
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
                animations = _normalize_animations(
                    animation_data.get("animations"), animation_briefs
                )
                quality_issue = _normalized_animation_quality_issue(
                    animations, raw_animation_briefs, section
                )
                if not quality_issue:
                    break
                logger.warning(
                    "Animation quality issue for section %s: %s",
                    target_section_id,
                    quality_issue,
                )
                if attempt == 0:
                    previous_html = ""
                    if animations:
                        previous_html = _clean_text(animations[0].get("html"))
                    query = _animation_repair_input(
                        state, outline, section, quality_issue, previous_html
                    )
                    continue
                break
            if animation_briefs and (
                not animations
                or _normalized_animation_quality_issue(
                    animations, raw_animation_briefs, section
                )
            ):
                try:
                    deterministic_animations = _normalize_animations(
                        _deterministic_animation_data(animation_briefs, section),
                        animation_briefs,
                    )
                except Exception as exc:
                    logger.warning(
                        "Deterministic animation rebuild failed for section %s: %s",
                        target_section_id,
                        exc,
                    )
                    deterministic_animations = []
                deterministic_issue = _normalized_animation_quality_issue(
                    deterministic_animations, raw_animation_briefs, section
                )
                if deterministic_issue:
                    logger.warning(
                        "Deterministic animation quality issue for section %s: %s",
                        target_section_id,
                        deterministic_issue,
                    )
                    return target_section_id, {
                        "error": f"{target_section_id} HTML 动画未生成。"
                    }
                animations = deterministic_animations
        if isinstance(animation_briefs, list) and animation_briefs and not animations:
            return target_section_id, {
                "error": f"{target_section_id} HTML 动画生成失败。"
            }
        quality_issue = _normalized_animation_quality_issue(
            animations, raw_animation_briefs, section
        )
        if quality_issue:
            logger.warning(
                "Animation quality issue for section %s: %s",
                target_section_id,
                quality_issue,
            )
            return target_section_id, {
                "error": f"{target_section_id} HTML 动画质量不合格。"
            }

        return target_section_id, {
            "section_id": target_section_id,
            "parent_section_id": section.get("parent_section_id"),
            "title": _section_title(outline, section),
            "animations": animations,
            "generated_at": _now_iso(),
        }

    section_html_animations: dict[str, dict] = {}
    failed_sections: list[dict] = []
    _sem = asyncio.Semaphore(_SECTION_CONCURRENCY_LIMIT)

    async def _limited_animation(section: dict) -> tuple[str, dict]:
        async with _sem:
            return await generate_html_animations(section)

    animation_results = await asyncio.gather(
        *(_limited_animation(section) for section in target_sections)
    )
    for section, (target_section_id, animation_value) in zip(
        target_sections, animation_results, strict=True
    ):
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
            ", ".join(
                _clean_text(section.get("section_id")) for section in failed_sections
            ),
        )
        for section in failed_sections:
            target_section_id, animation_value = await generate_html_animations(section)
            if not target_section_id or _clean_text(animation_value.get("error")):
                return {
                    "error": "课程资源生成失败：HTML 动画未生成，请稍后重试。",
                    "hard_error": True,
                }
            section_html_animations[target_section_id] = animation_value
    elif failed_sections:
        return {
            "error": "课程资源生成失败：HTML 动画未生成，请稍后重试。",
            "hard_error": True,
        }

    updated_outline = _merge_course_resource_data(
        outline, "section_html_animations", section_html_animations
    )
    section_composed_markdowns: dict[str, dict] = {}
    section_video_links = updated_outline.get("section_video_links")
    if isinstance(section_markdowns, dict):
        for section_id in target_section_ids:
            markdown_value = section_markdowns.get(section_id)
            video_value = (
                section_video_links.get(section_id)
                if isinstance(section_video_links, dict)
                else {}
            )
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
        logger.error(
            "Failed to persist course resources for user %s: %s",
            state.get("user_id", ""),
            exc,
        )
        return {"error": "课程资源保存失败，请稍后重试。", "hard_error": True}

    updated_plan = dict(resource_plan) if isinstance(resource_plan, dict) else {}
    updated_plan["target_section_ids"] = target_section_ids
    updated_plan["animation_section_ids"] = list(section_html_animations.keys())

    markdown_count = 0
    if isinstance(section_markdowns, dict):
        markdown_count = sum(
            1
            for section_id in target_section_ids
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
        len(value.get("animations", [])) for value in section_html_animations.values()
    )

    section_ids_text = "、".join(section_html_animations.keys()) or "指定小节"
    course_name = _clean_text(updated_outline.get("course_name")) or "课程"

    return {
        "user_id": state.get("user_id", ""),
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
