from __future__ import annotations

from collections.abc import Callable, Generator

from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from app.schemas import AuthResponse, LoginRequest, OAuthRequest, RegisterRequest
from app.services.auth_service import login_user, login_with_oauth, register_user


SessionDependency = Callable[[], Generator[Session]]


def create_auth_router(session_dependency: SessionDependency) -> APIRouter:
    router = APIRouter(prefix="/api/auth", tags=["auth"])

    @router.post(
        "/register",
        response_model=AuthResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def register(payload: RegisterRequest, session: Session = Depends(session_dependency)) -> AuthResponse:
        return register_user(session, payload)

    @router.post("/login", response_model=AuthResponse)
    def login(payload: LoginRequest, session: Session = Depends(session_dependency)) -> AuthResponse:
        return login_user(session, payload)

    @router.post("/oauth/mock", response_model=AuthResponse)
    def oauth(payload: OAuthRequest, session: Session = Depends(session_dependency)) -> AuthResponse:
        return login_with_oauth(session, payload)

    return router
