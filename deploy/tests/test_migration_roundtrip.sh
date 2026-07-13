#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
TMP_DIR="$(mktemp -d)"
SOURCE_DB="onetree_migration_source_$$"
TARGET_DB="onetree_migration_target_$$"
NO_CREATEDB_ROLE="onetree_no_createdb_$$"
MIGRATION_TEST_MAINTENANCE_URL="${MIGRATION_TEST_MAINTENANCE_URL:-postgresql:///postgres}"

cleanup() {
  SOURCE_DB="$SOURCE_DB" TARGET_DB="$TARGET_DB" NO_CREATEDB_ROLE="$NO_CREATEDB_ROLE" \
    MAINTENANCE_URL="$MIGRATION_TEST_MAINTENANCE_URL" \
    uv --directory "$BACKEND_DIR" run --no-env-file python - <<'PY'
import os

import psycopg2
from psycopg2 import sql

connection = psycopg2.connect(os.environ["MAINTENANCE_URL"])
connection.autocommit = True
try:
    for variable in ("SOURCE_DB", "TARGET_DB"):
        database_name = os.environ[variable]
        connection.cursor().execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                sql.Identifier(database_name)
            )
        )
    role_name = os.environ["NO_CREATEDB_ROLE"]
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role_name,))
        if cursor.fetchone() is not None:
            cursor.execute(
                sql.SQL("REVOKE {} FROM torch").format(sql.Identifier(role_name))
            )
            cursor.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role_name)))
finally:
    connection.close()
PY
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

SOURCE_URL_FILE="$TMP_DIR/source-url"
TARGET_URL_FILE="$TMP_DIR/target-url"
NO_CREATEDB_URL_FILE="$TMP_DIR/no-createdb-url"
SOURCE_DB="$SOURCE_DB" TARGET_DB="$TARGET_DB" NO_CREATEDB_ROLE="$NO_CREATEDB_ROLE" \
  MAINTENANCE_URL="$MIGRATION_TEST_MAINTENANCE_URL" \
  SOURCE_URL_FILE="$SOURCE_URL_FILE" TARGET_URL_FILE="$TARGET_URL_FILE" \
  NO_CREATEDB_URL_FILE="$NO_CREATEDB_URL_FILE" \
  uv --directory "$BACKEND_DIR" run --no-env-file python - <<'PY'
import os
from pathlib import Path

import psycopg2
from psycopg2 import sql
from sqlalchemy.engine import make_url

maintenance_url = os.environ["MAINTENANCE_URL"]
base_url = make_url(maintenance_url)
connection = psycopg2.connect(maintenance_url)
connection.autocommit = True
try:
    for variable in ("SOURCE_DB", "TARGET_DB"):
        connection.cursor().execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(os.environ[variable]))
        )
    role_name = os.environ["NO_CREATEDB_ROLE"]
    connection.cursor().execute(
        sql.SQL("CREATE ROLE {} NOCREATEDB").format(sql.Identifier(role_name))
    )
    connection.cursor().execute(
        sql.SQL("GRANT {} TO torch").format(sql.Identifier(role_name))
    )
finally:
    connection.close()

Path(os.environ["SOURCE_URL_FILE"]).write_text(
    base_url.set(database=os.environ["SOURCE_DB"]).render_as_string(hide_password=False)
)
Path(os.environ["TARGET_URL_FILE"]).write_text(
    base_url.set(database=os.environ["TARGET_DB"]).render_as_string(hide_password=False)
)
Path(os.environ["NO_CREATEDB_URL_FILE"]).write_text(
    base_url.set(database=os.environ["TARGET_DB"]).update_query_dict(
        {"options": f"-c role={os.environ['NO_CREATEDB_ROLE']}"}
    ).render_as_string(hide_password=False)
)
PY
chmod 600 "$SOURCE_URL_FILE" "$TARGET_URL_FILE" "$NO_CREATEDB_URL_FILE"
SOURCE_URL="$(<"$SOURCE_URL_FILE")"
TARGET_URL="$(<"$TARGET_URL_FILE")"
NO_CREATEDB_URL="$(<"$NO_CREATEDB_URL_FILE")"

cd "$BACKEND_DIR"
DATABASE_URL="$SOURCE_URL" uv run --no-env-file python - <<'PY'
import os

from sqlalchemy import create_engine
from sqlmodel import Session

from app.migration_state import migrate_to_head
from app.models import User

engine = create_engine(os.environ["DATABASE_URL"])
migrate_to_head(engine)
with Session(engine) as session:
    session.add_all(
        [
            User(
                uid="roundtrip-admin",
                username="admin",
                identifier="13297540721",
                role="admin",
            ),
            User(
                uid="roundtrip-user-100",
                username="user-100",
                identifier="18771701100",
                role="student",
            ),
            User(
                uid="roundtrip-user-111",
                username="user-111",
                identifier="18771701111",
                role="admin",
            ),
        ]
    )
    session.commit()
with engine.begin() as connection:
    connection.exec_driver_sql("DROP TABLE alembic_version")
PY

FAKE_REPO="$TMP_DIR/project"
SOURCE_UPLOADS="$FAKE_REPO/backend/.codex-artifacts/knowledge-base-uploads"
mkdir -p "$SOURCE_UPLOADS/高等数学/第一章" "$SOURCE_UPLOADS/计算机/导论"
printf '%s\n' '极限教材' > "$SOURCE_UPLOADS/高等数学/第一章/极限.txt"
printf '%s\n' '计算机教材' > "$SOURCE_UPLOADS/计算机/导论/概览.md"
printf 'DATABASE_URL=%s\n' "$SOURCE_URL" > "$FAKE_REPO/backend/.env"

SOURCE_TREE_HASH="$TMP_DIR/source-tree.sha256"
(
  cd "$SOURCE_UPLOADS"
  find . -type f -print0 | sort -z | xargs -0 shasum -a 256
) > "$SOURCE_TREE_HASH"

MISSING_ACCOUNT_BUNDLE="$TMP_DIR/missing-account.tar"
DATABASE_URL="$SOURCE_URL" uv run --no-env-file python - <<'PY'
import os

from sqlalchemy import create_engine, text

with create_engine(os.environ["DATABASE_URL"]).begin() as connection:
    connection.execute(
        text('DELETE FROM "user" WHERE identifier = :identifier'),
        {"identifier": "18771701111"},
    )
PY
"$REPO_ROOT/deploy/bin/export-local-data" \
  --repo-root "$FAKE_REPO" "$MISSING_ACCOUNT_BUNDLE"

DATABASE_URL="$SOURCE_URL" uv run --no-env-file python - <<'PY'
import os

from sqlalchemy import create_engine
from sqlmodel import Session

from app.models import User

with Session(create_engine(os.environ["DATABASE_URL"])) as session:
    session.add(
        User(
            uid="roundtrip-user-111",
            username="user-111",
            identifier="18771701111",
            role="admin",
        )
    )
    session.commit()
PY

BUNDLE="$TMP_DIR/local-data.tar"
FIXED_ARCHIVE_SENTINEL="$TMP_DIR/fixed-archive-sentinel"
FIXED_VERIFIED_SENTINEL="$TMP_DIR/.local-data.tar.verified"
printf '%s\n' 'archive-sentinel' > "$FIXED_ARCHIVE_SENTINEL"
ln -s "$FIXED_ARCHIVE_SENTINEL" "$TMP_DIR/.local-data.tar.tmp"
mkdir "$FIXED_VERIFIED_SENTINEL"
printf '%s\n' 'verified-sentinel' > "$FIXED_VERIFIED_SENTINEL/sentinel.txt"
"$REPO_ROOT/deploy/bin/export-local-data" --repo-root "$FAKE_REPO" "$BUNDLE"
test "$(<"$FIXED_ARCHIVE_SENTINEL")" = "archive-sentinel"
test "$(<"$FIXED_VERIFIED_SENTINEL/sentinel.txt")" = "verified-sentinel"
test -z "$(find "$TMP_DIR" -maxdepth 1 -type d -name '.migration-*' -print -quit)"
"$REPO_ROOT/deploy/bin/verify-bundle" "$BUNDLE"

NO_PERMISSION_UPLOADS="$TMP_DIR/no-permission-uploads"
NO_PERMISSION_ERROR="$TMP_DIR/no-permission-error"
mkdir "$NO_PERMISSION_UPLOADS"
printf '%s\n' 'permission-old' > "$NO_PERMISSION_UPLOADS/old.txt"
if TARGET_DATABASE_URL="$NO_CREATEDB_URL" ONETREE_MAINTENANCE_MODE=1 \
  "$REPO_ROOT/deploy/bin/import-bundle" "$BUNDLE" "$NO_PERMISSION_UPLOADS" \
  >/dev/null 2>"$NO_PERMISSION_ERROR"; then
  printf '%s\n' 'role without CREATEDB unexpectedly accepted' >&2
  exit 1
fi
grep -F '维护态数据库角色必须具备 CREATEDB 权限' "$NO_PERMISSION_ERROR" >/dev/null
if grep -F "$NO_CREATEDB_URL" "$NO_PERMISSION_ERROR" >/dev/null; then
  printf '%s\n' 'permission error leaked database URL' >&2
  exit 1
fi
test "$(<"$NO_PERMISSION_UPLOADS/old.txt")" = "permission-old"

SYMLINK_REAL_TARGET="$TMP_DIR/symlink-real-uploads"
SYMLINK_UPLOAD_TARGET="$TMP_DIR/symlink-uploads"
mkdir "$SYMLINK_REAL_TARGET"
printf '%s\n' 'symlink-old' > "$SYMLINK_REAL_TARGET/old.txt"
ln -s "$SYMLINK_REAL_TARGET" "$SYMLINK_UPLOAD_TARGET"
if TARGET_DATABASE_URL="$TARGET_URL" ONETREE_MAINTENANCE_MODE=1 \
  "$REPO_ROOT/deploy/bin/import-bundle" "$BUNDLE" "$SYMLINK_UPLOAD_TARGET" \
  >/dev/null 2>&1; then
  printf '%s\n' 'symlink upload target unexpectedly accepted' >&2
  exit 1
fi
test -L "$SYMLINK_UPLOAD_TARGET"
test "$(<"$SYMLINK_REAL_TARGET/old.txt")" = "symlink-old"

BAD_SCHEMA_DIRECTORY="$TMP_DIR/bad-schema-directory"
BAD_SCHEMA_BUNDLE="$TMP_DIR/bad-schema.tar"
DATABASE_URL="$SOURCE_URL" uv run --no-env-file python - <<'PY'
import os

from sqlalchemy import create_engine

with create_engine(os.environ["DATABASE_URL"]).begin() as connection:
    connection.exec_driver_sql('ALTER TABLE "user" DROP COLUMN provider')
    connection.exec_driver_sql(
        "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
    )
    connection.exec_driver_sql(
        "INSERT INTO alembic_version (version_num) "
        "VALUES ('0002_ingestion_job_leases')"
    )
PY
mkdir "$BAD_SCHEMA_DIRECTORY"
pg_dump --format=custom --file="$BAD_SCHEMA_DIRECTORY/database.dump" "$SOURCE_URL"
(
  cd "$SOURCE_UPLOADS"
  tar -cf "$BAD_SCHEMA_DIRECTORY/knowledge-base-uploads.tar" .
)
BAD_SCHEMA_DIRECTORY="$BAD_SCHEMA_DIRECTORY" BAD_SCHEMA_BUNDLE="$BAD_SCHEMA_BUNDLE" \
  python3 - <<PY
import os
import sys
from pathlib import Path

sys.path.insert(0, "$REPO_ROOT/deploy/lib")
from migration_manifest import create_bundle_archive, write_manifest

directory = Path(os.environ["BAD_SCHEMA_DIRECTORY"])
write_manifest(directory, "versioned", "0002_ingestion_job_leases")
create_bundle_archive(directory, Path(os.environ["BAD_SCHEMA_BUNDLE"]))
PY

VERIFY_SIGNAL_TMP="$TMP_DIR/verify-signal-tmp"
VERIFY_SIGNAL_BIN="$TMP_DIR/verify-signal-bin"
VERIFY_SIGNAL_MARKER="$TMP_DIR/verify-signal-marker"
mkdir "$VERIFY_SIGNAL_TMP" "$VERIFY_SIGNAL_BIN"
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'set -euo pipefail' \
  'printf "%s\n" "backend-check-started" > "$VERIFY_SIGNAL_MARKER"' \
  'sleep 30' \
  > "$VERIFY_SIGNAL_BIN/uv"
chmod 700 "$VERIFY_SIGNAL_BIN/uv"
TMPDIR="$VERIFY_SIGNAL_TMP" PATH="$VERIFY_SIGNAL_BIN:$PATH" \
  VERIFY_SIGNAL_MARKER="$VERIFY_SIGNAL_MARKER" \
  "$REPO_ROOT/deploy/bin/verify-bundle" "$BAD_SCHEMA_BUNDLE" >/dev/null 2>&1 &
VERIFY_SIGNAL_PID=$!
for _ in {1..100}; do
  if [[ -f "$VERIFY_SIGNAL_MARKER" ]]; then
    break
  fi
  sleep 0.05
done
test -f "$VERIFY_SIGNAL_MARKER"
test -n "$(find "$VERIFY_SIGNAL_TMP" -maxdepth 1 -type d -name 'onetree-bundle-check.*' -print -quit)"
kill -TERM "$VERIFY_SIGNAL_PID"
if wait "$VERIFY_SIGNAL_PID"; then
  printf '%s\n' 'verify-bundle unexpectedly accepted SIGTERM' >&2
  exit 1
fi
test -z "$(find "$VERIFY_SIGNAL_TMP" -maxdepth 1 -type d -name 'onetree-bundle-check.*' -print -quit)"

TARGET_UPLOADS="$TMP_DIR/restored-uploads"
mkdir -p "$TARGET_UPLOADS"
printf '%s\n' 'stale' > "$TARGET_UPLOADS/stale.txt"
DATABASE_URL="$TARGET_URL" uv run --no-env-file python - <<'PY'
import os

from sqlalchemy import create_engine

with create_engine(os.environ["DATABASE_URL"]).begin() as connection:
    connection.exec_driver_sql("CREATE TABLE migration_sentinel (value text NOT NULL)")
    connection.exec_driver_sql(
        "INSERT INTO migration_sentinel (value) VALUES ('untouched')"
    )
PY

assert_target_unchanged() {
  DATABASE_URL="$TARGET_URL" uv run --no-env-file python - <<'PY'
import os

from sqlalchemy import create_engine, text

with create_engine(os.environ["DATABASE_URL"]).connect() as connection:
    assert connection.execute(
        text("SELECT value FROM migration_sentinel")
    ).scalar_one() == "untouched"
    assert connection.execute(
        text("SELECT to_regclass('public.user')")
    ).scalar_one() is None
PY
}

assert_no_validation_databases() {
  MAINTENANCE_URL="$MIGRATION_TEST_MAINTENANCE_URL" \
    uv --directory "$BACKEND_DIR" run --no-env-file python - <<'PY'
import os

import psycopg2

with psycopg2.connect(os.environ["MAINTENANCE_URL"]) as connection:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_database "
            "WHERE datname LIKE 'onetree_import_verify_%'"
        )
        assert cursor.fetchone() == (0,)
PY
}

for invalid_bundle in "$MISSING_ACCOUNT_BUNDLE" "$BAD_SCHEMA_BUNDLE"; do
  if TARGET_DATABASE_URL="$TARGET_URL" ONETREE_MAINTENANCE_MODE=1 \
    "$REPO_ROOT/deploy/bin/import-bundle" "$invalid_bundle" "$TARGET_UPLOADS" \
    >/dev/null 2>&1; then
    printf '%s\n' 'invalid migration bundle unexpectedly imported' >&2
    exit 1
  fi
  assert_target_unchanged
  assert_no_validation_databases
  test -z "$(find "$TMP_DIR" -maxdepth 1 -type d -name '.migration-import.*' -print -quit)"
done

FIXED_PREVIOUS="$TMP_DIR/.restored-uploads.previous"
mkdir "$FIXED_PREVIOUS"
printf '%s\n' 'fixed-previous' > "$FIXED_PREVIOUS/sentinel.txt"
PG_RESTORE_INJECT_DIR="$TMP_DIR/pg-restore-inject"
PG_RESTORE_COUNT_FILE="$TMP_DIR/pg-restore-count"
PG_RESTORE_MARKER="$TMP_DIR/pg-restore-marker"
REAL_PG_RESTORE="$(command -v pg_restore)"
mkdir "$PG_RESTORE_INJECT_DIR"
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'set -euo pipefail' \
  'count=0' \
  'if [[ -f "$PG_RESTORE_COUNT_FILE" ]]; then count="$(<"$PG_RESTORE_COUNT_FILE")"; fi' \
  'count=$((count + 1))' \
  'printf "%s\n" "$count" > "$PG_RESTORE_COUNT_FILE"' \
  'if [[ "$count" -eq 2 ]]; then' \
  '  test -f "$INJECT_UPLOAD_TARGET/高等数学/第一章/极限.txt"' \
  '  test ! -e "$INJECT_UPLOAD_TARGET/stale.txt"' \
  '  printf "%s\n" "new-uploads-visible" > "$PG_RESTORE_MARKER"' \
  '  if [[ "$PG_RESTORE_INJECT_MODE" == "failure" ]]; then exit 97; fi' \
  '  kill -TERM "$PPID"' \
  '  sleep 30' \
  'fi' \
  'exec "$REAL_PG_RESTORE" "$@"' \
  > "$PG_RESTORE_INJECT_DIR/pg_restore"
chmod 700 "$PG_RESTORE_INJECT_DIR/pg_restore"

for inject_mode in failure signal; do
  rm -f "$PG_RESTORE_COUNT_FILE" "$PG_RESTORE_MARKER"
  if PATH="$PG_RESTORE_INJECT_DIR:$PATH" \
    PG_RESTORE_COUNT_FILE="$PG_RESTORE_COUNT_FILE" \
    PG_RESTORE_MARKER="$PG_RESTORE_MARKER" \
    PG_RESTORE_INJECT_MODE="$inject_mode" \
    INJECT_UPLOAD_TARGET="$TARGET_UPLOADS" \
    REAL_PG_RESTORE="$REAL_PG_RESTORE" \
    TARGET_DATABASE_URL="$TARGET_URL" ONETREE_MAINTENANCE_MODE=1 \
    "$REPO_ROOT/deploy/bin/import-bundle" "$BUNDLE" "$TARGET_UPLOADS" \
    >/dev/null 2>&1; then
    printf '%s\n' 'injected target restore interruption unexpectedly passed' >&2
    exit 1
  fi
  test "$(<"$PG_RESTORE_MARKER")" = "new-uploads-visible"
  assert_target_unchanged
  assert_no_validation_databases
  test "$(<"$TARGET_UPLOADS/stale.txt")" = "stale"
  test ! -e "$TARGET_UPLOADS/高等数学/第一章/极限.txt"
done
test "$(<"$FIXED_PREVIOUS/sentinel.txt")" = "fixed-previous"

DATABASE_URL="$TARGET_URL" uv run --no-env-file python - <<'PY'
import os

from sqlalchemy import create_engine

with create_engine(os.environ["DATABASE_URL"]).begin() as connection:
    connection.exec_driver_sql("DROP TABLE migration_sentinel")
PY
TARGET_DATABASE_URL="$TARGET_URL" ONETREE_MAINTENANCE_MODE=1 \
  "$REPO_ROOT/deploy/bin/import-bundle" "$BUNDLE" "$TARGET_UPLOADS"

DATABASE_URL="$TARGET_URL" uv run --no-env-file python - <<'PY'
import os

from sqlalchemy import create_engine, text

from app.migration_state import assert_schema_at_head, migrate_to_head

expected = [
    ("13297540721", "admin"),
    ("18771701100", "student"),
    ("18771701111", "admin"),
]
engine = create_engine(os.environ["DATABASE_URL"])
with engine.connect() as connection:
    actual = connection.execute(
        text(
            'SELECT identifier, role FROM "user" '
            "WHERE identifier IN (:admin, :user_100, :user_111) "
            "ORDER BY identifier"
        ),
        {
            "admin": "13297540721",
            "user_100": "18771701100",
            "user_111": "18771701111",
        },
    ).all()
assert [tuple(row) for row in actual] == expected
migrate_to_head(engine)
assert_schema_at_head(engine)
PY

TARGET_TREE_HASH="$TMP_DIR/target-tree.sha256"
(
  cd "$TARGET_UPLOADS"
  find . -type f -print0 | sort -z | xargs -0 shasum -a 256
) > "$TARGET_TREE_HASH"
cmp "$SOURCE_TREE_HASH" "$TARGET_TREE_HASH"
test ! -e "$TARGET_UPLOADS/stale.txt"
printf '%s\n' 'migration roundtrip passed'
