from __future__ import annotations

from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.models import Textbook
from app.services.knowledge_base_service import (
    complete_knowledge_base_ingestion_job,
    create_knowledge_base_ingestion_job,
    fail_knowledge_base_ingestion_job,
    run_textbook_source_ingestion,
    start_knowledge_base_ingestion_job,
)
from tests.fixtures.knowledge_base import enabled_source, textbook


def _engine(tmp_path: Path):
    return create_engine(
        f"sqlite:///{tmp_path / 'knowledge-base-ingestion-job.db'}",
        connect_args={"check_same_thread": False},
    )


def _seed_textbook(session: Session) -> None:
    session.add(enabled_source())
    session.add(textbook(textbook_id="textbook-job", title="整理任务教材"))
    session.commit()


def test_create_ingestion_job_records_queued_job_without_starting_textbook(
    tmp_path: Path,
) -> None:
    engine = _engine(tmp_path)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        _seed_textbook(session)

        job = create_knowledge_base_ingestion_job(session, "textbook-job")

        stored_textbook = session.get(Textbook, "textbook-job")

    assert job.textbook_id == "textbook-job"
    assert job.job_type == "agent_organize"
    assert job.status == "queued"
    assert job.started_at is None
    assert job.finished_at is None
    assert stored_textbook is not None
    assert stored_textbook.ingestion_status == "not_started"


def test_ingestion_job_running_then_completed_sets_textbook_ready_for_review(
    tmp_path: Path,
) -> None:
    engine = _engine(tmp_path)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        _seed_textbook(session)
        job = create_knowledge_base_ingestion_job(session, "textbook-job")

        running = start_knowledge_base_ingestion_job(session, job.job_id)
        assert running.status == "running"
        assert running.started_at is not None
        assert running.finished_at is None

        completed = complete_knowledge_base_ingestion_job(session, job.job_id)
        stored_textbook = session.get(Textbook, "textbook-job")

    assert completed.status == "completed"
    assert completed.finished_at is not None
    assert completed.error_message == ""
    assert stored_textbook is not None
    assert stored_textbook.ingestion_status == "ready_for_outline_review"
    assert stored_textbook.ingestion_error_message == ""


def test_ingestion_job_running_then_failed_records_error_on_textbook(
    tmp_path: Path,
) -> None:
    engine = _engine(tmp_path)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        _seed_textbook(session)
        job = create_knowledge_base_ingestion_job(session, "textbook-job")
        start_knowledge_base_ingestion_job(session, job.job_id)

        failed = fail_knowledge_base_ingestion_job(
            session,
            job.job_id,
            "教材解析失败。",
        )
        stored_textbook = session.get(Textbook, "textbook-job")

    assert failed.status == "failed"
    assert failed.finished_at is not None
    assert failed.error_message == "教材解析失败。"
    assert stored_textbook is not None
    assert stored_textbook.ingestion_status == "failed"
    assert stored_textbook.ingestion_error_message == "教材解析失败。"


def test_ingestion_job_rejects_invalid_transitions(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        _seed_textbook(session)
        job = create_knowledge_base_ingestion_job(session, "textbook-job")

        with pytest.raises(ValueError, match="只有 running 整理任务可以完成。"):
            complete_knowledge_base_ingestion_job(session, job.job_id)

        start_knowledge_base_ingestion_job(session, job.job_id)

        with pytest.raises(ValueError, match="只有 queued 整理任务可以开始。"):
            start_knowledge_base_ingestion_job(session, job.job_id)


def test_run_textbook_source_ingestion_fills_outline_and_sections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _engine(tmp_path)
    SQLModel.metadata.create_all(engine)

    def fake_parse_source(
        source_url: str, language: str
    ) -> tuple[dict, dict[str, str]]:
        assert source_url == "https://opendatastructures.org/ods-python.pdf"
        assert language == "en"
        return (
            {
                "chapters": [
                    {
                        "chapter_number": 1,
                        "title": "Chapter 1",
                        "sections": [
                            {"section_id": "sec_1_1", "title": "Arrays"},
                            {"section_id": "sec_1_2", "title": "Linked Lists"},
                        ],
                    }
                ]
            },
            {
                "sec_1_1": "Arrays original content.",
                "sec_1_2": "Linked lists original content.",
            },
        )

    monkeypatch.setattr(
        "app.services.knowledge_base_service.parse_textbook_source_to_sections",
        fake_parse_source,
    )
    monkeypatch.setattr(
        "app.services.knowledge_base_service.translate_section_content_to_zh",
        lambda content: f"中文译写：{content}",
    )

    with Session(engine) as session:
        session.add(enabled_source())
        session.add(
            Textbook(
                textbook_id="textbook-source-job",
                source_id="source-admitted",
                title="Open Data Structures",
                original_title="Open Data Structures",
                language="en",
                translated_language="zh",
                description="",
                tags=[],
                download_url="https://opendatastructures.org/ods-python.pdf",
                file_asset_url="https://opendatastructures.org/ods-python.pdf",
                outline={},
                ingestion_status="not_started",
                outline_review_status="unreviewed",
                student_availability_status="draft",
            )
        )
        session.commit()
        job = create_knowledge_base_ingestion_job(session, "textbook-source-job")

        completed = run_textbook_source_ingestion(session, job.job_id)
        stored = session.get(Textbook, "textbook-source-job")

    assert completed.status == "completed"
    assert stored is not None
    assert stored.ingestion_status == "ready_for_outline_review"
    assert stored.outline["chapters"][0]["sections"][0]["section_id"] == "sec_1_1"
