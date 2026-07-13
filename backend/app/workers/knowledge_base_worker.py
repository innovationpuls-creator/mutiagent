from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_
from sqlmodel import Session, select

from app.database import get_engine
from app.models import KnowledgeBaseIngestionJob, Textbook
from app.services.knowledge_base_service import run_claimed_textbook_source_ingestion

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
                run_claimed_textbook_source_ingestion(session, job)
                continue
        time.sleep(poll_seconds)


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
