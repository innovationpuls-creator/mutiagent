from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

# Use JSONB for PostgreSQL, fall back to JSON for SQLite/test environments
from sqlalchemy.types import TypeDecorator, JSON as SAJSON


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
    provider: str = Field(default="password", index=True, max_length=32)
    password_hash: str | None = Field(default=None, max_length=128)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login_at: datetime | None = Field(default=None)


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


class ConversationSession(SQLModel, table=True):
    """持久化会话消息，替代 LangGraph MemorySaver。"""
    __table_args__ = (
        Index("idx_conversation_user_time", "user_uid", "updated_at"),
    )
    session_id: str = Field(primary_key=True)
    user_uid: str = Field(foreign_key="user.uid", index=True)
    messages: list = Field(default_factory=list, sa_column=Column(_jsonb))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
