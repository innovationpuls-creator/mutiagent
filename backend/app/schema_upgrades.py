from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app.models import UserYearLearningPath


def run_schema_upgrades(engine: Engine) -> None:
    """Upgrade old local schemas to the current SQLModel schema.

    SQLModel creates missing tables, but it does not rename columns, rebuild
    primary keys, or drop tables that were removed from the model.
    """
    with engine.begin() as connection:
        _upgrade_user_role_column(connection)
        _upgrade_course_knowledge_outline_table(connection)
        _upgrade_profile_json_storage(connection)
        _drop_removed_agent_conversation_table(connection)


def migrate_removed_learning_path_table(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("userlearningpath"):
        return

    with Session(engine) as session:
        rows = session.exec(text("SELECT user_uid, path_data FROM userlearningpath")).all()
        for user_uid, path_data in rows:
            if isinstance(path_data, str):
                path_data = json.loads(path_data)
            if not isinstance(path_data, dict):
                continue
            _migrate_legacy_path_row(session, str(user_uid), path_data)
        session.commit()

    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS userlearningpath"))


def _drop_removed_agent_conversation_table(connection: Any) -> None:
    connection.execute(text("DROP TABLE IF EXISTS useragentconversation"))


def _upgrade_user_role_column(connection: Any) -> None:
    inspector = inspect(connection)
    if not inspector.has_table("user"):
        return

    columns = {column["name"] for column in inspector.get_columns("user")}
    if "role" in columns:
        return

    connection.execute(text('ALTER TABLE "user" ADD COLUMN role VARCHAR(16) NOT NULL DEFAULT \'student\''))
    connection.execute(text('CREATE INDEX IF NOT EXISTS ix_user_role ON "user" (role)'))


def _upgrade_profile_json_storage(connection: Any) -> None:
    if connection.dialect.name != "postgresql":
        return
    inspector = inspect(connection)
    if not inspector.has_table("userprofile"):
        return
    connection.execute(
        text("ALTER TABLE userprofile ALTER COLUMN profile_data TYPE JSONB USING profile_data::jsonb")
    )


def _upgrade_course_knowledge_outline_table(connection: Any) -> None:
    inspector = inspect(connection)
    if not inspector.has_table("usercourseknowledgeoutline"):
        return

    columns = {column["name"] for column in inspector.get_columns("usercourseknowledgeoutline")}
    needs_rebuild = not {"course_id", "grade_year"}.issubset(columns)
    if connection.dialect.name == "postgresql":
        outline_type = next(
            (str(column["type"]).lower() for column in inspector.get_columns("usercourseknowledgeoutline")
             if column["name"] == "outline_data"),
            "",
        )
        needs_rebuild = needs_rebuild or outline_type != "jsonb"

    if not needs_rebuild:
        return

    legacy_table = "usercourseknowledgeoutline_legacy_upgrade"
    connection.execute(text(f"DROP TABLE IF EXISTS {legacy_table}"))
    connection.execute(text(f"ALTER TABLE usercourseknowledgeoutline RENAME TO {legacy_table}"))
    _create_course_knowledge_outline_table(connection)
    _copy_course_knowledge_outline_rows(connection, legacy_table)
    connection.execute(text(f"DROP TABLE IF EXISTS {legacy_table}"))


def _create_course_knowledge_outline_table(connection: Any) -> None:
    json_type = "JSONB" if connection.dialect.name == "postgresql" else "JSON"
    connection.execute(
        text(
            f"""
            CREATE TABLE usercourseknowledgeoutline (
                user_uid VARCHAR NOT NULL,
                course_id VARCHAR(128) NOT NULL,
                grade_year VARCHAR(16) NOT NULL,
                course_name VARCHAR(256) NOT NULL,
                outline_data {json_type},
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                PRIMARY KEY (user_uid, course_id),
                FOREIGN KEY(user_uid) REFERENCES "user" (uid)
            )
            """
        )
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_course_knowledge_user_grade "
            "ON usercourseknowledgeoutline (user_uid, grade_year)"
        )
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_usercourseknowledgeoutline_grade_year "
            "ON usercourseknowledgeoutline (grade_year)"
        )
    )


def _copy_course_knowledge_outline_rows(connection: Any, legacy_table: str) -> None:
    inspector = inspect(connection)
    columns = {column["name"] for column in inspector.get_columns(legacy_table)}

    course_expr = "course_id" if "course_id" in columns else "course_node_id"
    grade_expr = "grade_year" if "grade_year" in columns else "grade_id"
    outline_expr = "outline_data::jsonb" if connection.dialect.name == "postgresql" else "outline_data"

    connection.execute(
        text(
            f"""
            INSERT INTO usercourseknowledgeoutline
                (user_uid, course_id, grade_year, course_name, outline_data, created_at, updated_at)
            SELECT
                user_uid,
                {course_expr},
                {grade_expr},
                course_name,
                {outline_expr},
                created_at,
                updated_at
            FROM {legacy_table}
            WHERE user_uid IS NOT NULL
              AND {course_expr} IS NOT NULL
              AND {course_expr} <> ''
            """
        )
    )


def _migrate_legacy_path_row(session: Session, user_uid: str, path_data: dict[str, Any]) -> None:
    grade_plans = path_data.get("grade_plans")
    if not isinstance(grade_plans, dict):
        return

    now = datetime.now(timezone.utc)
    learning_goal = path_data.get("learning_goal")
    if not isinstance(learning_goal, dict):
        learning_goal = {}
    learning_topic = str(learning_goal.get("target_course_or_skill") or "")

    for grade_year, grade_plan in grade_plans.items():
        if not isinstance(grade_year, str) or not isinstance(grade_plan, dict):
            continue

        migrated_path = _build_year_path_from_legacy_grade(grade_year, grade_plan)
        row = session.exec(
            select(UserYearLearningPath).where(
                UserYearLearningPath.user_uid == user_uid,
                UserYearLearningPath.grade_year == grade_year,
            )
        ).first()

        if row is None:
            row = UserYearLearningPath(
                user_uid=user_uid,
                grade_year=grade_year,
                learning_topic=learning_topic,
                path_data=migrated_path,
                created_at=now,
                updated_at=now,
            )
        else:
            row.learning_topic = row.learning_topic or learning_topic
            row.path_data = migrated_path
            row.updated_at = now
        session.add(row)


def _build_year_path_from_legacy_grade(grade_year: str, grade_plan: dict[str, Any]) -> dict[str, Any]:
    courses = []
    sequence = []
    course_nodes = grade_plan.get("course_nodes")
    if not isinstance(course_nodes, list):
        course_nodes = []

    for course_node in course_nodes:
        if not isinstance(course_node, dict):
            continue
        course_id = str(course_node.get("course_node_id") or "")
        if not course_id:
            continue
        sequence.append(course_id)
        time_arrangement = course_node.get("time_arrangement")
        if not isinstance(time_arrangement, dict):
            time_arrangement = {}
        key_topics = _legacy_key_topics(course_node)
        courses.append(
            {
                "course_id": course_id,
                "course_name": str(course_node.get("course_or_chapter_theme") or ""),
                "description": str(course_node.get("course_goal") or ""),
                "semester": str(time_arrangement.get("semester_scope") or ""),
                "prerequisites": course_node.get("prerequisite_node_ids") or [],
                "estimated_duration": str(time_arrangement.get("duration") or ""),
                "learning_goal": str(course_node.get("course_goal") or ""),
                "key_topics": key_topics,
            }
        )

    return {
        "grade_year": grade_year,
        "grade_name": str(grade_plan.get("grade_name") or ""),
        "grade_goal": str(grade_plan.get("grade_goal") or ""),
        "courses": courses,
        "recommended_sequence": sequence,
        "personalization_notes": "由旧版四年路径迁移",
    }


def _legacy_key_topics(course_node: dict[str, Any]) -> list[str]:
    key_points = course_node.get("key_points")
    if isinstance(key_points, list) and all(isinstance(item, str) for item in key_points):
        return key_points

    knowledge_points = course_node.get("core_knowledge_points")
    if not isinstance(knowledge_points, list):
        return []

    topics = []
    for point in knowledge_points:
        if isinstance(point, dict) and isinstance(point.get("title"), str):
            topics.append(point["title"])
    return topics
