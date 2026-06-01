from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session

from app.models import UserDifyConversation


def get_user_dify_conversation(session: Session, user_uid: str) -> UserDifyConversation | None:
    return session.get(UserDifyConversation, user_uid)


def upsert_user_dify_conversation(
    session: Session,
    user_uid: str,
    intent_conversation_id: str,
    profile_conversation_id: str,
) -> UserDifyConversation:
    stored = session.get(UserDifyConversation, user_uid)
    now = datetime.now(timezone.utc)
    if stored is None:
        stored = UserDifyConversation(
            user_uid=user_uid,
            intent_conversation_id=intent_conversation_id,
            profile_conversation_id=profile_conversation_id,
            created_at=now,
            updated_at=now,
        )
    else:
        stored.intent_conversation_id = intent_conversation_id
        stored.profile_conversation_id = profile_conversation_id
        stored.updated_at = now

    session.add(stored)
    session.commit()
    session.refresh(stored)
    return stored
