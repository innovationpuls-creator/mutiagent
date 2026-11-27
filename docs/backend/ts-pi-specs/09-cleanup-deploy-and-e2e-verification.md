# M9 开发文档：旧架构清退、生产部署适配与全链路回归验收

> 文档日期：2026-11-27  
> 对应里程碑：M9（前置依赖：M3、M7、M8 全部完成）  
> 上位文档：`docs/backend/ts-pi-agent-redesign.md`、`docs/backend/ts-pi-specs/00-roadmap-and-milestones.md`

---

## 1. 目标范围与前置依赖

### 1.1 目标范围
在 M1–M8 全部业务模块完成切流并单独验收通过后，执行最终的**旧编排代码与依赖清退**、**容器化与生产部署面适配（Docker Compose / Nginx / Smoke）**、**项目技术文档与 OpenAPI 同步**，以及**全链路端到端回归验收**，正式完成 OneTree AI 编排层向 TypeScript（`LangGraph.js` + `Pi`）的全面切换。

---

## 2. 现有源码盘点与清理/改造清单

1. **Python 依赖与旧编排目录清退**（`backend/pyproject.toml`、`backend/app/orchestration/`）
   - 移除 `pyproject.toml` 中的 `langchain`、`langchain-openai`、`langgraph`（及不再需要的 `dashscope`，如外部视频检索也已完整迁至 TS 侧），重新锁定 `backend/uv.lock`。
   - 清理 `backend/app/orchestration/` 下已被 TS 网关完全替代的旧 `graph.py`、`llm.py`、`rule_engine.py`、`agents/*` 以及 `backend/app/api/chat_handlers.py` 中已废弃的编排代码（保留仍在 Python 侧使用的纯数据契约工具或移至 `app/services/`）。
   - 清理 `backend/app/core/config.py` 中生产环境强制校验旧 `LLM_API_KEY` / `LLM_MODEL` 的条款，替换为校验内部通信密钥 `INTERNAL_API_TOKEN`、`AI_GATEWAY_URL` 与凭据加密主密钥 `MODEL_SECRET_ENCRYPTION_KEY`。
2. **容器化与生产部署编排适配**（`ai-gateway/Dockerfile`、`deploy/compose.production.yml`、`deploy/compose.ci.yml`、`deploy/env.production.example`）
   - 为 `ai-gateway` 编写多阶段生产 `Dockerfile`（Node 22 Alpine/Slim、非 root 运行、内置健康检查）。
   - 在 `deploy/compose.production.yml` 与 `compose.ci.yml` 新增 `ai-gateway` 服务：配置健康检查（`/api/ai/health/ready`）、`journald` 日志驱动（`tag: onetree-ai-gateway`）、环境变量（`JWT_SECRET`、`INTERNAL_API_TOKEN`、`PYTHON_BACKEND_URL`、`ALLOWED_ORIGINS`）。
   - `nginx` 服务增加对 `ai-gateway` 健康状态的依赖；`backend` 与 `worker` 增加 `AI_GATEWAY_URL`、`INTERNAL_API_TOKEN`、`MODEL_SECRET_ENCRYPTION_KEY` 环境变量。
3. **Nginx 生产路由模板对齐**（`deploy/nginx/conf.d/production.conf.template`、`production-ip.conf.template`）
   - 确认以下路径精确转发至 `http://ai-gateway:8100`（全部保留 `$maintenance_marker` 503 维护拦截、`X-Request-ID` 透传、长连接超时 `300s`）：
     - `/api/ai/`
     - `= /api/chat/message`
     - `= /api/forest/ai/stream`
     - `= /api/branch/canopy/report/stream`
   - 显式拦截外网 `/internal/` 路径（返回 `404`）。
4. **Smoke 探测与项目文档同步**（`deploy/bin/smoke`、`docs/`）
   - 扩展 `deploy/bin/smoke` 增加对 `/api/ai/health/live` 与 `/api/ai/health/ready` 的存活/就绪探测。
   - 重新运行 `frontend` 的 `npm run gen:api` 对齐最终 `openapi.json` 与 `src/types/api.ts`。
   - 同步更新 `docs/project-overview.md`、`docs/backend/agent逻辑.md`、`docs/backend/backend-tech-stack.md`、`docs/database/数据库表结构.md`，使仓库文档 100% 忠于重构后的真实代码。

---

## 3. 风险点与上线切换检查

1. **环境变量漏配导致生产启动失败**：在 `deploy/env.production.example` 与部署文档中显式标注所有新增必填变量（`INTERNAL_API_TOKEN`、`MODEL_SECRET_ENCRYPTION_KEY`、`AI_GATEWAY_URL`），并确保生产启动脚本做前置存在性检查。
2. **老测试依赖旧 `app.orchestration` 路径**：清退旧目录前，将后端旧测试中属于“数据服务/契约验证”的用例保留并调整导入，属于“旧 LangGraph 编排”的测试由 `ai-gateway` 侧同等覆盖率的单测与集成测试承接，确保总体测试覆盖率不降反升。
3. **升级迁移兼容性**：在包含历史数据的测试库上从 `0001` 完整滚动升级至 `0009`（最新 head），验证既有用户、画像、路径、大纲、测验、知识库记录零丢失、零破坏。

---

## 4. M9 最终全链路验收清单（项目收官达标线）

| 编号 | 验收维度 | 具体验证步骤 | 预期达成结果 |
|---|---|---|---|
| **AC-1** | Python 旧依赖彻底清退 | 检查 `backend/pyproject.toml`、`uv.lock` 与 `backend/app/`；运行 `cd backend && uv run pytest -q` 与 `ruff check` | 完全不含 `langchain`、`langgraph`、`langchain-openai`；后端全部单元测试与静态检查全绿。 |
| **AC-2** | TS 编排网关质量门禁 | 在 `ai-gateway/` 运行类型检查、Lint、全部单元测试与集成测试 | 零类型错误、零 Lint 警告、全部测试通过。 |
| **AC-3** | 前端构建与契约对齐 | 在 `frontend/` 运行 `npm run gen:api`、`npm test`、`npm run build` 与 Biome 检查 | OpenAPI 与生成类型无漂移，单测与生产构建全绿。 |
| **AC-4** | 数据库全量迁移演练 | 在全新独立测试库执行 `alembic upgrade head`，并验证从旧基线滚动升级至最新迁移 | 迁移无报错；所有表约束、索引与历史数据完整兼容。 |
| **AC-5** | 全链路端到端实测 | 启动 PostgreSQL + Python 后端 + `ai-gateway` + 前端，走通完整用户闭环：<br>① 新学生登录 → 未配置模型拦截跳转 → 配置个人模型 + 探针测试<br>② 萌芽对话画像采集（卡片 + 自纠）<br>③ 课程草案（问答/风险确认/知识缺口保留）→ 正式按年路径<br>④ 课程大纲（含超 8000 字拆节 & 全年并发）<br>⑤ 小节多模态资源（视频动画并行、首节可读、视频平稳降级、重生成显式状态）<br>⑥ 成林测验（出题、单选规则判分、图片真实视觉判分、断流恢复、Forest AI 提交前苏格拉底引导）<br>⑦ 成森成长报告（探索查证 + 防幻觉 + 溯源跳转）<br>⑧ 管理员配置个人模型执行公开教材搜书与外文教材入库翻译 | 全部 8 大环节端到端跑通，个人用量看板准确记录消耗，无 500 错误或契约断裂。 |
| **AC-6** | 生产 Compose 与 Smoke 验收 | 使用 `deploy/compose.ci.yml` / 生产模板构建并启动全套容器，执行 `deploy/bin/smoke` 并测试外网访问 `/internal/health` | 全容器健康启动，Smoke 探针全绿，外网访问 `/internal/*` 返回 `404`。 |
| **AC-7** | 仓库文档核对一致 | 核对 `docs/project-overview.md`、`docs/backend/agent逻辑.md`、`docs/backend/backend-tech-stack.md`、`docs/database/数据库表结构.md` | 文档描述与当前最终代码、接口、表结构完全一致。 |
