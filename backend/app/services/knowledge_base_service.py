from __future__ import annotations

import logging
import os
import re
from collections.abc import Generator
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from hashlib import sha1
from json import loads
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from langchain_openai import OpenAIEmbeddings
from sqlalchemy import func, or_, text
from sqlmodel import Session, select

from app.core.observability import get_request_id
from app.models import (
    KnowledgeBaseIngestionJob,
    KnowledgeGap,
    KnowledgeGapFollow,
    KnowledgeGapNotice,
    KnowledgeSource,
    Textbook,
    TextbookExtensionResource,
    TextbookSectionContent,
)
from app.orchestration.llm import get_search_worker_llm, get_translation_llm
from app.schemas import (
    KnowledgeBaseAgentGapHit,
    KnowledgeBaseAgentResponse,
    KnowledgeBaseAgentTextbookHit,
    KnowledgeBaseSourceResult,
)
from app.services.document_parser_service import (
    DocumentParseError,
    parse_textbook_source_to_sections,
)

logger = logging.getLogger(__name__)

_ADMITTED_SOURCE_VALUES = {
    "status": "enabled",
    "download_status": "verified",
    "parse_status": "supported",
    "license_review_status": "approved",
    "human_review_status": "reviewed",
}
_EVIDENCE_SECTION_LIMIT = 7
_EVIDENCE_CHAR_LIMIT = 8000
_VISIBLE_EXTENSION_RESOURCE_STATUS = "published"
_RESOLVABLE_GAP_STATUSES = ("open", "material_searching", "material_found")
_NOTICE_TYPE = "knowledge_gap_resolved"
_NOTICE_ACTION = "regenerate_learning_path_intake"
_SOURCE_RESULT_LIMIT = 5
_SOURCE_TYPES = {"pdf", "html"}
_TRANSLATION_CHUNK_CHAR_LIMIT = int(
    os.getenv("TEXTBOOK_TRANSLATION_CHUNK_CHARS", "1800")
)
_TRANSLATION_CHUNK_MAX_ATTEMPTS = int(
    os.getenv("TEXTBOOK_TRANSLATION_CHUNK_MAX_ATTEMPTS", "2")
)
_TRANSLATION_SECTION_MAX_WORKERS = int(
    os.getenv("TEXTBOOK_TRANSLATION_SECTION_MAX_WORKERS", "6")
)
_TRANSLATION_JOB_TIMEOUT_SECONDS = int(
    os.getenv("TEXTBOOK_TRANSLATION_JOB_TIMEOUT_SECONDS", "900")
)
_OPEN_TEXTBOOK_SOURCE_ROWS: tuple[dict[str, object], ...] = (
    {
        "topic_keywords": (
            "数据结构",
            "data structures",
            "data structure",
            "算法与数据结构",
            "algorithms and data structures",
        ),
        "title": "Open Data Structures (Python Edition)",
        "original_title": "Open Data Structures",
        "language": "en",
        "source_url": "https://opendatastructures.org/ods-python/",
        "source_type": "html",
        "provider_name": "Open Data Structures",
        "description": (
            "Open textbook covering arrays, linked lists, trees, hashing, "
            "graphs, and sorting."
        ),
        "tags": ["数据结构", "算法", "Python"],
        "parseability_score": 100,
        "parseability_reason": (
            "HTML textbook pages are accessible and can be converted by MarkItDown."
        ),
        "topic_summary": "覆盖数据结构课程的核心章节和小节正文。",
    },
    {
        "topic_keywords": (
            "数据结构",
            "data structures",
            "data structure",
            "算法与数据结构",
            "algorithms and data structures",
        ),
        "title": "Open Data Structures (Java Edition)",
        "original_title": "Open Data Structures",
        "language": "en",
        "source_url": "https://opendatastructures.org/ods-java/",
        "source_type": "html",
        "provider_name": "Open Data Structures",
        "description": (
            "Open textbook covering data structures with Java-oriented examples."
        ),
        "tags": ["数据结构", "算法", "Java"],
        "parseability_score": 98,
        "parseability_reason": (
            "HTML textbook pages are accessible and can be converted by MarkItDown."
        ),
        "topic_summary": "覆盖数据结构课程的核心章节和小节正文。",
    },
    {
        "topic_keywords": (
            "数据结构",
            "data structures",
            "data structure",
            "算法与数据结构",
            "algorithms and data structures",
        ),
        "title": "Open Data Structures (C++ Edition)",
        "original_title": "Open Data Structures",
        "language": "en",
        "source_url": "https://opendatastructures.org/ods-cpp/",
        "source_type": "html",
        "provider_name": "Open Data Structures",
        "description": (
            "Open textbook covering data structures with C++-oriented examples."
        ),
        "tags": ["数据结构", "算法", "C++"],
        "parseability_score": 96,
        "parseability_reason": (
            "HTML textbook pages are accessible and can be converted by MarkItDown."
        ),
        "topic_summary": "覆盖数据结构课程的核心章节和小节正文。",
    },
    {
        "topic_keywords": (
            "数据结构",
            "data structures",
            "data structure",
            "算法与数据结构",
            "algorithms and data structures",
        ),
        "title": "An Open Guide to Data Structures and Algorithms",
        "original_title": "An Open Guide to Data Structures and Algorithms",
        "language": "en",
        "source_url": (
            "https://pressbooks.palni.org/anopenguidetodatastructuresandalgorithms/"
        ),
        "source_type": "html",
        "provider_name": "PALNI Pressbooks",
        "description": (
            "Open Pressbooks textbook covering algorithms, lists, trees, hashing, "
            "queues, graphs, and dynamic programming."
        ),
        "tags": ["数据结构", "算法", "Open Textbook"],
        "parseability_score": 94,
        "parseability_reason": (
            "HTML textbook chapters are accessible and can be converted by MarkItDown."
        ),
        "topic_summary": "覆盖算法分析、线性结构、树、散列、图等内容。",
    },
    {
        "topic_keywords": (
            "数据结构",
            "data structures",
            "data structure",
            "算法与数据结构",
            "algorithms and data structures",
        ),
        "title": "OpenDSA Data Structures and Algorithms Modules Collection",
        "original_title": "OpenDSA Data Structures and Algorithms Modules Collection",
        "language": "en",
        "source_url": "https://opendsa-server.cs.vt.edu/ODSA/Books/Everything/html/",
        "source_type": "html",
        "provider_name": "OpenDSA",
        "description": (
            "OpenDSA HTML modules covering data structures and algorithms topics."
        ),
        "tags": ["数据结构", "算法", "OpenDSA"],
        "parseability_score": 90,
        "parseability_reason": (
            "HTML module pages are accessible and can be converted by MarkItDown."
        ),
        "topic_summary": "覆盖数据结构与算法模块，适合补充检索和解析。",
    },
    {
        "topic_keywords": (
            "agent开发",
            "agent 开发",
            "智能体开发",
            "ai agent",
            "ai agents",
            "computational agents",
            "artificial intelligence agents",
        ),
        "title": "Artificial Intelligence: Foundations of Computational Agents",
        "original_title": (
            "Artificial Intelligence: Foundations of Computational Agents"
        ),
        "language": "en",
        "source_url": "https://artint.info/3e/html/ArtInt3e.html",
        "source_type": "html",
        "provider_name": "Cambridge University Press",
        "description": (
            "Open textbook covering computational agents, reasoning, planning, "
            "learning, and agent foundations."
        ),
        "tags": ["agent开发", "AI Agent", "人工智能"],
        "parseability_score": 100,
        "parseability_reason": (
            "HTML textbook pages are accessible and can be converted by MarkItDown."
        ),
        "topic_summary": "覆盖智能体基础、知识表示、推理、规划与学习。",
    },
)
_PLACEHOLDER_HOSTS = {
    "example.com",
    "example.org",
    "example.net",
    "example.test",
    "localhost",
    "127.0.0.1",
}
_TEXTBOOK_CONTENT_TYPES = ("application/pdf", "text/html")
_NON_TEXTBOOK_SOURCE_MARKERS = (
    "/docs/",
    "/posts/",
    "/short-courses/",
    "docs.",
    "github.com/",
    "blog",
    "short-courses",
    "documentation",
    "api reference",
    "developer guide",
    "development guide",
    "user guide",
    "开发指南",
    "用户指南",
    "官方开发指南",
    "博客",
    "课程介绍页",
    "仓库",
    "文档",
)


def create_knowledge_source(
    session: Session, source: KnowledgeSource
) -> KnowledgeSource:
    session.add(source)
    session.commit()
    session.refresh(source)
    return source


def list_knowledge_sources(session: Session) -> list[KnowledgeSource]:
    stmt = select(KnowledgeSource).order_by(KnowledgeSource.source_id)
    return list(session.exec(stmt).all())


def update_knowledge_source(
    session: Session, source_id: str, **updates: object
) -> KnowledgeSource:
    source = session.get(KnowledgeSource, source_id)
    if source is None:
        raise ValueError("知识来源不存在。")
    for key in updates:
        if key not in KnowledgeSource.model_fields:
            raise ValueError(f"知识来源字段不存在：{key}")
    for key, value in updates.items():
        setattr(source, key, value)
    session.add(source)
    session.commit()
    session.refresh(source)
    return source


def delete_knowledge_source(session: Session, source_id: str) -> bool:
    source = session.get(KnowledgeSource, source_id)
    if source is None:
        return False
    session.delete(source)
    session.commit()
    return True


def is_source_admitted_for_primary_textbook(source: KnowledgeSource) -> bool:
    return all(
        getattr(source, key) == value for key, value in _ADMITTED_SOURCE_VALUES.items()
    )


def list_admitted_knowledge_sources(session: Session) -> list[KnowledgeSource]:
    stmt = (
        select(KnowledgeSource)
        .where(
            KnowledgeSource.status == "enabled",
            KnowledgeSource.download_status == "verified",
            KnowledgeSource.parse_status == "supported",
            KnowledgeSource.license_review_status == "approved",
            KnowledgeSource.human_review_status == "reviewed",
        )
        .order_by(KnowledgeSource.source_id)
    )
    return list(session.exec(stmt).all())


def require_student_visible_textbooks(
    session: Session, value: object
) -> list[Textbook]:
    textbook_ids = _source_textbook_ids(value)
    textbooks: list[Textbook] = []
    for textbook_id in textbook_ids:
        textbook = session.get(Textbook, textbook_id)
        if textbook is None:
            raise ValueError("教材不存在。")
        if textbook.student_availability_status != "published":
            raise ValueError("教材未发布。")
        textbooks.append(textbook)
    return textbooks


def upsert_structured_textbook(
    session: Session,
    textbook: Textbook,
    sections: list[TextbookSectionContent],
) -> Textbook:
    if textbook.student_availability_status == "published":
        raise ValueError("结构化入库不能直接发布教材。")

    stored_textbook = session.get(Textbook, textbook.textbook_id)
    supplied_section_ids = [section.section_id for section in sections]
    _reject_duplicate_section_ids(supplied_section_ids)

    incoming_outline_section_ids = {
        row["section_id"] for row in _outline_summary(textbook.outline)
    }
    if stored_textbook is not None:
        _reject_published_structured_overwrite(stored_textbook)
        stored_outline_section_ids = {
            row["section_id"] for row in _outline_summary(stored_textbook.outline)
        }
        if any(
            section_id not in stored_outline_section_ids
            for section_id in supplied_section_ids
        ):
            raise ValueError("教材小节不存在。")
    if any(
        section_id not in incoming_outline_section_ids
        for section_id in supplied_section_ids
    ):
        raise ValueError("教材小节不存在。")

    if stored_textbook is None:
        stored_textbook = textbook
    else:
        for key, value in textbook.model_dump().items():
            setattr(stored_textbook, key, value)
    session.add(stored_textbook)

    existing_sections = session.exec(
        select(TextbookSectionContent).where(
            TextbookSectionContent.textbook_id == textbook.textbook_id
        )
    ).all()
    for section in existing_sections:
        session.delete(section)
    session.flush()

    for section in sections:
        section.textbook_id = textbook.textbook_id
        _ensure_section_original_content(section)
        content_length = len(section.content_zh or "")
        if (
            section.content_char_count == 0
            or section.content_char_count != content_length
        ):
            section.content_char_count = content_length
        session.add(section)

    session.commit()
    session.refresh(stored_textbook)
    return stored_textbook


def _ensure_section_original_content(section: TextbookSectionContent) -> None:
    if not section.content_original:
        section.content_original = section.content_zh


def create_knowledge_base_ingestion_job(
    session: Session,
    textbook_id: str,
) -> KnowledgeBaseIngestionJob:
    textbook = session.get(Textbook, textbook_id)
    if textbook is None:
        raise ValueError("教材不存在。")
    if textbook.student_availability_status != "draft":
        raise ValueError("只有草稿教材可以创建整理任务。")

    job = KnowledgeBaseIngestionJob(
        job_id=_new_id("job"),
        textbook_id=textbook_id,
        job_type="agent_organize",
        status="queued",
        request_id=get_request_id(),
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def confirm_textbook_source_result(
    session: Session,
    source_result: KnowledgeBaseSourceResult,
) -> tuple[Textbook, KnowledgeBaseIngestionJob]:
    sources = list_admitted_knowledge_sources(session)
    if not sources:
        raise ValueError("缺少已准入教材来源。")
    _ensure_source_result_parseable(source_result, max_linked_pages=8)

    source = sources[0]
    textbook = Textbook(
        textbook_id=_new_id("textbook"),
        source_id=source.source_id,
        title=source_result.title,
        original_title=source_result.original_title,
        language=source_result.language,
        translated_language="zh"
        if source_result.language == "en"
        else source_result.language,
        description=source_result.description,
        tags=source_result.tags,
        download_url=source_result.source_url,
        file_asset_url=source_result.source_url,
        outline={},
        ingestion_status="not_started",
        outline_review_status="unreviewed",
        student_availability_status="draft",
    )
    session.add(textbook)
    session.commit()
    session.refresh(textbook)
    job = create_knowledge_base_ingestion_job(session, textbook.textbook_id)
    return textbook, job


def create_uploaded_textbook(
    session: Session,
    *,
    title: str,
    language: str,
    description: str,
    tags: list[str],
    file_name: str,
    file_bytes: bytes,
) -> tuple[Textbook, KnowledgeBaseIngestionJob]:
    sources = list_admitted_knowledge_sources(session)
    if not sources:
        raise ValueError("缺少已准入教材来源。")
    cleaned_file_name = os.path.basename(file_name.strip() or "textbook.pdf")
    if not cleaned_file_name.lower().endswith((".pdf", ".docx")):
        raise ValueError("只支持 PDF 或 DOCX 教材文件。")

    upload_dir = os.getenv("KNOWLEDGE_BASE_UPLOAD_DIR") or os.path.join(
        os.getcwd(),
        ".codex-artifacts",
        "knowledge-base-uploads",
    )
    os.makedirs(upload_dir, exist_ok=True)
    textbook_id = _new_id("textbook")
    stored_path = os.path.join(upload_dir, f"{textbook_id}-{cleaned_file_name}")
    with open(stored_path, "wb") as file_obj:
        file_obj.write(file_bytes)

    source = sources[0]
    textbook = Textbook(
        textbook_id=textbook_id,
        source_id=source.source_id,
        title=title,
        original_title=title,
        language=language,
        translated_language="zh" if language == "en" else language,
        description=description,
        tags=tags,
        download_url=stored_path,
        file_asset_url=stored_path,
        outline={},
        ingestion_status="not_started",
        outline_review_status="unreviewed",
        student_availability_status="draft",
    )
    session.add(textbook)
    session.commit()
    session.refresh(textbook)
    job = create_knowledge_base_ingestion_job(session, textbook.textbook_id)
    return textbook, job


def start_knowledge_base_ingestion_job(
    session: Session,
    job_id: str,
) -> KnowledgeBaseIngestionJob:
    job = _get_ingestion_job(session, job_id)
    if job.status != "queued":
        raise ValueError("只有 queued 整理任务可以开始。")

    textbook = _get_ingestion_job_textbook(session, job)
    now = datetime.now(timezone.utc)
    job.status = "running"
    job.started_at = now
    job.finished_at = None
    job.updated_at = now
    job.error_message = ""
    textbook.ingestion_status = "processing"
    textbook.ingestion_error_message = ""
    session.add(job)
    session.add(textbook)
    session.commit()
    session.refresh(job)
    return job


def complete_knowledge_base_ingestion_job(
    session: Session,
    job_id: str,
) -> KnowledgeBaseIngestionJob:
    job = _get_ingestion_job(session, job_id)
    if job.status != "running":
        raise ValueError("只有 running 整理任务可以完成。")

    textbook = _get_ingestion_job_textbook(session, job)
    now = datetime.now(timezone.utc)
    job.status = "completed"
    job.finished_at = now
    job.lease_expires_at = None
    job.updated_at = now
    job.error_message = ""
    textbook.ingestion_status = "ready_for_outline_review"
    textbook.ingestion_error_message = ""
    session.add(job)
    session.add(textbook)
    session.commit()
    session.refresh(job)
    return job


def fail_knowledge_base_ingestion_job(
    session: Session,
    job_id: str,
    error_message: str,
) -> KnowledgeBaseIngestionJob:
    job = _get_ingestion_job(session, job_id)
    if job.status != "running":
        raise ValueError("只有 running 整理任务可以失败。")

    textbook = _get_ingestion_job_textbook(session, job)
    message = error_message.strip() or "教材整理失败。"
    now = datetime.now(timezone.utc)
    job.status = "failed"
    job.finished_at = now
    job.lease_expires_at = None
    job.updated_at = now
    job.error_message = message
    textbook.ingestion_status = "failed"
    textbook.ingestion_error_message = message
    session.add(job)
    session.add(textbook)
    session.commit()
    session.refresh(job)
    return job


def translate_section_content_to_zh(content: str, source_language: str = "") -> str:
    """Translate parsed English textbook text section by section.

    MarkItDown remains the only source of textbook structure and source text.
    The model is only allowed to translate one parsed section into Chinese.
    """
    original_content = content.strip()
    if not _textbook_language_requires_translation(source_language):
        return original_content
    if _contains_cjk_text(original_content):
        return original_content

    translated_chunks: list[str] = []
    for chunk in _split_translation_chunks(
        original_content,
        _TRANSLATION_CHUNK_CHAR_LIMIT,
    ):
        translated = _translate_text_chunk_to_zh(chunk)
        if not translated or not _contains_cjk_text(translated):
            return original_content
        translated_chunks.append(translated)
    return "\n\n".join(translated_chunks).strip()


def _translate_text_chunk_to_zh(content: str) -> str:
    prompt = (
        "请把下面教材小节原文片段翻译成简体中文。"
        "必须忠实保留原文含义、代码、公式、列表和 Markdown 结构；"
        "不得新增原文没有的知识点，不得写摘要，不得解释翻译过程。"
        "\n\n教材小节原文片段：\n"
        f"{content}"
    )
    translated = ""
    for attempt_index in range(max(1, _TRANSLATION_CHUNK_MAX_ATTEMPTS)):
        try:
            response = get_translation_llm().invoke(prompt)
            translated = getattr(response, "content", "")
            break
        except Exception as exc:
            logger.warning(
                "Textbook section translation failed on attempt %s: %s",
                attempt_index + 1,
                exc,
            )
    else:
        return ""
    if not isinstance(translated, str):
        return ""
    translated = translated.strip()
    if not translated or not _contains_cjk_text(translated):
        return ""
    return translated


def _split_translation_chunks(content: str, chunk_char_limit: int) -> list[str]:
    if chunk_char_limit <= 0 or len(content) <= chunk_char_limit:
        return [content]

    chunks: list[str] = []
    current_parts: list[str] = []
    current_length = 0
    for raw_block in content.split("\n\n"):
        block = raw_block.strip()
        if not block:
            continue
        if len(block) > chunk_char_limit:
            if current_parts:
                chunks.append("\n\n".join(current_parts))
                current_parts = []
                current_length = 0
            chunks.extend(
                block[index : index + chunk_char_limit].strip()
                for index in range(0, len(block), chunk_char_limit)
                if block[index : index + chunk_char_limit].strip()
            )
            continue
        next_length = current_length + len(block) + (2 if current_parts else 0)
        if current_parts and next_length > chunk_char_limit:
            chunks.append("\n\n".join(current_parts))
            current_parts = [block]
            current_length = len(block)
            continue
        current_parts.append(block)
        current_length = next_length
    if current_parts:
        chunks.append("\n\n".join(current_parts))
    return chunks or [content]


def run_textbook_source_ingestion(
    session: Session,
    job_id: str,
    *,
    start_job: bool = True,
) -> KnowledgeBaseIngestionJob:
    job = (
        start_knowledge_base_ingestion_job(session, job_id)
        if start_job
        else _get_ingestion_job(session, job_id)
    )
    if job.status != "running":
        raise ValueError("只有 running 整理任务可以执行。")
    textbook = _get_ingestion_job_textbook(session, job)
    try:
        outline, sections = parse_textbook_source_to_sections(
            textbook.download_url,
            textbook.language,
        )
        outline_sections = _outline_summary(outline)
        if not outline_sections:
            raise ValueError("教材解析失败：未提取到可校对大纲。")
        missing_section_ids = [
            section["section_id"]
            for section in outline_sections
            if not sections.get(section["section_id"], "").strip()
        ]
        if missing_section_ids:
            raise ValueError("教材解析失败：未切分出完整小节正文。")

        textbook.outline = outline
        session.add(textbook)

        existing_sections = session.exec(
            select(TextbookSectionContent).where(
                TextbookSectionContent.textbook_id == textbook.textbook_id
            )
        ).all()
        for section in existing_sections:
            session.delete(section)
        session.flush()

        content_by_section_id = _section_content_by_section_id_for_ingestion(
            outline_sections,
            sections,
        )
        prepared_sections: list[dict[str, str | int]] = []
        for index, section in enumerate(outline_sections, start=1):
            original_content = sections.get(section["section_id"], "")
            content_text = content_by_section_id.get(section["section_id"], "")
            prepared_sections.append(
                {
                    "order_index": index,
                    "section_id": section["section_id"],
                    "title": section["title"],
                    "content_original": original_content.strip(),
                    "content_zh": content_text,
                    "content_char_count": len(content_text),
                }
            )

        for section in prepared_sections:
            session.add(
                TextbookSectionContent(
                    section_content_id=_new_id("section"),
                    textbook_id=textbook.textbook_id,
                    section_id=str(section["section_id"]),
                    order_index=int(section["order_index"]),
                    title=str(section["title"]),
                    original_title=str(section["title"]),
                    content_original=str(section["content_original"]),
                    content_zh=str(section["content_zh"]),
                    content_char_count=int(section["content_char_count"]),
                )
            )

        session.commit()
        return complete_knowledge_base_ingestion_job(session, job_id)
    except Exception as exc:
        session.rollback()
        return fail_knowledge_base_ingestion_job(session, job_id, str(exc))


def run_claimed_textbook_source_ingestion(
    session: Session,
    job: KnowledgeBaseIngestionJob,
) -> KnowledgeBaseIngestionJob:
    if job.status != "running":
        raise ValueError("只有 running 整理任务可以执行。")
    return run_textbook_source_ingestion(session, job.job_id, start_job=False)


def _section_content_by_section_id_for_ingestion(
    outline_sections: list[dict[str, str]],
    sections: dict[str, str],
) -> dict[str, str]:
    return {
        section["section_id"]: sections.get(section["section_id"], "").strip()
        for section in outline_sections
    }


def _translate_english_sections_concurrently(
    sections_to_translate: list[tuple[str, str]],
    source_language: str,
) -> dict[str, str]:
    max_workers = max(
        1,
        min(_TRANSLATION_SECTION_MAX_WORKERS, len(sections_to_translate)),
    )
    timeout_seconds = max(1, _TRANSLATION_JOB_TIMEOUT_SECONDS)
    executor = ThreadPoolExecutor(max_workers=max_workers)
    future_by_section_id = {
        executor.submit(
            translate_section_content_to_zh,
            original_content,
            source_language,
        ): section_id
        for section_id, original_content in sections_to_translate
    }
    pending = set(future_by_section_id)
    translated_by_section_id: dict[str, str] = {}
    deadline = monotonic() + timeout_seconds
    try:
        while pending:
            remaining = deadline - monotonic()
            if remaining <= 0:
                for future in pending:
                    future.cancel()
                raise TimeoutError("英文教材中文译写超时。")
            done, pending = wait(
                pending,
                timeout=remaining,
                return_when=FIRST_COMPLETED,
            )
            if not done:
                for future in pending:
                    future.cancel()
                raise TimeoutError("英文教材中文译写超时。")
            for future in done:
                section_id = future_by_section_id[future]
                translated = future.result()
                if not _contains_cjk_text(translated):
                    raise ValueError("英文教材缺少中文译写正文。")
                translated_by_section_id[section_id] = translated
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    return translated_by_section_id


def run_textbook_source_ingestion_for_textbook(
    session: Session,
    textbook_id: str,
) -> KnowledgeBaseIngestionJob:
    textbook = session.get(Textbook, textbook_id)
    if textbook is None:
        raise ValueError("教材不存在。")
    running_job = session.exec(
        select(KnowledgeBaseIngestionJob)
        .where(
            KnowledgeBaseIngestionJob.textbook_id == textbook_id,
            KnowledgeBaseIngestionJob.job_type == "agent_organize",
            KnowledgeBaseIngestionJob.status == "running",
        )
        .order_by(KnowledgeBaseIngestionJob.created_at.desc())
    ).first()
    if running_job is not None:
        raise ValueError("教材整理任务正在运行。")

    queued_job = session.exec(
        select(KnowledgeBaseIngestionJob)
        .where(
            KnowledgeBaseIngestionJob.textbook_id == textbook_id,
            KnowledgeBaseIngestionJob.job_type == "agent_organize",
            KnowledgeBaseIngestionJob.status == "queued",
        )
        .order_by(KnowledgeBaseIngestionJob.created_at.desc())
    ).first()
    job = queued_job or create_knowledge_base_ingestion_job(session, textbook_id)
    return run_textbook_source_ingestion(session, job.job_id)


def queue_textbook_source_ingestion_for_textbook(
    session: Session,
    textbook_id: str,
) -> KnowledgeBaseIngestionJob:
    textbook = session.get(Textbook, textbook_id)
    if textbook is None:
        raise ValueError("教材不存在。")
    active_job = session.exec(
        select(KnowledgeBaseIngestionJob)
        .where(
            KnowledgeBaseIngestionJob.textbook_id == textbook_id,
            KnowledgeBaseIngestionJob.job_type == "agent_organize",
            KnowledgeBaseIngestionJob.status.in_(["queued", "running"]),
        )
        .order_by(KnowledgeBaseIngestionJob.created_at.desc())
    ).first()
    return active_job or create_knowledge_base_ingestion_job(session, textbook_id)


def publish_textbook(session: Session, textbook_id: str) -> Textbook:
    textbook = session.get(Textbook, textbook_id)
    if textbook is None:
        raise ValueError("教材不存在。")

    source = session.get(KnowledgeSource, textbook.source_id)
    if source is None or not is_source_admitted_for_primary_textbook(source):
        raise ValueError("教材来源未通过准入校验。")
    if not _outline_has_named_section(textbook.outline):
        raise ValueError("教材缺少中文目录。")
    content_rows = _textbook_content_rows(session, textbook_id)
    if not _textbook_has_non_empty_content(content_rows):
        raise ValueError("教材缺少中文正文。")
    if not _textbook_has_complete_content(content_rows, textbook.outline):
        raise ValueError("教材缺少完整中文正文。")
    if _textbook_requires_zh_translation(textbook) and not _textbook_has_zh_content(
        content_rows,
        textbook.outline,
    ):
        raise ValueError("英文教材缺少中文译写正文。")

    try:
        textbook.outline_review_status = "approved"
        textbook.student_availability_status = "published"
        textbook.published_at = datetime.now(timezone.utc)
        session.add(textbook)
        create_gap_resolved_notices_for_textbook(session, textbook_id, commit=False)
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(textbook)
    return textbook


def get_published_textbook_context_for_topic(
    session: Session, topic: str, student_goal_summary: str = ""
) -> dict:
    matched = hybrid_search_textbooks(session, topic, limit=15)
    matched_by_id = {textbook.textbook_id: textbook for textbook in matched}
    published_textbooks = session.exec(
        select(Textbook)
        .where(Textbook.student_availability_status == "published")
        .order_by(Textbook.textbook_id)
    ).all()
    for textbook in published_textbooks:
        if textbook.textbook_id in matched_by_id:
            continue
        if _textbook_covers_topic(textbook, topic):
            matched.append(textbook)
            matched_by_id[textbook.textbook_id] = textbook

    if matched:
        return {
            "textbooks": [_textbook_context_row(textbook) for textbook in matched],
            "gap_id": None,
        }

    gap = create_or_update_knowledge_gap(session, topic, student_goal_summary)
    return {"textbooks": [], "gap_id": gap.gap_id}


def get_textbook_evidence_pack(
    session: Session, textbook_id: str, section_ids: list[str]
) -> dict:
    textbook = session.get(Textbook, textbook_id)
    if textbook is None:
        raise ValueError("教材不存在。")
    if textbook.student_availability_status != "published":
        raise ValueError("教材未发布。")
    if len(section_ids) > _EVIDENCE_SECTION_LIMIT:
        raise ValueError("证据包最多包含 7 个小节。")

    unique_section_ids = list(dict.fromkeys(section_ids))
    if not unique_section_ids:
        create_or_update_knowledge_gap(session, textbook_id)
        raise ValueError("证据包为空。")

    rows = session.exec(
        select(TextbookSectionContent).where(
            TextbookSectionContent.textbook_id == textbook_id,
            TextbookSectionContent.section_id.in_(unique_section_ids),
        )
    ).all()
    if {row.section_id for row in rows} != set(unique_section_ids):
        raise ValueError("教材小节不存在。")

    ordered_sections = sorted(rows, key=lambda row: row.order_index)
    order_indexes = [row.order_index for row in ordered_sections]
    if order_indexes != list(range(order_indexes[0], order_indexes[0] + len(rows))):
        raise ValueError("教材小节必须连续。")

    evidence_texts = [_section_available_content(row) for row in ordered_sections]
    if any(not text.strip() for text in evidence_texts):
        create_or_update_knowledge_gap(session, textbook_id)
        raise ValueError("证据包为空。")

    total_chars = sum(len(text) for text in evidence_texts)
    if total_chars > _EVIDENCE_CHAR_LIMIT:
        raise ValueError("证据包超过 8000 个中文字符。")

    return {
        "textbook_id": textbook.textbook_id,
        "title": textbook.title,
        "sections": [
            {"section_id": row.section_id, "title": row.title}
            for row in ordered_sections
        ],
        "total_chars": total_chars,
        "evidence_text": "\n\n".join(evidence_texts),
    }


def get_textbook_section_binding_context(
    session: Session,
    textbook_id: str,
    section_ids: list[str],
) -> list[dict[str, object]]:
    unique_section_ids = list(
        dict.fromkeys(
            section_id.strip() for section_id in section_ids if section_id.strip()
        )
    )
    if not unique_section_ids:
        return []

    rows = session.exec(
        select(TextbookSectionContent).where(
            TextbookSectionContent.textbook_id == textbook_id,
            TextbookSectionContent.section_id.in_(unique_section_ids),
        )
    ).all()
    rows_by_id = {row.section_id: row for row in rows}
    if set(rows_by_id) != set(unique_section_ids):
        raise ValueError("教材小节不存在。")

    ordered_rows = sorted(
        (rows_by_id[section_id] for section_id in unique_section_ids),
        key=lambda row: row.order_index,
    )
    return [
        {
            "section_id": row.section_id,
            "title": row.title,
            "parent_section_id": row.parent_section_id,
            "order_index": row.order_index,
            "content_char_count": len(_section_available_content(row)),
        }
        for row in ordered_rows
    ]


def create_or_update_knowledge_gap(
    session: Session, normalized_topic: str, student_goal_summary: str = ""
) -> KnowledgeGap:
    normalized_topic = normalized_topic.strip()
    now = datetime.now(timezone.utc)
    gap = session.exec(
        select(KnowledgeGap)
        .where(KnowledgeGap.normalized_topic == normalized_topic)
        .order_by(KnowledgeGap.gap_id)
    ).first()
    if gap is None:
        gap = KnowledgeGap(
            gap_id=_new_id("gap"),
            normalized_topic=normalized_topic,
            trigger_count=1,
            latest_triggered_at=now,
            student_goal_summaries=[],
            status="open",
        )
    else:
        gap.trigger_count += 1
        gap.latest_triggered_at = now

    summary = student_goal_summary.strip()
    if summary and summary not in gap.student_goal_summaries:
        gap.student_goal_summaries = [*gap.student_goal_summaries, summary]

    session.add(gap)
    session.commit()
    session.refresh(gap)
    return gap


def follow_knowledge_gap(
    session: Session, gap_id: str, user_uid: str
) -> KnowledgeGapFollow:
    gap = session.get(KnowledgeGap, gap_id)
    if gap is None:
        raise ValueError("知识缺口不存在。")

    existing_follow = session.exec(
        select(KnowledgeGapFollow).where(
            KnowledgeGapFollow.gap_id == gap_id,
            KnowledgeGapFollow.user_uid == user_uid,
        )
    ).first()
    if existing_follow is not None:
        return existing_follow

    follow = KnowledgeGapFollow(
        follow_id=_new_id("gap-follow"),
        gap_id=gap_id,
        user_uid=user_uid,
    )
    gap.follow_count += 1
    session.add(gap)
    session.add(follow)
    session.commit()
    session.refresh(follow)
    return follow


def create_gap_resolved_notices_for_textbook(
    session: Session, textbook_id: str, *, commit: bool = True
) -> list[KnowledgeGapNotice]:
    textbook = session.get(Textbook, textbook_id)
    if textbook is None or textbook.student_availability_status != "published":
        return []

    gaps = session.exec(
        select(KnowledgeGap)
        .where(KnowledgeGap.status.in_(_RESOLVABLE_GAP_STATUSES))
        .order_by(KnowledgeGap.gap_id)
    ).all()
    created_notices: list[KnowledgeGapNotice] = []
    now = datetime.now(timezone.utc)
    for gap in gaps:
        if not _textbook_covers_topic(textbook, gap.normalized_topic):
            continue

        gap.status = "resolved"
        gap.resolved_textbook_id = textbook_id
        gap.resolved_at = now
        session.add(gap)

        follows = session.exec(
            select(KnowledgeGapFollow).where(KnowledgeGapFollow.gap_id == gap.gap_id)
        ).all()
        for follow in follows:
            if _resolved_notice_exists(session, gap.gap_id, follow.user_uid):
                continue
            notice = KnowledgeGapNotice(
                notice_id=_new_id("gap-notice"),
                gap_id=gap.gap_id,
                user_uid=follow.user_uid,
                notice_type=_NOTICE_TYPE,
                title=f"{gap.normalized_topic} 已补齐",
                body="知识库已发布覆盖该主题的教材。",
                action_label="重新生成学习路径",
                action_payload={
                    "action": _NOTICE_ACTION,
                    "learning_topic": gap.normalized_topic,
                    "textbook_id": textbook_id,
                },
            )
            session.add(notice)
            created_notices.append(notice)

    if commit and (created_notices or gaps):
        session.commit()
        for notice in created_notices:
            session.refresh(notice)
    return created_notices


def add_textbook_extension_resource(
    session: Session, resource: TextbookExtensionResource
) -> TextbookExtensionResource:
    section = session.exec(
        select(TextbookSectionContent).where(
            TextbookSectionContent.textbook_id == resource.textbook_id,
            TextbookSectionContent.section_id == resource.section_id,
        )
    ).first()
    if section is None:
        raise ValueError("教材小节不存在。")

    session.add(resource)
    session.commit()
    session.refresh(resource)
    return resource


def list_extension_resources_for_sections(
    session: Session, textbook_id: str, section_ids: list[str]
) -> dict[str, list[TextbookExtensionResource]]:
    ordered_section_ids = list(dict.fromkeys(section_ids))
    resources_by_section: dict[str, list[TextbookExtensionResource]] = {
        section_id: [] for section_id in ordered_section_ids
    }
    if not ordered_section_ids:
        return resources_by_section

    rows = session.exec(
        select(TextbookExtensionResource)
        .where(
            TextbookExtensionResource.textbook_id == textbook_id,
            TextbookExtensionResource.section_id.in_(ordered_section_ids),
            TextbookExtensionResource.status == _VISIBLE_EXTENSION_RESOURCE_STATUS,
        )
        .order_by(
            TextbookExtensionResource.section_id,
            TextbookExtensionResource.resource_id,
        )
    ).all()
    for row in rows:
        section_resources = resources_by_section[row.section_id]
        if len(section_resources) < 3:
            section_resources.append(row)
    return resources_by_section


def _textbook_content_rows(
    session: Session, textbook_id: str
) -> list[TextbookSectionContent]:
    return list(
        session.exec(
            select(TextbookSectionContent).where(
                TextbookSectionContent.textbook_id == textbook_id
            )
        ).all()
    )


def _get_ingestion_job(session: Session, job_id: str) -> KnowledgeBaseIngestionJob:
    job = session.get(KnowledgeBaseIngestionJob, job_id)
    if job is None:
        raise ValueError("整理任务不存在。")
    return job


def _get_ingestion_job_textbook(
    session: Session,
    job: KnowledgeBaseIngestionJob,
) -> Textbook:
    textbook = session.get(Textbook, job.textbook_id)
    if textbook is None:
        raise ValueError("教材不存在。")
    return textbook


def _textbook_has_non_empty_content(rows: list[TextbookSectionContent]) -> bool:
    return any(_section_available_content(row) for row in rows)


def _textbook_has_complete_content(
    rows: list[TextbookSectionContent], outline: object
) -> bool:
    content_section_ids = {
        row.section_id for row in rows if _section_available_content(row)
    }
    leaf_section_ids = {row["section_id"] for row in _outline_leaf_summary(outline)}
    return bool(leaf_section_ids) and leaf_section_ids.issubset(content_section_ids)


def _textbook_requires_zh_translation(textbook: Textbook) -> bool:
    return False


def _textbook_language_requires_translation(language: str) -> bool:
    return language.strip().lower().startswith("en")


def _textbook_has_zh_content(
    rows: list[TextbookSectionContent], outline: object
) -> bool:
    rows_by_section_id = {row.section_id: row for row in rows}
    for leaf in _outline_leaf_summary(outline):
        row = rows_by_section_id.get(leaf["section_id"])
        if row is None or not _contains_cjk_text(row.content_zh):
            return False
    return True


def _contains_cjk_text(value: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", value))


def _section_available_content(row: TextbookSectionContent) -> str:
    return (row.content_zh or row.content_original or "").strip()


def textbook_covers_topic(textbook: Textbook, topic: str) -> bool:
    return _textbook_covers_topic(textbook, topic)


def textbook_payload_covers_topic(
    title: str,
    description: str,
    tags: list[str],
    outline: object,
    topic: str,
) -> bool:
    normalized_topic = topic.strip()
    if not normalized_topic:
        return False

    searchable_text = [
        title,
        description,
        *tags,
        *[row["title"] for row in _outline_summary(outline)],
    ]
    return any(normalized_topic in item for item in searchable_text)


def _reject_published_structured_overwrite(stored_textbook: Textbook) -> None:
    if stored_textbook.student_availability_status == "published":
        raise ValueError("已发布教材不能通过结构化入库覆盖。")


def _reject_duplicate_section_ids(section_ids: list[str]) -> None:
    if len(set(section_ids)) != len(section_ids):
        raise ValueError("教材小节重复。")


def _textbook_context_row(textbook: Textbook) -> dict:
    return {
        "textbook_id": textbook.textbook_id,
        "title": textbook.title,
        "source_id": textbook.source_id,
        "tags": textbook.tags,
        "description": textbook.description,
        "outline_summary": _outline_summary(textbook.outline),
    }


def _textbook_covers_topic(textbook: Textbook, topic: str) -> bool:
    normalized_topic = topic.strip()
    if not normalized_topic:
        return False

    searchable_text = [
        textbook.title,
        textbook.description,
        *[tag for tag in textbook.tags if isinstance(tag, str)],
        *[row["title"] for row in _outline_summary(textbook.outline)],
    ]
    return any(normalized_topic in item for item in searchable_text)


def _outline_summary(outline: object) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    def collect(value: object) -> None:
        if isinstance(value, list):
            for item in value:
                collect(item)
            return
        if not isinstance(value, dict):
            return

        section_id = value.get("section_id")
        title = value.get("title")
        if isinstance(section_id, str) and isinstance(title, str):
            rows.append({"section_id": section_id, "title": title})
        for nested_value in value.values():
            if isinstance(nested_value, list | dict):
                collect(nested_value)

    collect(outline)
    return rows


def _outline_leaf_summary(outline: object) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    def collect(value: object) -> bool:
        if isinstance(value, list):
            has_section = False
            for item in value:
                if collect(item):
                    has_section = True
            return has_section
        if not isinstance(value, dict):
            return False

        section_id = value.get("section_id")
        title = value.get("title")
        has_current_section = isinstance(section_id, str) and isinstance(title, str)
        has_nested_section = False
        for nested_value in value.values():
            if isinstance(nested_value, list | dict) and collect(nested_value):
                has_nested_section = True

        if has_current_section and not has_nested_section:
            rows.append({"section_id": section_id, "title": title})
        return has_current_section or has_nested_section

    collect(outline)
    return rows


def _outline_has_named_section(outline: object) -> bool:
    return any(
        row["section_id"].strip() and row["title"].strip()
        for row in _outline_summary(outline)
    )


def _resolved_notice_exists(session: Session, gap_id: str, user_uid: str) -> bool:
    notice = session.exec(
        select(KnowledgeGapNotice).where(
            KnowledgeGapNotice.gap_id == gap_id,
            KnowledgeGapNotice.user_uid == user_uid,
            KnowledgeGapNotice.notice_type == _NOTICE_TYPE,
        )
    ).first()
    return notice is not None


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def _source_textbook_ids(value: object) -> list[str]:
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []

    textbook_ids: list[str] = []

    def collect(item: object) -> None:
        if isinstance(item, dict):
            textbook_id = item.get("source_textbook_id")
            if isinstance(textbook_id, str) and textbook_id.strip():
                textbook_ids.append(textbook_id.strip())
            for nested_value in item.values():
                collect(nested_value)

    collect(value)
    return list(dict.fromkeys(textbook_ids))


def get_embeddings_client() -> OpenAIEmbeddings:
    base_url = os.getenv("LLM_BASE_URL")
    api_key = os.getenv("LLM_API_KEY")
    model = os.getenv("LLM_EMBEDDING_MODEL", "text-embedding-v2")
    return OpenAIEmbeddings(
        base_url=base_url,
        api_key=api_key,
        model=model,
    )


def hybrid_search_textbooks(
    session: Session, query: str, limit: int = 15
) -> list[Textbook]:
    # Only search published textbooks
    try:
        embeddings = get_embeddings_client()
        query_vector = embeddings.embed_query(query)

        # RRF Hybrid Search: cosine distance embedding <=> :vector + tsvector match
        sql = text("""
            WITH vector_search AS (
                SELECT textbook_id,
                       ROW_NUMBER() OVER (
                           ORDER BY embedding <=> :vector
                       ) as rank
                FROM textbook
                WHERE embedding IS NOT NULL
                  AND student_availability_status = 'published'
                LIMIT 30
            ),
            fts_search AS (
                SELECT textbook_id,
                       ROW_NUMBER() OVER (
                           ORDER BY ts_rank(
                               to_tsvector(
                                   'chinese',
                                   title || ' ' || tags::text
                               ),
                               plainto_tsquery('chinese', :query)
                           ) DESC
                       ) as rank
                FROM textbook
                WHERE to_tsvector(
                          'chinese',
                          title || ' ' || tags::text
                      ) @@ plainto_tsquery('chinese', :query)
                  AND student_availability_status = 'published'
                LIMIT 30
            )
            SELECT COALESCE(v.textbook_id, f.textbook_id) as textbook_id,
                   (1.0 / (60.0 + COALESCE(v.rank, 100)) +
                    1.0 / (60.0 + COALESCE(f.rank, 100))) as rrf_score
            FROM vector_search v
            FULL OUTER JOIN fts_search f ON v.textbook_id = f.textbook_id
            ORDER BY rrf_score DESC
            LIMIT :limit
        """)
        res = session.execute(
            sql, {"vector": query_vector, "query": query, "limit": limit}
        ).all()
        ids = [r[0] for r in res]
        if not ids:
            return []
        # Retrieve instances in RRF order
        tbs = session.exec(select(Textbook).where(Textbook.textbook_id.in_(ids))).all()
        tb_map = {tb.textbook_id: tb for tb in tbs}
        return [tb_map[t_id] for t_id in ids if t_id in tb_map]
    except Exception as e:
        logger.info("Hybrid search fallback to simple matching: %s", e)

    # Fallback: simple string matching (e.g., pgvector extension not available)
    stmt = select(Textbook).where(Textbook.student_availability_status == "published")
    all_tbs = session.exec(stmt).all()

    scored = []
    for tb in all_tbs:
        score = 0
        if query.lower() in tb.title.lower():
            score += 10
        if tb.tags:
            for tag in tb.tags:
                if query.lower() in tag.lower():
                    score += 5
        if score > 0:
            scored.append((score, tb))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored[:limit]]


def search_admin_textbooks(
    session: Session, query: str, limit: int = 5
) -> list[Textbook]:
    normalized_query = query.strip().lower()
    if not normalized_query:
        return []

    rows = session.exec(
        select(Textbook)
        .where(Textbook.student_availability_status != "archived")
        .order_by(Textbook.textbook_id)
    ).all()
    scored: list[tuple[int, Textbook]] = []
    for textbook in rows:
        searchable_text = [
            textbook.title,
            textbook.description,
            *[tag for tag in textbook.tags if isinstance(tag, str)],
            *[row["title"] for row in _outline_summary(textbook.outline)],
        ]
        score = sum(10 for item in searchable_text if normalized_query in item.lower())
        if textbook.student_availability_status == "published":
            score += 5
        if score > 0:
            scored.append((score, textbook))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [textbook for _, textbook in scored[:limit]]


def search_real_textbook_sources(
    topic: str, limit: int = _SOURCE_RESULT_LIMIT
) -> list[KnowledgeBaseSourceResult]:
    if limit <= 0:
        return []

    raw_results = [
        *_search_known_open_textbook_sources(topic),
        *_search_real_textbook_sources_with_llm(topic, limit),
    ]
    source_results: list[KnowledgeBaseSourceResult] = []
    seen_urls: set[str] = set()
    for raw_result in raw_results:
        source_result = _normalize_source_result(raw_result)
        if (
            source_result is None
            or source_result.source_url in seen_urls
            or not _source_result_looks_like_textbook(source_result)
            or not _source_result_is_parseable(source_result)
        ):
            continue
        seen_urls.add(source_result.source_url)
        source_results.append(source_result)

    source_results.sort(
        key=lambda result: (
            result.parseability_score,
            result.language.strip().lower() == "zh",
        ),
        reverse=True,
    )
    limited_results = source_results[:limit]
    for index, source_result in enumerate(limited_results):
        source_result.is_recommended = index == 0
    return limited_results


def _search_known_open_textbook_sources(topic: str) -> list[dict[str, object]]:
    normalized_topic = topic.strip().lower()
    if not normalized_topic:
        return []

    rows: list[dict[str, object]] = []
    for source_row in _OPEN_TEXTBOOK_SOURCE_ROWS:
        raw_keywords = source_row.get("topic_keywords")
        if not isinstance(raw_keywords, tuple):
            continue
        keywords = [keyword for keyword in raw_keywords if isinstance(keyword, str)]
        if not any(keyword.lower() in normalized_topic for keyword in keywords):
            continue
        rows.append(
            {key: value for key, value in source_row.items() if key != "topic_keywords"}
        )
    return rows


def _search_real_textbook_sources_with_llm(
    topic: str, limit: int
) -> list[dict[str, object]]:
    prompt = (
        "你是知识库教材来源搜索智能体。请联网搜索真实、可访问、适合作为教材来源的材料。"
        "只返回 JSON 数组，不要 Markdown，不要解释。"
        "数组每个对象字段必须是：title, original_title, language, source_url, "
        "source_type, provider_name, description, tags, parseability_score, "
        "parseability_reason, topic_summary。"
        "source_type 只能是 pdf 或 html。"
        "source_url 必须是真实教材页面或 PDF 地址，"
        "禁止 example.com、占位链接、无来源链接。"
        f"\n主题：{topic.strip()}"
        f"\n最多返回：{limit}"
    )
    try:
        response = get_search_worker_llm().invoke(prompt)
        content = getattr(response, "content", "")
        if not isinstance(content, str):
            return []
        payload = loads(_extract_json_array(content))
    except Exception as exc:
        logger.warning("Real textbook source search failed: %s", exc)
        return []

    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _extract_json_array(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        return stripped
    start = stripped.find("[")
    end = stripped.rfind("]")
    if start < 0 or end <= start:
        raise ValueError("搜索结果没有 JSON 数组。")
    return stripped[start : end + 1]


def _normalize_source_result(raw_result: object) -> KnowledgeBaseSourceResult | None:
    if not isinstance(raw_result, dict):
        return None

    title = _clean_text(raw_result.get("title"))
    source_url = _validated_textbook_url(raw_result.get("source_url"))
    source_type = _clean_text(raw_result.get("source_type")).lower()
    if not title or not source_url or source_type not in _SOURCE_TYPES:
        return None

    raw_tags = raw_result.get("tags")
    tags: list[str] = []
    if isinstance(raw_tags, list):
        tags = [tag for tag in (_clean_text(item) for item in raw_tags) if tag]

    parseability_score = _parse_source_score(raw_result.get("parseability_score"))
    return KnowledgeBaseSourceResult(
        source_result_id=_source_result_id(source_url),
        title=title,
        original_title=_clean_text(raw_result.get("original_title")),
        language=_clean_text(raw_result.get("language")),
        source_url=source_url,
        source_type=source_type,
        provider_name=_clean_text(raw_result.get("provider_name")),
        description=_clean_text(raw_result.get("description")),
        tags=tags,
        parseability_score=parseability_score,
        parseability_reason=_clean_text(raw_result.get("parseability_reason")),
        topic_summary=_clean_text(raw_result.get("topic_summary")),
    )


def _source_result_is_parseable(source_result: KnowledgeBaseSourceResult) -> bool:
    try:
        _ensure_source_result_parseable(source_result, max_linked_pages=8)
    except (DocumentParseError, ValueError) as exc:
        logger.info(
            "Rejected textbook source %s because parsing failed: %s",
            source_result.source_url,
            exc,
        )
        return False
    return True


def _source_result_looks_like_textbook(
    source_result: KnowledgeBaseSourceResult,
) -> bool:
    searchable_text = " ".join(
        [
            source_result.title,
            source_result.original_title,
            source_result.source_url,
            source_result.provider_name,
            source_result.description,
            source_result.parseability_reason,
            source_result.topic_summary,
            *source_result.tags,
        ]
    ).lower()
    return not any(
        marker.lower() in searchable_text for marker in _NON_TEXTBOOK_SOURCE_MARKERS
    )


def _ensure_source_result_parseable(
    source_result: KnowledgeBaseSourceResult,
    *,
    max_linked_pages: int,
) -> None:
    try:
        outline, sections = parse_textbook_source_to_sections(
            source_result.source_url,
            source_result.language,
            max_linked_pages=max_linked_pages,
        )
    except DocumentParseError as exc:
        raise ValueError(f"教材来源解析失败：{exc}") from exc
    outline_sections = _outline_summary(outline)
    if not outline_sections:
        raise ValueError("教材来源无法解析出可校对大纲。")
    has_missing_content = any(
        not sections.get(section["section_id"], "").strip()
        for section in outline_sections
    )
    if has_missing_content:
        raise ValueError("教材来源无法切分出完整小节正文。")


def _parse_source_score(value: object) -> int:
    if isinstance(value, int | float | str):
        try:
            score = int(value)
        except (TypeError, ValueError):
            return 0
        return max(0, min(score, 100))
    return 0


def _source_result_id(source_url: str) -> str:
    return "source-result-" + sha1(source_url.encode("utf-8")).hexdigest()[:8]


def _clean_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _validated_textbook_url(value: object) -> str:
    url = _clean_text(value)
    if not url:
        return ""
    parsed = urlparse(url)
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    if parsed.scheme not in {"http", "https"} or not hostname:
        return ""
    if hostname in _PLACEHOLDER_HOSTS:
        return ""
    if not _is_reachable_textbook_url(url):
        return ""
    return url


def _is_reachable_textbook_url(url: str) -> bool:
    for method in ("HEAD", "GET"):
        try:
            request = Request(url, method=method, headers={"User-Agent": "mutiagent"})
            with urlopen(request, timeout=8) as response:
                status = getattr(response, "status", 200)
                content_type = response.headers.get("content-type", "").lower()
                return 200 <= status < 400 and any(
                    item in content_type for item in _TEXTBOOK_CONTENT_TYPES
                )
        except HTTPError as exc:
            if method == "HEAD" and exc.code in {403, 405}:
                continue
            return False
        except (OSError, URLError, TimeoutError):
            continue
    return False


def _textbook_hits_from_matches(
    session: Session, matched_textbooks: list[Textbook]
) -> list[KnowledgeBaseAgentTextbookHit]:
    source_name_map = {
        source.source_id: source.name for source in list_knowledge_sources(session)
    }
    textbook_hits: list[KnowledgeBaseAgentTextbookHit] = []
    for textbook in matched_textbooks:
        source_name = source_name_map.get(textbook.source_id, textbook.source_id)
        score = 20 if textbook.student_availability_status == "published" else 10
        reason = (
            "已发布教材"
            if textbook.student_availability_status == "published"
            else "待整理教材"
        )
        textbook_hits.append(
            KnowledgeBaseAgentTextbookHit(
                textbook_id=textbook.textbook_id,
                title=textbook.title,
                source_name=source_name,
                student_availability_status=textbook.student_availability_status,
                score=score,
                reason=reason,
            )
        )
    return textbook_hits


def _matching_gap_hits(session: Session, query: str) -> list[KnowledgeBaseAgentGapHit]:
    gap_hits: list[KnowledgeBaseAgentGapHit] = []
    normalized_query = query.lower()
    for gap in session.exec(select(KnowledgeGap).order_by(KnowledgeGap.gap_id)).all():
        if normalized_query not in gap.normalized_topic.lower() and not any(
            normalized_query in summary.lower()
            for summary in gap.student_goal_summaries
        ):
            continue
        gap_hits.append(
            KnowledgeBaseAgentGapHit(
                gap_id=gap.gap_id,
                normalized_topic=gap.normalized_topic,
                status=gap.status,
                reason="缺口主题命中。",
            )
        )
    return gap_hits


def run_knowledge_base_agent(
    session: Session, message: str
) -> KnowledgeBaseAgentResponse:
    final_response: KnowledgeBaseAgentResponse | None = None
    for event in stream_knowledge_base_agent_events(session, message):
        if event["event"] != "completed":
            continue
        response_payload = event["payload"].get("response")
        if not isinstance(response_payload, dict):
            continue
        final_response = KnowledgeBaseAgentResponse.model_validate(response_payload)
    if final_response is None:
        return KnowledgeBaseAgentResponse(
            reply_text="知识库 Agent 未返回结果，请稍后重试。",
        )
    return final_response


def stream_knowledge_base_agent_events(
    session: Session, message: str
) -> Generator[dict[str, object], None, None]:
    query = message.strip()
    yield _agent_stream_event(
        "started",
        "已收到管理员消息。",
        raw_length=len(message),
        normalized_length=len(query),
    )
    if not query:
        response = KnowledgeBaseAgentResponse(
            reply_text="先说一句话，我会自动帮你从知识库里匹配教材。",
        )
        yield _agent_stream_event("completed", "本轮已结束。", response=response)
        return

    source_count = session.exec(select(KnowledgeSource)).all()
    textbook_count = session.exec(select(Textbook)).all()
    gap_count = session.exec(select(KnowledgeGap)).all()
    yield _agent_stream_event(
        "context_loaded",
        "已读取知识库现状。",
        source_count=len(source_count),
        textbook_count=len(textbook_count),
        gap_count=len(gap_count),
    )
    yield _agent_stream_event(
        "source_search_started",
        "正在联网查找真实教材来源。",
    )
    source_results = search_real_textbook_sources(query, limit=_SOURCE_RESULT_LIMIT)
    yield _agent_stream_event(
        "source_search_completed",
        "真实教材来源查找完成。",
        result_count=len(source_results),
    )

    yield _agent_stream_event(
        "duplicate_check_started",
        "正在进行本地知识库查重。",
    )
    for result in source_results:
        existing = session.exec(
            select(Textbook).where(
                or_(
                    Textbook.download_url == result.source_url,
                    func.lower(Textbook.title) == func.lower(result.title),
                )
            )
        ).first()
        if existing:
            result.already_imported = True
            result.textbook_id = existing.textbook_id

    imported_count = sum(1 for r in source_results if r.already_imported)
    yield _agent_stream_event(
        "duplicate_check_completed",
        "本地查重比对完成。",
        imported_count=imported_count,
    )

    yield _agent_stream_event(
        "gap_search_started",
        "正在检查未覆盖待办是否命中本轮主题。",
    )
    gap_hits = _matching_gap_hits(session, query)
    yield _agent_stream_event(
        "gap_search_completed",
        "待办检查完成。",
        hit_count=len(gap_hits),
    )

    selected_source_result_id = None
    if source_results:
        non_imported = [r for r in source_results if not r.already_imported]
        if non_imported:
            selected_source_result_id = non_imported[0].source_result_id
        else:
            selected_source_result_id = source_results[0].source_result_id

    reply_parts = []
    if source_results:
        msg = (
            f"我已联网为你查找到以下相关教材素材：共找到 {len(source_results)} "
            f"个真实教材来源（其中 {imported_count} 个已入库）。"
        )
        reply_parts.append(msg)
        reply_parts.append(
            "你可以点击“确认解析”将新资源导入知识库，或直接“去查看”已入库教材。"
        )
    else:
        reply_parts.append(
            "我尝试联网查找真实教材来源，但没有拿到可用结果。请检查搜索服务配置。"
        )

    if gap_hits:
        reply_parts.append(
            "仍然空着的方向有："
            + "、".join(f"“{hit.normalized_topic}”" for hit in gap_hits[:3])
            + "。"
        )

    response = KnowledgeBaseAgentResponse(
        reply_text=" ".join(reply_parts),
        selected_textbook_id=None,
        selected_source_result_id=selected_source_result_id,
        textbook_hits=[],
        gap_hits=gap_hits[:5],
        source_results=source_results,
    )
    yield _agent_stream_event(
        "reply_ready",
        "已生成管理员回复。",
        reply_length=len(response.reply_text),
    )
    yield _agent_stream_event("completed", "本轮已完成。", response=response)


def _agent_stream_event(
    event: str, message: str, **payload: object
) -> dict[str, object]:
    serialized_payload = {
        key: _serialize_agent_stream_value(value) for key, value in payload.items()
    }
    serialized_payload["message"] = message
    return {"event": event, "payload": serialized_payload}


def _serialize_agent_stream_value(value: object) -> object:
    if isinstance(value, KnowledgeBaseAgentResponse):
        return value.model_dump()
    if isinstance(value, KnowledgeBaseAgentTextbookHit):
        return value.model_dump()
    if isinstance(value, KnowledgeBaseAgentGapHit):
        return value.model_dump()
    if isinstance(value, KnowledgeBaseSourceResult):
        return value.model_dump()
    if isinstance(value, list):
        return [_serialize_agent_stream_value(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _serialize_agent_stream_value(item) for key, item in value.items()
        }
    return value
