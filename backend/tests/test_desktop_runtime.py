from pathlib import Path

from app import desktop_runtime


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
