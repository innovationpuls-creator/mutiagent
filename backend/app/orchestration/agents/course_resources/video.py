# ruff: noqa: C901, E501
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from urllib.parse import quote, urlparse

import httpx
from langchain_core.language_models import BaseChatModel

from app.orchestration.agents.course_resources.bilibili import (
    _bilibili_bvid_from_url,
    _is_bilibili_search_placeholder_title,
)
from app.orchestration.agents.course_resources.common import (
    _SECTION_CONCURRENCY_LIMIT,
    _VIDEO_METADATA_TIMEOUT_SECONDS,
    _VIDEO_VERIFIED_QUERY_LIMIT,
    _clean_text,
    _merge_course_resource_data,
    _now_iso,
    _parent_section,
    _persist_outline,
    _resource_context,
    _resource_query_with_prompt_budget,
    _section_by_id,
    _section_title,
    _target_sections_for_scope,
    _text_items,
    _tool_args,
)
from app.orchestration.state import OrchestrationState

logger = logging.getLogger(__name__)

_VIDEO_TOPIC_STOPWORDS = {
    "视频",
    "教程",
    "导入",
    "导入视频",
    "学习目标",
    "学习",
    "学习者",
    "帮助",
    "理解",
    "建立",
    "直觉",
    "本节",
    "小节",
    "目的",
    "实战",
    "讲解",
    "课程",
    "任务拆解",
    "检查点",
}

_VIDEO_QUALITY_GENERIC_KEYWORDS = {
    "ai",
    "agent",
    "openaiapi",
    "openai",
    "智能体",
    "大模型",
    "llm",
    "api",
    "apikey",
    "测试",
    "评测",
    "标准",
    "测试用例",
    "可靠性",
    "验收标准",
}

_VIDEO_DOMAIN_KEYWORDS = ("AI", "Agent", "OpenAI", "智能体", "大模型", "LLM", "API")

_VIDEO_TOPIC_SYNONYMS = {
    "检查点": ["测试", "评测", "检查", "测试用例"],
    "验收标准": ["测试", "评测", "标准", "可靠性", "测试用例"],
    "质量检查": ["测试", "评测", "质量", "可靠性", "测试用例"],
    "运行证据": ["日志", "测试", "报告", "证据", "调试"],
    "任务拆解": ["拆解", "任务", "需求"],
    "需求拆解": ["拆解", "需求", "任务"],
    "接口契约": ["接口", "契约", "API", "Schema"],
    "功能边界": ["功能", "边界", "范围"],
    "环境变量配置": ["Python"],
    "SDK初始化": ["Python", "SDK"],
    "异步编程中": ["asyncio", "异步编程"],
    "稳定性陷阱": ["event loop", "asyncio"],
    "阻塞事件循环": ["event loop", "asyncio"],
    "异步调用至关重要": ["asyncio", "event loop"],
    "文本分块": ["chunk", "chunking", "chunk_size", "chunk_overlap", "overlap", "切分"],
    "分块策略": [
        "文本分块",
        "chunk",
        "chunking",
        "chunk_size",
        "chunk_overlap",
        "overlap",
    ],
    "Embedding": ["向量化", "文本到向量", "向量", "嵌入"],
    "文本到向量": ["Embedding", "向量化", "向量"],
    "维度映射": ["向量维度", "向量空间"],
    "语义检索": ["检索", "召回", "RAG"],
    "RAG": ["检索增强生成", "检索", "召回"],
    "上下文丢失": ["上下文", "overlap"],
    "chunk": ["文本分块", "chunking", "chunk_size", "chunk_overlap", "overlap"],
    "chunking": ["文本分块", "chunk", "chunk_size", "chunk_overlap", "overlap"],
    "overlap": ["文本分块", "chunk", "chunking", "chunk_overlap"],
}

_VIDEO_TOPIC_SUBTERMS = (
    "文本分块",
    "分块策略",
    "chunk_size",
    "chunk_overlap",
    "chunking",
    "chunk",
    "overlap",
    "向量数据库",
    "向量存储",
    "文本到向量",
    "向量化",
    "维度映射",
    "向量空间",
    "语义检索",
    "检索",
    "召回",
    "Embedding",
    "RAG",
    "上下文",
)

_VIDEO_SPECIFIC_TERM_MARKERS = (
    "chunk",
    "pdf",
    "vector",
    "loader",
    "splitter",
    "embedder",
    "valueerror",
    "mismatch",
    "shape",
    "dimension",
    "debug",
    "query",
    "document",
)


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


def _fallback_video_search_url(query: str) -> str:
    clean_query = _clean_text(query) or "课程教学视频"
    return f"https://search.bilibili.com/video?keyword={quote(clean_query)}"


def _fallback_videos_for_briefs(
    video_briefs: object,
    section: dict,
    outline: dict | None = None,
) -> list[dict]:
    if not isinstance(video_briefs, list):
        return []

    fallback_videos: list[dict] = []
    section_title = _clean_text(section.get("title")) or "教学小节"
    knowledge_points = _text_items(section.get("key_knowledge_points"))

    for brief in video_briefs:
        if not isinstance(brief, dict):
            continue
        brief_id = _clean_text(brief.get("video_id"))
        if not brief_id:
            continue
        brief_title = _clean_text(brief.get("title"))
        brief_purpose = _clean_text(brief.get("purpose"))
        title = brief_title or section_title
        if knowledge_points:
            title = f"{title}：{knowledge_points[0]}"
        query = next(
            iter(_video_search_queries([brief], section, outline)),
            f"{section_title} 教程",
        )
        fallback_videos.append(
            {
                "brief_id": brief_id,
                "title": title,
                "url": _fallback_video_search_url(query),
                "cover_url": _fallback_cover_data_url(title),
                "cover_status": "fallback",
                "source": "Bilibili 搜索兜底",
                "summary": brief_purpose,
            }
        )
    return fallback_videos


def _video_topic_terms(
    video_briefs: object, section: dict, outline: dict | None = None
) -> list[str]:
    terms = [_clean_text(section.get("title"))]
    if isinstance(outline, dict):
        terms.append(_clean_text(outline.get("course_name")))
        parent_section = _parent_section(outline, section)
        if isinstance(parent_section, dict):
            terms.append(_clean_text(parent_section.get("title")))
    terms.extend(_text_items(section.get("key_knowledge_points")))
    if isinstance(video_briefs, list):
        for brief in video_briefs:
            if not isinstance(brief, dict):
                continue
            terms.append(_clean_text(brief.get("title")))
            terms.append(_clean_text(brief.get("purpose")))
    return [term for term in terms if term]


def _video_topic_keywords(topic_terms: list[str]) -> list[str]:
    keywords: list[str] = []
    for term in topic_terms:
        compact = re.sub(r"\s+", "", _clean_text(term))
        if compact and compact not in _VIDEO_TOPIC_STOPWORDS and len(compact) >= 2:
            keywords.append(compact)
            keywords.extend(_VIDEO_TOPIC_SYNONYMS.get(compact, []))
        for fragment in _video_term_fragments(term):
            if fragment in _VIDEO_TOPIC_STOPWORDS or len(fragment) < 2:
                continue
            keywords.append(fragment)
            keywords.extend(_VIDEO_TOPIC_SYNONYMS.get(fragment, []))
        for token in re.findall(r"[A-Za-z][A-Za-z0-9.+_-]*|[\u4e00-\u9fff]{2,}", term):
            clean_token = _clean_text(token)
            if clean_token in _VIDEO_TOPIC_STOPWORDS or len(clean_token) < 2:
                continue
            keywords.append(clean_token)
            keywords.extend(_VIDEO_TOPIC_SYNONYMS.get(clean_token, []))
    seen: set[str] = set()
    unique_keywords: list[str] = []
    for keyword in keywords:
        lowered = keyword.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique_keywords.append(keyword)
    return unique_keywords


def _video_quality_keywords(keywords: list[str]) -> list[str]:
    filtered: list[str] = []
    seen: set[str] = set()
    for keyword in keywords:
        clean_keyword = _clean_text(keyword)
        lowered = clean_keyword.lower()
        if not clean_keyword or lowered in seen:
            continue
        if lowered in _VIDEO_QUALITY_GENERIC_KEYWORDS:
            continue
        filtered.append(clean_keyword)
        seen.add(lowered)
    return filtered


def _video_term_fragments(term: str) -> list[str]:
    clean_term = _clean_text(term)
    if not clean_term:
        return []
    fragments: list[str] = []
    compact = re.sub(r"\s+", "", clean_term)
    compact_lower = compact.lower()
    for topic_subterm in _VIDEO_TOPIC_SUBTERMS:
        if topic_subterm.lower() in compact_lower and topic_subterm not in fragments:
            fragments.append(topic_subterm)
    for piece in re.split(r"[与和及、/（）()：:，,。·\-\s]+|的", clean_term):
        normalized = _clean_text(piece)
        if len(normalized) >= 2 and normalized not in fragments:
            fragments.append(normalized)
    return fragments


def _video_focus_query_terms(keywords: list[str]) -> list[str]:
    joined = " ".join(keywords)
    compact = re.sub(r"\s+", "", joined)
    lowered = compact.lower()
    focus_terms: list[str] = []

    def add(term: str) -> None:
        if term not in focus_terms:
            focus_terms.append(term)

    if "rag" in lowered or "检索增强生成" in compact:
        add("RAG")
    if "embedding" in lowered or "文本到向量" in compact or "向量化" in compact:
        add("Embedding")
    if "文本分块" in compact or "chunk" in lowered or "切分" in compact:
        add("文本分块")
    if "向量数据库" in compact or "向量存储" in compact:
        add("向量数据库")
    if "语义检索" in compact or "检索" in compact or "召回" in compact:
        add("语义检索")
    if "上下文" in compact or "overlap" in lowered:
        add("上下文")
    return focus_terms


def _video_domain_keywords(topic_terms: list[str]) -> list[str]:
    keywords = list(_VIDEO_DOMAIN_KEYWORDS)
    for term in topic_terms:
        clean_term = _clean_text(term)
        if clean_term and len(clean_term) >= 2:
            keywords.append(clean_term)
    return _video_topic_keywords(keywords)


def _video_domain_anchor_terms(section: dict, outline: dict | None = None) -> list[str]:
    terms: list[str] = []
    if isinstance(outline, dict):
        terms.append(_clean_text(outline.get("course_name")))
        parent_section = _parent_section(outline, section)
        if isinstance(parent_section, dict):
            terms.append(_clean_text(parent_section.get("title")))
            terms.extend(_text_items(parent_section.get("key_knowledge_points")))
    terms.extend(_text_items(section.get("key_knowledge_points")))
    return _video_topic_keywords([term for term in terms if term])


def _video_brief_anchor_terms(video_briefs: object) -> list[str]:
    if not isinstance(video_briefs, list):
        return []
    terms: list[str] = []
    for brief in video_briefs:
        if not isinstance(brief, dict):
            continue
        terms.append(_clean_text(brief.get("title")))
        terms.append(_clean_text(brief.get("purpose")))
    return _video_topic_keywords([term for term in terms if term])


def _strip_html_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", _clean_text(text))


def _matched_video_keywords(text: str, keywords: list[str]) -> list[str]:
    compact_text = re.sub(r"\s+", "", _strip_html_tags(text))
    lower_text = compact_text.lower()
    matches: list[str] = []
    seen: set[str] = set()
    for keyword in keywords:
        clean_keyword = _clean_text(keyword)
        lowered = clean_keyword.lower()
        if not clean_keyword or lowered in seen:
            continue
        if clean_keyword in compact_text or lowered in lower_text:
            matches.append(clean_keyword)
            seen.add(lowered)
    return matches


def _is_generic_video_term(term: str) -> bool:
    compact = re.sub(r"\s+", "", _clean_text(term))
    if not compact:
        return True
    remainder = compact
    for stopword in _VIDEO_TOPIC_STOPWORDS:
        remainder = remainder.replace(stopword, "")
    return len(remainder) < 2


def _strip_video_stopwords(term: str) -> str:
    compact = re.sub(r"\s+", "", _clean_text(term))
    for stopword in sorted(_VIDEO_TOPIC_STOPWORDS, key=len, reverse=True):
        compact = compact.replace(stopword, "")
    return compact


def _video_specific_brief_terms(
    video_briefs: object,
    section: dict,
    outline: dict | None = None,
) -> list[str]:
    if not isinstance(video_briefs, list):
        return []
    domain_terms = {
        _clean_text(term).lower()
        for term in _video_domain_anchor_terms(section, outline)
        if _clean_text(term)
    }
    specific_terms: list[str] = []
    seen: set[str] = set()

    def overlaps_domain(term: str) -> bool:
        compact = re.sub(r"\s+", "", _clean_text(term)).lower()
        if not compact:
            return False
        if compact in domain_terms:
            return True
        pieces = [
            _clean_text(piece).lower()
            for piece in re.split(r"[./_:+\-]+", compact)
            if _clean_text(piece)
        ]
        if any(piece in domain_terms for piece in pieces):
            return True
        return any(
            len(domain_term) >= 3 and (domain_term in compact or compact in domain_term)
            for domain_term in domain_terms
        )

    def add(term: str, *, allow_domain_overlap: bool = False) -> None:
        clean_term = _clean_text(term)
        lowered = clean_term.lower()
        if not clean_term or lowered in seen or _is_generic_video_term(clean_term):
            return
        if (
            re.fullmatch(r"[A-Za-z][A-Za-z0-9.+_-]*", clean_term)
            and not allow_domain_overlap
            and not overlaps_domain(clean_term)
        ):
            return
        if lowered in domain_terms and not allow_domain_overlap:
            return
        has_enough_length = len(clean_term) >= 4 or bool(
            re.fullmatch(r"[A-Za-z]{3,}", clean_term)
        )
        if not has_enough_length:
            return
        specific_terms.append(clean_term)
        seen.add(lowered)

    for brief in video_briefs:
        if not isinstance(brief, dict):
            continue
        title = _clean_text(brief.get("title"))
        purpose = _clean_text(brief.get("purpose"))
        stripped_title = _strip_video_stopwords(title)
        stripped_purpose = _strip_video_stopwords(purpose)
        add(stripped_title)
        for fragment in _video_term_fragments(stripped_title):
            add(fragment)
        for fragment in _video_term_fragments(stripped_purpose):
            add(fragment)
        for token in re.findall(
            r"[A-Za-z][A-Za-z0-9.+_-]*", " ".join([title, purpose])
        ):
            allow_domain_overlap = any(
                marker in token.lower() for marker in _VIDEO_SPECIFIC_TERM_MARKERS
            )
            add(token, allow_domain_overlap=allow_domain_overlap)
    return specific_terms


def _video_specific_brief_technical_tokens(
    video_briefs: object,
    section: dict,
    outline: dict | None = None,
) -> list[str]:
    return [
        term
        for term in _video_specific_brief_terms(video_briefs, section, outline)
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9.+_-]*", term)
    ]


def _requires_specific_video_brief_match(
    video_briefs: object,
    section: dict,
    outline: dict | None = None,
) -> bool:
    technical_tokens = _video_specific_brief_technical_tokens(
        video_briefs, section, outline
    )
    if len(technical_tokens) >= 2:
        return True
    specific_terms = _video_specific_brief_terms(video_briefs, section, outline)
    technical_markers = (
        "环境变量",
        "初始化",
        "api key",
        "apikey",
        "异步调用",
        "阻塞事件循环",
        "排查",
        "维度不匹配",
        "Chunking",
        "PDF",
        "Vector",
        "Loader",
        "Splitter",
        "Embedder",
    )
    return any(
        marker.lower() in term.lower()
        for term in specific_terms
        for marker in technical_markers
    )


def _has_strong_video_keyword_match(text: str, keywords: list[str]) -> bool:
    matches = _matched_video_keywords(text, keywords)
    if not matches:
        return False
    if any(len(match) >= 6 for match in matches):
        return True
    return len(matches) >= 2


def _has_strong_video_brief_match(
    text: str,
    video_briefs: object,
    section: dict,
    outline: dict | None = None,
) -> bool:
    specific_terms = _video_specific_brief_terms(video_briefs, section, outline)
    if not specific_terms:
        return False
    specific_keywords = _video_quality_keywords(_video_topic_keywords(specific_terms))
    return _has_strong_video_keyword_match(text, specific_keywords or specific_terms)


def _has_related_video_topic(
    text: str,
    video_briefs: object,
    section: dict,
    outline: dict | None = None,
) -> bool:
    domain_keywords = _video_quality_keywords(
        _video_domain_anchor_terms(section, outline)
    )
    brief_keywords = _video_quality_keywords(_video_brief_anchor_terms(video_briefs))
    topic_keywords = _video_quality_keywords(
        _video_topic_keywords(_video_topic_terms(video_briefs, section, outline))
    )
    matched_domain = _matched_video_keywords(text, domain_keywords)
    matched_brief = _matched_video_keywords(text, brief_keywords)
    matched_topic = _matched_video_keywords(text, topic_keywords)
    matched_focus = _matched_video_keywords(
        text,
        _video_focus_query_terms([*domain_keywords, *brief_keywords, *topic_keywords]),
    )
    return (
        len(matched_domain) >= 2
        or len(matched_topic) >= 3
        or (
            bool(matched_focus)
            and (bool(matched_domain) or bool(matched_brief) or len(matched_topic) >= 2)
        )
    )


def _matches_video_domain_or_section_topic(
    text: str,
    section: dict,
    outline: dict | None = None,
) -> bool:
    domain_anchor_terms = _video_quality_keywords(
        _video_domain_anchor_terms(section, outline)
    )
    section_terms = _video_quality_keywords(
        _video_topic_keywords(
            [
                _clean_text(section.get("title")),
                *_text_items(section.get("key_knowledge_points")),
            ]
        )
    )
    matched_domain = _matched_video_keywords(text, domain_anchor_terms)
    matched_section = _matched_video_keywords(text, section_terms)
    return bool(matched_domain) or bool(matched_section)


def _contains_any_video_keyword(text: str, keywords: list[str]) -> bool:
    return bool(_matched_video_keywords(text, keywords))


def _video_domain_issue(metadata_text: str, topic_terms: list[str]) -> str | None:
    normalized_text = re.sub(r"<[^>]+>", "", metadata_text)
    normalized_compact = re.sub(r"\s+", "", normalized_text)
    normalized_lower = normalized_text.lower()
    domain_keywords = _video_quality_keywords(_video_domain_keywords(topic_terms))
    if any(
        keyword in normalized_compact or keyword.lower() in normalized_lower
        for keyword in domain_keywords
    ):
        return None
    return "视频平台真实标题或简介未体现当前课程主题。"


def _video_metadata_topic_issue(
    metadata_text: str,
    topic_terms: list[str],
    section: dict,
    video_briefs: object,
    outline: dict | None = None,
) -> str | None:
    specific_brief_terms = _video_specific_brief_terms(video_briefs, section, outline)
    if specific_brief_terms and _requires_specific_video_brief_match(
        video_briefs, section, outline
    ):
        if not _has_strong_video_brief_match(
            metadata_text, video_briefs, section, outline
        ):
            if _has_related_video_topic(metadata_text, video_briefs, section, outline):
                return None
            return "视频平台真实标题或简介未体现小节主题。"
        return None
    domain_issue = _video_domain_issue(metadata_text, topic_terms)
    if domain_issue:
        return domain_issue
    domain_anchor_terms = _video_domain_anchor_terms(section, outline)
    if domain_anchor_terms and not _contains_any_video_keyword(
        metadata_text, domain_anchor_terms
    ):
        return "视频平台真实标题或简介未体现当前课程主题。"
    brief_anchor_terms = _video_brief_anchor_terms(video_briefs)
    if brief_anchor_terms and not _contains_any_video_keyword(
        metadata_text, brief_anchor_terms
    ):
        return "视频平台真实标题或简介未体现小节主题。"
    topic_keywords = _video_topic_keywords(topic_terms)
    if not topic_keywords:
        return None
    if _contains_any_video_keyword(metadata_text, topic_keywords):
        return None
    return "视频平台真实标题或简介未体现小节主题。"


def _is_youtube_watch_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.hostname == "www.youtube.com" and parsed.path == "/watch"


def _normalized_video_quality_issue(
    videos: list[dict],
    video_briefs: object,
    section: dict,
    outline: dict | None = None,
) -> str | None:
    if not videos:
        return "视频资源为空。"
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
    if expected_ids and video_ids != expected_ids:
        return "视频资源未完整绑定 brief。"
    topic_terms = _video_topic_terms(video_briefs, section, outline)
    for video in videos:
        url = _clean_text(video.get("url"))
        parsed = urlparse(url)
        bilibili_bvid = _bilibili_bvid_from_url(url)
        source = _clean_text(video.get("source"))
        is_youtube_watch_url = _is_youtube_watch_url(url)
        if source == "YouTube" and not is_youtube_watch_url:
            return "YouTube 视频 URL 必须为精确 watch 视频页地址。"
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            if source == "Bilibili":
                return "Bilibili 视频 URL 必须为精确视频页地址。"
            return "视频 URL 必须是可直接打开的 HTTP(S) 地址。"
        if not bilibili_bvid and not is_youtube_watch_url:
            return "Bilibili 视频 URL 必须为精确视频页地址。"
        title = _clean_text(video.get("title"))
        specific_brief_terms = _video_specific_brief_terms(
            video_briefs, section, outline
        )
        if not bilibili_bvid:
            title_source = (
                f"{_clean_text(video.get('title'))} {_clean_text(video.get('source'))}"
            )
            if specific_brief_terms and _requires_specific_video_brief_match(
                video_briefs, section, outline
            ):
                if not _has_strong_video_brief_match(
                    title_source, video_briefs, section, outline
                ):
                    if _has_related_video_topic(
                        title_source, video_briefs, section, outline
                    ):
                        continue
                    return "视频标题未体现小节主题或 brief 目的。"
                continue
            title_source = (
                f"{_clean_text(video.get('title'))} {_clean_text(video.get('source'))}"
            )
            title_keywords = _video_quality_keywords(_video_topic_keywords(topic_terms))
            if title_keywords and not _contains_any_video_keyword(
                title_source, title_keywords
            ):
                return "视频标题未体现小节主题或 brief 目的。"
        if bilibili_bvid and _is_bilibili_search_placeholder_title(title):
            continue
        title_source = f"{title} {_clean_text(video.get('source'))}"
        if specific_brief_terms and _requires_specific_video_brief_match(
            video_briefs, section, outline
        ):
            if not _has_strong_video_brief_match(
                title_source, video_briefs, section, outline
            ):
                if _has_related_video_topic(
                    title_source, video_briefs, section, outline
                ):
                    continue
                return "视频标题未体现小节主题或 brief 目的。"
            continue
        if not _matches_video_domain_or_section_topic(title_source, section, outline):
            if _has_related_video_topic(title_source, video_briefs, section, outline):
                continue
            return "视频标题未体现当前课程领域或小节主题。"
    return None


async def _normalized_video_quality_issue_async(
    videos: list[dict],
    video_briefs: object,
    section: dict,
    outline: dict | None = None,
) -> str | None:
    issue = _normalized_video_quality_issue(videos, video_briefs, section, outline)
    if issue:
        return issue
    topic_terms = _video_topic_terms(video_briefs, section, outline)
    for video in videos:
        url = _clean_text(video.get("url"))
        if not _bilibili_bvid_from_url(url):
            continue
        import app.orchestration.agents.course_resources as cr_pkg

        metadata = await cr_pkg._verify_bilibili_video_metadata(url)
        status = metadata.get("status")
        if status == "skip":
            continue
        if status != "ok":
            return _clean_text(metadata.get("reason")) or "视频平台元数据校验失败。"
        metadata_issue = _video_metadata_topic_issue(
            _clean_text(metadata.get("text")),
            topic_terms,
            section,
            video_briefs,
            outline,
        )
        if metadata_issue:
            return metadata_issue
        metadata_title = _clean_text(metadata.get("title"))
        if metadata_title:
            video["title"] = metadata_title
    return None


def _compact_video_query_parts(parts: list[str]) -> str:
    cleaned = [_clean_text(p) for p in parts if _clean_text(p)]
    seen: set[str] = set()
    unique_parts: list[str] = []
    for part in cleaned:
        lowered = part.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique_parts.append(part)
    return " ".join(unique_parts)


def _english_video_focus_queries(
    specific_terms: list[str],
    focus_terms: list[str],
) -> list[str]:
    lowered_terms = {term.lower() for term in specific_terms}
    queries: list[str] = []

    def add(query: str) -> None:
        clean_query = _clean_text(query)
        if clean_query and clean_query not in queries:
            queries.append(clean_query)

    if any(
        term in lowered_terms
        for term in ("dimension", "mismatch", "valueerror", "shape")
    ):
        add("RAG embedding dimension mismatch error tutorial")
        add("vector dimension mismatch embedding error")
        add("query document embedding mismatch debug")
    if any(
        term in lowered_terms
        for term in ("query", "question", "chunks", "top-3", "top3", "retrieval")
    ):
        add("RAG query function retrieval tutorial")
        add("RAG top k chunks retrieval tutorial")
    if any("chunk" in term for term in lowered_terms):
        add("RAG chunking strategy tutorial")
        add("RAG preprocessing chunking embeddings vector databases")
    if any(
        term in lowered_terms for term in ("pdf", "loader", "splitter", "embedder")
    ) or {
        "vector",
        "store",
    }.issubset(lowered_terms):
        add("RAG PDF to vector store tutorial")
        add("RAG loader splitter embedder vector database")
        add("LangChain PDF vector database tutorial")
    if "embedding" in {term.lower() for term in focus_terms} and not queries:
        add("Embedding tutorial for RAG")
    return queries


def _is_high_confidence_video_candidate(
    video: dict, brief: dict, section: dict, outline: dict | None = None
) -> bool:
    title = _clean_text(video.get("title")).lower()
    source = _clean_text(video.get("source")).lower()
    brief_title = _clean_text(brief.get("title")).lower()
    if brief_title in title or brief_title.replace("视频", "") in title:
        return True
    specific_terms = _video_specific_brief_terms([brief], section, outline)
    if specific_terms:
        specific_keywords = _video_quality_keywords(
            _video_topic_keywords(specific_terms)
        )
        matched = _matched_video_keywords(f"{title} {source}", specific_keywords)
        if len(matched) >= len(specific_keywords) * 0.7:
            return True
    return False


def _prioritize_video_query_terms(terms: list[str]) -> list[str]:
    technical: list[str] = []
    chinese: list[str] = []
    for term in terms:
        clean_term = _clean_text(term)
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9.+_-]*", clean_term):
            technical.append(clean_term)
        elif len(clean_term) >= 2:
            chinese.append(clean_term)
    return [*technical, *chinese]


def _video_search_queries(
    video_briefs: object, section: dict, outline: dict | None = None
) -> list[str]:
    title = _clean_text(section.get("title"))
    knowledge_points = _text_items(section.get("key_knowledge_points"))
    topic_terms = _video_topic_terms(video_briefs, section, outline)
    topic_keywords = _video_topic_keywords(topic_terms)
    brief_keywords = _video_brief_anchor_terms(video_briefs)
    specific_brief_terms = _video_specific_brief_terms(video_briefs, section, outline)
    prioritized_specific_terms = _prioritize_video_query_terms(specific_brief_terms)
    knowledge_keywords = _video_topic_keywords(knowledge_points)
    domain_keywords = _video_domain_anchor_terms(section, outline)
    focus_terms = _video_focus_query_terms([*brief_keywords, *domain_keywords])
    section_keywords = _video_topic_keywords([title, *knowledge_points])
    domain_query_terms = (
        domain_keywords[:3] or section_keywords[:3] or topic_keywords[:3]
    )
    queries = [
        *_english_video_focus_queries(
            [*prioritized_specific_terms, *knowledge_keywords], focus_terms
        ),
        _compact_video_query_parts(
            [*prioritized_specific_terms[:2], *focus_terms[:2], "教程"]
        ),
        _compact_video_query_parts([*knowledge_keywords[:4], *focus_terms[:2], "教程"]),
        _compact_video_query_parts(
            [*prioritized_specific_terms[:2], *domain_query_terms[:2], "教程"]
        ),
        _compact_video_query_parts([*brief_keywords[:3], *focus_terms[:2], "教程"]),
        _compact_video_query_parts([*section_keywords[:4], *focus_terms[:2], "教程"]),
        _compact_video_query_parts(
            [*domain_query_terms[:3], *section_keywords[:2], "教程"]
        ),
        _compact_video_query_parts([*topic_keywords[:4], *focus_terms[:2], "教程"]),
        _compact_video_query_parts(
            [*prioritized_specific_terms[:2], *section_keywords[:2], "视频"]
        ),
        _compact_video_query_parts([*domain_query_terms[:2], "实战", "教程"]),
        _compact_video_query_parts([*domain_query_terms[:2], "原理", "讲解"]),
    ]
    joined_specific_terms = " ".join(prioritized_specific_terms).lower()
    if any(
        marker in joined_specific_terms
        for marker in ("环境变量", "初始化", "sdk", "api key", "apikey")
    ):
        queries.extend(
            [
                _compact_video_query_parts(
                    ["Python", "OpenAI", "环境变量配置", "SDK初始化", "教程"]
                ),
                _compact_video_query_parts(
                    ["Python", "OpenAI", "API", "环境变量", "初始化", "教程"]
                ),
            ]
        )
    if any(
        marker in joined_specific_terms
        for marker in ("asyncio", "异步", "阻塞事件循环", "阻塞")
    ):
        queries.extend(
            [
                _compact_video_query_parts(
                    ["Python", "asyncio", "阻塞事件循环", "最佳实践", "教程"]
                ),
                _compact_video_query_parts(
                    ["Python", "异步编程", "阻塞事件循环", "稳定性", "教程"]
                ),
            ]
        )
    if "Embedding" in focus_terms:
        queries.append("Embedding 原理 文本到向量 教程")
    if "文本分块" in focus_terms:
        queries.append("RAG 文本分块 chunk overlap 教程")
    if {"RAG", "Embedding"}.issubset(set(focus_terms)):
        queries.append("RAG 架构 Embedding 教程")
    joined_keywords = " ".join([title, *knowledge_points])
    if any(term in joined_keywords for term in ("检查", "验收", "质量", "运行证据")):
        queries.extend(
            [
                _compact_video_query_parts(
                    [
                        *prioritized_specific_terms[:2],
                        *section_keywords[:2],
                        "测试",
                        "验收标准",
                    ]
                ),
                _compact_video_query_parts(
                    [*domain_query_terms[:2], *section_keywords[:2], "质量检查"]
                ),
                _compact_video_query_parts(
                    [*domain_query_terms[:2], *prioritized_specific_terms[:2], "评测"]
                ),
            ]
        )
    if any(term in joined_keywords for term in ("任务", "拆解", "需求", "接口契约")):
        queries.extend(
            [
                _compact_video_query_parts(
                    [
                        *prioritized_specific_terms[:2],
                        *domain_query_terms[:2],
                        "任务拆解",
                    ]
                ),
                _compact_video_query_parts(
                    [
                        *prioritized_specific_terms[:2],
                        *domain_query_terms[:2],
                        "需求拆解",
                    ]
                ),
            ]
        )
    if any(term in joined_keywords for term in ("OpenAI", "API", "功能边界")):
        queries.extend(
            [
                _compact_video_query_parts(
                    [
                        *prioritized_specific_terms[:2],
                        *domain_query_terms[:2],
                        "API",
                        "调用",
                        "教程",
                    ]
                ),
                _compact_video_query_parts(
                    [
                        *prioritized_specific_terms[:2],
                        *domain_query_terms[:2],
                        "API",
                        "接入",
                    ]
                ),
            ]
        )
    seen: set[str] = set()
    unique_queries: list[str] = []
    for query in queries:
        clean_query = _clean_text(query)
        if not clean_query or clean_query in seen:
            continue
        seen.add(clean_query)
        unique_queries.append(clean_query)
    return unique_queries


async def _search_youtube_video_results(query: str) -> list[dict]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    try:
        async with httpx.AsyncClient(
            timeout=_VIDEO_METADATA_TIMEOUT_SECONDS, follow_redirects=True
        ) as client:
            response = await client.get(
                "https://www.youtube.com/results",
                params={"search_query": query},
                headers=headers,
            )
            response.raise_for_status()
            page_text = response.text
    except Exception as exc:
        logger.warning(
            "YouTube search request failed query=%s error_type=%s error=%s",
            query,
            type(exc).__name__,
            exc,
        )
        return []

    logger.info(
        "YouTube search response received query=%s status_code=%s",
        query,
        response.status_code,
    )
    raw_result_count = page_text.count('"videoRenderer"')
    logger.info(
        "YouTube search parse query=%s raw_result_count=%s",
        query,
        raw_result_count,
    )
    initial_data_match = re.search(
        r"var ytInitialData = (\{.*?\});</script>", page_text, re.S
    )
    if not initial_data_match:
        logger.info(
            "YouTube search parse query=%s parsed_result_count=0",
            query,
        )
        return []
    try:
        initial_data = json.loads(initial_data_match.group(1))
    except Exception as exc:
        logger.warning(
            "YouTube initial data parse failed for query=%s parsed_result_count=0 error=%s",
            query,
            exc,
        )
        return []

    search_results: list[dict] = []

    def collect(node: object) -> None:
        if len(search_results) >= 12:
            return
        if isinstance(node, dict):
            video_renderer = node.get("videoRenderer")
            if isinstance(video_renderer, dict):
                video_id = _clean_text(video_renderer.get("videoId"))
                title_runs = (video_renderer.get("title") or {}).get("runs")
                title = ""
                if isinstance(title_runs, list):
                    title = "".join(
                        _clean_text(run.get("text"))
                        for run in title_runs
                        if isinstance(run, dict)
                    )
                if video_id and title:
                    search_results.append(
                        {
                            "title": title,
                            "url": f"https://www.youtube.com/watch?v={video_id}",
                            "cover_url": "",
                            "source": "YouTube",
                        }
                    )
                    return
            for value in node.values():
                collect(value)
            return
        if isinstance(node, list):
            for item in node:
                collect(item)

    collect(initial_data)
    logger.info(
        "YouTube search parse query=%s parsed_result_count=%s",
        query,
        len(search_results),
    )
    return search_results


async def _find_verified_video_from_search(
    video_briefs: object,
    section: dict,
    outline: dict | None = None,
) -> list[dict]:
    if not isinstance(video_briefs, list):
        return []
    verified: list[dict] = []
    for brief in video_briefs:
        if not isinstance(brief, dict):
            continue
        brief_id = _clean_text(brief.get("video_id"))
        if not brief_id:
            continue
        best_video: dict | None = None
        best_score = -1
        seen_urls: set[str] = set()
        for query in _video_search_queries([brief], section, outline)[
            :_VIDEO_VERIFIED_QUERY_LIMIT
        ]:
            import app.orchestration.agents.course_resources as cr_pkg

            async def search_platform(
                platform: str,
                search: Callable[[str], Awaitable[list[dict]]],
            ) -> list[dict]:
                started_at = time.monotonic()
                results = await search(query)
                elapsed_ms = round((time.monotonic() - started_at) * 1000, 1)
                logger.info(
                    "Video search completed platform=%s section=%s query=%s "
                    "elapsed_ms=%s result_count=%s",
                    platform,
                    _clean_text(section.get("section_id")),
                    query,
                    elapsed_ms,
                    len(results),
                )
                return results

            bilibili_results, youtube_results = await asyncio.gather(
                search_platform("bilibili", cr_pkg._search_bilibili_video_results),
                search_platform("youtube", cr_pkg._search_youtube_video_results),
            )
            search_results = [*bilibili_results, *youtube_results]
            for search_result in search_results:
                url = _clean_text(search_result.get("url"))
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                video = {"brief_id": brief_id, **search_result}
                if (
                    await _normalized_video_quality_issue_async(
                        [video], [brief], section, outline
                    )
                    is None
                ):
                    score = _video_candidate_score(
                        " ".join(
                            [
                                _clean_text(video.get("title")),
                                _clean_text(video.get("source")),
                            ]
                        ),
                        section,
                        [brief],
                        outline,
                    )
                    if score > best_score:
                        best_score = score
                        best_video = video
                        if score >= 40 and _is_high_confidence_video_candidate(
                            video, brief, section, outline
                        ):
                            verified.append(best_video)
                            break
            if best_video is not None and brief_id in {
                _clean_text(v.get("brief_id")) for v in verified
            }:
                break
        if best_video is not None:
            if brief_id not in {_clean_text(v.get("brief_id")) for v in verified}:
                verified.append(best_video)
    return verified


def _video_relevance_score(text: str, topic_terms: list[str]) -> int:
    keywords = _video_topic_keywords(topic_terms)
    compact_text = re.sub(r"\s+", "", _strip_html_tags(text))
    lower_text = compact_text.lower()
    score = 0
    for keyword in keywords:
        matched = keyword in compact_text or keyword.lower() in lower_text
        if not matched:
            continue
        if len(keyword) >= 12:
            score += 5
        elif len(keyword) >= 6:
            score += 2
        else:
            score += 1
    return score


def _video_candidate_score(
    text: str,
    section: dict,
    video_briefs: object,
    outline: dict | None = None,
) -> int:
    topic_score = _video_relevance_score(
        text, _video_topic_terms(video_briefs, section, outline)
    )
    brief_score = _video_relevance_score(text, _video_brief_anchor_terms(video_briefs))
    domain_score = _video_relevance_score(
        text, _video_domain_anchor_terms(section, outline)
    )
    focus_terms = _video_focus_query_terms(_video_brief_anchor_terms(video_briefs))
    focus_score = _video_relevance_score(text, focus_terms)
    focus_match_count = sum(
        1
        for keyword in focus_terms
        if keyword in re.sub(r"\s+", "", _strip_html_tags(text))
        or keyword.lower() in re.sub(r"\s+", "", _strip_html_tags(text)).lower()
    )
    focus_bonus = focus_match_count * 5
    if focus_match_count >= 2:
        focus_bonus += 5
    return (
        topic_score + (brief_score * 2) + domain_score + (focus_score * 2) + focus_bonus
    )


def _video_input(state: OrchestrationState, outline: dict, section: dict) -> str:
    section_id = _clean_text(section.get("section_id"))
    section_markdowns = outline.get("section_markdowns")
    target_markdowns = {}
    if isinstance(section_markdowns, dict):
        section_markdown = section_markdowns.get(section_id)
        if isinstance(section_markdown, dict):
            target_markdowns[section_id] = section_markdown

    context = _resource_context(
        state,
        outline,
        section,
        include_textbook_evidence=False,
    )
    payload = {
        **context,
        "parent_section": _parent_section(outline, section),
        "target_section": section,
        "section_markdowns": target_markdowns,
    }
    instruction = (
        "请为输入小节联网搜索可直接打开的视频教程资源。\n\n"
        "必须以 section_markdowns 中的 video_briefs 为检索计划："
        "每个 brief 的 search_terms、target_paragraph_summary、purpose 都要进入查询判断。"
    )
    return _resource_query_with_prompt_budget(
        instruction,
        payload,
        phase="video",
        protected_fragments=[
            _clean_text(section.get("source_textbook_id")),
            "、".join(_text_items(section.get("source_section_ids"))),
        ],
    )


def _video_repair_input(
    state: OrchestrationState,
    outline: dict,
    section: dict,
    quality_issue: str,
    previous_videos: object,
) -> str:
    section_id = _clean_text(section.get("section_id"))
    section_markdowns = outline.get("section_markdowns")
    target_markdowns = {}
    if isinstance(section_markdowns, dict):
        section_markdown = section_markdowns.get(section_id)
        if isinstance(section_markdown, dict):
            target_markdowns[section_id] = section_markdown

    context = _resource_context(
        state,
        outline,
        section,
        include_textbook_evidence=False,
    )
    payload = {
        **context,
        "parent_section": _parent_section(outline, section),
        "target_section": section,
        "section_markdowns": target_markdowns,
        "video_quality_issue": quality_issue,
        "previous_videos": previous_videos if isinstance(previous_videos, list) else [],
    }
    instruction = (
        "上一版视频资源未通过质量检查。请只基于同一个小节和 video_briefs 重新搜索视频资源。\n\n"
        "硬性要求：每条 videos.brief_id 必须等于对应 video_briefs.video_id；"
        "title 必须包含小节主题、关键知识点或 brief 目的中的具体词；"
        "url 必须来自联网搜索结果中已经存在的视频页面 HTTP(S) 地址；"
        "禁止编造 BV 号、av 号、YouTube ID 或任何看似合法的 URL；"
        "如果使用 Bilibili，url 必须是 https://www.bilibili.com/video/BV... 形式的真实可见稿件页面，"
        "平台真实标题或简介必须体现当前小节主题；"
        "不要返回课程首页、搜索页、泛泛合集首页、短链、缺少 BV 号的 Bilibili 页面或与当前小节无关的视频。"
    )
    return _resource_query_with_prompt_budget(
        instruction,
        payload,
        phase="video",
        protected_fragments=[
            _clean_text(section.get("source_textbook_id")),
            "、".join(_text_items(section.get("source_section_ids"))),
        ],
    )


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


def _existing_video_value(
    outline: dict, section: dict, video_briefs: object
) -> dict | None:
    section_id = _clean_text(section.get("section_id"))
    section_video_links = outline.get("section_video_links")
    if not isinstance(section_video_links, dict):
        return None
    value = section_video_links.get(section_id)
    if not isinstance(value, dict):
        return None
    videos = _normalize_videos(value.get("videos"), video_briefs)
    issue = _normalized_video_quality_issue(videos, video_briefs, section, outline)
    if issue:
        return None
    existing_value = dict(value)
    existing_value["videos"] = videos
    return existing_value


async def run_section_video_search_agent(
    state: OrchestrationState,
    llm: BaseChatModel,
    explicit_args: dict | None = None,
) -> dict:
    _ = llm
    outline = state.get("course_knowledge")
    if not isinstance(outline, dict):
        return {"error": "请先生成课程大纲。", "hard_error": True}

    resource_plan = state.get("course_resource_plan")
    plan_target_ids = None
    if isinstance(resource_plan, dict):
        plan_target_ids = resource_plan.get("target_section_ids")

    if isinstance(plan_target_ids, list):
        target_section_ids = [
            section_id
            for section_id in (_clean_text(value) for value in plan_target_ids)
            if section_id
        ]
        target_sections = [
            section
            for section_id in target_section_ids
            if (section := _section_by_id(outline, section_id)) is not None
        ]
    else:
        args = _tool_args(state, explicit_args)
        section_id = _clean_text(args.get("section_id", ""))
        scope = _clean_text(args.get("scope", "")) or "default_first_chapter"
        try:
            target_sections = _target_sections_for_scope(outline, section_id, scope)
        except ValueError as exc:
            return {"error": str(exc), "hard_error": True}
        target_section_ids = [
            _clean_text(section.get("section_id")) for section in target_sections
        ]

    try:
        for section in target_sections:
            _resource_context(state, outline, section)
    except ValueError as exc:
        return {"error": str(exc), "hard_error": True}

    section_markdowns = outline.get("section_markdowns")

    async def generate_video_links(section: dict) -> tuple[str, dict]:
        target_section_id = _clean_text(section.get("section_id"))
        if not target_section_id:
            return "", {}
        section_markdown = {}
        if isinstance(section_markdowns, dict):
            value = section_markdowns.get(target_section_id)
            if isinstance(value, dict):
                section_markdown = value
        video_briefs = section_markdown.get("video_briefs")
        existing_video = _existing_video_value(outline, section, video_briefs)
        if existing_video is not None:
            return target_section_id, existing_video

        query = " | ".join(_video_search_queries(video_briefs, section, outline)[:3])
        videos: list[dict] = []
        quality_issue = "视频资源为空或未绑定 brief。"
        import app.orchestration.agents.course_resources as cr_pkg

        async def search_verified_videos() -> tuple[list[dict], str]:
            current_videos: list[dict] = []
            current_quality_issue = quality_issue
            for _verified_attempt in range(2):
                try:
                    verified_videos = await cr_pkg._find_verified_video_from_search(
                        video_briefs, section, outline
                    )
                except Exception as exc:
                    logger.warning(
                        "Verified video search failed for section %s: %s",
                        target_section_id,
                        exc,
                    )
                    continue
                if not verified_videos:
                    continue
                current_videos = _normalize_videos(verified_videos, video_briefs)
                current_quality_issue = await _normalized_video_quality_issue_async(
                    current_videos, video_briefs, section, outline
                )
                if not current_quality_issue:
                    break
            return current_videos, current_quality_issue

        started_at = time.monotonic()
        try:
            videos, quality_issue = await asyncio.wait_for(
                search_verified_videos(),
                timeout=cr_pkg._VIDEO_SECTION_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            elapsed_ms = round((time.monotonic() - started_at) * 1000, 1)
            logger.warning(
                "Video search timed out for section %s after %sms",
                target_section_id,
                elapsed_ms,
            )
            quality_issue = "视频检索超时。"

        if quality_issue:
            logger.warning(
                "Video quality issue for section %s: %s",
                target_section_id,
                quality_issue,
            )
            return target_section_id, {
                "user_id": state.get("user_id", ""),
                "section_id": target_section_id,
                "parent_section_id": section.get("parent_section_id"),
                "title": _section_title(outline, section),
                "query": query,
                "status": "unavailable",
                "failure_reason": f"未找到合格视频：{quality_issue}",
                "videos": [],
                "generated_at": _now_iso(),
            }

        return target_section_id, {
            "user_id": state.get("user_id", ""),
            "section_id": target_section_id,
            "parent_section_id": section.get("parent_section_id"),
            "title": _section_title(outline, section),
            "query": query,
            "status": "available",
            "failure_reason": "",
            "videos": videos,
            "generated_at": _now_iso(),
        }

    section_video_links: dict[str, dict] = {}
    _sem = asyncio.Semaphore(_SECTION_CONCURRENCY_LIMIT)

    async def _limited_video(section: dict) -> tuple[str, dict]:
        async with _sem:
            return await generate_video_links(section)

    video_results = await asyncio.gather(
        *(_limited_video(section) for section in target_sections)
    )
    for target_section_id, video_value in video_results:
        if not target_section_id:
            continue
        if _clean_text(video_value.get("error")):
            return {
                "error": "课程资源生成失败：视频资源未生成，请稍后重试。",
                "hard_error": True,
            }
        section_video_links[target_section_id] = video_value

    updated_outline = _merge_course_resource_data(
        outline, "section_video_links", section_video_links
    )
    try:
        _persist_outline(str(state.get("user_id", "")), updated_outline)
    except Exception as exc:
        logger.error(
            "Failed to persist course resources for user %s: %s",
            state.get("user_id", ""),
            exc,
        )
        return {"error": "课程资源保存失败，请稍后重试。", "hard_error": True}

    updated_plan = dict(resource_plan) if isinstance(resource_plan, dict) else {}
    updated_plan["target_section_ids"] = target_section_ids
    updated_plan["video_section_ids"] = list(section_video_links.keys())

    return {
        "user_id": state.get("user_id", ""),
        "course_knowledge": updated_outline,
        "course_resource_plan": updated_plan,
    }
