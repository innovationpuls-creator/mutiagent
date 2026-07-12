from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin import create_admin_router
from app.api.admin_data import create_admin_data_router
from app.api.auth import create_auth_router
from app.api.branch import create_branch_router
from app.api.forest import create_forest_router
from app.api.knowledge_base import create_knowledge_base_router
from app.api.leaf import create_leaf_router
from app.api.learning_path import create_learning_path_router
from app.api.orchestration import create_orchestration_router
from app.api.profile import create_profile_router
from app.api.student import create_student_router
from app.api.teacher import create_teacher_router
from app.core.config import DEFAULT_JWT_SECRET, AppSettings, load_settings
from app.core.observability import RequestIdMiddleware, configure_json_logging
from app.core.security import configure_jwt
from app.database import (
    DATABASE_URL,
    build_engine,
    create_session_dependency,
    init_db,
    set_engine,
)
from app.schemas import HealthResponse

DEVELOPMENT_ORIGINS = ["http://127.0.0.1:5173", "http://localhost:5173"]


def create_app(
    database_url: str | None = None, settings: AppSettings | None = None
) -> FastAPI:
    resolved_settings = settings or load_settings()
    configure_jwt(resolved_settings.jwt_secret or DEFAULT_JWT_SECRET)
    configure_json_logging("mutiagent-backend")
    resolved_database_url = (
        database_url or resolved_settings.database_url or DATABASE_URL
    )
    engine = build_engine(resolved_database_url)
    set_engine(engine)
    init_db(engine, seed_users=not resolved_settings.is_production)

    app = FastAPI(title="Mutiagent API", version="0.1.0")
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(
            resolved_settings.allowed_origins
            if resolved_settings.is_production
            else DEVELOPMENT_ORIGINS
        ),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(create_auth_router(create_session_dependency(engine)))
    app.include_router(create_admin_router(create_session_dependency(engine)))
    app.include_router(create_admin_data_router(create_session_dependency(engine)))
    app.include_router(create_teacher_router(create_session_dependency(engine)))
    app.include_router(create_student_router(create_session_dependency(engine)))
    app.include_router(create_orchestration_router(create_session_dependency(engine)))
    app.include_router(create_profile_router(create_session_dependency(engine)))
    app.include_router(create_learning_path_router(create_session_dependency(engine)))
    app.include_router(create_branch_router(create_session_dependency(engine)))
    app.include_router(create_leaf_router(create_session_dependency(engine)))
    app.include_router(create_forest_router(create_session_dependency(engine)))
    app.include_router(create_knowledge_base_router(create_session_dependency(engine)))

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", database="connected")

    return app


_app: FastAPI | None = None


def __getattr__(name: str):
    global _app
    if name == "app":
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(name)
