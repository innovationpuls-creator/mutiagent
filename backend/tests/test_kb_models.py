from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.models import Textbook, TextbookSectionContent
from app.schema_upgrades import run_schema_upgrades


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test_kb_models.db'}",
        connect_args={"check_same_thread": False},
    )
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_create_and_query_textbook(db_session: Session):
    textbook = Textbook(
        textbook_id="test_tb_01",
        source_id="test_src_01",
        title="测试教材",
        tags=["测试", "Python"],
        outline={
            "chapters": [{"chapter_number": 1, "title": "第一章", "sections": []}]
        },
        ingestion_status="completed",
        embedding=[0.1, 0.2, 0.3],
    )
    db_session.add(textbook)
    db_session.commit()

    db_session.refresh(textbook)
    assert textbook.title == "测试教材"
    assert textbook.tags == ["测试", "Python"]
    assert textbook.outline["chapters"][0]["title"] == "第一章"
    assert textbook.embedding == [0.1, 0.2, 0.3]


def test_create_and_query_section_content(db_session: Session):
    section = TextbookSectionContent(
        section_content_id="test_sec_01",
        textbook_id="test_tb_01",
        section_id="1.1",
        title="第一节",
        content_zh="这是正文内容",
        content_char_count=6,
    )
    db_session.add(section)
    db_session.commit()

    db_session.refresh(section)
    assert section.title == "第一节"
    assert section.content_zh == "这是正文内容"
    assert section.content_char_count == 6
