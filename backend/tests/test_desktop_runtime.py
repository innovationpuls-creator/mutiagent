from pathlib import Path

from sqlmodel import Session, select

from app import desktop_runtime
from app.core.security import verify_password
from app.database import build_engine, ensure_demo_user
from app.migration_state import migrate_to_head
from app.models import User
from tests.postgres import postgresql_test_url


def test_runtime_uses_pyinstaller_resource_directory(
    monkeypatch, tmp_path: Path
) -> None:
    changes: list[Path] = []
    monkeypatch.setattr(desktop_runtime.sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setattr(desktop_runtime.os, "chdir", changes.append)

    desktop_runtime.configure_frozen_runtime()

    assert changes == [tmp_path]


def test_runtime_dispatches_serve_mode(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(desktop_runtime, "run_server", lambda: calls.append("serve"))

    assert desktop_runtime.main(["serve"]) == 0
    assert calls == ["serve"]


def test_runtime_dispatches_worker_mode(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(desktop_runtime, "run_worker", lambda: calls.append("worker"))

    assert desktop_runtime.main(["worker"]) == 0
    assert calls == ["worker"]


def test_runtime_dispatches_migrate_mode(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        desktop_runtime,
        "run_migration",
        lambda: calls.append("migrate") or 0,
    )

    assert desktop_runtime.main(["migrate"]) == 0
    assert calls == ["migrate"]


def test_runtime_rejects_unknown_mode() -> None:
    try:
        desktop_runtime.main(["unknown"])
    except ValueError as error:
        assert str(error) == "未知的桌面运行模式: unknown"
    else:
        raise AssertionError("unknown desktop runtime mode was accepted")


def test_ensure_demo_user_is_idempotent(tmp_path: Path) -> None:
    database_url = postgresql_test_url(tmp_path, "desktop-demo-user")
    engine = build_engine(database_url)
    migrate_to_head(engine)

    ensure_demo_user(engine)
    ensure_demo_user(engine)

    with Session(engine) as session:
        users = session.exec(
            select(User).where(User.identifier == "demo@mutiagent.local")
        ).all()

    assert len(users) == 1
    assert users[0].uid == "00000000-0000-0000-0000-000000000001"
    assert users[0].role == "student"
    assert verify_password("demo123456", users[0].password_hash)


def test_desktop_migration_seeds_demo_user_after_migration(monkeypatch) -> None:
    calls: list[str] = []

    class FakeEngine:
        def dispose(self) -> None:
            calls.append("dispose")

    monkeypatch.setenv("DATABASE_URL", "desktop-database-url")
    monkeypatch.setattr(
        desktop_runtime,
        "migrate_database",
        lambda: calls.append("migrate") or 0,
    )
    monkeypatch.setattr(
        desktop_runtime,
        "build_engine",
        lambda database_url: calls.append(f"build:{database_url}") or FakeEngine(),
    )
    monkeypatch.setattr(
        desktop_runtime,
        "ensure_demo_user",
        lambda engine: calls.append("seed"),
    )

    assert desktop_runtime.run_migration() == 0
    assert calls == ["migrate", "build:desktop-database-url", "seed", "dispose"]
