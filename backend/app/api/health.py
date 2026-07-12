from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import JSONResponse

from app.schemas import HealthResponse, LivenessResponse


def create_health_router(engine: Engine) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["health"])

    @router.get("/health/live", response_model=LivenessResponse)
    def liveness() -> LivenessResponse:
        return LivenessResponse(status="ok")

    @router.get("/health/ready", response_model=HealthResponse)
    def readiness() -> HealthResponse | JSONResponse:
        return _readiness_response(engine)

    @router.get("/health", response_model=HealthResponse)
    def legacy_health() -> HealthResponse | JSONResponse:
        return _readiness_response(engine)

    return router


def _readiness_response(engine: Engine) -> HealthResponse | JSONResponse:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        body = HealthResponse(status="error", database="unavailable")
        return JSONResponse(status_code=503, content=body.model_dump())
    return HealthResponse(status="ok", database="connected")
