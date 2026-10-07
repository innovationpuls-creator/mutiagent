"""Run the complete backend test suite under cProfile and export pstats data.

The suite's session fixture removes orphaned ``test_*`` schemas, so this runner
only accepts a loopback PostgreSQL database named ``onetree_perf*``. Use a
disposable PostgreSQL instance and a fresh database for each run.
"""

from __future__ import annotations

import argparse
import cProfile
import json
import os
import pstats
import time
from collections import Counter
from pathlib import Path
from threading import Lock
from unittest.mock import patch

from sqlalchemy.engine import make_url


def _backend_row(filename: str, backend_root: Path) -> bool:
    try:
        relative = Path(filename).resolve().relative_to(backend_root)
    except (OSError, ValueError):
        return False
    return bool(relative.parts) and relative.parts[0] in {"app", "migrations"}


def _json_rows(stats: pstats.Stats, backend_root: Path) -> list[dict[str, object]]:
    rows = []
    for (filename, line, function), values in stats.stats.items():
        if not _backend_row(filename, backend_root):
            continue
        primitive_calls, total_calls, self_seconds, cumulative_seconds, _ = values
        rows.append(
            {
                "file": Path(filename).resolve().relative_to(backend_root).as_posix(),
                "line": line,
                "function": function,
                "primitive_calls": primitive_calls,
                "calls": total_calls,
                "self_seconds": round(self_seconds, 6),
                "cumulative_seconds": round(cumulative_seconds, 6),
            }
        )
    return rows


def _write_pstats(stats: pstats.Stats, output: Path, top: int) -> None:
    with output.open("w", encoding="utf-8") as stream:
        report = stats
        report.stream = stream
        stream.write("=== Entire profiled pytest process: cumulative time ===\n")
        report.sort_stats(pstats.SortKey.CUMULATIVE).print_stats(top)
        stream.write("\n=== Entire profiled pytest process: self time ===\n")
        report.sort_stats(pstats.SortKey.TIME).print_stats(top)
        backend_pattern = r"/backend/(app|migrations)/"
        stream.write("\n=== Backend app/migrations: cumulative time ===\n")
        report.sort_stats(pstats.SortKey.CUMULATIVE).print_stats(backend_pattern)
        stream.write("\n=== Backend app/migrations: self time ===\n")
        report.sort_stats(pstats.SortKey.TIME).print_stats(backend_pattern)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--top", type=int, default=100)
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    url = make_url(args.database_url)
    if url.host not in {"localhost", "127.0.0.1", "::1"}:
        parser.error("--database-url must point to loopback PostgreSQL")
    if not (url.database or "").startswith("onetree_perf"):
        parser.error("database name must start with 'onetree_perf'")
    if args.top < 1:
        parser.error("--top must be positive")

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    expected_outputs = (
        "backend-test-suite.prof",
        "pstats-report.txt",
        "pstats-backend.json",
        "profile-summary.json",
    )
    existing = [name for name in expected_outputs if (output / name).exists()]
    if existing:
        parser.error(f"output files already exist: {', '.join(existing)}")

    os.environ.update(
        DATABASE_URL=args.database_url,
        LLM_API_KEY="offline-profile",
        LLM_BASE_URL="http://127.0.0.1:1/v1",
        LLM_MODEL="offline-profile",
        LANGSMITH_TRACING="false",
        LANGCHAIN_TRACING_V2="false",
    )

    pytest_args = args.pytest_args
    if pytest_args[:1] == ["--"]:
        pytest_args = pytest_args[1:]
    if not pytest_args:
        pytest_args = ["-q", "--tb=short"]

    import bcrypt
    import pytest

    bcrypt_calls: Counter[str] = Counter()
    bcrypt_lock = Lock()

    def counted(name, original):
        def call(*args, **kwargs):
            with bcrypt_lock:
                bcrypt_calls[name] += 1
            return original(*args, **kwargs)

        return call

    profiler = cProfile.Profile()
    started = time.perf_counter()
    profiler.enable()
    with (
        patch.object(bcrypt, "hashpw", counted("hashpw", bcrypt.hashpw)),
        patch.object(bcrypt, "checkpw", counted("checkpw", bcrypt.checkpw)),
    ):
        exit_code = int(pytest.main(pytest_args))
    profiler.disable()
    elapsed_seconds = time.perf_counter() - started

    profile_path = output / "backend-test-suite.prof"
    profiler.dump_stats(str(profile_path))
    stats = pstats.Stats(profiler)
    backend_root = Path(__file__).resolve().parents[1]
    rows = _json_rows(stats, backend_root)
    cumulative = sorted(rows, key=lambda row: row["cumulative_seconds"], reverse=True)
    self_time = sorted(rows, key=lambda row: row["self_seconds"], reverse=True)
    (output / "pstats-backend.json").write_text(
        json.dumps(
            {
                "scope": (
                    "backend/app and backend/migrations functions observed by cProfile"
                ),
                "profiled_backend_files": sorted({row["file"] for row in rows}),
                "function_rows": len(rows),
                "top_cumulative": cumulative[: args.top],
                "top_self_time": self_time[: args.top],
                "all_functions": rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _write_pstats(stats, output / "pstats-report.txt", args.top)
    summary = {
        "pytest_args": pytest_args,
        "pytest_exit_code": exit_code,
        "pytest_wall_seconds": round(elapsed_seconds, 3),
        "profile_total_calls": stats.total_calls,
        "profile_primitive_calls": stats.prim_calls,
        "profile_total_seconds": round(stats.total_tt, 3),
        "backend_function_rows": len(rows),
        "backend_source_files_observed": len({row["file"] for row in rows}),
        "profile_file": profile_path.name,
        "bcrypt_calls_all_threads": dict(bcrypt_calls),
    }
    (output / "profile-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
