# OneTree Production Baseline Master Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Ubuntu 24.04 x86_64 单机上交付可备份、可恢复、可诊断并能一条命令发布的 OneTree Docker 生产基线。

**Architecture:** 按风险和依赖拆成四个子计划。先建立生产配置与观测边界，再把数据库升级和长任务变成可恢复基础设施，随后实现容器与发布系统，最后接入 CI、文档和真实服务器验收。

**Tech Stack:** FastAPI, SQLModel, Alembic, PostgreSQL 18, React 18, Vite, Docker Compose, nginx, Certbot 5.4+, GitHub Actions, Bash, systemd.

## Global Constraints

- 所有标识符、路径、JSON 字段和配置键必须来自已批准设计或当前仓库真实文件，禁止格式匹配猜测。
- 后端改动必须运行 `uv run ruff check --fix` 和 `uv run ruff format`。
- 前端改动前必须加载 `/web-design-engineer` skill 的 Headspace meditation 风格，并按设计系统文档执行；改动后运行 `npx biome check --write`。
- 后端 Pydantic 请求或响应契约变化后必须在 `frontend/` 执行 `npm run gen:api`。
- 生产数据库迁移只能由 Alembic 执行；FastAPI 启动不得创建、修改或删除表。
- 生产环境不得使用默认 JWT 密钥、任意公网 CORS 或自动 demo 账号。
- 普通部署、停止、启动、回滚脚本禁止执行 `docker compose down -v`。
- 完整学习流程继续人工验证；自动烟雾测试只检查服务、数据库、首页和真实登录。
- 生产域名固定为 `onetree.chat` 与 `www.onetree.chat`，并保留固定公网 IPv4 的可信 HTTPS。
- PostgreSQL 和教材文件每次部署前备份，只保留最近 3 个校验完整的快照。
- Docker 日志进入 journald，`MaxRetentionSec=7day`，`SystemMaxUse=2G`。
- 每个任务严格执行 RED → GREEN → REFACTOR；没有观察到预期失败的测试不得进入生产实现。

---

## 子计划与顺序

- [ ] **Phase 1:** 执行 `docs/superpowers/plans/2026-07-13-production-security-observability.md`。
- [ ] **Phase 2:** 执行 `docs/superpowers/plans/2026-07-13-database-worker-recovery.md`。
- [ ] **Phase 3:** 执行 `docs/superpowers/plans/2026-07-13-docker-deployment-certificates.md`。
- [ ] **Phase 4:** 执行 `docs/superpowers/plans/2026-07-13-ci-documentation-acceptance.md`。

## 阶段门禁

- [ ] Phase 1 结束：生产配置、JWT、CORS、demo seed、request ID 和真实数据库健康检查定向测试全部通过。
- [ ] Phase 2 结束：全量后端测试不再耗尽 PostgreSQL locks；空库和当前库均到 Alembic head；worker 可接管过期租约；导出恢复 roundtrip 通过。
- [ ] Phase 3 结束：Compose 配置、nginx、备份恢复、发布回滚、bootstrap 与证书脚本测试全部通过。
- [ ] Phase 4 结束：GitHub Actions 全绿，中文部署文档逐命令复核，干净 Ubuntu 服务器 15 项验收证据全部归档。
