# Dify + LangGraph 开发指南

> **本文档面向 AI 辅助开发。AI 阅读本文档后，必须遵循第 1 章的提问规则。**

---

## 1. AI 交互规则（最高优先级）

**在开始任何编码任务前，AI 必须遵守以下规则：**

1. **所有不明确的地方必须向用户提问**，禁止猜测用户的意图
2. **禁止猜测变量名、字段名、API 路径、路由逻辑**
3. **所有 Dify App 的信息必须从 `.env` 或用户提供的信息中获取**，禁止硬编码
4. **修改任何代码前，必须先确认用户的意图和需求**
5. **如果 ARCHITECTURE.md、后端技术栈.md、本文档三者有冲突，优先参考 ARCHITECTURE.md**

---

## 2. 架构全景图

```
Frontend (React)
  │
  ▼
FastAPI (REST + SSE)
  │  POST /api/orchestration/chatflow/start    — 发起对话
  │  POST /api/orchestration/chatflow/continue  — 继续对话
  │  GET  /api/orchestration/stream/{exec_id}   — SSE 流式推送
  │  GET  /api/orchestration/result/{exec_id}   — 断线重连
  │
  ▼
LangGraph (编排状态机 — StateGraph + MemorySaver)
  │
  ├── Node: call_dify
  │   └─→ Dify Learner Profile Builder Chatflow (多轮对话)
  │        POST http://localhost/v1/chat-messages
  │
  ├── Node: parse_response
  │   └─→ 从 answer 字段提取 JSON → {type, stage, confirmed_info, ...}
  │
  └── Node: check_completion
       ├─ type == "basic_profile" → phase = "completed"
       └─ type == "collecting"    → phase = "collecting"
```

**三层 Dify App（逐步集成）：**

| 层级 | Dify App | 类型 | 状态 |
|------|----------|------|------|
| 意图路由 | Intent Chatflow | Chatflow | 待集成 |
| 主对话 | Learner Profile Builder | Chatflow | ✅ 已集成 |
| 下游 w1 | 文档生成 | Workflow | 待搭建 |
| 下游 w2 | 联网检索 | Workflow | 待搭建 |

---

## 3. 环境变量规范

**文件**: `backend/.env`

```env
DIFY_API_URL=http://localhost/v1
DIFY_CHATFLOW_API_KEY=app-xxx
```

**Python 加载方式** (`dify_client.py`):
```python
from dotenv import load_dotenv
load_dotenv()
DIFY_API_URL = os.getenv("DIFY_API_URL", "http://localhost/v1")
DIFY_CHATFLOW_API_KEY = os.getenv("DIFY_CHATFLOW_API_KEY", "")
```

> **AI 注意**：添加新的 Dify App 时（如意图识别、w1 工作流），请按相同模式添加环境变量，并向用户确认 API Key。

---

## 4. Dify Chatflow API 调用层

### 4.1 请求格式（实测验证）

```
POST {DIFY_API_URL}/chat-messages
Authorization: Bearer {DIFY_CHATFLOW_API_KEY}
Content-Type: application/json

{
  "inputs": {},                    // Chatflow 输入变量（当前为空对象）
  "query": "用户消息",              // 用户输入
  "response_mode": "blocking",     // blocking 或 streaming
  "conversation_id": "",           // 空字符串=新对话, 传入已有ID=继续对话
  "user": "用户标识"                // 由开发者定义，保证唯一
}
```

### 4.2 阻塞模式响应（实测验证）

```json
{
  "event": "message",
  "task_id": "f48ecb1c-...",
  "id": "4a9d5ba9-...",
  "message_id": "4a9d5ba9-...",
  "conversation_id": "40cb0537-...",
  "mode": "advanced-chat",
  "answer": "{...JSON 字符串...}",   // ← 核心：Chatflow 的输出
  "metadata": {
    "usage": {
      "prompt_tokens": 3118,
      "completion_tokens": 329,
      "total_tokens": 3447,
      "total_price": "0.0040736",
      "currency": "RMB",
      "latency": 7.506
    }
  },
  "created_at": 1780214622
}
```

### 4.3 answer 字段的 JSON 结构（实测验证）

**信息收集阶段** (`type: "collecting"`):
```json
{
  "type": "collecting",
  "stage": "basic_info",
  "question_mode": "question_md",
  "confirmed_info": {
    "current_grade": "",
    "major": "",
    "learning_stage": "",
    "...共15个字段..."
  },
  "defaulted_fields": [],
  "question_md": "已确认信息：...接下来需要了解：...",
  "question_box": {"question": "", "options": []},
  "text": "同上可读内容"
}
```

**生成完成阶段** (`type: "basic_profile"`):
```json
{
  "type": "basic_profile",
  "stage": "generated",
  "question_mode": "none",
  "confirmed_info": {
    "current_grade": "大三",
    "major": "软件工程",
    "...15个字段全部填充..."
  },
  "text": "【用户基础信息】\n...完整画像内容..."
}
```

### 4.4 流式模式 SSE 事件（实测验证）

| event | 含义 | 数据 |
|-------|------|------|
| `ping` | 每10秒心跳 | 保持连接 |
| `workflow_started` | 工作流开始 | `{task_id, workflow_run_id, data}` |
| `node_started` | 节点开始执行 | `{node_id, node_type, title, index}` |
| `node_finished` | 节点执行结束 | `{outputs, status, elapsed_time}` |
| `message` | LLM 文本块 | `{answer: "片段文本"}` |
| `message_end` | 消息结束 | `{metadata, usage}` |
| `workflow_finished` | 工作流结束 | `{outputs, status}` |

### 4.5 DifyClient 封装（已实现：`app/orchestration/dify_client.py`）

```python
class DifyClient:
    async def chat_blocking(query, user_id, conversation_id) -> DifyResponse
    async def chat_streaming(query, user_id, conversation_id) -> AsyncIterator[str]
```

---

## 5. LangGraph StateGraph 设计

### 5.1 State 定义（已实现：`app/orchestration/state.py`）

```python
class OrchestrationState(TypedDict):
    query: str              # 当前用户输入
    user_id: str            # 用户标识
    conversation_id: str    # Dify 多轮对话 ID
    dify_raw: dict          # Dify API 原始响应
    answer_json: dict       # 解析后的 answer JSON
    phase: str              # "collecting" | "completed" | "error"
    error: str              # 错误信息
```

### 5.2 Graph 结构（已实现：`app/orchestration/graph.py`）

```
START
  │
  ▼
call_dify ─── 调用 DifyClient.chat_blocking()
  │            输入: query, user_id, conversation_id
  │            输出: dify_raw, conversation_id
  ▼
parse_response ─── 从 dify_raw.answer 解析 JSON
  │                输出: answer_json = {type, stage, confirmed_info, ...}
  ▼
check_completion ─── 判断完成状态
  │                  type == "basic_profile" → phase = "completed"
  │                  否则 → phase = "collecting"
  ▼
END
```

### 5.3 关键实现细节

- 使用 `MemorySaver` 作为 checkpointer，在 Graph 内部保持 `conversation_id` 的持久化
- 每次调用 Dify API 都创建新的 `httpx.AsyncClient`（非线程安全）
- Graph 的 `thread_id` 用 `user_id`，确保同一用户的多轮对话共享状态

---

## 6. 完成检测策略

**当前实现**（基于实测，最可靠）:

```python
def check_completion(answer_json: dict) -> bool:
    return (
        answer_json.get("type") == "basic_profile"
        and answer_json.get("stage") == "generated"
    )
```

**备用策略**（从 ARCHITECTURE.md）:

当 Chatflow 没有按预期输出 JSON 时：
- 尝试 `json.loads()` 直接解析
- 尝试去除 markdown 代码块 ` ```json ` 包裹
- 检查 `data["type"]` 是否在规定列表中

> **AI 注意**：如果用户的 Chatflow 的 type 值不同（不是 "basic_profile"），必须向用户确认正确的完成类型值。不要硬编码。

---

## 7. FastAPI 路由设计

### 7.1 需要创建的端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/orchestration/chatflow/start` | 新建对话 |
| `POST` | `/api/orchestration/chatflow/continue` | 继续对话 |
| `GET` | `/api/orchestration/stream/{execution_id}` | SSE 流式推送 |
| `GET` | `/api/orchestration/result/{execution_id}` | 断线重连 |

### 7.2 `/chatflow/start` 请求/响应

**请求**:
```json
{"query": "我想学习数据结构"}
```

**响应**:
```json
{
  "execution_id": "uuid",
  "conversation_id": "dify-conv-id",
  "answer": {"type": "collecting", "text": "...", ...},
  "completed": false
}
```

### 7.3 `/chatflow/continue` 请求/响应

**请求**:
```json
{"execution_id": "uuid", "query": "大三软件工程"}
```

**响应**:
```json
{
  "answer": {"type": "collecting", ...},
  "completed": false
}
```

当完成时:
```json
{
  "answer": {"type": "basic_profile", "text": "...", ...},
  "completed": true,
  "final_result": {...}
}
```

### 7.4 SSE 推送协议

所有 SSE 事件使用 `event: message`（兼容 `EventSource.onmessage`）：

```javascript
// 前端接收
es.onmessage = (msg) => {
  const event = JSON.parse(msg.data);
  switch (event.type) {
    case "chatflow_completed":  // Chatflow 完成
    case "workflow_result":     // w1/w2 结果
    case "heartbeat":           // 心跳 (30s)
    case "complete":            // 全部完成
    case "error":               // 错误
  }
};
```

---

## 8. 扩展指南

### 8.1 添加意图识别 Chatflow

在 Graph 中新增节点：
```
START → call_intent_dify → route_by_intent → call_chatflow_dify → ...
```

需要向用户确认：
- 意图识别 Chatflow 的 API Key
- 输入的变量名
- 输出的意图类型有哪些
- 每种意图对应的下游路由

### 8.2 添加 w1/w2 Workflow 并行执行

在 `check_completion` 检测到完成后，用 `asyncio.gather` 并行调用：
```python
results = await asyncio.gather(
    client.run_workflow("w1_api_key", inputs),
    client.run_workflow("w2_api_key", inputs),
)
```

需要向用户确认：
- w1/w2 的 API Key
- 输入变量名（ARCHITECTURE.md 中提到是 `u_in`）
- 输出格式

---

## 9. 项目文件结构

```
backend/
├── .env                              # Dify API 配置
├── .python-version                   # Python 3.12
├── pyproject.toml                    # 依赖: langgraph, httpx, python-dotenv
├── app/
│   ├── main.py                       # FastAPI 入口
│   ├── api/auth.py                   # 认证路由（已实现）
│   ├── orchestration/                # LangGraph 编排层（本次新增）
│   │   ├── __init__.py
│   │   ├── state.py                  # OrchestrationState
│   │   ├── dify_client.py            # DifyClient
│   │   └── graph.py                  # StateGraph
│   └── api/routes/
│       └── orchestration.py          # FastAPI 路由（待实现）
├── tests/
│   └── test_auth_api.py              # 认证测试（已实现）
└── test_dify_orchestration.py        # 原型测试脚本（本次新增）
```

---

## 10. 开发路线图

| 阶段 | 任务 | 状态 |
|------|------|------|
| Phase 0 | Dify API 连通性测试 | ✅ 完成 |
| Phase 1 | LangGraph 原型：DifyClient + StateGraph | ✅ 完成 |
| Phase 2 | FastAPI 路由：`/start` `/continue` `/stream` `/result` | 待开发 |
| Phase 3 | ExecutionRegistry + SSE 推送 | 待开发 |
| Phase 4 | 意图识别 Chatflow 集成 | 待开发 |
| Phase 5 | w1/w2 Workflow 并行执行 | 待开发 |
| Phase 6 | 前端 Zustand Store + SSE 消费 | 待开发 |

---

## 11. 已知的实测发现（vs ARCHITECTURE.md 差异）

| 项目 | ARCHITECTURE.md 假设 | 实测结果 |
|------|---------------------|----------|
| `mode` | `"chat"` | `"advanced-chat"` |
| `answer` 格式 | 可能是自然语言 | **总是 JSON 字符串** |
| 完成检测方式 | JSON 提取 / Markdown 标题 | **检查 `type == "basic_profile"`** |
| 多轮状态 | conversation_id | conversation_id + confirmed_info 逐轮填充 |
| API URL | `http://8.162.7.16/v1` | `http://localhost/v1` |
