"""Chat context assembly and turn persistence for the TS orchestration gateway.

The gateway owns orchestration; Python stays the data core. These helpers back the
``/internal/chat/*`` and ``/internal/students/*`` endpoints.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    messages_from_dict,
    messages_to_dict,
)
from sqlmodel import Session, select

from app.orchestration.agents.profile import is_complete_profile_data
from app.orchestration.rule_engine import parse_leaf_regeneration_pending_marker
from app.services.conversation_session_service import (
    append_messages,
    latest_learning_path_intake,
    load_session,
    update_session_state,
)

logger = logging.getLogger(__name__)


class SessionNotFoundError(LookupError):
    """Session missing or owned by someone else (indistinguishable on purpose)."""


def _text_of(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            str(item.get("text", ""))
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        return "\n".join(part for part in parts if part)
    return ""


def history_for_gateway(raw_messages: list[Any]) -> list[dict[str, str]]:
    """Plain role/content history; structured legacy entries are not chat turns."""
    chat_dicts = [
        m
        for m in raw_messages or []
        if not (isinstance(m, dict) and m.get("type") == "learning_path_intake")
    ]
    history: list[dict[str, str]] = []
    for message in messages_from_dict(chat_dicts) if chat_dicts else []:
        if isinstance(message, HumanMessage):
            role = "user"
        elif isinstance(message, AIMessage):
            role = "assistant"
        else:
            continue
        text = _text_of(message.content)
        if text.strip():
            history.append({"role": role, "content": text})
    return history


def _latest_ai_text(raw_messages: list[Any]) -> str:
    chat_dicts = [
        m for m in raw_messages or [] if isinstance(m, dict) and m.get("type") == "ai"
    ]
    for message in reversed(chat_dicts):
        data = message.get("data")
        text = _text_of(data.get("content") if isinstance(data, dict) else "")
        if text.strip():
            return text.strip()
    return ""


def effective_session_state(session_state: dict | None, raw_messages: list) -> dict:
    """Explicit ``session_state`` first; legacy sessions are read through the old
    in-message conventions so both shapes restore without migration of old rows."""
    state: dict[str, Any] = dict(session_state or {})
    if "learning_path_intake" not in state:
        intake = latest_learning_path_intake(raw_messages or [])
        if intake:
            state["learning_path_intake"] = intake
    if "pending_leaf_regeneration" not in state:
        marker = parse_leaf_regeneration_pending_marker(_latest_ai_text(raw_messages))
        if marker is not None:
            state["pending_leaf_regeneration"] = marker
    return state


def inject_unconsumed_weaknesses(
    session: Session, user_uid: str, profile: dict | None, course_id: str
) -> dict | None:
    if not profile or not course_id:
        return profile
    from app.models import ChapterWeakness

    stmt = select(ChapterWeakness).where(
        ChapterWeakness.user_uid == user_uid,
        ChapterWeakness.course_node_id == course_id,
        ChapterWeakness.consumed.is_(False),
    )
    unconsumed = session.exec(stmt).all()
    kp_names = list(
        dict.fromkeys(
            w.knowledge_point_name for w in unconsumed if w.knowledge_point_name
        )
    )
    if not kp_names:
        return profile
    suffix = f"[Adaptive Weaknesses] Recently struggled with: {', '.join(kp_names)}"
    original = profile.get("weaknesses", "")
    profile["weaknesses"] = f"{original}\n{suffix}" if original else suffix
    return profile


def load_owned_session_row(session: Session, session_id: str, user_uid: str):
    row = load_session(session, session_id)
    if row is None or row.user_uid != user_uid:
        raise SessionNotFoundError(session_id)
    return row


def build_chat_context(session: Session, session_id: str, user_uid: str) -> dict:
    from app.services.course_knowledge_service import get_user_course_knowledge_outline
    from app.services.learning_path_service import (
        get_all_year_learning_paths,
        get_current_course_id_from_year_learning_paths,
        get_latest_grade_year,
    )
    from app.services.profile_service import get_user_profile

    row = load_owned_session_row(session, session_id, user_uid)
    raw_messages = list(row.messages or [])
    profile = get_user_profile(session, user_uid)
    year_paths = get_all_year_learning_paths(session, user_uid)
    latest_grade_year = get_latest_grade_year(session, user_uid)
    course_id = get_current_course_id_from_year_learning_paths(
        year_paths, latest_grade_year
    )
    course_knowledge = (
        get_user_course_knowledge_outline(session, user_uid, course_id)
        if course_id
        else None
    )
    profile = inject_unconsumed_weaknesses(session, user_uid, profile, course_id)
    return {
        "session_id": session_id,
        "user_uid": user_uid,
        "history": history_for_gateway(raw_messages),
        "session_state": effective_session_state(row.session_state, raw_messages),
        "profile": profile,
        "has_complete_profile": is_complete_profile_data(profile),
        "year_learning_paths": year_paths or None,
        "latest_grade_year": latest_grade_year or None,
        "course_knowledge": course_knowledge,
    }


def _user_message(text: str, image_attachment: str | None) -> HumanMessage:
    if image_attachment:
        return HumanMessage(
            content=[
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": image_attachment}},
            ]
        )
    return HumanMessage(content=text)


def persist_turn(
    session: Session,
    session_id: str,
    user_uid: str,
    *,
    user_message: str,
    image_attachment: str | None,
    assistant_message: str | None,
    session_state_patch: dict | None,
) -> dict:
    """Atomically append one turn. Full write first; on failure fall back to the
    user message alone so a refresh never loses what the student typed."""
    load_owned_session_row(session, session_id, user_uid)
    human = _user_message(user_message, image_attachment)
    new = [human]
    if assistant_message and assistant_message.strip():
        new.append(AIMessage(content=assistant_message))
    try:
        append_messages(session, session_id, messages_to_dict(new))
        if session_state_patch:
            update_session_state(session, session_id, session_state_patch)
        return {"persisted": "full" if len(new) == 2 else "user_only"}
    except Exception:
        logger.exception(
            "conversation_turn_persistence_failed", extra={"session_id": session_id}
        )
        session.rollback()
        try:
            append_messages(session, session_id, messages_to_dict([human]))
        except Exception:
            logger.exception(
                "conversation_turn_user_fallback_persistence_failed",
                extra={"session_id": session_id},
            )
            raise
        return {"persisted": "user_only"}


def save_student_profile(session: Session, user_uid: str, profile_data: dict) -> dict:
    from app.services.course_knowledge_service import delete_user_course_outlines
    from app.services.profile_service import upsert_user_profile
    from app.services.student_lock import lock_student

    lock_student(session, user_uid)
    upsert_user_profile(session, user_uid, profile_data, commit=False)
    # Same invariant as the legacy persist: any profile rewrite invalidates outlines.
    if profile_data.get("type") in {"basic_profile", "collecting"}:
        delete_user_course_outlines(session, user_uid, commit=False)
    session.commit()
    return {"saved": True, "type": profile_data.get("type")}


def _course_titles(path: dict, grade_year: str) -> dict[str, str]:
    from app.api.orchestration import _course_nodes_from_path, _course_title

    return {
        str(
            course.get("course_node_id") or course.get("course_id") or ""
        ): _course_title(course)
        for course in _course_nodes_from_path(grade_year, path)
    }


def build_learning_overview(session: Session, user_uid: str) -> dict:
    from app.api.orchestration import (
        _format_course_next_step_text,
        _format_course_outline_text,
        _format_learning_path_text,
    )
    from app.services.course_knowledge_service import get_user_course_knowledge_outline
    from app.services.learning_path_service import (
        get_all_year_learning_paths,
        get_current_course_id_from_year_learning_paths,
        get_latest_grade_year,
        get_learning_path_progress_snapshots,
    )

    year_paths = get_all_year_learning_paths(session, user_uid)
    latest_grade_year = get_latest_grade_year(session, user_uid)
    course_id = get_current_course_id_from_year_learning_paths(
        year_paths, latest_grade_year
    )
    course_knowledge = (
        get_user_course_knowledge_outline(session, user_uid, course_id)
        if course_id
        else None
    )
    progress = []
    for snapshot in get_learning_path_progress_snapshots(year_paths):
        grade_year = str(snapshot.get("grade_year", ""))
        titles = _course_titles(year_paths.get(grade_year, {}), grade_year)
        progress.append(
            {
                **snapshot,
                "current_course_title": titles.get(
                    str(snapshot.get("current_course_id", "")), ""
                ),
                "next_course_title": titles.get(
                    str(snapshot.get("next_course_id", "")), ""
                ),
            }
        )
    return {
        "has_paths": bool(year_paths),
        "has_outline": bool(course_knowledge),
        "latest_grade_year": latest_grade_year or None,
        "current_course_id": course_id or None,
        "progress": progress,
        "path_text": _format_learning_path_text(year_paths, latest_grade_year or "")
        if year_paths
        else "",
        "outline_text": _format_course_outline_text(course_knowledge)
        if course_knowledge
        else "",
        "next_step_text": _format_course_next_step_text(course_knowledge)
        if course_knowledge
        else "",
    }
