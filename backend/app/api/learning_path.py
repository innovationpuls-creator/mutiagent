from __future__ import annotations

from collections.abc import Callable, Generator

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.core.security import create_get_current_user
from app.models import User
from app.schemas import LearningPathReadResponse
from app.services.learning_path_service import get_user_learning_path

SessionDependency = Callable[[], Generator[Session, None, None]]


def create_learning_path_router(session_dependency: SessionDependency) -> APIRouter:
    router = APIRouter(prefix="/api/learning-path", tags=["learning-path"])
    get_current_user = create_get_current_user(session_dependency)

    @router.get("/me", response_model=LearningPathReadResponse)
    def read_my_learning_path(
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> LearningPathReadResponse:
        stored = get_user_learning_path(session, current_user.uid)
        if stored is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="还没有生成学习路径",
            )
        return LearningPathReadResponse(learning_path=stored.path_data, updated_at=stored.updated_at)

    return router
