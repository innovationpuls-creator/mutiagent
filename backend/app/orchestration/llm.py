"""LLM singleton factory — initialized once at import time, reused across all requests."""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

logger = logging.getLogger(__name__)

_BASE_URL = os.getenv("LLM_BASE_URL")
_API_KEY = os.getenv("LLM_API_KEY")
_MODEL = os.getenv("LLM_MODEL", "gpt-4o")

_SUPERVISOR_TIMEOUT = 30
_WORKER_TIMEOUT = 180

_supervisor_llm: ChatOpenAI | None = None
_worker_llm: ChatOpenAI | None = None
_thinking_worker_llm: ChatOpenAI | None = None


def _build(timeout: int, *, enable_thinking: bool, max_retries: int = 1) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=_BASE_URL,
        api_key=_API_KEY,
        model=_MODEL,
        temperature=0.7,
        timeout=timeout,
        max_retries=max_retries,
        streaming=True,
        model_kwargs={"extra_body": {"enable_thinking": enable_thinking}},
    )


def get_supervisor_llm() -> ChatOpenAI:
    """Return the cached supervisor LLM (timeout=30s)."""
    global _supervisor_llm
    if _supervisor_llm is None:
        _supervisor_llm = _build(_SUPERVISOR_TIMEOUT, enable_thinking=False)
        logger.info("Supervisor LLM initialized (timeout=%ds)", _SUPERVISOR_TIMEOUT)
    return _supervisor_llm


def get_worker_llm() -> ChatOpenAI:
    """Return the cached non-thinking worker LLM (timeout=180s)."""
    global _worker_llm
    if _worker_llm is None:
        _worker_llm = _build(_WORKER_TIMEOUT, enable_thinking=False)
        logger.info("Worker LLM initialized (timeout=%ds)", _WORKER_TIMEOUT)
    return _worker_llm


def get_thinking_worker_llm() -> ChatOpenAI:
    """Return the cached thinking worker LLM (timeout=180s)."""
    global _thinking_worker_llm
    if _thinking_worker_llm is None:
        _thinking_worker_llm = _build(_WORKER_TIMEOUT, enable_thinking=True)
        logger.info("Thinking worker LLM initialized (timeout=%ds)", _WORKER_TIMEOUT)
    return _thinking_worker_llm
