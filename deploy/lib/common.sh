#!/usr/bin/env bash

ONETREE_ROOT="${ONETREE_ROOT:-/opt/onetree}"
ONETREE_ENV_FILE="$ONETREE_ROOT/.env.production"
ONETREE_COMPOSE_FILE="$ONETREE_ROOT/deploy/compose.production.yml"
ONETREE_BACKUP_ROOT="$ONETREE_ROOT/backups"
ONETREE_DEPLOY_LOCK_FILE="${ONETREE_DEPLOY_LOCK_FILE:-/run/lock/onetree-deploy.lock}"
ONETREE_MAINTENANCE_MARKER="/var/www/certbot/.onetree-maintenance"
ONETREE_UPLOADS_PATH="/var/lib/onetree/knowledge-base-uploads"

deployment_error() {
  printf 'deployment error: %s\n' "$1" >&2
}

require_deployment_command() {
  command -v "$1" >/dev/null 2>&1 || {
    deployment_error "required command is unavailable: $1"
    return 1
  }
}

acquire_deployment_lock() {
  exec 9>"$ONETREE_DEPLOY_LOCK_FILE"
  if ! flock -n 9; then
    deployment_error "another deployment operation holds $ONETREE_DEPLOY_LOCK_FILE"
    return 1
  fi
}

production_env_value() {
  local key="$1"
  local line
  local value=""
  local matches=0

  if [[ ! -r "$ONETREE_ENV_FILE" ]]; then
    deployment_error "production environment file is not readable"
    return 1
  fi

  while IFS= read -r line || [[ -n "$line" ]]; do
    case "$line" in
      "$key="*)
        matches=$((matches + 1))
        value="${line#*=}"
        ;;
    esac
  done < "$ONETREE_ENV_FILE"

  if [[ "$matches" -ne 1 || -z "$value" ]]; then
    deployment_error "production environment must contain one non-empty $key entry"
    return 1
  fi
  printf '%s' "$value"
}

compose() {
  docker compose \
    --env-file "$ONETREE_ENV_FILE" \
    -f "$ONETREE_COMPOSE_FILE" \
    "$@"
}

enter_maintenance() {
  compose exec -T nginx touch "$ONETREE_MAINTENANCE_MARKER"
}

leave_maintenance() {
  compose exec -T nginx rm -f "$ONETREE_MAINTENANCE_MARKER"
}

stop_business_writes() {
  local running_services

  compose stop backend worker
  if ! running_services="$(
    compose ps --status running --services backend worker
  )"; then
    deployment_error "failed to verify backend and worker state"
    return 1
  fi
  if [[ -n "$running_services" ]]; then
    deployment_error "backend or worker is still running"
    return 1
  fi
}

valid_backup_id() {
  [[ "$1" =~ ^[0-9]{8}T[0-9]{6}\.[0-9]{6}Z$ ]]
}

create_deployment_backup() {
  local database_url="$1"
  local target_database_url="$2"
  local backup_id

  if ! backup_id="$(
    DATABASE_URL="$database_url" \
      TARGET_DATABASE_URL="$target_database_url" \
      ONETREE_MAINTENANCE_MODE=1 \
      compose --profile operations run --rm \
      -e DATABASE_URL \
      -e TARGET_DATABASE_URL \
      -e ONETREE_MAINTENANCE_MODE \
      backup
  )"; then
    deployment_error "backup command failed"
    return 1
  fi
  if ! valid_backup_id "$backup_id"; then
    deployment_error "backup did not return one valid backup id"
    return 1
  fi
  if [[ ! -d "$ONETREE_BACKUP_ROOT/$backup_id" ]]; then
    deployment_error "backup directory was not published"
    return 1
  fi
  printf '%s' "$backup_id"
}

restore_deployment_backup() {
  local backup_id="$1"
  local target_database_url="$2"

  TARGET_DATABASE_URL="$target_database_url" \
    ONETREE_MAINTENANCE_MODE=1 \
    compose --profile operations run --rm \
    -e TARGET_DATABASE_URL \
    -e ONETREE_MAINTENANCE_MODE \
    restore "/backups/$backup_id" "$ONETREE_UPLOADS_PATH"
}

run_database_migrations() {
  compose --profile operations run --rm migrate
}

start_production_stack() {
  compose up -d
}

run_production_smoke() {
  compose --profile operations run --rm smoke
}

current_image_id() {
  docker image inspect --format '{{.Id}}' "$1"
}

restore_image_tag() {
  docker image tag "$1" "$2"
}

validate_snapshot_manifest() {
  local backup_id="$1"
  local validation_code
  local snapshot_commit

  validation_code='import sys; from pathlib import Path; sys.path.insert(0, "/opt/onetree/deploy/lib"); from backup_manifest import validate_snapshot_directory; print(validate_snapshot_directory(Path(sys.argv[1]))["git_commit"])'
  if ! snapshot_commit="$(
    compose --profile operations run --rm --no-deps \
      --entrypoint python restore \
      -c "$validation_code" "/backups/$backup_id"
  )"; then
    deployment_error "snapshot manifest validation command failed"
    return 1
  fi
  if [[ ! "$snapshot_commit" =~ ^[0-9a-f]{40}$ ]]; then
    deployment_error "snapshot manifest did not return one Git commit"
    return 1
  fi
  printf '%s' "$snapshot_commit"
}
