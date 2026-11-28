from __future__ import annotations

from collections.abc import Mapping

import pytest

from app.core import security
from app.core.config import load_settings


def valid_production_environ() -> dict[str, str]:
    return {
        "APP_ENV": "production",
        "DATABASE_URL": "postgresql://user:password@localhost:5432/mutiagent",
        "JWT_SECRET": "test-production-jwt-secret",
        "ALLOWED_ORIGINS": "https://onetree.chat,https://www.onetree.chat",
        "INTERNAL_API_TOKEN": "test-production-internal-token",
        "AI_GATEWAY_URL": "http://ai-gateway:8100",
        "MODEL_SECRET_ENCRYPTION_KEY": "test-production-model-secret-key",
    }


@pytest.mark.parametrize(
    "missing_key",
    [
        "DATABASE_URL",
        "JWT_SECRET",
        "ALLOWED_ORIGINS",
        "INTERNAL_API_TOKEN",
        "AI_GATEWAY_URL",
        "MODEL_SECRET_ENCRYPTION_KEY",
    ],
)
def test_production_rejects_missing_required_settings(missing_key: str) -> None:
    environ = valid_production_environ()
    environ.pop(missing_key)

    with pytest.raises(ValueError, match=missing_key):
        load_settings(environ)


def test_production_rejects_default_jwt_secret() -> None:
    environ = valid_production_environ()
    environ["JWT_SECRET"] = "mutiagent-dev-secret-key-change-in-production"

    with pytest.raises(ValueError, match="JWT_SECRET"):
        load_settings(environ)


def test_development_accepts_explicit_development_settings() -> None:
    environ: Mapping[str, str] = {"APP_ENV": "development"}

    settings = load_settings(environ)

    assert settings.app_env == "development"


def test_jwt_requires_explicit_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "_jwt_secret", None)

    with pytest.raises(RuntimeError, match="JWT"):
        security.create_access_token({"sub": "user-1"})


def test_jwt_uses_configured_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "_jwt_secret", None)
    security.configure_jwt("configured-secret")

    token = security.create_access_token({"sub": "user-1"})

    assert security.decode_access_token(token)["sub"] == "user-1"


def test_production_rejects_default_internal_api_token() -> None:
    environ = valid_production_environ()
    environ["INTERNAL_API_TOKEN"] = "mutiagent-dev-internal-token-change-in-production"

    with pytest.raises(ValueError, match="INTERNAL_API_TOKEN"):
        load_settings(environ)


def test_production_does_not_need_platform_llm_credentials() -> None:
    environ = valid_production_environ()
    assert "LLM_API_KEY" not in environ and "LLM_MODEL" not in environ

    settings = load_settings(environ)

    assert settings.internal_api_token == "test-production-internal-token"
    assert settings.ai_gateway_url == "http://ai-gateway:8100"
