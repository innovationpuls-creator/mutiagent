from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from app.models import User
from app.services.learning_path_service import (
    get_all_year_learning_paths,
    get_latest_grade_year,
    get_year_learning_path,
    upsert_year_learning_path,
)
from tests.postgres import postgresql_test_url


def build_session(tmp_path: Path) -> Session:
    engine = create_engine(
        postgresql_test_url(tmp_path, "learning-path"),
    )
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    session.add(
        User(uid="user-1", username="路径用户", identifier="learning-path@example.com")
    )
    session.commit()
    return session


def test_upsert_year_learning_path_saves_latest_path_data(tmp_path: Path) -> None:
    with build_session(tmp_path) as session:
        first = {"grade_year": "year_1", "courses": []}
        second = {
            "grade_year": "year_1",
            "courses": [{"course_id": "year_1_course_1", "course_name": "Python"}],
        }

        upsert_year_learning_path(session, "user-1", "year_1", "Python", first)
        saved = upsert_year_learning_path(
            session, "user-1", "year_1", "Python进阶", second
        )
        loaded = get_year_learning_path(session, "user-1", "year_1")

    assert saved.path_data == second
    assert loaded is not None
    assert loaded["courses"][0]["course_name"] == "Python"


def _node(course_id: str, theme: str) -> dict:
    return {
        "course_node_id": course_id,
        "grade_id": "year_3",
        "course_or_chapter_theme": theme,
        "time_arrangement": {
            "semester_scope": "上学期",
            "duration": "4 周",
            "pace_reason": "平时学习",
        },
        "course_goal": f"完成{theme}",
        "prerequisite_node_ids": [],
        "chapter_nodes": [],
        "core_knowledge_points": [],
        "key_points": [],
        "difficult_points": [],
        "learning_sequence": [],
        "knowledge_relations": [],
        "downstream_resource_direction_ids": [],
        "acceptance_criteria": [],
    }


def _path() -> dict:
    first = _node("year_3_course_1", "AI 应用开发基础")
    second = _node("year_3_course_2", "AI Web 项目实战")
    return {
        "schema_version": "learning_path.v2.course_node",
        "grade_plans": {
            "year_3": {
                "grade_id": "year_3",
                "grade_name": "大三",
                "grade_goal": "完成 AI Web 项目",
                "course_nodes": [first, second],
            }
        },
        "current_learning_course": {
            "grade_id": "year_3",
            "course_node_id": "year_3_course_1",
            "course_or_chapter_theme": "AI 应用开发基础",
            "course_goal": "完成AI 应用开发基础",
            "time_arrangement": first["time_arrangement"],
            "current_focus": "正在学习 AI 应用开发基础",
            "progress_state": "in_progress",
            "next_action": "继续学习第一章",
        },
    }


def _multi_year_path() -> dict:
    def make_course(grade_id: str, course_id: str, theme: str) -> dict:
        return {
            "course_node_id": course_id,
            "grade_id": grade_id,
            "course_or_chapter_theme": theme,
            "time_arrangement": {
                "semester_scope": "上学期",
                "duration": "4 周",
                "pace_reason": "按学年推进",
            },
            "course_goal": f"完成{theme}",
            "prerequisite_node_ids": [],
            "chapter_nodes": [],
            "core_knowledge_points": [],
            "key_points": [],
            "difficult_points": [],
            "learning_sequence": [],
            "knowledge_relations": [],
            "downstream_resource_direction_ids": [],
            "acceptance_criteria": [],
        }

    year_1_course = make_course("year_1", "year_1_course_1", "编程基础")
    year_2_course = make_course("year_2", "year_2_course_1", "工程化 Web 开发")
    year_3_course = make_course("year_3", "year_3_course_1", "AI 应用开发基础")
    year_4_course = make_course("year_4", "year_4_course_1", "毕业项目实战")
    return {
        "schema_version": "learning_path.v2.course_node",
        "grade_plans": {
            "year_1": {
                "grade_id": "year_1",
                "grade_name": "大一",
                "grade_goal": "夯实编程基础",
                "course_nodes": [year_1_course],
            },
            "year_2": {
                "grade_id": "year_2",
                "grade_name": "大二",
                "grade_goal": "进入工程主线",
                "course_nodes": [year_2_course],
            },
            "year_3": {
                "grade_id": "year_3",
                "grade_name": "大三",
                "grade_goal": "完成 AI 应用开发项目",
                "course_nodes": [year_3_course],
            },
            "year_4": {
                "grade_id": "year_4",
                "grade_name": "大四",
                "grade_goal": "沉淀毕业项目作品",
                "course_nodes": [year_4_course],
            },
        },
        "current_learning_course": {
            "grade_id": "year_3",
            "course_node_id": "year_3_course_1",
            "course_or_chapter_theme": "AI 应用开发基础",
            "course_goal": "完成AI 应用开发基础",
            "time_arrangement": year_3_course["time_arrangement"],
            "current_focus": "正在学习 AI 应用开发基础",
            "progress_state": "in_progress",
            "next_action": "继续学习第一章",
        },
    }


def test_find_current_course_returns_course_node() -> None:
    from app.services.learning_path_service import find_current_course

    path = _path()
    current = find_current_course(path)

    assert current["course_node_id"] == "year_3_course_1"
    assert current["course_or_chapter_theme"] == "AI 应用开发基础"


def test_advance_current_learning_course_moves_after_score_above_70(
    tmp_path: Path,
) -> None:
    from app.services.learning_path_service import advance_current_learning_course

    with build_session(tmp_path) as session:
        upsert_year_learning_path(session, "user-1", "year_3", "AI", _path())

        updated = advance_current_learning_course(session, "user-1", "year_3", 71)

    assert updated["current_learning_course"]["course_node_id"] == "year_3_course_2"
    assert updated["current_learning_course"]["progress_state"] == "in_progress"


def test_advance_current_learning_course_stays_when_score_is_70(tmp_path: Path) -> None:
    from app.services.learning_path_service import advance_current_learning_course

    with build_session(tmp_path) as session:
        upsert_year_learning_path(session, "user-1", "year_3", "AI", _path())

        updated = advance_current_learning_course(session, "user-1", "year_3", 70)

    assert updated["current_learning_course"]["course_node_id"] == "year_3_course_1"
    assert updated["current_learning_courses"][0]["course_node_id"] == "year_3_course_1"


def test_get_all_year_learning_paths_orders_latest_updated_path_first(
    tmp_path: Path,
) -> None:
    with build_session(tmp_path) as session:
        upsert_year_learning_path(
            session,
            "user-1",
            "year_1",
            "Python",
            {"grade_year": "year_1", "courses": []},
        )
        upsert_year_learning_path(
            session,
            "user-1",
            "year_4",
            "AI",
            {"grade_year": "year_4", "courses": []},
        )

        first_row = session.get(
            __import__(
                "app.models", fromlist=["UserYearLearningPath"]
            ).UserYearLearningPath,
            ("user-1", "year_1"),
        )
        second_row = session.get(
            __import__(
                "app.models", fromlist=["UserYearLearningPath"]
            ).UserYearLearningPath,
            ("user-1", "year_4"),
        )
        assert first_row is not None
        assert second_row is not None
        first_row.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        second_row.updated_at = datetime(2026, 6, 5, tzinfo=timezone.utc)
        session.add(first_row)
        session.add(second_row)
        session.commit()

        paths = get_all_year_learning_paths(session, "user-1")
        latest_grade_year = get_latest_grade_year(session, "user-1")

    assert list(paths.keys()) == ["year_4", "year_1"]
    assert latest_grade_year == "year_4"


def test_get_year_learning_path_normalizes_current_learning_courses_for_legacy_path(
    tmp_path: Path,
) -> None:
    with build_session(tmp_path) as session:
        legacy_path = _path()
        upsert_year_learning_path(session, "user-1", "year_3", "AI", legacy_path)

        loaded = get_year_learning_path(session, "user-1", "year_3")

    assert loaded is not None
    assert (
        loaded["current_learning_courses"][0]["course_node_id"]
        == loaded["current_learning_course"]["course_node_id"]
    )


def test_get_all_year_learning_paths_expands_single_row_multi_grade_plan(
    tmp_path: Path,
) -> None:
    with build_session(tmp_path) as session:
        upsert_year_learning_path(
            session, "user-1", "year_3", "AI 应用开发", _multi_year_path()
        )

        paths = get_all_year_learning_paths(session, "user-1")

    assert set(paths) == {"year_1", "year_2", "year_3", "year_4"}
    assert (
        paths["year_1"]["grade_plans"]["year_1"]["course_nodes"][0]["course_node_id"]
        == "year_1_course_1"
    )
    assert (
        paths["year_4"]["grade_plans"]["year_4"]["course_nodes"][0]["course_node_id"]
        == "year_4_course_1"
    )


def test_get_year_learning_path_reads_expanded_grade_plan_from_single_row(
    tmp_path: Path,
) -> None:
    with build_session(tmp_path) as session:
        upsert_year_learning_path(
            session, "user-1", "year_3", "AI 应用开发", _multi_year_path()
        )

        loaded = get_year_learning_path(session, "user-1", "year_1")

    assert loaded is not None
    assert loaded["grade_plans"]["year_1"]["grade_name"] == "大一"
    assert loaded["current_learning_course"]["grade_id"] == "year_3"
