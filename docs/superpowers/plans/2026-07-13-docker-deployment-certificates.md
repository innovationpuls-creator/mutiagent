# Docker Deployment and Certificates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Ubuntu 24.04 x86_64 实现 Docker Compose 生产栈、nginx 安全入口、域名/IP 双证书、可回滚发布与一条命令 bootstrap。

**Architecture:** 生产 Compose 只暴露 nginx。发布脚本以 flock、备份、维护页、迁移、健康检查和失败 trap 形成原子流程；Certbot webroot 先 staging 后 production，systemd 每 12 小时续期并校验后 reload。

**Tech Stack:** Docker Engine, Docker Compose, nginx, Certbot 5.4+, systemd, UFW, Bash, shellcheck, OpenSSL.

## Global Constraints

- 主机固定为 Ubuntu 24.04 x86_64，root 执行。
- Compose 服务精确命名：`nginx`, `backend`, `worker`, `postgres`, `certbot`, `migrate`, `smoke`, `backup`, `restore`。
- 只发布主机 `80:80` 与 `443:443`；不得发布 `8000` 或 `5432`。
- 管理员上传单个 PDF 或 DOCX 教材最大为 `100 MB`；nginx 和后端必须在读取完整请求体前拒绝超限请求。
- PostgreSQL 使用 18 主版本。
- `TARGET_DATABASE_URL` 是容器内维护态连接；该角色具备 `CREATEDB`，并拥有导入时创建的随机临时校验库。应用数据库不发布宿主机端口，只允许 Docker 内网访问。
- swap 精确为 4 GB；UFW 只开放 `80/tcp`、`443/tcp`。
- secrets 文件 `/opt/onetree/.env.production` 权限 `0600`，不得回显。
- 正常发布禁止 `down -v`。

---

### Task 1: 生产镜像与 Compose 拓扑

**Files:**
- Create: `backend/Dockerfile`
- Create: `frontend/Dockerfile`
- Create: `.dockerignore`
- Create: `deploy/compose.production.yml`
- Create: `deploy/env.production.example`
- Create: `deploy/tests/test_compose_config.sh`

**Interfaces:**
- Named volumes: `postgres_data`, `textbook_uploads`, `letsencrypt`, `acme_webroot`, `frontend_dist`。
- Bind mount: `/opt/onetree/backups`。

- [ ] **Step 1: 写 Compose 红测**

脚本运行 `docker compose -f deploy/compose.production.yml config`，断言唯一主机端口为 80/443、postgres/backend 无 ports、`KNOWLEDGE_BASE_UPLOAD_DIR` 精确指向教材 volume、所有长驻服务 `restart: unless-stopped`、logging driver 为 journald。

- [ ] **Step 2: 运行红测**

Run: `bash deploy/tests/test_compose_config.sh`
Expected: FAIL，因为 Compose 不存在。

- [ ] **Step 3: 实现镜像与 Compose**

backend 使用 Python 3.12 slim 和非 root 用户；frontend Dockerfile 只输出 `dist` stage；worker command 为 `python -m app.workers`；migrate command 为 `alembic upgrade head`。所有 env 键必须与 Phase 1 的 `AppSettings` 精确一致。

- [ ] **Step 4: 验证和提交**

Run: `bash deploy/tests/test_compose_config.sh && docker compose -f deploy/compose.production.yml build`
Expected: PASS，所有镜像构建成功。

Commit: `git commit -m "feat: add production container topology"`

### Task 2: nginx bootstrap 与正式安全入口

**Files:**
- Create: `deploy/nginx/nginx.conf`
- Create: `deploy/nginx/conf.d/bootstrap.conf.template`
- Create: `deploy/nginx/conf.d/production.conf.template`
- Create: `deploy/nginx/maintenance/index.html`
- Create: `deploy/tests/test_nginx_config.sh`

**Interfaces:**
- `/api` upstream: `backend:8000`。
- Limit routes: `/api/auth/login`, `/api/auth/register`。
- Request header: `X-Request-ID`。

- [ ] **Step 1: 写 nginx 红测**

使用官方 nginx 容器执行 `nginx -t`；断言 HTTP challenge 不跳转、其他 HTTP 301 HTTPS、域名和固定 IP 分别加载对应证书、API proxy、限流、安全头、request ID 转发/响应存在。

- [ ] **Step 2: 写教材上传大小红测**

在 `backend/tests/test_knowledge_base_api.py` 增加精确 `100 * 1024 * 1024` 边界测试：`100 MB` 请求可进入文件校验，`100 MB + 1 byte` 返回明确 413 且不调用 `create_uploaded_textbook`。实现后端共享常量，并在 nginx 使用 `client_max_body_size 100m`。

- [ ] **Step 3: 实现并验证**

Run: `bash deploy/tests/test_nginx_config.sh`
Expected: PASS，两个配置均 `nginx -t` 成功。

Commit: `git commit -m "feat: add secure nginx gateway"`

### Task 3: 域名和固定 IP 证书签发与续期

**Files:**
- Create: `deploy/bin/cert-issue`
- Create: `deploy/bin/cert-renew`
- Create: `deploy/bin/cert-verify`
- Create: `deploy/systemd/onetree-cert-renew.service`
- Create: `deploy/systemd/onetree-cert-renew.timer`
- Create: `deploy/tests/test_cert_scripts.sh`

**Interfaces:**
- Domain certificate SAN: `onetree.chat`, `www.onetree.chat`。
- IP certificate command contains `--preferred-profile shortlived` and `--ip-address "$PUBLIC_IPV4"`。
- Timer: `OnCalendar=*-*-* 03,15:00:00`。

- [ ] **Step 1: 写签发顺序红测**

stub certbot，断言域名和 IP 都必须先 staging 成功再调用 production；staging 失败时 production 不执行；Certbot 版本小于 5.4 时 IP 签发立即失败。

- [ ] **Step 2: 写 reload 保护红测**

stub OpenSSL/nginx，断言链、SAN、私钥匹配、有效期任一失败时不 reload；全部成功时先 `nginx -t` 再 `nginx -s reload`。

- [ ] **Step 3: 运行红测**

Run: `bash deploy/tests/test_cert_scripts.sh`
Expected: FAIL，因为脚本不存在。

- [ ] **Step 4: 实现签发、验证与 systemd timer**

证书文件只存在持久化 letsencrypt volume；脚本输出不得包含私钥。`cert-renew` 每次运行 `certbot renew` 后对域名/IP 调用 `cert-verify`，失败返回非零并保留当前 nginx。

- [ ] **Step 5: 验证与提交**

Run: `bash deploy/tests/test_cert_scripts.sh && systemd-analyze verify deploy/systemd/onetree-cert-renew.service deploy/systemd/onetree-cert-renew.timer`
Expected: PASS。

Commit: `git commit -m "feat: automate domain and IP certificates"`

### Task 4: 真实登录 smoke

**Files:**
- Create: `deploy/bin/smoke`
- Create: `deploy/tests/test_smoke.sh`

**Interfaces:**
- Login route: `/api/auth/login`。
- Payload keys: `account`, `password`。
- Auth verification route: `/api/auth/me`。

- [ ] **Step 1: 写 smoke 红测**

stub curl 返回 live/ready/home/TLS/redirect/login/me 响应；断言 login 必须提取 `access_token`、Bearer 调用 me、me.identifier 等于输入账号；任何一步失败返回非零；stdout/stderr 不含密码或 token。

- [ ] **Step 2: 运行红测并实现**

Run: `bash deploy/tests/test_smoke.sh`
Expected before implementation: FAIL；实现后 PASS。

- [ ] **Step 3: Shellcheck 与提交**

Run: `shellcheck deploy/bin/smoke deploy/tests/test_smoke.sh`
Expected: exit 0。

Commit: `git commit -m "test: add production login smoke check"`

### Task 5: 原子 deploy 与 rollback

**Files:**
- Create: `deploy/lib/common.sh`
- Create: `deploy/bin/deploy`
- Create: `deploy/bin/rollback`
- Create: `deploy/tests/test_deploy_rollback.sh`

**Interfaces:**
- Deploy lock: `/run/lock/onetree-deploy.lock`。
- Installed commands: `/opt/onetree/bin/deploy`, `/opt/onetree/bin/rollback <backup-id>`。

- [ ] **Step 1: 写故障注入红测**

覆盖 fetch/build/backup/migrate/up/smoke 各阶段失败；断言维护状态保持、返回非零、旧 commit/镜像恢复；migrate 已执行后必须调用同一 backup-id 的 restore；smoke 成功才恢复正常流量。

- [ ] **Step 2: 写并发与危险命令红测**

第二个 deploy 获取不到 flock 时失败；静态扫描全部 deploy 脚本，断言不存在 `down -v`、`rm .*postgres_data` 或 secrets echo。

- [ ] **Step 3: 实现状态机与 trap**

使用显式阶段变量记录 migration 是否执行；每一步成功才推进。rollback 先验证 manifest，停止 worker/backend 写入，恢复数据与旧 commit/镜像，ready/login 成功后才退出维护。

- [ ] **Step 4: 验证与提交**

Run: `bash deploy/tests/test_deploy_rollback.sh && shellcheck deploy/lib/common.sh deploy/bin/deploy deploy/bin/rollback`
Expected: PASS。

Commit: `git commit -m "feat: add atomic production deployment"`

### Task 6: Ubuntu 一条命令 bootstrap

**Files:**
- Create: `deploy/bin/bootstrap`
- Create: `deploy/tests/test_bootstrap.sh`

**Interfaces:**
- Install root: `/opt/onetree`。
- Secrets: `/opt/onetree/.env.production`, mode `0600`。
- Swap: `/swapfile`, size 4 GB。

- [ ] **Step 1: 写系统前置红测**

非 root、`VERSION_ID` 非 24.04、`uname -m` 非 x86_64 必须在修改系统前失败。重复执行不能重复 fstab swap 行或破坏已有 Docker。

- [ ] **Step 2: 写 secrets 与防火墙红测**

交互输入只有 LLM API key/model、LE 邮箱、bundle 路径、smoke account/password；DB/JWT 用 OpenSSL 自动生成；文件 0600；日志无 secrets；UFW 只添加 80/443。

- [ ] **Step 3: 实现官方 Docker apt 安装与引导顺序**

顺序固定：系统检查→Docker/Git/curl/openssl/ufw→swap→UFW→clone main→secrets→bundle import→build→migrate→bootstrap nginx→cert issue→production nginx→smoke→安装 timer 和 `/opt/onetree/bin` 命令。

- [ ] **Step 4: 验证与提交**

Run: `bash deploy/tests/test_bootstrap.sh && shellcheck deploy/bin/bootstrap`
Expected: PASS。

Commit: `git commit -m "feat: add one-command server bootstrap"`

### Task 7: Phase 3 集成门禁

**Files:**
- Create: `deploy/compose.ci.yml`，只用于不访问公网 ACME 的本地与 CI 集成测试。

- [ ] **Step 1: 运行全部 shell 测试**

Run: `for test_file in deploy/tests/test_*.sh; do bash "$test_file"; done`
Expected: all PASS。

- [ ] **Step 2: 构建并启动生产等价栈**

Run: `docker compose -f deploy/compose.production.yml -f deploy/compose.ci.yml up -d --build`
Expected: postgres/backend/worker/nginx healthy。

- [ ] **Step 3: 运行 CI smoke 后清理非持久测试栈**

Run: `docker compose -f deploy/compose.production.yml -f deploy/compose.ci.yml run --rm smoke`
Expected: live、ready、首页、登录、me 全部成功。
