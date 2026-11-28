"""Deterministic Python side of the TS-gateway AI jobs for Forest and the growth report.

The gateway owns every model call; this module only reads data and enforces contracts.
"""

from __future__ import annotations

import json

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models import ChapterQuiz, ChapterQuizAttempt
from app.orchestration.agents.course_resources import markdown as markdown_mod
from app.report_schemas import EvidenceRequest, ReportNarrative
from app.services.course_knowledge_service import get_user_course_knowledge_outline
from app.services.forest_service import _top_level_sections
from app.services.growth_report_context import (
    build_report_context,
    read_report_evidence,
)
from app.services.growth_report_service import (
    _validate_numbers,
    generate_report_from_narrative,
    validate_narrative,
)

MATERIAL_SECTION_CHARS = 6000
MATERIAL_TOTAL_CHARS = 24000


def _clean(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def extract_knowledge_point_ids(chapter: dict) -> list[str]:
    """All knowledge point ids a chapter may tag its questions with."""
    ids: list[str] = []
    ids.extend(chapter.get("core_knowledge_point_ids") or [])
    for hierarchy in chapter.get("knowledge_hierarchy") or []:
        if isinstance(hierarchy, dict):
            ids.extend(hierarchy.get("knowledge_point_ids") or [])
    key_points = chapter.get("key_knowledge_points", [])
    if isinstance(key_points, list):
        for point in key_points:
            if isinstance(point, str):
                ids.append(point)
            elif isinstance(point, dict):
                found = point.get("knowledge_point_id") or point.get("id")
                if found:
                    ids.append(str(found))
    return list(dict.fromkeys(str(i).strip() for i in ids if str(i).strip()))


def _children(outline: dict, chapter_id: str) -> list[dict]:
    sections = outline.get("sections")
    rows = sections if isinstance(sections, list) else []
    return [
        s
        for s in rows
        if isinstance(s, dict) and _clean(s.get("parent_section_id")) == chapter_id
    ]


def _markdown_of(outline: dict, section_id: str) -> str:
    for key in ("section_markdowns", "section_composed_markdowns"):
        bucket = outline.get(key)
        item = bucket.get(section_id) if isinstance(bucket, dict) else None
        if isinstance(item, dict) and _clean(item.get("markdown")):
            return _clean(item["markdown"])
    return ""


def quiz_generation_material(
    session: Session, uid: str, course_node_id: str, chapter: dict
) -> dict:
    """Every leaf section's practice task and criteria for the question writer."""
    outline = get_user_course_knowledge_outline(session, uid, course_node_id) or {}
    chapter_id = _clean(chapter.get("section_id"))
    sections = []
    for child in _children(outline, chapter_id) or [chapter]:
        sid = _clean(child.get("section_id"))
        markdown = _markdown_of(outline, sid)
        sections.append(
            {
                "section_id": sid,
                "title": _clean(child.get("title")),
                "key_knowledge_points": child.get("key_knowledge_points") or [],
                "practice_task": markdown_mod._markdown_section_body(
                    markdown, "练习任务"
                )
                if markdown
                else "",
                "check_criteria": markdown_mod._markdown_section_body(
                    markdown, "检查标准"
                )
                if markdown
                else "",
            }
        )
    return {
        "chapter_id": chapter_id,
        "chapter_title": _clean(chapter.get("title")),
        "description": _clean(chapter.get("description")),
        "knowledge_point_ids": extract_knowledge_point_ids(chapter),
        "sections": sections,
    }


def forest_material(
    session: Session,
    uid: str,
    course_node_id: str,
    chapter_id: str,
    quiz_id: str | None,
) -> dict:
    """Read-only chapter material for Forest AI plus whether the quiz was submitted."""
    outline = get_user_course_knowledge_outline(session, uid, course_node_id)
    if not isinstance(outline, dict):
        raise HTTPException(status_code=404, detail="课程大纲不存在")
    chapter = next(
        (c for c in _top_level_sections(outline) if c.get("section_id") == chapter_id),
        None,
    )
    if chapter is None:
        raise HTTPException(status_code=404, detail="章节不存在")
    budget = MATERIAL_TOTAL_CHARS
    sections = []
    for child in _children(outline, chapter_id) or [chapter]:
        sid = _clean(child.get("section_id"))
        text = _markdown_of(outline, sid)[: min(MATERIAL_SECTION_CHARS, budget)]
        budget -= len(text)
        sections.append(
            {"section_id": sid, "title": _clean(child.get("title")), "markdown": text}
        )
    submitted = False
    if quiz_id:
        quiz = session.get(ChapterQuiz, quiz_id)
        if quiz is not None and quiz.user_uid == uid:
            submitted = (
                session.exec(
                    select(ChapterQuizAttempt.attempt_id).where(
                        ChapterQuizAttempt.user_uid == uid,
                        ChapterQuizAttempt.quiz_id == quiz_id,
                    )
                ).first()
                is not None
            )
    return {
        "chapter_title": _clean(chapter.get("title")),
        "sections": sections,
        "submitted": submitted,
    }


def report_context(session: Session, uid: str) -> dict:
    context = build_report_context(session, uid)
    return {
        "summary": context.summary(),
        "evidence_ids": list(context.evidence),
        "tools": {k: v[0] for k, v in context.tools.items()},
        "has_attempts": context.stats.attempts > 0,
    }


def report_evidence(session: Session, uid: str, tool: str, evidence_id: str) -> dict:
    context = build_report_context(session, uid)
    try:
        request = EvidenceRequest(tool=tool, evidence_id=evidence_id)  # type: ignore[arg-type]
        text = read_report_evidence(session, uid, context, request)
    except ValueError as exc:
        return {"ok": False, "issue": str(exc)}
    return {"ok": True, "text": text}


def report_validate(
    session: Session, uid: str, narrative: dict, details: dict[str, str]
) -> dict:
    """The four anti-hallucination checks; returns the final GrowthReport on success."""
    context = build_report_context(session, uid)
    try:
        parsed = ReportNarrative.model_validate(narrative)
        validate_narrative(parsed, context, set(details))
        facts = (
            context.summary()
            + "\n已读取详情："
            + json.dumps(details, ensure_ascii=False)
        )
        _validate_numbers(parsed, facts)
    except ValueError as exc:
        allowed = json.dumps(list(context.evidence), ensure_ascii=False)
        return {"ok": False, "issue": f"{exc}。允许的证据 ID（逐字复制）：{allowed}"}
    report = generate_report_from_narrative(context, parsed)
    return {"ok": True, "report": report.model_dump(mode="json")}
