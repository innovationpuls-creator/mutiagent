from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session

from app.models import UserProfile


def get_user_profile(session: Session, user_uid: str) -> dict | None:
    row = session.get(UserProfile, user_uid)
    if row is None:
        return None
    return row.profile_data


def upsert_user_profile(session: Session, user_uid: str, profile_data: dict) -> UserProfile:
    now = datetime.now(timezone.utc)
    profile_text = profile_data.get("summary_text", profile_data.get("text", ""))
    row = session.get(UserProfile, user_uid)
    if row is None:
        row = UserProfile(
            user_uid=user_uid,
            profile_data=profile_data,
            profile_text=profile_text,
            created_at=now,
            updated_at=now,
        )
    else:
        row.profile_data = profile_data
        row.profile_text = profile_text
        row.updated_at = now
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
