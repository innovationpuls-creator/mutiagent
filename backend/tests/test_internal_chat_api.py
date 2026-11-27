from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlmodel import Session

from app.core.config import DEFAULT_INTERNAL_API_TOKEN
from app.database import DEMO_USER_UID
from app.main import create_app
from app.models import ChapterWeakness, ConversationSession
from tests.postgres import postgresql_test_url

INTERNAL = {"X-Internal-Token": DEFAULT_INTERNAL_API_TOKEN}
CONFIRMED = {
    "current_grade": "大三",
    "major": "软件工程",
    "learning_stage": "有基础",
    "has_clear_goal": "是",
    "learning_method_preference": "项目驱动学习",
    "learning_pace_preference": "每天少量",
    "content_preference": ["代码实践"],
    "need_guidance": "需要轻量提醒",
    "knowledge_foundation": "有前后端基础",
    "strengths": "动手能力强",
    "weaknesses": "缺少项目经验",
    "experience": "有课程项目经验",
    "short_term_goal": "找工作",
    "long_term_goal": "成为全栈开发者",
    "weekly_available_time": "每周 6-10 小时",
    "constraints": "平时课程多",
}


def _profile(kind: str = "basic_profile") -> dict:
    return {
        "type": kind,
        "stage": "generated" if kind == "basic_profile" else "basic_info",
        "question_mode": "question_box",
        "confirmed_info": CONFIRMED,
        "defaulted_fields": [],
        "question_md": "下一步？",
        "question_box": {"question": "下一步？", "options": []},
        "text": "总结",
        "summary_text": "总结",
    }


@pytest.fixture
def ctx(tmp_path: Path):
    url = postgresql_test_url(tmp_path, "internal-chat")
    app = create_app(database_url=url)
    client = TestClient(app)
    engine = create_engine(url)
    return client, engine


def _new_session(
    engine, session_id: str, messages: list | None = None, **extra
) -> None:
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        session.add(
            ConversationSession(
                session_id=session_id,
                user_uid=DEMO_USER_UID,
                messages=messages or [],
                created_at=now,
                updated_at=now,
                **extra,
            )
        )
        session.commit()


def _human(text_: str) -> dict:
    return {"type": "human", "data": {"content": text_, "additional_kwargs": {}}}


def _ai(text_: str) -> dict:
    return {"type": "ai", "data": {"content": text_, "additional_kwargs": {}}}


def test_internal_chat_endpoints_require_token(ctx) -> None:
    client, _ = ctx
    url = f"/internal/chat/sessions/s1/context?user_uid={DEMO_USER_UID}"
    assert client.get(url).status_code == 401
    assert client.get(url, headers={"X-Internal-Token": "wrong"}).status_code == 403


def test_context_new_session_has_empty_state(ctx) -> None:
    client, engine = ctx
    _new_session(engine, "new-1")
    body = client.get(
        f"/internal/chat/sessions/new-1/context?user_uid={DEMO_USER_UID}",
        headers=INTERNAL,
    ).json()
    assert body["history"] == []
    assert body["session_state"] == {}
    assert body["profile"] is None
    assert body["has_complete_profile"] is False
    with engine.connect() as conn:
        stored = conn.execute(
            text(
                "select session_state from conversationsession where session_id='new-1'"
            )
        ).scalar_one()
    assert stored == {}


def test_context_reads_legacy_intake_and_marker_without_session_state(ctx) -> None:
    """AC-7: a legacy row (empty session_state, intake mixed into messages) restores."""
    client, engine = ctx
    intake = {"type": "learning_path_intake", "draft": {"courses": ["a"]}}
    marker = (
        "要重新生成吗？\n[LEAF_REGEN_PENDING]\ncourse_node_id: c1\n"
        "chapter_section_id: s1\n[/LEAF_REGEN_PENDING]"
    )
    _new_session(
        engine,
        "legacy-1",
        [_human("你好"), _ai("你好呀"), intake, _human("继续"), _ai(marker)],
    )
    body = client.get(
        f"/internal/chat/sessions/legacy-1/context?user_uid={DEMO_USER_UID}",
        headers=INTERNAL,
    ).json()
    assert [m["role"] for m in body["history"]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert all(m["content"] != str(intake) for m in body["history"])
    assert body["session_state"]["learning_path_intake"] == intake


def test_explicit_session_state_wins_over_legacy(ctx) -> None:
    client, engine = ctx
    explicit = {"type": "learning_path_intake", "draft": {"v": "explicit"}}
    old = {"type": "learning_path_intake", "draft": {"v": "legacy"}}
    _new_session(
        engine,
        "mixed-1",
        [_human("hi"), old],
        session_state={"learning_path_intake": explicit},
    )
    body = client.get(
        f"/internal/chat/sessions/mixed-1/context?user_uid={DEMO_USER_UID}",
        headers=INTERNAL,
    ).json()
    assert body["session_state"]["learning_path_intake"] == explicit


def test_context_rejects_foreign_or_missing_session(ctx) -> None:
    client, engine = ctx
    _new_session(engine, "owned-1")
    other = "00000000-0000-0000-0000-000000000099"
    assert (
        client.get(
            f"/internal/chat/sessions/owned-1/context?user_uid={other}",
            headers=INTERNAL,
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/internal/chat/sessions/nope/context?user_uid={DEMO_USER_UID}",
            headers=INTERNAL,
        ).status_code
        == 404
    )


def test_turn_persists_full_then_patches_state(ctx) -> None:
    client, engine = ctx
    _new_session(engine, "turn-1")
    response = client.post(
        "/internal/chat/sessions/turn-1/turn",
        headers=INTERNAL,
        json={
            "user_uid": DEMO_USER_UID,
            "user_message": "我大三",
            "assistant_message": "收到",
            "session_state_patch": {"pending_profile_followup": {"field": "major"}},
        },
    )
    assert response.status_code == 200
    assert response.json()["persisted"] == "full"
    ctx_body = client.get(
        f"/internal/chat/sessions/turn-1/context?user_uid={DEMO_USER_UID}",
        headers=INTERNAL,
    ).json()
    assert ctx_body["history"] == [
        {"role": "user", "content": "我大三"},
        {"role": "assistant", "content": "收到"},
    ]
    assert ctx_body["session_state"]["pending_profile_followup"] == {"field": "major"}

    client.post(
        "/internal/chat/sessions/turn-1/turn",
        headers=INTERNAL,
        json={
            "user_uid": DEMO_USER_UID,
            "user_message": "软件工程",
            "assistant_message": "好",
            "session_state_patch": {"pending_profile_followup": None},
        },
    )
    after = client.get(
        f"/internal/chat/sessions/turn-1/context?user_uid={DEMO_USER_UID}",
        headers=INTERNAL,
    ).json()
    assert "pending_profile_followup" not in after["session_state"]
    assert len(after["history"]) == 4


def test_turn_without_assistant_keeps_user_message(ctx) -> None:
    client, engine = ctx
    _new_session(engine, "turn-2")
    body = client.post(
        "/internal/chat/sessions/turn-2/turn",
        headers=INTERNAL,
        json={"user_uid": DEMO_USER_UID, "user_message": "在吗"},
    ).json()
    assert body["persisted"] == "user_only"
    with engine.connect() as conn:
        messages = conn.execute(
            text("select messages from conversationsession where session_id='turn-2'")
        ).scalar_one()
    assert [m["type"] for m in messages] == ["human"]


def test_turn_on_foreign_session_is_404_and_writes_nothing(ctx) -> None:
    client, engine = ctx
    _new_session(engine, "turn-3")
    response = client.post(
        "/internal/chat/sessions/turn-3/turn",
        headers=INTERNAL,
        json={
            "user_uid": "someone-else",
            "user_message": "x",
            "assistant_message": "y",
        },
    )
    assert response.status_code == 404
    with engine.connect() as conn:
        messages = conn.execute(
            text("select messages from conversationsession where session_id='turn-3'")
        ).scalar_one()
    assert messages == []


def test_put_profile_saves_both_types_and_rejects_others(ctx) -> None:
    client, engine = ctx
    for kind in ("collecting", "basic_profile"):
        response = client.put(
            f"/internal/students/{DEMO_USER_UID}/profile",
            headers=INTERNAL,
            json={"profile_data": _profile(kind)},
        )
        assert response.status_code == 200, response.text
        assert response.json()["type"] == kind
    with engine.connect() as conn:
        saved = conn.execute(
            text("select profile_data from userprofile where user_uid=:u"),
            {"u": DEMO_USER_UID},
        ).scalar_one()
    assert saved["type"] == "basic_profile"
    assert (
        client.put(
            f"/internal/students/{DEMO_USER_UID}/profile",
            headers=INTERNAL,
            json={"profile_data": {"type": "bogus"}},
        ).status_code
        == 422
    )
    assert (
        client.put(
            "/internal/students/ghost/profile",
            headers=INTERNAL,
            json={"profile_data": _profile()},
        ).status_code
        == 404
    )


def test_context_injects_unconsumed_weaknesses(ctx) -> None:
    client, engine = ctx
    _new_session(engine, "weak-1")
    client.put(
        f"/internal/students/{DEMO_USER_UID}/profile",
        headers=INTERNAL,
        json={"profile_data": _profile()},
    )
    # No current course -> nothing injected; the profile is returned verbatim.
    body = client.get(
        f"/internal/chat/sessions/weak-1/context?user_uid={DEMO_USER_UID}",
        headers=INTERNAL,
    ).json()
    assert body["profile"]["confirmed_info"]["weaknesses"] == "缺少项目经验"
    assert body["has_complete_profile"] is True


def test_inject_unconsumed_weaknesses_appends_suffix(ctx) -> None:
    from app.services.chat_context_service import inject_unconsumed_weaknesses

    _, engine = ctx
    with Session(engine) as session:
        session.add(
            ChapterWeakness(
                weakness_id="w1",
                user_uid=DEMO_USER_UID,
                course_node_id="course-1",
                chapter_id="ch1",
                knowledge_point_id="kp1",
                knowledge_point_name="指针",
                consumed=False,
            )
        )
        session.commit()
        profile = inject_unconsumed_weaknesses(
            session, DEMO_USER_UID, {"weaknesses": "原有"}, "course-1"
        )
    assert profile["weaknesses"].startswith("原有\n[Adaptive Weaknesses]")
    assert "指针" in profile["weaknesses"]


def test_learning_overview_empty_account(ctx) -> None:
    client, _ = ctx
    body = client.get(
        f"/internal/students/{DEMO_USER_UID}/learning-overview", headers=INTERNAL
    ).json()
    assert body["has_paths"] is False and body["has_outline"] is False
    assert body["progress"] == []
    assert (
        client.get(
            "/internal/students/ghost/learning-overview", headers=INTERNAL
        ).status_code
        == 404
    )
