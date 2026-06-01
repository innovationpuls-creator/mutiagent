from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session

from app.models import UserAgentConversation


def get_agent_conversation_id(session: Session, user_uid: str, agent_key: str) -> str:
    stored = session.get(UserAgentConversation, (user_uid, agent_key))
    if stored is None:
        return ""
    return stored.conversation_id


def upsert_agent_conversation(
    session: Session,
    user_uid: str,
    agent_key: str,
    conversation_id: str,
) -> UserAgentConversation:
    stored = session.get(UserAgentConversation, (user_uid, agent_key))
    now = datetime.now(timezone.utc)
    if stored is None:
        stored = UserAgentConversation(
            user_uid=user_uid,
            agent_key=agent_key,
            conversation_id=conversation_id,
            created_at=now,
            updated_at=now,
        )
    else:
        stored.conversation_id = conversation_id
        stored.updated_at = now

    session.add(stored)
    session.commit()
    session.refresh(stored)
    return stored
