# ruff: noqa: C901, E501
from __future__ import annotations

from app.orchestration.agents.course_resources.common import (
    _clean_text,
)


def _section_markdown_output_refs(outline: dict, section_id: str) -> dict[str, object]:
    section_markdowns = outline.get("section_markdowns")
    value = (
        section_markdowns.get(section_id) if isinstance(section_markdowns, dict) else {}
    )
    markdown_value = value if isinstance(value, dict) else {}
    video_briefs = markdown_value.get("video_briefs")
    animation_briefs = markdown_value.get("animation_briefs")
    source_references = markdown_value.get("source_references")
    return {
        "section_markdown_id": section_id,
        "source_reference_count": len(source_references)
        if isinstance(source_references, list)
        else 0,
        "video_brief_ids": [
            _clean_text(brief.get("video_id"))
            for brief in video_briefs
            if isinstance(brief, dict) and _clean_text(brief.get("video_id"))
        ]
        if isinstance(video_briefs, list)
        else [],
        "animation_brief_ids": [
            _clean_text(brief.get("animation_id"))
            for brief in animation_briefs
            if isinstance(brief, dict) and _clean_text(brief.get("animation_id"))
        ]
        if isinstance(animation_briefs, list)
        else [],
    }


def _section_video_output_refs(outline: dict, section_id: str) -> dict[str, object]:
    section_video_links = outline.get("section_video_links")
    value = (
        section_video_links.get(section_id)
        if isinstance(section_video_links, dict)
        else {}
    )
    video_value = value if isinstance(value, dict) else {}
    videos = video_value.get("videos")
    unavailable = video_value.get("unavailable_videos")
    return {
        "section_video_id": section_id,
        "available_video_count": len(videos) if isinstance(videos, list) else 0,
        "unavailable_video_count": len(unavailable)
        if isinstance(unavailable, list)
        else 0,
    }


def _section_animation_output_refs(outline: dict, section_id: str) -> dict[str, object]:
    section_html_animations = outline.get("section_html_animations")
    value = (
        section_html_animations.get(section_id)
        if isinstance(section_html_animations, dict)
        else {}
    )
    animation_value = value if isinstance(value, dict) else {}
    animations = animation_value.get("animations")
    return {
        "section_animation_id": section_id,
        "animation_count": len(animations) if isinstance(animations, list) else 0,
    }


def _section_compose_output_refs(outline: dict, section_id: str) -> dict[str, object]:
    section_composed_markdowns = outline.get("section_composed_markdowns")
    value = (
        section_composed_markdowns.get(section_id)
        if isinstance(section_composed_markdowns, dict)
        else {}
    )
    composed_value = value if isinstance(value, dict) else {}
    blocks = composed_value.get("blocks")
    source_references = composed_value.get("source_references")
    return {
        "section_composed_markdown_id": section_id,
        "block_count": len(blocks) if isinstance(blocks, list) else 0,
        "source_reference_count": len(source_references)
        if isinstance(source_references, list)
        else 0,
    }
