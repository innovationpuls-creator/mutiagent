from __future__ import annotations

import contextvars
import json
import logging
import re
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
request_id_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)
access_logger = logging.getLogger("app.access")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "service": getattr(record, "service", "mutiagent-backend"),
            "request_id": getattr(record, "request_id", None),
            "method": getattr(record, "method", None),
            "path": getattr(record, "path", None),
            "status_code": getattr(record, "status_code", None),
            "duration_ms": getattr(record, "duration_ms", None),
            "message": record.getMessage(),
        }
        return json.dumps(payload, ensure_ascii=False)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = _resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
        context_token = request_id_context.set(request_id)
        response: Response | None = None
        started_at = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            access_logger.info(
                "request_completed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code if response else 500,
                    "duration_ms": round((time.perf_counter() - started_at) * 1000, 3),
                    "service": "mutiagent-backend",
                },
            )
            request_id_context.reset(context_token)


def configure_json_logging(service_name: str) -> None:
    access_logger.disabled = False
    access_logger.setLevel(logging.INFO)
    if access_logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    access_logger.addHandler(handler)


def get_request_id() -> str | None:
    return request_id_context.get()


def _resolve_request_id(incoming_request_id: str | None) -> str:
    if incoming_request_id and REQUEST_ID_PATTERN.fullmatch(incoming_request_id):
        return incoming_request_id
    return uuid.uuid4().hex
