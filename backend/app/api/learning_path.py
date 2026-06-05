from __future__ import annotations

from collections.abc import Callable, Generator

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.core.security import create_get_current_user
from app.models import User, UserYearLearningPath
from app.schemas import YearLearningPathsReadResponse
from app.services.learning_path_service import get_all_year_learning_paths

SessionDependency = Callable[[], Generator[Session, None, None]]


def create_learning_path_router(session_dependency: SessionDependency) -> APIRouter:
    router = APIRouter(prefix="/api/learning-path", tags=["learning-path"])
    get_current_user = create_get_current_user(session_dependency)

    @router.get("/me", response_model=YearLearningPathsReadResponse)
    def read_my_learning_path(
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> YearLearningPathsReadResponse:
        paths = get_all_year_learning_paths(session, current_user.uid)
        if not paths:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="还没有生成学习路径",
            )
        latest = session.exec(
            select(UserYearLearningPath)
            .where(UserYearLearningPath.user_uid == current_user.uid)
            .order_by(UserYearLearningPath.updated_at.desc())
        ).first()
        return YearLearningPathsReadResponse(
            year_learning_paths=paths,
            updated_at=latest.updated_at if latest else None,
        )

    return router
