from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, select

from app.models import UserCourseKnowledgeOutline


def get_user_course_knowledge_outline(
    session: Session, user_uid: str, course_id: str
) -> dict | None:
    row = session.get(UserCourseKnowledgeOutline, (user_uid, course_id))
    if row is None:
        return None
    return row.outline_data


def list_user_course_outlines(session: Session, user_uid: str) -> list[UserCourseKnowledgeOutline]:
    stmt = select(UserCourseKnowledgeOutline).where(
        UserCourseKnowledgeOutline.user_uid == user_uid
    )
    return list(session.exec(stmt).all())


def get_latest_user_course_knowledge_outline(session: Session, user_uid: str) -> dict | None:
    stmt = (
        select(UserCourseKnowledgeOutline)
        .where(UserCourseKnowledgeOutline.user_uid == user_uid)
        .order_by(UserCourseKnowledgeOutline.updated_at.desc())
    )
    row = session.exec(stmt).first()
    if row is None:
        return None
    return row.outline_data


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
        row.outline_data = outline_data
        row.updated_at = now
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
