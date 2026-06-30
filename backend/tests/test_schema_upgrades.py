from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from app.models import User, UserCourseKnowledgeOutline, UserYearLearningPath
from app.schema_upgrades import migrate_removed_learning_path_table, run_schema_upgrades
from tests.postgres import postgresql_test_url


def test_schema_upgrades_rebuild_legacy_tables(tmp_path: Path) -> None:
    engine = create_engine(
        postgresql_test_url(tmp_path, "upgrade"),
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
                        "time_arrangement": {
                            "semester_scope": "上学期",
                            "duration": "8 周",
                        },
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
        session.add(
            User(uid="user-1", username="升级用户", identifier="upgrade@example.com")
        )
        session.commit()

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO usercourseknowledgeoutline
                    (
                        user_uid, course_node_id, grade_id, course_name,
                        outline_data, created_at, updated_at
                    )
                VALUES
                    (
                        'user-1', 'year_2_course_1', 'year_2', '数据结构基础',
                        '{"sections":[]}', '2026-06-01 00:00:00',
                        '2026-06-02 00:00:00'
                    )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO userlearningpath
                    (user_uid, path_data, created_at, updated_at)
                VALUES
                    (
                        :user_uid, :path_data, '2026-06-01 00:00:00',
                        '2026-06-02 00:00:00'
                    )
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
                    (
                        'user-1', 'profile_agent', 'legacy-conv',
                        '2026-06-01 00:00:00', '2026-06-02 00:00:00'
                    )
                """
            )
        )

    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)
    migrate_removed_learning_path_table(engine)

    inspector = inspect(engine)
    assert not inspector.has_table("useragentconversation")
    assert not inspector.has_table("userlearningpath")

    outline_columns = {
        column["name"] for column in inspector.get_columns("usercourseknowledgeoutline")
    }
    assert {
        "user_uid",
        "course_id",
        "grade_year",
        "course_name",
        "outline_data",
    }.issubset(outline_columns)
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


def test_schema_upgrades_remove_legacy_knowledge_gap_duplicates(
    tmp_path: Path,
) -> None:
    engine = create_engine(
        postgresql_test_url(tmp_path, "knowledge-gap-duplicates"),
    )

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE knowledgegap (
                    gap_id VARCHAR(64) NOT NULL PRIMARY KEY,
                    normalized_topic VARCHAR(256) NOT NULL,
                    trigger_count INTEGER NOT NULL,
                    follow_count INTEGER NOT NULL,
                    latest_triggered_at TIMESTAMP,
                    student_goal_summaries JSONB NOT NULL,
                    status VARCHAR(32) NOT NULL,
                    resolved_textbook_id VARCHAR(64),
                    resolved_at TIMESTAMP
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE knowledgegapfollow (
                    follow_id VARCHAR(64) NOT NULL PRIMARY KEY,
                    gap_id VARCHAR(64) NOT NULL,
                    user_uid VARCHAR(64) NOT NULL,
                    created_at TIMESTAMP NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO knowledgegap
                    (
                        gap_id, normalized_topic, trigger_count, follow_count,
                        latest_triggered_at, student_goal_summaries, status,
                        resolved_textbook_id, resolved_at
                    )
                VALUES
                    (
                        'gap-1', '线性代数', 1, 99, NULL, '[]'::jsonb,
                        'open', NULL, NULL
                    ),
                    (
                        'gap-2', '概率论', 1, 99, NULL, '[]'::jsonb,
                        'open', NULL, NULL
                    )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE knowledgegapnotice (
                    notice_id VARCHAR(64) NOT NULL PRIMARY KEY,
                    gap_id VARCHAR(64) NOT NULL,
                    user_uid VARCHAR(64) NOT NULL,
                    notice_type VARCHAR(64) NOT NULL,
                    title VARCHAR(256) NOT NULL,
                    body VARCHAR NOT NULL,
                    action_label VARCHAR(64) NOT NULL,
                    action_payload JSONB NOT NULL,
                    read_at TIMESTAMP,
                    created_at TIMESTAMP NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO knowledgegapfollow
                    (follow_id, gap_id, user_uid, created_at)
                VALUES
                    ('gap-follow-002', 'gap-1', 'user-1', '2026-06-02 00:00:00'),
                    ('gap-follow-001', 'gap-1', 'user-1', '2026-06-01 00:00:00'),
                    ('gap-follow-003', 'gap-2', 'user-1', '2026-06-03 00:00:00')
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO knowledgegapnotice
                    (
                        notice_id, gap_id, user_uid, notice_type, title, body,
                        action_label, action_payload, read_at, created_at
                    )
                VALUES
                    (
                        'gap-notice-002', 'gap-1', 'user-1',
                        'knowledge_gap_resolved', '线性代数已补齐', '',
                        '重新生成学习路径',
                        '{"action":"regenerate_learning_path_intake","learning_topic":"线性代数","textbook_id":"textbook-1"}'::jsonb,
                        NULL, '2026-06-02 00:00:00'
                    ),
                    (
                        'gap-notice-001', 'gap-1', 'user-1',
                        'knowledge_gap_resolved', '线性代数已补齐', '',
                        '重新生成学习路径',
                        '{"action":"regenerate_learning_path_intake","learning_topic":"线性代数","textbook_id":"textbook-1"}'::jsonb,
                        NULL, '2026-06-01 00:00:00'
                    ),
                    (
                        'gap-notice-003', 'gap-2', 'user-1',
                        'knowledge_gap_resolved', '概率论已补齐', '',
                        '重新生成学习路径',
                        '{"action":"regenerate_learning_path_intake","learning_topic":"概率论","textbook_id":"textbook-2"}'::jsonb,
                        NULL, '2026-06-03 00:00:00'
                    )
                """
            )
        )

    run_schema_upgrades(engine)

    inspector = inspect(engine)
    follow_unique_names = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("knowledgegapfollow")
    }
    notice_unique_names = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("knowledgegapnotice")
    }
    assert "uq_knowledgegapfollow_gap_user" in follow_unique_names
    assert "uq_knowledgegapnotice_gap_user_type" in notice_unique_names

    with engine.connect() as connection:
        gap_rows = connection.execute(
            text(
                """
                SELECT gap_id, follow_count
                FROM knowledgegap
                ORDER BY gap_id
                """
            )
        ).all()
        follow_rows = connection.execute(
            text(
                """
                SELECT gap_id, user_uid, array_agg(follow_id ORDER BY follow_id)
                FROM knowledgegapfollow
                GROUP BY gap_id, user_uid
                ORDER BY gap_id, user_uid
                """
            )
        ).all()
        notice_rows = connection.execute(
            text(
                """
                SELECT
                    gap_id,
                    user_uid,
                    notice_type,
                    array_agg(notice_id ORDER BY notice_id)
                FROM knowledgegapnotice
                GROUP BY gap_id, user_uid, notice_type
                ORDER BY gap_id, user_uid, notice_type
                """
            )
        ).all()

    assert follow_rows == [
        ("gap-1", "user-1", ["gap-follow-001"]),
        ("gap-2", "user-1", ["gap-follow-003"]),
    ]
    assert notice_rows == [
        ("gap-1", "user-1", "knowledge_gap_resolved", ["gap-notice-001"]),
        ("gap-2", "user-1", "knowledge_gap_resolved", ["gap-notice-003"]),
    ]
    assert gap_rows == [("gap-1", 1), ("gap-2", 1)]

    run_schema_upgrades(engine)

    with engine.connect() as connection:
        repeated_gap_rows = connection.execute(
            text(
                """
                SELECT gap_id, follow_count
                FROM knowledgegap
                ORDER BY gap_id
                """
            )
        ).all()
        repeated_follow_rows = connection.execute(
            text(
                """
                SELECT gap_id, user_uid, array_agg(follow_id ORDER BY follow_id)
                FROM knowledgegapfollow
                GROUP BY gap_id, user_uid
                ORDER BY gap_id, user_uid
                """
            )
        ).all()
        repeated_notice_rows = connection.execute(
            text(
                """
                SELECT
                    gap_id,
                    user_uid,
                    notice_type,
                    array_agg(notice_id ORDER BY notice_id)
                FROM knowledgegapnotice
                GROUP BY gap_id, user_uid, notice_type
                ORDER BY gap_id, user_uid, notice_type
                """
            )
        ).all()

    assert repeated_gap_rows == gap_rows
    assert repeated_follow_rows == follow_rows
    assert repeated_notice_rows == notice_rows


def test_schema_upgrades_merge_legacy_duplicate_knowledge_gap_topics(
    tmp_path: Path,
) -> None:
    engine = create_engine(
        postgresql_test_url(tmp_path, "knowledge-gap-topic-duplicates"),
    )

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE knowledgegap (
                    gap_id VARCHAR(64) NOT NULL PRIMARY KEY,
                    normalized_topic VARCHAR(256) NOT NULL,
                    trigger_count INTEGER NOT NULL,
                    follow_count INTEGER NOT NULL,
                    latest_triggered_at TIMESTAMP,
                    student_goal_summaries JSONB NOT NULL,
                    status VARCHAR(32) NOT NULL,
                    resolved_textbook_id VARCHAR(64),
                    resolved_at TIMESTAMP
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE knowledgegapfollow (
                    follow_id VARCHAR(64) NOT NULL PRIMARY KEY,
                    gap_id VARCHAR(64) NOT NULL,
                    user_uid VARCHAR(64) NOT NULL,
                    created_at TIMESTAMP NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE knowledgegapnotice (
                    notice_id VARCHAR(64) NOT NULL PRIMARY KEY,
                    gap_id VARCHAR(64) NOT NULL,
                    user_uid VARCHAR(64) NOT NULL,
                    notice_type VARCHAR(64) NOT NULL,
                    title VARCHAR(256) NOT NULL,
                    body VARCHAR NOT NULL,
                    action_label VARCHAR(64) NOT NULL,
                    action_payload JSONB NOT NULL,
                    read_at TIMESTAMP,
                    created_at TIMESTAMP NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO knowledgegap
                    (
                        gap_id, normalized_topic, trigger_count, follow_count,
                        latest_triggered_at, student_goal_summaries, status,
                        resolved_textbook_id, resolved_at
                    )
                VALUES
                    (
                        'gap-dup-002', '线性代数', 3, 99,
                        '2026-06-03 00:00:00',
                        '["准备学习矩阵","需要补齐向量空间"]'::jsonb,
                        'resolved', 'textbook-1', '2026-06-04 00:00:00'
                    ),
                    (
                        'gap-dup-001', '线性代数', 2, 99,
                        '2026-06-01 00:00:00',
                        '["准备学习矩阵"]'::jsonb,
                        'open', NULL, NULL
                    ),
                    (
                        'gap-other', '概率论', 1, 99, NULL, '[]'::jsonb,
                        'open', NULL, NULL
                    )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO knowledgegapfollow
                    (follow_id, gap_id, user_uid, created_at)
                VALUES
                    ('gap-follow-002', 'gap-dup-002', 'user-1', '2026-06-02 00:00:00'),
                    ('gap-follow-001', 'gap-dup-001', 'user-1', '2026-06-01 00:00:00'),
                    ('gap-follow-003', 'gap-dup-002', 'user-2', '2026-06-03 00:00:00')
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO knowledgegapnotice
                    (
                        notice_id, gap_id, user_uid, notice_type, title, body,
                        action_label, action_payload, read_at, created_at
                    )
                VALUES
                    (
                        'gap-notice-002', 'gap-dup-002', 'user-1',
                        'knowledge_gap_resolved', '线性代数已补齐', '',
                        '重新生成学习路径',
                        '{"action":"regenerate_learning_path_intake","learning_topic":"线性代数","textbook_id":"textbook-1"}'::jsonb,
                        NULL, '2026-06-02 00:00:00'
                    ),
                    (
                        'gap-notice-001', 'gap-dup-001', 'user-1',
                        'knowledge_gap_resolved', '线性代数已补齐', '',
                        '重新生成学习路径',
                        '{"action":"regenerate_learning_path_intake","learning_topic":"线性代数","textbook_id":"textbook-1"}'::jsonb,
                        NULL, '2026-06-01 00:00:00'
                    ),
                    (
                        'gap-notice-003', 'gap-dup-002', 'user-2',
                        'knowledge_gap_resolved', '线性代数已补齐', '',
                        '重新生成学习路径',
                        '{"action":"regenerate_learning_path_intake","learning_topic":"线性代数","textbook_id":"textbook-1"}'::jsonb,
                        NULL, '2026-06-03 00:00:00'
                    )
                """
            )
        )

    run_schema_upgrades(engine)

    inspector = inspect(engine)
    gap_unique_names = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("knowledgegap")
    }
    assert "uq_knowledgegap_normalized_topic" in gap_unique_names

    with engine.connect() as connection:
        gap_rows = connection.execute(
            text(
                """
                SELECT
                    gap_id,
                    normalized_topic,
                    trigger_count,
                    follow_count,
                    to_char(latest_triggered_at, 'YYYY-MM-DD HH24:MI:SS'),
                    student_goal_summaries,
                    status,
                    resolved_textbook_id,
                    to_char(resolved_at, 'YYYY-MM-DD HH24:MI:SS')
                FROM knowledgegap
                ORDER BY gap_id
                """
            )
        ).all()
        follow_rows = connection.execute(
            text(
                """
                SELECT gap_id, user_uid, array_agg(follow_id ORDER BY follow_id)
                FROM knowledgegapfollow
                GROUP BY gap_id, user_uid
                ORDER BY gap_id, user_uid
                """
            )
        ).all()
        notice_rows = connection.execute(
            text(
                """
                SELECT
                    gap_id,
                    user_uid,
                    notice_type,
                    array_agg(notice_id ORDER BY notice_id)
                FROM knowledgegapnotice
                GROUP BY gap_id, user_uid, notice_type
                ORDER BY gap_id, user_uid, notice_type
                """
            )
        ).all()

    assert gap_rows == [
        (
            "gap-dup-001",
            "线性代数",
            5,
            2,
            "2026-06-03 00:00:00",
            ["准备学习矩阵", "需要补齐向量空间"],
            "resolved",
            "textbook-1",
            "2026-06-04 00:00:00",
        ),
        ("gap-other", "概率论", 1, 0, None, [], "open", None, None),
    ]
    assert follow_rows == [
        ("gap-dup-001", "user-1", ["gap-follow-001"]),
        ("gap-dup-001", "user-2", ["gap-follow-003"]),
    ]
    assert notice_rows == [
        (
            "gap-dup-001",
            "user-1",
            "knowledge_gap_resolved",
            ["gap-notice-001"],
        ),
        (
            "gap-dup-001",
            "user-2",
            "knowledge_gap_resolved",
            ["gap-notice-003"],
        ),
    ]

    run_schema_upgrades(engine)

    with engine.connect() as connection:
        repeated_gap_rows = connection.execute(
            text(
                """
                SELECT
                    gap_id,
                    normalized_topic,
                    trigger_count,
                    follow_count,
                    to_char(latest_triggered_at, 'YYYY-MM-DD HH24:MI:SS'),
                    student_goal_summaries,
                    status,
                    resolved_textbook_id,
                    to_char(resolved_at, 'YYYY-MM-DD HH24:MI:SS')
                FROM knowledgegap
                ORDER BY gap_id
                """
            )
        ).all()
        repeated_follow_rows = connection.execute(
            text(
                """
                SELECT gap_id, user_uid, array_agg(follow_id ORDER BY follow_id)
                FROM knowledgegapfollow
                GROUP BY gap_id, user_uid
                ORDER BY gap_id, user_uid
                """
            )
        ).all()
        repeated_notice_rows = connection.execute(
            text(
                """
                SELECT
                    gap_id,
                    user_uid,
                    notice_type,
                    array_agg(notice_id ORDER BY notice_id)
                FROM knowledgegapnotice
                GROUP BY gap_id, user_uid, notice_type
                ORDER BY gap_id, user_uid, notice_type
                """
            )
        ).all()

    assert repeated_gap_rows == gap_rows
    assert repeated_follow_rows == follow_rows
    assert repeated_notice_rows == notice_rows
