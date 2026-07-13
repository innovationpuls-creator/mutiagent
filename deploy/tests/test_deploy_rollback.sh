#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMMON_SCRIPT="$REPO_ROOT/deploy/lib/common.sh"
DEPLOY_SCRIPT="$REPO_ROOT/deploy/bin/deploy"
ROLLBACK_SCRIPT="$REPO_ROOT/deploy/bin/rollback"

fail() {
  printf 'deploy rollback test failed: %s\n' "$1" >&2
  exit 1
}

for required_file in "$COMMON_SCRIPT" "$DEPLOY_SCRIPT" "$ROLLBACK_SCRIPT"; do
  [[ -f "$required_file" ]] || fail "missing required file: $required_file"
done

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

TEST_ROOT="$TMP_DIR/onetree"
STATE_DIR="$TMP_DIR/state"
STUB_BIN="$TMP_DIR/bin"
OUTPUT_FILE="$TMP_DIR/output"
LOCK_FILE="$TMP_DIR/onetree-deploy.lock"
OLD_COMMIT="1111111111111111111111111111111111111111"
NEW_COMMIT="2222222222222222222222222222222222222222"
OLD_BACKEND_IMAGE="sha256:old-backend"
OLD_NGINX_IMAGE="sha256:old-nginx"
NEW_BACKEND_IMAGE="sha256:new-backend"
NEW_NGINX_IMAGE="sha256:new-nginx"
ROLLBACK_BACKEND_IMAGE="sha256:rollback-backend"
ROLLBACK_NGINX_IMAGE="sha256:rollback-nginx"
BACKUP_ID="20260714T120000.000000Z"
DATABASE_URL_VALUE="postgresql://source-role:source-secret@postgres:5432/onetree?application_name=source=value"
TARGET_DATABASE_URL_VALUE="postgresql://maintenance-role:target-secret@postgres:5432/onetree?application_name=target=value"

mkdir -p \
  "$TEST_ROOT/deploy/lib" \
  "$TEST_ROOT/deploy" \
  "$TEST_ROOT/backups" \
  "$STATE_DIR" \
  "$STUB_BIN"
ln -s "$COMMON_SCRIPT" "$TEST_ROOT/deploy/lib/common.sh"
touch "$TEST_ROOT/deploy/compose.production.yml"
printf '%s\n' \
  "DATABASE_URL=$DATABASE_URL_VALUE" \
  "TARGET_DATABASE_URL=$TARGET_DATABASE_URL_VALUE" \
  'SMOKE_PASSWORD=smoke-secret-that-must-not-leak' \
  > "$TEST_ROOT/.env.production"

cat > "$STUB_BIN/flock" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

[[ "$1:$2" == "-n:9" ]] || exit 64
lock_directory="$TEST_STATE_DIR/flock-owner"
if mkdir "$lock_directory" 2>/dev/null; then
  printf '%s\n' "$PPID" > "$lock_directory/pid"
  exit 0
fi
owner_pid="$(<"$lock_directory/pid")"
if kill -0 "$owner_pid" 2>/dev/null; then
  exit 1
fi
rm -rf "$lock_directory"
mkdir "$lock_directory"
printf '%s\n' "$PPID" > "$lock_directory/pid"
SH

cat > "$STUB_BIN/git" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

printf 'git:%s\n' "$*" >> "$TEST_STATE_DIR/events"

case "$1:$2" in
  rev-parse:HEAD)
    cat "$TEST_STATE_DIR/current-commit"
    ;;
  rev-parse:FETCH_HEAD)
    printf '%s\n' "$TEST_NEW_COMMIT"
    ;;
  fetch:--prune)
    if [[ "${TEST_BLOCK_STAGE:-}" == "fetch" ]]; then
      touch "$TEST_STATE_DIR/fetch-blocked"
      while [[ ! -e "$TEST_STATE_DIR/release-fetch" ]]; do
        sleep 0.02
      done
    fi
    [[ "${TEST_FAIL_STAGE:-}" != "fetch" ]] || exit 71
    ;;
  checkout:--detach)
    printf '%s\n' "$3" > "$TEST_STATE_DIR/current-commit"
    ;;
  *)
    printf 'unexpected git command: %s\n' "$*" >&2
    exit 64
    ;;
esac
SH

cat > "$STUB_BIN/docker" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

event() {
  printf '%s\n' "$1" >> "$TEST_STATE_DIR/events"
}

fail_stage() {
  [[ "${TEST_FAIL_STAGE:-}" == "$1" ]]
}

assert_compose_paths() {
  [[ "$compose_env_file" == "$ONETREE_ROOT/.env.production" ]] || exit 65
  [[ "$compose_file" == "$ONETREE_ROOT/deploy/compose.production.yml" ]] || exit 66
}

if [[ "$1" == "image" && "$2" == "inspect" ]]; then
  image_name="$5"
  event "inspect:$image_name"
  case "$image_name" in
    onetree-backend:production) cat "$TEST_STATE_DIR/backend-image" ;;
    onetree-nginx:production) cat "$TEST_STATE_DIR/nginx-image" ;;
    *) exit 67 ;;
  esac
  exit 0
fi

if [[ "$1" == "image" && "$2" == "tag" ]]; then
  image_id="$3"
  image_name="$4"
  event "tag:$image_name:$image_id"
  case "$image_name" in
    onetree-backend:production) printf '%s\n' "$image_id" > "$TEST_STATE_DIR/backend-image" ;;
    onetree-nginx:production) printf '%s\n' "$image_id" > "$TEST_STATE_DIR/nginx-image" ;;
    *) exit 68 ;;
  esac
  exit 0
fi

[[ "$1" == "compose" ]] || exit 69
shift
compose_env_file=""
compose_file=""
profile=""
action=""
while (($#)); do
  case "$1" in
    --env-file)
      compose_env_file="$2"
      shift 2
      ;;
    -f)
      compose_file="$2"
      shift 2
      ;;
    --profile)
      profile="$2"
      shift 2
      ;;
    build|exec|stop|ps|run|up)
      action="$1"
      shift
      break
      ;;
    *)
      printf 'unexpected compose option: %s\n' "$1" >&2
      exit 64
      ;;
  esac
done
assert_compose_paths
event "compose:$action:$*"

case "$action" in
  build)
    event build
    printf '%s\n' "${TEST_BUILT_BACKEND_IMAGE:-$TEST_NEW_BACKEND_IMAGE}" \
      > "$TEST_STATE_DIR/backend-image"
    printf '%s\n' "${TEST_BUILT_NGINX_IMAGE:-$TEST_NEW_NGINX_IMAGE}" \
      > "$TEST_STATE_DIR/nginx-image"
    if fail_stage build; then
      exit 72
    fi
    ;;
  exec)
    [[ "$1:$2:$3" == "-T:nginx:touch" || "$1:$2:$3:$4" == "-T:nginx:rm:-f" ]] \
      || exit 73
    if [[ "$3" == "touch" ]]; then
      [[ "$4" == "/var/www/certbot/.onetree-maintenance" ]] || exit 74
      event maintenance-enter
      touch "$TEST_STATE_DIR/maintenance"
    else
      [[ "$5" == "/var/www/certbot/.onetree-maintenance" ]] || exit 75
      event maintenance-exit
      rm -f "$TEST_STATE_DIR/maintenance"
    fi
    ;;
  stop)
    [[ "$1:$2" == "backend:worker" ]] || exit 76
    event stop-writes
    touch "$TEST_STATE_DIR/writes-stopped"
    rm -f "$TEST_STATE_DIR/stop-verified"
    ;;
  ps)
    [[ "$1:$2:$3:$4:$5" == "--status:running:--services:backend:worker" ]] || exit 77
    event verify-stop
    if [[ -e "$TEST_STATE_DIR/writes-stopped" ]]; then
      touch "$TEST_STATE_DIR/stop-verified"
    else
      printf '%s\n' backend worker
    fi
    ;;
  up)
    [[ "$1" == "-d" ]] || exit 78
    event up
    rm -f "$TEST_STATE_DIR/writes-stopped" "$TEST_STATE_DIR/stop-verified"
    if fail_stage up; then
      exit 79
    fi
    ;;
  run)
    [[ "$profile" == "operations" ]] || exit 80
    entrypoint=""
    no_deps=0
    forwarded_database=0
    forwarded_target=0
    forwarded_maintenance=0
    while (($#)); do
      case "$1" in
        --rm)
          shift
          ;;
        --no-deps)
          no_deps=1
          shift
          ;;
        --entrypoint)
          entrypoint="$2"
          shift 2
          ;;
        -e)
          case "$2" in
            DATABASE_URL) forwarded_database=1 ;;
            TARGET_DATABASE_URL) forwarded_target=1 ;;
            ONETREE_MAINTENANCE_MODE) forwarded_maintenance=1 ;;
            *) exit 81 ;;
          esac
          shift 2
          ;;
        *)
          service="$1"
          shift
          break
          ;;
      esac
    done

    if [[ "$service" == "restore" && "$entrypoint" == "python" ]]; then
      [[ "$no_deps" -eq 1 ]] || exit 82
      event validate-manifest
      if fail_stage validate; then
        exit 83
      fi
      snapshot_path="${*: -1}"
      [[ "$snapshot_path" == "/backups/$TEST_BACKUP_ID" ]] || exit 84
      printf '%s\n' "$TEST_SNAPSHOT_COMMIT"
      exit 0
    fi

    case "$service" in
      backup)
        event "backup:$TEST_BACKUP_ID"
        [[ "$(<"$TEST_STATE_DIR/current-commit")" == "$TEST_OLD_COMMIT" ]] \
          || exit 105
        [[ "$forwarded_database:$forwarded_target:$forwarded_maintenance" == "1:1:1" ]] || exit 85
        [[ "$DATABASE_URL" == "$TEST_DATABASE_URL" ]] || exit 86
        [[ "$TARGET_DATABASE_URL" == "$TEST_TARGET_DATABASE_URL" ]] || exit 87
        [[ "$ONETREE_MAINTENANCE_MODE" == "1" ]] || exit 88
        [[ -e "$TEST_STATE_DIR/maintenance" && -e "$TEST_STATE_DIR/stop-verified" ]] || exit 89
        mkdir -p "$ONETREE_ROOT/backups/$TEST_BACKUP_ID"
        printf '%s\n' "$TEST_BACKUP_ID"
        if fail_stage backup; then
          exit 90
        fi
        ;;
      migrate)
        event migrate
        [[ "$(<"$TEST_STATE_DIR/current-commit")" == "$TEST_NEW_COMMIT" ]] \
          || exit 106
        [[ -e "$TEST_STATE_DIR/maintenance" && -e "$TEST_STATE_DIR/stop-verified" ]] || exit 91
        touch "$TEST_STATE_DIR/migration-started"
        if fail_stage migrate; then
          exit 92
        fi
        ;;
      restore)
        event "restore:$1"
        [[ "$forwarded_target:$forwarded_maintenance" == "1:1" ]] || exit 93
        [[ "$TARGET_DATABASE_URL" == "$TEST_TARGET_DATABASE_URL" ]] || exit 94
        [[ "$ONETREE_MAINTENANCE_MODE" == "1" ]] || exit 95
        [[ -e "$TEST_STATE_DIR/maintenance" && -e "$TEST_STATE_DIR/stop-verified" ]] || exit 96
        [[ "$1" == "/backups/$TEST_BACKUP_ID" ]] || exit 97
        [[ "$2" == "/var/lib/onetree/knowledge-base-uploads" ]] || exit 98
        touch "$TEST_STATE_DIR/restored"
        ;;
      smoke)
        event smoke
        [[ "$forwarded_database:$forwarded_target:$forwarded_maintenance" == "0:0:0" ]] || exit 99
        [[ -e "$TEST_STATE_DIR/maintenance" ]] || exit 100
        [[ ! -e "$TEST_STATE_DIR/writes-stopped" ]] || exit 101
        if fail_stage smoke; then
          exit 102
        fi
        ;;
      *)
        exit 103
        ;;
    esac
    ;;
  *)
    exit 104
    ;;
esac
SH

chmod 700 "$STUB_BIN/flock" "$STUB_BIN/git" "$STUB_BIN/docker"

reset_state() {
  rm -rf "$STATE_DIR" "$TEST_ROOT/backups"
  mkdir -p "$STATE_DIR" "$TEST_ROOT/backups"
  : > "$STATE_DIR/events"
  printf '%s\n' "$OLD_COMMIT" > "$STATE_DIR/current-commit"
  printf '%s\n' "$OLD_BACKEND_IMAGE" > "$STATE_DIR/backend-image"
  printf '%s\n' "$OLD_NGINX_IMAGE" > "$STATE_DIR/nginx-image"
  rm -f "$LOCK_FILE" "$OUTPUT_FILE"
}

base_environment() {
  env \
    PATH="$STUB_BIN:$PATH" \
    ONETREE_ROOT="$TEST_ROOT" \
    ONETREE_DEPLOY_LOCK_FILE="$LOCK_FILE" \
    TEST_STATE_DIR="$STATE_DIR" \
    TEST_NEW_COMMIT="$NEW_COMMIT" \
    TEST_OLD_COMMIT="$OLD_COMMIT" \
    TEST_NEW_BACKEND_IMAGE="$NEW_BACKEND_IMAGE" \
    TEST_NEW_NGINX_IMAGE="$NEW_NGINX_IMAGE" \
    TEST_BACKUP_ID="$BACKUP_ID" \
    TEST_DATABASE_URL="$DATABASE_URL_VALUE" \
    TEST_TARGET_DATABASE_URL="$TARGET_DATABASE_URL_VALUE" \
    TEST_SNAPSHOT_COMMIT="$OLD_COMMIT" \
    "$@"
}

run_deploy() {
  base_environment "$DEPLOY_SCRIPT" > "$OUTPUT_FILE" 2>&1
}

run_rollback() {
  base_environment \
    TEST_BUILT_BACKEND_IMAGE="$ROLLBACK_BACKEND_IMAGE" \
    TEST_BUILT_NGINX_IMAGE="$ROLLBACK_NGINX_IMAGE" \
    "$ROLLBACK_SCRIPT" "$BACKUP_ID" > "$OUTPUT_FILE" 2>&1
}

assert_secret_free_output() {
  local output_file="$1"
  local secret_value
  for secret_value in \
    "$DATABASE_URL_VALUE" \
    "$TARGET_DATABASE_URL_VALUE" \
    source-secret \
    target-secret \
    smoke-secret-that-must-not-leak; do
    if grep -Fq "$secret_value" "$output_file"; then
      fail "secret value leaked to output"
    fi
  done
}

assert_old_release_restored() {
  [[ "$(<"$STATE_DIR/current-commit")" == "$OLD_COMMIT" ]] \
    || fail "old commit was not restored"
  [[ "$(<"$STATE_DIR/backend-image")" == "$OLD_BACKEND_IMAGE" ]] \
    || fail "old backend image was not restored"
  [[ "$(<"$STATE_DIR/nginx-image")" == "$OLD_NGINX_IMAGE" ]] \
    || fail "old nginx image was not restored"
}

event_line() {
  local event_name="$1"
  awk -v expected="$event_name" '$0 == expected { print NR; exit }' \
    "$STATE_DIR/events"
}

assert_before() {
  local earlier="$1"
  local later="$2"
  local earlier_line
  local later_line
  earlier_line="$(event_line "$earlier")"
  later_line="$(event_line "$later")"
  [[ -n "$earlier_line" && -n "$later_line" && "$earlier_line" -lt "$later_line" ]] \
    || fail "expected $earlier before $later"
}

for failure_stage in fetch build backup migrate up smoke; do
  reset_state
  if base_environment TEST_FAIL_STAGE="$failure_stage" \
    "$DEPLOY_SCRIPT" > "$OUTPUT_FILE" 2>&1; then
    fail "$failure_stage failure unexpectedly passed"
  fi
  assert_old_release_restored
  case "$failure_stage" in
    fetch) expected_old_checkouts=0 ;;
    build|backup) expected_old_checkouts=1 ;;
    migrate|up|smoke) expected_old_checkouts=2 ;;
  esac
  [[ "$(grep -Fc "git:checkout --detach $OLD_COMMIT" "$STATE_DIR/events")" \
    -eq "$expected_old_checkouts" ]] \
    || fail "$failure_stage failure used an unexpected old commit transition count"
  [[ "$(grep -Fc "tag:onetree-backend:production:$OLD_BACKEND_IMAGE" "$STATE_DIR/events")" -eq 1 ]] \
    || fail "$failure_stage failure restored the old backend image more than once"
  [[ "$(grep -Fc "tag:onetree-nginx:production:$OLD_NGINX_IMAGE" "$STATE_DIR/events")" -eq 1 ]] \
    || fail "$failure_stage failure restored the old nginx image more than once"
  assert_secret_free_output "$OUTPUT_FILE"
  if [[ "$failure_stage" == "fetch" || "$failure_stage" == "build" ]]; then
    [[ ! -e "$STATE_DIR/maintenance" ]] \
      || fail "$failure_stage failure created maintenance marker"
  else
    [[ -e "$STATE_DIR/maintenance" ]] \
      || fail "$failure_stage failure removed maintenance marker; events: $(tr '\n' ',' < "$STATE_DIR/events"); errors: $(grep -E 'deployment error:|unbound variable|unexpected|line [0-9]+' "$OUTPUT_FILE" || true)"
  fi
  if [[ "$failure_stage" == "migrate" || "$failure_stage" == "up" || "$failure_stage" == "smoke" ]]; then
    [[ "$(grep -Fc "restore:/backups/$BACKUP_ID" "$STATE_DIR/events")" -eq 1 ]] \
      || fail "$failure_stage failure did not restore the same backup id"
  else
    ! grep -Fq 'restore:' "$STATE_DIR/events" \
      || fail "$failure_stage failure restored data before migration"
  fi
  ! grep -Fxq maintenance-exit "$STATE_DIR/events" \
    || fail "$failure_stage failure exited maintenance"
done

reset_state
touch "$STATE_DIR/maintenance"
if base_environment TEST_FAIL_STAGE=fetch "$DEPLOY_SCRIPT" > "$OUTPUT_FILE" 2>&1; then
  fail 'fetch failure with existing maintenance marker unexpectedly passed'
fi
[[ -e "$STATE_DIR/maintenance" ]] || fail 'existing maintenance marker was removed'
! grep -Fxq maintenance-exit "$STATE_DIR/events" \
  || fail 'failed deploy exited pre-existing maintenance'

reset_state
run_deploy || fail "successful deploy failed: $(<"$OUTPUT_FILE")"
[[ "$(<"$STATE_DIR/current-commit")" == "$NEW_COMMIT" ]] \
  || fail 'successful deploy did not keep the fetched commit'
[[ "$(<"$STATE_DIR/backend-image")" == "$NEW_BACKEND_IMAGE" ]] \
  || fail 'successful deploy did not keep the new backend image'
[[ "$(<"$STATE_DIR/nginx-image")" == "$NEW_NGINX_IMAGE" ]] \
  || fail 'successful deploy did not keep the new nginx image'
[[ ! -e "$STATE_DIR/maintenance" ]] || fail 'successful deploy kept maintenance marker'
! grep -Fq 'restore:' "$STATE_DIR/events" || fail 'successful deploy restored a backup'
assert_before 'git:fetch --prune origin main' 'build'
assert_before 'build' 'maintenance-enter'
assert_before 'maintenance-enter' 'stop-writes'
assert_before 'stop-writes' 'verify-stop'
assert_before 'verify-stop' "backup:$BACKUP_ID"
assert_before "backup:$BACKUP_ID" 'migrate'
assert_before 'migrate' 'up'
assert_before 'up' 'smoke'
assert_before 'smoke' 'maintenance-exit'
assert_secret_free_output "$OUTPUT_FILE"

reset_state
base_environment TEST_BLOCK_STAGE=fetch "$DEPLOY_SCRIPT" > "$TMP_DIR/first-output" 2>&1 &
first_deploy_pid=$!
for _ in {1..200}; do
  [[ -e "$STATE_DIR/fetch-blocked" ]] && break
  sleep 0.02
done
[[ -e "$STATE_DIR/fetch-blocked" ]] || fail 'first deploy did not reach lock test barrier'
if run_deploy; then
  kill "$first_deploy_pid" 2>/dev/null || true
  fail 'second deploy unexpectedly acquired the lock'
fi
assert_secret_free_output "$OUTPUT_FILE"
touch "$STATE_DIR/release-fetch"
wait "$first_deploy_pid" || fail 'first deploy failed after lock test release'

reset_state
printf '%s\n' "$NEW_COMMIT" > "$STATE_DIR/current-commit"
printf '%s\n' "$NEW_BACKEND_IMAGE" > "$STATE_DIR/backend-image"
printf '%s\n' "$NEW_NGINX_IMAGE" > "$STATE_DIR/nginx-image"
mkdir -p "$TEST_ROOT/backups/$BACKUP_ID"
run_rollback || fail "successful rollback failed: $(<"$OUTPUT_FILE")"
[[ "$(<"$STATE_DIR/current-commit")" == "$OLD_COMMIT" ]] \
  || fail 'rollback did not restore manifest commit'
[[ "$(<"$STATE_DIR/backend-image")" == "$ROLLBACK_BACKEND_IMAGE" ]] \
  || fail 'rollback did not build the corresponding backend image'
[[ "$(<"$STATE_DIR/nginx-image")" == "$ROLLBACK_NGINX_IMAGE" ]] \
  || fail 'rollback did not build the corresponding nginx image'
[[ -e "$STATE_DIR/restored" ]] || fail 'rollback did not restore snapshot data'
[[ ! -e "$STATE_DIR/maintenance" ]] || fail 'successful rollback kept maintenance marker'
assert_before 'validate-manifest' 'maintenance-enter'
assert_before 'maintenance-enter' 'stop-writes'
assert_before 'stop-writes' 'verify-stop'
assert_before 'verify-stop' "git:checkout --detach $OLD_COMMIT"
assert_before "git:checkout --detach $OLD_COMMIT" 'build'
assert_before 'build' "restore:/backups/$BACKUP_ID"
assert_before "restore:/backups/$BACKUP_ID" 'up'
assert_before 'up' 'smoke'
assert_before 'smoke' 'maintenance-exit'
assert_secret_free_output "$OUTPUT_FILE"

reset_state
printf '%s\n' "$NEW_COMMIT" > "$STATE_DIR/current-commit"
if base_environment TEST_FAIL_STAGE=validate "$ROLLBACK_SCRIPT" "$BACKUP_ID" \
  > "$OUTPUT_FILE" 2>&1; then
  fail 'invalid manifest unexpectedly passed rollback'
fi
[[ "$(<"$STATE_DIR/current-commit")" == "$NEW_COMMIT" ]] \
  || fail 'manifest failure changed commit'
[[ ! -e "$STATE_DIR/maintenance" ]] || fail 'manifest failure entered maintenance'
! grep -Fxq stop-writes "$STATE_DIR/events" || fail 'manifest failure stopped writes'

reset_state
printf '%s\n' "$NEW_COMMIT" > "$STATE_DIR/current-commit"
mkdir -p "$TEST_ROOT/backups/$BACKUP_ID"
if base_environment \
  TEST_FAIL_STAGE=smoke \
  TEST_BUILT_BACKEND_IMAGE="$ROLLBACK_BACKEND_IMAGE" \
  TEST_BUILT_NGINX_IMAGE="$ROLLBACK_NGINX_IMAGE" \
  "$ROLLBACK_SCRIPT" "$BACKUP_ID" > "$OUTPUT_FILE" 2>&1; then
  fail 'rollback smoke failure unexpectedly passed'
fi
[[ -e "$STATE_DIR/maintenance" ]] || fail 'rollback smoke failure exited maintenance'
[[ -e "$STATE_DIR/restored" ]] || fail 'rollback smoke failure skipped restore'
! grep -Fxq maintenance-exit "$STATE_DIR/events" \
  || fail 'rollback smoke failure removed maintenance marker'

reset_state
if base_environment "$ROLLBACK_SCRIPT" '../bad-backup-id' > "$OUTPUT_FILE" 2>&1; then
  fail 'path-like backup id unexpectedly passed'
fi
! grep -Fxq validate-manifest "$STATE_DIR/events" \
  || fail 'invalid backup id reached manifest validation'

grep -Fq '/run/lock/onetree-deploy.lock' "$COMMON_SCRIPT" \
  || fail 'fixed deploy lock path is missing'
grep -Fq '/opt/onetree' "$COMMON_SCRIPT" \
  || fail 'fixed install root is missing'

if grep -ERn --include='*.sh' --include='deploy' --include='rollback' \
  'down[[:space:]]+(-v|--volumes)|rm[[:space:]].*postgres_data' \
  "$REPO_ROOT/deploy/bin" "$REPO_ROOT/deploy/lib" > "$TMP_DIR/dangerous"; then
  fail "dangerous deployment command found: $(<"$TMP_DIR/dangerous")"
fi

if grep -ERn --include='*.sh' --include='deploy' --include='rollback' \
  '(echo|printf)[^\n]*(DATABASE_URL|TARGET_DATABASE_URL|JWT_SECRET|LLM_API_KEY|SMOKE_PASSWORD)' \
  "$REPO_ROOT/deploy/bin" "$REPO_ROOT/deploy/lib" > "$TMP_DIR/secret-echo"; then
  fail "secret echo found: $(<"$TMP_DIR/secret-echo")"
fi

printf '%s\n' 'deploy rollback tests passed'
