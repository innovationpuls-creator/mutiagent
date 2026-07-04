from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import CheckConstraint, UniqueConstraint, inspect, text
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app.models import (
    KnowledgeBaseIngestionJob,
    KnowledgeGap,
    KnowledgeGapFollow,
    KnowledgeGapNotice,
    KnowledgeSource,
    Textbook,
    TextbookExtensionResource,
    TextbookSectionContent,
    UserYearLearningPath,
)

_KNOWLEDGE_BASE_TABLE_MODELS = (
    KnowledgeSource,
    Textbook,
    TextbookSectionContent,
    TextbookExtensionResource,
    KnowledgeGap,
    KnowledgeGapFollow,
    KnowledgeGapNotice,
    KnowledgeBaseIngestionJob,
)


def run_schema_upgrades(engine: Engine) -> None:
    """Upgrade old local schemas to the current SQLModel schema.

    SQLModel creates missing tables, but it does not rename columns, rebuild
    primary keys, or drop tables that were removed from the model.
    """
    with engine.begin() as connection:
        _create_knowledge_base_tables(connection)
        _normalize_knowledge_gap_notice_action_payloads(connection)
        _ensure_knowledge_base_check_constraints(connection)
        _ensure_knowledge_base_unique_constraints(connection)
        _upgrade_textbook_section_content_original_column(connection)
        _recalculate_knowledge_gap_follow_counts(connection)
        _upgrade_user_role_column(connection)
        _migrate_teachers_to_admins(connection)
        _upgrade_user_cohort_columns(connection)
        _upgrade_course_knowledge_outline_table(connection)
        _upgrade_profile_json_storage(connection)
        _drop_removed_agent_conversation_table(connection)
        _upgrade_textbook_embedding_column(connection)


def migrate_removed_learning_path_table(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("userlearningpath"):
        return

    with Session(engine) as session:
        rows = session.exec(
            text("SELECT user_uid, path_data FROM userlearningpath")
        ).all()
        for user_uid, path_data in rows:
            if isinstance(path_data, str):
                path_data = json.loads(path_data)
            if not isinstance(path_data, dict):
                continue
            _migrate_legacy_path_row(session, str(user_uid), path_data)
        session.commit()

    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS userlearningpath"))


def _create_knowledge_base_tables(connection: Any) -> None:
    for model in _KNOWLEDGE_BASE_TABLE_MODELS:
        model.__table__.create(bind=connection, checkfirst=True)


def _ensure_knowledge_base_check_constraints(connection: Any) -> None:
    inspector = inspect(connection)
    for model in _KNOWLEDGE_BASE_TABLE_MODELS:
        table = model.__table__
        if not inspector.has_table(table.name):
            continue

        existing_names = {
            constraint["name"]
            for constraint in inspector.get_check_constraints(table.name)
        }
        for constraint in table.constraints:
            if not isinstance(constraint, CheckConstraint) or not constraint.name:
                continue
            if constraint.name in existing_names:
                if constraint.name != "ck_knowledgegapnotice_action_payload":
                    continue
                connection.execute(
                    text(f"ALTER TABLE {table.name} DROP CONSTRAINT {constraint.name}")
                )
            connection.execute(
                text(
                    f"ALTER TABLE {table.name} "
                    f"ADD CONSTRAINT {constraint.name} "
                    f"CHECK ({constraint.sqltext}) NOT VALID"
                )
            )


def _normalize_knowledge_gap_notice_action_payloads(connection: Any) -> None:
    inspector = inspect(connection)
    if not inspector.has_table(KnowledgeGapNotice.__tablename__):
        return

    columns = {
        column["name"]
        for column in inspector.get_columns(KnowledgeGapNotice.__tablename__)
    }
    if "action_payload" not in columns:
        return

    connection.execute(
        text(
            """
            UPDATE knowledgegapnotice
            SET action_payload = jsonb_build_object(
                'action', 'regenerate_learning_path_intake',
                'learning_topic', action_payload ->> 'learning_topic',
                'textbook_id', action_payload ->> 'textbook_id'
            )
            WHERE action_payload IS NOT NULL
                AND jsonb_typeof(action_payload) = 'object'
                AND (action_payload ? 'action')
                AND (action_payload ? 'learning_topic')
                AND (action_payload ? 'textbook_id')
                AND (
                    (action_payload ->> 'action')
                    = 'regenerate_learning_path_intake'
                )
                AND ((action_payload ->> 'learning_topic') IS NOT NULL)
                AND ((action_payload ->> 'textbook_id') IS NOT NULL)
                AND (
                    (action_payload - 'action' - 'learning_topic' - 'textbook_id')
                    <> '{}'::jsonb
                )
            """
        )
    )


def _ensure_knowledge_base_unique_constraints(connection: Any) -> None:
    inspector = inspect(connection)
    for model in _KNOWLEDGE_BASE_TABLE_MODELS:
        table = model.__table__
        if not inspector.has_table(table.name):
            continue

        existing_names = {
            constraint["name"]
            for constraint in inspector.get_unique_constraints(table.name)
        }
        for constraint in table.constraints:
            if not isinstance(constraint, UniqueConstraint) or not constraint.name:
                continue
            if constraint.name in existing_names:
                continue
            columns = ", ".join(column.name for column in constraint.columns)
            if constraint.name == "uq_knowledgegap_normalized_topic":
                _merge_duplicate_knowledge_gaps(connection)
            _remove_duplicate_rows_for_unique_constraint(
                connection, table.name, constraint
            )
            connection.execute(
                text(
                    f"ALTER TABLE {table.name} "
                    f"ADD CONSTRAINT {constraint.name} "
                    f"UNIQUE ({columns})"
                )
            )


def _upgrade_textbook_section_content_original_column(connection: Any) -> None:
    inspector = inspect(connection)
    table_name = TextbookSectionContent.__tablename__
    if not inspector.has_table(table_name):
        return

    columns = {column["name"] for column in inspector.get_columns(table_name)}
    if "content_original" not in columns:
        connection.execute(
            text(
                f"ALTER TABLE {table_name} "
                "ADD COLUMN content_original TEXT NOT NULL DEFAULT ''"
            )
        )
    connection.execute(
        text(
            f"UPDATE {table_name} "
            "SET content_original = content_zh "
            "WHERE content_original = '' AND content_zh <> ''"
        )
    )


def _merge_duplicate_knowledge_gaps(connection: Any) -> None:
    inspector = inspect(connection)
    if not inspector.has_table(KnowledgeGap.__tablename__):
        return

    if inspector.has_table(KnowledgeGapFollow.__tablename__):
        connection.execute(
            text(
                """
                WITH ranked_gaps AS (
                    SELECT
                        gap_id,
                        first_value(gap_id) OVER (
                            PARTITION BY normalized_topic
                            ORDER BY gap_id, ctid
                        ) AS retained_gap_id
                    FROM knowledgegap
                ),
                ranked_follows AS (
                    SELECT
                        knowledgegapfollow.ctid AS row_ctid,
                        row_number() OVER (
                            PARTITION BY
                                ranked_gaps.retained_gap_id,
                                knowledgegapfollow.user_uid
                            ORDER BY
                                knowledgegapfollow.follow_id,
                                knowledgegapfollow.ctid
                        ) AS row_rank
                    FROM knowledgegapfollow
                    JOIN ranked_gaps
                        ON ranked_gaps.gap_id = knowledgegapfollow.gap_id
                )
                DELETE FROM knowledgegapfollow
                WHERE ctid IN (
                    SELECT row_ctid
                    FROM ranked_follows
                    WHERE row_rank > 1
                )
                """
            )
        )
        connection.execute(
            text(
                """
                WITH ranked_gaps AS (
                    SELECT
                        gap_id,
                        first_value(gap_id) OVER (
                            PARTITION BY normalized_topic
                            ORDER BY gap_id, ctid
                        ) AS retained_gap_id
                    FROM knowledgegap
                )
                UPDATE knowledgegapfollow
                SET gap_id = ranked_gaps.retained_gap_id
                FROM ranked_gaps
                WHERE knowledgegapfollow.gap_id = ranked_gaps.gap_id
                    AND knowledgegapfollow.gap_id <> ranked_gaps.retained_gap_id
                """
            )
        )

    if inspector.has_table(KnowledgeGapNotice.__tablename__):
        connection.execute(
            text(
                """
                WITH ranked_gaps AS (
                    SELECT
                        gap_id,
                        first_value(gap_id) OVER (
                            PARTITION BY normalized_topic
                            ORDER BY gap_id, ctid
                        ) AS retained_gap_id
                    FROM knowledgegap
                ),
                ranked_notices AS (
                    SELECT
                        knowledgegapnotice.ctid AS row_ctid,
                        row_number() OVER (
                            PARTITION BY
                                ranked_gaps.retained_gap_id,
                                knowledgegapnotice.user_uid,
                                knowledgegapnotice.notice_type
                            ORDER BY
                                knowledgegapnotice.notice_id,
                                knowledgegapnotice.ctid
                        ) AS row_rank
                    FROM knowledgegapnotice
                    JOIN ranked_gaps
                        ON ranked_gaps.gap_id = knowledgegapnotice.gap_id
                )
                DELETE FROM knowledgegapnotice
                WHERE ctid IN (
                    SELECT row_ctid
                    FROM ranked_notices
                    WHERE row_rank > 1
                )
                """
            )
        )
        connection.execute(
            text(
                """
                WITH ranked_gaps AS (
                    SELECT
                        gap_id,
                        first_value(gap_id) OVER (
                            PARTITION BY normalized_topic
                            ORDER BY gap_id, ctid
                        ) AS retained_gap_id
                    FROM knowledgegap
                )
                UPDATE knowledgegapnotice
                SET gap_id = ranked_gaps.retained_gap_id
                FROM ranked_gaps
                WHERE knowledgegapnotice.gap_id = ranked_gaps.gap_id
                    AND knowledgegapnotice.gap_id <> ranked_gaps.retained_gap_id
                """
            )
        )

    _merge_knowledge_gap_parent_fields(connection)

    connection.execute(
        text(
            """
            DELETE FROM knowledgegap
            WHERE ctid IN (
                SELECT duplicate_ctid
                FROM (
                    SELECT
                        ctid AS duplicate_ctid,
                        row_number() OVER (
                            PARTITION BY normalized_topic
                            ORDER BY gap_id, ctid
                        ) AS duplicate_rank
                    FROM knowledgegap
                ) duplicate_rows
                WHERE duplicate_rank > 1
            )
            """
        )
    )


def _merge_knowledge_gap_parent_fields(connection: Any) -> None:
    connection.execute(
        text(
            """
            WITH ranked_gaps AS (
                SELECT
                    gap_id,
                    normalized_topic,
                    trigger_count,
                    latest_triggered_at,
                    student_goal_summaries,
                    status,
                    resolved_textbook_id,
                    resolved_at,
                    first_value(gap_id) OVER (
                        PARTITION BY normalized_topic
                        ORDER BY gap_id, ctid
                    ) AS retained_gap_id,
                    row_number() OVER (
                        PARTITION BY normalized_topic
                        ORDER BY gap_id, ctid
                    ) AS gap_rank
                FROM knowledgegap
            ),
            merged_counts AS (
                SELECT
                    retained_gap_id,
                    sum(coalesce(trigger_count, 0)) AS trigger_count,
                    max(latest_triggered_at) AS latest_triggered_at
                FROM ranked_gaps
                GROUP BY retained_gap_id
            ),
            unique_summaries AS (
                SELECT
                    retained_gap_id,
                    summary_text,
                    min(gap_rank) AS first_gap_rank,
                    min(summary_index) AS first_summary_index
                FROM ranked_gaps
                CROSS JOIN LATERAL jsonb_array_elements_text(
                    CASE
                        WHEN jsonb_typeof(student_goal_summaries) = 'array'
                        THEN student_goal_summaries
                        ELSE '[]'::jsonb
                    END
                ) WITH ORDINALITY AS summaries(summary_text, summary_index)
                GROUP BY retained_gap_id, summary_text
            ),
            merged_summaries AS (
                SELECT
                    retained_gap_id,
                    jsonb_agg(
                        summary_text
                        ORDER BY first_gap_rank, first_summary_index, summary_text
                    ) AS student_goal_summaries
                FROM unique_summaries
                GROUP BY retained_gap_id
            ),
            ranked_statuses AS (
                SELECT DISTINCT ON (retained_gap_id)
                    retained_gap_id,
                    status
                FROM ranked_gaps
                ORDER BY
                    retained_gap_id,
                    CASE status
                        WHEN 'closed' THEN 5
                        WHEN 'resolved' THEN 4
                        WHEN 'material_found' THEN 3
                        WHEN 'material_searching' THEN 2
                        WHEN 'open' THEN 1
                        ELSE 0
                    END DESC,
                    coalesce(resolved_at, latest_triggered_at) DESC NULLS LAST,
                    gap_id
            ),
            ranked_resolution AS (
                SELECT DISTINCT ON (retained_gap_id)
                    retained_gap_id,
                    resolved_textbook_id,
                    resolved_at
                FROM ranked_gaps
                WHERE
                    status = 'resolved'
                    OR resolved_textbook_id IS NOT NULL
                    OR resolved_at IS NOT NULL
                ORDER BY
                    retained_gap_id,
                    resolved_at DESC NULLS LAST,
                    latest_triggered_at DESC NULLS LAST,
                    gap_id
            )
            UPDATE knowledgegap
            SET
                trigger_count = merged_counts.trigger_count,
                latest_triggered_at = merged_counts.latest_triggered_at,
                student_goal_summaries = coalesce(
                    merged_summaries.student_goal_summaries,
                    '[]'::jsonb
                ),
                status = ranked_statuses.status,
                resolved_textbook_id = coalesce(
                    ranked_resolution.resolved_textbook_id,
                    knowledgegap.resolved_textbook_id
                ),
                resolved_at = coalesce(
                    ranked_resolution.resolved_at,
                    knowledgegap.resolved_at
                )
            FROM merged_counts
            LEFT JOIN merged_summaries
                ON merged_summaries.retained_gap_id = merged_counts.retained_gap_id
            JOIN ranked_statuses
                ON ranked_statuses.retained_gap_id = merged_counts.retained_gap_id
            LEFT JOIN ranked_resolution
                ON ranked_resolution.retained_gap_id = merged_counts.retained_gap_id
            WHERE knowledgegap.gap_id = merged_counts.retained_gap_id
            """
        )
    )


def _remove_duplicate_rows_for_unique_constraint(
    connection: Any,
    table_name: str,
    constraint: UniqueConstraint,
) -> None:
    unique_columns = [column.name for column in constraint.columns]
    primary_key_columns = [column.name for column in constraint.table.primary_key]
    if not unique_columns or not primary_key_columns:
        return

    preparer = connection.dialect.identifier_preparer
    quoted_table = preparer.quote(table_name)
    partition_columns = ", ".join(preparer.quote(column) for column in unique_columns)
    order_columns = ", ".join(preparer.quote(column) for column in primary_key_columns)
    connection.execute(
        text(
            f"""
            DELETE FROM {quoted_table}
            WHERE ctid IN (
                SELECT duplicate_ctid
                FROM (
                    SELECT
                        ctid AS duplicate_ctid,
                        row_number() OVER (
                            PARTITION BY {partition_columns}
                            ORDER BY {order_columns}, ctid
                        ) AS duplicate_rank
                    FROM {quoted_table}
                ) duplicate_rows
                WHERE duplicate_rank > 1
            )
            """
        )
    )


def _recalculate_knowledge_gap_follow_counts(connection: Any) -> None:
    inspector = inspect(connection)
    if not inspector.has_table(KnowledgeGap.__tablename__) or not inspector.has_table(
        KnowledgeGapFollow.__tablename__
    ):
        return

    gap_columns = {
        column["name"] for column in inspector.get_columns(KnowledgeGap.__tablename__)
    }
    follow_columns = {
        column["name"]
        for column in inspector.get_columns(KnowledgeGapFollow.__tablename__)
    }
    if "follow_count" not in gap_columns or "gap_id" not in follow_columns:
        return

    connection.execute(
        text(
            """
            UPDATE knowledgegap
            SET follow_count = (
                SELECT count(*)
                FROM knowledgegapfollow
                WHERE knowledgegapfollow.gap_id = knowledgegap.gap_id
            )
            """
        )
    )


def _drop_removed_agent_conversation_table(connection: Any) -> None:
    connection.execute(text("DROP TABLE IF EXISTS useragentconversation"))


def _upgrade_user_role_column(connection: Any) -> None:
    inspector = inspect(connection)
    if not inspector.has_table("user"):
        return

    columns = {column["name"] for column in inspector.get_columns("user")}
    if "role" in columns:
        return

    connection.execute(
        text(
            'ALTER TABLE "user" ADD COLUMN role VARCHAR(16) '
            "NOT NULL DEFAULT 'student'"
        )
    )
    connection.execute(text('CREATE INDEX IF NOT EXISTS ix_user_role ON "user" (role)'))


def _migrate_teachers_to_admins(connection: Any) -> None:
    inspector = inspect(connection)
    if not inspector.has_table("user"):
        return
    connection.execute(
        text("UPDATE \"user\" SET role = 'admin' WHERE role = 'teacher';")
    )


def _upgrade_user_cohort_columns(connection: Any) -> None:
    inspector = inspect(connection)
    if not inspector.has_table("user"):
        return

    columns = {column["name"] for column in inspector.get_columns("user")}
    for column_name in ("school", "major", "class_name"):
        if column_name not in columns:
            connection.execute(
                text(
                    f'ALTER TABLE "user" ADD COLUMN {column_name} '
                    "VARCHAR(128) NOT NULL DEFAULT ''"
                )
            )
            connection.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS ix_user_{column_name} "
                    f'ON "user" ({column_name})'
                )
            )


def _upgrade_profile_json_storage(connection: Any) -> None:
    inspector = inspect(connection)
    if not inspector.has_table("userprofile"):
        return
    connection.execute(
        text(
            "ALTER TABLE userprofile ALTER COLUMN profile_data "
            "TYPE JSONB USING profile_data::jsonb"
        )
    )


def _upgrade_course_knowledge_outline_table(connection: Any) -> None:
    inspector = inspect(connection)
    if not inspector.has_table("usercourseknowledgeoutline"):
        return

    columns = {
        column["name"] for column in inspector.get_columns("usercourseknowledgeoutline")
    }
    needs_rebuild = not {"course_id", "grade_year"}.issubset(columns)
    outline_type = next(
        (
            str(column["type"]).lower()
            for column in inspector.get_columns("usercourseknowledgeoutline")
            if column["name"] == "outline_data"
        ),
        "",
    )
    needs_rebuild = needs_rebuild or outline_type != "jsonb"

    if not needs_rebuild:
        return

    legacy_table = "usercourseknowledgeoutline_legacy_upgrade"
    connection.execute(text(f"DROP TABLE IF EXISTS {legacy_table}"))
    connection.execute(
        text(f"ALTER TABLE usercourseknowledgeoutline RENAME TO {legacy_table}")
    )
    _create_course_knowledge_outline_table(connection)
    _copy_course_knowledge_outline_rows(connection, legacy_table)
    connection.execute(text(f"DROP TABLE IF EXISTS {legacy_table}"))


def _create_course_knowledge_outline_table(connection: Any) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE usercourseknowledgeoutline (
                user_uid VARCHAR NOT NULL,
                course_id VARCHAR(128) NOT NULL,
                grade_year VARCHAR(16) NOT NULL,
                course_name VARCHAR(256) NOT NULL,
                outline_data JSONB,
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
    outline_expr = "outline_data::jsonb"

    connection.execute(
        text(
            f"""
            INSERT INTO usercourseknowledgeoutline
                (user_uid, course_id, grade_year, course_name,
                 outline_data, created_at, updated_at)
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


def _migrate_legacy_path_row(
    session: Session, user_uid: str, path_data: dict[str, Any]
) -> None:
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


def _build_year_path_from_legacy_grade(
    grade_year: str, grade_plan: dict[str, Any]
) -> dict[str, Any]:
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
    if isinstance(key_points, list) and all(
        isinstance(item, str) for item in key_points
    ):
        return key_points

    knowledge_points = course_node.get("core_knowledge_points")
    if not isinstance(knowledge_points, list):
        return []

    topics = []
    for point in knowledge_points:
        if isinstance(point, dict) and isinstance(point.get("title"), str):
            topics.append(point["title"])
    return topics


def _upgrade_textbook_embedding_column(connection: Any) -> None:
    inspector = inspect(connection)
    if not inspector.has_table("textbook"):
        return

    columns = {column["name"] for column in inspector.get_columns("textbook")}
    if "embedding" in columns:
        return

    connection.execute(text("ALTER TABLE textbook ADD COLUMN embedding FLOAT[]"))
