from __future__ import annotations

from collections.abc import Callable, Generator

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.security import create_get_current_user
from app.models import User
from app.schemas import CultivationProgramRead
from app.services.cultivation_program_service import get_matched_program_for_student

SessionDependency = Callable[[], Generator[Session, None, None]]


def create_student_router(session_dependency: SessionDependency) -> APIRouter:
    router = APIRouter(prefix="/api/student", tags=["student"])
    get_current_user = create_get_current_user(session_dependency)

    @router.get("/matched-program", response_model=CultivationProgramRead | None)
    def matched_program(
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> CultivationProgramRead | None:
        return get_matched_program_for_student(session, current_user)

    return router
