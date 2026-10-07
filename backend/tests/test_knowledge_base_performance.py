"""HTTP responsiveness and transaction lifetime contracts for knowledge-base work."""

import asyncio
import builtins
import io
import threading

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy import func, text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, SQLModel, select

from app.api import knowledge_base as api
from app.api.health import create_health_router
from app.core.observability import RequestIdMiddleware
from app.core.security import configure_jwt, create_access_token
from app.database import build_engine, create_session_dependency
from app.models import KnowledgeBaseIngestionJob, KnowledgeGap, Textbook, User
from app.schemas import KnowledgeBaseAgentRequest, KnowledgeBaseSourceResult
from app.services import knowledge_base_service as kb
from tests.fixtures.knowledge_base import enabled_source
from tests.postgres import postgresql_test_url


@pytest.fixture
def engine(tmp_path):
    engine = build_engine(postgresql_test_url(tmp_path, "kb-performance"))
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def http_app(engine, tmp_path, monkeypatch):
    configure_jwt("knowledge-base-performance-test")
    with Session(engine) as session:
        session.add(
            User(uid="admin", username="Admin", identifier="admin", role="admin")
        )
        session.add(enabled_source())
        session.commit()
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    app.include_router(
        api.create_knowledge_base_router(create_session_dependency(engine))
    )
    app.include_router(create_health_router(engine))
    monkeypatch.setenv("KNOWLEDGE_BASE_UPLOAD_DIR", str(tmp_path))
    headers = {
        "Authorization": f"Bearer {create_access_token({'sub': 'admin'})}",
        "X-Request-ID": "kb-performance-upload",
    }
    return app, headers


def test_factory_events_release_connections_and_preserve_payloads(engine, monkeypatch):
    with Session(engine) as session:
        session.add(enabled_source())
        session.add(
            Textbook(textbook_id="book", source_id="source-admitted", title="Topic")
        )
        session.add(KnowledgeGap(gap_id="gap", normalized_topic="Topic"))
        session.commit()

    def search(_query, limit=5):
        return [
            KnowledgeBaseSourceResult(
                source_result_id="result",
                title="Topic",
                source_url="https://example.test/book.pdf",
                source_type="pdf",
                parseability_score=95,
            )
        ]

    monkeypatch.setattr(kb, "search_real_textbook_sources", search)
    actual = []
    for item in kb.stream_knowledge_base_agent_events(lambda: Session(engine), "Topic"):
        assert engine.pool.checkedout() == 0
        actual.append(item)
    with Session(engine) as session:
        expected = list(kb.stream_knowledge_base_agent_events(session, "Topic"))
    assert actual == expected
    assert [item["event"] for item in actual] == [
        "started",
        "context_loaded",
        "source_search_started",
        "source_search_completed",
        "duplicate_check_started",
        "duplicate_check_completed",
        "gap_search_started",
        "gap_search_completed",
        "reply_ready",
        "completed",
    ]
    assert actual[-1]["payload"]["response"]["source_results"][0]["already_imported"]


def test_direct_session_keeps_uncommitted_rows_and_caller_transaction(
    engine, monkeypatch
):
    monkeypatch.setattr(
        kb, "search_real_textbook_sources", lambda *_args, **_kwargs: []
    )
    with Session(engine) as session:
        session.add(KnowledgeGap(gap_id="pending", normalized_topic="Topic"))
        result = kb.run_knowledge_base_agent(session, "Topic")
        assert result.gap_hits[0].gap_id == "pending"
        assert session.in_transaction()
        with Session(engine) as other:
            assert other.get(KnowledgeGap, "pending") is None
        session.rollback()
    with Session(engine) as session:
        assert session.get(KnowledgeGap, "pending") is None


def test_empty_and_closed_streams_do_not_start_search_or_hold_connection(
    engine, monkeypatch
):
    def unexpected(*_args, **_kwargs):
        pytest.fail("empty or closed stream must not search")

    monkeypatch.setattr(kb, "search_real_textbook_sources", unexpected)
    empty = list(kb.stream_knowledge_base_agent_events(unexpected, " "))
    assert [item["event"] for item in empty] == ["started", "completed"]
    stream = kb.stream_knowledge_base_agent_events(lambda: Session(engine), "Topic")
    assert next(stream)["event"] == "started"
    assert next(stream)["event"] == "context_loaded"
    assert next(stream)["event"] == "source_search_started"
    stream.close()
    assert engine.pool.checkedout() == 0


def test_http_stream_closes_inner_generator(http_app, engine, monkeypatch):
    closed = threading.Event()

    def events(*_args):
        try:
            yield {"event": "started", "payload": {}}
            yield {"event": "completed", "payload": {}}
        finally:
            closed.set()

    monkeypatch.setattr(api, "stream_knowledge_base_agent_events", events)
    app, _headers = http_app
    route = next(r for r in app.routes if r.path.endswith("/agent/stream"))

    async def exercise():
        with Session(engine) as session:
            response = route.endpoint(
                KnowledgeBaseAgentRequest(message="Topic"), None, session
            )
        await anext(response.body_iterator)
        await response.body_iterator.aclose()
        assert closed.is_set()

    asyncio.run(exercise())


def test_http_query_failure_releases_connection_and_keeps_error_event(
    http_app, engine, monkeypatch
):
    def fail(session):
        session.execute(text("SELECT 1"))
        raise ValueError("query failed")

    monkeypatch.setattr(kb, "_knowledge_base_counts", fail)
    app, headers = http_app

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/admin/knowledge-base/agent/stream",
                headers=headers,
                json={"message": "Topic"},
            )
            assert response.status_code == 200
            assert (
                "event: error" in response.text
                and '"recoverable": true' in response.text
            )
            assert engine.pool.checkedout() == 0
            assert (await client.get("/api/health/ready")).status_code == 200

    asyncio.run(exercise())


@pytest.mark.parametrize("streaming", [False, True])
def test_35_http_agents_release_connections_during_search(
    http_app, engine, monkeypatch, streaming
):
    ready, release = threading.Event(), threading.Event()
    lock = threading.Lock()
    arrivals = 0

    def search(_query, limit=5):
        nonlocal arrivals
        with lock:
            arrivals += 1
            if arrivals == 35:
                ready.set()
        assert release.wait(15)
        return []

    monkeypatch.setattr(kb, "search_real_textbook_sources", search)
    app, headers = http_app

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            path = "/api/admin/knowledge-base/agent" + ("/stream" if streaming else "")
            tasks = [
                asyncio.create_task(
                    client.post(path, headers=headers, json={"message": "Topic"})
                )
                for _ in range(35)
            ]
            try:
                assert await asyncio.to_thread(ready.wait, 10)
                assert engine.pool.checkedout() == 0
                assert (
                    await asyncio.wait_for(client.get("/api/health/ready"), 2)
                ).status_code == 200
            finally:
                release.set()
                responses = await asyncio.gather(*tasks)
            assert all(r.status_code == 200 for r in responses)
            if streaming:
                assert all(
                    "event: completed" in r.text and "event: error" not in r.text
                    for r in responses
                )
            assert engine.pool.checkedout() == 0

    asyncio.run(exercise())


@pytest.mark.parametrize("cancel", [False, True])
def test_upload_write_does_not_block_loop_and_owns_session(
    http_app, engine, monkeypatch, tmp_path, cancel
):
    ready, release = threading.Event(), threading.Event()
    original_open = builtins.open
    write_threads = []
    files = []

    class Writer:
        def __init__(self, *args, **kwargs):
            self.file = original_open(*args, **kwargs)
            files.append(self.file)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.file.close()

        def write(self, data):
            write_threads.append(threading.get_ident())
            ready.set()
            assert release.wait(10)
            return self.file.write(data)

    monkeypatch.setattr(kb, "open", Writer, raising=False)
    app, headers = http_app

    async def exercise():
        loop_thread = threading.get_ident()
        timer = threading.Timer(5, release.set)
        timer.start()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            task = asyncio.create_task(
                client.post(
                    "/api/admin/knowledge-base/uploads",
                    headers=headers,
                    data={"title": "Topic"},
                    files={"file": ("book.pdf", b"pdf", "application/pdf")},
                )
            )
            try:
                assert await asyncio.to_thread(ready.wait, 4)
                assert (
                    await asyncio.wait_for(client.get("/api/health/ready"), 2)
                ).status_code == 200
                await asyncio.sleep(0.03)
                assert not release.is_set()
                assert (
                    write_threads == [write_threads[0]]
                    and write_threads[0] != loop_thread
                )
                if cancel:
                    task.cancel()
            finally:
                release.set()
                timer.cancel()
                result = await asyncio.gather(task, return_exceptions=True)
            if not cancel:
                assert result[0].status_code == 201
            for _ in range(100):
                if engine.pool.checkedout() == 0:
                    break
                await asyncio.sleep(0.01)
            assert engine.pool.checkedout() == 0

    asyncio.run(exercise())
    assert all(file.closed for file in files)
    with Session(engine) as session:
        job = session.exec(select(KnowledgeBaseIngestionJob)).one()
        book = session.get(Textbook, job.textbook_id)
        assert job.request_id == "kb-performance-upload"
        assert book.download_url.startswith(str(tmp_path))


@pytest.mark.parametrize(
    "failure", ["disk", "first_commit", "job_commit", "no_source", "extension"]
)
def test_upload_failures_release_resources_and_preserve_commit_boundaries(
    http_app, engine, monkeypatch, failure
):
    app, headers = http_app
    if failure == "no_source":
        with Session(engine) as session:
            source = session.get(type(enabled_source()), "source-admitted")
            session.delete(source)
            session.commit()
    if failure == "disk":

        def fail_open(*_args, **_kwargs):
            raise OSError("disk failed")

        monkeypatch.setattr(kb, "open", fail_open, raising=False)
    if failure in {"first_commit", "job_commit"}:
        original_commit = Session.commit
        row_type = Textbook if failure == "first_commit" else KnowledgeBaseIngestionJob

        def fail_commit(session):
            if any(isinstance(row, row_type) for row in session.new):
                raise SQLAlchemyError("commit failed")
            return original_commit(session)

        monkeypatch.setattr(Session, "commit", fail_commit)

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            extension = "txt" if failure == "extension" else "pdf"
            response = await client.post(
                "/api/admin/knowledge-base/uploads",
                headers=headers,
                data={"title": "Topic"},
                files={"file": (f"book.{extension}", b"pdf", "application/pdf")},
            )
            assert response.status_code == (
                400 if failure in {"no_source", "extension"} else 500
            )
            assert engine.pool.checkedout() == 0

    asyncio.run(exercise())
    with Session(engine) as session:
        assert session.exec(select(func.count()).select_from(Textbook)).one() == (
            1 if failure == "job_commit" else 0
        )
        assert (
            session.exec(
                select(func.count()).select_from(KnowledgeBaseIngestionJob)
            ).one()
            == 0
        )


@pytest.mark.parametrize("payload, rejected", [(b"1234", False), (b"12345", True)])
def test_unknown_upload_size_enforces_streamed_limit(monkeypatch, payload, rejected):
    monkeypatch.setattr(api, "MAX_TEXTBOOK_UPLOAD_BYTES", 4)

    class Upload:
        size = None
        file = io.BytesIO(payload)

        async def read(self, size):
            return self.file.read(size)

    file = Upload()
    api._validate_textbook_upload_size(file)
    if rejected:
        with pytest.raises(HTTPException) as error:
            asyncio.run(api._read_textbook_upload(file))
        assert error.value.status_code == 413
    else:
        assert asyncio.run(api._read_textbook_upload(file)) == payload
