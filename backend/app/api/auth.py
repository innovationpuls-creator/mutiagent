from __future__ import annotations

from collections.abc import Callable, Generator

from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from app.core.security import create_get_current_user
from app.models import User
from app.schemas import (
    AuthResponse,
    LoginRequest,
    OAuthRequest,
    RegisterRequest,
    UserRead,
)
from app.services.auth_service import (
    login_user,
    login_with_oauth,
    register_user,
    to_user_read,
)

SessionDependency = Callable[[], Generator[Session, None, None]]


def create_auth_router(session_dependency: SessionDependency) -> APIRouter:
    router = APIRouter(prefix="/api/auth", tags=["auth"])
    get_current_user = create_get_current_user(session_dependency)

    @router.post(
        "/register",
        response_model=AuthResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def register(
        payload: RegisterRequest, session: Session = Depends(session_dependency)
    ) -> AuthResponse:
        return register_user(session, payload)

    @router.post("/login", response_model=AuthResponse)
    def login(
        payload: LoginRequest, session: Session = Depends(session_dependency)
    ) -> AuthResponse:
        return login_user(session, payload)

    @router.post("/oauth/mock", response_model=AuthResponse)
    def oauth(
        payload: OAuthRequest, session: Session = Depends(session_dependency)
    ) -> AuthResponse:
        return login_with_oauth(session, payload)

    @router.get("/me", response_model=UserRead)
    def me(current_user: User = Depends(get_current_user)) -> UserRead:
        return to_user_read(current_user)

    return router
