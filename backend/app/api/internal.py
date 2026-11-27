from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select
from starlette.responses import JSONResponse

from app.models import User

INTERNAL_TOKEN_HEADER = "X-Internal-Token"


def create_internal_router(engine: Engine, internal_token: str | None) -> APIRouter:
    def verify_internal_token(
        provided: str | None = Header(default=None, alias=INTERNAL_TOKEN_HEADER),
    ) -> None:
        if provided is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少内部令牌"
            )
        if not internal_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="内部接口未启用"
            )
        if not hmac.compare_digest(
            provided.encode("utf-8"), internal_token.encode("utf-8")
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="内部令牌无效"
            )

    router = APIRouter(
        prefix="/internal",
        dependencies=[Depends(verify_internal_token)],
        include_in_schema=False,
    )

    @router.get("/health")
    def internal_health() -> JSONResponse:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            return JSONResponse(
                status_code=503,
                content={"status": "error", "database": "unavailable"},
            )
        return JSONResponse(content={"status": "ok", "database": "connected"})

    @router.get("/users/{user_uid}/auth-status")
    def user_auth_status(user_uid: str) -> dict[str, str | bool | None]:
        with Session(engine) as session:
            user = session.exec(select(User).where(User.uid == user_uid)).first()
            if user is None:
                return {
                    "user_uid": user_uid,
                    "exists": False,
                    "role": None,
                    "is_active": False,
                }
            return {
                "user_uid": user.uid,
                "exists": True,
                "role": user.role,
                "is_active": user.is_active,
            }

    return router
