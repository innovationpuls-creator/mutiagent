from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


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
    profile_data: dict = Field(default_factory=dict, sa_column=Column(JSON))
    profile_text: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UserDifyConversation(SQLModel, table=True):
    user_uid: str = Field(foreign_key="user.uid", primary_key=True)
    intent_conversation_id: str = Field(default="")
    profile_conversation_id: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
