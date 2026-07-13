from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import JSONResponse

from app.migration_state import assert_schema_at_head
from app.schemas import HealthResponse, LivenessResponse


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
