from __future__ import annotations

from collections.abc import Callable, Generator

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.security import create_get_current_user
from app.models import User
from app.schemas import LeafCourseReadResponse
from app.services.leaf_service import read_leaf_course

SessionDependency = Callable[[], Generator[Session, None, None]]


def create_leaf_router(session_dependency: SessionDependency) -> APIRouter:
    router = APIRouter(prefix="/api/leaf", tags=["leaf"])
    get_current_user = create_get_current_user(session_dependency)

    @router.get("/courses/{course_node_id}", response_model=LeafCourseReadResponse)
    def get_leaf_course(
        course_node_id: str,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> LeafCourseReadResponse:
        return read_leaf_course(session, current_user.uid, course_node_id)

    return router
