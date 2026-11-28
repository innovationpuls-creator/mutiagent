#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/deploy/compose.production.yml"
CI_COMPOSE_FILE="$REPO_ROOT/deploy/compose.ci.yml"
CONFIG_FILE="$(mktemp)"
CI_CONFIG_FILE="$(mktemp)"
trap 'rm -f "$CONFIG_FILE" "$CI_CONFIG_FILE"' EXIT

export APP_ENV=production
export POSTGRES_MAINTENANCE_PASSWORD=compose-test-maintenance-password
export POSTGRES_APP_PASSWORD=compose-test-app-password
export JWT_SECRET=compose-test-jwt-secret
export INTERNAL_API_TOKEN=compose-test-internal-token
export MODEL_SECRET_ENCRYPTION_KEY=compose-test-model-secret-key
export ALLOWED_ORIGINS=https://onetree.chat,https://www.onetree.chat
export PUBLIC_IPV4=192.0.2.10
export MAINTENANCE_BYPASS_TOKEN=compose-test-maintenance-bypass
export NGINX_CONFIG_MODE=production-ip
export VITE_ICP_BEIAN_NUMBER=粤ICP备2026100568号-1
export LETSENCRYPT_EMAIL=compose-test@example.com
export SMOKE_ACCOUNT=18771701100
export SMOKE_PASSWORD=compose-test-password

docker compose --profile operations -f "$COMPOSE_FILE" config --format json \
  > "$CONFIG_FILE"
docker compose --profile operations -f "$COMPOSE_FILE" -f "$CI_COMPOSE_FILE" \
  config --format json > "$CI_CONFIG_FILE"

python3 - \
  "$CONFIG_FILE" \
  "$REPO_ROOT/.gitignore" \
  "$REPO_ROOT/backend/Dockerfile" \
  "$CI_CONFIG_FILE" \
  "$REPO_ROOT/ai-gateway/Dockerfile" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
gitignore_lines = set(Path(sys.argv[2]).read_text(encoding="utf-8").splitlines())
backend_dockerfile = Path(sys.argv[3]).read_text(encoding="utf-8")
ci_config = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8"))
gateway_dockerfile = Path(sys.argv[5]).read_text(encoding="utf-8")
services = config["services"]
ci_services = ci_config["services"]

for runtime_path in (".env.production", "/backups/", "/bin/"):
    assert runtime_path in gitignore_lines, runtime_path
assert "ghcr.io" not in backend_dockerfile
assert "uv==0.8.22" in backend_dockerfile

expected_services = {
    "nginx",
    "ai-gateway",
    "backend",
    "worker",
    "postgres",
    "certbot",
    "migrate",
    "smoke",
    "backup",
    "restore",
}
assert set(services) == expected_services, set(services)

expected_volumes = {
    "postgres_data",
    "textbook_uploads",
    "letsencrypt",
    "acme_webroot",
    "frontend_dist",
}
assert set(config["volumes"]) == expected_volumes, set(config["volumes"])

published_ports: list[tuple[str, int, int]] = []
for service_name, service in services.items():
    for port in service.get("ports", []):
        published_ports.append(
            (service_name, int(port["published"]), int(port["target"]))
        )
assert sorted(published_ports) == [
    ("nginx", 80, 80),
    ("nginx", 443, 443),
], published_ports
assert "ports" not in services["backend"]
assert "ports" not in services["ai-gateway"]
assert "ports" not in services["postgres"]

for service_name in (
    "nginx",
    "ai-gateway",
    "backend",
    "worker",
    "postgres",
    "certbot",
):
    assert services[service_name]["restart"] == "unless-stopped", service_name

for service_name, service in services.items():
    assert service["logging"]["driver"] == "journald", service_name

assert services["postgres"]["image"].split(":", maxsplit=1)[1].startswith("18")
assert services["worker"]["command"] == ["python", "-m", "app.workers"]
assert services["migrate"]["command"] == ["python", "-m", "app.migration_cli"]
assert services["postgres"]["environment"]["POSTGRES_DB"] == "onetree"
assert services["postgres"]["environment"]["POSTGRES_USER"] == "onetree_maintenance"
assert services["backend"]["build"]["args"]["DEBIAN_MIRROR"] == (
    "http://deb.debian.org/debian"
)
assert services["backend"]["build"]["args"]["DEBIAN_SECURITY_MIRROR"] == (
    "http://deb.debian.org/debian-security"
)
assert services["backend"]["build"]["args"]["PGDG_KEY_URL"] == (
    "https://www.postgresql.org/media/keys/ACCC4CF8.asc"
)
assert services["backend"]["build"]["args"]["PYTHON_PACKAGE_INDEX"] == (
    "https://pypi.org/simple"
)
assert services["backend"]["build"]["args"]["UV_HTTP_TIMEOUT"] == "300"
for service_name in ("worker", "migrate", "smoke", "backup", "restore"):
    assert services[service_name]["image"] == "onetree-backend:production"
    assert "build" not in services[service_name], service_name
assert "onetree_app" in services["backend"]["environment"]["DATABASE_URL"]
assert "onetree_maintenance" in services["migrate"]["environment"]["DATABASE_URL"]
assert "onetree_maintenance" in ci_services["migrate"]["environment"]["DATABASE_URL"]
assert "onetree_maintenance" in services["backup"]["environment"]["TARGET_DATABASE_URL"]
assert "onetree_maintenance" in services["restore"]["environment"]["TARGET_DATABASE_URL"]
assert services["backup"]["user"] == "0:0"
assert services["restore"]["user"] == "0:0"
assert services["restore"]["entrypoint"] == ["/opt/onetree/deploy/bin/restore"]
assert services["restore"]["environment"]["UPLOADS_OWNER_UID"] == "10001"
assert services["restore"]["environment"]["UPLOADS_OWNER_GID"] == "10001"
assert "frontend" not in services

nginx_build = services["nginx"]["build"]
assert nginx_build["target"] == "dist"
assert nginx_build["args"]["NPM_REGISTRY"] == "https://registry.npmjs.org"
assert nginx_build["args"]["VITE_ICP_BEIAN_NUMBER"] == "粤ICP备2026100568号-1"
assert "/opt/onetree/frontend-dist" in " ".join(services["nginx"]["command"])
assert services["nginx"]["environment"]["MAINTENANCE_BYPASS_TOKEN"] == (
    "compose-test-maintenance-bypass"
)
assert services["smoke"]["environment"]["MAINTENANCE_BYPASS_TOKEN"] == (
    "compose-test-maintenance-bypass"
)
assert services["smoke"]["environment"]["NGINX_CONFIG_MODE"] == "production-ip"
assert services["smoke"]["depends_on"]["worker"]["condition"] == "service_started"

gateway = services["ai-gateway"]
assert gateway["image"] == "onetree-ai-gateway:production"
assert gateway["build"]["dockerfile"] == "ai-gateway/Dockerfile"
assert gateway["logging"]["options"]["tag"] == "onetree-ai-gateway"
assert gateway["depends_on"]["backend"]["condition"] == "service_healthy"
assert "/api/ai/health/ready" in " ".join(gateway["healthcheck"]["test"])
assert gateway["environment"]["PYTHON_BACKEND_URL"] == "http://backend:8000"
for key, value in {
    "APP_ENV": "production",
    "JWT_SECRET": "compose-test-jwt-secret",
    "INTERNAL_API_TOKEN": "compose-test-internal-token",
    "ALLOWED_ORIGINS": "https://onetree.chat,https://www.onetree.chat",
}.items():
    assert gateway["environment"][key] == value, key
assert services["nginx"]["depends_on"]["ai-gateway"]["condition"] == "service_healthy"
for service_name in ("backend", "worker"):
    environment = services[service_name]["environment"]
    assert environment["AI_GATEWAY_URL"] == "http://ai-gateway:8100", service_name
    assert environment["INTERNAL_API_TOKEN"] == "compose-test-internal-token"
    assert environment["MODEL_SECRET_ENCRYPTION_KEY"] == (
        "compose-test-model-secret-key"
    )
assert ci_services["ai-gateway"]["environment"]["INTERNAL_API_TOKEN"] == (
    ci_services["backend"]["environment"]["INTERNAL_API_TOKEN"]
)
assert "FROM node:22" in gateway_dockerfile or "node:22" in gateway_dockerfile
assert "USER node" in gateway_dockerfile
assert "HEALTHCHECK" in gateway_dockerfile
assert "/api/ai/health/live" in gateway_dockerfile
assert gateway_dockerfile.count("FROM ") >= 2

upload_dir = services["backend"]["environment"]["KNOWLEDGE_BASE_UPLOAD_DIR"]
upload_volume_target = str(Path(upload_dir).parent)
for service_name in ("backend", "worker", "backup", "restore"):
    mounts = services[service_name].get("volumes", [])
    matching_mounts = [
        mount
        for mount in mounts
        if mount["type"] == "volume"
        and mount["source"].endswith("textbook_uploads")
        and mount["target"] == upload_volume_target
    ]
    assert len(matching_mounts) == 1, service_name

for service_name in ("backup", "restore"):
    mounts = services[service_name].get("volumes", [])
    assert any(
        mount["type"] == "bind" and mount["source"] == "/opt/onetree/backups"
        for mount in mounts
    ), service_name

print("production compose config passed")
PY

if env -u MAINTENANCE_BYPASS_TOKEN \
  docker compose --profile operations -f "$COMPOSE_FILE" config \
  >/dev/null 2>&1; then
  printf '%s\n' 'missing MAINTENANCE_BYPASS_TOKEN was accepted' >&2
  exit 1
fi

for required_variable in INTERNAL_API_TOKEN MODEL_SECRET_ENCRYPTION_KEY; do
  if env -u "$required_variable" \
    docker compose --profile operations -f "$COMPOSE_FILE" config \
    >/dev/null 2>&1; then
    printf 'missing %s was accepted\n' "$required_variable" >&2
    exit 1
  fi
done
