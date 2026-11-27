from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

DEFAULT_LLM_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_JWT_SECRET = "mutiagent-dev-secret-key-change-in-production"
DEFAULT_INTERNAL_API_TOKEN = "mutiagent-dev-internal-token-change-in-production"
DEFAULT_AI_GATEWAY_URL = "http://127.0.0.1:8100"
PRODUCTION_ENVIRONMENT = "production"


@dataclass(frozen=True)
class AppSettings:
    app_env: str
    database_url: str | None
    jwt_secret: str | None
    llm_base_url: str
    llm_api_key: str | None
    llm_model: str | None
    allowed_origins: tuple[str, ...]
    internal_api_token: str | None = None
    model_secret_encryption_key: str | None = None
    ai_gateway_url: str = DEFAULT_AI_GATEWAY_URL
    ai_gateway_url_configured: bool = False

    @property
    def is_production(self) -> bool:
        return self.app_env == PRODUCTION_ENVIRONMENT


def load_settings(environ: Mapping[str, str] | None = None) -> AppSettings:
    values = os.environ if environ is None else environ
    app_env = values.get("APP_ENV", "development").strip().lower()
    database_url = _optional_value(values, "DATABASE_URL")
    jwt_secret = _optional_value(values, "JWT_SECRET")
    llm_api_key = _optional_value(values, "LLM_API_KEY")
    llm_model = _optional_value(values, "LLM_MODEL")
    allowed_origins = _parse_allowed_origins(values.get("ALLOWED_ORIGINS", ""))
    settings = AppSettings(
        app_env=app_env,
        database_url=database_url,
        jwt_secret=jwt_secret,
        llm_base_url=values.get("LLM_BASE_URL", DEFAULT_LLM_BASE_URL).strip()
        or DEFAULT_LLM_BASE_URL,
        llm_api_key=llm_api_key,
        llm_model=llm_model,
        allowed_origins=allowed_origins,
        internal_api_token=_optional_value(values, "INTERNAL_API_TOKEN"),
        model_secret_encryption_key=_optional_value(
            values, "MODEL_SECRET_ENCRYPTION_KEY"
        ),
        ai_gateway_url=(
            _optional_value(values, "AI_GATEWAY_URL") or DEFAULT_AI_GATEWAY_URL
        ).rstrip("/"),
        ai_gateway_url_configured=bool(_optional_value(values, "AI_GATEWAY_URL")),
    )
    if settings.is_production:
        _validate_production_settings(settings)
    return settings


def _optional_value(values: Mapping[str, str], key: str) -> str | None:
    value = values.get(key, "").strip()
    return value or None


def _parse_allowed_origins(raw_value: str) -> tuple[str, ...]:
    return tuple(origin.strip() for origin in raw_value.split(",") if origin.strip())


def _validate_production_settings(settings: AppSettings) -> None:
    # Model credentials are per-user now (stored encrypted and used by the AI
    # gateway); LLM_API_KEY / LLM_MODEL only feed the optional platform video
    # search and are no longer required.
    required_values = {
        "DATABASE_URL": settings.database_url,
        "JWT_SECRET": settings.jwt_secret,
        "ALLOWED_ORIGINS": settings.allowed_origins,
        "INTERNAL_API_TOKEN": settings.internal_api_token,
        "AI_GATEWAY_URL": settings.ai_gateway_url_configured,
        "MODEL_SECRET_ENCRYPTION_KEY": settings.model_secret_encryption_key,
    }
    for key, value in required_values.items():
        if not value:
            raise ValueError(f"生产环境缺少 {key}")
    if settings.jwt_secret == DEFAULT_JWT_SECRET:
        raise ValueError("生产环境不能使用默认 JWT_SECRET")
    if settings.internal_api_token == DEFAULT_INTERNAL_API_TOKEN:
        raise ValueError("生产环境不能使用默认 INTERNAL_API_TOKEN")
