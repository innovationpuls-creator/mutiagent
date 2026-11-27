"""Regression contracts for database lifetime and bounded work."""

import threading
from datetime import datetime, timezone

import pytest
from sqlalchemy import event
from sqlmodel import Session, SQLModel

from app.database import build_engine
from app.models import KnowledgeBaseIngestionJob, KnowledgeGap, Textbook, User
from app.services import knowledge_base_service as kb
from app.workers.knowledge_base_worker import claim_next_ingestion_job
from tests.postgres import postgresql_test_url


@pytest.fixture
def engine(tmp_path):
    engine = build_engine(postgresql_test_url(tmp_path, "performance"))
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


def test_search_published_textbooks_preserves_ranking(engine):
    with Session(engine) as session:
        for key, title, tags, published in (
            ("title", "Python", [], True),
            ("tags", "Other", ["Python", "Python", "Python"], True),
            ("hidden", "Python", ["Python"] * 10, False),
        ):
            session.add(
                Textbook(
                    textbook_id=key,
                    source_id="source",
                    title=title,
                    tags=tags,
                    student_availability_status="published" if published else "draft",
                )
            )
        session.commit()
        assert [
            row.textbook_id
            for row in kb.search_published_textbooks(session, "python", 10)
        ] == ["tags", "title"]


def test_two_workers_claim_distinct_jobs_before_first_commit(engine):
    with Session(engine) as session:
        for index in range(2):
            session.add(
                Textbook(
                    textbook_id=f"book-{index}", source_id="source", title="Worker"
                )
            )
        session.commit()
        for index in range(2):
            session.add(
                KnowledgeBaseIngestionJob(
                    job_id=f"job-{index}", textbook_id=f"book-{index}"
                )
            )
        session.commit()
    selected, release = threading.Event(), threading.Event()
    results, errors = [], []

    def pause_first(_conn, _cursor, statement, *_args):
        if (
            threading.current_thread().name == "first-claim"
            and "FOR UPDATE" in statement
        ):
            selected.set()
            if not release.wait(10):
                raise TimeoutError("second worker did not finish")

    def first():
        try:
            with Session(engine) as session:
                results.append(
                    claim_next_ingestion_job(
                        session, "first", datetime.now(timezone.utc)
                    )
                )
        except BaseException as error:
            errors.append(error)

    event.listen(engine, "after_cursor_execute", pause_first)
    thread = threading.Thread(target=first, name="first-claim")
    thread.start()
    try:
        assert selected.wait(5)
        with Session(engine) as session:
            second = claim_next_ingestion_job(
                session, "second", datetime.now(timezone.utc)
            )
        assert second is not None
    finally:
        release.set()
        thread.join(10)
        event.remove(engine, "after_cursor_execute", pause_first)
    assert not errors
    assert not thread.is_alive()
    assert results[0].job_id != second.job_id


def test_current_upgrade_skips_jsonb_alter_and_unchanged_follow_counts(engine):
    from app.schema_upgrades import run_schema_upgrades

    with Session(engine) as session:
        session.add(
            KnowledgeGap(gap_id="stale", normalized_topic="stale", follow_count=9)
        )
        session.commit()
    updates, alters = [], []

    def observe(_conn, cursor, statement, *_args):
        lowered = statement.lower()
        if "update knowledgegap" in lowered and "follow_count" in lowered:
            updates.append(cursor.rowcount)
        if "alter column" in lowered and "type jsonb" in lowered:
            alters.append(statement)

    event.listen(engine, "after_cursor_execute", observe)
    try:
        run_schema_upgrades(engine)
        run_schema_upgrades(engine)
    finally:
        event.remove(engine, "after_cursor_execute", observe)
    assert updates == [1, 0]
    assert alters == []
    with Session(engine) as session:
        assert session.get(KnowledgeGap, "stale").follow_count == 0


def test_slice_unicode_crlf_toc_missing_and_repeated_headings():
    from app.services.document_parser_service import locate_and_slice_sections

    markdown = "重复 …… 1\r\n## 重复\r\n正文🙂\r\n## 重复\r\n尾部é"
    outline = {
        "chapters": [
            {
                "sections": [
                    {"section_id": "a", "title": "重复"},
                    {"section_id": "missing", "title": "不存在"},
                    {"section_id": "b", "title": "重复"},
                ]
            }
        ]
    }
    assert locate_and_slice_sections(markdown, outline) == {
        "a": "## 重复\r\n正文🙂",
        "b": "## 重复\r\n尾部é",
    }


def test_report_counts_all_history_but_loads_recent_evidence(engine):
    from datetime import timedelta

    from app.models import ChapterQuiz, ChapterQuizAttempt
    from app.services.growth_report_context import build_report_context

    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        session.add(User(uid="owner", username="Owner", identifier="owner"))
        session.add(User(uid="other", username="Other", identifier="other"))
        session.commit()
        for index in range(40):
            session.add(
                ChapterQuiz(
                    quiz_id=f"quiz-{index}",
                    user_uid="owner",
                    course_node_id="course",
                    chapter_id=str(index),
                )
            )
        session.add(
            ChapterQuiz(
                quiz_id="secret",
                user_uid="other",
                course_node_id="course",
                chapter_id="secret",
            )
        )
        session.commit()
        for index in range(40):
            for order, score in enumerate((40, 80)):
                session.add(
                    ChapterQuizAttempt(
                        attempt_id=f"attempt-{index}-{order}",
                        quiz_id=f"quiz-{index}",
                        user_uid="owner",
                        score=score,
                        created_at=now + timedelta(seconds=index * 2 + order),
                    )
                )
        session.add(
            ChapterQuizAttempt(
                attempt_id="secret", quiz_id="secret", user_uid="other", score=100
            )
        )
        session.commit()
        context = build_report_context(session, "owner")
        quizzes = [item for item in context.evidence.values() if item.kind == "quiz"]
        assert context.stats.attempts == 80
        assert context.stats.tested_chapters == 40
        assert len(quizzes) == 30
        assert quizzes[0].id == "quiz:quiz-39"
        assert quizzes[-1].id == "quiz:quiz-10"
        assert all("首次 40 分，最近 80 分" in item.detail for item in quizzes)
