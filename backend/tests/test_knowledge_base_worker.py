from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import KnowledgeBaseIngestionJob, Textbook
from app.services.knowledge_base_service import (
    create_knowledge_base_ingestion_job,
    run_claimed_textbook_source_ingestion,
)
from app.workers.knowledge_base_worker import (
    claim_next_ingestion_job,
    renew_ingestion_job_lease,
)
from tests.fixtures.knowledge_base import enabled_source, textbook
from tests.postgres import postgresql_test_url


def _engine(tmp_path: Path):
    engine = create_engine(postgresql_test_url(tmp_path, "knowledge-base-worker"))
    SQLModel.metadata.create_all(engine)
    return engine


def _seed_job(session: Session) -> KnowledgeBaseIngestionJob:
    session.add(enabled_source())
    session.add(textbook(textbook_id="textbook-worker", title="Worker 教材"))
    session.commit()
    return create_knowledge_base_ingestion_job(session, "textbook-worker")


def _parsed_textbook() -> tuple[dict, dict[str, str]]:
    return (
        {
            "chapters": [
                {
                    "chapter_number": 1,
                    "title": "Worker chapter",
                    "sections": [{"section_id": "sec_1", "title": "Worker section"}],
                }
            ]
        },
        {"sec_1": "Worker content"},
    )


def test_claim_uses_skip_locked_and_only_one_worker_gets_job(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    now = datetime.now(timezone.utc) + timedelta(minutes=1)
    with Session(engine) as seed_session:
        job = _seed_job(seed_session)

    with Session(engine) as locking_session, Session(engine) as claiming_session:
        locked = locking_session.exec(
            select(KnowledgeBaseIngestionJob)
            .where(KnowledgeBaseIngestionJob.job_id == job.job_id)
            .with_for_update()
        ).one()
        assert locked.job_id == job.job_id

        assert claim_next_ingestion_job(claiming_session, "worker-2", now) is None

    with Session(engine) as first_session, Session(engine) as second_session:
        claimed = claim_next_ingestion_job(first_session, "worker-1", now)
        repeated = claim_next_ingestion_job(second_session, "worker-2", now)

    assert claimed is not None
    assert claimed.job_id == job.job_id
    assert claimed.worker_id == "worker-1"
    assert claimed.attempt_count == 1
    assert claimed.lease_expires_at is not None
    assert repeated is None


def test_claim_reclaims_expired_lease_before_attempt_limit(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    now = datetime.now(timezone.utc) + timedelta(minutes=1)
    with Session(engine) as session:
        job = _seed_job(session)
        job.status = "running"
        job.worker_id = "dead-worker"
        job.attempt_count = 1
        job.max_attempts = 3
        job.lease_expires_at = now - timedelta(seconds=1)
        session.add(job)
        session.commit()

        reclaimed = claim_next_ingestion_job(session, "worker-new", now)

    assert reclaimed is not None
    assert reclaimed.worker_id == "worker-new"
    assert reclaimed.attempt_count == 2
    assert reclaimed.status == "running"


def test_claim_does_not_take_over_unexpired_running_job(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    now = datetime.now(timezone.utc) + timedelta(minutes=1)
    with Session(engine) as session:
        job = _seed_job(session)
        job.status = "running"
        job.worker_id = "active-worker"
        job.attempt_count = 1
        job.lease_expires_at = now + timedelta(seconds=1)
        session.add(job)
        session.commit()

        claimed = claim_next_ingestion_job(session, "worker-new", now)

    assert claimed is None


def test_claimed_job_execution_completes_and_clears_lease(
    tmp_path: Path, monkeypatch
) -> None:
    engine = _engine(tmp_path)
    now = datetime.now(timezone.utc) + timedelta(minutes=1)
    with Session(engine) as session:
        _seed_job(session)
        claimed = claim_next_ingestion_job(session, "worker-1", now)
        assert claimed is not None
        monkeypatch.setattr(
            "app.services.knowledge_base_service.parse_textbook_source_to_sections",
            lambda *_args: _parsed_textbook(),
        )

        completed = run_claimed_textbook_source_ingestion(session, claimed)

    assert completed.status == "completed"
    assert completed.lease_expires_at is None
    assert completed.updated_at == completed.finished_at


def test_old_worker_cannot_complete_after_job_is_reclaimed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _engine(tmp_path)
    first_claim_time = datetime.now(timezone.utc) + timedelta(minutes=1)
    with Session(engine) as session:
        _seed_job(session)
        old_claim = claim_next_ingestion_job(session, "worker-old", first_claim_time)
        assert old_claim is not None

    reclaim_time = first_claim_time + timedelta(minutes=11)
    with Session(engine) as session:
        reclaimed = claim_next_ingestion_job(session, "worker-new", reclaim_time)
        assert reclaimed is not None
        assert reclaimed.attempt_count == 2
        new_worker_lease = reclaimed.lease_expires_at

    with Session(engine) as session:
        renewed = renew_ingestion_job_lease(
            session,
            old_claim.job_id,
            "worker-old",
            1,
            reclaim_time,
            timedelta(minutes=10),
        )
        stored_after_renewal = session.get(KnowledgeBaseIngestionJob, old_claim.job_id)
    assert renewed is False
    assert stored_after_renewal is not None
    assert stored_after_renewal.lease_expires_at == new_worker_lease

    monkeypatch.setattr(
        "app.services.knowledge_base_service.parse_textbook_source_to_sections",
        lambda *_args: _parsed_textbook(),
    )
    with Session(engine) as session:
        with pytest.raises(RuntimeError, match="worker ownership"):
            run_claimed_textbook_source_ingestion(session, old_claim)

    with Session(engine) as session:
        stored_job = session.get(KnowledgeBaseIngestionJob, old_claim.job_id)
        stored_textbook = session.get(Textbook, old_claim.textbook_id)
    assert stored_job is not None
    assert stored_job.status == "running"
    assert stored_job.worker_id == "worker-new"
    assert stored_job.attempt_count == 2
    assert stored_textbook is not None
    assert stored_textbook.outline == {}
    assert stored_textbook.ingestion_status == "processing"


def test_old_worker_cannot_fail_after_job_is_reclaimed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _engine(tmp_path)
    first_claim_time = datetime.now(timezone.utc) + timedelta(minutes=1)
    with Session(engine) as session:
        _seed_job(session)
        old_claim = claim_next_ingestion_job(session, "worker-old", first_claim_time)
        assert old_claim is not None

    reclaim_time = first_claim_time + timedelta(minutes=11)
    with Session(engine) as session:
        reclaimed = claim_next_ingestion_job(session, "worker-new", reclaim_time)
        assert reclaimed is not None

    monkeypatch.setattr(
        "app.services.knowledge_base_service.parse_textbook_source_to_sections",
        lambda *_args: (_ for _ in ()).throw(ValueError("parse failed")),
    )
    with Session(engine) as session:
        with pytest.raises(RuntimeError, match="worker ownership"):
            run_claimed_textbook_source_ingestion(session, old_claim)

    with Session(engine) as session:
        stored_job = session.get(KnowledgeBaseIngestionJob, old_claim.job_id)
        stored_textbook = session.get(Textbook, old_claim.textbook_id)
    assert stored_job is not None
    assert stored_job.status == "running"
    assert stored_job.worker_id == "worker-new"
    assert stored_job.error_message == ""
    assert stored_textbook is not None
    assert stored_textbook.ingestion_status == "processing"
    assert stored_textbook.ingestion_error_message == ""


def test_long_running_job_renews_lease_during_synchronous_parse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.workers import knowledge_base_worker as worker_module

    engine = _engine(tmp_path)
    lease_duration = timedelta(milliseconds=600)
    monkeypatch.setattr(worker_module, "LEASE_DURATION", lease_duration)
    renewed_event = threading.Event()
    renew_lease = worker_module.renew_ingestion_job_lease

    def track_renewal(*args, **kwargs) -> bool:
        renewed = renew_lease(*args, **kwargs)
        if renewed:
            renewed_event.set()
        return renewed

    monkeypatch.setattr(worker_module, "renew_ingestion_job_lease", track_renewal)
    with Session(engine) as session:
        _seed_job(session)
        claimed = claim_next_ingestion_job(
            session,
            "worker-heartbeat",
            datetime.now(timezone.utc) + timedelta(milliseconds=10),
        )
        assert claimed is not None
        initial_lease = claimed.lease_expires_at
        assert initial_lease is not None

        def slow_parse(*_args) -> tuple[dict, dict[str, str]]:
            assert renewed_event.wait(timeout=2)
            with Session(engine) as check_session:
                renewed = check_session.get(KnowledgeBaseIngestionJob, claimed.job_id)
            assert renewed is not None
            assert renewed.lease_expires_at is not None
            assert renewed.lease_expires_at > initial_lease
            return _parsed_textbook()

        monkeypatch.setattr(
            "app.services.knowledge_base_service.parse_textbook_source_to_sections",
            slow_parse,
        )
        completed = worker_module.process_claimed_ingestion_job(session, claimed)

    assert completed.status == "completed"


def test_claim_marks_exhausted_expired_job_failed(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    now = datetime.now(timezone.utc) + timedelta(minutes=1)
    with Session(engine) as session:
        job = _seed_job(session)
        job.status = "running"
        job.worker_id = "dead-worker"
        job.attempt_count = 3
        job.max_attempts = 3
        job.lease_expires_at = now - timedelta(seconds=1)
        session.add(job)
        session.commit()

        claimed = claim_next_ingestion_job(session, "worker-new", now)
        stored_job = session.get(KnowledgeBaseIngestionJob, job.job_id)
        stored_textbook = session.get(Textbook, "textbook-worker")

    assert claimed is None
    assert stored_job is not None
    assert stored_job.status == "failed"
    assert stored_job.finished_at == now.astimezone().replace(tzinfo=None)
    assert stored_textbook is not None
    assert stored_textbook.ingestion_status == "failed"
