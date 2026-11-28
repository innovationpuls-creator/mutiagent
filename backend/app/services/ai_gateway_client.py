"""Backend -> TS gateway calls (cache invalidation, builtin capability lookup)."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Protocol

from app.core.observability import REQUEST_ID_HEADER, get_request_id

logger = logging.getLogger(__name__)


class AiGatewayUnavailableError(RuntimeError):
    pass


class AiGatewayHttpError(RuntimeError):
    def __init__(self, status: int, detail: str, error_code: str | None):
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.error_code = error_code


class AiGatewayClient(Protocol):
    def invalidate_user_model_config(self, user_uid: str) -> None: ...

    def get_builtin_capabilities(
        self, refs: list[dict[str, str]]
    ) -> dict[str, dict[str, bool]]: ...


class HttpAiGatewayClient:
    def __init__(self, base_url: str, internal_token: str | None, timeout: float = 3):
        self._base_url = base_url.rstrip("/")
        self._token = internal_token
        self._timeout = timeout

    def _post(self, path: str, body: dict) -> dict:
        if not self._token:
            raise AiGatewayUnavailableError("内部令牌未配置")
        headers = {
            "Content-Type": "application/json",
            "X-Internal-Token": self._token,
        }
        request_id = get_request_id()
        if request_id:
            headers[REQUEST_ID_HEADER] = request_id
        request = urllib.request.Request(
            f"{self._base_url}{path}",
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310
                return json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as exc:
            detail, code = "AI 服务暂时不可用", None
            try:
                data = json.loads(exc.read().decode("utf-8") or "{}")
                detail = str(data.get("detail") or detail)
                code = data.get("error_code")
            except (ValueError, OSError):
                pass
            raise AiGatewayHttpError(exc.code, detail, code) from exc
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            raise AiGatewayUnavailableError(type(exc).__name__) from exc

    def invalidate_user_model_config(self, user_uid: str) -> None:
        """Best effort: failures only warn; the gateway cache TTL is the backstop."""
        try:
            self._post(
                "/internal/cache/invalidate-user-model-config", {"user_uid": user_uid}
            )
        except AiGatewayUnavailableError as exc:
            logger.warning(
                "model_config_cache_invalidate_failed",
                extra={"user_uid": user_uid, "reason": str(exc)},
            )

    def get_builtin_capabilities(
        self, refs: list[dict[str, str]]
    ) -> dict[str, dict[str, bool]]:
        result = self._post("/internal/models/capabilities", {"refs": refs})
        capabilities = result.get("capabilities")
        return capabilities if isinstance(capabilities, dict) else {}


class AiGatewayError(RuntimeError):
    """The gateway answered an AI call with an HTTP error."""

    def __init__(self, status: int, detail: str, error_code: str | None = None):
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.error_code = error_code


def call_gateway_ai(path: str, body: dict, timeout: float = 240) -> dict:
    """POST an internal AI job to the TS gateway (runs on the caller's own model)."""
    from app.core.config import DEFAULT_INTERNAL_API_TOKEN, load_settings

    settings = load_settings()
    token = settings.internal_api_token or (
        None if settings.is_production else DEFAULT_INTERNAL_API_TOKEN
    )
    client = HttpAiGatewayClient(settings.ai_gateway_url, token, timeout=timeout)
    try:
        return client._post(path, body)
    except AiGatewayHttpError as exc:
        raise AiGatewayError(exc.status, exc.detail, exc.error_code) from exc


async def acall_gateway_ai(path: str, body: dict, timeout: float = 240) -> dict:
    import asyncio

    return await asyncio.to_thread(call_gateway_ai, path, body, timeout)
