# ruff: noqa: C901, E501
from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

import httpx

from app.orchestration.agents.course_resources.common import (
    _VIDEO_METADATA_TIMEOUT_SECONDS,
    _clean_text,
)

logger = logging.getLogger(__name__)

_BILIBILI_BVID_PATTERN = re.compile(r"\b(BV[0-9A-Za-z]{10})\b")
_BILIBILI_VIDEO_PATH_PATTERN = re.compile(r"^/video/(BV[0-9A-Za-z]{10})$")


def _is_bilibili_search_placeholder_title(title: str) -> bool:
    cleaned = _clean_text(title)
    return cleaned.startswith("Bilibili 搜索结果 BV")


def _bilibili_bvid_from_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "www.bilibili.com":
        return ""
    match = _BILIBILI_VIDEO_PATH_PATTERN.fullmatch(parsed.path)
    return match.group(1) if match else ""


async def _verify_bilibili_video_metadata(url: str) -> dict:
    bvid = _bilibili_bvid_from_url(url)
    if not bvid:
        return {"status": "skip"}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.bilibili.com/",
    }
    api_url = "https://api.bilibili.com/x/web-interface/view"
    try:
        async with httpx.AsyncClient(
            timeout=_VIDEO_METADATA_TIMEOUT_SECONDS, follow_redirects=True
        ) as client:
            response = await client.get(api_url, params={"bvid": bvid}, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.warning("Bilibili metadata validation failed for %s: %s", url, exc)
        return await _verify_bilibili_video_page(url, bvid, headers)

    if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
        message = _clean_text(payload.get("message")) or "稿件不可见"
        return {"status": "invalid", "reason": f"Bilibili 视频不可见：{message}。"}
    data = payload["data"]
    metadata_text = " ".join(
        item
        for item in [
            _clean_text(data.get("title")),
            _clean_text(data.get("desc")),
            _clean_text(data.get("tname")),
            _clean_text(
                (data.get("owner") or {}).get("name")
                if isinstance(data.get("owner"), dict)
                else ""
            ),
        ]
        if item
    )
    return {
        "status": "ok",
        "text": metadata_text,
        "title": _clean_text(data.get("title")),
    }


async def _verify_bilibili_video_page(
    url: str, bvid: str, headers: dict[str, str]
) -> dict:
    try:
        async with httpx.AsyncClient(
            timeout=_VIDEO_METADATA_TIMEOUT_SECONDS, follow_redirects=True
        ) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            page_text = response.text
    except Exception as exc:
        logger.warning("Bilibili page validation failed for %s: %s", url, exc)
        return {"status": "error", "reason": "视频平台页面校验失败。"}

    if (
        "啊叻？视频不见了？" in page_text
        or "稿件不可见" in page_text
        or "视频去哪了呢？" in page_text
    ):
        return {"status": "invalid", "reason": "Bilibili 视频不可见。"}
    if bvid and bvid not in page_text:
        return {"status": "invalid", "reason": "Bilibili 页面未匹配目标稿件。"}

    title_match = re.search(r"<title[^>]*>(.*?)</title>", page_text, re.S | re.I)
    state_title_match = re.search(r'"title":"([^"]+)"', page_text)
    title = _clean_text(state_title_match.group(1) if state_title_match else "")
    page_title = _clean_text(
        re.sub(r"\s+", " ", title_match.group(1)) if title_match else ""
    )
    metadata_text = " ".join(item for item in [title, page_title] if item)
    if not metadata_text:
        return {"status": "error", "reason": "视频平台页面缺少可校验标题。"}
    return {"status": "ok", "text": metadata_text, "title": title or page_title}


async def _search_bilibili_video_results(query: str) -> list[dict]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.bilibili.com/",
    }
    return await _search_bilibili_video_page_results(query, headers)


async def _search_bilibili_video_page_results(
    query: str, headers: dict[str, str]
) -> list[dict]:
    try:
        async with httpx.AsyncClient(
            timeout=_VIDEO_METADATA_TIMEOUT_SECONDS, follow_redirects=True
        ) as client:
            response = await client.get(
                "https://search.bilibili.com/video",
                params={"keyword": query},
                headers=headers,
            )
            response.raise_for_status()
            page_text = response.text
    except Exception as exc:
        logger.warning(
            "Bilibili search request failed query=%s error_type=%s error=%s",
            query,
            type(exc).__name__,
            exc,
        )
        return []

    logger.info(
        "Bilibili search response received query=%s status_code=%s",
        query,
        response.status_code,
    )
    raw_bvids = _BILIBILI_BVID_PATTERN.findall(page_text)
    logger.info(
        "Bilibili search parse query=%s raw_result_count=%s",
        query,
        len(raw_bvids),
    )
    bvids: list[str] = []
    for bvid in raw_bvids:
        if bvid not in bvids:
            bvids.append(bvid)
        if len(bvids) >= 12:
            break
    results = [
        {
            "title": f"Bilibili 搜索结果 {bvid}",
            "url": f"https://www.bilibili.com/video/{bvid}",
            "cover_url": "",
            "source": "Bilibili",
        }
        for bvid in bvids
    ]
    logger.info(
        "Bilibili search parse query=%s parsed_result_count=%s",
        query,
        len(results),
    )
    return results
