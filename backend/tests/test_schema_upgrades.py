from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from app.models import User, UserCourseKnowledgeOutline, UserYearLearningPath
from app.schema_upgrades import migrate_removed_learning_path_table, run_schema_upgrades


def test_schema_upgrades_rebuild_legacy_tables(tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'upgrade.db'}",
        connect_args={"check_same_thread": False},
    )
    User.__table__.create(engine)

    legacy_path = {
        "learning_goal": {"target_course_or_skill": "数据结构"},
        "grade_plans": {
            "year_2": {
                "grade_id": "year_2",
                "grade_name": "大二",
                "grade_goal": "进入数据结构",
                "course_nodes": [
                    {
                        "course_node_id": "year_2_course_1",
                        "grade_id": "year_2",
                        "course_or_chapter_theme": "数据结构基础",
                        "time_arrangement": {"semester_scope": "上学期", "duration": "8 周"},
                        "course_goal": "掌握线性表、树和图",
                        "prerequisite_node_ids": ["year_1_course_1"],
                        "key_points": ["线性表", "树", "图"],
                    }
                ],
            }
        },
    }

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE usercourseknowledgeoutline (
                    user_uid VARCHAR NOT NULL,
                    course_node_id VARCHAR(128) NOT NULL,
                    grade_id VARCHAR(32) NOT NULL,
                    course_name VARCHAR(128) NOT NULL,
                    outline_data JSON,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    PRIMARY KEY (user_uid, course_node_id)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE userlearningpath (
                    user_uid VARCHAR NOT NULL PRIMARY KEY,
                    path_data JSON,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE useragentconversation (
                    user_uid VARCHAR NOT NULL,
                    agent_key VARCHAR NOT NULL,
                    conversation_id VARCHAR NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    PRIMARY KEY (user_uid, agent_key)
                )
                """
            )
        )

    with Session(engine) as session:
        session.add(User(uid="user-1", username="升级用户", identifier="upgrade@example.com"))
        session.commit()

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO usercourseknowledgeoutline
                    (user_uid, course_node_id, grade_id, course_name, outline_data, created_at, updated_at)
                VALUES
                    ('user-1', 'year_2_course_1', 'year_2', '数据结构基础', '{"sections":[]}',
                     '2026-06-01 00:00:00', '2026-06-02 00:00:00')
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO userlearningpath
                    (user_uid, path_data, created_at, updated_at)
                VALUES
                    (:user_uid, :path_data, '2026-06-01 00:00:00', '2026-06-02 00:00:00')
                """
            ),
            {"user_uid": "user-1", "path_data": json.dumps(legacy_path)},
        )
        connection.execute(
            text(
                """
                INSERT INTO useragentconversation
                    (user_uid, agent_key, conversation_id, created_at, updated_at)
                VALUES
                    ('user-1', 'profile_agent', 'legacy-conv', '2026-06-01 00:00:00', '2026-06-02 00:00:00')
                """
            )
        )

    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)
    migrate_removed_learning_path_table(engine)

    inspector = inspect(engine)
    assert not inspector.has_table("useragentconversation")
    assert not inspector.has_table("userlearningpath")

    outline_columns = {column["name"] for column in inspector.get_columns("usercourseknowledgeoutline")}
    assert {"user_uid", "course_id", "grade_year", "course_name", "outline_data"}.issubset(outline_columns)
    assert "course_node_id" not in outline_columns
    assert "grade_id" not in outline_columns

    with Session(engine) as session:
        outline = session.get(UserCourseKnowledgeOutline, ("user-1", "year_2_course_1"))
        assert outline is not None
        assert outline.grade_year == "year_2"
        assert outline.course_name == "数据结构基础"

        path = session.get(UserYearLearningPath, ("user-1", "year_2"))
        assert path is not None
        assert path.learning_topic == "数据结构"
        assert path.path_data["courses"][0]["course_id"] == "year_2_course_1"
        assert path.path_data["courses"][0]["key_topics"] == ["线性表", "树", "图"]
