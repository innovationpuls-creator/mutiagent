from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_
from sqlalchemy.engine import Connection, Engine
from sqlmodel import Session, select

from app.database import get_engine
from app.models import KnowledgeBaseIngestionJob, Textbook
from app.services.knowledge_base_service import (
    IngestionJobOwnershipLost,
    run_claimed_textbook_source_ingestion,
)

LEASE_DURATION = timedelta(minutes=10)
logger = logging.getLogger("app.worker.knowledge_base")


def claim_next_ingestion_job(
    session: Session, worker_id: str, now: datetime
) -> KnowledgeBaseIngestionJob | None:
    while True:
        job = session.exec(
            select(KnowledgeBaseIngestionJob)
            .where(
                or_(
                    and_(
                        KnowledgeBaseIngestionJob.status == "queued",
                        KnowledgeBaseIngestionJob.available_at <= now,
                    ),
                    and_(
                        KnowledgeBaseIngestionJob.status == "running",
                        KnowledgeBaseIngestionJob.lease_expires_at <= now,
                    ),
                )
            )
            .order_by(
                KnowledgeBaseIngestionJob.available_at,
                KnowledgeBaseIngestionJob.created_at,
            )
            .with_for_update(skip_locked=True)
        ).first()
        if job is None:
            session.rollback()
            return None
        if job.attempt_count >= job.max_attempts:
            _mark_exhausted_job_failed(session, job, now)
            continue

        textbook = session.get(Textbook, job.textbook_id)
        job.status = "running"
        job.attempt_count += 1
        job.worker_id = worker_id
        job.started_at = now
        job.finished_at = None
        job.lease_expires_at = now + LEASE_DURATION
        job.updated_at = now
        job.error_message = ""
        if textbook is not None:
            textbook.ingestion_status = "processing"
            textbook.ingestion_error_message = ""
            session.add(textbook)
        session.add(job)
        session.commit()
        session.refresh(job)
        return job


def run_worker(poll_seconds: float) -> None:
    worker_id = f"worker-{uuid.uuid4().hex}"
    while True:
        with Session(get_engine()) as session:
            job = claim_next_ingestion_job(
                session, worker_id, datetime.now(timezone.utc)
            )
            if job is not None:
                logger.info(
                    "ingestion_job_claimed",
                    extra={"job_id": job.job_id, "request_id": job.request_id},
                )
                try:
                    process_claimed_ingestion_job(session, job)
                except IngestionJobOwnershipLost:
                    logger.warning(
                        "ingestion_job_ownership_lost",
                        extra={"job_id": job.job_id, "request_id": job.request_id},
                    )
                continue
        time.sleep(poll_seconds)


def process_claimed_ingestion_job(
    session: Session,
    job: KnowledgeBaseIngestionJob,
) -> KnowledgeBaseIngestionJob:
    bind = session.get_bind()
    engine = bind.engine if isinstance(bind, Connection) else bind
    heartbeat = _LeaseHeartbeat(engine, job, LEASE_DURATION)
    heartbeat.start()
    try:
        return run_claimed_textbook_source_ingestion(session, job)
    finally:
        heartbeat.stop()


def renew_ingestion_job_lease(
    session: Session,
    job_id: str,
    worker_id: str,
    attempt_count: int,
    now: datetime,
    lease_duration: timedelta,
) -> bool:
    job = session.exec(
        select(KnowledgeBaseIngestionJob)
        .where(
            KnowledgeBaseIngestionJob.job_id == job_id,
            KnowledgeBaseIngestionJob.status == "running",
            KnowledgeBaseIngestionJob.worker_id == worker_id,
            KnowledgeBaseIngestionJob.attempt_count == attempt_count,
            KnowledgeBaseIngestionJob.lease_expires_at > now,
        )
        .with_for_update()
    ).first()
    if job is None:
        session.rollback()
        return False
    job.lease_expires_at = now + lease_duration
    job.updated_at = now
    session.add(job)
    session.commit()
    return True


class _LeaseHeartbeat:
    def __init__(
        self,
        engine: Engine,
        job: KnowledgeBaseIngestionJob,
        lease_duration: timedelta,
    ) -> None:
        if job.worker_id is None:
            raise RuntimeError("ingestion worker ownership missing")
        self._engine = engine
        self._job_id = job.job_id
        self._worker_id = job.worker_id
        self._attempt_count = job.attempt_count
        self._lease_duration = lease_duration
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name=f"ingestion-heartbeat-{job.job_id}",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join()

    def _run(self) -> None:
        interval_seconds = max(self._lease_duration.total_seconds() / 3, 0.01)
        while not self._stop_event.wait(interval_seconds):
            try:
                with Session(self._engine) as session:
                    renewed = renew_ingestion_job_lease(
                        session,
                        self._job_id,
                        self._worker_id,
                        self._attempt_count,
                        datetime.now(timezone.utc),
                        self._lease_duration,
                    )
                if not renewed:
                    return
            except Exception:
                logger.exception(
                    "ingestion_job_lease_renewal_failed",
                    extra={"job_id": self._job_id},
                )
                return


def _mark_exhausted_job_failed(
    session: Session, job: KnowledgeBaseIngestionJob, now: datetime
) -> None:
    message = "教材整理任务已达到最大尝试次数。"
    job.status = "failed"
    job.finished_at = now
    job.lease_expires_at = None
    job.updated_at = now
    job.error_message = message
    textbook = session.get(Textbook, job.textbook_id)
    if textbook is not None:
        textbook.ingestion_status = "failed"
        textbook.ingestion_error_message = message
        session.add(textbook)
    session.add(job)
    session.commit()
