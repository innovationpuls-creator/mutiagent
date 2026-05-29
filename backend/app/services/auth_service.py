from __future__ import annotations

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.core.security import create_mock_token, hash_password, verify_password
from app.models import User
from app.schemas import AuthResponse, AuthType, LoginRequest, OAuthRequest, RegisterRequest, UserRead


def to_user_read(user: User) -> UserRead:
    if user.id is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return UserRead(
        id=user.id,
        username=user.username,
        identifier=user.identifier,
        provider=user.provider,
    )


def find_user(session: Session, identifier: str) -> User | None:
    return session.exec(select(User).where(User.identifier == identifier)).first()


def create_auth_response(user: User, auth_type: AuthType) -> AuthResponse:
    return AuthResponse(
        token=create_mock_token(),
        auth_type=auth_type,
        user=to_user_read(user),
    )


def register_user(session: Session, payload: RegisterRequest) -> AuthResponse:
    if find_user(session, payload.identifier):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="账号已存在",
        )

    user = User(
        username=payload.username,
        identifier=payload.identifier,
        provider="password",
        password_hash=hash_password(payload.password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return create_auth_response(user, "password")


def login_user(session: Session, payload: LoginRequest) -> AuthResponse:
    user = find_user(session, payload.account)
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号或密码不正确",
        )

    return create_auth_response(user, "password")


def login_with_oauth(session: Session, payload: OAuthRequest) -> AuthResponse:
    identifier = f"{payload.provider}-learner@mock.local"
    user = find_user(session, identifier)
    if user:
        return create_auth_response(user, "oauth")

    user = User(
        username="学习伙伴" if payload.provider == "xuexitong" else "QQ 同学",
        identifier=identifier,
        provider=payload.provider,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return create_auth_response(user, "oauth")
