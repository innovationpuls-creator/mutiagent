from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import create_auth_router
from app.database import DEFAULT_DATABASE_URL, build_engine, create_session_dependency, init_db
from app.schemas import HealthResponse


def create_app(database_url: str = DEFAULT_DATABASE_URL) -> FastAPI:
    engine = build_engine(database_url)
    init_db(engine)

    app = FastAPI(title="Mutiagent API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(create_auth_router(create_session_dependency(engine)))

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", database="connected")

    return app


app = create_app()
