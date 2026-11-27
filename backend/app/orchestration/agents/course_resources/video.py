# ruff: noqa: C901, E501
from __future__ import annotations

import asyncio
import json
import logging
import re
from urllib.parse import quote

from app.orchestration.agents.course_resources.aliyun_bilibili_search import (
    _search_aliyun_bilibili_sources,
)
from app.orchestration.agents.course_resources.bilibili import (
    _bilibili_bvid_from_url,
    _verify_bilibili_video_metadata,
)
from app.orchestration.agents.course_resources.common import (
    _clean_text,
    _parent_section,
    _text_items,
)

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


async def _find_verified_video_from_search(
    video_briefs: object,
    section: dict,
    outline: dict | None = None,
) -> list[dict]:
    if not isinstance(video_briefs, list):
        return []

    parent = _parent_section(outline or {}, section)

    def section_summary(value: dict | None) -> dict:
        if not isinstance(value, dict):
            return {}
        return {
            "title": _clean_text(value.get("title")),
            "description": _clean_text(value.get("description")),
            "key_knowledge_points": _text_items(value.get("key_knowledge_points")),
        }

    async def find_for_brief(brief: object) -> dict | None:
        if not isinstance(brief, dict):
            return None
        brief_id = _clean_text(brief.get("video_id"))
        if not brief_id:
            return None

        section_scope = json.dumps(
            {
                "course_name": _clean_text((outline or {}).get("course_name")),
                "parent_section": section_summary(parent),
                "section": section_summary(section),
                "video_brief": {
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
                },
            },
            ensure_ascii=False,
        )
        search_queries = _video_search_queries([brief], section, outline)
        if not search_queries:
            logger.warning(
                "DashScope Bilibili search skipped section=%s brief=%s "
                "reason=no_search_query",
                _clean_text(section.get("section_id")),
                brief_id,
            )
            return None
        search_query = search_queries[0]
        sources = await _search_aliyun_bilibili_sources(
            search_query,
            section_scope,
        )
        logger.info(
            "DashScope Bilibili search resolved section=%s brief=%s source_count=%s",
            _clean_text(section.get("section_id")),
            brief_id,
            len(sources),
        )

        async def validate_source(source: object) -> dict | None:
            source_url = _clean_text(getattr(source, "url", ""))
            url = source_url.removesuffix("/")
            if not _bilibili_bvid_from_url(url):
                return None
            metadata = await _verify_bilibili_video_metadata(url)
            if metadata.get("status") != "ok":
                return None
            title = _clean_text(metadata.get("title"))
            if not title:
                return None
            return {
                "brief_id": brief_id,
                "title": title,
                "url": url,
                "source": "Bilibili",
            }

        validated = await asyncio.gather(
            *(validate_source(source) for source in sources)
        )
        return next((video for video in validated if video is not None), None)

    results = await asyncio.gather(*(find_for_brief(brief) for brief in video_briefs))
    return [video for video in results if video is not None]


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
