from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from http import HTTPStatus

from dashscope import Generation, MultiModalConversation

logger = logging.getLogger(__name__)

_SEARCH_SYSTEM_PROMPT = "使用联网搜索查找与输入小节语义最相关的 Bilibili 教学视频。"
_SELECTION_SYSTEM_PROMPT = (
    "根据小节语义，对给定的真实搜索来源按相关性从高到低排序。"
    "返回所有语义相关来源的索引，不判断 URL 形态，不遗漏较低排名来源。"
    '只返回严格 JSON：{"indexes":[整数索引]}。'
)
_TEXT_ENDPOINT_ERROR_CODE = "InvalidParameter"
_TEXT_ENDPOINT_ERROR_MESSAGE = (
    "url error, please check url！ For details, see: "
    "https://help.aliyun.com/zh/model-studio/error-code#error-url"
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
            or (site_name is not None and not isinstance(site_name, str))
            or not isinstance(index, int)
            or isinstance(index, bool)
        ):
            continue
        sources[index] = AliyunBilibiliSearchSource(
            title=title,
            url=url,
            site_name=site_name or "",
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


def _collect_stream_sources(
    responses: object,
) -> tuple[object, str, str, dict[int, AliyunBilibiliSearchSource]]:
    if not hasattr(responses, "__iter__"):
        return None, "", "", {}
    status_code: object = None
    code = ""
    message = ""
    try:
        for response in responses:
            status_code = _response_value(response, "status_code")
            code_value = _response_value(response, "code")
            message_value = _response_value(response, "message")
            code = code_value if isinstance(code_value, str) else ""
            message = message_value if isinstance(message_value, str) else ""
            if status_code != HTTPStatus.OK:
                return status_code, code, message, {}
            sources = _search_sources(_response_value(response, "output"))
            if sources:
                return status_code, code, message, sources
    finally:
        close = getattr(responses, "close", None)
        if callable(close):
            close()
    return status_code, code, message, {}


def _search_multimodal_stream_sources(
    api_key: str,
    model: str,
    search_query: str,
) -> tuple[object, str, str, dict[int, AliyunBilibiliSearchSource]]:
    responses = MultiModalConversation.call(
        api_key=api_key,
        model=model,
        messages=[
            {
                "role": "system",
                "content": [{"text": _SEARCH_SYSTEM_PROMPT}],
            },
            {
                "role": "user",
                "content": [
                    {"text": f"{search_query}\n只返回 Bilibili 视频稿件来源。"}
                ],
            },
        ],
        enable_search=True,
        search_options={
            "forced_search": True,
            "search_strategy": "agent",
            "enable_source": True,
        },
        stream=True,
        incremental_output=True,
    )
    return _collect_stream_sources(responses)


def _search_generation_stream_sources(
    api_key: str,
    model: str,
    search_query: str,
) -> tuple[object, str, str, dict[int, AliyunBilibiliSearchSource]]:
    responses = Generation.call(
        api_key=api_key,
        model=model,
        messages=[
            {"role": "system", "content": _SEARCH_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"{search_query}\n只返回 Bilibili 视频稿件来源。",
            },
        ],
        enable_search=True,
        result_format="message",
        search_options={
            "forced_search": True,
            "search_strategy": "agent",
            "enable_source": True,
        },
        stream=True,
        incremental_output=True,
    )
    return _collect_stream_sources(responses)


def _requires_generation_endpoint(
    status_code: object,
    code: str,
    message: str,
) -> bool:
    return (
        status_code == HTTPStatus.BAD_REQUEST
        and code == _TEXT_ENDPOINT_ERROR_CODE
        and message == _TEXT_ENDPOINT_ERROR_MESSAGE
    )


def _selection_input(
    section_scope: str,
    sources: dict[int, AliyunBilibiliSearchSource],
) -> str:
    return json.dumps(
        {
            "section_scope": section_scope,
            "search_results": [
                {
                    "index": source.index,
                    "title": source.title,
                    "site_name": source.site_name,
                }
                for source in sources.values()
            ],
        },
        ensure_ascii=False,
    )


async def _search_aliyun_bilibili_sources(
    search_query: str,
    section_scope: str,
) -> list[AliyunBilibiliSearchSource]:
    api_key = os.getenv("LLM_API_KEY")
    model = os.getenv("LLM_MODEL")
    if not api_key or not model or not search_query or not section_scope:
        return []

    try:
        status_code, code, message, sources = await asyncio.to_thread(
            _search_multimodal_stream_sources,
            api_key,
            model,
            search_query,
        )
    except Exception as exc:
        logger.warning(
            "DashScope Bilibili search failed error_type=%s",
            type(exc).__name__,
        )
        return []

    use_generation_endpoint = _requires_generation_endpoint(
        status_code,
        code,
        message,
    )
    if use_generation_endpoint:
        logger.info("DashScope Bilibili search switching to text model endpoint")
        try:
            status_code, code, message, sources = await asyncio.to_thread(
                _search_generation_stream_sources,
                api_key,
                model,
                search_query,
            )
        except Exception as exc:
            logger.warning(
                "DashScope Bilibili text search failed error_type=%s",
                type(exc).__name__,
            )
            return []

    if status_code != HTTPStatus.OK:
        logger.warning(
            "DashScope Bilibili search rejected status=%s code=%s message=%s",
            status_code,
            code,
            message,
        )
        return []
    if not sources:
        logger.warning("DashScope Bilibili search returned no auditable sources")
        return []

    try:
        if use_generation_endpoint:
            selection_response = await asyncio.to_thread(
                Generation.call,
                api_key=api_key,
                model=model,
                messages=[
                    {"role": "system", "content": _SELECTION_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": _selection_input(section_scope, sources),
                    },
                ],
                result_format="message",
            )
        else:
            selection_response = await asyncio.to_thread(
                MultiModalConversation.call,
                api_key=api_key,
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": [{"text": _SELECTION_SYSTEM_PROMPT}],
                    },
                    {
                        "role": "user",
                        "content": [{"text": _selection_input(section_scope, sources)}],
                    },
                ],
            )
    except Exception as exc:
        logger.warning(
            "DashScope Bilibili source ranking failed error_type=%s",
            type(exc).__name__,
        )
        return []
    selection_status = _response_value(selection_response, "status_code")
    if selection_status != HTTPStatus.OK:
        logger.warning(
            "DashScope Bilibili source ranking rejected status=%s code=%s",
            selection_status,
            _response_value(selection_response, "code"),
        )
        return []
    output = _response_value(selection_response, "output")
    selected = _selected_sources(_response_content(output), sources)
    logger.info(
        "DashScope Bilibili sources ranked source_count=%s selected_count=%s",
        len(sources),
        len(selected),
    )
    return selected
