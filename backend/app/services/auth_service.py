from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas import AuthResponse, AuthType, LoginRequest, OAuthRequest, RegisterRequest, UserRead


def to_user_read(user: User) -> UserRead:
    return UserRead(
        uid=user.uid,
        username=user.username,
        identifier=user.identifier,
        role=user.role,
        provider=user.provider,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


def find_user(session: Session, identifier: str) -> User | None:
    return session.exec(select(User).where(User.identifier == identifier)).first()


def create_auth_response(user: User, auth_type: AuthType) -> AuthResponse:
    token = create_access_token(data={"sub": user.uid})
    return AuthResponse(
        access_token=token,
        token_type="bearer",
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
        uid=str(uuid4()),
        username=payload.username,
        identifier=payload.identifier,
        role=payload.role,
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

    user.last_login_at = datetime.now(timezone.utc)
    session.add(user)
    session.commit()
    session.refresh(user)
    return create_auth_response(user, "password")


def login_with_oauth(session: Session, payload: OAuthRequest) -> AuthResponse:
    identifier = f"{payload.provider}-learner@mock.local"
    user = find_user(session, identifier)
    if user:
        user.last_login_at = datetime.now(timezone.utc)
        session.add(user)
        session.commit()
        session.refresh(user)
        return create_auth_response(user, "oauth")

    user = User(
        uid=str(uuid4()),
        username="学习伙伴" if payload.provider == "xuexitong" else "QQ 同学",
        identifier=identifier,
        role="student",
        provider=payload.provider,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return create_auth_response(user, "oauth")
