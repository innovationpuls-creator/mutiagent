"""LLM singleton factory reused across requests."""

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
_TRANSLATION_TIMEOUT = int(os.getenv("LLM_TRANSLATION_TIMEOUT", "45"))
_WORKER_MAX_TOKENS = 8192
_TRANSLATION_MAX_TOKENS = int(os.getenv("LLM_TRANSLATION_MAX_TOKENS", "4096"))

_supervisor_llm: ChatOpenAI | None = None
_worker_llm: ChatOpenAI | None = None
_thinking_worker_llm: ChatOpenAI | None = None
_search_worker_llm: ChatOpenAI | None = None
_translation_llm: ChatOpenAI | None = None


def _build(
    timeout: int,
    *,
    enable_thinking: bool,
    enable_search: bool = False,
    streaming: bool = True,
    max_tokens: int | None = None,
    max_retries: int = 1,
) -> ChatOpenAI:
    extra_body = {"enable_thinking": enable_thinking}
    if enable_search:
        extra_body.update(
            {
                "enable_search": True,
                "search_options": {
                    "forced_search": True,
                    "search_strategy": "turbo",
                },
            }
        )
    return ChatOpenAI(
        base_url=_BASE_URL,
        api_key=_API_KEY,
        model=_MODEL,
        temperature=0.7,
        timeout=timeout,
        max_tokens=max_tokens
        if max_tokens is not None
        else (_WORKER_MAX_TOKENS if timeout == _WORKER_TIMEOUT else None),
        max_retries=max_retries,
        streaming=streaming,
        extra_body=extra_body,
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


def get_search_worker_llm() -> ChatOpenAI:
    global _search_worker_llm
    if _search_worker_llm is None:
        _search_worker_llm = _build(
            _WORKER_TIMEOUT, enable_thinking=True, enable_search=True
        )
        logger.info("Search worker LLM initialized (timeout=%ds)", _WORKER_TIMEOUT)
    return _search_worker_llm


def get_translation_llm() -> ChatOpenAI:
    """Return the cached textbook translation LLM."""
    global _translation_llm
    if _translation_llm is None:
        _translation_llm = _build(
            _TRANSLATION_TIMEOUT,
            enable_thinking=False,
            streaming=False,
            max_tokens=_TRANSLATION_MAX_TOKENS,
            max_retries=0,
        )
        logger.info(
            "Translation LLM initialized (timeout=%ds)",
            _TRANSLATION_TIMEOUT,
        )
    return _translation_llm
