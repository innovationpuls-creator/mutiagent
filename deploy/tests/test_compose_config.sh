#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/deploy/compose.production.yml"
CONFIG_FILE="$(mktemp)"
trap 'rm -f "$CONFIG_FILE"' EXIT

export APP_ENV=production
export POSTGRES_MAINTENANCE_PASSWORD=compose-test-maintenance-password
export POSTGRES_APP_PASSWORD=compose-test-app-password
export JWT_SECRET=compose-test-jwt-secret
export LLM_API_KEY=compose-test-llm-api-key
export LLM_MODEL=compose-test-llm-model
export LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
export ALLOWED_ORIGINS=https://onetree.chat,https://www.onetree.chat
export PUBLIC_IPV4=192.0.2.10
export MAINTENANCE_BYPASS_TOKEN=compose-test-maintenance-bypass
export LETSENCRYPT_EMAIL=compose-test@example.com
export SMOKE_ACCOUNT=18771701100
export SMOKE_PASSWORD=compose-test-password

docker compose --profile operations -f "$COMPOSE_FILE" config --format json \
  > "$CONFIG_FILE"

python3 - \
  "$CONFIG_FILE" \
  "$REPO_ROOT/.gitignore" \
  "$REPO_ROOT/backend/Dockerfile" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
gitignore_lines = set(Path(sys.argv[2]).read_text(encoding="utf-8").splitlines())
backend_dockerfile = Path(sys.argv[3]).read_text(encoding="utf-8")
services = config["services"]

for runtime_path in (".env.production", "/backups/", "/bin/"):
    assert runtime_path in gitignore_lines, runtime_path
assert "ghcr.io" not in backend_dockerfile
assert "uv==0.8.22" in backend_dockerfile

expected_services = {
    "nginx",
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
assert "ports" not in services["postgres"]

for service_name in ("nginx", "backend", "worker", "postgres", "certbot"):
    assert services[service_name]["restart"] == "unless-stopped", service_name

for service_name, service in services.items():
    assert service["logging"]["driver"] == "journald", service_name

assert services["postgres"]["image"].split(":", maxsplit=1)[1].startswith("18")
assert services["worker"]["command"] == ["python", "-m", "app.workers"]
assert services["migrate"]["command"] == ["alembic", "upgrade", "head"]
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
assert "/opt/onetree/frontend-dist" in " ".join(services["nginx"]["command"])
assert services["nginx"]["environment"]["MAINTENANCE_BYPASS_TOKEN"] == (
    "compose-test-maintenance-bypass"
)
assert services["smoke"]["environment"]["MAINTENANCE_BYPASS_TOKEN"] == (
    "compose-test-maintenance-bypass"
)

upload_dir = services["backend"]["environment"]["KNOWLEDGE_BASE_UPLOAD_DIR"]
for service_name in ("backend", "worker", "backup", "restore"):
    mounts = services[service_name].get("volumes", [])
    matching_mounts = [
        mount
        for mount in mounts
        if mount["type"] == "volume"
        and mount["source"].endswith("textbook_uploads")
        and mount["target"] == upload_dir
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
