from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select
from starlette.responses import JSONResponse

from app.model_config_schemas import (
    OAuthCredentialPayload,
    OAuthRefreshPayload,
    UsageRecordPayload,
)
from app.models import User
from app.services import model_config_service as model_service

INTERNAL_TOKEN_HEADER = "X-Internal-Token"


def create_internal_router(engine: Engine, internal_token: str | None) -> APIRouter:  # noqa: C901
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

    @router.get("/users/{user_uid}/model-runtime-config")
    def model_runtime_config(user_uid: str, request: Request) -> JSONResponse:
        with Session(engine) as session:
            user = session.exec(select(User).where(User.uid == user_uid)).first()
            if user is None:
                raise HTTPException(status_code=404, detail="用户不存在")
            config = model_service.runtime_config(
                session, user_uid, request.app.state.model_cipher
            )
        return JSONResponse(content=jsonable_encoder(config))

    @router.post("/users/{user_uid}/providers/{provider_id}/oauth-refresh-lock")
    def oauth_refresh_lock(
        user_uid: str,
        provider_id: str,
        payload: OAuthRefreshPayload,
        request: Request,
    ) -> JSONResponse:
        with Session(engine) as session:
            result = model_service.oauth_refresh_lock(
                session,
                user_uid,
                provider_id,
                payload.previous_refresh_fingerprint,
                payload.new_credential,
                payload.expires_at,
                request.app.state.model_cipher,
            )
        return JSONResponse(content=jsonable_encoder(result))

    @router.put("/users/{user_uid}/providers/{provider_id}/oauth-credential")
    def save_oauth_credential(
        user_uid: str,
        provider_id: str,
        payload: OAuthCredentialPayload,
        request: Request,
    ) -> dict[str, bool]:
        with Session(engine) as session:
            if session.exec(select(User).where(User.uid == user_uid)).first() is None:
                raise HTTPException(status_code=404, detail="用户不存在")
            model_service.save_oauth_credential(
                session,
                user_uid,
                provider_id,
                payload.credential,
                payload.expires_at,
                payload.account_label,
                request.app.state.model_cipher,
            )
        request.app.state.ai_gateway_client.invalidate_user_model_config(user_uid)
        return {"ok": True}

    @router.post("/users/{user_uid}/model-usage")
    def model_usage(user_uid: str, payload: UsageRecordPayload) -> dict[str, str]:
        with Session(engine) as session:
            if session.exec(select(User).where(User.uid == user_uid)).first() is None:
                raise HTTPException(status_code=404, detail="用户不存在")
            row = model_service.record_usage(session, user_uid, payload)
            return {"usage_id": row.usage_id}

    return router
