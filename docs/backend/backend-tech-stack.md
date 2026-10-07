# Backend 技术文档

> 本文是当前源码快照。最后全面核对：2026-07-15；数据库生命周期与性能路径核对：2026-10-04。代码、测试和配置变更后应同步更新本文。

当前后端使用 FastAPI + LangGraph + LangChain，采用无 checkpoint 的单轮 StateGraph 编排。每轮请求从数据库加载画像、按年学习路径、课程大纲、资源状态和会话消息。知识库教材整理是独立的数据库任务 worker。

## 启动

```bash
cd backend
uv run uvicorn app.main:app --reload --port 8000
```

## 技术栈

| 层级 | 技术 | 用途 |
|---|---|---|
| Web 框架 | FastAPI | REST API + SSE 流式 |
| Agent 编排 | LangGraph | 单轮 StateGraph 编排，无 checkpoint |
| LLM 调用 | LangChain + langchain-openai | ChatModel、tool calling、structured output |
| 数据库 | PostgreSQL + psycopg2 | 生产与测试存储 |
| ORM | SQLModel | 模型定义、Session 管理 |
| JSON 存储 | PostgreSQL JSONB | 画像、路径、课程大纲、会话消息 |
| 认证 | python-jose + bcrypt | Bearer token 认证 |
| LLM 接入 | OpenAI-compatible API | 当前：阿里百炼 Qwen3.5+ |

## 架构总览

```text
用户消息
  -> POST /api/chat/message
  -> 从 DB 加载 ConversationSession.messages + UserProfile + UserYearLearningPath + UserCourseKnowledgeOutline
  -> 构建 OrchestrationState
  -> LangGraph 单次执行
       supervisor
         -> profile_agent
         -> learning_path_intake_agent
         -> learning_path_agent
         -> course_knowledge_agent
         -> section_markdown_agent
         -> section_video_search_agent
         -> section_html_animation_agent
       资源阶段按 plan 顺序衔接，最终由确定性 compose 完成
  -> SSE 输出过程事件
  -> 追加本轮消息到 ConversationSession
  -> 持久化完成后输出 message_completed / session_completed
```

### 数据库操作与模型等待

同步数据库路由使用 `def`。聊天、测验、资源生成和成长报告按“短事务读取上下文 → 等待模型 → 短事务写入结果”执行；认证查询也在独立短 Session 中完成。`database.run_db` 在线程池内创建、使用并关闭绑定当前应用 engine 的 Session，返回已加载的数据或完整 DTO，不在线程之间共享 Session。

Agent 的同步数据库 helper 整段在线程中执行。聊天只在推进 SSE 生成器期间绑定请求 engine，输出事件前恢复上下文，提前关闭亦可安全清理。发生事务失败时，用户消息回退使用新 Session。生产启动只检查 Alembic head，不执行开发模式的 `init_db`；开发空 schema 直接创建当前模型，非空 schema 仍走历史兼容升级。

知识库管理员 Agent 的普通与 SSE HTTP 入口传入绑定应用 engine 的 Session factory；计数、查重和缺口查询分别在短 Session 内完成，关闭后才联网搜索或输出事件。直接传入 Session 的内部服务调用仍由调用者管理事务，保留未提交数据的可见性。SSE 保持同步生成器，并在退出时关闭内层生成器。

教材上传继续异步分块读取并执行 100 MiB 限额检查；字节拼接在线程池完成，文件落盘、教材与整理任务持久化及响应 DTO 构造在工作线程自己的 Session 中完成。请求 Session 和 UploadFile 不跨线程，教材与任务仍按现有顺序分次提交。

当前教材 embedding 列为 FLOAT[]。检索先检测向量类型、运算符、全文配置和已发布向量；不满足条件时跳过 embedding API，按原字符串评分规则匹配。混合 SQL 使用 savepoint 隔离失败。教材切片使用标题偏移索引，MarkItDown 在转换时导入。统计与证据加载的测量边界见 [性能报告](backend-performance-profile.md)。

## Agent 系统

### Supervisor 与 Worker

- 文件：`backend/app/orchestration/agents/supervisor.py`
- 实现：Supervisor LLM + tool calling；硬规则在 `rule_engine.py` 和路由函数中执行。
- 决策：LLM 负责大部分调度，`rule_engine.py` 负责硬性守卫。
- 关键守卫：
  - 没有完成画像时，禁止调用路径 Agent 和课程大纲 Agent。
  - 有画像但没有按年路径时，禁止调用课程大纲 Agent。
  - 用户明确开始课程时，可强制调用课程大纲 Agent。

当前 LangGraph Worker：每个 Worker 按自身契约维护独立的 LangChain Chain；结构化输出 Worker 使用 Pydantic 模型。

| Agent | 文件 | 作用 | 主要结果 |
|---|---|---|---|
| `profile_agent` | `agents/profile.py` | 从对话构建或更新画像 | `userprofile.profile_data` |
| `learning_path_intake_agent` | `agents/learning_path_intake.py` | 收集课程草案需求并确认 | 编排状态中的课程草案 |
| `learning_path_agent` | `agents/learning_path.py` | 生成或刷新按年学习路径 | `useryearlearningpath.path_data` |
| `course_knowledge_agent` | `agents/course_knowledge.py` | 生成课程章节大纲 | `usercourseknowledgeoutline.outline_data` |
| `section_markdown_agent` | `agents/course_resources/markdown.py` | 生成小节教学文档 | 资源计划中的 Markdown |
| `section_video_search_agent` | `agents/course_resources/video.py` | 校验并选择视频资源 | 资源计划中的视频 |
| `section_html_animation_agent` | `agents/course_resources/animation.py` | 生成并校验 HTML 动画 | 资源计划中的动画 |

资源编排入口为 `agents/course_resources/main.py`。其阶段名为 `markdown`、`video`、`animation`、`compose`；`compose` 使用确定性逻辑合并资源结果，不是独立 LLM Worker。

### 知识库后台 Worker

`python -m app.workers` 启动 `knowledge_base_worker`，从 `KnowledgeBaseIngestionJob` 领取教材整理任务。领取按原排队顺序执行 `LIMIT 1 FOR UPDATE SKIP LOCKED`，任务使用数据库锁、租约、心跳、重试次数和失败状态，生产 Compose 中由 `worker` 服务运行。上传文件由 `KNOWLEDGE_BASE_UPLOAD_DIR` 指向的持久卷保存。

## 数据库模型

项目包含以下核心 SQLModel 数据库表（当前表名和字段以 `backend/app/models.py` 及迁移为准；详见 [数据库表结构文档](../database/数据库表结构.md)）：

1. **User** (`user`)：用户账户及基本属性。
2. **CultivationProgram** (`cultivationprogram`)：通用培养方案大纲模板。
3. **UserProfile** (`userprofile`)：用户个人画像特征及自然语言总结。
4. **UserYearLearningPath** (`useryearlearningpath`)：按学年生成的课程规划拓扑。
5. **UserCourseKnowledgeOutline** (`usercourseknowledgeoutline`)：单门课程的具体章节知识大纲。
6. **ChapterQuiz** (`chapterquiz`)：为章节动态生成的测验题集。
7. **ChapterQuizAttempt** (`chapterquizattempt`)：学生每次提交试卷的打分批改记录。
8. **ChapterProgress** (`chapterprogress`)：章节通关/解锁进度状态。
9. **ChapterWeakness** (`chapterweakness`)：测验中暴露出的薄弱知识点记录。
10. **CourseResourceQuality** (`courseresourcequality`)：章节图文及动画生成质量评分。
11. **ConversationSession** (`conversationsession`)：会话消息历史持久化记录。

启动时 `schema_upgrades.py` 会将旧结构升级到当前结构：

- 删除旧 `useragentconversation`。
- 迁移并删除旧 `userlearningpath`。
- 将旧 `usercourseknowledgeoutline.course_node_id/grade_id` 重建为 `course_id/grade_year`。
- 将 `profile_data`、`outline_data` 等 JSON 存储升级为 JSONB。

## API 分组

关于完整字段和示例，请参考 [认证接口](../api-specs/API-认证接口.md)、[业务接口](../api-specs/API-业务接口.md) 和 `frontend/openapi.json`。

### 1. 认证端点 (`/api/auth`)
* `POST /register` — 注册新用户
* `POST /login` — 密码登录
* `POST /oauth/mock` — Mock OAuth 登录
* `GET /me` — 获取当前用户信息

### 2. Chat 编排端点 (`/api/chat`)
* `POST /start` — 启动 AI 对话
* `POST /message` — 发送消息 (SSE 流式事件)
* `GET /sessions/{session_id}` — 获取会话消息历史

### 3. 业务模块端点 (`/api/*`)
* **画像大盘**：`GET /api/profile/dashboard`
* **学习路径**：`GET /api/learning-path/me`
* **繁枝总览**：`GET /api/branch/canopy`、`GET /api/branch/overview`
* **展叶大纲**：`GET /api/leaf/courses/{course_node_id}`
* **测验森林**：`GET /api/forest/courses/.../quiz`、`POST /api/forest/courses/.../quiz/generate`、`POST /api/forest/quizzes/{quiz_id}/attempts` (或 `/attempts/stream` 流式批改)、`POST /api/forest/ai/stream` (AI答疑)
* **教师与学生**：`GET /api/student/matched-program`、`GET/PUT /api/teacher/program`、`POST /api/teacher/program/publish`
* **系统管理**：包含 `/api/admin/accounts/*` (账号CSV导入导出等) 及 `/api/admin/data/*` (学情监控) 的完整后台路由

### 4. 其他
* `GET /api/health` — 健康检查 (健康度与数据库连接状态)

## 环境变量

```bash
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=sk-xxx
LLM_MODEL=qwen3.5-plus-2026-04-20
DATABASE_URL=postgresql://mutiagent:mutiagent@localhost:5432/mutiagent
```

## 验证

```bash
cd backend
uv run pytest -q

cd ../frontend
npm test
npm run build
```
