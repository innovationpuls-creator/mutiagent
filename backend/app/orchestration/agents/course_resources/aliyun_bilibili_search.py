from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any

from dashscope import MultiModalConversation

logger = logging.getLogger(__name__)

_SELECTION_SYSTEM_PROMPT = (
    "根据小节语义，对联网搜索来源按相关性从高到低排序。"
    "返回所有语义相关来源的索引，不判断 URL 形态，不遗漏较低排名来源。"
    '只返回严格 JSON：{"indexes":[整数索引]}。'
)


@dataclass(frozen=True)
class AliyunBilibiliSearchSource:
    title: str
    url: str
    site_name: str
    index: int


def _response_value(value: object, key: str) -> object:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _response_content(output: object) -> str:
    choices = _response_value(output, "choices")
    if not isinstance(choices, list) or not choices:
        return ""
    message = _response_value(choices[0], "message")
    content = _response_value(message, "content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list) or len(content) != 1:
        return ""
    text = _response_value(content[0], "text")
    return text if isinstance(text, str) else ""


def _json_content(content: str) -> str:
    stripped = content.strip()
    prefix = "```json\n"
    suffix = "\n```"
    if stripped.startswith(prefix) and stripped.endswith(suffix):
        return stripped[len(prefix) : -len(suffix)].strip()
    return stripped


def _search_sources(output: object) -> dict[int, AliyunBilibiliSearchSource]:
    search_info = _response_value(output, "search_info")
    search_results = _response_value(search_info, "search_results")
    if not isinstance(search_results, list):
        return {}

    sources: dict[int, AliyunBilibiliSearchSource] = {}
    for result in search_results:
        title = _response_value(result, "title")
        url = _response_value(result, "url")
        site_name = _response_value(result, "site_name")
        index = _response_value(result, "index")
        if (
            not isinstance(title, str)
            or not isinstance(url, str)
            or not isinstance(site_name, str)
            or not isinstance(index, int)
            or isinstance(index, bool)
        ):
            continue
        sources[index] = AliyunBilibiliSearchSource(
            title=title,
            url=url,
            site_name=site_name,
            index=index,
        )
    return sources


def _selected_sources(
    content: str,
    sources: dict[int, AliyunBilibiliSearchSource],
) -> list[AliyunBilibiliSearchSource]:
    try:
        payload = json.loads(_json_content(content))
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(payload, dict):
        return []
    indexes = payload.get("indexes")
    if not isinstance(indexes, list):
        return []

    selected: list[AliyunBilibiliSearchSource] = []
    seen: set[int] = set()
    for index in indexes:
        if not isinstance(index, int) or isinstance(index, bool) or index in seen:
            continue
        source = sources.get(index)
        if source is None:
            continue
        seen.add(index)
        selected.append(source)
    return selected


async def _search_aliyun_bilibili_sources(
    section_scope: str,
) -> list[AliyunBilibiliSearchSource]:
    api_key = os.getenv("LLM_API_KEY")
    model = os.getenv("LLM_MODEL")
    if not api_key or not model or not section_scope:
        return []

    kwargs: dict[str, Any] = {
        "api_key": api_key,
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": [{"text": _SELECTION_SYSTEM_PROMPT}],
            },
            {"role": "user", "content": [{"text": section_scope}]},
        ],
        "enable_search": True,
        "result_format": "message",
        "search_options": {
            "forced_search": True,
            "search_strategy": "turbo",
            "enable_source": True,
            "assigned_site_list": ["bilibili.com"],
            "intention_options": {"prompt_intervene": section_scope},
        },
    }
    try:
        response = await asyncio.to_thread(MultiModalConversation.call, **kwargs)
    except Exception as exc:
        logger.warning(
            "DashScope Bilibili search failed error_type=%s",
            type(exc).__name__,
        )
        return []

    if _response_value(response, "status_code") != HTTPStatus.OK:
        return []
    output = _response_value(response, "output")
    sources = _search_sources(output)
    return _selected_sources(_response_content(output), sources)
