from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


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


class ChatflowStartRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)


class ChatflowContinueRequest(BaseModel):
    execution_id: str = Field(min_length=1, max_length=80)
    query: str = Field(min_length=1, max_length=4000)


class ChatflowResponse(BaseModel):
    execution_id: str
    conversation_id: str
    answer: dict
    completed: bool
    final_result: dict | None = None


class ChatflowContinueResponse(BaseModel):
    answer: dict
    completed: bool
    conversation_id: str
    final_result: dict | None = None


class SessionStartRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)


class SessionContinueRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=80)
    query: str = Field(min_length=1, max_length=4000)


class AgentQuestionBox(BaseModel):
    question: str
    options: list[str]


class AgentUserAnswer(BaseModel):
    user_message: str
    question_box: AgentQuestionBox | None = None


class AgentTraceStep(BaseModel):
    step_id: str
    agent_key: str
    label: str
    phase: str
    status: str
    message: str
    depends_on: list[str] = Field(default_factory=list)
    parallel_group: str | None = None


class SessionResponse(BaseModel):
    session_id: str
    answer: AgentUserAnswer
    agent_trace: list[AgentTraceStep] = Field(default_factory=list)
    completed: bool
    profile: dict | None = None
    learning_path: dict | None = None


class LearningPathReadResponse(BaseModel):
    learning_path: dict
    updated_at: datetime
