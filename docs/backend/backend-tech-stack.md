# Backend 技术文档

> 本文是当前源码快照。最后全面核对：2026-11-27。代码、测试和配置变更后应同步更新本文。

系统由两个服务组成：**Python 后端**（FastAPI，本文主角）是数据核心，负责认证、持久化、确定性契约校验和 `/internal/*` 数据接口；**TypeScript AI 网关**（`ai-gateway/`，Hono + LangGraph.js + Pi `Agent`，端口 8100）负责全部模型编排与 SSE，详见 [Agent 逻辑](agent逻辑.md) 与 [TS/Pi 重构设计](ts-pi-agent-redesign.md)。Python 后端**不再依赖** LangChain / LangGraph；模型凭据按用户保存，由网关按场景解析。知识库教材整理是独立的数据库任务 worker。

## 启动

```bash
cd backend
uv run uvicorn app.main:app --reload --port 8000

cd ai-gateway
npm install && npm run dev   # 默认 127.0.0.1:8100
```

## 技术栈

| 层级 | 技术 | 用途 |
|---|---|---|
| Web 框架 | FastAPI | REST API（含 `/internal/*` 内部接口） |
| AI 编排 | TypeScript 网关：Hono + `@langchain/langgraph` + Pi `Agent` | 对话图、工具调用、SSE、出题/批改、成长报告、知识库 AI |
| Python→网关 | `app/services/ai_gateway_client.py` | 带 `X-Internal-Token` 的 `/internal/ai/*` 调用与错误映射 |
| 数据库 | PostgreSQL 18 + psycopg2 | 生产存储与独立隔离 schema 测试 |
| ORM | SQLModel | 模型定义、Session 管理 |
| JSON 存储 | PostgreSQL JSONB | 画像、路径、课程大纲、会话消息 |
| 认证 | python-jose + bcrypt | Bearer token 认证（网关复用同一 `JWT_SECRET` 验签） |
| 模型接入 | 用户自带模型（OpenAI 兼容 / OAuth 订阅等），按场景绑定 | 凭据用 `MODEL_SECRET_ENCRYPTION_KEY` 加密保存 |
| 视频检索 | 阿里云 DashScope（Bilibili 搜索） | 唯一保留的 Python 侧模型调用，平台密钥可选，缺失则视频降级 |

## 架构总览

```text
浏览器 --JWT--> Nginx
  /api/ai/*  /api/chat/message  /api/forest/ai/stream  /api/branch/canopy/report/stream  -> ai-gateway:8100
  其余 /api/*                                                                              -> backend:8000
  /internal/*                                                                              -> 404（仅容器网络内可达）

ai-gateway --X-Internal-Token--> backend /internal/*   （上下文、校验、保存、锁）
backend    --X-Internal-Token--> ai-gateway /internal/ai/*   （出题、批改、KB 翻译/搜书）
```

一轮对话：网关校验 JWT → 从 `/internal/chat/sessions/{id}/context` 读取会话/画像/路径/大纲 → `StateGraph` 单次执行（`entry → supervisor → 各 Agent → finalize`）→ SSE 输出 → `/internal/chat/sessions/{id}/turn` 落库 → 输出 `message_completed` / `session_completed`。

### 数据库操作与模型等待

同步数据库路由使用 `def`。聊天、测验、资源生成和成长报告按“短事务读取上下文 → 等待模型 → 短事务写入结果”执行；认证查询也在独立短 Session 中完成。`database.run_db` 在线程池内创建、使用并关闭绑定当前应用 engine 的 Session，返回已加载的数据或完整 DTO，不在线程之间共享 Session。

Agent 的同步数据库 helper 整段在线程中执行。聊天只在推进 SSE 生成器期间绑定请求 engine，输出事件前恢复上下文，提前关闭亦可安全清理。发生事务失败时，用户消息回退使用新 Session。生产启动只检查 Alembic head，不执行开发模式的 `init_db`；开发空 schema 直接创建当前模型，非空 schema 仍走历史兼容升级。

知识库管理员 Agent 的普通与 SSE HTTP 入口传入绑定应用 engine 的 Session factory；计数、查重和缺口查询分别在短 Session 内完成，关闭后才联网搜索或输出事件。直接传入 Session 的内部服务调用仍由调用者管理事务，保留未提交数据的可见性。SSE 保持同步生成器，并在退出时关闭内层生成器。

教材上传继续异步分块读取并执行 100 MiB 限额检查；字节拼接在线程池完成，文件落盘、教材与整理任务持久化及响应 DTO 构造在工作线程自己的 Session 中完成。请求 Session 和 UploadFile 不跨线程，教材与任务仍按现有顺序分次提交。

教材检索通过 `search_published_textbooks` 按标题、标签和关键词匹配已发布教材；教材切片使用标题偏移索引，MarkItDown 在转换时导入。历史性能边界见 [性能报告](backend-performance-profile.md)。

## AI 能力划分

模型编排全部在网关，Python 只提供确定性部分：

| 能力 | 网关 | Python 内部接口（`/internal/...`） |
|---|---|---|
| 画像采集 | `profileAgent` | `chat/sessions/*`、`students/{uid}/profile` |
| 课程草案与按年路径 | `intakeAgent`、`pathAgent` | 草案契约校验、路径装配（`learning-paths/{grade_year}/assemble`）与保存 |
| 课程大纲 | `outlineAgent`（只命名） | 骨架与超 8000 字拆节、合规检查、带指纹原子保存（`course-outlines/*`） |
| 小节多模态资源 | `resourceAgent` | `courses/.../chapters/*/generation-prepare|finish`、`sections/*/markdown|video|animation`、`resources`（章节锁与检查点） |
| 测验出题 / 批改 | `ai/quiz.ts` | `students/{uid}/quiz-material`；forest 路由经 `acall_gateway_ai` 调用网关 |
| Forest AI / 成长报告 | `ai/forestAi.ts`、`ai/growthReport.ts` | `forest/chapters/.../material`、`canopy/{uid}/report-context|report-evidence|report-validate` |
| 知识库搜书 / 外文翻译 | `ai/kb.ts` | 由 `knowledge_base_service` 调用网关，使用管理员本人模型 |

`backend/app/orchestration/` 现仅保留不含模型调用的纯契约/校验工具（见 [Agent 逻辑 §7](agent逻辑.md)）。

### 知识库后台 Worker

`python -m app.workers` 启动 `knowledge_base_worker`，从 `KnowledgeBaseIngestionJob` 领取教材整理任务。领取按原排队顺序执行 `LIMIT 1 FOR UPDATE SKIP LOCKED`，任务使用数据库锁、租约、心跳、重试次数和失败状态，生产 Compose 中由 `worker` 服务运行。上传文件由 `KNOWLEDGE_BASE_UPLOAD_DIR` 指向的持久卷保存。

## 数据库模型

项目包含以下核心 SQLModel 数据库表（当前共 24 张表，字段与迁移以 `backend/app/models.py` 及 `backend/migrations/versions/` 为准；详见 [数据库表结构文档](../database/数据库表结构.md)）：

1. **User** (`user`)：用户账户及基本属性（角色：`student` / `admin`）。
2. **CultivationProgram** (`cultivationprogram`)：通用培养方案大纲模板。
3. **UserProfile** (`userprofile`)：用户个人画像特征及自然语言总结。
4. **UserYearLearningPath** (`useryearlearningpath`)：按学年生成的课程规划拓扑。
5. **UserCourseKnowledgeOutline** (`usercourseknowledgeoutline`)：单门课程的具体章节知识大纲。
6. **ChapterQuiz** (`chapterquiz`)：为章节动态生成的测验题集。
7. **ChapterQuizAttempt** (`chapterquizattempt`)：学生每次提交试卷的打分批改记录（含 `quiz_version` 与 `recovery_snapshot`）。
8. **ChapterProgress** (`chapterprogress`)：章节通关/解锁进度状态（`locked` / `available` / `passed`）。
9. **ChapterWeakness** (`chapterweakness`)：测验中暴露出的薄弱知识点记录。
10. **CourseResourceQuality** (`courseresourcequality`)：章节图文及动画生成质量评分。
11. **ConversationSession** (`conversationsession`)：会话消息历史持久化记录。
12. **KnowledgeSource** (`knowledgesource`)：知识库来源与准入审核状态。
13. **Textbook** (`textbook`)：教材元数据、解析大纲与发布状态。
14. **TextbookSectionContent** (`textbooksectioncontent`)：教材小节原文与中文内容切片。
15. **TextbookExtensionResource** (`textbookextensionresource`)：教材小节关联的扩展学习资源。
16. **KnowledgeGap** (`knowledgegap`)：学生触发的知识缺口记录与补全状态。
17. **KnowledgeGapFollow** (`knowledgegapfollow`)：学生对知识缺口的关注记录。
18. **KnowledgeGapNotice** (`knowledgegapnotice`)：知识缺口补全后生成的学生通知。
19. **KnowledgeBaseIngestionJob** (`knowledgebaseingestionjob`)：知识库后台整理任务（租约、重试、状态）。
20. **WorkerHeartbeat** (`workerheartbeat`)：后台 Worker 存活心跳记录。
21. **UserModelProvider** (`user_model_provider`)：用户的模型提供商配置（凭据加密保存）。
22. **UserCustomModel** (`user_custom_model`)：用户自定义模型及其能力声明。
23. **UserModelPreferences** (`user_model_preferences`)：用户的简单/高级模型绑定与快速切换。
24. **UserModelUsageLog** (`user_model_usage_log`)：个人模型用量记录（用量看板数据源）。

生产环境通过 Alembic 迁移（`0001_production_baseline` ~ `0009_kb_job_triggered_by`）管理结构演进；开发与测试初始化时 `init_db` 会创建当前模型并由 `schema_upgrades.py` 兼容历史结构（如将旧 `teacher` 角色规范为 `admin`、将 `cultivationprogram.teacher_uid` 迁移为 `admin_uid`、清理已废弃的 `textbook.embedding` 列、删除旧 `useragentconversation`/`userlearningpath`、升级 JSON 为 JSONB 等）。

## API 分组

关于完整字段和示例，请参考 [认证接口](../api-specs/API-认证接口.md)、[业务接口](../api-specs/API-业务接口.md)、[成长报告接口](../api-specs/API-成长报告.md) 和 `frontend/openapi.json`。

### 1. 认证端点 (`/api/auth`)
* `POST /register` — 注册新用户（固定注册为 `student`）
* `POST /login` — 密码登录
* `POST /oauth/mock` — Mock OAuth 登录（仅非生产环境启用）
* `GET /me` — 获取当前用户信息

### 2. Chat 端点 (`/api/chat`)
* `POST /start` — 启动 AI 对话（Python）
* `GET /sessions/{session_id}` — 获取会话消息历史（Python）
* `POST /message` — 发送消息 (SSE 流式事件)，**由 AI 网关提供**，Nginx 路由到 `ai-gateway`

### 2b. 个人模型配置 (`/api/model-config`) 与 AI 网关 (`/api/ai/*`)
* Python：`GET /api/model-config`、`PUT/DELETE /providers/{id}`、`PUT /custom-models`、`PUT /preferences`、`PATCH /quick-switch`、`GET /usage`（用量看板）
* 网关：`GET /api/ai/models/catalog`、`POST /api/ai/models/probe|scene-check`、`/api/ai/oauth/{provider}/start|complete|status`、`GET /api/ai/health/live|ready`

### 3. 业务模块端点 (`/api/*`)
* **画像大盘**：`GET /api/profile/dashboard`
* **学习路径**：`GET /api/learning-path/me`
* **繁枝与成长**：`GET /api/branch/canopy`、`GET /api/branch/overview`、`POST /api/branch/canopy/report/stream` (SSE 成长报告，网关提供)
* **展叶大纲**：`GET /api/leaf/courses/{course_node_id}`
* **测验森林**：`GET /api/forest/courses/.../quiz`、`POST /api/forest/courses/.../quiz/generate`、`POST /api/forest/quizzes/{quiz_id}/attempts`、`POST /api/forest/quizzes/{quiz_id}/attempts/stream` (SSE 流式批改)、`GET /api/forest/quizzes/{quiz_id}/submissions/{client_submission_id}` (提交恢复查询)、`POST /api/forest/ai/stream` (AI 答疑，网关提供)
* **培养方案（学生与管理端）**：`GET /api/student/matched-program`、`GET/PUT /api/admin/program`、`POST /api/admin/program/publish`
* **系统管理**：`/api/admin/accounts*`（账号管理与 CSV 导入导出）及 `/api/admin/data*`（学情监控与清理）
* **教材知识库**：`/api/admin/knowledge-base/*`（管理端来源准入、教材管理/上传/解析/发布、Agent 流式检索、缺口管理、扩展资源）及 `/api/knowledge-base/gaps/{gap_id}/follow`、`/api/knowledge-base/notices*`（学生端缺口关注与提醒）

### 4. 其他
* `GET /api/health/live` — 进程存活检查
* `GET /api/health/ready` / `GET /api/health` — 数据库与迁移状态就绪检查
* `GET /api/health/deep` — 含知识库 Worker 心跳的深度健康检查

## 环境变量

后端（生产启动前会校验，缺失即拒绝启动）：

```bash
APP_ENV=production
DATABASE_URL=postgresql://mutiagent:mutiagent@localhost:5432/mutiagent
JWT_SECRET=...                    # 网关使用同一值验签
ALLOWED_ORIGINS=https://onetree.chat
INTERNAL_API_TOKEN=...            # 与网关共享，不能是默认值
AI_GATEWAY_URL=http://ai-gateway:8100
MODEL_SECRET_ENCRYPTION_KEY=...   # 用户模型凭据的加密主密钥，生成后不可随意更换
```

网关：`APP_ENV`、`JWT_SECRET`、`INTERNAL_API_TOKEN`、`PYTHON_BACKEND_URL`、`ALLOWED_ORIGINS`、`PORT`（默认 8100）、`HOST`、`BACKEND_TIMEOUT_MS`、`SSE_HEARTBEAT_MS`。

## 验证

```bash
cd backend
uv run pytest -q && uv run ruff check app tests

cd ../ai-gateway
npm run typecheck && npm run lint && npm test

cd ../frontend
npm test
npm run build
```
