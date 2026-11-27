from __future__ import annotations

from collections.abc import Callable, Generator

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session

from app.core.security import create_get_current_user
from app.models import User
from app.schemas import (
    AdminAccountBatchRequest,
    AdminAccountCreateRequest,
    AdminAccountImportRequest,
    AdminAccountImportResponse,
    AdminAccountUpdateRequest,
    CultivationProgramRead,
    CultivationProgramSaveRequest,
    UserRead,
)
from app.services.admin_account_service import (
    batch_accounts,
    create_account,
    delete_account,
    export_accounts,
    import_accounts,
    list_accounts,
    update_account,
)
from app.services.cultivation_program_service import (
    get_program_for_admin,
    publish_program_for_admin,
    save_program_for_admin,
)

SessionDependency = Callable[[], Generator[Session, None, None]]


def require_admin_user(current_user: User) -> User:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return current_user


def _register_program_routes(
    router: APIRouter,
    require_admin: Callable[..., User],
    session_dependency: SessionDependency,
) -> None:
    @router.get("/program", response_model=CultivationProgramRead | None)
    def read_program(
        current_user: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> CultivationProgramRead | None:
        return get_program_for_admin(session, current_user)

    @router.put("/program", response_model=CultivationProgramRead)
    def save_program(
        payload: CultivationProgramSaveRequest,
        current_user: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> CultivationProgramRead:
        return save_program_for_admin(
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
        current_user: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> CultivationProgramRead:
        return publish_program_for_admin(
            session,
            current_user,
            payload.courses,
            payload.school,
            payload.major,
            payload.class_name,
        )


def create_admin_router(session_dependency: SessionDependency) -> APIRouter:
    router = APIRouter(prefix="/api/admin", tags=["admin"])
    get_current_user = create_get_current_user(session_dependency)

    def require_admin(current_user: User = Depends(get_current_user)) -> User:
        return require_admin_user(current_user)

    @router.get("/accounts", response_model=list[UserRead])
    def accounts(
        _: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> list[UserRead]:
        return list_accounts(session)

    @router.post(
        "/accounts", response_model=UserRead, status_code=status.HTTP_201_CREATED
    )
    def create(
        payload: AdminAccountCreateRequest,
        _: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> UserRead:
        return create_account(session, payload)

    @router.post("/accounts/batch", response_model=list[UserRead])
    def batch(
        payload: AdminAccountBatchRequest,
        current_user: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> list[UserRead]:
        return batch_accounts(session, payload, current_user)

    @router.post("/accounts/import", response_model=AdminAccountImportResponse)
    def import_csv(
        payload: AdminAccountImportRequest,
        current_user: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> AdminAccountImportResponse:
        return import_accounts(session, payload.csv_text, current_user)

    @router.get("/accounts/export")
    def export_csv(
        _: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> Response:
        return Response(
            content=export_accounts(session),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="accounts.csv"'},
        )

    @router.put("/accounts/{uid}", response_model=UserRead)
    def update(
        uid: str,
        payload: AdminAccountUpdateRequest,
        current_user: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> UserRead:
        return update_account(session, uid, payload, current_user)

    @router.delete("/accounts/{uid}", status_code=status.HTTP_204_NO_CONTENT)
    def delete(
        uid: str,
        current_user: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> Response:
        delete_account(session, uid, current_user)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    _register_program_routes(router, require_admin, session_dependency)
    return router
