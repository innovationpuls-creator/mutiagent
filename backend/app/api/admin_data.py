from __future__ import annotations

from collections.abc import Callable, Generator

from fastapi import APIRouter, Depends, Response, status
from sqlmodel import Session

from app.api.admin import require_admin_user
from app.core.security import create_get_current_user
from app.models import User
from app.schemas import CultivationProgramRead, DataCohortRead, DataOverviewResponse, UserLearningDataRead
from app.services.admin_data_service import (
    delete_learning_data_for_user,
    delete_program_for_data_cohort,
    get_data_overview,
    list_data_cohorts,
    list_data_programs,
    read_user_learning_data,
)

SessionDependency = Callable[[], Generator[Session, None, None]]


def create_admin_data_router(session_dependency: SessionDependency) -> APIRouter:
    router = APIRouter(prefix="/api/admin/data", tags=["admin-data"])
    get_current_user = create_get_current_user(session_dependency)

    def require_admin(current_user: User = Depends(get_current_user)) -> User:
        return require_admin_user(current_user)

    @router.get("/overview", response_model=DataOverviewResponse)
    def overview(
        _: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> DataOverviewResponse:
        return get_data_overview(session)

    @router.get("/cohorts", response_model=list[DataCohortRead])
    def cohorts(
        _: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> list[DataCohortRead]:
        return list_data_cohorts(session)

    @router.get("/programs", response_model=list[CultivationProgramRead])
    def programs(
        _: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> list[CultivationProgramRead]:
        return list_data_programs(session)

    @router.get("/users/{uid}/learning-data", response_model=UserLearningDataRead)
    def user_learning_data(
        uid: str,
        _: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> UserLearningDataRead:
        return read_user_learning_data(session, uid)

    @router.delete("/users/{uid}/learning-data", status_code=status.HTTP_204_NO_CONTENT)
    def delete_user_learning_data(
        uid: str,
        _: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> Response:
        delete_learning_data_for_user(session, uid)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.delete("/cohorts/{school}/{major}/{class_name}/program", status_code=status.HTTP_204_NO_CONTENT)
    def delete_cohort_program(
        school: str,
        major: str,
        class_name: str,
        _: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> Response:
        delete_program_for_data_cohort(session, school, major, class_name)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
