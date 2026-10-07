from __future__ import annotations

import os
from collections.abc import Callable, Generator
from contextvars import ContextVar
from typing import Any, TypeVar

from dotenv import load_dotenv
from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, select
from starlette.concurrency import run_in_threadpool

from app.core.security import hash_password
from app.models import User
from app.schema_upgrades import migrate_removed_learning_path_table, run_schema_upgrades

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://mutiagent:mutiagent@localhost:5432/mutiagent"
)

DEMO_USER_UID = "00000000-0000-0000-0000-000000000001"
DEMO_USER_IDENTIFIER = "demo@mutiagent.local"
DEMO_USER_PASSWORD = "demo123456"


_engine: Engine | None = None
request_engine_context: ContextVar[Engine | None] = ContextVar(
    "request_engine", default=None
)
SessionFactory = Callable[[], Session]
_Result = TypeVar("_Result")


def session_factory_from_session(session: Session) -> SessionFactory:
    """Capture the injected application's bind without sharing its Session."""
    bind = session.get_bind()
    return lambda: Session(bind)


def run_db_sync(
    factory: SessionFactory,
    operation: Callable[..., _Result],
    *args: Any,
    **kwargs: Any,
) -> _Result:
    with factory() as session:
        result = operation(session, *args, **kwargs)
        session.expunge_all()
        return result


async def run_db(
    factory: SessionFactory,
    operation: Callable[..., _Result],
    *args: Any,
    **kwargs: Any,
) -> _Result:
    """Run one complete database operation in a thread-owned short Session."""
    return await run_in_threadpool(run_db_sync, factory, operation, *args, **kwargs)


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
    request_engine = request_engine_context.get()
    if request_engine is not None:
        return request_engine
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


def init_db(engine: Engine, *, seed_users: bool = True) -> None:
    with engine.begin() as connection:
        empty = not inspect(connection).get_table_names()
        if empty:
            SQLModel.metadata.create_all(connection, checkfirst=False)
    if not empty:
        run_schema_upgrades(engine)
        SQLModel.metadata.create_all(engine)
        migrate_removed_learning_path_table(engine)

    if not seed_users:
        return

    with Session(engine) as session:
        _ensure_admin_user(session)
    ensure_demo_user(engine)


def ensure_demo_user(engine: Engine) -> None:
    with Session(engine) as session:
        existing = session.exec(
            select(User).where(User.identifier == DEMO_USER_IDENTIFIER),
        ).first()
        if existing:
            return

        session.add(
            User(
                uid=DEMO_USER_UID,
                username="体验同学",
                identifier=DEMO_USER_IDENTIFIER,
                role="student",
                provider="password",
                password_hash=hash_password(DEMO_USER_PASSWORD),
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
