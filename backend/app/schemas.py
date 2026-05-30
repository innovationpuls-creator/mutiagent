from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


OAuthProvider = Literal["qq", "xuexitong"]
AuthType = Literal["password", "oauth"]


class LoginRequest(BaseModel):
    account: str = Field(min_length=3, max_length=128)
    password: str = Field(min_length=6, max_length=128)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    identifier: str = Field(min_length=3, max_length=128)
    password: str = Field(min_length=6, max_length=128)
    confirm_password: str = Field(min_length=6, max_length=128)

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
