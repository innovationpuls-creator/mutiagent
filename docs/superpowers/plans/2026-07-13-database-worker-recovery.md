# Database, Worker, and Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用稳定测试基础设施、Alembic、PostgreSQL 持久化 worker 和可校验快照替代启动时 DDL 与请求内长任务。

**Architecture:** 先修复测试 schema 生命周期，再建立空库与现有库两条明确 Alembic 路径。worker 通过 PostgreSQL lease 和 `FOR UPDATE SKIP LOCKED` claim；数据迁移与部署快照都使用 hash manifest 和原子提交。

**Tech Stack:** PostgreSQL 18, Alembic, SQLModel, pytest, Bash, pg_dump/pg_restore, tar, SHA-256.

## Global Constraints

- 不得通过调大 `max_locks_per_transaction` 掩盖测试 schema 泄漏。
- 不得对结构未经精确验证的现有数据库盲目 `alembic stamp`。
- `schema_upgrades.py` 在旧 schema 覆盖迁入 Alembic 前不得删除。
- worker 不得使用仅存在于进程内存的队列。
- 恢复必须同时恢复 Git commit/镜像、数据库和教材文件。
- 迁移包固定成员：`database.dump`, `knowledge-base-uploads.tar`, `manifest.json`。

---

### Task 1: 修复 PostgreSQL 测试 schema 生命周期

**Files:**
- Modify: `backend/tests/postgres.py`
- Modify: `backend/tests/conftest.py`
- Create: `backend/tests/test_postgres_test_support.py`

**Interfaces:**
- Produces: `drop_postgresql_test_schema(database_url: str) -> None`。
- Produces: 每个测试 schema 在所属 fixture 结束时立即独立事务 DROP。

- [ ] **Step 1: 写锁泄漏红测**

创建多个 `postgresql_test_url`，调用新 cleanup 接口后查询 `information_schema.schemata`，断言对应精确 schema 全部不存在；再断言每次 DROP 使用独立提交而非 session 末尾单一事务。

- [ ] **Step 2: 运行红测**

Run: `cd backend && uv run pytest tests/test_postgres_test_support.py -q`
Expected: FAIL，因为 cleanup 接口不存在。

- [ ] **Step 3: 实现 registry 与即时清理**

URL 返回值必须保留精确 schema；清理从 SQLAlchemy URL 的 `options=-c search_path=<schema>` 读取已生成 schema，不做名称猜测。session autouse 只清理异常遗留，每个 DROP 单独 `engine.begin()`。

- [ ] **Step 4: 运行全量测试证明根因消失**

Run: `cd backend && uv run pytest -q`
Expected: 完整结束，0 failures，输出不含 `out of shared memory` 或 `max_locks_per_transaction`。

- [ ] **Step 5: Ruff 与提交**

Commit: `git commit -m "test: bound PostgreSQL schema lifecycle"`

### Task 2: 建立 Alembic 唯一迁移入口

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/alembic.ini`
- Create: `backend/migrations/env.py`
- Create: `backend/migrations/script.py.mako`
- Create: `backend/migrations/versions/0001_production_baseline.py`
- Create: `backend/app/migration_state.py`
- Modify: `backend/app/database.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_alembic_migrations.py`
- Modify: `backend/tests/test_schema_upgrades.py`

**Interfaces:**
- Produces: `inspect_schema_state(engine: Engine) -> SchemaState`，状态只允许 `empty`, `current_unversioned`, `legacy`, `versioned`。
- Produces: `assert_schema_at_head(engine: Engine) -> None`，供 readiness 使用。

- [ ] **Step 1: 写空库和当前库红测**

空 PostgreSQL schema 执行 `alembic upgrade head` 后，比较 `inspect(engine).get_table_names()` 与 `SQLModel.metadata.tables` 精确表名集合并断言 `alembic current` 为 head。当前 SQLModel schema 无 `alembic_version` 时，`inspect_schema_state` 必须返回 `current_unversioned`；缺列或类型不符时不得返回该值。

- [ ] **Step 2: 写生产启动无 DDL 红测**

patch `run_schema_upgrades`、`SQLModel.metadata.create_all`、`migrate_removed_learning_path_table` 为抛错函数，调用 production `create_app` 并断言不会触发。

- [ ] **Step 3: 运行红测**

Run: `cd backend && uv run pytest tests/test_alembic_migrations.py -q`
Expected: FAIL，因为 Alembic 与 schema state 接口不存在。

- [ ] **Step 4: 实现 baseline 与现有库验证 stamp**

`0001_production_baseline.upgrade()` 在空库基于当前 SQLModel metadata 创建全部表；现有库只有在精确表、列、类型、主键和约束检查通过时才允许 stamp。legacy 状态必须运行从现有 `schema_upgrades.py` 提取并冻结的有版本迁移，且保留现有测试覆盖的每种数据转换。

- [ ] **Step 5: 切断 production 启动 DDL**

`create_app` 只 build engine 并调用 `assert_schema_at_head`；测试/开发 fixture 显式调用建表或 Alembic。`init_db` 不再是 production 入口。

- [ ] **Step 6: 补 readiness revision 测试**

修改 `backend/tests/test_health_api.py`，增加 revision 落后时 503、head 时 200。

- [ ] **Step 7: 验证与提交**

Run: `cd backend && uv run pytest tests/test_alembic_migrations.py tests/test_schema_upgrades.py tests/test_health_api.py -q`
Expected: PASS。

Commit: `git commit -m "feat: version production database schema"`

### Task 3: PostgreSQL 持久化教材 worker

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/schemas.py`
- Create: `backend/migrations/versions/0002_ingestion_job_leases.py`
- Create: `backend/app/workers/__init__.py`
- Create: `backend/app/workers/__main__.py`
- Create: `backend/app/workers/knowledge_base_worker.py`
- Modify: `backend/app/services/knowledge_base_service.py`
- Modify: `backend/app/api/knowledge_base.py`
- Modify: `frontend/src/api/knowledgeBase.ts`
- Modify: `frontend/src/pages/admin/AdminKnowledgeBasePage.tsx`
- Modify: `frontend/src/pages/admin/AdminKnowledgeBasePage.test.tsx`
- Create: `backend/tests/test_knowledge_base_worker.py`
- Modify: `backend/tests/test_knowledge_base_ingestion_job.py`
- Modify: `backend/tests/test_knowledge_base_api.py`

**Interfaces:**
- Adds exact job fields: `attempt_count`, `max_attempts`, `available_at`, `lease_expires_at`, `worker_id`, `request_id`, `updated_at`。
- Produces: `claim_next_ingestion_job(session: Session, worker_id: str, now: datetime) -> KnowledgeBaseIngestionJob | None`。
- Produces: `run_worker(poll_seconds: float) -> None`。

- [ ] **Step 1: 写并发 claim 与 lease 红测**

两个真实 PostgreSQL Session 同时 claim 同一 queued job，断言只有一个返回 job；未过期 running job 不接管；过期 lease 在 attempt 未达上限时重新 claim；达上限时变为 failed。

- [ ] **Step 2: 写 API 快速返回红测**

patch 教材解析函数为抛错，POST organize/run API 后断言返回 queued 且解析函数未调用；GET job 可轮询状态。

- [ ] **Step 3: 运行红测**

Run: `cd backend && uv run pytest tests/test_knowledge_base_worker.py tests/test_knowledge_base_api.py -q`
Expected: FAIL，因为 claim 与 worker 不存在且 run API 同步执行。

- [ ] **Step 4: 实现 lease claim 和执行边界**

claim 必须在同一事务使用 `with_for_update(skip_locked=True)` 完成 queued→running。业务执行函数接收已 claim job，不重复执行 queued 状态校验；成功/失败更新 job 与 textbook 状态并提交。

- [ ] **Step 5: 修改 API 与前端轮询**

API 只入队并返回 202/queued。更新生成类型与 `knowledgeBase.ts`；`AdminKnowledgeBasePage.tsx` 按现有 GET job 路由轮询到 terminal 状态，不引入新字段猜测。

- [ ] **Step 6: 前端规范与验证**

在修改任何前端文件前读取 `/web-design-engineer` skill 和相关设计系统文档；修改后运行 `npx biome check --write <changed-files>`、`npm run gen:api`、定向 Vitest 和 `npm run build`。

- [ ] **Step 7: 后端验证与提交**

Run: `cd backend && uv run pytest tests/test_knowledge_base_worker.py tests/test_knowledge_base_ingestion_job.py tests/test_knowledge_base_api.py -q`
Expected: PASS。

Commit: `git commit -m "feat: run ingestion in durable worker"`

### Task 4: 可校验本地导出与首次导入

**Files:**
- Create: `deploy/lib/migration_manifest.py`
- Create: `deploy/bin/export-local-data`
- Create: `deploy/bin/verify-bundle`
- Create: `deploy/bin/import-bundle`
- Create: `backend/tests/deployment/test_migration_manifest.py`
- Create: `deploy/tests/test_migration_roundtrip.sh`

**Interfaces:**
- Bundle members are exactly `database.dump`, `knowledge-base-uploads.tar`, `manifest.json`。
- `manifest.json` includes UTC timestamp, Alembic revision, per-file byte size and SHA-256; no secrets.

- [ ] **Step 1: 写 manifest 红测**

测试正确 bundle 通过；缺成员、hash 错、size 错、额外绝对路径、`../` path、manifest 含 `DATABASE_URL`/`JWT_SECRET`/`LLM_API_KEY` 时失败且不写目标目录。

- [ ] **Step 2: 运行红测**

Run: `cd backend && uv run pytest tests/deployment/test_migration_manifest.py -q`
Expected: FAIL，因为模块不存在。

- [ ] **Step 3: 实现本地导出**

只从 `backend/.env` 精确读取 `DATABASE_URL`，缺失就失败；教材源路径参数默认精确为仓库 `backend/.codex-artifacts/knowledge-base-uploads` 并打印确认；使用 `pg_dump --format=custom`，不打印 URL。

- [ ] **Step 4: 实现校验后原子导入**

先在 staging 目录完整验证，再 `pg_restore` 到明确维护态目标库；教材 tar 解压到 staging，拒绝 path traversal，最后原子替换目标目录。

- [ ] **Step 5: 运行 PostgreSQL 18 roundtrip**

Run: `bash deploy/tests/test_migration_roundtrip.sh`
Expected: 管理员、`18771701100`、`18771701111` 与教材层级/hash 全部一致。

Commit: `git commit -m "feat: add verified production data transfer"`

### Task 5: 部署前备份、恢复与最近三份轮转

**Files:**
- Create: `deploy/lib/backup_manifest.py`
- Create: `deploy/bin/backup`
- Create: `deploy/bin/restore`
- Create: `backend/tests/deployment/test_backup_manifest.py`
- Create: `deploy/tests/test_backup_restore.sh`

**Interfaces:**
- Snapshot contains exactly `database.dump`, `knowledge-base-uploads.tar`, `manifest.json`。
- Manifest includes UTC timestamp, Git commit, Alembic revision, file sizes and hashes.

- [ ] **Step 1: 写原子快照与轮转红测**

断言 pg_dump/tar/hash 任一步失败时不产生完整 snapshot；新快照完整后才轮转；仅最近 3 个完整 snapshot 保留；源教材目录从不被轮转删除。

- [ ] **Step 2: 写恢复保护红测**

hash 错误时 restore 必须在执行 `pg_restore` 和修改教材目录前失败；正确快照恢复后 DB 行与教材 hash 匹配。

- [ ] **Step 3: 实现并运行测试**

Run: `cd backend && uv run pytest tests/deployment/test_backup_manifest.py -q && cd .. && bash deploy/tests/test_backup_restore.sh`
Expected: PASS。

- [ ] **Step 4: Phase 2 全回归**

Run: `cd backend && uv run pytest -q`
Expected: 完整结束，0 failures，无 PostgreSQL lock exhaustion。

Commit: `git commit -m "feat: add atomic production recovery"`
