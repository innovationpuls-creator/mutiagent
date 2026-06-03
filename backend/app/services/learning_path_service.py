from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, select

from app.models import UserYearLearningPath


def get_year_learning_path(session: Session, user_uid: str, grade_year: str) -> dict | None:
    row = session.get(UserYearLearningPath, (user_uid, grade_year))
    if row is None:
        return None
    return row.path_data


def get_all_year_learning_paths(session: Session, user_uid: str) -> dict[str, dict]:
    stmt = select(UserYearLearningPath).where(UserYearLearningPath.user_uid == user_uid)
    rows = session.exec(stmt).all()
    return {row.grade_year: row.path_data for row in rows}


def upsert_year_learning_path(
    session: Session,
    user_uid: str,
    grade_year: str,
    learning_topic: str,
    path_data: dict,
) -> UserYearLearningPath:
    now = datetime.now(timezone.utc)
    row = session.get(UserYearLearningPath, (user_uid, grade_year))
    if row is None:
        row = UserYearLearningPath(
            user_uid=user_uid,
            grade_year=grade_year,
            learning_topic=learning_topic,
            path_data=path_data,
            created_at=now,
            updated_at=now,
        )
    else:
        row.learning_topic = learning_topic
        row.path_data = path_data
        row.updated_at = now
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
