from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.models import Textbook
from app.schema_upgrades import run_schema_upgrades
from app.services.knowledge_base_service import hybrid_search_textbooks
from tests.postgres import postgresql_test_url


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(
        postgresql_test_url(tmp_path, "test_hybrid"),
    )
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_hybrid_search_textbooks(db_session: Session):
    tb1 = Textbook(
        textbook_id="tb_1",
        source_id="src_1",
        title="FastAPI 高性能开发",
        tags=["FastAPI", "Python"],
        status="success",
        student_availability_status="published",
    )
    tb2 = Textbook(
        textbook_id="tb_2",
        source_id="src_2",
        title="Django Web 教程",
        tags=["Django", "Python"],
        status="success",
        student_availability_status="published",
    )
    db_session.add(tb1)
    db_session.add(tb2)
    db_session.commit()

    results = hybrid_search_textbooks(db_session, "FastAPI", limit=10)
    assert len(results) >= 1
    assert results[0].title == "FastAPI 高性能开发"
