from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from pathlib import Path

import uvicorn

from app.database import build_engine, ensure_demo_user
from app.desktop import create_desktop_app
from app.migration_cli import main as migrate_database
from app.workers.knowledge_base_worker import run_worker as run_knowledge_worker


def configure_frozen_runtime() -> None:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        os.chdir(Path(bundle_root))


def run_server() -> None:
    frontend_dist = os.environ.get("ONETREE_FRONTEND_DIST", "").strip()
    if not frontend_dist:
        raise RuntimeError("ONETREE_FRONTEND_DIST is required")
    app = create_desktop_app(frontend_dist=Path(frontend_dist))
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")


def run_worker() -> None:
    run_knowledge_worker(poll_seconds=2.0)


def run_migration() -> int:
    migration_result = migrate_database()
    if migration_result != 0:
        return migration_result

    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")
    engine = build_engine(database_url)
    try:
        ensure_demo_user(engine)
    finally:
        engine.dispose()
    return 0


def main(arguments: Sequence[str] | None = None) -> int:
    configure_frozen_runtime()
    resolved_arguments = list(sys.argv[1:] if arguments is None else arguments)
    mode = resolved_arguments[0] if resolved_arguments else ""
    if mode == "serve":
        run_server()
        return 0
    if mode == "worker":
        run_worker()
        return 0
    if mode == "migrate":
        return run_migration()
    raise ValueError(f"未知的桌面运行模式: {mode}")


if __name__ == "__main__":
    raise SystemExit(main())
