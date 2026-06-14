from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session

from app.models import ConversationSession


def load_session(session: Session, session_id: str) -> ConversationSession | None:
    return session.get(ConversationSession, session_id)


def latest_learning_path_intake(messages: list[dict]) -> dict | None:
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("type") == "learning_path_intake":
            return message
    return None


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


def replace_latest_learning_path_intake(session: Session, session_id: str, intake: dict) -> ConversationSession:
    row = session.get(ConversationSession, session_id)
    if row is None:
        raise ValueError(f"Conversation session {session_id} not found")
    row.messages = [
        message
        for message in row.messages
        if not (isinstance(message, dict) and message.get("type") == "learning_path_intake")
    ] + [intake]
    row.updated_at = datetime.now(timezone.utc)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def append_messages(session: Session, session_id: str, new_messages: list[dict]) -> ConversationSession:
    row = session.get(ConversationSession, session_id)
    if row is None:
        raise ValueError(f"Conversation session {session_id} not found")
    session.refresh(row)
    row.messages = (row.messages or []) + new_messages
    row.updated_at = datetime.now(timezone.utc)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
