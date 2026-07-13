#!/usr/bin/env bash
set -euo pipefail

SOURCE_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP_DIR="$(mktemp -d)"
REPO_ROOT="$TMP_DIR/repository"
git -C "$SOURCE_REPO_ROOT" diff --quiet HEAD -- \
  deploy/bin/backup deploy/bin/restore deploy/bin/import-bundle \
  deploy/lib/backup_manifest.py deploy/lib/migration_manifest.py \
  backend/migrations backend/app/migration_state.py
mkdir "$REPO_ROOT"
git -C "$SOURCE_REPO_ROOT" archive HEAD | tar -x -C "$REPO_ROOT"
git -C "$REPO_ROOT" init -q
git -C "$REPO_ROOT" config user.email test@example.com
git -C "$REPO_ROOT" config user.name "Backup Test"
git -C "$REPO_ROOT" add .
git -C "$REPO_ROOT" commit -qm initial
BACKEND_DIR="$REPO_ROOT/backend"
export UV_PROJECT_ENVIRONMENT="$SOURCE_REPO_ROOT/backend/.venv"
SOURCE_DB="onetree_backup_source_$$"
TARGET_DB="onetree_backup_target_$$"
SOURCE_ROLE="onetree_backup_source_role_$$"
MAINTENANCE_URL="${BACKUP_TEST_MAINTENANCE_URL:-postgresql:///postgres}"

cleanup() {
  SOURCE_DB="$SOURCE_DB" TARGET_DB="$TARGET_DB" SOURCE_ROLE="$SOURCE_ROLE" MAINTENANCE_URL="$MAINTENANCE_URL" \
    uv --directory "$BACKEND_DIR" run --no-env-file python - <<'PY'
import os
import psycopg2
from psycopg2 import sql

connection = psycopg2.connect(os.environ["MAINTENANCE_URL"])
connection.autocommit = True
try:
    with connection.cursor() as cursor:
        for key in ("SOURCE_DB", "TARGET_DB"):
            cursor.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(os.environ[key])
                )
            )
        cursor.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(os.environ["SOURCE_ROLE"])))
finally:
    connection.close()
PY
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

URLS_FILE="$TMP_DIR/urls"
SOURCE_DB="$SOURCE_DB" TARGET_DB="$TARGET_DB" SOURCE_ROLE="$SOURCE_ROLE" MAINTENANCE_URL="$MAINTENANCE_URL" \
  URLS_FILE="$URLS_FILE" uv --directory "$BACKEND_DIR" run --no-env-file python - <<'PY'
import os
from pathlib import Path
import psycopg2
from psycopg2 import sql
from sqlalchemy.engine import make_url

connection = psycopg2.connect(os.environ["MAINTENANCE_URL"])
connection.autocommit = True
try:
    with connection.cursor() as cursor:
        for key in ("SOURCE_DB", "TARGET_DB"):
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(os.environ[key])))
        cursor.execute(sql.SQL("CREATE ROLE {} NOCREATEDB").format(sql.Identifier(os.environ["SOURCE_ROLE"])))
        cursor.execute(sql.SQL("GRANT {} TO torch").format(sql.Identifier(os.environ["SOURCE_ROLE"])))
finally:
    connection.close()
base = make_url(os.environ["MAINTENANCE_URL"])
source = base.set(database=os.environ["SOURCE_DB"]).render_as_string(hide_password=False)
target = base.set(database=os.environ["TARGET_DB"]).render_as_string(hide_password=False)
Path(os.environ["URLS_FILE"]).write_text(f"{source}\n{target}\n", encoding="utf-8")
PY

SOURCE_URL="$(sed -n '1p' "$URLS_FILE")"
TARGET_URL="$(sed -n '2p' "$URLS_FILE")"

DATABASE_URL="$SOURCE_URL" uv --directory "$BACKEND_DIR" run --no-env-file python - <<'PY'
import os
from sqlalchemy import create_engine
from sqlmodel import Session
from app.migration_state import migrate_to_head
from app.models import User

engine = create_engine(os.environ["DATABASE_URL"])
migrate_to_head(engine)
with Session(engine) as session:
    session.add_all([
        User(uid="backup-admin", username="admin", identifier="13297540721", role="admin"),
        User(uid="backup-100", username="user-100", identifier="18771701100", role="student"),
        User(uid="backup-111", username="user-111", identifier="18771701111", role="admin"),
    ])
    session.commit()
PY

SOURCE_ROLE="$SOURCE_ROLE" DATABASE_URL="$SOURCE_URL" uv --directory "$BACKEND_DIR" run --no-env-file python - <<'PY'
import os
from sqlalchemy import create_engine
from psycopg2 import sql
engine = create_engine(os.environ["DATABASE_URL"])
with engine.begin() as connection:
    role = sql.Identifier(os.environ["SOURCE_ROLE"]).as_string(connection.connection.driver_connection)
    connection.exec_driver_sql(f"GRANT USAGE ON SCHEMA public TO {role}")
    connection.exec_driver_sql(f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {role}")
PY
SOURCE_BACKUP_URL="${SOURCE_URL}?options=-c%20role%3D${SOURCE_ROLE}"

UPLOADS_SOURCE="$TMP_DIR/source-uploads"
UPLOADS_TARGET="$TMP_DIR/target-uploads"
BACKUPS="$TMP_DIR/backups"
mkdir -p "$UPLOADS_SOURCE/chapter" "$UPLOADS_TARGET" "$BACKUPS"
printf '%s\n' 'original textbook' > "$UPLOADS_SOURCE/chapter/textbook.txt"
printf '%s\n' 'old target' > "$UPLOADS_TARGET/old.txt"

if DATABASE_URL="$SOURCE_BACKUP_URL" ONETREE_MAINTENANCE_MODE=1 \
  "$REPO_ROOT/deploy/bin/backup" "$BACKUPS" "$UPLOADS_SOURCE" \
  >/dev/null 2>&1; then
  printf '%s\n' 'backup without maintenance connection unexpectedly passed' >&2
  exit 1
fi

for index in 1 2 3 4; do
  printf '%s\n' "snapshot-$index" > "$UPLOADS_SOURCE/chapter/version.txt"
  DATABASE_URL="$SOURCE_BACKUP_URL" ONETREE_MAINTENANCE_MODE=1 TARGET_DATABASE_URL="$MAINTENANCE_URL" "$REPO_ROOT/deploy/bin/backup" \
    "$BACKUPS" "$UPLOADS_SOURCE" >/dev/null
done
test "$(find "$BACKUPS" -mindepth 1 -maxdepth 1 -type d ! -name '.*' | wc -l | tr -d ' ')" = "3"
SNAPSHOT="$(find "$BACKUPS" -mindepth 1 -maxdepth 1 -type d ! -name '.*' | sort | tail -1)"

VISIBLE_BEFORE="$(find "$BACKUPS" -mindepth 1 -maxdepth 1 -type d ! -name '.*' | sort)"
FAIL_BIN="$TMP_DIR/fail-bin"
mkdir "$FAIL_BIN"
printf '%s\n' '#!/usr/bin/env bash' 'exit 93' > "$FAIL_BIN/pg_dump"
chmod 700 "$FAIL_BIN/pg_dump"
if PATH="$FAIL_BIN:$PATH" DATABASE_URL="$SOURCE_BACKUP_URL" ONETREE_MAINTENANCE_MODE=1 TARGET_DATABASE_URL="$MAINTENANCE_URL" \
  "$REPO_ROOT/deploy/bin/backup" "$BACKUPS" "$UPLOADS_SOURCE" \
  >/dev/null 2>&1; then
  printf '%s\n' 'failing pg_dump unexpectedly published a snapshot' >&2
  exit 1
fi
test "$VISIBLE_BEFORE" = "$(find "$BACKUPS" -mindepth 1 -maxdepth 1 -type d ! -name '.*' | sort)"
test -z "$(find "$BACKUPS" -mindepth 1 -maxdepth 1 -type d -name '.snapshot.*' -print -quit)"

CORRUPT_BIN="$TMP_DIR/corrupt-bin"
REAL_PG_DUMP="$(command -v pg_dump)"
mkdir "$CORRUPT_BIN"
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'set -euo pipefail' \
  '"$REAL_PG_DUMP" "$@"' \
  'output=""' \
  'for argument in "$@"; do case "$argument" in --file=*) output="${argument#--file=}" ;; esac; done' \
  'printf "%s\n" corrupt > "$output"' > "$CORRUPT_BIN/pg_dump"
chmod 700 "$CORRUPT_BIN/pg_dump"
if PATH="$CORRUPT_BIN:$PATH" REAL_PG_DUMP="$REAL_PG_DUMP" \
  DATABASE_URL="$SOURCE_BACKUP_URL" ONETREE_MAINTENANCE_MODE=1 TARGET_DATABASE_URL="$MAINTENANCE_URL" \
  "$REPO_ROOT/deploy/bin/backup" "$BACKUPS" "$UPLOADS_SOURCE" >/dev/null 2>&1; then
  printf '%s\n' 'zero-exit corrupt dump unexpectedly published a snapshot' >&2
  exit 1
fi
test "$VISIBLE_BEFORE" = "$(find "$BACKUPS" -mindepth 1 -maxdepth 1 -type d ! -name '.*' | sort)"

DATABASE_URL="$TARGET_URL" uv --directory "$BACKEND_DIR" run --no-env-file python - <<'PY'
import os
from sqlalchemy import create_engine
with create_engine(os.environ["DATABASE_URL"]).begin() as connection:
    connection.exec_driver_sql("CREATE TABLE restore_sentinel (value text NOT NULL)")
    connection.exec_driver_sql("INSERT INTO restore_sentinel VALUES ('untouched')")
PY

TAMPERED="$TMP_DIR/tampered"
cp -R "$SNAPSHOT" "$TAMPERED"
printf '%s\n' 'tampered' >> "$TAMPERED/database.dump"
if TARGET_DATABASE_URL="$TARGET_URL" ONETREE_MAINTENANCE_MODE=1 \
  "$REPO_ROOT/deploy/bin/restore" "$TAMPERED" "$UPLOADS_TARGET" \
  >/dev/null 2>&1; then
  printf '%s\n' 'tampered snapshot unexpectedly restored' >&2
  exit 1
fi
test "$(<"$UPLOADS_TARGET/old.txt")" = "old target"
DATABASE_URL="$TARGET_URL" uv --directory "$BACKEND_DIR" run --no-env-file python - <<'PY'
import os
from sqlalchemy import create_engine, text
with create_engine(os.environ["DATABASE_URL"]).connect() as connection:
    assert connection.execute(text("SELECT value FROM restore_sentinel")).scalar_one() == "untouched"
PY

TARGET_DATABASE_URL="$TARGET_URL" ONETREE_MAINTENANCE_MODE=1 \
  "$REPO_ROOT/deploy/bin/restore" "$SNAPSHOT" "$UPLOADS_TARGET" \
  >/dev/null
test ! -e "$UPLOADS_TARGET/old.txt"
test "$(<"$UPLOADS_TARGET/chapter/textbook.txt")" = "original textbook"
test "$(<"$UPLOADS_TARGET/chapter/version.txt")" = "snapshot-4"
DATABASE_URL="$TARGET_URL" uv --directory "$BACKEND_DIR" run --no-env-file python - <<'PY'
import os
from sqlalchemy import create_engine, text
expected = [("13297540721", "admin"), ("18771701100", "student"), ("18771701111", "admin")]
with create_engine(os.environ["DATABASE_URL"]).connect() as connection:
    actual = connection.execute(text('SELECT identifier, role FROM "user" ORDER BY identifier')).all()
assert [tuple(row) for row in actual] == expected
PY

printf '%s\n' 'snapshot-5' > "$UPLOADS_SOURCE/chapter/version.txt"
DATABASE_URL="$SOURCE_URL" uv --directory "$BACKEND_DIR" run --no-env-file python - <<'PY'
import os
from sqlalchemy import create_engine, text
with create_engine(os.environ["DATABASE_URL"]).begin() as connection:
    connection.execute(
        text('UPDATE "user" SET username = :username WHERE identifier = :identifier'),
        {"username": "changed-after-backup", "identifier": "18771701100"},
    )
PY
DATABASE_URL="$SOURCE_BACKUP_URL" ONETREE_MAINTENANCE_MODE=1 TARGET_DATABASE_URL="$MAINTENANCE_URL" "$REPO_ROOT/deploy/bin/backup" \
  "$BACKUPS" "$UPLOADS_SOURCE" >/dev/null
NEW_SNAPSHOT="$(find "$BACKUPS" -mindepth 1 -maxdepth 1 -type d ! -name '.*' | sort | tail -1)"
RESTORE_FAIL_BIN="$TMP_DIR/restore-fail-bin"
RESTORE_COUNT="$TMP_DIR/restore-count"
REAL_PG_RESTORE="$(command -v pg_restore)"
mkdir "$RESTORE_FAIL_BIN"
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'set -euo pipefail' \
  'count=0' \
  'if [[ -f "$RESTORE_COUNT" ]]; then count="$(<"$RESTORE_COUNT")"; fi' \
  'count=$((count + 1))' \
  'printf "%s\n" "$count" > "$RESTORE_COUNT"' \
  'if [[ "$count" -eq 2 ]]; then exit 97; fi' \
  'exec "$REAL_PG_RESTORE" "$@"' > "$RESTORE_FAIL_BIN/pg_restore"
chmod 700 "$RESTORE_FAIL_BIN/pg_restore"
if PATH="$RESTORE_FAIL_BIN:$PATH" RESTORE_COUNT="$RESTORE_COUNT" \
  REAL_PG_RESTORE="$REAL_PG_RESTORE" TARGET_DATABASE_URL="$TARGET_URL" \
  ONETREE_MAINTENANCE_MODE=1 "$REPO_ROOT/deploy/bin/restore" \
  "$NEW_SNAPSHOT" "$UPLOADS_TARGET" >/dev/null 2>&1; then
  printf '%s\n' 'failing target pg_restore unexpectedly passed' >&2
  exit 1
fi
test "$(<"$UPLOADS_TARGET/chapter/version.txt")" = "snapshot-4"
DATABASE_URL="$TARGET_URL" uv --directory "$BACKEND_DIR" run --no-env-file python - <<'PY'
import os
from sqlalchemy import create_engine, text
with create_engine(os.environ["DATABASE_URL"]).connect() as connection:
    username = connection.execute(
        text('SELECT username FROM "user" WHERE identifier = :identifier'),
        {"identifier": "18771701100"},
    ).scalar_one()
assert username == "user-100"
PY

RESTORE_SIGNAL_BIN="$TMP_DIR/restore-signal-bin"
RESTORE_SIGNAL_TMP="$TMP_DIR/restore-signal-tmp"
mkdir "$RESTORE_SIGNAL_BIN" "$RESTORE_SIGNAL_TMP"
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'set -euo pipefail' \
  'count=0' \
  'if [[ -f "$RESTORE_SIGNAL_COUNT" ]]; then count="$(<"$RESTORE_SIGNAL_COUNT")"; fi' \
  'count=$((count + 1))' \
  'printf "%s\n" "$count" > "$RESTORE_SIGNAL_COUNT"' \
  'if [[ "$count" -eq 2 ]]; then' \
  '  printf "%s\n" target-restore-started > "$RESTORE_SIGNAL_MARKER"' \
  '  printf "%s\n" "$$" > "$RESTORE_SIGNAL_CHILD_PID"' \
  '  sleep 30' \
  'fi' \
  'exec "$REAL_PG_RESTORE" "$@"' > "$RESTORE_SIGNAL_BIN/pg_restore"
chmod 700 "$RESTORE_SIGNAL_BIN/pg_restore"

for restore_signal in INT TERM; do
  RESTORE_SIGNAL_COUNT="$TMP_DIR/restore-signal-count-$restore_signal"
  RESTORE_SIGNAL_MARKER="$TMP_DIR/restore-signal-marker-$restore_signal"
  RESTORE_SIGNAL_CHILD_PID="$TMP_DIR/restore-signal-child-$restore_signal"
  PATH="$RESTORE_SIGNAL_BIN:$PATH" TMPDIR="$RESTORE_SIGNAL_TMP" \
    RESTORE_SIGNAL_COUNT="$RESTORE_SIGNAL_COUNT" \
    RESTORE_SIGNAL_MARKER="$RESTORE_SIGNAL_MARKER" \
    RESTORE_SIGNAL_CHILD_PID="$RESTORE_SIGNAL_CHILD_PID" \
    REAL_PG_RESTORE="$REAL_PG_RESTORE" TARGET_DATABASE_URL="$TARGET_URL" \
    ONETREE_MAINTENANCE_MODE=1 "$REPO_ROOT/deploy/bin/restore" \
    "$NEW_SNAPSHOT" "$UPLOADS_TARGET" >/dev/null 2>&1 &
  restore_pid=$!
  for _ in {1..200}; do
    if [[ -s "$RESTORE_SIGNAL_MARKER" && -s "$RESTORE_SIGNAL_CHILD_PID" ]]; then
      break
    fi
    sleep 0.05
  done
  test "$(<"$RESTORE_SIGNAL_MARKER")" = "target-restore-started"
  kill -s "$restore_signal" "$restore_pid"
  if wait "$restore_pid"; then
    printf '%s\n' "restore unexpectedly passed $restore_signal" >&2
    exit 1
  fi
  child_pid="$(<"$RESTORE_SIGNAL_CHILD_PID")"
  for _ in {1..100}; do
    if ! kill -0 "$child_pid" 2>/dev/null; then
      break
    fi
    sleep 0.05
  done
  if kill -0 "$child_pid" 2>/dev/null; then
    child_state="$(ps -o stat= -p "$child_pid" | tr -d ' ')"
    if [[ "$child_state" != Z* ]]; then
      printf '%s\n' "restore left running descendant after $restore_signal" >&2
      exit 1
    fi
  fi
  upload_version="$(<"$UPLOADS_TARGET/chapter/version.txt")"
  database_username="$(DATABASE_URL="$TARGET_URL" uv --directory "$BACKEND_DIR" run --no-env-file python - <<'PY'
import os
from sqlalchemy import create_engine, text
with create_engine(os.environ["DATABASE_URL"]).connect() as connection:
    print(connection.execute(
        text('SELECT username FROM "user" WHERE identifier = :identifier'),
        {"identifier": "18771701100"},
    ).scalar_one())
PY
)"
  if [[ "$upload_version:$database_username" != "snapshot-4:user-100" && \
        "$upload_version:$database_username" != "snapshot-5:changed-after-backup" ]]; then
    printf '%s\n' "restore left inconsistent data after $restore_signal" >&2
    exit 1
  fi
  test -z "$(find "$RESTORE_SIGNAL_TMP" -mindepth 1 ! -name 'uv-*.lock' -print -quit)"
  find "$RESTORE_SIGNAL_TMP" -maxdepth 1 -type f -name 'uv-*.lock' -delete
  test -z "$(find "$(dirname "$UPLOADS_TARGET")" -maxdepth 1 -type d -name '.migration-import.*' -print -quit)"
  MAINTENANCE_URL="$MAINTENANCE_URL" uv --directory "$BACKEND_DIR" run --no-env-file python - <<'PY'
import os
import psycopg2
with psycopg2.connect(os.environ["MAINTENANCE_URL"]) as connection:
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM pg_database WHERE datname LIKE 'onetree_import_verify_%'")
        assert cursor.fetchone() == (0,)
PY
done

SIGNAL_BIN="$TMP_DIR/signal-bin"
SIGNAL_MARKER="$TMP_DIR/signal-marker"
REAL_PG_DUMP="$(command -v pg_dump)"
mkdir "$SIGNAL_BIN"
VISIBLE_BEFORE="$(find "$BACKUPS" -mindepth 1 -maxdepth 1 -type d ! -name '.*' | sort)"
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'set -euo pipefail' \
  'printf "%s\n" started > "$SIGNAL_MARKER"' \
  'kill -TERM "$PPID"' \
  'sleep 1' \
  'exec "$REAL_PG_DUMP" "$@"' > "$SIGNAL_BIN/pg_dump"
chmod 700 "$SIGNAL_BIN/pg_dump"
if PATH="$SIGNAL_BIN:$PATH" SIGNAL_MARKER="$SIGNAL_MARKER" \
  REAL_PG_DUMP="$REAL_PG_DUMP" DATABASE_URL="$SOURCE_BACKUP_URL" \
  ONETREE_MAINTENANCE_MODE=1 TARGET_DATABASE_URL="$MAINTENANCE_URL" \
  "$REPO_ROOT/deploy/bin/backup" "$BACKUPS" "$UPLOADS_SOURCE" \
  >/dev/null 2>&1; then
  printf '%s\n' 'SIGTERM backup unexpectedly passed' >&2
  exit 1
fi
test "$(<"$SIGNAL_MARKER")" = "started"
test "$VISIBLE_BEFORE" = "$(find "$BACKUPS" -mindepth 1 -maxdepth 1 -type d ! -name '.*' | sort)"
test -z "$(find "$BACKUPS" -mindepth 1 -maxdepth 1 -type d -name '.snapshot.*' -print -quit)"

printf '%s\n' 'backup restore roundtrip passed'
