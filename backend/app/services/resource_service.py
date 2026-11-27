"""Internal helpers for the TS gateway's section resource pipeline (M7).

The model only writes the Markdown document and the HTML animation. Gating, the
chapter lock, prompts built from the textbook evidence pack, every quality check, the
external video search, the deterministic animation fallback, the placeholder
composition and the per-section atomic persistence stay here and are exposed through
narrow internal endpoints.
"""

from __future__ import annotations

import copy
import logging
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.models import ChapterWeakness, UserProfile
from app.orchestration.agents.course_resources import animation as animation_mod
from app.orchestration.agents.course_resources import common as common_mod
from app.orchestration.agents.course_resources import main as resource_main
from app.orchestration.agents.course_resources import markdown as markdown_mod
from app.orchestration.agents.course_resources import video as video_mod
from app.orchestration.agents.prompts import SECTION_HTML_ANIMATION_AGENT_SYSTEM_PROMPT
from app.orchestration.contracts import quality_passed
from app.orchestration.recovery import update_section_phase_checkpoint
from app.services.course_generation_status_service import (
    finish_course_generation,
    start_course_generation,
)
from app.services.course_knowledge_service import (
    get_user_course_knowledge_outline,
    upsert_user_course_knowledge_outline,
)
from app.services.forest_service import (
    chapter_generation_is_available,
    first_generatable_chapter_id,
)
from app.services.knowledge_base_service import require_student_visible_textbooks
from app.services.learning_path_service import (
    get_all_year_learning_paths,
    get_current_course_id_from_year_learning_paths,
    get_latest_grade_year,
)
from app.services.student_lock import lock_student

logger = logging.getLogger(__name__)

PHASES = ("markdown", "video", "animation", "compose")
_STORE_KEYS = {
    "markdown": "section_markdowns",
    "video": "section_video_links",
    "animation": "section_html_animations",
}
_clean = common_mod._clean_text


class ResourceRequestError(ValueError):
    """The request cannot be served; the message is safe to show the student."""


def _load(session: Session, user_uid: str, course_id: str) -> dict:
    outline = get_user_course_knowledge_outline(session, user_uid, course_id)
    if not isinstance(outline, dict):
        raise ResourceRequestError("请先生成课程大纲。")
    return outline


def _state(session: Session, user_uid: str, outline: dict) -> dict:
    row = session.get(UserProfile, user_uid)
    return {
        "user_id": user_uid,
        "profile": row.profile_data
        if row is not None and isinstance(row.profile_data, dict)
        else None,
        "year_learning_paths": get_all_year_learning_paths(session, user_uid),
        "latest_grade_year": get_latest_grade_year(session, user_uid),
        "course_knowledge": outline,
    }


def _section(outline: dict, section_id: str) -> dict:
    section = common_mod._section_by_id(outline, section_id)
    if section is None or int(section.get("depth", 1)) <= 1:
        raise ResourceRequestError("指定小节无法定位。")
    return section


def _checkpoint_status(outline: dict, section_id: str) -> dict[str, str]:
    stored = outline.get("section_resource_checkpoints")
    stored = stored.get(section_id) if isinstance(stored, dict) else None
    return {
        phase: str((stored or {}).get(phase, {}).get("status", ""))
        for phase in PHASES
        if isinstance(stored, dict) and isinstance(stored.get(phase), dict)
    }


def prepare_generation(
    session: Session,
    user_uid: str,
    course_id: str,
    chapter_ref: str,
    mode: str,
) -> dict:
    """Gate a chapter generation and, when allowed, take the chapter lock.

    Returns a status of `refused` (message), `needs_focus`, `busy` or `ready`.
    """
    outline = get_user_course_knowledge_outline(session, user_uid, course_id)
    year_paths = get_all_year_learning_paths(session, user_uid)
    latest = get_latest_grade_year(session, user_uid)
    if course_id != get_current_course_id_from_year_learning_paths(year_paths, latest):
        return {"status": "refused", "message": "只能为当前课程生成教学内容。"}
    ref = chapter_ref.strip()
    if not ref or ref in {"default", "__default__"}:
        ref = first_generatable_chapter_id(session, user_uid, course_id, outline) or ""
    if not ref or not chapter_generation_is_available(
        session, user_uid, course_id, ref, outline
    ):
        return {"status": "refused", "message": "通过章节测验后会开放下一章内容生成。"}
    if not isinstance(outline, dict):
        return {"status": "refused", "message": "请先生成课程大纲。"}
    try:
        require_student_visible_textbooks(session, outline)
        targets = common_mod._target_sections_for_scope(
            outline, ref, "chapter_sections"
        )
    except ValueError as exc:
        return {"status": "refused", "message": str(exc)}
    if not targets:
        return {"status": "refused", "message": "这一章没有可生成的小节。"}

    composed = outline.get("section_composed_markdowns")
    # Only a fully generated chapter asks for a focus; a partly failed one resumes.
    has_composed = isinstance(composed, dict) and all(
        _clean(t.get("section_id")) in composed for t in targets
    )
    if mode == "generate" and has_composed:
        return {"status": "needs_focus", "chapter_section_id": ref}
    try:
        start_course_generation(user_uid, course_id, ref)
    except ValueError as exc:
        return {"status": "busy", "message": str(exc)}

    markdowns = outline.get("section_markdowns")
    sections = []
    for target in targets:
        sid = _clean(target.get("section_id"))
        stored = markdowns.get(sid) if isinstance(markdowns, dict) else None
        sections.append(
            {
                "section_id": sid,
                "title": _clean(target.get("title")),
                "checkpoints": _checkpoint_status(outline, sid),
                "has_composed": isinstance(composed, dict) and sid in composed,
                "has_markdown": isinstance(stored, dict),
            }
        )
    return {
        "status": "ready",
        "course_id": course_id,
        "course_name": _clean(outline.get("course_name")),
        "chapter_section_id": ref,
        "sections": sections,
    }


def markdown_prompt(
    session: Session,
    user_uid: str,
    course_id: str,
    section_id: str,
    issue: str,
    regeneration_focus: str,
) -> dict:
    outline = _load(session, user_uid, course_id)
    section = _section(outline, section_id)
    query = markdown_mod._markdown_expansion_input(
        _state(session, user_uid, outline),
        outline,
        section,
        issue or "请生成完整 Markdown 教学文档。",
        "",
        "完整文档",
    )
    if regeneration_focus.strip():
        query += f"\n\n学生希望下一版重点侧重：{regeneration_focus.strip()}"
    return {
        "system_prompt": common_mod.SECTION_MARKDOWN_EXPANSION_SYSTEM_PROMPT,
        "query": query,
    }


def validate_markdown(
    session: Session,
    user_uid: str,
    course_id: str,
    section_id: str,
    raw_output: str,
) -> dict:
    outline = _load(session, user_uid, course_id)
    section = _section(outline, section_id)
    headings = common_mod._REQUIRED_MARKDOWN_HEADING_TITLES

    def bodies_of(data: dict) -> dict[str, str]:
        return {
            heading: markdown_mod._scaffolded_markdown_section_body(
                section,
                heading,
                markdown_mod._markdown_section_body(
                    _clean(data.get("markdown")), heading
                ),
            )
            for heading in headings
        }

    data = markdown_mod._markdown_data_from_full_document(raw_output, section)
    data = markdown_mod._normalize_markdown_resources(data, section)
    # The legacy pipeline scaffolds missing parts, which would hide a bad draft from
    # the model: judge what the model actually wrote first so it can repair itself.
    written = _clean(data.get("markdown"))
    raw_issues = [
        issue
        for heading in headings
        if (
            issue := markdown_mod._markdown_section_body_issue(
                heading, markdown_mod._markdown_section_body(written, heading)
            )
        )
    ]
    if raw_issues:
        return {"ok": False, "issue": "；".join(raw_issues)}
    data = markdown_mod._compose_llm_section_markdown(data, section, bodies_of(data))
    data = markdown_mod._normalize_markdown_resources(data, section)
    issue = markdown_mod._markdown_quality_issue(
        _clean(data.get("markdown")),
        section,
        data.get("video_briefs"),
        data.get("animation_briefs"),
    )
    if issue:
        return {"ok": False, "issue": issue}
    cleaned, reason = common_mod._extract_recommendation_reason(
        _clean(data.get("markdown"))
    )
    video_briefs = data.get("video_briefs")
    animation_briefs = data.get("animation_briefs")
    return {
        "ok": True,
        "value": {
            "user_id": user_uid,
            "section_id": section_id,
            "parent_section_id": section.get("parent_section_id"),
            "title": _clean(section.get("title")) or _clean(data.get("title")),
            "markdown": cleaned,
            "video_briefs": video_briefs if isinstance(video_briefs, list) else [],
            "animation_briefs": animation_briefs
            if isinstance(animation_briefs, list)
            else [],
            "recommendation_reason": reason,
            "generated_at": common_mod._now_iso(),
        },
    }


async def search_section_video(
    session: Session, user_uid: str, course_id: str, section_id: str
) -> dict:
    """Verified video search; "nothing found" degrades gracefully instead of raising."""
    outline = _load(session, user_uid, course_id)
    section = _section(outline, section_id)
    stored = (outline.get("section_markdowns") or {}).get(section_id)
    briefs = stored.get("video_briefs") if isinstance(stored, dict) else None
    query = " | ".join(video_mod._video_search_queries(briefs, section, outline)[:3])
    videos: list[dict] = []
    issue = "视频资源为空或未绑定 brief。"
    for _attempt in range(2):
        try:
            found = await video_mod._find_verified_video_from_search(
                briefs, section, outline
            )
        except Exception as exc:  # noqa: BLE001 - external search must never fail the section
            logger.warning("Verified video search failed for %s: %s", section_id, exc)
            issue = f"视频检索失败：{type(exc).__name__}"
            continue
        if not found:
            continue
        videos = video_mod._normalize_videos(found, briefs)
        issue = video_mod._native_video_quality_issue(videos, briefs) or ""
        if not issue:
            break
    base = {
        "user_id": user_uid,
        "section_id": section_id,
        "parent_section_id": section.get("parent_section_id"),
        "title": common_mod._section_title(outline, section),
        "query": query,
        "generated_at": common_mod._now_iso(),
    }
    if issue:
        return {
            "status": "unavailable",
            "value": {
                **base,
                "status": "unavailable",
                "failure_reason": f"未找到合格视频：{issue}",
                "videos": [],
            },
        }
    return {
        "status": "available",
        "value": {
            **base,
            "status": "available",
            "failure_reason": "",
            "videos": videos,
        },
    }


def _animation_briefs(outline: dict, section: dict) -> tuple[object, list[dict]]:
    stored = (outline.get("section_markdowns") or {}).get(
        _clean(section.get("section_id"))
    )
    raw = stored.get("animation_briefs") if isinstance(stored, dict) else None
    return raw, markdown_mod._normalize_markdown_animation_briefs(section, raw)


def animation_prompt(
    session: Session,
    user_uid: str,
    course_id: str,
    section_id: str,
    issue: str,
    previous_html: str,
) -> dict:
    outline = _load(session, user_uid, course_id)
    section = _section(outline, section_id)
    _raw, briefs = _animation_briefs(outline, section)
    if not briefs:
        return {"needed": False}
    state = _state(session, user_uid, outline)
    query = (
        animation_mod._animation_repair_input(
            state, outline, section, issue, previous_html
        )
        if issue
        else animation_mod._animation_input(state, outline, section)
    )
    return {
        "needed": True,
        "system_prompt": SECTION_HTML_ANIMATION_AGENT_SYSTEM_PROMPT,
        "query": query,
    }


def _animation_value(outline: dict, section: dict, animations: list[dict]) -> dict:
    section_id = _clean(section.get("section_id"))
    return {
        "section_id": section_id,
        "parent_section_id": section.get("parent_section_id"),
        "title": common_mod._section_title(outline, section),
        "animations": animations,
        "generated_at": common_mod._now_iso(),
    }


def validate_animations(
    session: Session,
    user_uid: str,
    course_id: str,
    section_id: str,
    raw_animations: list[dict],
    *,
    fallback: bool = False,
) -> dict:
    outline = _load(session, user_uid, course_id)
    section = _section(outline, section_id)
    raw_briefs, briefs = _animation_briefs(outline, section)
    if not briefs:
        return {"ok": True, "value": _animation_value(outline, section, [])}
    try:
        animations = animation_mod._normalize_animations(
            animation_mod._deterministic_animation_data(briefs, section)
            if fallback
            else raw_animations,
            briefs,
        )
    except Exception as exc:  # noqa: BLE001 - normalisation errors are model-facing issues
        return {"ok": False, "issue": f"动画结构无法解析：{exc}"}
    issue = animation_mod._normalized_animation_quality_issue(
        animations, raw_briefs, section
    )
    if issue or not animations:
        return {"ok": False, "issue": issue or "动画为空。"}
    return {"ok": True, "value": _animation_value(outline, section, animations)}


def _refs(phase: str, outline: dict, section_id: str) -> dict:
    if phase == "markdown":
        return resource_main._section_markdown_output_refs(outline, section_id)
    if phase == "video":
        return resource_main._section_video_output_refs(outline, section_id)
    if phase == "animation":
        return resource_main._section_animation_output_refs(outline, section_id)
    return resource_main._section_compose_output_refs(outline, section_id)


def save_section_phase(
    session: Session,
    user_uid: str,
    course_id: str,
    section_id: str,
    phase: str,
    value: dict | None,
    failure: str,
) -> dict:
    """Atomically merge one section's phase result under the student lock.

    Only this section's keys are touched, so concurrent sections never overwrite
    each other.
    """
    if phase not in PHASES:
        raise ResourceRequestError("未知的资源阶段。")
    try:
        lock_student(session, user_uid)
        outline = copy.deepcopy(_load(session, user_uid, course_id))
        section = _section(outline, section_id)
        failed = bool(failure)
        if not failed:
            if phase == "compose":
                markdown_value = (outline.get("section_markdowns") or {}).get(
                    section_id
                )
                if not isinstance(markdown_value, dict):
                    raise ResourceRequestError("小节正文尚未生成，无法拼装。")
                videos = (outline.get("section_video_links") or {}).get(
                    section_id
                ) or {}
                animations = (outline.get("section_html_animations") or {}).get(
                    section_id
                ) or {}
                value = common_mod._compose_section_content(
                    markdown_value, videos, animations
                )
                outline.setdefault("section_composed_markdowns", {})[section_id] = value
            else:
                if not isinstance(value, dict):
                    raise ResourceRequestError("缺少阶段结果。")
                outline.setdefault(_STORE_KEYS[phase], {})[section_id] = value
            errors = outline.get("section_resource_errors")
            if isinstance(errors, dict) and phase == "compose":
                errors.pop(section_id, None)
        else:
            outline.setdefault("section_resource_errors", {})[section_id] = {
                "section_id": section_id,
                "phase": phase,
                "message": failure,
                "retryable": True,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        refs = {} if failed else _refs(phase, outline, section_id)
        outline = update_section_phase_checkpoint(
            outline,
            section_id=section_id,
            phase=phase,
            status="failed" if failed else "completed",
            output_refs=refs,
            quality_result=quality_passed().to_dict(),
            failure_reason=failure,
        )
        upsert_user_course_knowledge_outline(session, user_uid, outline, commit=False)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return {
        "section_id": section_id,
        "phase": phase,
        "output_refs": refs,
        "title": _clean(section.get("title")),
    }


def finish_generation(
    session: Session,
    user_uid: str,
    course_id: str,
    chapter_id: str,
    succeeded_section_ids: list[str],
) -> dict:
    """Release the chapter lock (always) and, when something was produced, score it."""
    scored = False
    try:
        if succeeded_section_ids:
            outline = get_user_course_knowledge_outline(session, user_uid, course_id)
            if isinstance(outline, dict):
                markdown_mod._score_generated_resources(user_uid, outline)
                scored = True
                rows = session.exec(
                    select(ChapterWeakness).where(
                        ChapterWeakness.user_uid == user_uid,
                        ChapterWeakness.course_node_id == course_id,
                        ChapterWeakness.consumed.is_(False),
                    )
                ).all()
                for row in rows:
                    row.consumed = True
                    session.add(row)
                session.commit()
    except Exception:  # noqa: BLE001 - scoring is best effort, the lock must still be released
        session.rollback()
        logger.warning(
            "Resource scoring failed for %s/%s", user_uid, course_id, exc_info=True
        )
    finally:
        finish_course_generation(user_uid, course_id, chapter_id)
    return {"released": True, "scored": scored}
