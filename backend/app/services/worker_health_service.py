from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlmodel import Session

from app.models import WorkerHeartbeat

WORKER_HEARTBEAT_NAME = "knowledge-base-ingestion"
WORKER_HEARTBEAT_MAX_AGE = timedelta(minutes=2)


def record_worker_heartbeat(
    session: Session,
    worker_id: str,
    observed_at: datetime,
) -> WorkerHeartbeat:
    heartbeat = session.get(WorkerHeartbeat, WORKER_HEARTBEAT_NAME)
    if heartbeat is None:
        heartbeat = WorkerHeartbeat(
            worker_name=WORKER_HEARTBEAT_NAME,
            worker_id=worker_id,
            last_heartbeat_at=observed_at,
        )
    else:
        heartbeat.worker_id = worker_id
        heartbeat.last_heartbeat_at = observed_at
    session.add(heartbeat)
    session.commit()
    session.refresh(heartbeat)
    return heartbeat


def is_worker_heartbeat_fresh(
    heartbeat: WorkerHeartbeat | None,
    observed_at: datetime,
) -> bool:
    if heartbeat is None:
        return False
    heartbeat_at = _as_utc(heartbeat.last_heartbeat_at)
    return observed_at <= heartbeat_at + WORKER_HEARTBEAT_MAX_AGE


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
