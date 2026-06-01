from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session

from app.models import UserLearningPath


def get_user_learning_path(session: Session, user_uid: str) -> UserLearningPath | None:
    return session.get(UserLearningPath, user_uid)


def upsert_user_learning_path(session: Session, user_uid: str, path_data: dict) -> UserLearningPath:
    stored = session.get(UserLearningPath, user_uid)
    now = datetime.now(timezone.utc)
    if stored is None:
        stored = UserLearningPath(
            user_uid=user_uid,
            path_data=path_data,
            created_at=now,
            updated_at=now,
        )
    else:
        stored.path_data = path_data
        stored.updated_at = now

    session.add(stored)
    session.commit()
    session.refresh(stored)
    return stored
