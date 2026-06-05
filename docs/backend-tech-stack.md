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
| 数据库 | PostgreSQL + psycopg2 | 生产存储；测试用 SQLite |
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

```text
User
  uid PK
  username
  identifier UNIQUE
  provider
  password_hash
  is_active
  created_at
  updated_at
  last_login_at

UserProfile
  user_uid PK/FK -> User.uid
  profile_data JSONB
  profile_text
  created_at
  updated_at

UserYearLearningPath
  user_uid PK/FK -> User.uid
  grade_year PK
  learning_topic
  path_data JSONB
  created_at
  updated_at

UserCourseKnowledgeOutline
  user_uid PK/FK -> User.uid
  course_id PK
  grade_year
  course_name
  outline_data JSONB
  created_at
  updated_at

ConversationSession
  session_id PK
  user_uid FK -> User.uid
  messages JSONB
  created_at
  updated_at
```

启动时 `schema_upgrades.py` 会将旧结构升级到当前结构：

- 删除旧 `useragentconversation`。
- 迁移并删除旧 `userlearningpath`。
- 将旧 `usercourseknowledgeoutline.course_node_id/grade_id` 重建为 `course_id/grade_year`。
- 将 `profile_data`、`outline_data` 等 JSON 存储升级为 JSONB。

## API 端点

### 认证

| Method | Path | 说明 |
|---|---|---|
| POST | `/api/auth/register` | 注册，返回 JWT |
| POST | `/api/auth/login` | 登录，返回 JWT |
| POST | `/api/auth/oauth/mock` | Mock OAuth |
| GET | `/api/auth/me` | 当前用户信息 |

### Chat 编排

| Method | Path | 说明 |
|---|---|---|
| POST | `/api/chat/start` | 创建会话，返回 `session_id` 和开场回复 |
| POST | `/api/chat/message` | 发送用户消息，返回 SSE |
| GET | `/api/chat/sessions/{session_id}` | 读取 DB 中的会话状态 |

`POST /api/chat/message` 请求体：

```json
{
  "session_id": "uuid",
  "message": "你好"
}
```

SSE 事件：

```text
session_started
message(type=supervisor_thinking)
message(type=supervisor_plan)
agent_calling
agent_progress
agent_result
data_update
text_chunk
message_completed
session_completed
error
```

### 其他

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/profile/dashboard` | 用户画像仪表盘 |
| GET | `/api/learning-path/me` | 用户全部按年学习路径 |
| GET | `/api/health` | 健康检查 |

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
