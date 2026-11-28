from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session

from app.core.config import DEFAULT_INTERNAL_API_TOKEN
from app.database import DEMO_USER_UID
from app.main import create_app
from app.models import User, UserModelProvider
from app.services.ai_gateway_client import AiGatewayUnavailableError
from tests.postgres import postgresql_test_url

INTERNAL = {"X-Internal-Token": DEFAULT_INTERNAL_API_TOKEN}
BUILTIN_CAPS = {
    "openai/gpt-vision": {"vision": True, "tools": True, "reasoning": True},
    "openai/gpt-text": {"vision": False, "tools": True, "reasoning": False},
}


class FakeGateway:
    def __init__(self) -> None:
        self.invalidated: list[str] = []
        self.down = False

    def invalidate_user_model_config(self, user_uid: str) -> None:
        self.invalidated.append(user_uid)

    def get_builtin_capabilities(self, refs):
        if self.down:
            raise AiGatewayUnavailableError("down")
        return {
            f"{r['provider_id']}/{r['model_id']}": BUILTIN_CAPS[
                f"{r['provider_id']}/{r['model_id']}"
            ]
            for r in refs
            if f"{r['provider_id']}/{r['model_id']}" in BUILTIN_CAPS
        }


@pytest.fixture
def ctx(tmp_path: Path):
    url = postgresql_test_url(tmp_path, "model-config")
    app = create_app(database_url=url)
    gateway = FakeGateway()
    app.state.ai_gateway_client = gateway
    client = TestClient(app)
    token = client.post(
        "/api/auth/login",
        json={"account": "demo@mutiagent.local", "password": "demo123456"},
    ).json()["access_token"]
    return client, {"Authorization": f"Bearer {token}"}, gateway, url


def test_provider_secret_is_encrypted_and_masked(ctx) -> None:
    client, headers, gateway, url = ctx
    response = client.put(
        "/api/model-config/providers/openai",
        headers=headers,
        json={"api_key": "sk-secret-1234567890", "headers": {"X-Org": "org-secret"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["has_secret"] is True
    assert body["secret_mask"] == "••••7890"
    assert body["headers"] == {"X-Org": "••••"}
    assert "sk-secret" not in response.text and "org-secret" not in response.text

    listing = client.get("/api/model-config", headers=headers)
    assert "sk-secret" not in listing.text and "org-secret" not in listing.text

    from sqlalchemy import create_engine

    engine = create_engine(url)
    with engine.connect() as conn:
        row = conn.execute(
            text("select secret_encrypted, headers_encrypted from user_model_provider")
        ).one()
    assert "sk-secret" not in row[0] and "org-secret" not in row[1]
    assert row[0].startswith("gAAAA")
    assert gateway.invalidated == [DEMO_USER_UID]


def test_empty_api_key_update_keeps_existing_secret(ctx) -> None:
    client, headers, *_ = ctx
    client.put(
        "/api/model-config/providers/openai",
        headers=headers,
        json={"api_key": "sk-keep-me-0001"},
    )
    again = client.put(
        "/api/model-config/providers/openai",
        headers=headers,
        json={"display_name": "OpenAI 个人"},
    ).json()
    assert again["secret_mask"] == "••••0001"


def test_custom_provider_requires_protocol_and_base_url(ctx) -> None:
    client, headers, *_ = ctx
    response = client.put(
        "/api/model-config/providers/my-relay",
        headers=headers,
        json={"is_builtin": False},
    )
    assert response.status_code == 422


def test_custom_model_rejected_on_builtin_provider(ctx) -> None:
    client, headers, *_ = ctx
    client.put(
        "/api/model-config/providers/openai",
        headers=headers,
        json={"api_key": "sk-openai-0001"},
    )
    response = client.put(
        "/api/model-config/custom-models",
        headers=headers,
        json={"provider_id": "openai", "model_id": "gpt-x"},
    )
    assert response.status_code == 422


def test_custom_model_with_compat_roundtrip_and_runtime_decrypts(ctx) -> None:
    client, headers, *_ = ctx
    client.put(
        "/api/model-config/providers/my-relay",
        headers=headers,
        json={
            "is_builtin": False,
            "protocol": "openai-completions",
            "base_url": "http://relay.test/v1",
            "api_key": "relay-key-9999",
            "headers": {"X-Relay": "abc"},
        },
    )
    model = client.put(
        "/api/model-config/custom-models",
        headers=headers,
        json={
            "provider_id": "my-relay",
            "model_id": "relay-vl",
            "supports_vision": True,
            "compat_config": {"supportsDeveloperRole": False},
        },
    )
    assert model.status_code == 200
    runtime = client.get(
        f"/internal/users/{DEMO_USER_UID}/model-runtime-config", headers=INTERNAL
    ).json()
    provider = runtime["providers"][0]
    assert provider["api_key"] == "relay-key-9999"
    assert provider["headers"] == {"X-Relay": "abc"}
    assert runtime["custom_models"][0]["compat_config"] == {
        "supportsDeveloperRole": False
    }
    assert (
        client.delete(
            f"/api/model-config/custom-models/{model.json()['id']}", headers=headers
        ).status_code
        == 204
    )


def test_runtime_config_requires_internal_token(ctx) -> None:
    client, headers, *_ = ctx
    assert (
        client.get(
            f"/internal/users/{DEMO_USER_UID}/model-runtime-config", headers=headers
        ).status_code
        == 401
    )


def _prefs(**overrides):
    body = {
        "config_mode": "advanced",
        "default_model_ref": {"provider_id": "openai", "model_id": "gpt-text"},
        "slot_bindings": {},
    }
    body.update(overrides)
    return body


def test_vision_slot_rejects_non_vision_model(ctx) -> None:
    client, headers, *_ = ctx
    response = client.put(
        "/api/model-config/preferences",
        headers=headers,
        json=_prefs(
            slot_bindings={
                "quiz_vision": {
                    "model_ref": {"provider_id": "openai", "model_id": "gpt-text"}
                }
            }
        ),
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "MODEL_CAPABILITY_MISMATCH"


def test_vision_slot_fallback_chain_is_also_checked(ctx) -> None:
    client, headers, *_ = ctx
    response = client.put(
        "/api/model-config/preferences",
        headers=headers,
        json=_prefs(
            slot_bindings={
                "quiz_vision": {
                    "model_ref": {"provider_id": "openai", "model_id": "gpt-vision"},
                    "fallback_chain": [
                        {"provider_id": "openai", "model_id": "gpt-text"}
                    ],
                }
            }
        ),
    )
    assert response.status_code == 422


def test_custom_tool_less_model_rejected_for_chat_slot(ctx) -> None:
    client, headers, *_ = ctx
    client.put(
        "/api/model-config/providers/r",
        headers=headers,
        json={
            "is_builtin": False,
            "protocol": "openai-completions",
            "base_url": "http://x/v1",
        },
    )
    client.put(
        "/api/model-config/custom-models",
        headers=headers,
        json={"provider_id": "r", "model_id": "no-tools", "supports_tools": False},
    )
    response = client.put(
        "/api/model-config/preferences",
        headers=headers,
        json=_prefs(
            slot_bindings={
                "chat_profile": {
                    "model_ref": {"provider_id": "r", "model_id": "no-tools"}
                }
            }
        ),
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "MODEL_CAPABILITY_MISMATCH"


def test_valid_preferences_save_quick_switch_and_invalidate(ctx) -> None:
    client, headers, gateway, _ = ctx
    saved = client.put(
        "/api/model-config/preferences",
        headers=headers,
        json=_prefs(
            default_vision_model_ref={
                "provider_id": "openai",
                "model_id": "gpt-vision",
            },
            default_thinking_level="low",
        ),
    )
    assert saved.status_code == 200
    gateway.invalidated.clear()
    switched = client.patch(
        "/api/model-config/quick-switch",
        headers=headers,
        json={
            "model_ref": {"provider_id": "openai", "model_id": "gpt-vision"},
            "thinking_level": "xhigh",
        },
    )
    assert switched.status_code == 200
    assert switched.json()["default_thinking_level"] == "xhigh"
    assert switched.json()["default_model_ref"]["model_id"] == "gpt-vision"
    assert gateway.invalidated == [DEMO_USER_UID]


def test_gateway_down_during_capability_check_is_503(ctx) -> None:
    client, headers, gateway, _ = ctx
    gateway.down = True
    response = client.put(
        "/api/model-config/preferences", headers=headers, json=_prefs()
    )
    assert response.status_code == 503
    assert response.json()["error_code"] == "INTERNAL_SERVICE_UNAVAILABLE"


def test_admin_only_slot_rejected_for_students(ctx) -> None:
    client, headers, *_ = ctx
    response = client.put(
        "/api/model-config/preferences",
        headers=headers,
        json=_prefs(
            slot_bindings={
                "kb_translate": {
                    "model_ref": {"provider_id": "openai", "model_id": "gpt-text"}
                }
            }
        ),
    )
    assert response.status_code == 403


def test_unconfigured_user_gets_empty_runtime_config(ctx) -> None:
    client, *_ = ctx
    runtime = client.get(
        f"/internal/users/{DEMO_USER_UID}/model-runtime-config", headers=INTERNAL
    ).json()
    assert runtime["providers"] == []
    assert runtime["preferences"]["default_model_ref"] is None


def test_usage_is_recorded_and_aggregated(ctx) -> None:
    client, headers, *_ = ctx
    for success in (True, False):
        r = client.post(
            f"/internal/users/{DEMO_USER_UID}/model-usage",
            headers=INTERNAL,
            json={
                "scene": "chat_profile",
                "provider_id": "openai",
                "model_id": "gpt-text",
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_read_tokens": 10,
                "reasoning_tokens": 5,
                "estimated_cost_usd": 0.002,
                "latency_ms": 400,
                "success": success,
                "error_code": None if success else "RATE_LIMIT",
            },
        )
        assert r.status_code == 200
    usage = client.get("/api/model-config/usage?days=7", headers=headers).json()
    assert usage["total_requests"] == 2
    bucket = usage["buckets"][0]
    assert bucket["scene"] == "chat_profile"
    assert bucket["input_tokens"] == 200 and bucket["success_requests"] == 1
    assert bucket["estimated_cost_usd"] == pytest.approx(0.004)
    assert usage["total_tokens"] == 2 * (100 + 50 + 5)


def _oauth_cred(refresh: str) -> dict:
    return {"access": "acc-" + refresh, "refresh": refresh, "expires": 1}


def test_oauth_refresh_lock_is_compare_and_swap(ctx) -> None:
    client, headers, _, url = ctx
    exp = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    assert (
        client.put(
            f"/internal/users/{DEMO_USER_UID}/providers/openai-codex/oauth-credential",
            headers=INTERNAL,
            json={
                "credential": _oauth_cred("r0"),
                "expires_at": exp,
                "account_label": "me@x",
            },
        ).status_code
        == 200
    )
    view = client.get("/api/model-config", headers=headers).json()["providers"][0]
    assert view["oauth_status"] == "expired" and "acc-r0" not in str(view)

    lock = f"/internal/users/{DEMO_USER_UID}/providers/openai-codex/oauth-refresh-lock"
    current = client.post(lock, headers=INTERNAL, json={}).json()
    assert current["outcome"] == "unchanged"
    fp = current["refresh_fingerprint"]

    fresh = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    first = client.post(
        lock,
        headers=INTERNAL,
        json={
            "previous_refresh_fingerprint": fp,
            "new_credential": _oauth_cred("r1"),
            "expires_at": fresh,
        },
    ).json()
    assert first["outcome"] == "refreshed"
    stale = client.post(
        lock,
        headers=INTERNAL,
        json={
            "previous_refresh_fingerprint": fp,
            "new_credential": _oauth_cred("r2"),
            "expires_at": fresh,
        },
    ).json()
    assert stale["outcome"] == "conflict"
    assert stale["credential"]["refresh"] == "r1"


def test_concurrent_cas_refresh_lets_exactly_one_writer_win(ctx) -> None:
    client, _, _, _ = ctx
    exp = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    base = f"/internal/users/{DEMO_USER_UID}/providers/openai-codex"
    client.put(
        f"{base}/oauth-credential",
        headers=INTERNAL,
        json={"credential": _oauth_cred("r0"), "expires_at": exp},
    )
    fp = client.post(f"{base}/oauth-refresh-lock", headers=INTERNAL, json={}).json()[
        "refresh_fingerprint"
    ]
    outcomes: list[str] = []

    def attempt(n: int) -> None:
        r = client.post(
            f"{base}/oauth-refresh-lock",
            headers=INTERNAL,
            json={
                "previous_refresh_fingerprint": fp,
                "new_credential": _oauth_cred(f"n{n}"),
                "expires_at": exp,
            },
        )
        outcomes.append(r.json()["outcome"])

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(5)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert outcomes.count("refreshed") == 1
    assert outcomes.count("conflict") == 4


def test_missing_encryption_key_in_production_fails_closed(tmp_path: Path) -> None:
    from sqlalchemy import create_engine

    from app.core.config import AppSettings
    from app.migration_state import migrate_to_head

    url = postgresql_test_url(tmp_path, "model-config-prod")
    migrate_to_head(create_engine(url))
    settings = AppSettings(
        app_env="production",
        database_url=url,
        jwt_secret="prod-secret",
        allowed_origins=("https://x.test",),
        internal_api_token="tok",
    )
    app = create_app(database_url=url, settings=settings)
    with Session(
        app.state_engine if hasattr(app, "state_engine") else create_engine(url)
    ) as s:
        s.add(
            User(uid="u-prod", username="u", identifier="prod@x.test", role="student")
        )
        s.commit()
    from app.core.security import create_access_token

    headers = {"Authorization": f"Bearer {create_access_token({'sub': 'u-prod'})}"}
    client = TestClient(app)
    response = client.put(
        "/api/model-config/providers/openai",
        headers=headers,
        json={"api_key": "sk-x-1234"},
    )
    assert response.status_code == 503
    assert UserModelProvider.__tablename__ == "user_model_provider"
