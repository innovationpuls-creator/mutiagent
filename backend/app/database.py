from __future__ import annotations

import os
from collections.abc import Callable, Generator

from dotenv import load_dotenv
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.security import hash_password
from app.models import User
from app.schema_upgrades import migrate_removed_learning_path_table, run_schema_upgrades

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://mutiagent:mutiagent@localhost:5432/mutiagent"
)


_engine: Engine | None = None


def build_engine(database_url: str = DATABASE_URL) -> Engine:
    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_recycle=3600,
        pool_size=10,
        max_overflow=20,
    )


def get_engine(database_url: str = DATABASE_URL) -> Engine:
    """Return a module-level cached engine singleton."""
    global _engine
    if _engine is None:
        _engine = build_engine(database_url)
    return _engine


def set_engine(engine: Engine) -> None:
    """Set the module-level engine (called by create_app)."""
    global _engine
    _engine = engine


def create_session_dependency(
    engine: Engine,
) -> Callable[[], Generator[Session, None, None]]:
    def get_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    return get_session


def init_db(engine: Engine) -> None:
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)
    migrate_removed_learning_path_table(engine)

    with Session(engine) as session:
        _ensure_admin_user(session)
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
                role="student",
                provider="password",
                password_hash=hash_password("demo123456"),
            ),
        )
        session.commit()


def _ensure_admin_user(session: Session) -> None:
    admin_username = os.getenv("ADMIN_USERNAME")
    admin_identifier = os.getenv("ADMIN_IDENTIFIER")
    admin_password = os.getenv("ADMIN_PASSWORD")
    if not admin_username or not admin_identifier or not admin_password:
        return

    existing = session.exec(
        select(User).where(User.identifier == admin_identifier),
    ).first()
    if existing:
        existing.username = admin_username
        existing.role = "admin"
        existing.provider = "password"
        existing.password_hash = hash_password(admin_password)
        session.add(existing)
        session.commit()
        return

    session.add(
        User(
            uid="00000000-0000-0000-0000-0000000000ad",
            username=admin_username,
            identifier=admin_identifier,
            role="admin",
            provider="password",
            password_hash=hash_password(admin_password),
        ),
    )
    session.commit()
