from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator, Callable, Generator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from sqlmodel import Session

from app.core.security import create_get_current_user
from app.models import User, UserProfile
from app.orchestration.graph import build_orchestration_graph, stream_orchestration_events
from app.schemas import (
    ChatMessageRequest,
    ChatResponse,
    ChatStartRequest,
    SessionStateResponse,
)

SessionDependency = Callable[[], Generator[Session, None, None]]


def _completed_user_profile(session: Session, user_uid: str) -> dict | None:
    profile = session.get(UserProfile, user_uid)
    if profile is None:
        return None
    if profile.profile_data.get("type") != "basic_profile":
        return profile.profile_data if profile.profile_data else None
    return profile.profile_data


def _sse(event: str, payload: dict) -> str:
    """Format an SSE event with fine-grained event types."""
    if event == "message":
        payload["type"] = payload.get("type", event)
        return f"event: message\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _stream_chat_events(
    session_id: str,
    user_uid: str,
    user_message: str,
    db_session: Session,
) -> AsyncGenerator[str, None]:
    """SSE generator: load context from DB, run graph, stream events."""
    from app.services.profile_service import get_user_profile
    from app.services.learning_path_service import get_all_year_learning_paths
    from app.services.conversation_session_service import load_or_create_session

    # Load context from DB
    conv_session = load_or_create_session(db_session, session_id, user_uid)
    profile = get_user_profile(db_session, user_uid)
    year_paths = get_all_year_learning_paths(db_session, user_uid)

    # Build state
    state = {
        "user_id": user_uid,
        "session_id": session_id,
        "query": user_message,
        "messages": [HumanMessage(content=user_message)],
    }

    if profile:
        state["profile"] = profile
    if year_paths:
        state["year_learning_paths"] = year_paths

    try:
        async for event in stream_orchestration_events(state):
            event_name = str(event.get("event", "message"))
            # For 'message' events, use the generic onmessage handler
            if event_name in {"text_chunk", "supervisor_thinking", "supervisor_plan"}:
                payload = {k: v for k, v in event.items() if k != "event"}
                yield _sse("message", {**payload, "type": event_name})
            else:
                payload = {k: v for k, v in event.items() if k != "event"}
                yield _sse(event_name, payload)
    except Exception as exc:
        yield _sse("error", {
            "message": str(exc) or "对话请求失败，请稍后重试。",
            "recoverable": True,
        })


def create_orchestration_router(session_dependency: SessionDependency) -> APIRouter:
    router = APIRouter(prefix="/api/chat", tags=["chat"])
    get_current_user = create_get_current_user(session_dependency)

    @router.post("/start", response_model=ChatResponse)
    async def start_chat(
        payload: ChatStartRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> ChatResponse:
        """Start a new chat session."""
        session_id = str(uuid.uuid4())

        from app.services.conversation_session_service import load_or_create_session
        load_or_create_session(session, session_id, current_user.uid)

        return ChatResponse(
            session_id=session_id,
            reply_text="你好！我是你的学习助手。请告诉我你的基本情况，比如年级、专业、想学什么？",
        )

    @router.post("/message")
    async def send_message(
        payload: ChatMessageRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> StreamingResponse:
        """Send a message and receive SSE-streamed agent responses."""
        return StreamingResponse(
            _stream_chat_events(
                session_id=payload.session_id,
                user_uid=current_user.uid,
                user_message=payload.message,
                db_session=session,
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.get("/sessions/{session_id}", response_model=SessionStateResponse)
    async def get_session_state(
        session_id: str,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> SessionStateResponse:
        """Get the current state of a chat session."""
        from app.services.conversation_session_service import load_session as load_conv
        from app.services.profile_service import get_user_profile
        from app.services.learning_path_service import get_all_year_learning_paths

        conv = load_conv(session, session_id)
        if conv is None or conv.user_uid != current_user.uid:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

        profile = get_user_profile(session, current_user.uid)
        year_paths = get_all_year_learning_paths(session, current_user.uid)

        return SessionStateResponse(
            session_id=session_id,
            user_uid=current_user.uid,
            profile=profile,
            year_learning_paths=year_paths,
            updated_at=conv.updated_at,
        )

    return router
