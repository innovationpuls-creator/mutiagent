from __future__ import annotations

import uuid
from collections.abc import Callable, Generator

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.core.security import create_get_current_user
from app.models import User
from app.schemas import (
    ChatResponse,
    ChatStartRequest,
    SessionStateResponse,
)

SessionDependency = Callable[[], Generator[Session, None, None]]


def create_orchestration_router(session_dependency: SessionDependency) -> APIRouter:
    router = APIRouter(prefix="/api/chat", tags=["chat"])
    get_current_user = create_get_current_user(session_dependency)

    @router.post("/start", response_model=ChatResponse)
    def start_chat(
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

    @router.get("/sessions/{session_id}", response_model=SessionStateResponse)
    def get_session_state(
        session_id: str,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> SessionStateResponse:
        """Get the current state of a chat session."""
        from app.services.conversation_session_service import load_session as load_conv
        from app.services.course_knowledge_service import (
            get_user_course_knowledge_outline,
        )
        from app.services.learning_path_service import (
            get_all_year_learning_paths,
            get_current_course_id_from_year_learning_paths,
            get_latest_grade_year,
        )
        from app.services.profile_service import get_user_profile

        conv = load_conv(session, session_id)
        if conv is None or conv.user_uid != current_user.uid:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在"
            )

        profile = get_user_profile(session, current_user.uid)
        year_paths = get_all_year_learning_paths(session, current_user.uid)
        latest_grade_year = get_latest_grade_year(session, current_user.uid)
        current_course_id = get_current_course_id_from_year_learning_paths(
            year_paths,
            latest_grade_year,
        )
        course_knowledge = (
            get_user_course_knowledge_outline(
                session, current_user.uid, current_course_id
            )
            if current_course_id
            else None
        )

        return SessionStateResponse(
            session_id=session_id,
            user_uid=current_user.uid,
            messages=conv.messages or [],
            profile=profile,
            year_learning_paths=year_paths,
            latest_grade_year=latest_grade_year or None,
            course_knowledge=course_knowledge,
            updated_at=conv.updated_at,
        )

    return router
