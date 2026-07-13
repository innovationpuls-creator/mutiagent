# IP HTTPS Production Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the one-command production bootstrap issue, serve, renew, and verify only the Let's Encrypt certificate for `https://1.12.69.26` while preserving the existing domain-plus-IP mode for use after ICP filing.

**Architecture:** Add a `production-ip` Nginx template and use the existing `NGINX_CONFIG_MODE` as the single source of truth. Certificate issuance receives an explicit `ip` or `all` mode; renewal uses the mode injected by the existing systemd `EnvironmentFile` and verifies only certificates loaded by that mode. Bootstrap explicitly selects `ip`, switches to `production-ip` only after successful issuance, then runs the existing smoke workflow.

**Tech Stack:** Bash, Docker Compose, Nginx 1.28, Certbot 5.4+, OpenSSL, Python assertions in shell tests, systemd.

## Global Constraints

- Work directly on `main`; do not create a branch or worktree.
- Do not modify database schemas, application code, accounts, or textbook files.
- Preserve exact identifiers `production-ip`, `production`, `bootstrap`, `onetree-ip`, and `onetree-domain`.
- Automatic production acceptance remains limited to services, database health, and login.
- Remove temporary validation files after they are no longer needed.

---

### Task 1: Specify Certificate Modes With Failing Tests

**Files:**
- Modify: `deploy/tests/test_cert_scripts.sh`
- Test: `deploy/tests/test_cert_scripts.sh`

**Interfaces:**
- Consumes: existing `deploy/bin/cert-issue`, `deploy/bin/cert-renew`, and `.env.production` fixture.
- Produces: assertions for `cert-issue ip`, `cert-issue all`, `NGINX_CONFIG_MODE=production-ip`, and `NGINX_CONFIG_MODE=production`.

- [ ] **Step 1: Add an IP-only issuance assertion**

Run `cert-issue ip` through `run_script`, parse the command log with `shlex.split`, and assert the exact sequence:

```python
assert observed == [
    ("onetree-ip", True),
    ("onetree-ip", False),
], observed
```

Also assert no command contains `onetree-domain`, `onetree.chat`, or `www.onetree.chat`.

- [ ] **Step 2: Preserve all-mode compatibility**

Run `cert-issue all` and the no-argument form. For both calls assert:

```python
assert observed == [
    ("onetree-domain", True),
    ("onetree-ip", True),
    ("onetree-domain", False),
    ("onetree-ip", False),
], observed
```

- [ ] **Step 3: Add renewal mode assertions**

Write the exact fixture line `NGINX_CONFIG_MODE=production-ip`, run `cert-renew`, and assert only `onetree-ip` is verified and served. Repeat with `NGINX_CONFIG_MODE=production` and assert both certificates are verified and served. Add an invalid-mode case that asserts no Nginx reload occurs.

- [ ] **Step 4: Run the test and verify failure**

Run:

```bash
bash deploy/tests/test_cert_scripts.sh
```

Expected: FAIL because the current scripts do not implement the explicit issuance modes and renewal still requires both certificates.

---

### Task 2: Implement Certificate Mode Selection

**Files:**
- Modify: `deploy/bin/cert-issue`
- Modify: `deploy/bin/cert-renew`
- Test: `deploy/tests/test_cert_scripts.sh`

**Interfaces:**
- Consumes: argument `${1:-all}` in `cert-issue`; exact `NGINX_CONFIG_MODE` environment variable injected by `onetree-cert-renew.service`.
- Produces: deterministic certificate selection without changing `cert-verify`.

- [ ] **Step 1: Validate the issuance mode**

Add this exact mode dispatch after environment validation:

```bash
CERTIFICATE_MODE="${1:-all}"
case "$CERTIFICATE_MODE" in
  ip|all) ;;
  *)
    printf 'unsupported certificate mode: %s\n' "$CERTIFICATE_MODE" >&2
    exit 64
    ;;
esac
```

- [ ] **Step 2: Run only selected issuance commands**

For `all`, retain the current domain staging, IP staging, domain production, IP production order and verify both certificates. For `ip`, run only IP staging, IP production, and `cert-verify onetree-ip`.

- [ ] **Step 3: Select certificates from the injected Nginx mode during renewal**

Require `NGINX_CONFIG_MODE` and dispatch its exact values without sourcing or executing `.env.production`:

```bash
: "${NGINX_CONFIG_MODE:?NGINX_CONFIG_MODE is required}"
case "$NGINX_CONFIG_MODE" in
  production-ip)
    CERTIFICATE_NAMES=(onetree-ip)
    ;;
  production)
    CERTIFICATE_NAMES=(onetree-domain onetree-ip)
    ;;
  *)
    printf 'unsupported Nginx certificate mode: %s\n' "$NGINX_CONFIG_MODE" >&2
    exit 64
    ;;
esac
```

Loop over `CERTIFICATE_NAMES` for disk verification. After Nginx reload, call `verify_served_certificate onetree-domain -servername onetree.chat` only in `production`, and call `verify_served_certificate onetree-ip -noservername` in both production modes.

- [ ] **Step 4: Run certificate tests**

Run:

```bash
bash deploy/tests/test_cert_scripts.sh
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deploy/bin/cert-issue deploy/bin/cert-renew deploy/tests/test_cert_scripts.sh
git commit -m "fix: support IP-only certificate lifecycle"
```

---

### Task 3: Add the IP-Only Nginx Production Mode

**Files:**
- Create: `deploy/nginx/conf.d/production-ip.conf.template`
- Modify: `deploy/nginx/nginx.conf`
- Modify: `deploy/compose.production.yml`
- Modify: `deploy/tests/test_nginx_config.sh`
- Test: `deploy/tests/test_nginx_config.sh`

**Interfaces:**
- Consumes: `${PUBLIC_IPV4}` and `${MAINTENANCE_BYPASS_TOKEN}`.
- Produces: an Nginx configuration that serves only `onetree-ip` on 443.

- [ ] **Step 1: Add failing template assertions**

Require `production-ip.conf.template`. Parse its server blocks and assert exactly three blocks: IP HTTP, default HTTP, and IP HTTPS. Assert that its text contains:

```nginx
ssl_certificate /etc/letsencrypt/live/onetree-ip/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/onetree-ip/privkey.pem;
```

Assert that it does not contain `onetree-domain`, `server_name onetree.chat`, or `server_name www.onetree.chat`.

Use the same 64-character maintenance bypass token generated by bootstrap and require `map_hash_bucket_size 128;` in the Nginx `http` block.

- [ ] **Step 2: Add a failing Compose mode assertion**

Change the expected shell case from `bootstrap|production)` to:

```bash
bootstrap|production-ip|production)
```

- [ ] **Step 3: Run the Nginx test and verify failure**

Run:

```bash
bash deploy/tests/test_nginx_config.sh
```

Expected: FAIL because the template and Compose mode do not exist.

- [ ] **Step 4: Create the template**

Copy the maintenance marker map and the complete IP HTTP, default HTTP, and IP HTTPS server blocks from `production.conf.template` without changing their directives. Exclude both domain server blocks. The resulting file must reference only the `onetree-ip` certificate.

- [ ] **Step 5: Allow the exact Compose mode**

Change the Nginx command case to:

```bash
case "$${NGINX_CONFIG_MODE}" in
  bootstrap|production-ip|production) ;;
  *) echo "invalid NGINX_CONFIG_MODE: $${NGINX_CONFIG_MODE}" >&2; exit 64 ;;
esac;
```

Add `map_hash_bucket_size 128;` next to the other global HTTP settings so the generated 64-character maintenance token can be used as a `map` key.

- [ ] **Step 6: Run the Nginx test**

Run:

```bash
bash deploy/tests/test_nginx_config.sh
```

Expected: PASS, including `nginx -t` for the rendered `production-ip` template.

- [ ] **Step 7: Commit**

```bash
git add deploy/nginx/conf.d/production-ip.conf.template deploy/nginx/nginx.conf deploy/compose.production.yml deploy/tests/test_nginx_config.sh
git commit -m "feat: add IP-only Nginx production mode"
```

---

### Task 4: Select IP HTTPS During One-Command Bootstrap

**Files:**
- Modify: `deploy/bin/bootstrap`
- Modify: `deploy/tests/test_bootstrap.sh`
- Test: `deploy/tests/test_bootstrap.sh`

**Interfaces:**
- Consumes: `cert-issue ip` and `production-ip` from Tasks 2 and 3.
- Produces: a completed bootstrap whose persisted environment selects `production-ip`.

- [ ] **Step 1: Change the bootstrap fixture expectations**

Require the certificate stub to log its arguments and assert the exact line `cert-issue ip`. Change the forced Nginx recreation assertion and final environment assertion to:

```bash
grep -qx 'NGINX_CONFIG_MODE=production-ip' "$ENV_FILE"
```

- [ ] **Step 2: Run the bootstrap test and verify failure**

Run:

```bash
bash deploy/tests/test_bootstrap.sh
```

Expected: FAIL because bootstrap still invokes all-mode issuance and persists `production`.

- [ ] **Step 3: Implement the two exact bootstrap changes**

Change `start_production` to execute:

```bash
"$ONETREE_INSTALL_ROOT/deploy/bin/cert-issue" ip
write_production_env production-ip
```

Change completion output to print only:

```bash
printf 'https://%s\n' "$PUBLIC_IPV4"
```

- [ ] **Step 4: Run the bootstrap test**

Run:

```bash
bash deploy/tests/test_bootstrap.sh
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deploy/bin/bootstrap deploy/tests/test_bootstrap.sh
git commit -m "fix: bootstrap with IP HTTPS before ICP filing"
```

---

### Task 5: Update the Production Runbook and Verify the Full Deployment Suite

**Files:**
- Modify: `deploy/bin/smoke`
- Modify: `deploy/compose.production.yml`
- Modify: `deploy/tests/test_smoke.sh`
- Modify: `deploy/tests/test_compose_config.sh`
- Modify: `docs/deployment/docker-production.md`
- Test: all `deploy/tests/test_*.sh`

**Interfaces:**
- Consumes: the completed IP-only production workflow.
- Produces: exact operator instructions for the current pre-filing state.

- [ ] **Step 1: Make smoke select checks by production mode**

Pass `NGINX_CONFIG_MODE` into the smoke container. In `production-ip`, skip the direct `https://onetree.chat` request and retain IP TLS, redirect, live, ready, home, login, and `/api/auth/me` checks. In `production`, retain the domain request and all IP checks. Reject every other mode before invoking curl.

- [ ] **Step 2: Verify smoke mode selection**

Run:

```bash
bash deploy/tests/test_smoke.sh
bash deploy/tests/test_compose_config.sh
```

Expected: both tests PASS, with `production-ip` making no domain request.

- [ ] **Step 3: Document the current public URL and mode**

State that the current production URL is `https://1.12.69.26`, `.env.production` must contain `NGINX_CONFIG_MODE=production-ip`, and domain access remains unavailable until ICP filing passes. Preserve the existing domain certificate commands as the post-filing transition procedure.

- [ ] **Step 4: Run deployment tests in parallel**

Run every executable `deploy/tests/test_*.sh` concurrently, capture each exit status, and fail the verification if any script fails.

Expected: all deployment tests PASS.

- [ ] **Step 5: Check the diff**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors and only the planned files changed.

- [ ] **Step 6: Commit**

```bash
git add docs/deployment/docker-production.md
git commit -m "docs: document pre-filing IP HTTPS deployment"
```

---

### Task 6: Deploy and Verify on the Ubuntu Server

**Files:**
- Server repository: `/opt/onetree`
- Server environment: `/opt/onetree/.env.production`

**Interfaces:**
- Consumes: local `main` commits delivered through an offline Git bundle when GitHub is unreachable.
- Produces: live `https://1.12.69.26` with automated renewal.

- [ ] **Step 1: Transfer and fast-forward the exact local `main`**

Create a Git bundle containing the new commits, upload it through OrcaTerm, verify its SHA-256, then run `git fetch <bundle> main` and `git merge --ff-only FETCH_HEAD` in `/opt/onetree`.

- [ ] **Step 2: Resume from the existing healthy bootstrap services**

Run `cert-issue ip`, persist `NGINX_CONFIG_MODE=production-ip` without changing any other environment entry, force-recreate Nginx, and enable `onetree-cert-renew.timer`.

- [ ] **Step 3: Run exact production verification**

Verify Compose services are healthy, run `cert-verify onetree-ip`, run the existing smoke command, inspect the renewal timer, and request `https://1.12.69.26` externally.

- [ ] **Step 4: Remove temporary artifacts**

After successful verification, remove transferred Git bundles and obsolete debug scripts. Remove the temporary SSH public key, UFW TCP 22 rule, Tencent Cloud TCP 22 rule, and local temporary private key after the required destructive-action confirmation.
