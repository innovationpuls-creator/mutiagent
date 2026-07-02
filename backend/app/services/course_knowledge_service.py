from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, select

from app.models import UserCourseKnowledgeOutline

SECTION_GENERATED_ASSET_KEYS = (
    "section_markdowns",
    "section_composed_markdowns",
    "section_video_links",
    "section_html_animations",
)
SECTION_STRUCTURE_SIGNATURE_KEYS = (
    "section_id",
    "parent_section_id",
    "depth",
    "title",
    "order_index",
    "description",
    "key_knowledge_points",
)
SECTION_SOURCE_SIGNATURE_KEYS = (
    "source_textbook_id",
    "source_textbook_title",
    "source_section_ids",
    "source_section_titles",
    "source_content_chars",
)


def get_user_course_knowledge_outline(
    session: Session, user_uid: str, course_id: str
) -> dict | None:
    row = session.get(UserCourseKnowledgeOutline, (user_uid, course_id))
    if row is None:
        return None
    return row.outline_data


def list_user_course_outlines(
    session: Session, user_uid: str
) -> list[UserCourseKnowledgeOutline]:
    stmt = select(UserCourseKnowledgeOutline).where(
        UserCourseKnowledgeOutline.user_uid == user_uid
    )
    return list(session.exec(stmt).all())


def delete_user_course_outlines(session: Session, user_uid: str) -> int:
    stmt = select(UserCourseKnowledgeOutline).where(
        UserCourseKnowledgeOutline.user_uid == user_uid
    )
    rows = list(session.exec(stmt).all())
    for row in rows:
        session.delete(row)
    if rows:
        session.commit()
    return len(rows)


def delete_user_course_outlines_by_grade_year(
    session: Session,
    user_uid: str,
    grade_year: str,
) -> int:
    stmt = select(UserCourseKnowledgeOutline).where(
        UserCourseKnowledgeOutline.user_uid == user_uid,
        UserCourseKnowledgeOutline.grade_year == grade_year,
    )
    rows = list(session.exec(stmt).all())
    for row in rows:
        session.delete(row)
    if rows:
        session.commit()
    return len(rows)


def get_latest_user_course_knowledge_outline(
    session: Session, user_uid: str
) -> dict | None:
    stmt = (
        select(UserCourseKnowledgeOutline)
        .where(UserCourseKnowledgeOutline.user_uid == user_uid)
        .order_by(UserCourseKnowledgeOutline.updated_at.desc())
    )
    row = session.exec(stmt).first()
    if row is None:
        return None
    return row.outline_data


def _section_signature(section: object) -> dict:
    if not isinstance(section, dict):
        return {}
    return {
        key: section.get(key)
        for key in (*SECTION_STRUCTURE_SIGNATURE_KEYS, *SECTION_SOURCE_SIGNATURE_KEYS)
    }


def _outline_sections_signature(outline_data: object) -> list[dict]:
    if not isinstance(outline_data, dict):
        return []
    sections = outline_data.get("sections")
    if not isinstance(sections, list):
        return []
    return [_section_signature(section) for section in sections]


def _outline_sections_changed(existing_outline: dict, next_outline: dict) -> bool:
    return _outline_sections_signature(existing_outline) != _outline_sections_signature(
        next_outline
    )


def _clear_section_generated_assets(outline_data: dict) -> dict:
    cleaned = dict(outline_data)
    for key in SECTION_GENERATED_ASSET_KEYS:
        cleaned.pop(key, None)
    return cleaned


def upsert_user_course_knowledge_outline(
    session: Session,
    user_uid: str,
    outline_data: dict,
) -> UserCourseKnowledgeOutline:
    now = datetime.now(timezone.utc)
    course_id = outline_data.get("course_id", "")
    row = session.get(UserCourseKnowledgeOutline, (user_uid, course_id))
    if row is None:
        row = UserCourseKnowledgeOutline(
            user_uid=user_uid,
            course_id=course_id,
            grade_year=outline_data.get("grade_year", ""),
            course_name=outline_data.get("course_name", ""),
            outline_data=outline_data,
            created_at=now,
            updated_at=now,
        )
    else:
        row.grade_year = outline_data.get("grade_year", row.grade_year)
        row.course_name = outline_data.get("course_name", row.course_name)
        if _outline_sections_changed(row.outline_data, outline_data):
            outline_data = _clear_section_generated_assets(outline_data)
        row.outline_data = outline_data
        row.updated_at = now
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
