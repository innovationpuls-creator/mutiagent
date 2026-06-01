from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session

from app.models import UserProfile


def upsert_user_profile(session: Session, user_uid: str, profile_result: dict) -> UserProfile:
    profile = session.get(UserProfile, user_uid)
    now = datetime.now(timezone.utc)
    profile_text = str(profile_result.get("text", ""))

    if profile is None:
        profile = UserProfile(
            user_uid=user_uid,
            profile_data=profile_result,
            profile_text=profile_text,
            created_at=now,
            updated_at=now,
        )
    else:
        profile.profile_data = profile_result
        profile.profile_text = profile_text
        profile.updated_at = now

    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile
