from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session

from app.models import ConversationSession


def load_session(session: Session, session_id: str) -> ConversationSession | None:
    return session.get(ConversationSession, session_id)


def load_or_create_session(session: Session, session_id: str, user_uid: str) -> ConversationSession:
    row = session.get(ConversationSession, session_id)
    if row is not None:
        if row.user_uid != user_uid:
            raise ValueError(f"Conversation session {session_id} does not belong to user {user_uid}")
        return row

    now = datetime.now(timezone.utc)
    row = ConversationSession(
        session_id=session_id,
        user_uid=user_uid,
        messages=[],
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def append_messages(session: Session, session_id: str, new_messages: list[dict]) -> ConversationSession:
    row = session.get(ConversationSession, session_id)
    if row is None:
        raise ValueError(f"Conversation session {session_id} not found")
    row.messages = list(row.messages) + new_messages
    row.updated_at = datetime.now(timezone.utc)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
