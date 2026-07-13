#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNBOOK="$REPO_ROOT/docs/deployment/docker-production.md"
README="$REPO_ROOT/README.md"

fail() {
  printf 'deployment docs test failed: %s\n' "$1" >&2
  exit 1
}

[[ -f "$RUNBOOK" ]] || fail "missing Docker production runbook"

grep -Fq \
  'https://raw.githubusercontent.com/innovationpuls-creator/mutiagent/main/deploy/bin/bootstrap' \
  "$RUNBOOK" || fail "bootstrap URL is missing"
grep -Fq '/opt/onetree/bin/deploy' "$RUNBOOK" \
  || fail "deploy command is missing"
python3 - "$RUNBOOK" <<'PY'
from pathlib import Path
import sys

runbook = Path(sys.argv[1]).read_text(encoding="utf-8")
required_guidance = (
    "\u82e5 `/opt/onetree/bin/deploy` \u5df2\u5b58\u5728",
    "\u9996\u6b21\u90e8\u7f72\u4e2d\u9014\u5931\u8d25",
)
for guidance in required_guidance:
    if guidance not in runbook:
        raise SystemExit(1)
PY
grep -Fq '/opt/onetree/bin/rollback <backup-id>' "$RUNBOOK" \
  || fail "rollback command contract is missing"
grep -Fq 'docs/deployment/docker-production.md' "$README" \
  || fail "README production link is missing"

for command_name in deploy rollback; do
  [[ -x "$REPO_ROOT/deploy/bin/$command_name" ]] \
    || fail "documented command is not executable: $command_name"
done

printf '%s\n' 'deployment docs tests passed'
