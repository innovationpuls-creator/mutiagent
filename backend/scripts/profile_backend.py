"""Offline profiles. Run from backend against an explicitly isolated PostgreSQL."""

from __future__ import annotations

import argparse
import asyncio
import cProfile
import hashlib
import json
import os
import platform
import pstats
import statistics
import sys
import time
import tracemalloc
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.update(
    LLM_API_KEY="offline-unused",
    LLM_BASE_URL="http://127.0.0.1:1/v1",
    LLM_MODEL="offline-unused",
)

from sqlalchemy import event, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlmodel import Session, SQLModel  # noqa: E402

from app.database import build_engine, init_db  # noqa: E402
from app.models import (  # noqa: E402
    ChapterProgress,
    ChapterQuiz,
    ChapterQuizAttempt,
    KnowledgeBaseIngestionJob,
    Textbook,
    User,
)


@contextmanager
def schema_engine(database_url):
    base = build_engine(database_url)
    name = "profile_" + uuid4().hex
    with base.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{name}"'))
    url = make_url(database_url)
    query = dict(url.query, options=f"-c search_path={name}")
    engine = build_engine(url.set(query=query).render_as_string(hide_password=False))
    try:
        yield engine
    finally:
        engine.dispose()
        with base.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{name}" CASCADE'))
        base.dispose()


def measure(name, operation, engine, output, repeats, prepare=None):  # noqa: C901
    timings, peaks, counts, sql_ms = [], [], [], []
    statements = Counter()
    maximum = 0
    waiting = []
    held, holds, latencies = {}, [], []

    def checkout(_dbapi, record, _proxy):
        nonlocal maximum
        maximum = max(maximum, engine.pool.checkedout())
        held[id(record)] = time.perf_counter()

    def checkin(_dbapi, record):
        started = held.pop(id(record), None)
        if started is not None:
            holds.append((time.perf_counter() - started) * 1000)

    def before(_conn, _cursor, statement, _parameters, context, _many):
        statements[statement.split()[0].upper()] += 1
        context._profile_started = time.perf_counter()

    def after(_conn, _cursor, _statement, _parameters, context, _many):
        sql_ms.append((time.perf_counter() - context._profile_started) * 1000)

    listeners = (
        ("checkout", checkout),
        ("checkin", checkin),
        ("before_cursor_execute", before),
        ("after_cursor_execute", after),
    )
    for key, listener in listeners:
        event.listen(engine, key, listener)
    profiler = cProfile.Profile()
    try:
        for _ in range(repeats):
            if prepare is not None:
                for key, listener in listeners:
                    event.remove(engine, key, listener)
                prepare()
                for key, listener in listeners:
                    event.listen(engine, key, listener)
            old_count = sum(statements.values())
            tracemalloc.start()
            started = time.perf_counter()
            profiler.enable()
            result = operation()
            profiler.disable()
            timings.append((time.perf_counter() - started) * 1000)
            peaks.append(tracemalloc.get_traced_memory()[1])
            tracemalloc.stop()
            counts.append(sum(statements.values()) - old_count)
            if isinstance(result, dict) and "model_wait_connections" in result:
                waiting.extend(result["model_wait_connections"])
                latencies.extend(result.get("request_latency_ms", []))
    finally:
        profiler.disable()
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        for key, listener in listeners:
            event.remove(engine, key, listener)
    profiler.dump_stats(str(output / f"{name}.prof"))
    with (output / f"{name}.txt").open("w") as stream:
        stats = pstats.Stats(profiler, stream=stream)
        stats.sort_stats("cumulative").print_stats(25)
        stats.sort_stats("tottime").print_stats(25)
    return {
        "runs": repeats,
        "median_ms": round(statistics.median(timings), 3),
        "samples_ms": [round(value, 3) for value in timings],
        "peak_python_bytes": max(peaks),
        "sql_count_per_run": counts,
        "sql_types": dict(statements),
        "sql_total_ms": round(sum(sql_ms), 3),
        "max_checked_out": maximum,
        "model_wait_connections": waiting,
        "connection_hold_total_ms": round(sum(holds), 3),
        "request_latency_ms": [round(value, 3) for value in latencies],
        "request_p95_ms": round(sorted(latencies)[int(len(latencies) * 0.95)], 3)
        if latencies
        else None,
    }


def populate(engine, size):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with Session(engine) as session:
        session.add(User(uid="profile-user", username="Profile", identifier="profile"))
        session.flush()
        attempts = []
        for index in range(size):
            session.add(
                Textbook(
                    textbook_id=f"book-{index:05}",
                    source_id="profile-source",
                    title=f"Python textbook {index}",
                    tags=["Python", "Programming"],
                    outline={"chapters": [{"title": "x" * 2000}]},
                    student_availability_status="published",
                )
            )
            session.add(
                ChapterQuiz(
                    quiz_id=f"quiz-{index}",
                    user_uid="profile-user",
                    course_node_id="course",
                    chapter_id=str(index),
                    questions=[{"question": "x" * 2000}],
                    created_at=now,
                )
            )
            attempts.append(
                ChapterQuizAttempt(
                    attempt_id=f"attempt-{index}",
                    quiz_id=f"quiz-{index}",
                    user_uid="profile-user",
                    score=index % 100,
                    answers={"q": "x" * 2000},
                    created_at=now + timedelta(seconds=index),
                )
            )
            session.add(
                ChapterProgress(
                    user_uid="profile-user",
                    course_node_id="course",
                    chapter_id=str(index),
                    state="passed",
                    best_score=index % 100,
                    passed_at=now,
                )
            )
        session.flush()
        session.add_all(attempts)
        session.commit()


def markdown_sample(count):
    lines, chapters = [], []
    for chapter_index in range(8):
        sections = []
        lines.append(f"# Chapter {chapter_index + 1}\n")
        for index in range(count // 8):
            title = f"{chapter_index + 1}.{index + 1} Sample section"
            sections.append(
                {"section_id": f"s-{chapter_index}-{index}", "title": title}
            )
            lines.append(
                f"## {title}\n" + "Textbook paragraph explaining concepts.\n" * 4
            )
        chapters.append({"sections": sections})
    return "".join(lines), {"chapters": chapters}


async def report_concurrency(engine, count):
    from app.services.growth_report_service import stream_growth_report

    connections, latencies = [], []

    class Model:
        def with_structured_output(self, schema):
            self.schema = schema
            return self

        async def ainvoke(self, _messages):
            schema = self.schema
            connections.append(engine.pool.checkedout())
            await asyncio.sleep(0.05)
            if schema.__name__ == "EvidenceSelection":
                return {"requests": []}
            return {
                "overview": "Profile report",
                "strengths": [],
                "improvements": [],
                "actions": [],
            }

    async def run():
        started = time.perf_counter()
        with Session(engine) as session:
            async for _ in stream_growth_report(session, "profile-user", Model()):
                pass
        latencies.append((time.perf_counter() - started) * 1000)

    await asyncio.gather(*(run() for _ in range(count)))
    return {"model_wait_connections": connections, "request_latency_ms": latencies}


def main():  # noqa: C901
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--size", type=int, default=1000)
    parser.add_argument(
        "--cases", default="init,search,parser,statistics,auth,worker,sse"
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    os.environ["DATABASE_URL"] = args.database_url
    results = {
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "size": args.size,
            "offline_models": True,
        },
        "cases": {},
    }
    with schema_engine(args.database_url) as engine:
        cases = results["cases"]

        def record(name, operation, repeats=None, prepare=None):
            cases[name] = measure(
                name,
                operation,
                engine,
                args.output_dir,
                repeats or args.repeats,
                prepare,
            )
            print(name, json.dumps(cases[name]), flush=True)

        selected = set(args.cases.split(","))
        if "init" in selected:
            record(
                "empty_init",
                lambda: init_db(engine, seed_users=False),
                prepare=lambda: SQLModel.metadata.drop_all(engine),
            )
            record("current_init", lambda: init_db(engine, seed_users=False))

            def prepare_legacy():
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "ALTER TABLE userprofile ALTER COLUMN profile_data "
                            "TYPE JSON USING profile_data::json"
                        )
                    )

            record(
                "legacy_json_init",
                lambda: init_db(engine, seed_users=False),
                prepare=prepare_legacy,
            )
        else:
            SQLModel.metadata.create_all(engine)
        populate(engine, args.size)
        if "search" in selected:
            from app.services import knowledge_base_service as kb

            class Embeddings:
                def embed_query(self, _query):
                    return [0.0, 1.0]

            def search():
                with Session(engine) as session:
                    with patch.object(
                        kb, "get_embeddings_client", return_value=Embeddings()
                    ):
                        try:
                            return len(
                                kb.hybrid_search_textbooks(session, "Python", 15)
                            )
                        except Exception as error:
                            return {"error": type(error).__name__}

            record("search", search)
            cases["search"]["result"] = search()

            def matching():
                with Session(engine) as session:
                    with patch.object(
                        kb,
                        "get_embeddings_client",
                        side_effect=RuntimeError("offline unsupported"),
                    ):
                        return [
                            row.textbook_id
                            for row in kb.hybrid_search_textbooks(session, "Python", 15)
                        ]

            record("search_matching", matching)
            cases["search_matching"]["result"] = matching()
        if "parser" in selected:
            from app.services.document_parser_service import (
                convert_textbook_source_to_markdown,
                extract_outline_from_markdown,
                locate_and_slice_sections,
            )

            for count in (400, 1600, 6400):
                markdown, outline = markdown_sample(count)
                source = args.output_dir / f"synthetic_{count}.txt"
                source.write_text(markdown)
                try:
                    record(
                        f"convert_{count}",
                        lambda: convert_textbook_source_to_markdown(str(source)),
                    )
                finally:
                    source.unlink()
                record(
                    f"outline_{count}", lambda: extract_outline_from_markdown(markdown)
                )
                record(
                    f"slice_{count}",
                    lambda: locate_and_slice_sections(markdown, outline),
                )
                sections = locate_and_slice_sections(markdown, outline)
                cases[f"slice_{count}"]["output_sha256"] = hashlib.sha256(
                    json.dumps(sections, ensure_ascii=False, sort_keys=True).encode()
                ).hexdigest()
                plain = []
                for _ in range(args.repeats):
                    started = time.perf_counter()
                    locate_and_slice_sections(markdown, outline)
                    plain.append((time.perf_counter() - started) * 1000)
                cases[f"slice_{count}"]["uninstrumented_median_ms"] = round(
                    statistics.median(plain), 3
                )
        if "statistics" in selected:
            from app.services.forest_service import first_generatable_chapter_id
            from app.services.growth_report_context import build_report_context
            from app.services.learning_path_service import get_canopy_overview

            def read(operation):
                with Session(engine) as session:
                    return operation(session)

            record(
                "canopy",
                lambda: read(
                    lambda session: get_canopy_overview(session, "profile-user")
                ),
            )
            record(
                "report_context",
                lambda: read(
                    lambda session: build_report_context(session, "profile-user")
                ),
            )
            outline = {
                "sections": [
                    {"section_id": str(i), "order_index": i} for i in range(args.size)
                ]
            }
            record(
                "chapter_progress",
                lambda: read(
                    lambda session: first_generatable_chapter_id(
                        session, "profile-user", "course", outline
                    )
                ),
            )
        if "auth" in selected:
            from app.core.security import configure_jwt
            from app.schemas import LoginRequest, RegisterRequest
            from app.services.auth_service import login_user, register_user

            configure_jwt("offline-profile-secret")
            identifier = ""

            def register():
                nonlocal identifier
                identifier = uuid4().hex + "@profile.test"
                with Session(engine) as session:
                    return register_user(
                        session,
                        RegisterRequest(
                            username="Profile",
                            identifier=identifier,
                            password="profile-password",
                            confirm_password="profile-password",
                            school="school",
                            major="major",
                            class_name="class",
                        ),
                    )

            record("register", register)

            def login():
                with Session(engine) as session:
                    return login_user(
                        session,
                        LoginRequest(account=identifier, password="profile-password"),
                    )

            record("login", login)
        if "worker" in selected:
            from app.workers.knowledge_base_worker import claim_next_ingestion_job

            with Session(engine) as session:
                for index in range(args.repeats):
                    session.add(
                        KnowledgeBaseIngestionJob(
                            job_id=f"job-{index}", textbook_id=f"book-{index:05}"
                        )
                    )
                session.commit()

            def claim():
                with Session(engine) as session:
                    return claim_next_ingestion_job(
                        session, "profile-worker", datetime.now(timezone.utc)
                    )

            record("worker_claim", claim)
        if "sse" in selected:
            record(
                "report_concurrency_10",
                lambda: asyncio.run(report_concurrency(engine, 10)),
                1,
            )
    (args.output_dir / "summary.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False)
    )


if __name__ == "__main__":
    main()
