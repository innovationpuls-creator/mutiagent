# Backend 技术文档

> 当前后端使用 FastAPI + LangGraph + LangChain，本地多 Agent 编排，不依赖 Dify，不依赖 LangGraph Checkpoint。每轮请求从数据库加载画像、按年学习路径、最近课程大纲和会话消息。

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
         -> learning_path_agent
         -> course_knowledge_agent
       worker 完成后回到 supervisor
  -> SSE 输出过程事件
  -> message_completed 后追加本轮消息到 ConversationSession
```

## Agent 系统

### Supervisor

- 文件：`backend/app/orchestration/agents/supervisor.py`
- 实现：LLM + `bind_tools([profile_agent, learning_path_agent, course_knowledge_agent])`
- 决策：LLM 负责大部分调度，`rule_engine.py` 负责硬性守卫。
- 关键守卫：
  - 没有完成画像时，禁止调用路径 Agent 和课程大纲 Agent。
  - 有画像但没有按年路径时，禁止调用课程大纲 Agent。
  - 用户明确开始课程时，可强制调用课程大纲 Agent。

### Worker Agent

每个 Worker 是 `ChatPromptTemplate -> LLM.with_structured_output(Pydantic)`。

| Agent | 文件 | 输出模型 | 前置条件 | 持久化 |
|---|---|---|---|---|
| ProfileAgent | `agents/profile.py` | `ProfileOutput` | 用户对话摘要 | `userprofile.profile_data` |
| LearningPathAgent | `agents/learning_path.py` | `YearLearningPathOutput` | 已完成画像 | `useryearlearningpath.path_data` |
| CourseKnowledgeAgent | `agents/course_knowledge.py` | `CourseKnowledgeOutput` | 已完成画像 + 至少一年路径 | `usercourseknowledgeoutline.outline_data` |

## 数据库模型

项目包含以下 11 个核心 SQLModel 数据库表（各表字段定义与约束详见 [数据库表结构文档](file:///Users/torch/torch/opt/mutiagent/docs/database/数据库表结构.md)）：

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

## API 端点

关于完整、详细的 API 协议约定及示例，请参考以下文档：
* **认证接口**：[API-认证接口.md](file:///Users/torch/torch/opt/mutiagent/docs/api-specs/API-认证接口.md)
* **业务接口**：[API-业务接口.md](file:///Users/torch/torch/opt/mutiagent/docs/api-specs/API-业务接口.md)

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
