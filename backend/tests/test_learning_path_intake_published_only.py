from __future__ import annotations

from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.models import KnowledgeSource, Textbook
from app.schema_upgrades import run_schema_upgrades
from app.services.knowledge_base_service import (
    TextbookSectionContent,
    create_knowledge_source,
    get_published_textbook_context_for_topic,
    publish_textbook,
    upsert_structured_textbook,
)
from tests.postgres import postgresql_test_url


@pytest.fixture
def db_session(tmp_path: Path):
    engine = create_engine(
        postgresql_test_url(tmp_path, "test_learning_path_intake_published_only"),
    )
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _source(source_id: str = "source-intake") -> KnowledgeSource:
    return KnowledgeSource(
        source_id=source_id,
        name="草案来源",
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


def _published_textbook() -> Textbook:
    return Textbook(
        textbook_id="textbook-published-intake",
        source_id="source-intake",
        title="矩阵专题",
        original_title="Matrix Topic",
        language="en",
        translated_language="zh",
        description="覆盖矩阵乘法",
        tags=["矩阵"],
        download_url="https://example.test/book.pdf",
        file_asset_url="https://example.test/book.md",
        outline={
            "chapters": [
                {
                    "chapter_number": 1,
                    "title": "第一章 矩阵基础",
                    "sections": [
                        {
                            "section_id": "1.1",
                            "title": "1.1 矩阵乘法",
                        }
                    ],
                }
            ]
        },
        outline_review_status="approved",
        ingestion_status="completed",
    )


def _published_section() -> dict:
    return TextbookSectionContent(
        section_content_id="section-published-intake-1",
        textbook_id="textbook-published-intake",
        section_id="1.1",
        parent_section_id="1",
        order_index=1,
        title="1.1 矩阵乘法",
        original_title="Matrix Multiplication",
        content_zh="矩阵乘法是线性代数的核心主题。",
        content_char_count=15,
    )


def _draft_textbook() -> Textbook:
    return Textbook(
        textbook_id="textbook-draft-intake",
        source_id="source-intake",
        title="未发布矩阵专题",
        original_title="Matrix Topic Draft",
        language="en",
        translated_language="zh",
        description="草稿教材",
        tags=["矩阵"],
        download_url="https://example.test/book-draft.pdf",
        file_asset_url="https://example.test/book-draft.md",
        outline={
            "chapters": [{"chapter_number": 1, "title": "第一章", "sections": []}]
        },
    )


def test_published_textbook_context_excludes_draft_textbooks(db_session: Session):
    create_knowledge_source(db_session, _source())
    published_draft = _published_textbook()
    published_section = _published_section()
    published = upsert_structured_textbook(
        db_session,
        published_draft,
        [published_section],
    )
    published = publish_textbook(db_session, published.textbook_id)
    draft = _draft_textbook()
    db_session.add(draft)
    db_session.commit()

    context = get_published_textbook_context_for_topic(db_session, "矩阵")

    assert published.student_availability_status == "published"
    assert context["gap_id"] is None
    assert context["textbooks"]
    assert all(
        item["textbook_id"] != draft.textbook_id for item in context["textbooks"]
    )
    assert all(
        item["textbook_id"] == published.textbook_id for item in context["textbooks"]
    )


def test_missing_published_textbook_creates_gap(db_session: Session):
    create_knowledge_source(db_session, _source())
    db_session.add(_draft_textbook())
    db_session.commit()

    context = get_published_textbook_context_for_topic(db_session, "矩阵")

    assert context["textbooks"] == []
    assert context["gap_id"] is not None


def test_learning_path_intake_ignores_unconfirmed_source_results(
    tmp_path: Path,
) -> None:
    engine = create_engine(
        postgresql_test_url(tmp_path, "published-only"),
    )
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(_source())
        session.commit()
        context = get_published_textbook_context_for_topic(
            session,
            "数据结构",
            "我想学习数据结构",
        )

    assert context["textbooks"] == []
    assert context["gap_id"] is not None
