from __future__ import annotations

from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.models import User
from app.services.conversation_session_service import (
    append_messages,
    load_or_create_session,
)


def build_session(tmp_path: Path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'conversation-session.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    session.add(User(uid="user-1", username="会话用户", identifier="conversation-session@example.com"))
    session.add(User(uid="user-2", username="第二用户", identifier="conversation-session-2@example.com"))
    session.commit()
    return session


def test_load_or_create_session_creates_empty_session_for_new_id(tmp_path: Path) -> None:
    session = build_session(tmp_path)

    row = load_or_create_session(session, "sess-new", "user-1")

    assert row.session_id == "sess-new"
    assert row.user_uid == "user-1"
    assert row.messages == []


def test_load_or_create_session_returns_existing_session_for_same_user(tmp_path: Path) -> None:
    session = build_session(tmp_path)
    created = load_or_create_session(session, "sess-existing", "user-1")
    append_messages(
        session,
        "sess-existing",
        [
            {"type": "human", "data": {"content": "你好"}},
            {"type": "ai", "data": {"content": "欢迎回来"}},
        ],
    )

    loaded = load_or_create_session(session, "sess-existing", "user-1")

    assert loaded.session_id == created.session_id
    assert loaded.user_uid == "user-1"
    assert loaded.messages == [
        {"type": "human", "data": {"content": "你好"}},
        {"type": "ai", "data": {"content": "欢迎回来"}},
    ]


def test_load_or_create_session_rejects_session_owned_by_another_user(tmp_path: Path) -> None:
    session = build_session(tmp_path)
    load_or_create_session(session, "sess-owned", "user-1")

    with pytest.raises(ValueError, match="does not belong to user user-2"):
        load_or_create_session(session, "sess-owned", "user-2")


def test_append_messages_appends_in_order(tmp_path: Path) -> None:
    session = build_session(tmp_path)
    load_or_create_session(session, "sess-append", "user-1")

    append_messages(
        session,
        "sess-append",
        [{"type": "human", "data": {"content": "第一条"}}],
    )
    updated = append_messages(
        session,
        "sess-append",
        [{"type": "ai", "data": {"content": "第二条"}}],
    )

    assert updated.messages == [
        {"type": "human", "data": {"content": "第一条"}},
        {"type": "ai", "data": {"content": "第二条"}},
    ]


def test_append_messages_raises_for_missing_session(tmp_path: Path) -> None:
    session = build_session(tmp_path)

    with pytest.raises(ValueError, match="Conversation session sess-missing not found"):
        append_messages(session, "sess-missing", [{"type": "human", "data": {"content": "你好"}}])
