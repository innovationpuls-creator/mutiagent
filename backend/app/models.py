from __future__ import annotations

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True, min_length=1, max_length=64)
    identifier: str = Field(index=True, min_length=3, max_length=128)
    provider: str = Field(default="password", index=True, max_length=32)
    password_hash: str | None = Field(default=None, max_length=128)
