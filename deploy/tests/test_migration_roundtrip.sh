#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
TMP_DIR="$(mktemp -d)"
SOURCE_DB="onetree_migration_source_$$"
TARGET_DB="onetree_migration_target_$$"
MIGRATION_TEST_MAINTENANCE_URL="${MIGRATION_TEST_MAINTENANCE_URL:-postgresql:///postgres}"

cleanup() {
  SOURCE_DB="$SOURCE_DB" TARGET_DB="$TARGET_DB" \
    MAINTENANCE_URL="$MIGRATION_TEST_MAINTENANCE_URL" \
    "$BACKEND_DIR/.venv/bin/python" - <<'PY'
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
finally:
    connection.close()
PY
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

SOURCE_URL_FILE="$TMP_DIR/source-url"
TARGET_URL_FILE="$TMP_DIR/target-url"
SOURCE_DB="$SOURCE_DB" TARGET_DB="$TARGET_DB" \
  MAINTENANCE_URL="$MIGRATION_TEST_MAINTENANCE_URL" \
  SOURCE_URL_FILE="$SOURCE_URL_FILE" TARGET_URL_FILE="$TARGET_URL_FILE" \
  "$BACKEND_DIR/.venv/bin/python" - <<'PY'
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
finally:
    connection.close()

Path(os.environ["SOURCE_URL_FILE"]).write_text(
    base_url.set(database=os.environ["SOURCE_DB"]).render_as_string(hide_password=False)
)
Path(os.environ["TARGET_URL_FILE"]).write_text(
    base_url.set(database=os.environ["TARGET_DB"]).render_as_string(hide_password=False)
)
PY
chmod 600 "$SOURCE_URL_FILE" "$TARGET_URL_FILE"
SOURCE_URL="$(<"$SOURCE_URL_FILE")"
TARGET_URL="$(<"$TARGET_URL_FILE")"

cd "$BACKEND_DIR"
DATABASE_URL="$SOURCE_URL" .venv/bin/python - <<'PY'
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

BUNDLE="$TMP_DIR/local-data.tar"
"$REPO_ROOT/deploy/bin/export-local-data" --repo-root "$FAKE_REPO" "$BUNDLE"
"$REPO_ROOT/deploy/bin/verify-bundle" "$BUNDLE"

TARGET_UPLOADS="$TMP_DIR/restored-uploads"
mkdir -p "$TARGET_UPLOADS"
printf '%s\n' 'stale' > "$TARGET_UPLOADS/stale.txt"
mkdir "$TMP_DIR/.restored-uploads.previous"
if TARGET_DATABASE_URL="$TARGET_URL" ONETREE_MAINTENANCE_MODE=1 \
  "$REPO_ROOT/deploy/bin/import-bundle" "$BUNDLE" "$TARGET_UPLOADS" \
  >/dev/null 2>&1; then
  printf '%s\n' 'import unexpectedly accepted an existing protection directory' >&2
  exit 1
fi
DATABASE_URL="$TARGET_URL" .venv/bin/python - <<'PY'
import os

from sqlalchemy import create_engine, text

with create_engine(os.environ["DATABASE_URL"]).connect() as connection:
    assert connection.execute(text("SELECT to_regclass('public.user')")).scalar_one() is None
PY
rmdir "$TMP_DIR/.restored-uploads.previous"
TARGET_DATABASE_URL="$TARGET_URL" ONETREE_MAINTENANCE_MODE=1 \
  "$REPO_ROOT/deploy/bin/import-bundle" "$BUNDLE" "$TARGET_UPLOADS"

DATABASE_URL="$TARGET_URL" .venv/bin/python - <<'PY'
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
