from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


OAuthProvider = Literal["qq", "xuexitong"]
AuthType = Literal["password", "oauth"]

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
_PHONE_RE = re.compile(r"^1[3-9]\d[\s]?\d{4}[\s]?\d{4}$")
_IDENTIFIER_EXPLAIN = "请输入有效的邮箱或手机号（11 位中国大陆手机号）"


def _validate_identifier(value: str) -> str:
    trimmed = value.strip()
    if _EMAIL_RE.match(trimmed) or _PHONE_RE.match(trimmed):
        return trimmed
    raise ValueError(_IDENTIFIER_EXPLAIN)


# ── Auth ──

class LoginRequest(BaseModel):
    account: str = Field(min_length=3, max_length=128)
    password: str = Field(min_length=6, max_length=128)

    @field_validator("account")
    @classmethod
    def validate_account(cls, v: str) -> str:
        return _validate_identifier(v)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    identifier: str = Field(min_length=3, max_length=128)
    password: str = Field(min_length=6, max_length=128)
    confirm_password: str = Field(min_length=6, max_length=128)

    @field_validator("identifier")
    @classmethod
    def validate_identifier(cls, v: str) -> str:
        return _validate_identifier(v)

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, confirm_password: str, info: object) -> str:
        data = getattr(info, "data", {})
        if data.get("password") != confirm_password:
            raise ValueError("两次输入的密码不一致")
        return confirm_password


class OAuthRequest(BaseModel):
    provider: OAuthProvider
    authorization_code: str = Field(min_length=4, max_length=64)


class UserRead(BaseModel):
    uid: str
    username: str
    identifier: str
    provider: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    auth_type: AuthType
    user: UserRead


class HealthResponse(BaseModel):
    status: Literal["ok"]
    database: Literal["connected"]


# ── Chat ──

class ChatStartRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)


class ChatMessageRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    session_id: str
    reply_text: str | None = None
    profile: dict | None = None
    year_learning_paths: dict | None = None
    course_knowledge: dict | None = None


class SessionStateResponse(BaseModel):
    session_id: str
    user_uid: str
    messages: list[dict] = Field(default_factory=list)
    profile: dict | None = None
    year_learning_paths: dict | None = None
    latest_grade_year: str | None = None
    course_knowledge: dict | None = None
    updated_at: datetime


# ── Learning Path ──

class YearLearningPathsReadResponse(BaseModel):
    year_learning_paths: dict[str, dict]
    updated_at: datetime | None = None


BranchCourseStatus = Literal["completed", "current", "locked"]


class BranchCourseNodeRead(BaseModel):
    course_node_id: str
    course_or_chapter_theme: str
    course_goal: str
    status: BranchCourseStatus
    has_outline: bool


class BranchYearRead(BaseModel):
    grade_id: str
    grade_name: str
    has_courses: bool
    has_outline_content: bool
    is_clickable: bool
    current_course_id: str | None = None
    courses: list[BranchCourseNodeRead]


class BranchOverviewReadResponse(BaseModel):
    years: dict[str, BranchYearRead]
    updated_at: datetime | None = None


LeafAccessState = Literal["available", "locked"]


class LeafCourseRead(BaseModel):
    course_node_id: str
    grade_id: str
    course_or_chapter_theme: str
    course_goal: str
    status: BranchCourseStatus
    has_outline: bool


class LeafGenerationStatusRead(BaseModel):
    course_node_id: str
    chapter_section_id: str
    status: Literal["running"]
    message: str


class LeafCourseReadResponse(BaseModel):
    access_state: LeafAccessState
    course: LeafCourseRead
    outline: dict | None = None
    sections: list[dict] = Field(default_factory=list)
    section_composed_markdowns: dict[str, dict] = Field(default_factory=dict)
    generation_status: LeafGenerationStatusRead | None = None
    can_generate: bool
    first_generatable_chapter_id: str | None = None
    locked_reason: str | None = None


LeafAccessState = Literal["available", "locked"]


class LeafCourseRead(BaseModel):
    course_node_id: str
    grade_id: str
    course_or_chapter_theme: str
    course_goal: str
    status: BranchCourseStatus
    has_outline: bool


class LeafGenerationStatusRead(BaseModel):
    course_node_id: str
    chapter_section_id: str
    status: Literal["running"]
    message: str


class LeafCourseReadResponse(BaseModel):
    access_state: LeafAccessState
    course: LeafCourseRead
    outline: dict | None = None
    sections: list[dict] = Field(default_factory=list)
    section_composed_markdowns: dict[str, dict] = Field(default_factory=dict)
    generation_status: LeafGenerationStatusRead | None = None
    can_generate: bool
    first_generatable_chapter_id: str | None = None
    locked_reason: str | None = None
