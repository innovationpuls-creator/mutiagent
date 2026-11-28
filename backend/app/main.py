from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.admin import create_admin_router
from app.api.admin_data import create_admin_data_router
from app.api.auth import create_auth_router
from app.api.branch import create_branch_router
from app.api.forest import create_forest_router
from app.api.health import create_health_router
from app.api.internal import create_internal_router
from app.api.knowledge_base import create_knowledge_base_router
from app.api.leaf import create_leaf_router
from app.api.learning_path import create_learning_path_router
from app.api.model_config import create_model_config_router
from app.api.orchestration import create_orchestration_router
from app.api.profile import create_profile_router
from app.api.student import create_student_router
from app.core.config import (
    DEFAULT_INTERNAL_API_TOKEN,
    DEFAULT_JWT_SECRET,
    AppSettings,
    load_settings,
)
from app.core.crypto import (
    SecretDecryptError,
    SecretKeyUnavailableError,
    build_cipher,
)
from app.core.observability import RequestIdMiddleware, configure_json_logging
from app.core.security import configure_jwt
from app.database import (
    DATABASE_URL,
    build_engine,
    create_session_dependency,
    init_db,
    set_engine,
)
from app.migration_state import assert_schema_at_head
from app.services.ai_gateway_client import HttpAiGatewayClient
from app.services.model_config_service import ModelConfigError

logger = logging.getLogger(__name__)

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
    if resolved_settings.is_production:
        assert_schema_at_head(engine)
    else:
        init_db(engine)

    app = FastAPI(title="Mutiagent API", version="0.1.0")
    internal_token = _resolve_internal_token(resolved_settings)
    app.state.model_cipher = build_cipher(
        resolved_settings.model_secret_encryption_key,
        is_production=resolved_settings.is_production,
    )
    app.state.ai_gateway_client = HttpAiGatewayClient(
        resolved_settings.ai_gateway_url, internal_token
    )
    _register_model_config_errors(app)
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
    app.include_router(
        create_auth_router(
            create_session_dependency(engine),
            allow_mock_oauth=not resolved_settings.is_production,
        )
    )
    app.include_router(
        create_health_router(
            engine, check_schema_revision=resolved_settings.is_production
        )
    )
    app.include_router(create_internal_router(engine, internal_token))
    app.include_router(create_model_config_router(create_session_dependency(engine)))
    app.include_router(create_admin_router(create_session_dependency(engine)))
    app.include_router(create_admin_data_router(create_session_dependency(engine)))
    app.include_router(create_student_router(create_session_dependency(engine)))
    app.include_router(create_orchestration_router(create_session_dependency(engine)))
    app.include_router(create_profile_router(create_session_dependency(engine)))
    app.include_router(create_learning_path_router(create_session_dependency(engine)))
    app.include_router(create_branch_router(create_session_dependency(engine)))
    app.include_router(create_leaf_router(create_session_dependency(engine)))
    app.include_router(create_forest_router(create_session_dependency(engine)))
    app.include_router(create_knowledge_base_router(create_session_dependency(engine)))

    return app


def _resolve_internal_token(settings: AppSettings) -> str | None:
    if settings.is_production:
        return settings.internal_api_token
    if settings.internal_api_token:
        return settings.internal_api_token
    logger.warning("INTERNAL_API_TOKEN 未配置，正在使用开发默认内部令牌")
    return DEFAULT_INTERNAL_API_TOKEN


def _register_model_config_errors(app: FastAPI) -> None:
    @app.exception_handler(ModelConfigError)
    async def _model_config_error(_request, exc: ModelConfigError) -> JSONResponse:
        content: dict[str, str] = {"detail": exc.detail}
        if exc.error_code:
            content["error_code"] = exc.error_code
        return JSONResponse(status_code=exc.status_code, content=content)

    @app.exception_handler(SecretKeyUnavailableError)
    async def _secret_key_missing(_request, _exc) -> JSONResponse:
        return JSONResponse(
            status_code=503, content={"detail": "模型凭据加密服务未配置，暂不可用"}
        )

    @app.exception_handler(SecretDecryptError)
    async def _secret_decrypt(_request, exc: SecretDecryptError) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": str(exc)})


_app: FastAPI | None = None


def __getattr__(name: str):
    global _app
    if name == "app":
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(name)
