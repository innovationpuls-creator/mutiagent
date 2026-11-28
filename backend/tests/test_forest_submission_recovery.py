from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, select

from app.main import create_app
from app.models import (
    ChapterProgress,
    ChapterQuizAttempt,
    UserCourseKnowledgeOutline,
    UserYearLearningPath,
)
from app.schemas import ForestQuizAttemptCreateRequest
from app.services.forest_service import generate_or_read_quiz
from app.services.forest_submission_service import (
    persist_submission,
    prepare_submission,
    read_submission,
)
from app.services.learning_path_service import upsert_year_learning_path
from tests.postgres import postgresql_test_url
from tests.test_forest_api import _auth_headers, _path, _seed_forest_data

QUESTIONS = [
    {
        "question_id": "q1",
        "type": "single_choice",
        "prompt": "选择答案",
        "options": [{"option_id": "A", "text": "正确"}],
        "correct_option_id": "A",
        "points": 100,
    }
]
GRADE = {"score": 80, "question_results": [], "summary": "通过"}


def setup_quiz(tmp_path: Path):
    url = postgresql_test_url(tmp_path, "forest-recovery")
    client = TestClient(create_app(database_url=url))
    uid = _seed_forest_data(url)
    engine = create_engine(url)
    with Session(engine) as session:
        quiz = generate_or_read_quiz(
            session, uid, "year_3_course_2", "1", QUESTIONS, regenerate=False
        )
    payload = ForestQuizAttemptCreateRequest(
        answers={"q1": "A"},
        client_submission_id=uuid4(),
        quiz_version=quiz.quiz_version,
    )
    return engine, client, uid, quiz, payload


def submit(engine, uid, quiz, payload):
    with Session(engine) as session:
        questions, version = prepare_submission(session, uid, quiz.quiz_id, payload)
    with Session(engine) as session:
        return persist_submission(
            session, uid, quiz.quiz_id, payload, questions, version, GRADE
        )


def test_exact_result_recovered_and_replayed_after_regenerate(tmp_path):
    engine, client, uid, quiz, payload = setup_quiz(tmp_path)
    original = submit(engine, uid, quiz, payload)
    with Session(engine) as session:
        updated = generate_or_read_quiz(
            session,
            uid,
            "year_3_course_2",
            "1",
            [{**QUESTIONS[0], "correct_option_id": "B"}],
            regenerate=True,
        )
    assert updated.quiz_version != quiz.quiz_version
    response = client.get(
        f"/api/forest/quizzes/{quiz.quiz_id}/submissions/{payload.client_submission_id}",
        headers=_auth_headers(uid),
    )
    assert response.json() == original
    with patch(
        "app.api.forest.grade_quiz_answers",
        side_effect=AssertionError("must not regrade"),
    ):
        replay = client.post(
            f"/api/forest/quizzes/{quiz.quiz_id}/attempts/stream",
            json=payload.model_dump(mode="json"),
            headers=_auth_headers(uid),
        )
    assert replay.status_code == 200 and "event: done" in replay.text
    with Session(engine) as session:
        assert len(session.exec(select(ChapterQuizAttempt)).all()) == 1
    assert client.get(
        f"/api/forest/quizzes/{quiz.quiz_id}/submissions/{payload.client_submission_id}",
        headers=_auth_headers("other-user"),
    ).status_code in (401, 404)


def test_concurrent_same_submission_commits_once(tmp_path):
    engine, _client, uid, quiz, payload = setup_quiz(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(engine, uid, quiz, payload), range(2)))
    assert results[0] == results[1]
    with Session(engine) as session:
        assert len(session.exec(select(ChapterQuizAttempt)).all()) == 1


def test_same_uuid_different_answers_conflicts(tmp_path):
    engine, client, uid, quiz, payload = setup_quiz(tmp_path)
    submit(engine, uid, quiz, payload)
    data = payload.model_dump(mode="json")
    data["answers"] = {"q1": "B"}
    response = client.post(
        f"/api/forest/quizzes/{quiz.quiz_id}/attempts",
        json=data,
        headers=_auth_headers(uid),
    )
    assert response.status_code == 409


@pytest.mark.parametrize("change", ["regenerate", "remove_chapter", "replace_path"])
def test_changed_state_during_grading_cannot_commit(tmp_path, change):
    engine, _client, uid, quiz, payload = setup_quiz(tmp_path)
    with Session(engine) as session:
        questions, version = prepare_submission(session, uid, quiz.quiz_id, payload)
    with Session(engine) as session:
        if change == "regenerate":
            generate_or_read_quiz(
                session,
                uid,
                "year_3_course_2",
                "1",
                [{**QUESTIONS[0], "prompt": "新题目"}],
                regenerate=True,
            )
        elif change == "remove_chapter":
            row = session.get(UserCourseKnowledgeOutline, (uid, "year_3_course_2"))
            row.outline_data = {**row.outline_data, "sections": []}
            session.add(row)
            session.commit()
        else:
            path = _path()
            path["grade_plans"]["year_3"]["course_nodes"][0]["course_node_id"] = (
                "replacement"
            )
            upsert_year_learning_path(session, uid, "year_3", "AI", path)
    with Session(engine) as session, pytest.raises(HTTPException) as error:
        persist_submission(
            session, uid, quiz.quiz_id, payload, questions, version, GRADE
        )
    assert error.value.status_code in (404, 409)
    with Session(engine) as session:
        assert session.exec(select(ChapterQuizAttempt)).all() == []


def test_snapshot_failure_rolls_back_attempt_and_progress(tmp_path):
    engine, _client, uid, quiz, payload = setup_quiz(tmp_path)
    with (
        patch(
            "app.services.forest_submission_service.get_canopy_overview",
            side_effect=RuntimeError("snapshot failure"),
        ),
        pytest.raises(RuntimeError),
    ):
        submit(engine, uid, quiz, payload)
    with Session(engine) as session:
        assert session.exec(select(ChapterQuizAttempt)).all() == []
        assert (
            session.get(ChapterProgress, (uid, "year_3_course_2", "1")).state
            == "available"
        )
        assert session.get(ChapterProgress, (uid, "year_3_course_2", "2")) is None


def test_repeating_final_chapter_does_not_advance_successor(tmp_path):
    engine, _client, uid, quiz, payload = setup_quiz(tmp_path)
    submit(engine, uid, quiz, payload)
    with Session(engine) as session:
        final = generate_or_read_quiz(
            session, uid, "year_3_course_2", "2", QUESTIONS, regenerate=False
        )
    data = ForestQuizAttemptCreateRequest(
        answers={"q1": "A"},
        client_submission_id=uuid4(),
        quiz_version=final.quiz_version,
    )
    submit(engine, uid, final, data)
    data.client_submission_id = uuid4()
    submit(engine, uid, final, data)
    with Session(engine) as session:
        path = session.get(UserYearLearningPath, (uid, "year_3")).path_data
        assert path["current_learning_course"]["course_node_id"] == "year_3_course_3"
        assert path["current_learning_course"]["progress_state"] == "in_progress"


def test_leaf_progress_listing_has_no_writes_and_pending_is_unknown(tmp_path):
    engine, client, uid, quiz, payload = setup_quiz(tmp_path)
    with Session(engine) as session:
        before = len(session.exec(select(ChapterProgress)).all())
    response = client.get(
        "/api/leaf/courses/year_3_course_2", headers=_auth_headers(uid)
    )
    assert [p["state"] for p in response.json()["chapter_progress"]] == [
        "available",
        "locked",
    ]
    with Session(engine) as session:
        assert len(session.exec(select(ChapterProgress)).all()) == before
        with pytest.raises(HTTPException) as error:
            read_submission(session, uid, quiz.quiz_id, payload.client_submission_id)
        assert error.value.status_code == 404


def test_advancement_updates_merged_year_row_without_creating_another(tmp_path):
    engine, _client, uid, quiz, payload = setup_quiz(tmp_path)
    with Session(engine) as session:
        row = session.get(UserYearLearningPath, (uid, "year_3"))
        row.grade_year = "year_1"
        session.add(row)
        session.commit()
    submit(engine, uid, quiz, payload)
    with Session(engine) as session:
        final = generate_or_read_quiz(
            session, uid, "year_3_course_2", "2", QUESTIONS, regenerate=False
        )
    final_payload = ForestQuizAttemptCreateRequest(
        answers={"q1": "A"},
        client_submission_id=uuid4(),
        quiz_version=final.quiz_version,
    )
    submit(engine, uid, final, final_payload)
    with Session(engine) as session:
        rows = session.exec(select(UserYearLearningPath)).all()
        assert len(rows) == 1 and rows[0].grade_year == "year_1"
        assert (
            rows[0].path_data["current_learning_course"]["course_node_id"]
            == "year_3_course_3"
        )


def test_recovery_migration_preserves_unknown_historical_version(tmp_path):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect, text

    url = postgresql_test_url(tmp_path, "quiz-recovery-migration")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE chapterquizattempt (attempt_id varchar(64) PRIMARY KEY, "
                "answers jsonb NOT NULL, score integer NOT NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO chapterquizattempt VALUES "
                "('historical', '{\"q1\":\"A\"}', 80)"
            )
        )
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "migrations"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.stamp(config, "0004_worker_heartbeats")
    command.upgrade(config, "head")
    with engine.connect() as connection:
        row = (
            connection.execute(text("SELECT * FROM chapterquizattempt"))
            .mappings()
            .one()
        )
        assert row["answers"] == {"q1": "A"} and row["score"] == 80
        assert row["quiz_version"] is None and row["recovery_snapshot"] is None
    command.downgrade(config, "0004_worker_heartbeats")
    assert "quiz_version" not in {
        column["name"] for column in inspect(engine).get_columns("chapterquizattempt")
    }
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT score FROM chapterquizattempt")
            ).scalar_one()
            == 80
        )


def test_path_replacement_serializes_with_quiz_generation(tmp_path):
    from concurrent.futures import TimeoutError
    from threading import Event

    from app.services.student_lock import lock_student

    engine, _client, uid, quiz, _payload = setup_quiz(tmp_path)
    reached_lock = Event()

    def observed_lock(session, user_uid):
        reached_lock.set()
        lock_student(session, user_uid)

    def generate():
        with Session(engine) as session:
            return generate_or_read_quiz(
                session,
                uid,
                "year_3_course_2",
                "1",
                [{**QUESTIONS[0], "prompt": "replacement generation"}],
                regenerate=True,
            )

    with Session(engine) as replacement:
        lock_student(replacement, uid)
        with patch("app.services.forest_service.lock_student", observed_lock):
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(generate)
                try:
                    assert reached_lock.wait(2)
                    with pytest.raises(TimeoutError):
                        future.result(timeout=0.1)
                    path = _path()
                    path["grade_plans"]["year_3"]["course_nodes"][0][
                        "course_node_id"
                    ] = "replacement"
                    upsert_year_learning_path(
                        replacement, uid, "year_3", "AI", path, commit=False
                    )
                    replacement.commit()
                    with pytest.raises(HTTPException) as error:
                        future.result(timeout=5)
                    assert error.value.status_code == 404
                finally:
                    replacement.rollback()
    from app.models import ChapterQuiz

    with Session(engine) as session:
        assert session.get(ChapterQuiz, quiz.quiz_id) is None


def test_generation_rejects_changed_chapter_content(tmp_path):
    engine, client, uid, quiz, _payload = setup_quiz(tmp_path)

    async def generate_and_change_outline(*args, **kwargs):
        with Session(engine) as session:
            row = session.get(UserCourseKnowledgeOutline, (uid, "year_3_course_2"))
            outline = dict(row.outline_data)
            sections = [dict(section) for section in outline["sections"]]
            sections[0]["title"] = "更新后的章节内容"
            row.outline_data = {**outline, "sections": sections}
            session.add(row)
            session.commit()
        return [{**QUESTIONS[0], "prompt": "旧章节生成的题目"}]

    with patch("app.api.forest.generate_quiz_questions", generate_and_change_outline):
        response = client.post(
            "/api/forest/courses/year_3_course_2/chapters/1/quiz/generate",
            json={"regenerate": True},
            headers=_auth_headers(uid),
        )
    assert response.status_code == 409
    with Session(engine) as session:
        from app.models import ChapterQuiz

        stored = session.get(ChapterQuiz, quiz.quiz_id)
        assert stored.questions == QUESTIONS
