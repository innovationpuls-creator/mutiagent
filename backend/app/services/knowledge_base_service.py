from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from uuid import uuid4

from langchain_openai import OpenAIEmbeddings
from sqlalchemy import text
from sqlmodel import Session, select

from app.database import get_engine
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
from app.orchestration.llm import get_worker_llm

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
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def start_knowledge_base_ingestion_job(
    session: Session,
    job_id: str,
) -> KnowledgeBaseIngestionJob:
    job = _get_ingestion_job(session, job_id)
    if job.status != "queued":
        raise ValueError("只有 queued 整理任务可以开始。")

    textbook = _get_ingestion_job_textbook(session, job)
    job.status = "running"
    job.started_at = datetime.now(timezone.utc)
    job.finished_at = None
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
    job.status = "completed"
    job.finished_at = datetime.now(timezone.utc)
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
    job.status = "failed"
    job.finished_at = datetime.now(timezone.utc)
    job.error_message = message
    textbook.ingestion_status = "failed"
    textbook.ingestion_error_message = message
    session.add(job)
    session.add(textbook)
    session.commit()
    session.refresh(job)
    return job


def publish_textbook(session: Session, textbook_id: str) -> Textbook:
    textbook = session.get(Textbook, textbook_id)
    if textbook is None:
        raise ValueError("教材不存在。")

    source = session.get(KnowledgeSource, textbook.source_id)
    if source is None or not is_source_admitted_for_primary_textbook(source):
        raise ValueError("教材来源未通过准入校验。")
    if not _outline_has_named_section(textbook.outline):
        raise ValueError("教材缺少中文目录。")
    if textbook.outline_review_status != "approved":
        raise ValueError("教材目录未校对。")
    content_rows = _textbook_content_rows(session, textbook_id)
    if not _textbook_has_non_empty_content(content_rows):
        raise ValueError("教材缺少中文正文。")
    if not _textbook_has_complete_content(content_rows, textbook.outline):
        raise ValueError("教材缺少完整中文正文。")

    try:
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
    stmt = (
        select(Textbook)
        .where(Textbook.student_availability_status == "published")
        .order_by(Textbook.textbook_id)
    )
    matched_textbooks = [
        _textbook_context_row(textbook)
        for textbook in session.exec(stmt).all()
        if _textbook_covers_topic(textbook, topic)
    ]
    if matched_textbooks:
        return {"textbooks": matched_textbooks, "gap_id": None}

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

    if any(not row.content_zh.strip() for row in ordered_sections):
        create_or_update_knowledge_gap(session, textbook_id)
        raise ValueError("证据包为空。")

    total_chars = sum(len(row.content_zh or "") for row in ordered_sections)
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
        "evidence_text": "\n\n".join(row.content_zh for row in ordered_sections),
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
            "content_char_count": len(row.content_zh or ""),
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
    return any(row.content_zh.strip() for row in rows)


def _textbook_has_complete_content(
    rows: list[TextbookSectionContent], outline: object
) -> bool:
    content_section_ids = {row.section_id for row in rows if row.content_zh.strip()}
    leaf_section_ids = {row["section_id"] for row in _outline_leaf_summary(outline)}
    return bool(leaf_section_ids) and leaf_section_ids.issubset(content_section_ids)


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


async def generate_textbook_contents_task(
    textbook_id: str,
    job_id: str,
    session_maker: object = None,
) -> None:
    engine = get_engine()
    with Session(engine) as session:
        job = session.get(KnowledgeBaseIngestionJob, job_id)
        if job is None:
            return

        textbook = session.get(Textbook, textbook_id)
        if textbook is None:
            job.status = "failed"
            job.finished_at = datetime.now(timezone.utc)
            job.error_message = "教材不存在。"
            session.add(job)
            session.commit()
            return

        try:
            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            session.add(job)
            session.commit()

            chapters = textbook.outline.get("chapters", [])
            order_index = 0

            for ch in chapters:
                chapter_title = ch.get("title", "")
                sections = ch.get("sections", [])
                for sec in sections:
                    section_id = sec.get("section_id")
                    section_title = sec.get("title", "")

                    existing = session.exec(
                        select(TextbookSectionContent).where(
                            TextbookSectionContent.textbook_id == textbook_id,
                            TextbookSectionContent.section_id == section_id,
                        )
                    ).first()

                    if not existing:
                        llm = get_worker_llm()
                        prompt = (
                            f"你是一个专业的教材撰写专家。请为教材《{textbook.title}》的章节"
                            f"《{chapter_title}》中的小节《{section_title}》撰写详细的教学正文。"
                            "正文应包含理论讲解、代码示例、概念分析等，"
                            "字数在 2000 到 5000 字之间。"
                            "输出必须是纯 Markdown 格式。"
                        )
                        response = await llm.ainvoke(prompt)
                        content = response.content

                        section_content = TextbookSectionContent(
                            section_content_id=f"content-{uuid4().hex}",
                            textbook_id=textbook_id,
                            section_id=section_id,
                            title=section_title,
                            content_zh=content,
                            content_char_count=len(content),
                            order_index=order_index,
                        )
                        session.add(section_content)
                        session.commit()
                    order_index += 1

            job.status = "completed"
            job.finished_at = datetime.now(timezone.utc)
            session.add(job)
            session.commit()

        except Exception as exc:
            job.status = "failed"
            job.finished_at = datetime.now(timezone.utc)
            job.error_message = str(exc)
            session.add(job)
            session.commit()


def get_textbook_generation_progress(
    session: Session,
    textbook_id: str,
) -> dict[str, object]:
    textbook = session.get(Textbook, textbook_id)
    if textbook is None:
        raise ValueError("教材不存在。")

    outline_sections = _outline_summary(textbook.outline)
    total_sections = len(outline_sections)

    section_contents = session.exec(
        select(TextbookSectionContent).where(
            TextbookSectionContent.textbook_id == textbook_id
        )
    ).all()

    written_section_ids = {
        sc.section_id
        for sc in section_contents
        if sc.content_zh and sc.content_zh.strip()
    }

    written_count = 0
    for sec in outline_sections:
        sec_id = sec.get("section_id")
        if sec_id in written_section_ids:
            written_count += 1

    progress_percentage = (
        (written_count / total_sections) * 100.0 if total_sections > 0 else 0.0
    )

    job = session.exec(
        select(KnowledgeBaseIngestionJob)
        .where(
            KnowledgeBaseIngestionJob.textbook_id == textbook_id,
            KnowledgeBaseIngestionJob.job_type == "aigc_generation",
        )
        .order_by(KnowledgeBaseIngestionJob.created_at.desc())
    ).first()

    status_val = job.status if job else "not_started"

    current_section_title = ""
    if status_val == "running":
        for sec in outline_sections:
            sec_id = sec.get("section_id")
            if sec_id not in written_section_ids:
                current_section_title = sec.get("title", "")
                break

    return {
        "textbook_id": textbook_id,
        "progress_percentage": progress_percentage,
        "status": status_val,
        "current_section_title": current_section_title,
    }


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
    bind = session.get_bind()
    dialect_name = bind.dialect.name

    if dialect_name == "postgresql":
        try:
            embeddings = get_embeddings_client()
            query_vector = embeddings.embed_query(query)

            # Perform RRF Hybrid Search in PostgreSQL using raw SQL text:
            # Combine cosine distance embedding <=> :vector and tsvector match
            # Make sure to handle tsquery correctly using websearch_to_tsquery
            # or plainto_tsquery.
            # Return the Textbook instances matching the IDs
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
            tbs = session.exec(
                select(Textbook).where(Textbook.textbook_id.in_(ids))
            ).all()
            tb_map = {tb.textbook_id: tb for tb in tbs}
            return [tb_map[t_id] for t_id in ids if t_id in tb_map]
        except Exception as e:
            logger.warning("PostgreSQL hybrid search failed, falling back: %s", e)

    # SQLite or Postgres fallback: Simple matching
    stmt = select(Textbook).where(Textbook.student_availability_status == "published")
    all_tbs = session.exec(stmt).all()

    # Calculate simple match score (e.g., query string overlap in title or tags)
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
