from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import create_auth_router
from app.api.branch import create_branch_router
from app.api.learning_path import create_learning_path_router
from app.api.orchestration import create_orchestration_router
from app.api.profile import create_profile_router
from app.database import DATABASE_URL, build_engine, create_session_dependency, init_db, set_engine
from app.schemas import HealthResponse


def create_app(database_url: str = DATABASE_URL) -> FastAPI:
    engine = build_engine(database_url)
    set_engine(engine)
    init_db(engine)

    app = FastAPI(title="Mutiagent API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_origin_regex=r"http://(127\.0\.0\.1|localhost):517\d",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(create_auth_router(create_session_dependency(engine)))
    app.include_router(create_orchestration_router(create_session_dependency(engine)))
    app.include_router(create_profile_router(create_session_dependency(engine)))
    app.include_router(create_learning_path_router(create_session_dependency(engine)))
    app.include_router(create_branch_router(create_session_dependency(engine)))

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
