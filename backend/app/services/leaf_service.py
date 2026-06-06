from __future__ import annotations

from fastapi import HTTPException, status
from sqlmodel import Session

from app.orchestration.agents.course_resources import _compose_section_content
from app.schemas import LeafCourseRead, LeafCourseReadResponse, LeafGenerationStatusRead
from app.services.course_generation_status_service import get_course_generation_status
from app.services.course_knowledge_service import get_user_course_knowledge_outline
from app.services.learning_path_service import (
    compare_grade_years,
    get_all_year_learning_paths,
    get_current_grade_year_from_path,
    get_current_learning_course,
    get_grade_courses,
)


def _clean_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _status_for_course(path_data: dict, rendered_grade_id: str, courses: list[dict], index: int) -> str:
    current_grade_id = get_current_grade_year_from_path(path_data)
    grade_compare = compare_grade_years(rendered_grade_id, current_grade_id)
    if grade_compare < 0:
        return "completed"
    if grade_compare > 0:
        return "locked"

    current = get_current_learning_course(path_data)
    current_course_id = _clean_text(current.get("course_node_id")) if isinstance(current, dict) else ""
    current_index = next(
        (
            item_index
            for item_index, course in enumerate(courses)
            if course.get("course_node_id") == current_course_id
        ),
        -1,
    )
    if current_index < 0:
        return "locked"
    if index < current_index:
        return "completed"
    if index == current_index:
        progress_state = _clean_text(current.get("progress_state")) if isinstance(current, dict) else ""
        return "completed" if progress_state == "completed" else "current"
    return "locked"


def _find_course(year_paths: dict[str, dict], course_node_id: str) -> tuple[dict, str, dict, int, str] | None:
    for grade_id, path_data in year_paths.items():
        if not isinstance(path_data, dict):
            continue
        courses = get_grade_courses(path_data, grade_id)
        for index, course in enumerate(courses):
            if not isinstance(course, dict):
                continue
            if course.get("course_node_id") != course_node_id:
                continue
            status_value = _status_for_course(path_data, grade_id, courses, index)
            return path_data, grade_id, course, index, status_value
    return None


def _composed_sections_from_outline(outline: dict) -> dict[str, dict]:
    composed = outline.get("section_composed_markdowns")
    result = dict(composed) if isinstance(composed, dict) else {}

    section_markdowns = outline.get("section_markdowns")
    if not isinstance(section_markdowns, dict):
        return result

    section_video_links = outline.get("section_video_links")
    section_html_animations = outline.get("section_html_animations")

    for section_id, section_markdown in section_markdowns.items():
        if section_id in result or not isinstance(section_markdown, dict):
            continue
        video_links = section_video_links.get(section_id) if isinstance(section_video_links, dict) else {}
        animations = (
            section_html_animations.get(section_id)
            if isinstance(section_html_animations, dict)
            else {}
        )
        result[str(section_id)] = _compose_section_content(
            section_markdown,
            video_links if isinstance(video_links, dict) else {},
            animations if isinstance(animations, dict) else {},
        )

    return result


def read_leaf_course(session: Session, user_uid: str, course_node_id: str) -> LeafCourseReadResponse:
    year_paths = get_all_year_learning_paths(session, user_uid)
    found = _find_course(year_paths, course_node_id)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程不存在")

    _path_data, grade_id, course, _index, course_status = found
    outline = get_user_course_knowledge_outline(session, user_uid, course_node_id)
    has_outline = isinstance(outline, dict)
    sections = outline.get("sections", []) if isinstance(outline, dict) and isinstance(outline.get("sections"), list) else []
    composed = _composed_sections_from_outline(outline) if isinstance(outline, dict) else {}
    running = get_course_generation_status(user_uid, course_node_id)

    generation_status = (
        LeafGenerationStatusRead(
            course_node_id=running.course_node_id,
            chapter_section_id=running.chapter_section_id,
            status="running",
            message=running.message,
        )
        if running is not None
        else None
    )

    leaf_course = LeafCourseRead(
        course_node_id=course_node_id,
        grade_id=grade_id,
        course_or_chapter_theme=_clean_text(course.get("course_or_chapter_theme")) or course_node_id,
        course_goal=_clean_text(course.get("course_goal")) or "继续沿着学习路径稳步推进。",
        status=course_status,
        has_outline=has_outline,
    )

    if course_status == "locked":
        return LeafCourseReadResponse(
            access_state="locked",
            course=leaf_course,
            outline=None,
            sections=[],
            section_composed_markdowns={},
            generation_status=generation_status,
            can_generate=False,
            first_generatable_chapter_id=None,
            locked_reason="这门课程还未解锁。",
        )

    return LeafCourseReadResponse(
        access_state="available",
        course=leaf_course,
        outline=outline,
        sections=sections,
        section_composed_markdowns=composed,
        generation_status=generation_status,
        can_generate=course_status == "current",
        first_generatable_chapter_id="1" if course_status == "current" else None,
        locked_reason=None,
    )
