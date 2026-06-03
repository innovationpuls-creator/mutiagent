from __future__ import annotations

import os
from collections.abc import Callable, Generator

from dotenv import load_dotenv
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.security import hash_password
from app.models import User

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://mutiagent:mutiagent@localhost:5432/mutiagent")


def build_engine(database_url: str = DATABASE_URL) -> Engine:
    return create_engine(database_url, pool_pre_ping=True, pool_recycle=3600)


def create_session_dependency(engine: Engine) -> Callable[[], Generator[Session, None, None]]:
    def get_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    return get_session


def init_db(engine: Engine) -> None:
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        existing = session.exec(
            select(User).where(User.identifier == "demo@mutiagent.local"),
        ).first()
        if existing:
            return

        session.add(
            User(
                uid="00000000-0000-0000-0000-000000000001",
                username="体验同学",
                identifier="demo@mutiagent.local",
                provider="password",
                password_hash=hash_password("demo123456"),
            ),
        )
        session.commit()
