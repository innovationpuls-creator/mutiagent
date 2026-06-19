from __future__ import annotations

from collections.abc import Callable, Generator

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.security import create_get_current_user
from app.models import User
from app.schemas import CultivationProgramRead, CultivationProgramSaveRequest
from app.services.cultivation_program_service import (
    get_program_for_teacher,
    publish_program_for_teacher,
    save_program_for_teacher,
)

SessionDependency = Callable[[], Generator[Session, None, None]]


def create_teacher_router(session_dependency: SessionDependency) -> APIRouter:
    router = APIRouter(prefix="/api/teacher", tags=["teacher"])
    get_current_user = create_get_current_user(session_dependency)

    @router.get("/program", response_model=CultivationProgramRead | None)
    def read_program(
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> CultivationProgramRead | None:
        return get_program_for_teacher(session, current_user)

    @router.put("/program", response_model=CultivationProgramRead)
    def save_program(
        payload: CultivationProgramSaveRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> CultivationProgramRead:
        return save_program_for_teacher(
            session,
            current_user,
            payload.courses,
            payload.school,
            payload.major,
            payload.class_name,
        )

    @router.post("/program/publish", response_model=CultivationProgramRead)
    def publish_program(
        payload: CultivationProgramSaveRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> CultivationProgramRead:
        return publish_program_for_teacher(
            session,
            current_user,
            payload.courses,
            payload.school,
            payload.major,
            payload.class_name,
        )

    return router
