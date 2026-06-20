from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON as SAJSON

# Use JSONB for PostgreSQL, fall back to JSON for SQLite/test environments
from sqlalchemy.types import TypeDecorator
from sqlmodel import Field, SQLModel


class _JSONBOrJSON(TypeDecorator):
    """Use JSONB on PostgreSQL, plain JSON on SQLite."""

    impl = SAJSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB(none_as_null=False))
        return dialect.type_descriptor(SAJSON())


_jsonb = _JSONBOrJSON


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
