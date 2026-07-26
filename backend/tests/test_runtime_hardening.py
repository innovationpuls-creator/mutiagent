from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import HumanMessage
from sqlmodel import Session, SQLModel, create_engine

from app.api.health import create_health_router
from app.api.orchestration import (
    _append_turn_with_user_fallback,
    _append_user_message_safely,
    _stream_error_message,
)
from app.services.admin_data_service import (
    get_data_overview,
    list_data_cohorts,
    list_data_programs,
)
from tests.postgres import postgresql_test_url


def test_stream_non_http_exception_uses_safe_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.conversation_session_service.load_session",
        lambda *_args: SimpleNamespace(user_uid="user-1"),
    )

    message = _stream_error_message(
        None,  # type: ignore[arg-type]
        "session-1",
        "user-1",
        RuntimeError("database password leaked"),
    )

    assert message == "对话请求失败，请稍后重试。"
    assert "database password leaked" not in message


def test_user_message_persistence_failure_is_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def raise_persistence_error(*_args, **_kwargs) -> None:
        raise RuntimeError("write failed")

    monkeypatch.setattr(
        "app.services.conversation_session_service.append_messages",
        raise_persistence_error,
    )
    caplog.set_level(logging.ERROR, logger="app.api.orchestration")

    _append_user_message_safely(
        None,  # type: ignore[arg-type]
        "session-1",
        HumanMessage(content="继续生成"),
    )

    assert "conversation_user_message_persistence_failed" in caplog.text


def test_completed_turn_persistence_failure_is_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def raise_persistence_error(*_args, **_kwargs) -> None:
        raise RuntimeError("write failed")

    monkeypatch.setattr(
        "app.services.conversation_session_service.append_messages",
        raise_persistence_error,
    )
    caplog.set_level(logging.ERROR, logger="app.api.orchestration")

    with pytest.raises(RuntimeError, match="write failed"):
        _append_turn_with_user_fallback(
            None,  # type: ignore[arg-type]
            "session-1",
            HumanMessage(content="继续生成"),
            "已完成",
        )

    assert "conversation_turn_persistence_failed" in caplog.text


class _Result:
    def __init__(self, rows: list[object], scalar: int = 0) -> None:
        self._rows = rows
        self._scalar = scalar

    def all(self) -> list[object]:
        return self._rows

    def one(self) -> int:
        return self._scalar


class _OverviewSession:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def exec(self, statement):  # type: ignore[no-untyped-def]
        sql = str(statement).lower()
        self.statements.append(sql)
        if "group by" in sql:
            return _Result([("student", 2), ("admin", 1), ("teacher", 1)])
        return _Result([], scalar=7)


def test_data_overview_uses_database_aggregates() -> None:
    session = _OverviewSession()

    overview = get_data_overview(session)  # type: ignore[arg-type]

    assert overview.accounts == {"student": 2, "admin": 2}
    assert overview.cohorts == 7
    assert overview.programs == 7
    assert overview.learning_data == {
        "profiles": 7,
        "year_learning_paths": 7,
        "course_outlines": 7,
        "chapter_quizzes": 7,
        "chapter_progress": 7,
        "resource_quality": 7,
        "conversation_sessions": 7,
    }
    assert all("count(" in statement for statement in session.statements)


class _CohortSession:
    def __init__(self) -> None:
        self.get_calls: list[str] = []

    def exec(self, statement):  # type: ignore[no-untyped-def]
        sql = str(statement).lower()
        if "group by" in sql:
            return _Result(
                [
                    (
                        "南山大学",
                        "软件工程",
                        "一班",
                        2,
                        1,
                        "teacher-1",
                        datetime(2026, 7, 26, tzinfo=timezone.utc),
                        "教师",
                    )
                ]
            )
        if "join" in sql:
            program = SimpleNamespace(
                program_id="program-1",
                teacher_uid="teacher-1",
                school="南山大学",
                major="软件工程",
                class_name="一班",
                courses=[],
                published_at=None,
                updated_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
            )
            teacher = SimpleNamespace(username="教师", identifier="teacher@example.com")
            return _Result([(program, teacher)])
        if "cultivationprogram" in sql:
            return _Result(
                [
                    SimpleNamespace(
                        program_id="program-1",
                        teacher_uid="teacher-1",
                        school="南山大学",
                        major="软件工程",
                        class_name="一班",
                        courses=[],
                        published_at=None,
                        updated_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
                    )
                ]
            )
        return _Result(
            [
                SimpleNamespace(
                    school="南山大学",
                    major="软件工程",
                    class_name="一班",
                    role="student",
                )
            ]
        )

    def get(self, *_args):  # type: ignore[no-untyped-def]
        self.get_calls.append("get")
        return SimpleNamespace(username="教师")


def test_data_cohorts_avoids_per_program_teacher_lookups() -> None:
    session = _CohortSession()

    cohorts = list_data_cohorts(session)  # type: ignore[arg-type]

    assert session.get_calls == []
    assert cohorts[0].program_teacher_name == "教师"
    assert cohorts[0].student_count == 2
    assert cohorts[0].admin_count == 1


def test_data_programs_avoids_per_program_teacher_lookups() -> None:
    session = _CohortSession()

    programs = list_data_programs(session)  # type: ignore[arg-type]

    assert session.get_calls == []
    assert programs[0].teacher_name == "教师"


def test_admin_data_aggregates_and_joined_program_reads_run_on_postgresql(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    from app.models import CultivationProgram, User

    engine = create_engine(postgresql_test_url(tmp_path, "admin-data-aggregates"))
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        teacher = User(
            uid="teacher-1",
            username="教师",
            identifier="teacher@example.com",
            role="teacher",
            school="南山大学",
            major="软件工程",
            class_name="一班",
        )
        session.add_all(
            [
                teacher,
                User(
                    uid="student-1",
                    username="学生甲",
                    identifier="student-1@example.com",
                    role="student",
                    school="南山大学",
                    major="软件工程",
                    class_name="一班",
                ),
                User(
                    uid="student-2",
                    username="学生乙",
                    identifier="student-2@example.com",
                    role="student",
                    school="南山大学",
                    major="软件工程",
                    class_name="一班",
                ),
                User(
                    uid="unassigned-1",
                    username="未分班学生",
                    identifier="unassigned@example.com",
                    role="student",
                ),
            ]
        )
        session.commit()
        session.add(
            CultivationProgram(
                program_id="program-1",
                teacher_uid=teacher.uid,
                school="南山大学",
                major="软件工程",
                class_name="一班",
                courses=[],
            )
        )
        session.commit()

        overview = get_data_overview(session)
        cohorts = list_data_cohorts(session)
        programs = list_data_programs(session)

    assert overview.accounts == {"student": 3, "admin": 1}
    assert overview.cohorts == 1
    assert overview.programs == 1
    assert len(cohorts) == 1
    assert cohorts[0].student_count == 2
    assert cohorts[0].admin_count == 1
    assert cohorts[0].program_teacher_name == "教师"
    assert programs[0].teacher_name == "教师"


def test_worker_heartbeat_upsert_and_staleness_boundary() -> None:
    from app.models import WorkerHeartbeat
    from app.services.worker_health_service import (
        WORKER_HEARTBEAT_MAX_AGE,
        WORKER_HEARTBEAT_NAME,
        record_worker_heartbeat,
    )

    engine = create_engine("sqlite://")
    WorkerHeartbeat.__table__.create(engine)
    now = datetime(2026, 7, 26, tzinfo=timezone.utc)

    with Session(engine) as session:
        record_worker_heartbeat(session, "worker-first", now)
        record_worker_heartbeat(session, "worker-second", now + timedelta(seconds=1))
        stored = session.get(WorkerHeartbeat, WORKER_HEARTBEAT_NAME)

    assert stored is not None
    assert stored.worker_id == "worker-second"
    assert stored.last_heartbeat_at.replace(tzinfo=timezone.utc) == now + timedelta(
        seconds=1
    )
    assert (
        now
        + timedelta(seconds=1)
        - stored.last_heartbeat_at.replace(tzinfo=timezone.utc)
        < WORKER_HEARTBEAT_MAX_AGE
    )


def test_deep_health_requires_and_reports_fresh_worker_heartbeat(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.models import WorkerHeartbeat
    from app.services.worker_health_service import record_worker_heartbeat

    engine = create_engine(postgresql_test_url(tmp_path, "deep-worker-health"))
    WorkerHeartbeat.__table__.create(engine)
    app = FastAPI()
    app.include_router(create_health_router(engine))
    client = TestClient(app)

    missing_response = client.get("/api/health/deep")

    assert missing_response.status_code == 503
    assert missing_response.json() == {
        "status": "error",
        "database": "connected",
        "knowledge_base_worker": "unavailable",
    }

    with Session(engine) as session:
        record_worker_heartbeat(session, "worker-ready", datetime.now(timezone.utc))

    ready_response = client.get("/api/health/deep")

    assert ready_response.status_code == 200
    assert ready_response.json() == {
        "status": "ok",
        "database": "connected",
        "knowledge_base_worker": "connected",
    }
