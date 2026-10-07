"""Cold production startup in separate processes and isolated schema."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from profile_backend import schema_engine

from app.migration_state import migrate_to_head

CHILD = """
import cProfile, json, os, time, tracemalloc
from pathlib import Path
output = Path(os.environ["PROFILE_OUTPUT"])
instrumented = os.environ.get("PROFILE_PLAIN") != "1"
if instrumented: tracemalloc.start()
profiler = cProfile.Profile()
started = time.perf_counter()
if instrumented: profiler.enable()
from app.main import create_app
profiler.disable()
import_ms = (time.perf_counter() - started) * 1000
if instrumented: profiler.dump_stats(str(output / "cold_import.prof"))
profiler = cProfile.Profile()
started = time.perf_counter()
if instrumented: profiler.enable()
app = create_app()
profiler.disable()
factory_ms = (time.perf_counter() - started) * 1000
if instrumented: profiler.dump_stats(str(output / "production_factory.prof"))
print(json.dumps({"cold_import_ms": import_ms, "production_factory_ms": factory_ms,
                  "peak_python_bytes": (tracemalloc.get_traced_memory()[1]
                                        if instrumented else None)}))
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--plain", action="store_true", help="No profiling overhead")
    args = parser.parse_args()
    samples = []
    with schema_engine(args.database_url) as engine:
        migrate_to_head(engine)
        for index in range(args.repeats):
            output = args.output_dir / str(index)
            output.mkdir(parents=True, exist_ok=True)
            env = dict(
                os.environ,
                APP_ENV="production",
                DATABASE_URL=engine.url.render_as_string(hide_password=False),
                JWT_SECRET="offline-profile-secret",
                ALLOWED_ORIGINS="http://localhost:5173",
                PROFILE_OUTPUT=str(output),
                PROFILE_PLAIN="1" if args.plain else "0",
            )
            result = subprocess.run(
                [sys.executable, "-c", CHILD],
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            samples.append(json.loads(result.stdout.splitlines()[-1]))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "summary.json").write_text(json.dumps(samples, indent=2))
    print(json.dumps(samples))


if __name__ == "__main__":
    main()
