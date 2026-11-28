"""Offline HTTP knowledge-base benchmarks on a disposable loopback database."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.update(
    LLM_API_KEY="offline",
    LLM_BASE_URL="http://127.0.0.1:1/v1",
    LLM_MODEL="offline",
    LANGSMITH_TRACING="false",
    LANGCHAIN_TRACING_V2="false",
)

import httpx  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from profile_backend import measure, schema_engine  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlmodel import Session, SQLModel  # noqa: E402

from app.api import knowledge_base as api  # noqa: E402
from app.api.health import create_health_router  # noqa: E402
from app.core.observability import RequestIdMiddleware  # noqa: E402
from app.core.security import configure_jwt, create_access_token  # noqa: E402
from app.database import create_session_dependency  # noqa: E402
from app.models import User  # noqa: E402
from tests.fixtures.knowledge_base import enabled_source  # noqa: E402


def application(engine):
    SQLModel.metadata.create_all(engine)
    configure_jwt("offline-knowledge-base-benchmark")
    with Session(engine) as session:
        session.add(
            User(uid="admin", username="Admin", identifier="admin", role="admin")
        )
        session.add(enabled_source())
        session.commit()
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    app.include_router(
        api.create_knowledge_base_router(create_session_dependency(engine))
    )
    app.include_router(create_health_router(engine))
    headers = {"Authorization": f"Bearer {create_access_token({'sub': 'admin'})}"}
    return app, headers


async def upload(app, headers, payload):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://benchmark"
    ) as client:
        response = await client.post(
            "/api/admin/knowledge-base/uploads",
            headers=headers,
            data={"title": "Offline upload", "language": "zh"},
            files={"file": ("synthetic.pdf", payload, "application/pdf")},
        )
        assert response.status_code == 201, response.text
        assert response.json()["job"]["status"] == "queued"


async def upload_barrier(app, headers, engine, directory):
    import builtins

    ready, release = threading.Event(), threading.Event()
    original_open = builtins.open
    heartbeat = 0
    samples = {}

    class Writer:
        def __init__(self, path, mode):
            self.file = original_open(path, mode)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.file.close()

        def write(self, data):
            samples["write_thread"] = threading.get_ident()
            samples["write_connections"] = engine.pool.checkedout()
            ready.set()
            if not release.wait(5):
                raise TimeoutError("write barrier expired")
            return self.file.write(data)

    def open_file(path, mode="r", *args, **kwargs):
        if mode == "wb" and Path(path).parent == directory:
            return Writer(path, mode)
        return original_open(path, mode, *args, **kwargs)

    async def pulse():
        nonlocal heartbeat
        while True:
            heartbeat += 1
            await asyncio.sleep(0.01)

    # Releases even when the old async route blocks its event loop.
    timer = threading.Timer(1, release.set)
    timer.start()
    ticker = asyncio.create_task(pulse())
    started = time.perf_counter()
    loop_thread = threading.get_ident()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://benchmark"
    ) as client:
        with patch("app.services.knowledge_base_service.open", open_file, create=True):
            task = asyncio.create_task(upload(app, headers, b"x" * 1024 * 1024))
            try:
                assert await asyncio.to_thread(ready.wait, 5)
                health = await client.get("/api/health/ready")
                await asyncio.sleep(0.03)
                samples.update(
                    health_status=health.status_code,
                    health_elapsed_ms=(time.perf_counter() - started) * 1000,
                    health_before_release=not release.is_set(),
                    heartbeat_count=heartbeat,
                    write_in_event_loop=samples["write_thread"] == loop_thread,
                )
            finally:
                release.set()
                timer.cancel()
                await task
                ticker.cancel()
                await asyncio.gather(ticker, return_exceptions=True)
    samples.pop("write_thread")
    return samples


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--acceptance", action="store_true")
    args = parser.parse_args()
    url = make_url(args.database_url)
    if url.host not in {"localhost", "127.0.0.1", "::1"} or not (
        url.database or ""
    ).startswith("onetree_perf"):
        parser.error("use a disposable loopback onetree_perf database")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    results = {}
    with (
        schema_engine(args.database_url) as engine,
        tempfile.TemporaryDirectory() as temp,
    ):
        directory = Path(temp)
        app, headers = application(engine)
        with patch.dict(os.environ, {"KNOWLEDGE_BASE_UPLOAD_DIR": temp}):
            for size in (1, 10, 100):
                payload = b"x" * (size * 1024 * 1024)
                results[f"upload_{size}_mib"] = measure(
                    f"upload_{size}_mib",
                    lambda: asyncio.run(upload(app, headers, payload)),
                    engine,
                    args.output_dir,
                    5,
                )
            results["upload_barrier"] = asyncio.run(
                upload_barrier(app, headers, engine, directory)
            )
    data = {
        "method": "five warm samples; cProfile main thread + tracemalloc; offline HTTP",
        "synthetic_uploads": "bytes with PDF filename; no parsing or external network",
        "results": results,
    }
    (args.output_dir / "summary.json").write_text(json.dumps(data, indent=2))
    print(json.dumps({key: value.get("median_ms") for key, value in results.items()}))


if __name__ == "__main__":
    main()
