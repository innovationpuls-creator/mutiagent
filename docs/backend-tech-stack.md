# Backend 技术文档

> 面向 AI Agent 的快速上手指南。简明、准确、可执行。

## 技术栈

| 层级 | 技术 | 用途 |
|---|---|---|
| Web 框架 | FastAPI | REST API + SSE 流式 |
| Agent 编排 | LangGraph | 图结构编排，Checkpoint 持久化 |
| LLM 调用 | LangChain + langchain-openai | ChatModel、tool calling、structured output |
| 数据库 | PostgreSQL (psycopg2) | 生产存储；测试用 SQLite |
| ORM | SQLModel | 模型定义、Session 管理 |
| 认证 | python-jose (JWT) + bcrypt | Bearer token 认证 |
| 异步 | asyncio | 全链路 async |
| LLM 接入 | OpenAI-compatible API | 当前: 阿里百炼 Qwen3.5+ |

## 架构总览

```
用户 HTTP 请求
  │
  ▼
POST /api/orchestration/sessions/start  (或 /stream)
  │
  ▼
FastAPI Router ──→ create_orchestration_graph(session)
  │
  ▼
┌─────────────────────────────────────────┐
│         LangGraph StateGraph            │
│                                         │
│  START ──→ [supervisor] ◄──────────┐   │
│               │                     │   │
│         tool_calls?                 │   │
│          /    |    \                │   │
│    profile learning course          │   │
│    _agent  _path   _knowledge       │   │
│       \     |     /                 │   │
│        ─────┴─────                  │   │
│                                     │   │
│  END ◄── (no tool_calls)            │   │
└─────────────────────────────────────┘
  │
  ▼
SessionResponse (JSON) 或 SSE 事件流
```

## Agent 系统

### Supervisor（主 Agent）

- **文件**: `orchestration/agents/supervisor.py`
- **实现**: LLM + `bind_tools([profile_agent, learning_path_agent, course_knowledge_agent])`
- **职责**: 接收用户消息，决定直接回复还是调用 Worker Agent
- **路由**: `_route_after_supervisor()` 检查最后一条 AIMessage 的 tool_calls
- **Prompt**: `SUPERVISOR_SYSTEM_PROMPT` in `agents/prompts.py`

### Worker Agent（子 Agent）

每个 Worker 是 LangChain Chain: `ChatPromptTemplate → LLM → with_structured_output(Pydantic)`

| Agent | 文件 | 输出模型 | 前置条件 | 持久化 |
|---|---|---|---|---|
| ProfileAgent | `agents/profile.py` | `ProfileAgentOutput` | 无 | `user_profile` 表 |
| LearningPathAgent | `agents/learning_path.py` | `LearningPathResult` | 已完成的 profile | `user_learning_path` 表 |
| CourseKnowledgeAgent | `agents/course_knowledge.py` | `CourseKnowledgeOutlineResult` | profile + learning_path | `user_course_knowledge_outline` 表 |

### 通信机制

- **Supervisor → Worker**: 通过 LangGraph tool_call 路由到对应 graph node
- **Worker → Supervisor**: Worker 返回 `{"profile": ..., "messages": [ToolMessage(...)]}`，Supervisor 从 messages 读取结果
- **Worker → DB**: 各自直接调用 service 层持久化
- **状态传递**: 全部通过 `OrchestrationState` (TypedDict)

## 目录结构

```
backend/app/
├── main.py                          # FastAPI 入口，create_app() 工厂
├── database.py                      # 数据库引擎、Session、init
├── models.py                        # SQLModel 表定义（5 张表）
├── schemas.py                       # Pydantic 请求/响应 Schema
│
├── core/
│   └── security.py                  # JWT 生成/验证、密码哈希
│
├── api/
│   ├── auth.py                      # POST /api/auth/register, /login, /oauth/mock, GET /me
│   ├── orchestration.py             # POST /api/orchestration/sessions/start, /continue, /stream
│   ├── profile.py                   # GET /api/profile/dashboard
│   └── learning_path.py             # GET /api/learning-path/me
│
├── orchestration/
│   ├── state.py                     # OrchestrationState TypedDict
│   ├── graph.py                     # LangGraph 建图 + SSE 流式生成器
│   ├── agent_plan.py                # Pydantic 模型（LearningPathResult, etc.）
│   ├── execution_registry.py        # 内存级 Session 注册表
│   │
│   └── agents/
│       ├── __init__.py
│       ├── prompts.py               # 所有 agent 的 System Prompt 模板
│       ├── models.py                # Worker Agent 的 Pydantic 输出模型
│       ├── supervisor.py            # Supervisor 节点 + tool 定义
│       ├── profile.py               # ProfileAgent
│       ├── learning_path.py         # LearningPathAgent
│       └── course_knowledge.py      # CourseKnowledgeAgent
│
└── services/
    ├── auth_service.py              # 注册、登录逻辑
    ├── profile_service.py           # UserProfile CRUD
    ├── learning_path_service.py     # UserLearningPath CRUD
    ├── course_knowledge_service.py  # UserCourseKnowledgeOutline CRUD + 节点解析
    └── agent_conversation_service.py # Agent 对话 ID 持久化
```

## 数据库模型

```sql
-- 用户表
User (uid PK, username, identifier UNIQUE, provider, password_hash, is_active,
      created_at, updated_at, last_login_at)

-- 用户画像
UserProfile (user_uid PK/FK→User, profile_data JSON, profile_text, created_at, updated_at)

-- Agent 对话记录
UserAgentConversation (user_uid PK/FK→User, agent_key PK, conversation_id, created_at, updated_at)

-- 学习路径
UserLearningPath (user_uid PK/FK→User, path_data JSON, created_at, updated_at)

-- 课程章节大纲
UserCourseKnowledgeOutline (user_uid PK/FK→User, course_node_id PK,
                            grade_id, course_name, outline_data JSON, created_at, updated_at)
```

## API 端点

### 认证
| Method | Path | 说明 |
|---|---|---|
| POST | `/api/auth/register` | 注册，返回 JWT |
| POST | `/api/auth/login` | 登录，返回 JWT |
| POST | `/api/auth/oauth/mock` | Mock OAuth |
| GET  | `/api/auth/me` | 当前用户信息 |

### 编排（核心）
| Method | Path | 说明 |
|---|---|---|
| POST | `/api/orchestration/sessions/start` | 新建会话，非流式 |
| POST | `/api/orchestration/sessions/continue` | 继续会话，非流式 |
| POST | `/api/orchestration/sessions/start/stream` | 新建会话，SSE 流式 |
| POST | `/api/orchestration/sessions/continue/stream` | 继续会话，SSE 流式 |

请求体: `{"query": "..."}` (start) / `{"session_id": "...", "query": "..."}` (continue)

响应体 `SessionResponse`:
```json
{
  "session_id": "uuid",
  "answer": {"user_message": "...", "question_box": null | {...}},
  "agent_trace": [{"step_id": "...", "agent_key": "...", "label": "...", ...}],
  "completed": true,
  "profile": null | {...},
  "learning_path": null | {...},
  "course_knowledge_outline": null | {...}
}
```

SSE 事件: `agent_step_started` → `agent_step_completed` → `orchestration_completed` (或 `orchestration_failed`)

### 其他
| Method | Path | 说明 |
|---|---|---|
| GET | `/api/profile/dashboard` | 用户画像仪表盘 |
| GET | `/api/learning-path/me` | 用户学习路径 |
| GET | `/api/health` | 健康检查 |

## 环境变量 (.env)

```bash
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=sk-xxx
LLM_MODEL=qwen3.5-plus-2026-04-20
DATABASE_URL=postgresql://mutiagent:mutiagent@localhost:5432/mutiagent
```

LLM 接入支持任何 OpenAI-compatible API（阿里百炼、DeepSeek、OpenAI 等），只需改 `.env`。

## 运行

```bash
# 启动 PostgreSQL
brew services start postgresql@18

# 创建数据库（首次）
psql postgres -c "CREATE USER mutiagent WITH PASSWORD 'mutiagent';"
psql postgres -c "CREATE DATABASE mutiagent OWNER mutiagent;"

# 启动后端
cd backend
uv sync                         # 安装依赖
uv run uvicorn app.main:app --reload --port 8000

# 运行测试
uv run pytest tests/ -v
```

## 关键设计决策

1. **Supervisor 驱动多轮**: Worker 不持有状态，Supervisor 每轮根据 State 决定继续还是切换
2. **Worker 结构统一**: 每个 Worker 是 `prompt → LLM → structured_output` 的 Chain，无子图
3. **Tool Calling 路由**: Supervisor 用 `bind_tools` 声明能力，LangGraph `tools_condition` 自动路由
4. **State 精简**: OrchestrationState 只保留核心字段（query, messages, profile, learning_path, course_knowledge, response）
5. **SSE 事件协议**: 使用 LangGraph `astream_events(v2)` 生成标准 SSE 事件
6. **异步全链路**: 所有 agent 调用、DB 操作均为 async
7. **LLM 可替换**: 通过 OpenAI-compatible API 接入，换模型只需改 `.env`

## 历史说明

2026-06-03 重构前，系统依赖 Dify 平台（5 个外部 API key）做 agent 编排。重构后全部本地化，用 LangGraph + LangChain 替代。旧的 Dify 相关代码（`dify_client.py`, `agent_executor.py`, `response_parser.py`）已全部删除。
