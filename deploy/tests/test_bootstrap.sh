#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BOOTSTRAP="$REPO_ROOT/deploy/bin/bootstrap"
TEMP_ROOT="$(cd "${TMPDIR:-/tmp}" && pwd -P)"
TEMP_DIR=""

cleanup_temp_dir() {
  if [[ -n "$TEMP_DIR" && "$TEMP_DIR" == "$TEMP_ROOT"/tmp.* ]]; then
    rm -rf -- "$TEMP_DIR"
  fi
}

trap cleanup_temp_dir EXIT
TEMP_DIR="$(mktemp -d "$TEMP_ROOT/tmp.XXXXXXXX")" || {
  printf '%s\n' 'bootstrap test failed: cannot create temporary directory' >&2
  exit 1
}
TEMP_DIR="$(cd "$TEMP_DIR" && pwd -P)"

fail() {
  printf 'bootstrap test failed: %s\n' "$1" >&2
  exit 1
}

[[ -x "$BOOTSTRAP" ]] || fail "missing executable: $BOOTSTRAP"

VALID_OS_RELEASE="$TEMP_DIR/os-release"
cat > "$VALID_OS_RELEASE" <<'EOF'
ID=ubuntu
VERSION_ID="24.04"
VERSION_CODENAME=noble
EOF

run_rejected_platform() {
  local effective_uid="$1"
  local os_release="$2"
  local architecture="$3"
  local case_root="$TEMP_DIR/rejected-$effective_uid-${architecture//\//_}"

  mkdir -p "$case_root/etc"
  : > "$case_root/etc/fstab"
  if env \
    ONETREE_BOOTSTRAP_EUID="$effective_uid" \
    ONETREE_OS_RELEASE_FILE="$os_release" \
    ONETREE_ARCH="$architecture" \
    ONETREE_INSTALL_ROOT="$case_root/opt/onetree" \
    ONETREE_FSTAB_FILE="$case_root/etc/fstab" \
    ONETREE_SWAPFILE="$case_root/swapfile" \
    "$BOOTSTRAP" </dev/null >"$case_root/output.log" 2>&1; then
    fail "invalid platform was accepted"
  fi
  [[ ! -e "$case_root/opt/onetree" ]] || \
    fail "invalid platform modified install root"
  [[ ! -e "$case_root/swapfile" ]] || \
    fail "invalid platform modified swap"
  [[ ! -s "$case_root/etc/fstab" ]] || \
    fail "invalid platform modified fstab"
}

NON_UBUNTU="$TEMP_DIR/non-ubuntu"
cat > "$NON_UBUNTU" <<'EOF'
ID=debian
VERSION_ID="24.04"
VERSION_CODENAME=noble
EOF
WRONG_VERSION="$TEMP_DIR/wrong-version"
cat > "$WRONG_VERSION" <<'EOF'
ID=ubuntu
VERSION_ID="22.04"
VERSION_CODENAME=jammy
EOF

run_rejected_platform 1000 "$VALID_OS_RELEASE" x86_64
run_rejected_platform 0 "$NON_UBUNTU" x86_64
run_rejected_platform 0 "$WRONG_VERSION" x86_64
run_rejected_platform 0 "$VALID_OS_RELEASE" aarch64

EXISTING_ROOT="$TEMP_DIR/existing-install/opt/onetree"
EXISTING_SYSTEM="$TEMP_DIR/existing-install/system"
EXISTING_BIN="$TEMP_DIR/existing-install/bin"
EXISTING_COMMAND_MARKER="$TEMP_DIR/existing-install/system-command-ran"
mkdir -p "$EXISTING_ROOT/bin" "$EXISTING_SYSTEM" "$EXISTING_BIN"
printf 'existing-production-env\n' > "$EXISTING_ROOT/.env.production"
printf '#!/usr/bin/env bash\nexit 0\n' > "$EXISTING_ROOT/bin/deploy"
chmod 755 "$EXISTING_ROOT/bin/deploy"
: > "$EXISTING_SYSTEM/fstab"
cat > "$EXISTING_BIN/apt-get" <<'STUB'
#!/usr/bin/env bash
touch "$EXISTING_COMMAND_MARKER"
exit 99
STUB
chmod 755 "$EXISTING_BIN/apt-get"
if PATH="$EXISTING_BIN:$PATH" \
  EXISTING_COMMAND_MARKER="$EXISTING_COMMAND_MARKER" \
  ONETREE_BOOTSTRAP_EUID=0 \
  ONETREE_OS_RELEASE_FILE="$VALID_OS_RELEASE" \
  ONETREE_ARCH=x86_64 \
  ONETREE_INSTALL_ROOT="$EXISTING_ROOT" \
  ONETREE_FSTAB_FILE="$EXISTING_SYSTEM/fstab" \
  ONETREE_SWAPFILE="$EXISTING_SYSTEM/swapfile" \
  ONETREE_UBUNTU_SOURCE_FILE="$EXISTING_SYSTEM/ubuntu.list" \
  "$BOOTSTRAP" </dev/null > "$EXISTING_SYSTEM/output.log" 2>&1; then
  fail "existing production install was accepted"
fi
grep -q '/opt/onetree/bin/deploy' "$EXISTING_SYSTEM/output.log" || \
  fail "existing install did not direct updates to deploy"
[[ ! -e "$EXISTING_COMMAND_MARKER" ]] || \
  fail "existing install ran a system command before rejection"
[[ ! -e "$EXISTING_SYSTEM/swapfile" ]] || \
  fail "existing install modified swap"
[[ ! -s "$EXISTING_SYSTEM/fstab" ]] || \
  fail "existing install modified fstab"

# shellcheck source=../bin/bootstrap
# shellcheck disable=SC1091
ONETREE_BOOTSTRAP_SOURCE_ONLY=1 source "$BOOTSTRAP"

validate_public_ipv4 "192.0.2.10" || fail "valid IPv4 was rejected"
if validate_public_ipv4 "2001:db8::10"; then
  fail "IPv6 was accepted"
fi
if validate_public_ipv4 "192.0.2.999"; then
  fail "invalid IPv4 was accepted"
fi
if validate_public_ipv4 "192.0.2.10 extra"; then
  fail "non-address content was accepted"
fi
declare -F validate_env_literal_input >/dev/null || \
  fail "shared Compose/systemd env validation is missing"
if validate_env_literal_input SMOKE_PASSWORD "not'representable" 2>/dev/null; then
  fail "single quote was accepted for the shared Compose/systemd env file"
fi
declare -F resolve_bundle_path >/dev/null || \
  fail "bundle path normalization is missing"
BUNDLE_PATH_DIR="$TEMP_DIR/bundle-path"
mkdir -p "$BUNDLE_PATH_DIR"
: > "$BUNDLE_PATH_DIR/migration.tar"
resolved_bundle="$({
  cd "$BUNDLE_PATH_DIR"
  resolve_bundle_path migration.tar
})"
[[ "$resolved_bundle" == "$BUNDLE_PATH_DIR/migration.tar" ]] || \
  fail "relative bundle path was not normalized"
declare -F create_baseline_backup >/dev/null || \
  fail "baseline backup function is missing"
if (
  # shellcheck disable=SC2329
  compose() { return 73; }
  export ONETREE_BACKUP_ROOT="$TEMP_DIR/failed-baseline-backup"
  export DATABASE_URL=postgresql://source
  export TARGET_DATABASE_URL=postgresql://target
  create_baseline_backup
) >/dev/null 2>&1; then
  fail "baseline backup command failure was accepted"
fi
declare -F prepare_partial_retry >/dev/null || \
  fail "partial retry service stop is missing"
if (
  # shellcheck disable=SC2329
  compose() {
    if [[ " $* " == *" ps "* ]]; then
      printf 'backend\n'
    fi
  }
  prepare_partial_retry
) >/dev/null 2>&1; then
  fail "partial retry accepted a running service"
fi

FSTAB_TEST="$TEMP_DIR/fstab"
SWAP_TEST="$TEMP_DIR/swapfile"
cat > "$FSTAB_TEST" <<EOF
UUID=example / ext4 defaults 0 1
$SWAP_TEST none swap sw 0 0
$SWAP_TEST none swap sw 0 0
EOF
ensure_swap_fstab_entry "$FSTAB_TEST" "$SWAP_TEST"
ensure_swap_fstab_entry "$FSTAB_TEST" "$SWAP_TEST"
python3 - "$FSTAB_TEST" "$SWAP_TEST" <<'PY'
from pathlib import Path
import sys

lines = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
assert lines.count(f"{sys.argv[2]} none swap sw 0 0") == 1, lines
assert "UUID=example / ext4 defaults 0 1" in lines, lines
PY

DAEMON_JSON="$TEMP_DIR/daemon.json"
cat > "$DAEMON_JSON" <<'EOF'
{
  "features": {"buildkit": true},
  "log-driver": "journald",
  "registry-mirrors": ["https://existing.example"]
}
EOF
merge_registry_mirror "$DAEMON_JSON" "https://docker.m.daocloud.io"
merge_registry_mirror "$DAEMON_JSON" "https://docker.m.daocloud.io"
python3 - "$DAEMON_JSON" <<'PY'
import json
from pathlib import Path
import sys

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert payload["features"] == {"buildkit": True}, payload
assert payload["log-driver"] == "journald", payload
assert payload["registry-mirrors"] == [
    "https://existing.example",
    "https://docker.m.daocloud.io",
], payload
PY

SYSTEM_ROOT="$TEMP_DIR/system"
INSTALL_ROOT="$SYSTEM_ROOT/opt/onetree"
FAKE_BIN="$TEMP_DIR/bin"
COMMAND_LOG="$TEMP_DIR/commands.log"
STATE_DIR="$TEMP_DIR/state"
ENV_FILE="$INSTALL_ROOT/.env.production"
DOCKER_SOURCE_FILE="$SYSTEM_ROOT/etc/apt/sources.list.d/docker.list"
DOCKER_KEY_FILE="$SYSTEM_ROOT/etc/apt/keyrings/docker.asc"
UBUNTU_SOURCE_FILE="$SYSTEM_ROOT/etc/apt/sources.list.d/onetree-ubuntu.list"
DAEMON_FILE="$SYSTEM_ROOT/etc/docker/daemon.json"
FSTAB_FILE="$SYSTEM_ROOT/etc/fstab"
SWAPFILE="$SYSTEM_ROOT/swapfile"
JOURNALD_FILE="$SYSTEM_ROOT/etc/systemd/journald.conf.d/onetree.conf"
SYSTEMD_DIR="$SYSTEM_ROOT/etc/systemd/system"
BUNDLE_FILE="$TEMP_DIR/onetree-migration.tar"
LLM_API_KEY_INPUT="llm-\$key # secret"
SMOKE_PASSWORD_INPUT="smoke-\$pass # secret"

mkdir -p \
  "$FAKE_BIN" \
  "$STATE_DIR" \
  "$(dirname "$DOCKER_SOURCE_FILE")" \
  "$(dirname "$DOCKER_KEY_FILE")" \
  "$(dirname "$DAEMON_FILE")" \
  "$(dirname "$FSTAB_FILE")" \
  "$(dirname "$JOURNALD_FILE")" \
  "$SYSTEMD_DIR"
: > "$COMMAND_LOG"
: > "$FSTAB_FILE"
: > "$BUNDLE_FILE"
cat > "$DAEMON_FILE" <<'EOF'
{"features":{"containerd-snapshotter":true},"log-driver":"journald"}
EOF

cat > "$FAKE_BIN/apt-get" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
printf 'apt-get' >> "$COMMAND_LOG"
printf ' %q' "$@" >> "$COMMAND_LOG"
printf '\n' >> "$COMMAND_LOG"

operation=""
for argument in "$@"; do
  case "$argument" in
    update|install)
      operation="$argument"
      break
      ;;
  esac
done

if [[ "$operation" == "install" && " $* " == *" ca-certificates "* ]] && \
  [[ ! -e "$STATE_DIR/base-install-failed" ]]; then
  touch "$STATE_DIR/base-install-failed"
  exit 31
fi
if [[ "$operation" == "update" && -f "$DOCKER_SOURCE_FILE" ]] && \
  grep -q 'https://download.docker.com/linux/ubuntu' "$DOCKER_SOURCE_FILE" && \
  [[ ! -e "$STATE_DIR/official-docker-failed" ]]; then
  touch "$STATE_DIR/official-docker-failed"
  exit 32
fi
if [[ "$operation" == "install" && " $* " == *" docker-ce "* ]]; then
  touch "$STATE_DIR/docker-ready"
fi
STUB

cat > "$FAKE_BIN/curl" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
printf 'curl' >> "$COMMAND_LOG"
printf ' %q' "$@" >> "$COMMAND_LOG"
printf '\n' >> "$COMMAND_LOG"

output_file=""
url=""
while (($# > 0)); do
  case "$1" in
    --output|-o)
      output_file="$2"
      shift 2
      ;;
    http://*|https://*)
      url="$1"
      shift
      ;;
    *)
      shift
      ;;
  esac
done

case "$url" in
  http://metadata.tencentyun.com/latest/meta-data/public-ipv4)
    exit 33
    ;;
  https://api.ipify.org)
    printf '203.0.113.10'
    ;;
  https://download.docker.com/linux/ubuntu/gpg|\
  https://mirrors.cloud.tencent.com/docker-ce/linux/ubuntu/gpg)
    [[ -n "$output_file" ]] || exit 34
    printf 'verified-docker-gpg\n' > "$output_file"
    ;;
  *)
    exit 35
    ;;
esac
STUB

cat > "$FAKE_BIN/sha256sum" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
printf '1500c1f56fa9e26b9b8f42452a553675796ade0807cdce11975eb98170b3a570  %s\n' "$1"
STUB

cat > "$FAKE_BIN/docker" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "compose" && "${2:-}" == "version" ]]; then
  [[ -e "$STATE_DIR/docker-ready" ]]
  exit
fi
if [[ "${1:-}" == "info" ]]; then
  [[ -e "$STATE_DIR/docker-daemon-ready" ]]
  exit
fi
[[ -e "$STATE_DIR/docker-daemon-ready" ]] || exit 71

printf 'docker' >> "$COMMAND_LOG"
printf ' %q' "$@" >> "$COMMAND_LOG"
printf '\n' >> "$COMMAND_LOG"

if [[ " $* " == *" build "* ]]; then
  printf 'build-env DEBIAN_MIRROR=%s DEBIAN_SECURITY_MIRROR=%s PGDG_KEY_URL=%s PGDG_REPOSITORY=%q PYTHON_PACKAGE_INDEX=%s NPM_REGISTRY=%s UV_HTTP_TIMEOUT=%s\n' \
    "${DEBIAN_MIRROR:-}" \
    "${DEBIAN_SECURITY_MIRROR:-}" \
    "${PGDG_KEY_URL:-}" \
    "${PGDG_REPOSITORY:-}" \
    "${PYTHON_PACKAGE_INDEX:-}" \
    "${NPM_REGISTRY:-}" \
    "${UV_HTTP_TIMEOUT:-}" >> "$COMMAND_LOG"
  if [[ ! -e "$STATE_DIR/first-build-failed" ]]; then
    touch "$STATE_DIR/first-build-failed"
    exit 41
  fi
fi

if [[ " $* " == *" backup "* ]]; then
  backup_id=20260714T010203.123456Z
  mkdir -p "$INSTALL_ROOT/backups/$backup_id"
  printf '%s\n' "$backup_id"
fi

if [[ " $* " == *" up -d "* && " $* " == *" nginx "* ]]; then
  if [[ " $* " == *" --force-recreate "* ]]; then
    grep -qx 'NGINX_CONFIG_MODE=production-ip' "$ENV_FILE" || exit 42
  else
    grep -qx 'NGINX_CONFIG_MODE=bootstrap' "$ENV_FILE" || exit 43
  fi
fi
STUB

cat > "$FAKE_BIN/git" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
printf 'git' >> "$COMMAND_LOG"
printf ' %q' "$@" >> "$COMMAND_LOG"
printf '\n' >> "$COMMAND_LOG"

if [[ "${1:-}" == "-C" && "${3:-}" == "remote" && \
  "${4:-}" == "get-url" && "${5:-}" == "origin" ]]; then
  printf '%s\n' 'https://github.com/innovationpuls-creator/mutiagent.git'
  exit 0
fi
if [[ "${1:-}" == "clone" ]]; then
  destination="${@: -1}"
  mkdir -p \
    "$destination/.git" \
    "$destination/deploy/bin" \
    "$destination/deploy/systemd"
  : > "$destination/deploy/compose.production.yml"
  cat > "$destination/deploy/bin/cert-issue" <<'CERT'
#!/usr/bin/env bash
set -euo pipefail
printf 'cert-issue' >> "$COMMAND_LOG"
printf ' %q' "$@" >> "$COMMAND_LOG"
printf '\n' >> "$COMMAND_LOG"
CERT
  cat > "$destination/deploy/bin/deploy" <<'DEPLOY'
#!/usr/bin/env bash
exit 0
DEPLOY
  cat > "$destination/deploy/bin/rollback" <<'ROLLBACK'
#!/usr/bin/env bash
exit 0
ROLLBACK
  chmod 755 \
    "$destination/deploy/bin/cert-issue" \
    "$destination/deploy/bin/deploy" \
    "$destination/deploy/bin/rollback"
  printf '[Unit]\nDescription=test renewal\n' \
    > "$destination/deploy/systemd/onetree-cert-renew.service"
  printf '[Timer]\nOnCalendar=*-*-* 03,15:00:00\n' \
    > "$destination/deploy/systemd/onetree-cert-renew.timer"
fi
STUB

cat > "$FAKE_BIN/openssl" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
[[ "${1:-}" == "rand" && "${2:-}" == "-hex" ]] || exit 51
count=0
[[ ! -f "$STATE_DIR/openssl-count" ]] || count="$(< "$STATE_DIR/openssl-count")"
count=$((count + 1))
printf '%s\n' "$count" > "$STATE_DIR/openssl-count"
printf '%064x\n' "$count"
STUB

cat > "$FAKE_BIN/fallocate" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
printf 'fallocate' >> "$COMMAND_LOG"
printf ' %q' "$@" >> "$COMMAND_LOG"
printf '\n' >> "$COMMAND_LOG"
[[ "$1" == "-l" ]]
python3 - "$2" "$3" <<'PY'
from pathlib import Path
import sys

with Path(sys.argv[2]).open("wb") as handle:
    handle.truncate(int(sys.argv[1]))
PY
STUB

cat > "$FAKE_BIN/stat" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
[[ "$1" == "-c" && "$2" == "%s" ]]
python3 - "$3" <<'PY'
from pathlib import Path
import sys

print(Path(sys.argv[1]).stat().st_size)
PY
STUB

cat > "$FAKE_BIN/mkswap" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
printf 'mkswap %q\n' "$1" >> "$COMMAND_LOG"
STUB

cat > "$FAKE_BIN/swapon" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "--show=NAME" ]]; then
  [[ ! -f "$STATE_DIR/swap-active" ]] || cat "$STATE_DIR/swap-active"
  exit 0
fi
printf 'swapon %q\n' "$1" >> "$COMMAND_LOG"
printf '%s\n' "$1" > "$STATE_DIR/swap-active"
STUB

cat > "$FAKE_BIN/swapoff" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
printf 'swapoff %q\n' "$1" >> "$COMMAND_LOG"
rm -f "$STATE_DIR/swap-active"
STUB

for command_name in ufw systemctl systemd-tmpfiles; do
  cat > "$FAKE_BIN/$command_name" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
printf '%s' "$(basename "$0")" >> "$COMMAND_LOG"
printf ' %q' "$@" >> "$COMMAND_LOG"
printf '\n' >> "$COMMAND_LOG"
if [[ "$(basename "$0")" == "systemctl" ]]; then
  if [[ " $* " == *" enable --now docker "* || \
    " $* " == *" restart docker "* ]]; then
    touch "$STATE_DIR/docker-daemon-ready"
  fi
fi
STUB
done

chmod 755 "$FAKE_BIN"/*

PREINSTALLED_STATE_DIR="$TEMP_DIR/preinstalled-docker-state"
PREINSTALLED_COMMAND_LOG="$TEMP_DIR/preinstalled-docker.log"
mkdir -p "$PREINSTALLED_STATE_DIR"
: > "$PREINSTALLED_COMMAND_LOG"
touch "$PREINSTALLED_STATE_DIR/docker-ready"
if ! PATH="$FAKE_BIN:$PATH" \
  COMMAND_LOG="$PREINSTALLED_COMMAND_LOG" \
  STATE_DIR="$PREINSTALLED_STATE_DIR" \
  install_docker_engine; then
  fail "preinstalled Docker CLI was not recovered"
fi
[[ -e "$PREINSTALLED_STATE_DIR/docker-daemon-ready" ]] || \
  fail "preinstalled Docker daemon was not started"
grep -qx 'systemctl enable --now docker' "$PREINSTALLED_COMMAND_LOG" || \
  fail "preinstalled Docker was not enabled at boot"

OUTPUT_FILE="$TEMP_DIR/bootstrap-output.log"
if ! printf '%s\n' \
  "$LLM_API_KEY_INPUT" \
  'qwen3.5-plus' \
  'ops@example.com' \
  "$BUNDLE_FILE" \
  '18771701100' \
  "$SMOKE_PASSWORD_INPUT" | env \
    PATH="$FAKE_BIN:$PATH" \
    COMMAND_LOG="$COMMAND_LOG" \
    STATE_DIR="$STATE_DIR" \
    REPO_ROOT="$REPO_ROOT" \
    INSTALL_ROOT="$INSTALL_ROOT" \
    ENV_FILE="$ENV_FILE" \
    DOCKER_SOURCE_FILE="$DOCKER_SOURCE_FILE" \
    ONETREE_BOOTSTRAP_EUID=0 \
    ONETREE_OS_RELEASE_FILE="$VALID_OS_RELEASE" \
    ONETREE_ARCH=x86_64 \
    ONETREE_INSTALL_ROOT="$INSTALL_ROOT" \
    ONETREE_FSTAB_FILE="$FSTAB_FILE" \
    ONETREE_SWAPFILE="$SWAPFILE" \
    ONETREE_UBUNTU_SOURCE_FILE="$UBUNTU_SOURCE_FILE" \
    ONETREE_DOCKER_SOURCE_FILE="$DOCKER_SOURCE_FILE" \
    ONETREE_DOCKER_KEY_FILE="$DOCKER_KEY_FILE" \
    ONETREE_DOCKER_DAEMON_FILE="$DAEMON_FILE" \
    ONETREE_JOURNALD_DROPIN_FILE="$JOURNALD_FILE" \
    ONETREE_SYSTEMD_UNIT_DIR="$SYSTEMD_DIR" \
    "$BOOTSTRAP" > "$OUTPUT_FILE" 2>&1; then
  sed -n '1,200p' "$OUTPUT_FILE" >&2
  sed -n '1,240p' "$COMMAND_LOG" >&2
  fail "mocked bootstrap failed"
fi

python3 - \
  "$ENV_FILE" \
  "$OUTPUT_FILE" \
  "$LLM_API_KEY_INPUT" \
  "$SMOKE_PASSWORD_INPUT" <<'PY'
from pathlib import Path
import os
import stat
import sys

env_path = Path(sys.argv[1])
output = Path(sys.argv[2]).read_text(encoding="utf-8")
assert stat.S_IMODE(env_path.stat().st_mode) == 0o600

entries = {}
raw_entries = {}
for line in env_path.read_text(encoding="utf-8").splitlines():
    key, value = line.split("=", maxsplit=1)
    assert key not in entries, key
    assert value, key
    raw_entries[key] = value
    if value.startswith("'"):
        assert value.endswith("'"), (key, value)
        value = value[1:-1].replace("\\'", "'")
    entries[key] = value

expected_keys = {
    "APP_ENV",
    "POSTGRES_MAINTENANCE_PASSWORD",
    "POSTGRES_APP_PASSWORD",
    "DATABASE_URL",
    "TARGET_DATABASE_URL",
    "JWT_SECRET",
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "LLM_MODEL",
    "ALLOWED_ORIGINS",
    "PUBLIC_IPV4",
    "MAINTENANCE_BYPASS_TOKEN",
    "NGINX_CONFIG_MODE",
    "VITE_ICP_BEIAN_NUMBER",
    "LETSENCRYPT_EMAIL",
    "SMOKE_ACCOUNT",
    "SMOKE_PASSWORD",
    "DEBIAN_MIRROR",
    "DEBIAN_SECURITY_MIRROR",
    "PGDG_KEY_URL",
    "PGDG_REPOSITORY",
    "PYTHON_PACKAGE_INDEX",
    "NPM_REGISTRY",
    "UV_HTTP_TIMEOUT",
}
assert set(entries) == expected_keys, entries
assert entries["APP_ENV"] == "production"
assert entries["LLM_BASE_URL"] == (
    "https://dashscope.aliyuncs.com/compatible-mode/v1"
)
assert entries["PUBLIC_IPV4"] == "203.0.113.10"
assert entries["ALLOWED_ORIGINS"] == (
    "https://onetree.chat,https://www.onetree.chat,https://203.0.113.10"
)
assert entries["NGINX_CONFIG_MODE"] == "production-ip"
assert entries["VITE_ICP_BEIAN_NUMBER"] == "粤ICP备2026100568号-1"
assert entries["LLM_API_KEY"] == sys.argv[3]
assert entries["LLM_MODEL"] == "qwen3.5-plus"
assert entries["LETSENCRYPT_EMAIL"] == "ops@example.com"
assert entries["SMOKE_ACCOUNT"] == "18771701100"
assert entries["SMOKE_PASSWORD"] == sys.argv[4]
assert raw_entries["LLM_API_KEY"].startswith("'")
assert raw_entries["SMOKE_PASSWORD"].startswith("'")
assert entries["DEBIAN_MIRROR"] == "https://mirrors.cloud.tencent.com/debian"
assert entries["DEBIAN_SECURITY_MIRROR"] == (
    "https://mirrors.cloud.tencent.com/debian-security"
)
assert entries["PGDG_KEY_URL"] == (
    "https://mirrors.cloud.tencent.com/postgresql/repos/apt/ACCC4CF8.asc"
)
assert entries["PGDG_REPOSITORY"] == (
    "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] "
    "https://mirrors.cloud.tencent.com/postgresql/repos/apt bookworm-pgdg main"
)
assert entries["PYTHON_PACKAGE_INDEX"] == (
    "https://mirrors.cloud.tencent.com/pypi/simple/"
)
assert entries["NPM_REGISTRY"] == "https://mirrors.cloud.tencent.com/npm/"
assert entries["UV_HTTP_TIMEOUT"] == "300"
assert raw_entries["PGDG_REPOSITORY"] == entries["PGDG_REPOSITORY"]

generated_keys = (
    "POSTGRES_MAINTENANCE_PASSWORD",
    "POSTGRES_APP_PASSWORD",
    "JWT_SECRET",
    "MAINTENANCE_BYPASS_TOKEN",
)
generated_values = [entries[key] for key in generated_keys]
assert len(set(generated_values)) == len(generated_values)
assert all(len(value) == 64 for value in generated_values)
assert all(set(value) <= set("0123456789abcdef") for value in generated_values)
assert entries["DATABASE_URL"] == (
    "postgresql://onetree_app:"
    f"{entries['POSTGRES_APP_PASSWORD']}@postgres:5432/onetree"
)
assert entries["TARGET_DATABASE_URL"] == (
    "postgresql://onetree_maintenance:"
    f"{entries['POSTGRES_MAINTENANCE_PASSWORD']}@postgres:5432/onetree"
)

for secret in (
    entries["LLM_API_KEY"],
    entries["SMOKE_PASSWORD"],
    *generated_values,
):
    assert secret not in output
assert "https://203.0.113.10" in output
assert "https://onetree.chat\n" not in output
assert "https://www.onetree.chat\n" not in output
PY

COMPOSE_CONFIG="$TEMP_DIR/compose-config.json"
COMPOSE_ENVIRONMENT="$TEMP_DIR/compose-environment.txt"
docker compose \
  --profile operations \
  --env-file "$ENV_FILE" \
  -f "$REPO_ROOT/deploy/compose.production.yml" \
  config --format json > "$COMPOSE_CONFIG"
docker compose \
  --env-file "$ENV_FILE" \
  -f "$REPO_ROOT/deploy/compose.production.yml" \
  config --environment > "$COMPOSE_ENVIRONMENT"
python3 - \
  "$COMPOSE_CONFIG" \
  "$COMPOSE_ENVIRONMENT" \
  "$LLM_API_KEY_INPUT" \
  "$SMOKE_PASSWORD_INPUT" <<'PY'
import json
from pathlib import Path
import sys

services = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["services"]
compose_environment = {}
for line in Path(sys.argv[2]).read_text(encoding="utf-8").splitlines():
    key, separator, value = line.partition("=")
    if separator:
        compose_environment[key] = value
assert compose_environment["LLM_API_KEY"] == sys.argv[3]
assert compose_environment["SMOKE_PASSWORD"] == sys.argv[4]
build_args = services["backend"]["build"]["args"]
assert build_args["DEBIAN_MIRROR"] == "https://mirrors.cloud.tencent.com/debian"
assert build_args["DEBIAN_SECURITY_MIRROR"] == (
    "https://mirrors.cloud.tencent.com/debian-security"
)
assert build_args["PGDG_REPOSITORY"] == (
    "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] "
    "https://mirrors.cloud.tencent.com/postgresql/repos/apt bookworm-pgdg main"
)
assert build_args["PYTHON_PACKAGE_INDEX"] == (
    "https://mirrors.cloud.tencent.com/pypi/simple/"
)
assert services["nginx"]["build"]["args"]["NPM_REGISTRY"] == (
    "https://mirrors.cloud.tencent.com/npm/"
)
assert services["nginx"]["build"]["args"]["VITE_ICP_BEIAN_NUMBER"] == (
    "粤ICP备2026100568号-1"
)
PY

python3 - \
  "$COMMAND_LOG" \
  "$FSTAB_FILE" \
  "$SWAPFILE" \
  "$UBUNTU_SOURCE_FILE" \
  "$DOCKER_SOURCE_FILE" \
  "$DAEMON_FILE" \
  "$JOURNALD_FILE" \
  "$ENV_FILE" \
  "$BUNDLE_FILE" <<'PY'
import json
from pathlib import Path
import shlex
import sys

(
    log_path,
    fstab_path,
    swap_path,
    ubuntu_source_path,
    docker_source_path,
    daemon_path,
    journald_path,
    env_path,
    bundle_path,
) = map(Path, sys.argv[1:])
lines = log_path.read_text(encoding="utf-8").splitlines()

metadata = next(
    index
    for index, line in enumerate(lines)
    if "http://metadata.tencentyun.com/latest/meta-data/public-ipv4" in line
)
ipify = next(
    index for index, line in enumerate(lines) if "https://api.ipify.org" in line
)
swap = next(index for index, line in enumerate(lines) if line.startswith("mkswap "))
ufw = next(index for index, line in enumerate(lines) if line.startswith("ufw "))
clone = next(index for index, line in enumerate(lines) if line.startswith("git clone "))
assert metadata < ipify < swap < ufw < clone, lines

for line in (lines[metadata], lines[ipify]):
    command = shlex.split(line)
    assert command[:2] == ["curl", "-4fsS"], command
    assert command[command.index("--connect-timeout") + 1] == "2", command
    assert command[command.index("--max-time") + 1] == "5", command

git_clone = shlex.split(lines[clone])
assert git_clone == [
    "git",
    "clone",
    "--branch",
    "main",
    "--single-branch",
    "https://github.com/innovationpuls-creator/mutiagent.git",
    str(env_path.parent),
], git_clone

ufw_commands = [shlex.split(line) for line in lines if line.startswith("ufw ")]
assert ufw_commands == [
    ["ufw", "--force", "reset"],
    ["ufw", "default", "deny", "incoming"],
    ["ufw", "default", "allow", "outgoing"],
    ["ufw", "allow", "80/tcp"],
    ["ufw", "allow", "443/tcp"],
    ["ufw", "--force", "enable"],
], ufw_commands

fstab_lines = fstab_path.read_text(encoding="utf-8").splitlines()
assert fstab_lines.count(f"{swap_path} none swap sw 0 0") == 1, fstab_lines
assert swap_path.stat().st_size == 4 * 1024 * 1024 * 1024

assert "https://mirrors.cloud.tencent.com/ubuntu/" in ubuntu_source_path.read_text(
    encoding="utf-8"
)
docker_source = docker_source_path.read_text(encoding="utf-8")
assert "https://mirrors.cloud.tencent.com/docker-ce/linux/ubuntu" in docker_source
assert "https://download.docker.com/linux/ubuntu" not in docker_source

gpg_urls = [
    line
    for line in lines
    if line.startswith("curl ") and line.endswith("/gpg") is False
]
full_log = "\n".join(lines)
assert "https://download.docker.com/linux/ubuntu/gpg" in full_log
assert "https://mirrors.cloud.tencent.com/docker-ce/linux/ubuntu/gpg" in full_log

daemon = json.loads(daemon_path.read_text(encoding="utf-8"))
assert daemon["features"] == {"containerd-snapshotter": True}, daemon
assert daemon["log-driver"] == "journald", daemon
assert daemon["registry-mirrors"] == ["https://docker.m.daocloud.io"], daemon

expected_build_env = (
    "build-env "
    "DEBIAN_MIRROR=https://mirrors.cloud.tencent.com/debian "
    "DEBIAN_SECURITY_MIRROR=https://mirrors.cloud.tencent.com/debian-security "
    "PGDG_KEY_URL=https://mirrors.cloud.tencent.com/postgresql/repos/apt/ACCC4CF8.asc "
)
assert any(line.startswith(expected_build_env) for line in lines), lines
assert "PYTHON_PACKAGE_INDEX=https://mirrors.cloud.tencent.com/pypi/simple/" in full_log
assert "NPM_REGISTRY=https://mirrors.cloud.tencent.com/npm/" in full_log
assert "UV_HTTP_TIMEOUT=300" in full_log
assert "https://mirrors.cloud.tencent.com/postgresql/repos/apt" in full_log

compose_lines = [line for line in lines if line.startswith("docker compose ")]
assert compose_lines, lines
for line in compose_lines:
    command = shlex.split(line)
    assert command[command.index("--env-file") + 1] == str(env_path), command
    compose_file = env_path.parent / "deploy/compose.production.yml"
    assert command[command.index("-f") + 1] == str(compose_file), command

def command_index(*parts: str) -> int:
    matches = [
        index for index, line in enumerate(lines) if all(part in line for part in parts)
    ]
    assert matches, (parts, lines)
    return matches[0]

backend_build = command_index("docker compose", " build backend")
postgres_up = command_index("docker compose", " up -d --wait postgres")
bundle_import = command_index(
    "docker compose",
    "--entrypoint /opt/onetree/deploy/bin/import-bundle",
    str(bundle_path),
    "/var/lib/onetree/knowledge-base-uploads",
)
baseline_backup = command_index(
    "docker compose", " --profile operations run --rm", " backup"
)
full_build_matches = [
    index
    for index, line in enumerate(lines)
    if line.startswith("docker compose ") and line.endswith(" build")
]
assert len(full_build_matches) == 1, full_build_matches
full_build = full_build_matches[0]
migrate = command_index(
    "docker compose", " --profile operations run --rm migrate"
)
bootstrap_nginx = command_index(
    "docker compose", " up -d --wait postgres backend worker certbot nginx"
)
cert_issue = command_index("cert-issue ip")
production_nginx = command_index(
    "docker compose", " up -d --wait --force-recreate nginx"
)
smoke = command_index(
    "docker compose", " --profile operations run --rm smoke"
)
timer = command_index("systemctl enable --now onetree-cert-renew.timer")
assert (
    backend_build
    < postgres_up
    < bundle_import
    < migrate
    < baseline_backup
    < full_build
    < bootstrap_nginx
    < cert_issue
    < production_nginx
    < smoke
    < timer
), lines

import_command = shlex.split(lines[bundle_import])
assert "--user" in import_command
assert import_command[import_command.index("--user") + 1] == "0:0"
for key in (
    "TARGET_DATABASE_URL",
    "ONETREE_MAINTENANCE_MODE",
    "UPLOADS_OWNER_UID",
    "UPLOADS_OWNER_GID",
):
    assert key in import_command, import_command

backup_command = shlex.split(lines[baseline_backup])
for key in ("DATABASE_URL", "TARGET_DATABASE_URL", "ONETREE_MAINTENANCE_MODE"):
    assert key in backup_command, backup_command

journald = journald_path.read_text(encoding="utf-8")
assert journald == (
    "[Journal]\n"
    "Storage=persistent\n"
    "MaxRetentionSec=7day\n"
    "SystemMaxUse=2G\n"
)
assert "systemctl restart docker" in full_log
assert "systemctl restart systemd-journald" in full_log
tmpfiles_index = command_index(
    "systemd-tmpfiles --create --prefix /var/log/journal"
)
journal_restart_index = command_index("systemctl restart systemd-journald")
assert tmpfiles_index < journal_restart_index < swap, lines
PY

[[ -f "$SYSTEMD_DIR/onetree-cert-renew.service" ]] || \
  fail "renewal service was not installed"
[[ -f "$SYSTEMD_DIR/onetree-cert-renew.timer" ]] || \
  fail "renewal timer was not installed"
[[ -L "$INSTALL_ROOT/bin/deploy" ]] || fail "deploy command is not a symlink"
[[ -L "$INSTALL_ROOT/bin/rollback" ]] || fail "rollback command is not a symlink"
[[ "$(readlink "$INSTALL_ROOT/bin/deploy")" == \
  "$INSTALL_ROOT/deploy/bin/deploy" ]] || fail "deploy symlink target"
[[ "$(readlink "$INSTALL_ROOT/bin/rollback")" == \
  "$INSTALL_ROOT/deploy/bin/rollback" ]] || fail "rollback symlink target"

PARTIAL_SECRETS_BEFORE="$TEMP_DIR/partial-secrets-before.json"
python3 - "$ENV_FILE" "$PARTIAL_SECRETS_BEFORE" <<'PY'
import json
from pathlib import Path
import sys

entries = dict(
    line.split("=", maxsplit=1)
    for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
)
keys = (
    "POSTGRES_MAINTENANCE_PASSWORD",
    "POSTGRES_APP_PASSWORD",
    "JWT_SECRET",
    "MAINTENANCE_BYPASS_TOKEN",
)
Path(sys.argv[2]).write_text(
    json.dumps({key: entries[key] for key in keys}, sort_keys=True),
    encoding="utf-8",
)
PY
OPENSSL_COUNT_BEFORE="$(< "$STATE_DIR/openssl-count")"
PARTIAL_COMMAND_LOG="$TEMP_DIR/partial-commands.log"
PARTIAL_OUTPUT_FILE="$TEMP_DIR/partial-output.log"
: > "$PARTIAL_COMMAND_LOG"
rm -f "$INSTALL_ROOT/bin/deploy"
if ! printf '%s\n' \
  "$LLM_API_KEY_INPUT" \
  'qwen3.5-plus' \
  'ops@example.com' \
  "$BUNDLE_FILE" \
  '18771701100' \
  "$SMOKE_PASSWORD_INPUT" | env \
    PATH="$FAKE_BIN:$PATH" \
    COMMAND_LOG="$PARTIAL_COMMAND_LOG" \
    STATE_DIR="$STATE_DIR" \
    REPO_ROOT="$REPO_ROOT" \
    INSTALL_ROOT="$INSTALL_ROOT" \
    ENV_FILE="$ENV_FILE" \
    DOCKER_SOURCE_FILE="$DOCKER_SOURCE_FILE" \
    ONETREE_BOOTSTRAP_EUID=0 \
    ONETREE_OS_RELEASE_FILE="$VALID_OS_RELEASE" \
    ONETREE_ARCH=x86_64 \
    ONETREE_INSTALL_ROOT="$INSTALL_ROOT" \
    ONETREE_FSTAB_FILE="$FSTAB_FILE" \
    ONETREE_SWAPFILE="$SWAPFILE" \
    ONETREE_UBUNTU_SOURCE_FILE="$UBUNTU_SOURCE_FILE" \
    ONETREE_DOCKER_SOURCE_FILE="$DOCKER_SOURCE_FILE" \
    ONETREE_DOCKER_KEY_FILE="$DOCKER_KEY_FILE" \
    ONETREE_DOCKER_DAEMON_FILE="$DAEMON_FILE" \
    ONETREE_JOURNALD_DROPIN_FILE="$JOURNALD_FILE" \
    ONETREE_SYSTEMD_UNIT_DIR="$SYSTEMD_DIR" \
    "$BOOTSTRAP" > "$PARTIAL_OUTPUT_FILE" 2>&1; then
  sed -n '1,200p' "$PARTIAL_OUTPUT_FILE" >&2
  sed -n '1,240p' "$PARTIAL_COMMAND_LOG" >&2
  fail "partial bootstrap retry failed"
fi
[[ "$(< "$STATE_DIR/openssl-count")" == "$OPENSSL_COUNT_BEFORE" ]] || \
  fail "partial retry regenerated automatic secrets"
python3 - "$ENV_FILE" "$PARTIAL_SECRETS_BEFORE" <<'PY'
import json
from pathlib import Path
import sys

entries = dict(
    line.split("=", maxsplit=1)
    for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
)
expected = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
assert {key: entries[key] for key in expected} == expected
for key in (
    "DEBIAN_MIRROR",
    "DEBIAN_SECURITY_MIRROR",
    "PGDG_KEY_URL",
    "PGDG_REPOSITORY",
    "PYTHON_PACKAGE_INDEX",
    "NPM_REGISTRY",
    "UV_HTTP_TIMEOUT",
):
    assert key in entries, key
PY
python3 - "$PARTIAL_COMMAND_LOG" <<'PY'
from pathlib import Path
import sys

lines = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
stop = next(
    index
    for index, line in enumerate(lines)
    if " stop backend worker nginx certbot" in line
)
verify = next(
    index
    for index, line in enumerate(lines)
    if " ps --status running --services backend worker nginx certbot" in line
)
bundle_import = next(
    index
    for index, line in enumerate(lines)
    if "--entrypoint /opt/onetree/deploy/bin/import-bundle" in line
)
assert stop < verify < bundle_import, lines
PY
[[ -x "$INSTALL_ROOT/bin/deploy" ]] || \
  fail "partial retry did not create the completion marker"

python3 - "$BOOTSTRAP" <<'PY'
from pathlib import Path
import re
import sys

script = Path(sys.argv[1]).read_text(encoding="utf-8")
assert "set -x" not in script
assert "down -v" not in script
assert re.search(r"read\s+-r\s+-s[^\n]*LLM_API_KEY", script), script
assert re.search(r"read\s+-r\s+-s[^\n]*SMOKE_PASSWORD", script), script
interactive_fields = re.findall(
    r"(?m)^\s*IFS= read -r(?: -s)? "
    r"(LLM_API_KEY|LLM_MODEL|LETSENCRYPT_EMAIL|BUNDLE_PATH|SMOKE_ACCOUNT|SMOKE_PASSWORD)$",
    script,
)
assert interactive_fields == [
    "LLM_API_KEY",
    "LLM_MODEL",
    "LETSENCRYPT_EMAIL",
    "BUNDLE_PATH",
    "SMOKE_ACCOUNT",
    "SMOKE_PASSWORD",
], interactive_fields
image_retry_calls = re.findall(
    r"(?m)^\s*run_image_step compose ([^\n]+)$",
    script,
)
assert image_retry_calls, script
assert all(call.startswith(("pull ", "build")) for call in image_retry_calls), (
    image_retry_calls
)
assert any(call.startswith("pull ") for call in image_retry_calls), image_retry_calls
assert any(call.startswith("build") for call in image_retry_calls), image_retry_calls
operations_match = re.search(
    r"(?ms)^install_operations\(\) \{\n(?P<body>.*?)^\}",
    script,
)
assert operations_match is not None, script
operations_body = operations_match.group("body")
timer_enable = operations_body.index(
    "systemctl enable --now onetree-cert-renew.timer"
)
rollback_link = operations_body.index("$ONETREE_INSTALL_ROOT/bin/rollback")
deploy_temporary = operations_body.index("temporary_deploy_link=")
deploy_replace = operations_body.rindex("mv -f")
assert timer_enable < rollback_link < deploy_temporary < deploy_replace, operations_body
assert operations_body.rstrip().endswith(
    'mv -f "$temporary_deploy_link" "$ONETREE_INSTALL_ROOT/bin/deploy"'
), operations_body
main_match = re.search(r"(?ms)^main\(\) \{\n(?P<body>.*?)^\}", script)
assert main_match is not None, script
main_body = main_match.group("body")
assert main_body.index("prepare_partial_retry") < main_body.index("collect_inputs")
assert main_body.index("collect_inputs") < main_body.index("import_migration_bundle")
PY

printf '%s\n' 'bootstrap tests passed'
