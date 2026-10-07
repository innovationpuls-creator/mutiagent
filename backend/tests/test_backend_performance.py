"""Regression contracts for database lifetime and bounded work."""

import asyncio
import threading
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import event
from sqlmodel import Session, SQLModel

from app.database import build_engine, get_engine
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


def test_search_skips_embeddings_and_preserves_ranking(engine, monkeypatch):
    def unexpected():
        pytest.fail("unsupported hybrid search must not request embeddings")

    monkeypatch.setattr(kb, "get_embeddings_client", unexpected)
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
            row.textbook_id for row in kb.hybrid_search_textbooks(session, "python", 10)
        ] == ["tags", "title"]


def test_hybrid_failure_preserves_callers_transaction(engine, monkeypatch):
    class Embeddings:
        def embed_query(self, _query):
            return [0.0, 1.0]

    monkeypatch.setattr(kb, "_supports_hybrid_search", lambda _session: True)
    monkeypatch.setattr(kb, "get_embeddings_client", lambda: Embeddings())
    with Session(engine) as session:
        session.add(
            Textbook(
                textbook_id="book",
                source_id="source",
                title="Python",
                student_availability_status="published",
            )
        )
        session.commit()
        session.add(KnowledgeGap(gap_id="pending", normalized_topic="pending"))
        assert kb.hybrid_search_textbooks(session, "Python")[0].textbook_id == "book"
        session.commit()
    with Session(engine) as session:
        assert session.get(KnowledgeGap, "pending") is not None


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


def test_35_report_streams_release_connections_during_model_wait(tmp_path, monkeypatch):
    from app.core.security import create_access_token
    from app.main import create_app

    app = create_app(database_url=postgresql_test_url(tmp_path, "report-concurrency"))
    engine = get_engine()
    with Session(engine) as session:
        session.add(
            User(uid="concurrent", username="Concurrent", identifier="concurrent")
        )
        session.commit()
    token = create_access_token({"sub": "concurrent"})

    async def exercise():
        ready, release = asyncio.Event(), asyncio.Event()
        arrivals = 0

        class Model:
            def with_structured_output(self, schema):
                class Structured:
                    async def ainvoke(self, _messages):
                        nonlocal arrivals
                        if schema.__name__ == "EvidenceSelection":
                            arrivals += 1
                            if arrivals == 35:
                                ready.set()
                            await release.wait()
                            return {"requests": []}
                        return {
                            "overview": "等待建立学习记录",
                            "strengths": [],
                            "improvements": [],
                            "actions": [],
                        }

                return Structured()

        monkeypatch.setattr("app.api.branch.get_worker_llm", lambda: Model())
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            tasks = [
                asyncio.create_task(
                    client.post(
                        "/api/branch/canopy/report/stream",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                )
                for _ in range(35)
            ]
            try:
                await asyncio.wait_for(ready.wait(), 15)
                assert engine.pool.checkedout() == 0
                health = await asyncio.wait_for(client.get("/api/health/ready"), 2)
                assert health.status_code == 200
            finally:
                release.set()
                responses = await asyncio.gather(*tasks)
            assert all(
                response.status_code == 200
                and "report_completed" in response.text
                and "report_error" not in response.text
                for response in responses
            )
            assert engine.pool.checkedout() == 0

    try:
        asyncio.run(exercise())
    finally:
        engine.dispose()


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


def test_chat_releases_connection_and_persists_before_completion(engine, monkeypatch):
    from app.api.orchestration import _stream_chat_events
    from app.database import request_engine_context
    from app.models import ConversationSession
    from app.services.conversation_session_service import load_or_create_session

    with Session(engine) as session:
        session.add(User(uid="chat", username="Chat", identifier="chat"))
        session.commit()
        load_or_create_session(session, "chat-session", "chat")

    async def fake_events(_state):
        assert get_engine() is engine
        assert engine.pool.checkedout() == 0
        await asyncio.sleep(0.01)
        yield {"event": "message_completed", "full_text": "回复"}
        yield {"event": "session_completed", "session_id": "chat-session"}

    monkeypatch.setattr(
        "app.api.orchestration.stream_orchestration_events", fake_events
    )

    async def exercise():
        previous = request_engine_context.get()
        with Session(engine) as session:
            async for message in _stream_chat_events(
                "chat-session", "chat", "你好", session
            ):
                if "event: message_completed" in message:
                    with Session(engine) as reader:
                        row = reader.get(ConversationSession, "chat-session")
                        assert [item["type"] for item in row.messages] == [
                            "human",
                            "ai",
                        ]
        assert request_engine_context.get() is previous
        assert engine.pool.checkedout() == 0

    asyncio.run(exercise())


def test_chat_stream_can_be_closed_by_another_task(engine):
    from app.api.orchestration import _stream_chat_events
    from app.database import request_engine_context

    async def exercise():
        previous = request_engine_context.get()
        with Session(engine) as session:
            iterator = _stream_chat_events("unused", "unused", "你好", session)
            assert "session_started" in await anext(iterator)
            assert request_engine_context.get() is previous
            await asyncio.create_task(iterator.aclose())
            assert request_engine_context.get() is previous
        assert engine.pool.checkedout() == 0

    asyncio.run(exercise())
