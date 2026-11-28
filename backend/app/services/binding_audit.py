"""Read-only audit: which saved courses cannot generate an outline any more.

Outlines need an explicit textbook binding (no keyword guessing). Paths saved by
older versions may lack it; this finds them so the owners can be asked to
regenerate the path draft. It never writes.
"""

from __future__ import annotations

from sqlmodel import Session, select

from app.models import Textbook, UserYearLearningPath
from app.services.learning_path_service import get_grade_courses


def audit_course_bindings(session: Session) -> list[dict[str, str]]:
    """One row per unusable course: user, grade, course id/title and the reason."""
    published = {
        textbook_id
        for textbook_id in session.exec(
            select(Textbook.textbook_id).where(
                Textbook.student_availability_status == "published"
            )
        ).all()
    }
    problems: list[dict[str, str]] = []
    for row in session.exec(select(UserYearLearningPath)).all():
        for course in get_grade_courses(row.path_data or {}, row.grade_year):
            textbook_id = str(course.get("source_textbook_id") or "").strip()
            sections = course.get("source_outline_section_ids")
            reason = ""
            if not textbook_id or textbook_id.lower() in {"none", "null"}:
                reason = "没有教材绑定"
            elif not isinstance(sections, list) or not sections:
                reason = "没有绑定教材小节"
            elif textbook_id not in published:
                reason = "绑定的教材已不是已发布状态"
            if reason:
                problems.append(
                    {
                        "user_uid": row.user_uid,
                        "grade_year": row.grade_year,
                        "course_node_id": str(course.get("course_node_id") or ""),
                        "course": str(course.get("course_or_chapter_theme") or ""),
                        "reason": reason,
                    }
                )
    return problems
