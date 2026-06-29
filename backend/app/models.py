from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, Float, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlmodel import Field, SQLModel

_jsonb = JSONB(none_as_null=False)

KNOWLEDGE_SOURCE_STATUS_VALUES = ("enabled", "disabled")
KNOWLEDGE_SOURCE_DOWNLOAD_STATUS_VALUES = ("unverified", "verified", "failed")
KNOWLEDGE_SOURCE_PARSE_STATUS_VALUES = ("unverified", "supported", "failed")
KNOWLEDGE_SOURCE_LICENSE_REVIEW_STATUS_VALUES = (
    "unreviewed",
    "approved",
    "rejected",
)
KNOWLEDGE_SOURCE_HUMAN_REVIEW_STATUS_VALUES = ("unreviewed", "reviewed")
TEXTBOOK_INGESTION_STATUS_VALUES = (
    "not_started",
    "processing",
    "failed",
    "ready_for_outline_review",
    "completed",
)
TEXTBOOK_OUTLINE_REVIEW_STATUS_VALUES = ("unreviewed", "approved")
TEXTBOOK_STUDENT_AVAILABILITY_STATUS_VALUES = (
    "draft",
    "published",
    "unpublished",
    "archived",
)
TEXTBOOK_EXTENSION_RESOURCE_RENDER_MODE_VALUES = ("reader", "video", "webpage")
KNOWLEDGE_GAP_STATUS_VALUES = (
    "open",
    "material_searching",
    "material_found",
    "resolved",
    "closed",
)
KNOWLEDGE_GAP_NOTICE_TYPE_VALUES = ("knowledge_gap_resolved",)
KNOWLEDGE_GAP_NOTICE_ACTION_VALUES = ("regenerate_learning_path_intake",)
KNOWLEDGE_BASE_INGESTION_JOB_STATUS_VALUES = (
    "queued",
    "running",
    "failed",
    "completed",
)
KNOWLEDGE_GAP_NOTICE_ACTION_VALUE = KNOWLEDGE_GAP_NOTICE_ACTION_VALUES[0]


def _check_in_values(column_name: str, values: tuple[str, ...]) -> str:
    allowed_values = ", ".join(f"'{value}'" for value in values)
    return f"{column_name} IN ({allowed_values})"


KNOWLEDGE_GAP_NOTICE_ACTION_PAYLOAD_CHECK_SQL = (
    "(action_payload IS NOT NULL) "
    "AND (jsonb_typeof(action_payload) = 'object') "
    "AND (action_payload ? 'action') "
    "AND (action_payload ? 'learning_topic') "
    "AND (action_payload ? 'textbook_id') "
    "AND ("
    "(action_payload - 'action' - 'learning_topic' - 'textbook_id') = '{}'::jsonb"
    ") "
    f"AND ((action_payload ->> 'action') = '{KNOWLEDGE_GAP_NOTICE_ACTION_VALUE}') "
    "AND ((action_payload ->> 'learning_topic') IS NOT NULL) "
    "AND ((action_payload ->> 'textbook_id') IS NOT NULL)"
)


class User(SQLModel, table=True):
    uid: str = Field(primary_key=True)
    username: str = Field(index=True, min_length=1, max_length=64)
    identifier: str = Field(index=True, unique=True, min_length=3, max_length=128)
    role: str = Field(default="student", index=True, max_length=16)
    school: str = Field(default="", index=True, max_length=128)
    major: str = Field(default="", index=True, max_length=128)
    class_name: str = Field(default="", index=True, max_length=128)
    provider: str = Field(default="password", index=True, max_length=32)
    password_hash: str | None = Field(default=None, max_length=128)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login_at: datetime | None = Field(default=None)


class CultivationProgram(SQLModel, table=True):
    """Published human cultivation program for one school/major/class scope."""

    __table_args__ = (
        UniqueConstraint(
            "school", "major", "class_name", name="uq_cultivation_program_cohort"
        ),
        Index("idx_cultivation_program_teacher", "teacher_uid"),
        Index("idx_cultivation_program_cohort", "school", "major", "class_name"),
    )

    program_id: str = Field(primary_key=True, max_length=64)
    teacher_uid: str = Field(foreign_key="user.uid", index=True)
    school: str = Field(index=True, max_length=128)
    major: str = Field(index=True, max_length=128)
    class_name: str = Field(index=True, max_length=128)
    courses: list = Field(default_factory=list, sa_column=Column(_jsonb))
    published_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UserProfile(SQLModel, table=True):
    user_uid: str = Field(foreign_key="user.uid", primary_key=True)
    profile_data: dict = Field(default_factory=dict, sa_column=Column(_jsonb))
    profile_text: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UserYearLearningPath(SQLModel, table=True):
    """每个用户每年一条记录，按年存储学习路径（简版 Schema）。"""

    __table_args__ = (
        Index("idx_year_learning_path_updated", "user_uid", "updated_at"),
    )
    user_uid: str = Field(foreign_key="user.uid", primary_key=True)
    grade_year: str = Field(primary_key=True, max_length=16)
    learning_topic: str = Field(default="", max_length=256)
    path_data: dict = Field(default_factory=dict, sa_column=Column(_jsonb))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UserCourseKnowledgeOutline(SQLModel, table=True):
    """课程大纲（详版 Schema），按课程节点存储。"""

    __table_args__ = (
        Index("idx_course_knowledge_user_grade", "user_uid", "grade_year"),
    )
    user_uid: str = Field(foreign_key="user.uid", primary_key=True)
    course_id: str = Field(primary_key=True, max_length=128)
    grade_year: str = Field(index=True, max_length=16)
    course_name: str = Field(default="", max_length=256)
    outline_data: dict = Field(default_factory=dict, sa_column=Column(_jsonb))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChapterQuiz(SQLModel, table=True):
    """Generated quiz for one user/course/chapter."""

    __table_args__ = (
        UniqueConstraint(
            "user_uid", "course_node_id", "chapter_id", name="uq_chapter_quiz_scope"
        ),
        Index("idx_chapter_quiz_user_course", "user_uid", "course_node_id"),
    )

    quiz_id: str = Field(primary_key=True, max_length=64)
    user_uid: str = Field(foreign_key="user.uid", index=True)
    course_node_id: str = Field(index=True, max_length=128)
    chapter_id: str = Field(index=True, max_length=64)
    status: str = Field(default="ready", index=True, max_length=24)
    questions: list = Field(default_factory=list, sa_column=Column(_jsonb))
    source_outline_version: str = Field(default="", max_length=64)
    generation_error: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChapterQuizAttempt(SQLModel, table=True):
    """Submitted answer set and grading result for a quiz."""

    __table_args__ = (
        Index("idx_chapter_quiz_attempt_user_quiz", "user_uid", "quiz_id"),
    )

    attempt_id: str = Field(primary_key=True, max_length=64)
    quiz_id: str = Field(foreign_key="chapterquiz.quiz_id", index=True, max_length=64)
    user_uid: str = Field(foreign_key="user.uid", index=True)
    answers: dict = Field(default_factory=dict, sa_column=Column(_jsonb))
    score: int = Field(default=0)
    passed: bool = Field(default=False, index=True)
    grading_result: dict = Field(default_factory=dict, sa_column=Column(_jsonb))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChapterProgress(SQLModel, table=True):
    """Unlock state for one user/course/chapter."""

    __table_args__ = (
        Index("idx_chapter_progress_user_course", "user_uid", "course_node_id"),
    )

    user_uid: str = Field(foreign_key="user.uid", primary_key=True)
    course_node_id: str = Field(primary_key=True, max_length=128)
    chapter_id: str = Field(primary_key=True, max_length=64)
    state: str = Field(default="locked", index=True, max_length=24)
    best_score: int = Field(default=0)
    latest_attempt_id: str | None = Field(default=None, max_length=64)
    passed_at: datetime | None = Field(default=None)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChapterWeakness(SQLModel, table=True):
    """薄弱知识点记录，由测验表现分析产生。"""

    __table_args__ = (
        Index("idx_chapter_weakness_user_course", "user_uid", "course_node_id"),
        Index("idx_chapter_weakness_consumed", "user_uid", "consumed"),
    )

    weakness_id: str = Field(primary_key=True, max_length=64)
    user_uid: str = Field(foreign_key="user.uid", index=True)
    course_node_id: str = Field(max_length=128)
    chapter_id: str = Field(max_length=64)
    knowledge_point_id: str = Field(max_length=128)
    knowledge_point_name: str = Field(default="", max_length=256)
    severity: int = Field(default=1, ge=1, le=3)
    consumed: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CourseResourceQuality(SQLModel, table=True):
    """Automated quality scores for generated course resources."""

    __table_args__ = (
        Index("idx_resource_quality_user_course", "user_uid", "course_node_id"),
    )

    user_uid: str = Field(foreign_key="user.uid", primary_key=True)
    course_node_id: str = Field(primary_key=True, max_length=128)
    accuracy_score: int = Field(default=0, ge=0, le=100)
    difficulty_fit_score: int = Field(default=0, ge=0, le=100)
    completeness_score: int = Field(default=0, ge=0, le=100)
    overall_score: int = Field(default=0, ge=0, le=100)
    suggestions: list = Field(default_factory=list, sa_column=Column(_jsonb))
    scored_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ConversationSession(SQLModel, table=True):
    """持久化会话消息，替代 LangGraph MemorySaver。"""

    __table_args__ = (Index("idx_conversation_user_time", "user_uid", "updated_at"),)
    session_id: str = Field(primary_key=True)
    user_uid: str = Field(foreign_key="user.uid", index=True)
    messages: list = Field(default_factory=list, sa_column=Column(_jsonb))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class KnowledgeSource(SQLModel, table=True):
    __table_args__ = (
        CheckConstraint(
            _check_in_values("status", KNOWLEDGE_SOURCE_STATUS_VALUES),
            name="ck_knowledgesource_status",
        ),
        CheckConstraint(
            _check_in_values(
                "download_status", KNOWLEDGE_SOURCE_DOWNLOAD_STATUS_VALUES
            ),
            name="ck_knowledgesource_download_status",
        ),
        CheckConstraint(
            _check_in_values("parse_status", KNOWLEDGE_SOURCE_PARSE_STATUS_VALUES),
            name="ck_knowledgesource_parse_status",
        ),
        CheckConstraint(
            _check_in_values(
                "license_review_status",
                KNOWLEDGE_SOURCE_LICENSE_REVIEW_STATUS_VALUES,
            ),
            name="ck_knowledgesource_license_review_status",
        ),
        CheckConstraint(
            _check_in_values(
                "human_review_status", KNOWLEDGE_SOURCE_HUMAN_REVIEW_STATUS_VALUES
            ),
            name="ck_knowledgesource_human_review_status",
        ),
    )

    source_id: str = Field(primary_key=True, max_length=64)
    name: str = Field(index=True, max_length=256)
    base_url: str = Field(default="", max_length=1024)
    status: str = Field(default="enabled", index=True, max_length=16)
    source_kind: str = Field(default="", index=True, max_length=64)
    download_requirement: str = Field(default="")
    ai_search_requirement: str = Field(default="")
    download_status: str = Field(default="unverified", index=True, max_length=16)
    parse_status: str = Field(default="unverified", index=True, max_length=16)
    license_review_status: str = Field(default="unreviewed", index=True, max_length=16)
    human_review_status: str = Field(default="unreviewed", index=True, max_length=16)


class Textbook(SQLModel, table=True):
    __table_args__ = (
        CheckConstraint(
            _check_in_values("ingestion_status", TEXTBOOK_INGESTION_STATUS_VALUES),
            name="ck_textbook_ingestion_status",
        ),
        CheckConstraint(
            _check_in_values(
                "outline_review_status", TEXTBOOK_OUTLINE_REVIEW_STATUS_VALUES
            ),
            name="ck_textbook_outline_review_status",
        ),
        CheckConstraint(
            _check_in_values(
                "student_availability_status",
                TEXTBOOK_STUDENT_AVAILABILITY_STATUS_VALUES,
            ),
            name="ck_textbook_student_availability_status",
        ),
    )

    textbook_id: str = Field(primary_key=True, max_length=64)
    source_id: str = Field(index=True, max_length=64)
    title: str = Field(index=True, max_length=256)
    original_title: str = Field(default="", max_length=256)
    language: str = Field(default="", max_length=32)
    translated_language: str = Field(default="", max_length=32)
    description: str = Field(default="")
    tags: list = Field(default_factory=list, sa_column=Column(_jsonb))
    download_url: str = Field(default="", max_length=1024)
    file_asset_url: str = Field(default="", max_length=1024)
    outline: dict = Field(default_factory=dict, sa_column=Column(_jsonb))
    ingestion_status: str = Field(default="not_started", index=True, max_length=32)
    outline_review_status: str = Field(default="unreviewed", index=True, max_length=16)
    student_availability_status: str = Field(default="draft", index=True, max_length=16)
    ingestion_error_message: str = Field(default="")
    published_at: datetime | None = Field(default=None)
    unpublished_at: datetime | None = Field(default=None)
    archived_at: datetime | None = Field(default=None)
    embedding: list[float] | None = Field(default=None, sa_column=Column(ARRAY(Float)))


class TextbookSectionContent(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint(
            "textbook_id",
            "section_id",
            name="uq_textbooksectioncontent_textbook_section",
        ),
    )

    section_content_id: str = Field(primary_key=True, max_length=64)
    textbook_id: str = Field(index=True, max_length=64)
    section_id: str = Field(index=True, max_length=128)
    parent_section_id: str | None = Field(default=None, index=True, max_length=128)
    order_index: int = Field(default=0, index=True)
    title: str = Field(max_length=256)
    original_title: str = Field(default="", max_length=256)
    content_zh: str = Field(default="")
    content_char_count: int = Field(default=0)


class TextbookExtensionResource(SQLModel, table=True):
    __table_args__ = (
        CheckConstraint(
            _check_in_values(
                "render_mode", TEXTBOOK_EXTENSION_RESOURCE_RENDER_MODE_VALUES
            ),
            name="ck_textbookextensionresource_render_mode",
        ),
    )

    resource_id: str = Field(primary_key=True, max_length=64)
    textbook_id: str = Field(index=True, max_length=64)
    section_id: str = Field(index=True, max_length=128)
    resource_type: str = Field(default="", index=True, max_length=64)
    title_zh: str = Field(max_length=256)
    description_zh: str = Field(default="")
    render_mode: str = Field(default="reader", index=True, max_length=16)
    url: str = Field(default="", max_length=1024)
    cover_url: str = Field(default="", max_length=1024)
    source_name: str = Field(default="", max_length=256)
    status: str = Field(default="", index=True, max_length=32)


class KnowledgeGap(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint(
            "normalized_topic",
            name="uq_knowledgegap_normalized_topic",
        ),
        CheckConstraint(
            _check_in_values("status", KNOWLEDGE_GAP_STATUS_VALUES),
            name="ck_knowledgegap_status",
        ),
    )

    gap_id: str = Field(primary_key=True, max_length=64)
    normalized_topic: str = Field(index=True, max_length=256)
    trigger_count: int = Field(default=0)
    follow_count: int = Field(default=0)
    latest_triggered_at: datetime | None = Field(default=None)
    student_goal_summaries: list = Field(default_factory=list, sa_column=Column(_jsonb))
    status: str = Field(default="open", index=True, max_length=32)
    resolved_textbook_id: str | None = Field(default=None, index=True, max_length=64)
    resolved_at: datetime | None = Field(default=None)


class KnowledgeGapFollow(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("gap_id", "user_uid", name="uq_knowledgegapfollow_gap_user"),
    )

    follow_id: str = Field(primary_key=True, max_length=64)
    gap_id: str = Field(index=True, max_length=64)
    user_uid: str = Field(index=True, max_length=64)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class KnowledgeGapNotice(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint(
            "gap_id",
            "user_uid",
            "notice_type",
            name="uq_knowledgegapnotice_gap_user_type",
        ),
        CheckConstraint(
            _check_in_values("notice_type", KNOWLEDGE_GAP_NOTICE_TYPE_VALUES),
            name="ck_knowledgegapnotice_notice_type",
        ),
        CheckConstraint(
            KNOWLEDGE_GAP_NOTICE_ACTION_PAYLOAD_CHECK_SQL,
            name="ck_knowledgegapnotice_action_payload",
        ),
    )

    notice_id: str = Field(primary_key=True, max_length=64)
    gap_id: str = Field(index=True, max_length=64)
    user_uid: str = Field(index=True, max_length=64)
    notice_type: str = Field(
        default="knowledge_gap_resolved", index=True, max_length=64
    )
    title: str = Field(max_length=256)
    body: str = Field(default="")
    action_label: str = Field(default="", max_length=64)
    action_payload: dict = Field(default_factory=dict, sa_column=Column(_jsonb))
    read_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class KnowledgeBaseIngestionJob(SQLModel, table=True):
    __table_args__ = (
        CheckConstraint(
            _check_in_values("status", KNOWLEDGE_BASE_INGESTION_JOB_STATUS_VALUES),
            name="ck_knowledgebaseingestionjob_status",
        ),
    )

    job_id: str = Field(primary_key=True, max_length=64)
    textbook_id: str = Field(index=True, max_length=64)
    job_type: str = Field(default="", index=True, max_length=64)
    status: str = Field(default="queued", index=True, max_length=16)
    error_message: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = Field(default=None)
    finished_at: datetime | None = Field(default=None)
