#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
NGINX_DIR="$REPO_ROOT/deploy/nginx"
NGINX_CONF="$NGINX_DIR/nginx.conf"
BOOTSTRAP_TEMPLATE="$NGINX_DIR/conf.d/bootstrap.conf.template"
PRODUCTION_IP_TEMPLATE="$NGINX_DIR/conf.d/production-ip.conf.template"
PRODUCTION_TEMPLATE="$NGINX_DIR/conf.d/production.conf.template"
MAINTENANCE_PAGE="$NGINX_DIR/maintenance/index.html"
DOCKERFILE="$REPO_ROOT/frontend/Dockerfile"
COMPOSE_FILE="$REPO_ROOT/deploy/compose.production.yml"
NGINX_IMAGE="nginx:1.28-alpine"
PUBLIC_IPV4="192.0.2.10"
MAINTENANCE_BYPASS_TOKEN="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT

fail() {
  printf 'nginx config test failed: %s\n' "$1" >&2
  exit 1
}

for required_file in \
  "$NGINX_CONF" \
  "$BOOTSTRAP_TEMPLATE" \
  "$PRODUCTION_IP_TEMPLATE" \
  "$PRODUCTION_TEMPLATE" \
  "$MAINTENANCE_PAGE"; do
  [[ -f "$required_file" ]] || fail "missing required file: $required_file"
done

python3 - \
  "$NGINX_CONF" \
  "$BOOTSTRAP_TEMPLATE" \
  "$PRODUCTION_IP_TEMPLATE" \
  "$PRODUCTION_TEMPLATE" \
  "$DOCKERFILE" \
  "$COMPOSE_FILE" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def directive_block(text: str, directive_pattern: str) -> str:
    match = re.search(rf"{directive_pattern}\s*\{{", text)
    assert match is not None, directive_pattern
    depth = 1
    cursor = match.end()
    while cursor < len(text) and depth:
        if text[cursor] == "{":
            depth += 1
        elif text[cursor] == "}":
            depth -= 1
        cursor += 1
    assert depth == 0, directive_pattern
    return text[match.end() : cursor - 1]


def server_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    cursor = 0
    while match := re.search(r"\bserver\s*\{", text[cursor:]):
        start = cursor + match.start()
        opening_brace = text.index("{", start)
        depth = 1
        end = opening_brace + 1
        while end < len(text) and depth:
            if text[end] == "{":
                depth += 1
            elif text[end] == "}":
                depth -= 1
            end += 1
        assert depth == 0, "server"
        blocks.append(text[opening_brace + 1 : end - 1])
        cursor = end
    return blocks


def assert_security_headers(block: str, request_id_variable: str) -> None:
    required = (
        'add_header X-Content-Type-Options "nosniff" always;',
        'add_header X-Frame-Options "DENY" always;',
        'add_header Referrer-Policy "strict-origin-when-cross-origin" always;',
        'add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;',
        f'add_header X-Request-ID ${request_id_variable} always;',
    )
    for directive in required:
        assert directive in block, directive


nginx_conf, bootstrap, production_ip, production, dockerfile, compose = map(
    read, sys.argv[1:]
)

for production_template in (production_ip, production):
    assert re.search(
        r"map\s+\$http_x_onetree_maintenance_bypass\s+\$maintenance_marker\s*\{"
        r".*?default\s+/var/www/certbot/\.onetree-maintenance;"
        r'.*?"\$\{MAINTENANCE_BYPASS_TOKEN\}"\s+'
        r"/var/www/certbot/\.onetree-maintenance-bypassed;"
        r".*?\}",
        production_template,
        flags=re.DOTALL,
    )

for directive in (
    "server_tokens off;",
    "map_hash_bucket_size 128;",
    "client_max_body_size 100m;",
    "limit_req_status 429;",
    "limit_req_zone $binary_remote_addr zone=login_limit:10m rate=10r/m;",
    "limit_req_zone $binary_remote_addr zone=register_limit:10m rate=5r/m;",
):
    assert directive in nginx_conf, directive
assert re.search(
    r"map\s+\$http_x_request_id\s+\$request_id_header\s*\{"
    r".*?default\s+\$http_x_request_id;"
    r".*?\"\"\s+\$request_id;"
    r".*?\}",
    nginx_conf,
    flags=re.DOTALL,
)
assert re.search(
    r"map\s+\$upstream_http_x_request_id\s+\$response_request_id\s*\{"
    r".*?default\s+\$upstream_http_x_request_id;"
    r'.*?""\s+\$request_id_header;'
    r".*?\}",
    nginx_conf,
    flags=re.DOTALL,
)

bootstrap_servers = server_blocks(bootstrap)
assert len(bootstrap_servers) == 3, len(bootstrap_servers)
bootstrap_allowed = [
    block
    for block in bootstrap_servers
    if "server_name onetree.chat www.onetree.chat;" in block
    or "server_name ${PUBLIC_IPV4};" in block
]
assert len(bootstrap_allowed) == 2, len(bootstrap_allowed)
for bootstrap_server in bootstrap_allowed:
    assert_security_headers(bootstrap_server, "request_id_header")
    bootstrap_challenge = directive_block(
        bootstrap_server, r"location\s+\^~\s+/\.well-known/acme-challenge/"
    )
    assert "root /var/www/certbot;" in bootstrap_challenge
    assert "return 301" not in bootstrap_challenge
    bootstrap_http = directive_block(bootstrap_server, r"location\s+/\s*")
    assert "return 301 https://$host$request_uri;" in bootstrap_http
bootstrap_default = next(
    block for block in bootstrap_servers if "listen 80 default_server;" in block
)
assert "server_name _;" in bootstrap_default
assert "return 444;" in bootstrap_default

production_servers = server_blocks(production)
assert len(production_servers) == 5, len(production_servers)
http_servers = [block for block in production_servers if "listen 80" in block]
https_servers = [block for block in production_servers if "listen 443 ssl" in block]
assert len(http_servers) == 3, len(http_servers)
assert len(https_servers) == 2, len(https_servers)

http_allowed = [
    block
    for block in http_servers
    if "server_name onetree.chat www.onetree.chat;" in block
    or "server_name ${PUBLIC_IPV4};" in block
]
assert len(http_allowed) == 2, len(http_allowed)
for http_server in http_allowed:
    assert_security_headers(http_server, "response_request_id")
    http_challenge = directive_block(
        http_server, r"location\s+\^~\s+/\.well-known/acme-challenge/"
    )
    assert "root /var/www/certbot;" in http_challenge
    assert "return 301" not in http_challenge
    http_default = directive_block(http_server, r"location\s+/\s*")
    assert "return 301 https://$host$request_uri;" in http_default
http_default_server = next(
    block for block in http_servers if "listen 80 default_server;" in block
)
assert "server_name _;" in http_default_server
assert "return 444;" in http_default_server

domain_server = next(
    block
    for block in https_servers
    if "server_name onetree.chat www.onetree.chat;" in block
)
ip_server = next(
    block for block in https_servers if "server_name ${PUBLIC_IPV4};" in block
)

assert (
    "ssl_certificate /etc/letsencrypt/live/onetree-domain/fullchain.pem;"
    in domain_server
)
assert (
    "ssl_certificate_key /etc/letsencrypt/live/onetree-domain/privkey.pem;"
    in domain_server
)
assert "ssl_certificate /etc/letsencrypt/live/onetree-ip/fullchain.pem;" in ip_server
assert "ssl_certificate_key /etc/letsencrypt/live/onetree-ip/privkey.pem;" in ip_server

production_ip_servers = server_blocks(production_ip)
assert len(production_ip_servers) == 3, len(production_ip_servers)
production_ip_http_servers = [
    block for block in production_ip_servers if "listen 80" in block
]
production_ip_https_servers = [
    block for block in production_ip_servers if "listen 443 ssl" in block
]
assert len(production_ip_http_servers) == 2, len(production_ip_http_servers)
assert len(production_ip_https_servers) == 1, len(production_ip_https_servers)
assert "onetree-domain" not in production_ip, production_ip
assert "server_name onetree.chat" not in production_ip, production_ip
assert "server_name www.onetree.chat" not in production_ip, production_ip

production_ip_http = next(
    block
    for block in production_ip_http_servers
    if "server_name ${PUBLIC_IPV4};" in block
)
assert_security_headers(production_ip_http, "response_request_id")
production_ip_challenge = directive_block(
    production_ip_http, r"location\s+\^~\s+/\.well-known/acme-challenge/"
)
assert "root /var/www/certbot;" in production_ip_challenge
assert "return 301" not in production_ip_challenge
production_ip_redirect = directive_block(production_ip_http, r"location\s+/\s*")
assert "return 301 https://$host$request_uri;" in production_ip_redirect

production_ip_http_default = next(
    block
    for block in production_ip_http_servers
    if "listen 80 default_server;" in block
)
assert "server_name _;" in production_ip_http_default
assert "return 444;" in production_ip_http_default

production_ip_https = production_ip_https_servers[0]
assert "listen 443 ssl default_server;" in production_ip_https
assert "server_name ${PUBLIC_IPV4};" in production_ip_https
assert (
    "ssl_certificate /etc/letsencrypt/live/onetree-ip/fullchain.pem;"
    in production_ip_https
)
assert (
    "ssl_certificate_key /etc/letsencrypt/live/onetree-ip/privkey.pem;"
    in production_ip_https
)

for https_server in (*https_servers, production_ip_https):
    assert_security_headers(https_server, "response_request_id")
    assert "proxy_hide_header X-Request-ID;" in https_server
    assert "proxy_intercept_errors on;" in https_server
    assert re.search(
        r"if\s*\(-f\s+\$maintenance_marker\)\s*\{"
        r"\s*return 503;\s*\}",
        https_server,
    )
    assert (
        'add_header Strict-Transport-Security '
        '"max-age=31536000; includeSubDomains" always;'
        in https_server
    )

    login = directive_block(https_server, r"location\s+=\s+/api/auth/login")
    assert "limit_req zone=login_limit burst=5 nodelay;" in login
    assert "proxy_pass http://backend:8000;" in login
    assert "proxy_set_header X-Request-ID $request_id_header;" in login

    register = directive_block(https_server, r"location\s+=\s+/api/auth/register")
    assert "limit_req zone=register_limit burst=2 nodelay;" in register
    assert "proxy_pass http://backend:8000;" in register
    assert "proxy_set_header X-Request-ID $request_id_header;" in register

    api = directive_block(https_server, r"location\s+/api")
    assert "proxy_pass http://backend:8000;" in api
    assert "proxy_set_header X-Request-ID $request_id_header;" in api

    upload = directive_block(
        https_server,
        r"location\s+=\s+/api/admin/knowledge-base/uploads",
    )
    assert "client_max_body_size 101m;" in upload
    assert "proxy_pass http://backend:8000;" in upload
    assert "proxy_set_header X-Request-ID $request_id_header;" in upload

assert "FROM nginx:1.28-alpine AS dist" in dockerfile
for source in (
    "deploy/nginx/nginx.conf",
    "deploy/nginx/conf.d/",
    "deploy/nginx/maintenance/index.html",
):
    assert source in dockerfile, source

assert "NGINX_CONFIG_MODE: ${NGINX_CONFIG_MODE:-bootstrap}" in compose
assert "PUBLIC_IPV4: ${PUBLIC_IPV4}" in compose
assert (
    "MAINTENANCE_BYPASS_TOKEN: "
    "${MAINTENANCE_BYPASS_TOKEN:?MAINTENANCE_BYPASS_TOKEN is required}"
    in compose
)
assert 'case "$${NGINX_CONFIG_MODE}" in' in compose
assert "bootstrap|production-ip|production)" in compose
assert "exit 64" in compose
assert (
    '"/opt/onetree/nginx/conf.d/$${NGINX_CONFIG_MODE}.conf.template"'
    in compose
)
assert "'$${PUBLIC_IPV4} $${MAINTENANCE_BYPASS_TOKEN}'" in compose
PY

mkdir -p \
  "$TEMP_DIR/acme/.well-known/acme-challenge" \
  "$TEMP_DIR/html" \
  "$TEMP_DIR/letsencrypt/live/onetree-domain" \
  "$TEMP_DIR/letsencrypt/live/onetree-ip"
printf 'ok\n' > "$TEMP_DIR/html/index.html"

openssl req -x509 -nodes -newkey rsa:2048 \
  -keyout "$TEMP_DIR/test-key.pem" \
  -out "$TEMP_DIR/test-cert.pem" \
  -subj "/CN=onetree.chat" \
  -days 1 >/dev/null 2>&1

for cert_name in onetree-domain onetree-ip; do
  cp "$TEMP_DIR/test-cert.pem" \
    "$TEMP_DIR/letsencrypt/live/$cert_name/fullchain.pem"
  cp "$TEMP_DIR/test-key.pem" \
    "$TEMP_DIR/letsencrypt/live/$cert_name/privkey.pem"
done

python3 - \
  "$PRODUCTION_TEMPLATE" \
  "$TEMP_DIR/production.conf" \
  "$PUBLIC_IPV4" \
  "$MAINTENANCE_BYPASS_TOKEN" <<'PY'
from pathlib import Path
import sys

template = Path(sys.argv[1]).read_text(encoding="utf-8")
Path(sys.argv[2]).write_text(
    template.replace("${PUBLIC_IPV4}", sys.argv[3]).replace(
        "${MAINTENANCE_BYPASS_TOKEN}", sys.argv[4]
    ),
    encoding="utf-8",
)
PY

python3 - \
  "$PRODUCTION_IP_TEMPLATE" \
  "$TEMP_DIR/production-ip.conf" \
  "$PUBLIC_IPV4" \
  "$MAINTENANCE_BYPASS_TOKEN" <<'PY'
from pathlib import Path
import sys

template = Path(sys.argv[1]).read_text(encoding="utf-8")
Path(sys.argv[2]).write_text(
    template.replace("${PUBLIC_IPV4}", sys.argv[3]).replace(
        "${MAINTENANCE_BYPASS_TOKEN}", sys.argv[4]
    ),
    encoding="utf-8",
)
PY

validate_config() {
  local rendered_config="$1"

  docker run --rm \
    --add-host backend:127.0.0.1 \
    --volume "$NGINX_CONF:/etc/nginx/nginx.conf:ro" \
    --volume "$rendered_config:/etc/nginx/conf.d/default.conf:ro" \
    --volume "$TEMP_DIR/acme:/var/www/certbot:ro" \
    --volume "$TEMP_DIR/html:/usr/share/nginx/html:ro" \
    --volume "$TEMP_DIR/letsencrypt:/etc/letsencrypt:ro" \
    "$NGINX_IMAGE" nginx -t
}

validate_config "$BOOTSTRAP_TEMPLATE"
validate_config "$TEMP_DIR/production-ip.conf"
validate_config "$TEMP_DIR/production.conf"

export APP_ENV=production
export POSTGRES_MAINTENANCE_PASSWORD=nginx-test-maintenance-password
export POSTGRES_APP_PASSWORD=nginx-test-app-password
export JWT_SECRET=nginx-test-jwt-secret
export LLM_API_KEY=nginx-test-llm-api-key
export LLM_MODEL=nginx-test-llm-model
export LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
export ALLOWED_ORIGINS=https://onetree.chat,https://www.onetree.chat
export LETSENCRYPT_EMAIL=nginx-test@example.com
export SMOKE_ACCOUNT=18771701100
export SMOKE_PASSWORD=nginx-test-password
export PUBLIC_IPV4
export MAINTENANCE_BYPASS_TOKEN

docker compose --profile operations -f "$COMPOSE_FILE" config --format json \
  > "$TEMP_DIR/compose.json"
python3 - "$TEMP_DIR/compose.json" > "$TEMP_DIR/nginx-start-command" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
command = config["services"]["nginx"]["command"]
assert command[:2] == ["/bin/sh", "-c"], command
print(command[2].replace("$$", "$"))
PY

if docker run --rm \
  --env NGINX_CONFIG_MODE=invalid \
  --env PUBLIC_IPV4="$PUBLIC_IPV4" \
  "$NGINX_IMAGE" \
  /bin/sh -c "$(cat "$TEMP_DIR/nginx-start-command")"; then
  fail "invalid NGINX_CONFIG_MODE was accepted"
fi

printf 'nginx config passed\n'
