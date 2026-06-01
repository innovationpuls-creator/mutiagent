from __future__ import annotations

from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from app.models import User
from app.services.agent_conversation_service import get_agent_conversation_id, upsert_agent_conversation


def build_session(tmp_path: Path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'agent-conversation.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    session.add(User(uid="user-1", username="测试用户", identifier="agent-conversation@example.com"))
    session.commit()
    return session


def test_upsert_agent_conversation_creates_and_updates_by_agent_key(tmp_path: Path) -> None:
    session = build_session(tmp_path)

    created = upsert_agent_conversation(
        session=session,
        user_uid="user-1",
        agent_key="main_agent",
        conversation_id="main-conv-1",
    )
    updated = upsert_agent_conversation(
        session=session,
        user_uid="user-1",
        agent_key="main_agent",
        conversation_id="main-conv-2",
    )

    assert created.user_uid == "user-1"
    assert updated.conversation_id == "main-conv-2"
    assert get_agent_conversation_id(session, "user-1", "main_agent") == "main-conv-2"
    assert get_agent_conversation_id(session, "user-1", "profile_agent") == ""
