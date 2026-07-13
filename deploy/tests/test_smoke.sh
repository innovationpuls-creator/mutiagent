#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SMOKE="$REPO_ROOT/deploy/bin/smoke"
TEMP_DIR="$(mktemp -d)"
FAKE_BIN="$TEMP_DIR/bin"
CURL_LOG="$TEMP_DIR/curl.log"
SMOKE_ACCOUNT="smoke@example.com"
SMOKE_PASSWORD="smoke-password-secret"
SMOKE_TEST_TOKEN="token-for-smoke-test"
MAINTENANCE_BYPASS_TOKEN="maintenance-bypass-secret"
PUBLIC_IPV4="192.0.2.10"
trap 'rm -rf "$TEMP_DIR"' EXIT

if [[ ! -x "$SMOKE" ]]; then
    printf 'smoke executable is missing: %s\n' "$SMOKE" >&2
    exit 1
fi

mkdir -p "$FAKE_BIN"
cat > "$FAKE_BIN/curl" <<'CURL'
#!/usr/bin/env bash
set -euo pipefail

url=""
connect_to=""
data_file=""
head_request=0
write_out=""
header_count=0
declare -a headers

while (( $# > 0 )); do
    case "$1" in
        --connect-to)
            connect_to="$2"
            shift 2
            ;;
        --connect-timeout|--max-time|--output|--request)
            shift 2
            ;;
        --data-binary)
            data_file="${2#@}"
            shift 2
            ;;
        --header)
            headers[header_count]="$2"
            ((header_count += 1))
            shift 2
            ;;
        --head)
            head_request=1
            shift
            ;;
        --write-out)
            write_out="$2"
            shift 2
            ;;
        --fail|--silent|--show-error)
            shift
            ;;
        --insecure|-k)
            printf 'curl must verify TLS certificates\n' >&2
            exit 90
            ;;
        http://*|https://*)
            url="$1"
            shift
            ;;
        *)
            printf 'unexpected curl argument\n' >&2
            exit 91
            ;;
    esac
done

header_file_contains() {
    local expected="$1"
    local header
    local header_file
    local index

    for ((index = 0; index < header_count; index += 1)); do
        header="${headers[index]}"
        [[ "$header" == @* ]] || continue
        header_file="${header#@}"
        [[ -f "$header_file" ]] || exit 105
        if [[ "$(< "$header_file")" == "$expected" ]]; then
            return 0
        fi
    done
    return 1
}

expected_https_connect="${PUBLIC_IPV4}:443:nginx:443"
expected_http_connect="${PUBLIC_IPV4}:80:nginx:80"
if [[ "$url" == https://* ]]; then
    header_file_contains \
        "X-OneTree-Maintenance-Bypass: ${MAINTENANCE_BYPASS_TOKEN}" || exit 106
fi
case "$url" in
    "https://onetree.chat/")
        [[ -z "$connect_to" ]] || exit 108
        if (( head_request == 1 )); then
            printf 'public-domain\n' >> "$CURL_LOG"
            [[ "$FAIL_STEP" != "public-domain" ]] || exit 61
        else
            exit 109
        fi
        ;;
    "https://${PUBLIC_IPV4}/")
        [[ "$connect_to" == "$expected_https_connect" ]] || exit 92
        if (( head_request == 1 )); then
            printf 'tls\n' >> "$CURL_LOG"
            [[ "$FAIL_STEP" != "tls" ]] || exit 60
        else
            printf 'home\n' >> "$CURL_LOG"
            [[ "$FAIL_STEP" != "home" ]] || exit 22
        fi
        ;;
    "http://${PUBLIC_IPV4}/")
        [[ "$connect_to" == "$expected_http_connect" ]] || exit 93
        [[ "$head_request" == 1 ]] || exit 94
        [[ -n "$write_out" ]] || exit 95
        (( header_count == 0 )) || exit 107
        printf 'redirect\n' >> "$CURL_LOG"
        if [[ "$FAIL_STEP" == "redirect" ]]; then
            printf '200\n\n'
        else
            printf '301\nhttps://%s/\n' "$PUBLIC_IPV4"
        fi
        ;;
    "https://${PUBLIC_IPV4}/api/health/live")
        [[ "$connect_to" == "$expected_https_connect" ]] || exit 96
        printf 'live\n' >> "$CURL_LOG"
        if [[ "$FAIL_STEP" == "live" ]]; then
            printf '{"status":"error"}\n'
        else
            printf '{"status":"ok"}\n'
        fi
        ;;
    "https://${PUBLIC_IPV4}/api/health/ready")
        [[ "$connect_to" == "$expected_https_connect" ]] || exit 97
        printf 'ready\n' >> "$CURL_LOG"
        if [[ "$FAIL_STEP" == "ready" ]]; then
            printf '{"status":"ok","database":"unavailable"}\n'
        else
            printf '{"status":"ok","database":"connected"}\n'
        fi
        ;;
    "https://${PUBLIC_IPV4}/api/auth/login")
        [[ "$connect_to" == "$expected_https_connect" ]] || exit 98
        [[ -f "$data_file" ]] || exit 99
        printf 'login\n' >> "$CURL_LOG"
        content_type_found=0
        for ((index = 0; index < header_count; index += 1)); do
            header="${headers[index]}"
            if [[ "$header" == "Content-Type: application/json" ]]; then
                content_type_found=1
            fi
        done
        [[ "$content_type_found" == 1 ]] || exit 100
        python - "$data_file" <<'PY'
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert set(payload) == {"account", "password"}
assert payload["account"] == os.environ["SMOKE_ACCOUNT"]
assert payload["password"] == os.environ["SMOKE_PASSWORD"]
PY
        if [[ "$FAIL_STEP" == "login" ]]; then
            printf '{"token_type":"bearer"}\n'
        else
            printf '{"access_token":"%s","token_type":"bearer"}\n' \
                "$SMOKE_TEST_TOKEN"
        fi
        ;;
    "https://${PUBLIC_IPV4}/api/auth/me")
        [[ "$connect_to" == "$expected_https_connect" ]] || exit 101
        printf 'me\n' >> "$CURL_LOG"
        authorization_found=0
        for ((index = 0; index < header_count; index += 1)); do
            header="${headers[index]}"
            if [[ "$header" == @* ]]; then
                header_file="${header#@}"
                [[ -f "$header_file" ]] || exit 102
                if [[ "$(< "$header_file")" == \
                    "Authorization: Bearer ${SMOKE_TEST_TOKEN}" ]]; then
                    authorization_found=1
                fi
            fi
        done
        [[ "$authorization_found" == 1 ]] || exit 103
        if [[ "$FAIL_STEP" == "me" ]]; then
            printf '{"identifier":"other@example.com"}\n'
        else
            printf '{"identifier":"%s"}\n' "$SMOKE_ACCOUNT"
        fi
        ;;
    *)
        printf 'unexpected URL\n' >&2
        exit 104
        ;;
esac
CURL
chmod +x "$FAKE_BIN/curl"
python3_path="$(command -v python3)"
ln -s "$python3_path" "$FAKE_BIN/python"

run_smoke() {
    local nginx_config_mode="$1"
    local fail_step="$2"
    local expected_status="$3"
    local output
    local status

    : > "$CURL_LOG"
    set +e
    output="$(
        PATH="$FAKE_BIN:$PATH" \
        BASE_URL="https://nginx" \
        NGINX_CONFIG_MODE="$nginx_config_mode" \
        PUBLIC_IPV4="$PUBLIC_IPV4" \
        SMOKE_ACCOUNT="$SMOKE_ACCOUNT" \
        SMOKE_PASSWORD="$SMOKE_PASSWORD" \
        SMOKE_TEST_TOKEN="$SMOKE_TEST_TOKEN" \
        MAINTENANCE_BYPASS_TOKEN="$MAINTENANCE_BYPASS_TOKEN" \
        CURL_LOG="$CURL_LOG" \
        FAIL_STEP="$fail_step" \
        "$SMOKE" 2>&1
    )"
    status=$?
    set -e

    if [[ "$output" == *"$SMOKE_PASSWORD"* ]]; then
        printf 'smoke output leaked the password\n' >&2
        exit 1
    fi
    if [[ "$output" == *"$SMOKE_TEST_TOKEN"* ]]; then
        printf 'smoke output leaked the access token\n' >&2
        exit 1
    fi
    if [[ "$output" == *"$MAINTENANCE_BYPASS_TOKEN"* ]]; then
        printf 'smoke output leaked the maintenance bypass token\n' >&2
        exit 1
    fi

    if [[ "$expected_status" == "zero" && "$status" -ne 0 ]]; then
        printf 'smoke unexpectedly failed: %s\n' "$output" >&2
        exit 1
    fi
    if [[ "$expected_status" == "nonzero" && "$status" -eq 0 ]]; then
        printf 'smoke unexpectedly passed for step: %s\n' "$fail_step" >&2
        exit 1
    fi
}

run_smoke production-ip "" zero
python3 - "$CURL_LOG" <<'PY'
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

calls = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
assert Counter(calls) == Counter(
    ["tls", "redirect", "live", "ready", "home", "login", "me"]
)
PY

run_smoke production "" zero
python3 - "$CURL_LOG" <<'PY'
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

calls = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
assert Counter(calls) == Counter(
    ["public-domain", "tls", "redirect", "live", "ready", "home", "login", "me"]
)
PY

for fail_step in tls redirect live ready home login me; do
    run_smoke production-ip "$fail_step" nonzero
done
run_smoke production public-domain nonzero

run_smoke bootstrap "" nonzero
[[ ! -s "$CURL_LOG" ]] || {
    printf 'invalid smoke mode invoked curl\n' >&2
    exit 1
}

printf 'smoke tests passed\n'
