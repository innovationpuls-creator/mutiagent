# ruff: noqa: E501
from __future__ import annotations

import logging
from urllib.parse import quote

from app.orchestration.agents.course_resources.bilibili import _bilibili_bvid_from_url
from app.orchestration.agents.course_resources.common import (
    _clean_text,
    _parent_section,
    _text_items,
)

logger = logging.getLogger(__name__)


def _section_summary(value: dict | None) -> dict:
    if not isinstance(value, dict):
        return {}
    return {
        "title": _clean_text(value.get("title")),
        "description": _clean_text(value.get("description")),
        "key_knowledge_points": _text_items(value.get("key_knowledge_points")),
    }


def _video_context(video_briefs: object, section: dict, outline: dict) -> dict:
    """What the video agent needs to search with judgment: the section and its briefs."""
    briefs = [
        {
            key: brief[key]
            for key in (
                "video_id",
                "title",
                "purpose",
                "target_markdown_heading",
                "target_paragraph_summary",
                "search_terms",
            )
            if key in brief
        }
        for brief in (video_briefs if isinstance(video_briefs, list) else [])
        if isinstance(brief, dict) and _clean_text(brief.get("video_id"))
    ]
    return {
        "course_name": _clean_text(outline.get("course_name")),
        "parent_section": _section_summary(_parent_section(outline, section)),
        "section": _section_summary(section),
        "video_briefs": briefs,
    }


def _fallback_cover_data_url(title: str) -> str:
    safe_title = _clean_text(title) or "课程视频"
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='640' height='360' viewBox='0 0 640 360'>"
        "<rect width='640' height='360' fill='oklch(22% 0.04 220)'/>"
        "<circle cx='320' cy='150' r='54' fill='oklch(70% 0.12 190)' opacity='0.85'/>"
        "<polygon points='305,122 305,178 352,150' fill='oklch(96% 0.02 90)'/>"
        f"<text x='320' y='255' text-anchor='middle' font-size='28' fill='oklch(92% 0.02 90)'>{safe_title}</text>"
        "</svg>"
    )
    encoded_svg = quote(svg, safe="/:=;,%#?&'() ")
    return "data:image/svg+xml;utf8," + encoded_svg.replace(
        quote(safe_title), safe_title
    )


def _native_video_quality_issue(videos: list[dict], video_briefs: object) -> str | None:
    if not videos:
        return "视频资源为空。"
    if not isinstance(video_briefs, list):
        return "视频资源未完整绑定 brief。"
    expected_ids = {
        _clean_text(brief.get("video_id"))
        for brief in video_briefs
        if isinstance(brief, dict) and _clean_text(brief.get("video_id"))
    }
    video_ids = {
        _clean_text(video.get("brief_id"))
        for video in videos
        if _clean_text(video.get("brief_id"))
    }
    if not expected_ids or video_ids != expected_ids:
        return "视频资源未完整绑定 brief。"
    if any(
        not _bilibili_bvid_from_url(_clean_text(video.get("url"))) for video in videos
    ):
        return "Bilibili 视频 URL 必须为精确视频页地址。"
    return None


def _normalize_videos(videos: object, video_briefs: object) -> list[dict]:
    if not isinstance(videos, list) or not isinstance(video_briefs, list):
        return []

    brief_titles = {}
    brief_purposes = {}
    for brief in video_briefs:
        if not isinstance(brief, dict):
            continue
        video_id = _clean_text(brief.get("video_id"))
        if video_id:
            brief_titles[video_id] = _clean_text(brief.get("title"))
            brief_purposes[video_id] = _clean_text(brief.get("purpose"))

    normalized = []
    for video in videos:
        if hasattr(video, "model_dump"):
            video_data = video.model_dump()
        elif isinstance(video, dict):
            video_data = dict(video)
        else:
            continue

        brief_id = _clean_text(video_data.get("brief_id") or video_data.get("video_id"))
        url = _clean_text(video_data.get("url"))
        title = _clean_text(video_data.get("title"))
        if not brief_id or not url:
            continue

        fallback_title = brief_titles.get(brief_id) or "教学视频"
        summary = brief_purposes.get(brief_id) or ""
        normalized.append(
            {
                "brief_id": brief_id,
                "title": title or fallback_title,
                "url": url,
                "cover_url": _fallback_cover_data_url(title or fallback_title),
                "cover_status": "fallback",
                "source": _clean_text(video_data.get("source")) or "Bilibili",
                "summary": summary,
            }
        )
    return normalized
