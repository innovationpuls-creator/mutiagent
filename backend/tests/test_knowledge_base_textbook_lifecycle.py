from __future__ import annotations

from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.models import KnowledgeSource, Textbook
from app.schema_upgrades import run_schema_upgrades
from tests.postgres import postgresql_test_url


@pytest.fixture
def db_session(tmp_path: Path):
    engine = create_engine(
        postgresql_test_url(tmp_path, "test_knowledge_base_textbook_lifecycle"),
    )
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _source(source_id: str = "source-lifecycle") -> KnowledgeSource:
    return KnowledgeSource(
        source_id=source_id,
        name="生命周期来源",
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


def _textbook(textbook_id: str = "textbook-lifecycle") -> Textbook:
    return Textbook(
        textbook_id=textbook_id,
        source_id="source-lifecycle",
        title="矩阵专题",
        original_title="Matrix Topic",
        language="en",
        translated_language="zh",
        description="覆盖矩阵乘法",
        tags=["矩阵"],
        download_url="https://example.test/book.pdf",
        file_asset_url="https://example.test/book.md",
        outline={"sections": [{"section_id": "1.1", "title": "矩阵乘法"}]},
    )


def test_textbook_defaults_start_in_draft_reviewable_state(db_session: Session):
    db_session.add(_source())

    textbook = _textbook()
    db_session.add(textbook)
    db_session.commit()
    db_session.refresh(textbook)

    assert textbook.ingestion_status == "not_started"
    assert textbook.outline_review_status == "unreviewed"
    assert textbook.student_availability_status == "draft"
    assert textbook.published_at is None
    assert textbook.unpublished_at is None
    assert textbook.archived_at is None


def test_textbook_created_for_first_phase_keeps_publish_gate_closed(
    db_session: Session,
):
    db_session.add(_source())

    textbook = _textbook()
    db_session.add(textbook)
    db_session.commit()
    db_session.refresh(textbook)

    assert textbook.student_availability_status != "published"
    assert textbook.ingestion_status in {
        "not_started",
        "processing",
        "failed",
        "ready_for_outline_review",
        "completed",
    }
    assert textbook.outline_review_status in {"unreviewed", "approved"}
