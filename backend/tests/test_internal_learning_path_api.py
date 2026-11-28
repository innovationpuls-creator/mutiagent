from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlmodel import Session, select

from app.core.config import DEFAULT_INTERNAL_API_TOKEN
from app.database import DEMO_USER_UID
from app.main import create_app
from app.models import KnowledgeGap, UserCourseKnowledgeOutline, UserYearLearningPath
from tests.postgres import postgresql_test_url
from tests.test_learning_path_agent_contract import (
    _complete_profile,
    _confirmed_intake,
    _llm_learning_path_plan_payload,
)

INTERNAL = {"X-Internal-Token": DEFAULT_INTERNAL_API_TOKEN}


@pytest.fixture
def ctx(tmp_path: Path):
    url = postgresql_test_url(tmp_path, "internal-path")
    client = TestClient(create_app(database_url=url))
    return client, create_engine(url)


def _assemble(client, intake: dict, plan: dict, grade_year: str = "year_3"):
    return client.post(
        f"/internal/students/{DEMO_USER_UID}/learning-paths/{grade_year}/assemble",
        headers=INTERNAL,
        json={
            "profile": _complete_profile(),
            "learning_topic": intake["learning_topic"],
            "plan": plan,
            "intake_courses": intake["courses"],
        },
    )


def _plan_for(intake: dict) -> dict:
    return _llm_learning_path_plan_payload([c["title"] for c in intake["courses"]])


def test_new_endpoints_require_token(ctx) -> None:
    client, _ = ctx
    assert client.get("/internal/knowledge-base/published-textbooks").status_code == 401
    assert (
        client.get(f"/internal/students/{DEMO_USER_UID}/protected-courses").status_code
        == 401
    )
    assert (
        client.get(
            f"/internal/students/{DEMO_USER_UID}/learning-paths/progress-snapshots"
        ).status_code
        == 401
    )


def test_catalog_is_empty_and_gap_registration_is_idempotent(ctx) -> None:
    client, engine = ctx
    listed = client.get(
        "/internal/knowledge-base/published-textbooks", headers=INTERNAL
    )
    assert listed.status_code == 200
    assert listed.json()["textbooks"] == []
    assert listed.json()["total"] == 0
    missing = client.get(
        "/internal/knowledge-base/published-textbooks/ghost/outline", headers=INTERNAL
    )
    assert missing.status_code == 404

    first = client.post(
        "/internal/knowledge-base/gaps",
        headers=INTERNAL,
        json={"topic": "量子力学", "student_goal_summary": "想学量子"},
    )
    again = client.post(
        "/internal/knowledge-base/gaps", headers=INTERNAL, json={"topic": "量子力学"}
    )
    assert first.status_code == 200
    assert again.json()["gap_id"] == first.json()["gap_id"]
    with Session(engine) as session:
        gaps = session.exec(select(KnowledgeGap)).all()
        assert [g.gap_id for g in gaps] == [first.json()["gap_id"]]


def test_assemble_save_and_progress_continuation(ctx) -> None:
    client, engine = ctx
    intake = _confirmed_intake()
    plan = _plan_for(intake)

    assembled = _assemble(client, intake, plan)
    assert assembled.status_code == 200, assembled.text
    path = assembled.json()["path_data"]
    assert path["schema_version"] == "learning_path.v2.course_node"
    nodes = path["grade_plans"]["year_3"]["course_nodes"]
    assert [n["course_or_chapter_theme"] for n in nodes] == [
        c["title"] for c in intake["courses"]
    ]
    assert [n["source_textbook_id"] for n in nodes] == [
        c["source_textbook_id"] for c in intake["courses"]
    ]
    assert (
        path["current_learning_course"]["course_node_id"] == nodes[0]["course_node_id"]
    )

    saved = client.put(
        f"/internal/students/{DEMO_USER_UID}/learning-paths/year_3",
        headers=INTERNAL,
        json={"learning_topic": intake["learning_topic"], "path_data": path},
    )
    assert saved.status_code == 200

    # Mark first course completed, then refresh: current course must continue to #2.
    stored = dict(path)
    stored["grade_plans"]["year_3"]["course_nodes"][0]["progress_state"] = "completed"
    stored["current_learning_course"] = {
        **path["current_learning_course"],
        "progress_state": "completed",
    }
    stored["current_learning_courses"] = [stored["current_learning_course"]]
    client.put(
        f"/internal/students/{DEMO_USER_UID}/learning-paths/year_3",
        headers=INTERNAL,
        json={"learning_topic": intake["learning_topic"], "path_data": stored},
    )
    snaps = client.get(
        f"/internal/students/{DEMO_USER_UID}/learning-paths/progress-snapshots",
        headers=INTERNAL,
    ).json()["snapshots"]
    assert snaps[0]["grade_year"] == "year_3"
    assert snaps[0]["completed_courses"] == 1

    refreshed = _assemble(client, intake, plan).json()["path_data"]
    refreshed_nodes = refreshed["grade_plans"]["year_3"]["course_nodes"]
    assert (
        refreshed["current_learning_course"]["course_node_id"]
        == refreshed_nodes[1]["course_node_id"]
    )

    protected = client.get(
        f"/internal/students/{DEMO_USER_UID}/protected-courses", headers=INTERNAL
    ).json()["courses"]
    assert {"title": intake["courses"][0]["title"], "reason": "已开始学习"} in protected
    with Session(engine) as session:
        assert session.get(UserYearLearningPath, (DEMO_USER_UID, "year_3"))


def test_assemble_rejects_count_mismatch_with_422(ctx) -> None:
    client, _ = ctx
    intake = _confirmed_intake()
    plan = _plan_for(intake)
    plan["course_specs"] = plan["course_specs"][:-1]
    res = _assemble(client, intake, plan)
    assert res.status_code == 422
    assert "一致" in res.json()["detail"]


def test_save_clears_only_that_years_outlines(ctx) -> None:
    client, engine = ctx
    intake = _confirmed_intake()
    path = _assemble(client, intake, _plan_for(intake)).json()["path_data"]
    with Session(engine) as session:
        for course_id, year in (("c-y3", "year_3"), ("c-y2", "year_2")):
            session.add(
                UserCourseKnowledgeOutline(
                    user_uid=DEMO_USER_UID,
                    course_id=course_id,
                    grade_year=year,
                    course_name=f"课-{year}",
                    outline_data={},
                )
            )
        session.commit()

    protected = client.get(
        f"/internal/students/{DEMO_USER_UID}/protected-courses", headers=INTERNAL
    ).json()["courses"]
    assert {"title": "课-year_3", "reason": "已有课程大纲"} in protected

    client.put(
        f"/internal/students/{DEMO_USER_UID}/learning-paths/year_3",
        headers=INTERNAL,
        json={"learning_topic": intake["learning_topic"], "path_data": path},
    )
    with Session(engine) as session:
        remaining = session.exec(select(UserCourseKnowledgeOutline)).all()
        assert [r.grade_year for r in remaining] == ["year_2"]
