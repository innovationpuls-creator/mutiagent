from __future__ import annotations

from datetime import datetime, timezone

from app.models import (
    KnowledgeGap,
    KnowledgeGapFollow,
    KnowledgeGapNotice,
    KnowledgeSource,
    Textbook,
    TextbookExtensionResource,
    TextbookSectionContent,
)

_PUBLISHED_AT = datetime(2026, 6, 1, tzinfo=timezone.utc)
_ARCHIVED_AT = datetime(2026, 6, 2, tzinfo=timezone.utc)


def enabled_source(
    source_id: str = "source-admitted",
    name: str = "已准入来源",
) -> KnowledgeSource:
    return KnowledgeSource(
        source_id=source_id,
        name=name,
        base_url="https://example.test/source",
        status="enabled",
        source_kind="open_textbook",
        download_requirement="公开下载",
        ai_search_requirement="允许搜索",
        download_status="verified",
        parse_status="supported",
        license_review_status="approved",
        human_review_status="reviewed",
    )


def unenabled_source(
    source_id: str = "source-blocked",
    name: str = "未启用来源",
) -> KnowledgeSource:
    source = enabled_source(source_id=source_id, name=name)
    source.status = "disabled"
    return source


def source_payload(source: KnowledgeSource) -> dict[str, object]:
    return {
        "source_id": source.source_id,
        "name": source.name,
        "base_url": source.base_url,
        "status": source.status,
        "source_kind": source.source_kind,
        "download_requirement": source.download_requirement,
        "ai_search_requirement": source.ai_search_requirement,
        "download_status": source.download_status,
        "parse_status": source.parse_status,
        "license_review_status": source.license_review_status,
        "human_review_status": source.human_review_status,
    }


def admitted_source_payload(
    source_id: str = "source-admitted-api",
) -> dict[str, object]:
    return source_payload(enabled_source(source_id=source_id, name="已准入来源"))


def blocked_source_payload(source_id: str = "source-blocked-api") -> dict[str, object]:
    return source_payload(unenabled_source(source_id=source_id, name="未启用来源"))


def textbook(
    *,
    textbook_id: str,
    title: str,
    source_id: str = "source-admitted",
    description: str = "",
    tags: list[str] | None = None,
    outline: dict[str, object] | None = None,
    ingestion_status: str = "not_started",
    outline_review_status: str = "unreviewed",
    student_availability_status: str = "draft",
    language: str = "en",
    translated_language: str = "zh",
) -> Textbook:
    return Textbook(
        textbook_id=textbook_id,
        source_id=source_id,
        title=title,
        original_title="Linear Algebra",
        language=language,
        translated_language=translated_language,
        description=description,
        tags=tags or [],
        download_url="https://example.test/book.pdf",
        file_asset_url="https://example.test/book.md",
        outline=outline or {},
        ingestion_status=ingestion_status,
        outline_review_status=outline_review_status,
        student_availability_status=student_availability_status,
    )


def published_textbook(
    textbook_id: str = "textbook-published",
    source_id: str = "source-admitted",
    title: str = "线性代数",
) -> Textbook:
    row = textbook(
        textbook_id=textbook_id,
        source_id=source_id,
        title=title,
        description="覆盖矩阵和向量空间",
        tags=["矩阵", "向量空间"],
        outline={"sections": [{"section_id": "1.1", "title": "矩阵乘法"}]},
        ingestion_status="completed",
        outline_review_status="approved",
        student_availability_status="published",
    )
    row.published_at = _PUBLISHED_AT
    return row


def unpublished_textbook(
    textbook_id: str = "textbook-draft",
    source_id: str = "source-admitted",
    title: str = "矩阵专题草稿",
) -> Textbook:
    return textbook(
        textbook_id=textbook_id,
        source_id=source_id,
        title=title,
        description="未发布教材不能进入上下文",
        tags=["矩阵"],
        outline={"sections": [{"section_id": "1.1", "title": "矩阵"}]},
        ingestion_status="completed",
        outline_review_status="approved",
        student_availability_status="draft",
    )


def archived_textbook(
    textbook_id: str = "textbook-archived",
    source_id: str = "source-admitted",
    title: str = "已归档教材",
) -> Textbook:
    row = unpublished_textbook(
        textbook_id=textbook_id,
        source_id=source_id,
        title=title,
    )
    row.student_availability_status = "archived"
    row.archived_at = _ARCHIVED_AT
    return row


def textbook_payload(row: Textbook) -> dict[str, object]:
    return {
        "textbook_id": row.textbook_id,
        "source_id": row.source_id,
        "title": row.title,
        "original_title": row.original_title,
        "language": row.language,
        "translated_language": row.translated_language,
        "description": row.description,
        "tags": row.tags,
        "download_url": row.download_url,
        "file_asset_url": row.file_asset_url,
        "outline": row.outline,
        "ingestion_status": row.ingestion_status,
        "outline_review_status": row.outline_review_status,
        "student_availability_status": row.student_availability_status,
        "ingestion_error_message": row.ingestion_error_message,
    }


def section(
    *,
    textbook_id: str,
    section_content_id: str,
    section_id: str,
    title: str = "小节",
    content_zh: str,
    content_original: str = "",
    order_index: int = 1,
    parent_section_id: str | None = None,
    original_title: str = "",
    content_char_count: int | None = None,
) -> TextbookSectionContent:
    return TextbookSectionContent(
        section_content_id=section_content_id,
        textbook_id=textbook_id,
        section_id=section_id,
        parent_section_id=parent_section_id,
        order_index=order_index,
        title=title,
        original_title=original_title,
        content_original=content_original or content_zh,
        content_zh=content_zh,
        content_char_count=(
            len(content_zh) if content_char_count is None else content_char_count
        ),
    )


def section_payload(row: TextbookSectionContent) -> dict[str, object]:
    return {
        "section_content_id": row.section_content_id,
        "section_id": row.section_id,
        "parent_section_id": row.parent_section_id,
        "order_index": row.order_index,
        "title": row.title,
        "original_title": row.original_title,
        "content_original": row.content_original,
        "content_zh": row.content_zh,
        "content_char_count": row.content_char_count,
    }


def continuous_sections(
    textbook_id: str = "textbook-evidence",
) -> list[TextbookSectionContent]:
    return [
        section(
            textbook_id=textbook_id,
            section_content_id=f"section-evidence-{index}",
            section_id=f"1.{index}",
            order_index=index,
            title=f"小节 {index}",
            content_zh=f"第 {index} 节中文正文",
        )
        for index in range(1, 4)
    ]


def non_continuous_sections(
    textbook_id: str = "textbook-evidence",
) -> list[TextbookSectionContent]:
    return [
        section(
            textbook_id=textbook_id,
            section_content_id="section-evidence-non-continuous-1",
            section_id="1.1",
            order_index=1,
            title="小节 1",
            content_zh="第 1 节中文正文",
        ),
        section(
            textbook_id=textbook_id,
            section_content_id="section-evidence-non-continuous-3",
            section_id="1.3",
            order_index=3,
            title="小节 3",
            content_zh="第 3 节中文正文",
        ),
    ]


def over_8000_char_sections(
    textbook_id: str = "textbook-evidence",
) -> list[TextbookSectionContent]:
    return [
        section(
            textbook_id=textbook_id,
            section_content_id="section-evidence-over-limit-1",
            section_id="1.98",
            order_index=98,
            title="超长小节一",
            content_zh="字" * 4001,
        ),
        section(
            textbook_id=textbook_id,
            section_content_id="section-evidence-over-limit-2",
            section_id="1.99",
            order_index=99,
            title="超长小节二",
            content_zh="字" * 4001,
        ),
    ]


def structured_textbook_payload(
    textbook_id: str = "textbook-linear-api",
    source_id: str = "source-admitted-api",
    title: str = "线性代数",
    outline_review_status: str = "approved",
) -> dict[str, object]:
    row = unpublished_textbook(
        textbook_id=textbook_id,
        source_id=source_id,
        title=title,
    )
    row.description = "覆盖矩阵乘法"
    row.tags = ["矩阵"]
    row.outline = {"sections": [{"section_id": "1.1", "title": "矩阵乘法"}]}
    row.outline_review_status = outline_review_status
    rows = [
        section(
            textbook_id=textbook_id,
            section_content_id=f"section-{textbook_id}-1",
            section_id="1.1",
            order_index=1,
            title="矩阵乘法",
            original_title="Matrix Multiplication",
            content_zh="矩阵乘法的中文正文。",
            content_char_count=0,
        )
    ]
    return {
        "textbook": textbook_payload(row),
        "sections": [section_payload(section_row) for section_row in rows],
    }


def uncovered_topic_gap(
    gap_id: str = "gap-api",
    normalized_topic: str = "概率论",
) -> KnowledgeGap:
    return KnowledgeGap(
        gap_id=gap_id,
        normalized_topic=normalized_topic,
        trigger_count=1,
        status="open",
        student_goal_summaries=["希望学习概率基础"],
    )


def followed_gap_student(
    gap_id: str = "gap-api",
    user_uid: str = "user-followed-gap",
    follow_id: str = "gap-follow-followed-student",
) -> KnowledgeGapFollow:
    return KnowledgeGapFollow(
        follow_id=follow_id,
        gap_id=gap_id,
        user_uid=user_uid,
    )


def gap_resolved_notice(
    *,
    notice_id: str,
    gap_id: str,
    user_uid: str,
    learning_topic: str = "概率论",
    textbook_id: str = "textbook-linear-api",
) -> KnowledgeGapNotice:
    return KnowledgeGapNotice(
        notice_id=notice_id,
        gap_id=gap_id,
        user_uid=user_uid,
        notice_type="knowledge_gap_resolved",
        title=f"{learning_topic} 已补齐",
        body="知识库已发布覆盖该主题的教材。",
        action_label="重新生成学习路径",
        action_payload={
            "action": "regenerate_learning_path_intake",
            "learning_topic": learning_topic,
            "textbook_id": textbook_id,
        },
    )


def extension_resource(
    *,
    resource_id: str,
    textbook_id: str,
    section_id: str,
    title_zh: str,
    status: str,
    render_mode: str = "webpage",
) -> TextbookExtensionResource:
    return TextbookExtensionResource(
        resource_id=resource_id,
        textbook_id=textbook_id,
        section_id=section_id,
        resource_type="webpage",
        title_zh=title_zh,
        description_zh="补充阅读",
        render_mode=render_mode,
        url=f"https://example.test/{resource_id}",
        cover_url=f"https://example.test/{resource_id}.png",
        source_name="已准入来源",
        status=status,
    )


def extension_resource_payload(row: TextbookExtensionResource) -> dict[str, object]:
    return {
        "resource_id": row.resource_id,
        "section_id": row.section_id,
        "resource_type": row.resource_type,
        "title_zh": row.title_zh,
        "description_zh": row.description_zh,
        "render_mode": row.render_mode,
        "url": row.url,
        "cover_url": row.cover_url,
        "source_name": row.source_name,
        "status": row.status,
    }


def extension_resources_three(
    textbook_id: str = "textbook-extension",
    section_id: str = "1.1",
) -> list[TextbookExtensionResource]:
    return [
        extension_resource(
            resource_id=f"resource-visible-{index}",
            textbook_id=textbook_id,
            section_id=section_id,
            title_zh=f"扩展资料 {index}",
            status="published",
        )
        for index in range(1, 4)
    ]


def extension_resources_four(
    textbook_id: str = "textbook-extension",
    section_id: str = "1.1",
) -> list[TextbookExtensionResource]:
    return [
        extension_resource(
            resource_id=f"resource-visible-{index}",
            textbook_id=textbook_id,
            section_id=section_id,
            title_zh=f"扩展资料 {index}",
            status="published",
        )
        for index in range(1, 5)
    ]
