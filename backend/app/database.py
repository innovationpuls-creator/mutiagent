from __future__ import annotations

from collections.abc import Callable, Generator
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.security import hash_password
from app.models import User


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_URL = f"sqlite:///{BACKEND_ROOT / 'mutiagent.db'}"


def build_engine(database_url: str = DEFAULT_DATABASE_URL) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)


def create_session_dependency(engine: Engine) -> Callable[[], Generator[Session]]:
    def get_session() -> Generator[Session]:
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
                username="体验同学",
                identifier="demo@mutiagent.local",
                provider="password",
                password_hash=hash_password("demo123456"),
            ),
        )
        session.commit()
