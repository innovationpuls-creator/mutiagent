#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CERT_ISSUE="$REPO_ROOT/deploy/bin/cert-issue"
CERT_RENEW="$REPO_ROOT/deploy/bin/cert-renew"
CERT_VERIFY="$REPO_ROOT/deploy/bin/cert-verify"
SERVICE_UNIT="$REPO_ROOT/deploy/systemd/onetree-cert-renew.service"
TIMER_UNIT="$REPO_ROOT/deploy/systemd/onetree-cert-renew.timer"
TMP_DIR="$(mktemp -d)"
STUB_BIN="$TMP_DIR/bin"
COMMAND_LOG="$TMP_DIR/commands.log"
PUBLIC_IPV4="192.0.2.10"
LETSENCRYPT_EMAIL="certificate-test@example.com"
trap 'rm -rf "$TMP_DIR"' EXIT

fail() {
  printf 'certificate script test failed: %s\n' "$1" >&2
  exit 1
}

for required_file in \
  "$CERT_ISSUE" \
  "$CERT_RENEW" \
  "$CERT_VERIFY" \
  "$SERVICE_UNIT" \
  "$TIMER_UNIT"; do
  [[ -f "$required_file" ]] || fail "missing required file: $required_file"
done

for executable in "$CERT_ISSUE" "$CERT_RENEW" "$CERT_VERIFY"; do
  [[ -x "$executable" ]] || fail "script is not executable: $executable"
done

mkdir -p "$STUB_BIN"

cat > "$STUB_BIN/docker" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail

arguments=("$@")
for ((index = 0; index < ${#arguments[@]}; index += 1)); do
  [[ "${arguments[$index]}" == "exec" ]] || continue
  command_index=$((index + 1))
  if [[ "${arguments[$command_index]}" == "-T" ]]; then
    command_index=$((command_index + 1))
  fi
  command_index=$((command_index + 1))
  executable="${arguments[$command_index]}"
  exec "$STUB_BIN/$executable" "${arguments[@]:$((command_index + 1))}"
done

printf 'unexpected docker command:' >&2
printf ' %s' "$@" >&2
printf '\n' >&2
exit 97
STUB

cat > "$STUB_BIN/certbot" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail

printf 'certbot' >> "$COMMAND_LOG"
printf ' %s' "$@" >> "$COMMAND_LOG"
printf '\n' >> "$COMMAND_LOG"

has_argument() {
  local expected="$1"
  shift
  local argument
  for argument in "$@"; do
    [[ "$argument" == "$expected" ]] && return 0
  done
  return 1
}

argument_value() {
  local expected="$1"
  shift
  while (($# > 0)); do
    if [[ "$1" == "$expected" ]]; then
      printf '%s\n' "$2"
      return 0
    fi
    shift
  done
  return 1
}

if [[ "${1:-}" == "--version" ]]; then
  printf 'certbot %s\n' "${CERTBOT_VERSION:-5.4.0}"
  exit 0
fi

if ! has_argument --quiet "$@"; then
  printf 'CERTBOT-SENSITIVE-%s\n' "${LETSENCRYPT_EMAIL:-unset}"
fi

if [[ "${1:-}" == "renew" ]]; then
  [[ "${FAIL_CERTBOT_RENEW:-0}" == "1" ]] && exit 81
  exit 0
fi

if [[ "${1:-}" == "certonly" ]]; then
  cert_name="$(argument_value --cert-name "$@")"
  if has_argument --staging "$@" || has_argument --dry-run "$@"; then
    [[ "${FAIL_CERTBOT_STAGE:-}" == "$cert_name" ]] && exit 82
  fi
  exit 0
fi

exit 83
STUB

cat > "$STUB_BIN/openssl" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail

printf -v command_log_arguments ' %q' "$@"
printf 'openssl%s\n' "$command_log_arguments" >> "$COMMAND_LOG"

has_argument() {
  local expected="$1"
  shift
  local argument
  for argument in "$@"; do
    [[ "$argument" == "$expected" ]] && return 0
  done
  return 1
}

argument_value() {
  local expected="$1"
  shift
  while (($# > 0)); do
    if [[ "$1" == "$expected" ]]; then
      printf '%s\n' "$2"
      return 0
    fi
    shift
  done
  return 1
}

input_path=""
previous=""
for argument in "$@"; do
  if [[ "$previous" == "-in" ]]; then
    input_path="$argument"
    break
  fi
  previous="$argument"
done
cert_name="${input_path#*/live/}"
cert_name="${cert_name%%/*}"

should_fail() {
  local check="$1"
  [[ "${OPENSSL_FAIL_CHECK:-}" == "$check" ]] || return 1
  [[ -z "${OPENSSL_FAIL_CERT_NAME:-}" || "${OPENSSL_FAIL_CERT_NAME}" == "$cert_name" ]]
}

case "${1:-}" in
  verify)
    should_fail chain && exit 84
    ;;
  x509)
    if has_argument -serial "$@"; then
      if [[ -n "$input_path" ]]; then
        printf 'serial=SERIAL-%s\n' "$cert_name"
      else
        read -r online_certificate
        cert_name="${online_certificate#ONLINE-CERT-}"
        if [[ "${OPENSSL_MISMATCH_ONLINE_CERT_NAME:-}" == "$cert_name" ]]; then
          printf 'serial=MISMATCHED-%s\n' "$cert_name"
        else
          printf 'serial=SERIAL-%s\n' "$cert_name"
        fi
      fi
    elif has_argument -checkhost "$@" || has_argument -checkip "$@"; then
      should_fail san && exit 85
    elif has_argument -checkend "$@"; then
      should_fail expiry && exit 86
    elif has_argument -pubkey "$@"; then
      printf 'PUBLIC-KEY-%s\n' "$cert_name"
    fi
    ;;
  s_client)
    if has_argument -servername "$@"; then
      server_name="$(argument_value -servername "$@")"
      [[ "$server_name" == "onetree.chat" ]] || exit 88
      printf 'ONLINE-CERT-onetree-domain\n'
    elif has_argument -noservername "$@"; then
      printf 'ONLINE-CERT-onetree-ip\n'
    else
      exit 89
    fi
    ;;
  pkey)
    if ! has_argument -pubout "$@"; then
      printf 'PRIVATE-KEY-MATERIAL-%s\n' "$cert_name"
    elif should_fail key; then
      printf 'MISMATCHED-PUBLIC-KEY-%s\n' "$cert_name"
    else
      printf 'PUBLIC-KEY-%s\n' "$cert_name"
    fi
    ;;
  *)
    exit 87
    ;;
esac
exit 0
STUB

cat > "$STUB_BIN/nginx" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail

printf 'nginx' >> "$COMMAND_LOG"
printf ' %s' "$@" >> "$COMMAND_LOG"
printf '\n' >> "$COMMAND_LOG"

if [[ "${1:-}" == "-t" ]]; then
  [[ "${FAIL_NGINX_TEST:-0}" == "1" ]] && exit 88
  exit 0
fi
if [[ "${1:-}" == "-s" && "${2:-}" == "reload" ]]; then
  [[ "${FAIL_NGINX_RELOAD:-0}" == "1" ]] && exit 89
  exit 0
fi
exit 90
STUB

chmod 700 "$STUB_BIN/docker" "$STUB_BIN/certbot" "$STUB_BIN/openssl" "$STUB_BIN/nginx"

run_script() {
  env \
    PATH="$STUB_BIN:$PATH" \
    STUB_BIN="$STUB_BIN" \
    COMMAND_LOG="$COMMAND_LOG" \
    PUBLIC_IPV4="$PUBLIC_IPV4" \
    LETSENCRYPT_EMAIL="$LETSENCRYPT_EMAIL" \
    "$@"
}

assert_no_sensitive_output() {
  local output_file="$1"
  python3 - "$output_file" "$LETSENCRYPT_EMAIL" <<'PY'
from pathlib import Path
import sys

output = Path(sys.argv[1]).read_text(encoding="utf-8")
assert sys.argv[2] not in output, output
assert "PRIVATE-KEY-MATERIAL" not in output, output
assert "CERTBOT-SENSITIVE" not in output, output
PY
}

: > "$COMMAND_LOG"
IP_ISSUE_OUTPUT="$TMP_DIR/ip-issue-output.log"
if ! run_script "$CERT_ISSUE" ip > "$IP_ISSUE_OUTPUT" 2>&1; then
  sed -n '1,160p' "$IP_ISSUE_OUTPUT" >&2
  sed -n '1,160p' "$COMMAND_LOG" >&2
  fail "IP certificate issuance failed"
fi
assert_no_sensitive_output "$IP_ISSUE_OUTPUT"

python3 - "$COMMAND_LOG" "$PUBLIC_IPV4" <<'PY'
from pathlib import Path
import shlex
import sys

commands = [
    shlex.split(line)
    for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
]
issuance = [command for command in commands if command[:2] == ["certbot", "certonly"]]
observed = [
    (
        command[command.index("--cert-name") + 1],
        "--staging" in command or "--dry-run" in command,
    )
    for command in issuance
]
assert observed == [
    ("onetree-ip", True),
    ("onetree-ip", False),
], observed
assert all("onetree-domain" not in command for command in commands), commands
assert all("onetree.chat" not in command for command in commands), commands
assert all("www.onetree.chat" not in command for command in commands), commands
ip_commands = [command for command in issuance if "--ip-address" in command]
assert len(ip_commands) == 2, ip_commands
assert all(
    command[command.index("--ip-address") + 1] == sys.argv[2]
    for command in ip_commands
), ip_commands
PY

: > "$COMMAND_LOG"
ISSUE_OUTPUT="$TMP_DIR/issue-output.log"
if ! run_script "$CERT_ISSUE" all > "$ISSUE_OUTPUT" 2>&1; then
  sed -n '1,160p' "$ISSUE_OUTPUT" >&2
  sed -n '1,160p' "$COMMAND_LOG" >&2
  fail "certificate issuance failed"
fi
assert_no_sensitive_output "$ISSUE_OUTPUT"

python3 - "$COMMAND_LOG" "$PUBLIC_IPV4" "$LETSENCRYPT_EMAIL" <<'PY'
from pathlib import Path
import shlex
import sys

lines = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
commands = [shlex.split(line) for line in lines]
assert commands[0] == ["certbot", "--version"], commands

issuance = [command for command in commands if command[:2] == ["certbot", "certonly"]]
assert len(issuance) == 4, issuance

observed = []
for command in issuance:
    cert_name = command[command.index("--cert-name") + 1]
    staging = "--staging" in command or "--dry-run" in command
    assert "--quiet" in command, command
    assert "--non-interactive" in command, command
    assert "--webroot" in command, command
    assert command[command.index("--webroot-path") + 1] == "/var/www/certbot", command
    assert command[command.index("--email") + 1] == sys.argv[3], command
    if staging:
        assert "--staging" in command, command
        assert "--dry-run" in command, command
    if cert_name == "onetree-domain":
        domains = [command[index + 1] for index, value in enumerate(command) if value == "-d"]
        assert domains == ["onetree.chat", "www.onetree.chat"], command
    elif cert_name == "onetree-ip":
        assert command[command.index("--preferred-profile") + 1] == "shortlived", command
        assert command[command.index("--ip-address") + 1] == sys.argv[2], command
        assert "-d" not in command, command
    else:
        raise AssertionError(command)
    observed.append((cert_name, staging))

assert observed == [
    ("onetree-domain", True),
    ("onetree-ip", True),
    ("onetree-domain", False),
    ("onetree-ip", False),
], observed

openssl_commands = [command for command in commands if command and command[0] == "openssl"]
assert any("/live/onetree-domain/" in " ".join(command) for command in openssl_commands)
assert any("/live/onetree-ip/" in " ".join(command) for command in openssl_commands)
certificate_inputs = [
    command[command.index("-in") + 1]
    for command in openssl_commands
    if command[1] == "x509" and "-in" in command
]
assert certificate_inputs, openssl_commands
assert all(path.endswith("/fullchain.pem") for path in certificate_inputs), certificate_inputs
verify_targets = [command[-1] for command in openssl_commands if command[1] == "verify"]
assert verify_targets, openssl_commands
assert all(path.endswith("/fullchain.pem") for path in verify_targets), verify_targets
checkend_values = [
    command[command.index("-checkend") + 1]
    for command in openssl_commands
    if "-checkend" in command
]
assert checkend_values == ["86400", "86400"], checkend_values
assert not any(command and command[0] == "nginx" for command in commands), commands
PY

: > "$COMMAND_LOG"
DEFAULT_ISSUE_OUTPUT="$TMP_DIR/default-issue-output.log"
run_script "$CERT_ISSUE" > "$DEFAULT_ISSUE_OUTPUT" 2>&1
assert_no_sensitive_output "$DEFAULT_ISSUE_OUTPUT"
python3 - "$COMMAND_LOG" <<'PY'
from pathlib import Path
import shlex
import sys

commands = [
    shlex.split(line)
    for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
]
issuance = [command for command in commands if command[:2] == ["certbot", "certonly"]]
observed = [
    (
        command[command.index("--cert-name") + 1],
        "--staging" in command or "--dry-run" in command,
    )
    for command in issuance
]
assert observed == [
    ("onetree-domain", True),
    ("onetree-ip", True),
    ("onetree-domain", False),
    ("onetree-ip", False),
], observed
PY

for failed_stage in onetree-domain onetree-ip; do
  : > "$COMMAND_LOG"
  if run_script FAIL_CERTBOT_STAGE="$failed_stage" "$CERT_ISSUE" >/dev/null 2>&1; then
    fail "$failed_stage staging failure unexpectedly passed"
  fi
  python3 - "$COMMAND_LOG" <<'PY'
from pathlib import Path
import shlex
import sys

commands = [shlex.split(line) for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()]
issuance = [command for command in commands if command[:2] == ["certbot", "certonly"]]
assert issuance, commands
assert all("--staging" in command and "--dry-run" in command for command in issuance), issuance
assert not any(command and command[0] in {"openssl", "nginx"} for command in commands), commands
PY
done

: > "$COMMAND_LOG"
if run_script CERTBOT_VERSION=5.3.99 "$CERT_ISSUE" >/dev/null 2>&1; then
  fail "Certbot 5.3.99 unexpectedly passed"
fi
python3 - "$COMMAND_LOG" <<'PY'
from pathlib import Path
import shlex
import sys

commands = [shlex.split(line) for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()]
assert commands == [["certbot", "--version"]], commands
PY

for failed_check in chain san key expiry; do
  : > "$COMMAND_LOG"
  if run_script NGINX_CONFIG_MODE=production OPENSSL_FAIL_CHECK="$failed_check" \
    "$CERT_RENEW" >/dev/null 2>&1; then
    fail "$failed_check verification failure unexpectedly passed"
  fi
  python3 - "$COMMAND_LOG" <<'PY'
from pathlib import Path
import shlex
import sys

commands = [shlex.split(line) for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()]
assert commands[0][:2] == ["certbot", "renew"], commands
assert not any(command and command[0] == "nginx" for command in commands), commands
PY
done

: > "$COMMAND_LOG"
if run_script NGINX_CONFIG_MODE=production FAIL_CERTBOT_RENEW=1 \
  "$CERT_RENEW" >/dev/null 2>&1; then
  fail "Certbot renewal failure unexpectedly passed"
fi
python3 - "$COMMAND_LOG" <<'PY'
from pathlib import Path
import shlex
import sys

commands = [shlex.split(line) for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()]
assert len(commands) == 1 and commands[0][:2] == ["certbot", "renew"], commands
PY

: > "$COMMAND_LOG"
if run_script NGINX_CONFIG_MODE=production FAIL_NGINX_TEST=1 \
  "$CERT_RENEW" >/dev/null 2>&1; then
  fail "nginx configuration failure unexpectedly passed"
fi
python3 - "$COMMAND_LOG" <<'PY'
from pathlib import Path
import shlex
import sys

commands = [shlex.split(line) for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()]
nginx_commands = [command for command in commands if command and command[0] == "nginx"]
assert nginx_commands == [["nginx", "-t"]], nginx_commands
PY

: > "$COMMAND_LOG"
RENEW_OUTPUT="$TMP_DIR/renew-output.log"
run_script NGINX_CONFIG_MODE=production "$CERT_RENEW" > "$RENEW_OUTPUT" 2>&1
assert_no_sensitive_output "$RENEW_OUTPUT"
python3 - "$COMMAND_LOG" "$PUBLIC_IPV4" <<'PY'
from pathlib import Path
import shlex
import sys

commands = [shlex.split(line) for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()]
assert commands[0][:2] == ["certbot", "renew"], commands
assert "--quiet" in commands[0], commands[0]

openssl_commands = [command for command in commands if command and command[0] == "openssl"]
for cert_name in ("onetree-domain", "onetree-ip"):
    cert_commands = [
        command for command in openssl_commands if f"/live/{cert_name}/" in " ".join(command)
    ]
    assert any(command[1] == "verify" for command in cert_commands), cert_commands
    assert any("-checkend" in command for command in cert_commands), cert_commands
    assert any(command[1] == "pkey" and "-pubout" in command for command in cert_commands), cert_commands
    certificate_inputs = [
        command[command.index("-in") + 1]
        for command in cert_commands
        if command[1] == "x509" and "-in" in command
    ]
    assert certificate_inputs, cert_commands
    assert all(path.endswith("/fullchain.pem") for path in certificate_inputs), certificate_inputs
    checkend_values = [
        command[command.index("-checkend") + 1]
        for command in cert_commands
        if "-checkend" in command
    ]
    assert checkend_values == ["86400"], checkend_values

domain_checks = [
    command[command.index("-checkhost") + 1]
    for command in openssl_commands
    if "-checkhost" in command
]
assert domain_checks == ["onetree.chat", "www.onetree.chat"], domain_checks
ip_checks = [
    command[command.index("-checkip") + 1]
    for command in openssl_commands
    if "-checkip" in command
]
assert ip_checks == [sys.argv[2]], ip_checks

nginx_commands = [command for command in commands if command and command[0] == "nginx"]
assert nginx_commands == [["nginx", "-t"], ["nginx", "-s", "reload"]], nginx_commands
reload_index = commands.index(["nginx", "-s", "reload"])
s_client_commands = [
    command for command in openssl_commands if command[1] == "s_client"
]
assert s_client_commands == [
    ["openssl", "s_client", "-connect", "nginx:443", "-servername", "onetree.chat"],
    ["openssl", "s_client", "-connect", "nginx:443", "-noservername"],
], s_client_commands
assert all(commands.index(command) > reload_index for command in s_client_commands), commands
serial_commands = [command for command in openssl_commands if "-serial" in command]
assert len(serial_commands) == 4, serial_commands
assert all(commands.index(command) > reload_index for command in serial_commands), commands
PY

: > "$COMMAND_LOG"
IP_RENEW_OUTPUT="$TMP_DIR/ip-renew-output.log"
run_script NGINX_CONFIG_MODE=production-ip \
  "$CERT_RENEW" > "$IP_RENEW_OUTPUT" 2>&1
assert_no_sensitive_output "$IP_RENEW_OUTPUT"
python3 - "$COMMAND_LOG" "$PUBLIC_IPV4" <<'PY'
from pathlib import Path
import shlex
import sys

commands = [
    shlex.split(line)
    for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
]
assert commands[0][:2] == ["certbot", "renew"], commands
openssl_commands = [
    command for command in commands if command and command[0] == "openssl"
]
assert all("/live/onetree-domain/" not in " ".join(command) for command in commands), commands
assert not any("-checkhost" in command for command in openssl_commands), commands
ip_checks = [
    command[command.index("-checkip") + 1]
    for command in openssl_commands
    if "-checkip" in command
]
assert ip_checks == [sys.argv[2]], ip_checks
nginx_commands = [command for command in commands if command and command[0] == "nginx"]
assert nginx_commands == [["nginx", "-t"], ["nginx", "-s", "reload"]], nginx_commands
s_client_commands = [
    command for command in openssl_commands if command[1] == "s_client"
]
assert s_client_commands == [
    ["openssl", "s_client", "-connect", "nginx:443", "-noservername"],
], s_client_commands
serial_commands = [command for command in openssl_commands if "-serial" in command]
assert len(serial_commands) == 2, serial_commands
PY

: > "$COMMAND_LOG"
if run_script NGINX_CONFIG_MODE=bootstrap "$CERT_RENEW" >/dev/null 2>&1; then
  fail "bootstrap renewal mode unexpectedly passed"
fi
[[ ! -s "$COMMAND_LOG" ]] || fail "bootstrap renewal mode invoked external commands"

for mismatched_cert_name in onetree-domain onetree-ip; do
  : > "$COMMAND_LOG"
  if run_script NGINX_CONFIG_MODE=production \
    OPENSSL_MISMATCH_ONLINE_CERT_NAME="$mismatched_cert_name" \
    "$CERT_RENEW" >/dev/null 2>&1; then
    fail "$mismatched_cert_name online serial mismatch unexpectedly passed"
  fi
  python3 - "$COMMAND_LOG" <<'PY'
from pathlib import Path
import shlex
import sys

commands = [shlex.split(line) for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()]
reload_index = commands.index(["nginx", "-s", "reload"])
s_client_indexes = [
    index
    for index, command in enumerate(commands)
    if command[:2] == ["openssl", "s_client"]
]
assert s_client_indexes, commands
assert all(index > reload_index for index in s_client_indexes), commands
PY
done

: > "$COMMAND_LOG"
if run_script "$CERT_VERIFY" unknown-certificate >/dev/null 2>&1; then
  fail "unknown certificate name unexpectedly passed"
fi
[[ ! -s "$COMMAND_LOG" ]] || fail "unknown certificate name invoked external commands"

python3 - "$SERVICE_UNIT" "$TIMER_UNIT" "$CERT_ISSUE" "$CERT_RENEW" "$CERT_VERIFY" <<'PY'
from pathlib import Path
import re
import sys

service = Path(sys.argv[1]).read_text(encoding="utf-8")
timer = Path(sys.argv[2]).read_text(encoding="utf-8")

assert re.search(r"(?m)^Type=oneshot$", service), service
assert re.search(r"(?m)^WorkingDirectory=/opt/onetree$", service), service
assert re.search(r"(?m)^EnvironmentFile=/opt/onetree/\.env\.production$", service), service
assert re.search(r"(?m)^ExecStart=/opt/onetree/deploy/bin/cert-renew$", service), service
assert re.search(r"(?m)^OnCalendar=\*-\*-\* 03,15:00:00$", timer), timer
assert re.search(r"(?m)^Persistent=true$", timer), timer
assert re.search(r"(?m)^Unit=onetree-cert-renew\.service$", timer), timer
assert re.search(r"(?m)^WantedBy=timers\.target$", timer), timer

for script_path in sys.argv[3:]:
    script = Path(script_path).read_text(encoding="utf-8")
    assert "set -x" not in script, script_path
    assert not re.search(r"\bcat\b[^\n]*privkey\.pem", script), script_path
PY

printf '%s\n' 'certificate script tests passed'
