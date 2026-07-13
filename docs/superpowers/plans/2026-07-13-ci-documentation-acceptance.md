# CI, Documentation, and Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将全部生产基线检查变成 GitHub 门禁，交付可复制中文文档，并在真实 Ubuntu 服务器逐项证明上线条件。

**Architecture:** GitHub Actions 按 backend/migration/frontend/containers/smoke 分 job；部署文档只引用已经由脚本测试验证的命令。最终验收同时使用 CI、故障注入和真实服务器输出，不用局部测试替代整体证据。

**Tech Stack:** GitHub Actions, PostgreSQL 18 service container, uv, npm, Biome, Vitest, Docker Compose, shellcheck, Markdown.

## Global Constraints

- CI 触发范围：pull request 与 `main` push。
- CI 不调用真实 LLM，不申请正式证书。
- OpenAPI drift 必须执行生成命令后使用 Git diff 判断。
- 文档必须覆盖首次迁移、部署、更新、停止、日志、证书、恢复和回滚。
- 真实服务器验收完成前不得宣称项目可以安全上线。

---

### Task 1: GitHub Actions 生产门禁

**Files:**
- Modify: `.gitignore`
- Create: `.github/workflows/production.yml`
- Modify: `deploy/compose.ci.yml`

**Interfaces:**
- Jobs: `backend`, `migration`, `frontend`, `containers`, `smoke`。

- [ ] **Step 1: 先让 workflow 可被 Git 跟踪**

将 `.gitignore` 的整目录 `.github` 忽略改为只忽略未批准内容，并精确允许 `.github/workflows/production.yml`。运行 `git check-ignore -v .github/workflows/production.yml`，预期不再被忽略。

- [ ] **Step 2: 编写 backend job**

PostgreSQL 18 service 配置健康检查；执行 `uv sync --extra test`、`uv run ruff check app tests`、`uv run ruff format --check app tests`、`uv run pytest -q`。不得通过调高 locks 参数让测试通过。

- [ ] **Step 3: 编写 migration job**

对空数据库执行 `alembic upgrade head`、`alembic current` 并精确断言 head；对由当前 models 创建的未版本库执行 schema 验证、stamp/upgrade、current=head；运行旧 schema migration tests。

- [ ] **Step 4: 编写 frontend job**

执行 `npm ci`、`npx biome check .`、`npm test -- --run`、`npm run build`、`npm run gen:api`，然后 `git diff --exit-code -- frontend/openapi.json frontend/src/types/api.ts`。

- [ ] **Step 5: 编写 containers 与 smoke jobs**

执行 `shellcheck deploy/bin/* deploy/lib/*.sh deploy/tests/*.sh`、全部 shell tests、`docker compose config --quiet`、build。CI override 使用 HTTP 本地入口和 fixture 账号，不运行 ACME；启动后执行 migrate 与 smoke。

- [ ] **Step 6: 本地语法验证与提交**

Run: `docker compose -f deploy/compose.production.yml -f deploy/compose.ci.yml config --quiet`
Expected: exit 0。

Run: `git diff --check`
Expected: exit 0。

Commit: `git commit -m "ci: enforce production readiness gates"`

### Task 2: 中文部署与恢复文档

**Files:**
- Create: `docs/deployment/docker-production.md`
- Modify: `README.md`

**Interfaces:**
- Canonical commands: `deploy/bin/export-local-data`, server bootstrap command, `/opt/onetree/bin/deploy`, `/opt/onetree/bin/rollback <backup-id>`。

- [ ] **Step 1: 写完整文档**

按批准设计第 13 节逐项写：ICP备案/DNS、local export、OrcaTerm/SFTP/scp 上传、bootstrap、交互字段、update、日志、stop/start、证书状态/手动续期、Alembic revision、restore/rollback、磁盘/轮转和故障诊断。

- [ ] **Step 2: 验证所有文档命令真实存在**

为每个 `/opt/onetree/bin/*` 命令映射仓库 `deploy/bin/*`；使用 `rg` 提取文档代码块中的项目脚本路径，逐个 `test -x`；禁止写尚不存在的命令。

- [ ] **Step 3: README 增加生产入口**

明确当前 README 的 `uvicorn --reload` 和 `npm run dev` 仅用于本地开发；生产部署链接到中文文档，不复制第二套命令。

- [ ] **Step 4: 文档检查与提交**

Run: `git diff --check -- README.md docs/deployment/docker-production.md`
Expected: exit 0。

Commit: `git commit -m "docs: add Docker production runbook"`

### Task 3: 备案号可配置展示

**Files:**
- Create: `frontend/src/components/layout/IcpFilingLink.tsx`
- Create: `frontend/src/components/layout/IcpFilingLink.module.css`
- Create: `frontend/src/components/layout/IcpFilingLink.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`

**Interfaces:**
- Build key: `VITE_ICP_BEIAN_NUMBER`。
- Link target: `https://beian.miit.gov.cn/`。

- [ ] **Step 1: 加载前端技能与设计文档**

必须先读取 `/web-design-engineer` skill，并按需读取颜色、字体、间距、圆角阴影、materials、motion 与 session design 文档；本任务只增加页脚备案链接，不重做页面。

- [ ] **Step 2: 验证 App 根布局挂载点**

Run: `cd frontend && rg -n "<AnimatedRoutes|<AppGlobalAiWidget" src/App.tsx`
Expected: `App.tsx` 同时挂载路由和全局 AI widget；备案组件作为第三个全局子节点挂载，覆盖登录、学生和管理页面。

- [ ] **Step 3: 写条件渲染红测**

无 `VITE_ICP_BEIAN_NUMBER` 时不显示空链接；配置精确备案号时显示相同文本并链接工信部，`target`/`rel` 按现有外链约定。

- [ ] **Step 4: 实现并验证**

只使用现有 OKLCH/token、LXGW WenKai、`--space-*` 与现有阴影；无布局动画。运行 `npx biome check --write <changed-files>`、定向测试、`npm run build`。

Commit: `git commit -m "feat: display configurable ICP filing"`

### Task 4: 故障注入与真实服务器验收

**Files:**
- Create: `docs/deployment/acceptance/README.md`
- Create: `deploy/bin/acceptance-check`
- Create: `deploy/tests/test_acceptance_check.sh`

**Interfaces:**
- Evidence directory: `/opt/onetree/acceptance/<UTC timestamp>/`。

- [ ] **Step 1: 写验收检查红测**

stub 每项依赖，断言 15 项设计验收任何一项失败时整体非零；每项生成带时间与命令 exit code 的独立文本证据；输出不得包含 secrets。

- [ ] **Step 2: 实现本地可自动部分**

检查 Compose 服务/端口、HTTPS、redirect、cert SAN/expiry、production secret rejection test、demo absence、ready DB failure/recovery、request ID、volume persistence、CI commit、文档命令存在。

- [ ] **Step 3: 执行故障注入**

在维护态测试库/volume 上分别触发 migration failure、new app health failure、worker running interruption；验证对应 backup-id 数据、教材 hash、旧 commit/容器恢复。不得在未备份的生产数据上故障注入。

- [ ] **Step 4: 干净 Ubuntu 24.04 真实 bootstrap**

在目标服务器执行文档中的唯一 bootstrap 命令，导入真实迁移包；保存安装、构建、migration、证书和 smoke 输出到 evidence directory。

- [ ] **Step 5: 运行 15 项最终检查**

Run: `/opt/onetree/bin/acceptance-check`
Expected: 15/15 PASS，exit 0。

- [ ] **Step 6: 人工学习流程验收**

用户使用真实 LLM 完成登录→学习路径→课程内容→测验流程并明确反馈结果；自动化不替代此项人工确认。

- [ ] **Step 7: 最终全仓验证**

Run: `cd backend && uv run ruff check app tests && uv run ruff format --check app tests && uv run pytest -q`
Expected: 0 failures。

Run: `cd frontend && npx biome check . && npm test -- --run && npm run build`
Expected: 0 failures，build exit 0。

Run: `for test_file in deploy/tests/test_*.sh; do bash "$test_file"; done`
Expected: all PASS。

Commit: `git commit -m "test: verify production recovery baseline"`
