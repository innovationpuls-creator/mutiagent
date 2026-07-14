# AGENTS.md

## 项目边界

这是 OneTree 全栈单体仓库：

- `frontend/`：React 18、TypeScript、Vite，负责学生端和管理端。
- `backend/`：FastAPI、SQLModel、LangGraph、LangChain，负责 API、SSE 编排、知识库和持久化。
- `deploy/`：生产 Docker Compose、Nginx、迁移、备份、证书和 smoke 脚本。
- `docs/`：架构、接口、数据库、部署、UI 规范和验收资料。

前端、后端的专属规则分别位于 `frontend/AGENTS.md` 和 `backend/AGENTS.md`。

## 工作规则

- 不猜测标识符、路径、字段、配置键或数据结构；先读取源码、测试、配置或日志。
- 如果仓库无法提供精确信息，先向用户询问，不自行补全。
- 优先并行读取和验证；临时验证文件使用完立即删除。
- 只修改当前请求直接涉及的内容，保留用户已有的未提交改动。
- 新增或修改行为时补充针对性测试；文档中的命令和路径必须来自仓库现状。
- 保持强类型、清晰的模块边界和最小改动。

## 常用验证

```bash
cd backend && uv run pytest -q
cd frontend && npm test && npm run build
cd frontend && npm run e2e
```

后端 Python 修改后运行 `uv run ruff check --fix` 和 `uv run ruff format`。前端 JS/TS/JSX/TSX 修改后运行 `npx biome check --write`。后端 Pydantic 请求/响应模型变化后，在 `frontend/` 运行 `npm run gen:api`。

本地开发分别启动：

```bash
cd backend && uv run uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
```

生产环境使用 `deploy/bin/bootstrap`、`deploy/bin/deploy` 和 `docs/deployment/docker-production.md`，不要用开发服务器替代生产部署。

## 文档事实来源

- 项目现状和模块关系：`docs/project-overview.md`
- 后端架构和 API 分组：`docs/backend/backend-tech-stack.md`
- Agent 详细执行记录：`docs/backend/agent逻辑.md`
- API 字段：`docs/api-specs/` 与后端路由、生成的 `frontend/openapi.json`
- 数据库字段：`backend/app/models.py`、`backend/migrations/versions/` 和 `docs/database/数据库表结构.md`

代码与文档冲突时，以当前代码、测试和配置为准，并在同一变更中修正文档。

## Git

Commit 格式：`<type>: <描述>`，type 取 `feat`、`fix`、`refactor`、`docs`、`test`、`chore`、`perf`、`ci`。
