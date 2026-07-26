from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session
from starlette.responses import JSONResponse

from app.migration_state import assert_schema_at_head
from app.models import WorkerHeartbeat
from app.schemas import HealthResponse, LivenessResponse
from app.services.worker_health_service import (
    WORKER_HEARTBEAT_NAME,
    is_worker_heartbeat_fresh,
)


def create_health_router(
    engine: Engine, *, check_schema_revision: bool = False
) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["health"])

    @router.get("/health/live", response_model=LivenessResponse)
    def liveness() -> LivenessResponse:
        return LivenessResponse(status="ok")

    @router.get("/health/ready", response_model=HealthResponse)
    def readiness() -> HealthResponse | JSONResponse:
        return _readiness_response(engine, check_schema_revision=check_schema_revision)

    @router.get("/health", response_model=HealthResponse)
    def legacy_health() -> HealthResponse | JSONResponse:
        return _readiness_response(engine, check_schema_revision=check_schema_revision)

    @router.get("/health/deep")
    def deep_readiness() -> JSONResponse:
        return _deep_readiness_response(
            engine, check_schema_revision=check_schema_revision
        )

    return router


def _readiness_response(
    engine: Engine, *, check_schema_revision: bool
) -> HealthResponse | JSONResponse:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        if check_schema_revision:
            assert_schema_at_head(engine)
    except (RuntimeError, SQLAlchemyError):
        body = HealthResponse(status="error", database="unavailable")
        return JSONResponse(status_code=503, content=body.model_dump())
    return HealthResponse(status="ok", database="connected")


def _deep_readiness_response(
    engine: Engine, *, check_schema_revision: bool
) -> JSONResponse:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        if check_schema_revision:
            assert_schema_at_head(engine)
        with Session(engine) as session:
            heartbeat = session.get(WorkerHeartbeat, WORKER_HEARTBEAT_NAME)
    except (RuntimeError, SQLAlchemyError):
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "database": "unavailable",
                "knowledge_base_worker": "unavailable",
            },
        )

    if not is_worker_heartbeat_fresh(heartbeat, datetime.now(timezone.utc)):
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "database": "connected",
                "knowledge_base_worker": "unavailable",
            },
        )
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "database": "connected",
            "knowledge_base_worker": "connected",
        },
    )
