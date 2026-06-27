from __future__ import annotations

from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.database import build_engine, init_db, set_engine
from app.models import User
from app.services.conversation_session_service import (
    append_messages,
    latest_learning_path_intake,
    load_or_create_session,
    load_session,
    replace_latest_learning_path_intake,
)


def build_session(tmp_path: Path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'conversation-session.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    session.add(
        User(
            uid="user-1",
            username="会话用户",
            identifier="conversation-session@example.com",
        )
    )
    session.add(
        User(
            uid="user-2",
            username="第二用户",
            identifier="conversation-session-2@example.com",
        )
    )
    session.commit()
    return session


def test_load_or_create_session_creates_empty_session_for_new_id(
    tmp_path: Path,
) -> None:
    session = build_session(tmp_path)

    row = load_or_create_session(session, "sess-new", "user-1")

    assert row.session_id == "sess-new"
    assert row.user_uid == "user-1"
    assert row.messages == []


def test_load_or_create_session_returns_existing_session_for_same_user(
    tmp_path: Path,
) -> None:
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


def test_load_or_create_session_rejects_session_owned_by_another_user(
    tmp_path: Path,
) -> None:
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
        append_messages(
            session, "sess-missing", [{"type": "human", "data": {"content": "你好"}}]
        )


def test_replace_latest_learning_path_intake_message(tmp_path: Path) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'session-intake.db'}")
    set_engine(engine)
    init_db(engine)

    with Session(engine) as session:
        session.add(
            User(
                uid="user-1",
                username="会话用户",
                identifier="conversation-session@example.com",
            )
        )
        session.commit()
        load_or_create_session(session, "session-intake", "user-1")
        first = {
            "type": "learning_path_intake",
            "status": "draft",
            "grade_year": "year_3",
            "grade_name": "大三",
            "learning_topic": "数据结构",
            "courses": [{"title": "数据结构基础", "purpose": "建立基础"}],
            "recommendation_reasons": ["目标是学习数据结构"],
            "user_modification_summary": "",
            "risk_warnings": [],
            "requires_second_confirmation": False,
        }
        second = {
            **first,
            "courses": [
                {"title": "数据结构基础", "purpose": "建立基础"},
                {"title": "线性结构实践", "purpose": "练习数组链表栈队列"},
            ],
        }

        replace_latest_learning_path_intake(session, "session-intake", first)
        replace_latest_learning_path_intake(session, "session-intake", second)
        row = load_session(session, "session-intake")

    intake_messages = [
        message
        for message in row.messages
        if isinstance(message, dict) and message.get("type") == "learning_path_intake"
    ]
    assert intake_messages == [second]
    assert latest_learning_path_intake(row.messages) == second
