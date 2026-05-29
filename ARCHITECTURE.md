# Chatflow 多轮对话编排架构

## 概述

本系统实现了一个基于 Dify Chatflow 的多轮对话编排流程：**前端 → 后端 API → Chatflow 多轮对话 → 完成检测 → w1/w2 并行执行 → SSE 推送结果**。

核心创新在于 Chatflow 本身是一个多轮对话 Agent（非单次 API 调用），后端通过 `start/continue` 端点管理其生命周期，在检测到对话"完成"信号后自动触发下游工作流并行执行。

## 架构总览

```
Frontend (React+Zustand)          Backend (FastAPI)                 Dify
      │                               │                              │
      │── POST /chatflow/start ──────>│                              │
      │                               │── POST /chat-messages ──────>│
      │                               │    (conversation_id="" 新对话) │
      │<── {exec_id, ans, conv_id} ──│<──── answer + conv_id ───────│
      │                               │                              │
      │  ... N 轮信息收集 ...          │                              │
      │                               │                              │
      │── POST /chatflow/continue ───>│                              │
      │                               │── POST /chat-messages ──────>│
      │                               │    (复用 conversation_id)     │
      │<── {answer, completed=false} ─│<──── still collecting ───────│
      │                               │                              │
      │  ... 最终用户说"可以了" ...    │                              │
      │                               │                              │
      │── POST /chatflow/continue ───>│                              │
      │                               │── POST /chat-messages ──────>│
      │                               │<──── JSON/教学大纲文档 ──────│
      │                               │                              │
      │  检测到完成!                   │                              │
      │                               ├── 并行执行 w1/w2 (Dify Workflow)
      │                               │                              │
      │  SSE: chatflow_completed      │<──── w1 result ──────────────│
      │  SSE: workflow_result(w1)     │<──── w2 result ──────────────│
      │  SSE: workflow_result(w2)     │                              │
      │  SSE: complete                │                              │
      │                               │                              │
      │── GET /result/{exec_id} ─────>│  (断线重连拉取)              │
```

## 状态机

### Chatflow 对话状态

```
pending → in_progress → awaiting_input → in_progress → ... → completed
                                                                ↓
                                                          触发 w1/w2
```

- `pending`: 初始状态
- `in_progress`: 正在等待 Dify API 响应
- `awaiting_input`: 等待用户输入下一轮消息
- `completed`: 检测到完成信号，进入 w1/w2 阶段
- `failed`: 出错

### 前端阶段

```
idle → chatflow → generating → completed
                    ↓
                  error
```

- `idle`: 欢迎页面
- `chatflow`: 多轮对话进行中（含 isPending 控制输入框禁用）
- `generating`: Chatflow 结束，w1/w2 执行中
- `completed`: 全部完成
- `error`: 出现错误

## 后端组件

### 1. ExecutionRegistry（单例）
- **文件**: [`execution_registry.py`](execution_registry.py)
- **职责**: 管理所有执行状态和 SSE 事件队列
- **关键状态字段**:
  ```python
  @dataclass
  class ExecutionState:
      execution_id: str
      chatflow_result: dict | None        # 最终结果 {"text": "...", "type": "..."}
      chatflow_completed: bool
      workflows: dict[str, WorkflowResult]  # {"workflow_a": WorkflowResult, ...}
      all_workflows_completed: bool
      conversation: ChatflowConversation    # 多轮对话状态
      queue: asyncio.Queue                 # SSE 事件队列
  ```
- **重要**: 5 分钟后自动清理已完成执行（`cleanup_completed`）

### 2. ChatflowConversationOrchestrator
- **文件**: [`chatflow_conversation.py`](chatflow_conversation.py)
- **职责**: 管理多轮对话生命周期
- **核心方法**:
  - `start_conversation(execution_id, query)` — 发起新对话
  - `continue_conversation(execution_id, query)` — 继续对话
  - `_call_chatflow_turn(query, conversation_id)` — 单次 Dify API 调用（每次新建 httpx.Client）
  - `_on_chatflow_completed(execution_id, final_result)` — 完成后触发 w1/w2
- **重要**: 每次 API 调用创建新 `DifyClient`（`httpx.Client` 非线程安全）

### 3. WorkflowExecutor
- **文件**: [`workflow_executor.py`](workflow_executor.py)
- **职责**: `asyncio.gather` 并行执行 w1/w2，结果推送 SSE 队列
- **重试**: 最多 3 次
- **输入**: `chatflow_result` 的 `text` 字段作为 `u_in`
- **清理**: 完成后 5 分钟自动清理

### 4. DifyClient
- **文件**: [`dify/client.py`](../../dify/client.py)
- **职责**: 封装 Dify Chatflow/Workflow API 调用
- **关键**: `httpx.Client` NOT thread-safe，需每次调用新建实例

### 5. DifyResponseNormalizer（注意修复）
- **文件**: [`dify/response_normalizer.py`](../../dify/response_normalizer.py)
- **Workflow 响应标准化**: 必须访问 `data.get("data", {})` 的嵌套层级
  ```python
  # Dify API 返回结构:
  { "task_id": "...", "data": { "id": "...", "outputs": {...} } }
  # 正确做法:
  inner = data.get("data", {})
  outputs = inner.get("outputs")
  ```

## API 端点

### `POST /api/orchestration/chatflow/start`
- **请求**: `{ "query": "我要生成教学大纲" }`
- **响应**: `{ "execution_id", "conversation_id", "answer", "completed" }`
- **说明**: 创建新执行实例，发起第一轮对话

### `POST /api/orchestration/chatflow/continue`
- **请求**: `{ "execution_id": "...", "query": "课程名称是数据结构" }`
- **响应**: `{ "answer", "completed", "final_result?" }`
- **说明**: 继续已有对话，`completed=true` 表示检测到完成
- **错误**: 409 (already completed), 500 (not found), 404 (wrong status)

### `GET /api/orchestration/stream/{execution_id}`
- **说明**: SSE 流式推送 w1/w2 结果
- **重要**: 所有事件使用 `event: message`（确保 `EventSource.onmessage` 兼容）
- **心跳**: 30 秒超时发送 `{"type": "heartbeat", "status": "still_running"}`

### `GET /api/orchestration/result/{execution_id}`
- **说明**: 获取已完成的执行结果（断线重连）
- **返回**: chatflow_result + workflows 结果

## SSE 事件协议

**关键约定**: 所有 SSE 事件使用 `event: message`，类型信息放在 data 的 `type` 字段。

```javascript
// EventSource 只能通过 onmessage 接收 event: message
const es = new EventSource(url);
es.onmessage = (msg) => {
  const event = JSON.parse(msg.data);
  switch (event.type) {
    case 'chatflow_turn':      // 每轮 Chatflow 回复
    case 'chatflow_completed': // Chatflow 结束
    case 'workflow_result':    // w1/w2 完成
    case 'heartbeat':          // 存活心跳（30s）
    case 'complete':           // 全部完成
    case 'error':              // 错误
  }
};
```

| type | 时机 | data |
|------|------|------|
| `chatflow_turn` | 每轮对话后 | `{conversation_id, answer, turn_index}` |
| `chatflow_completed` | Chatflow 结束 | `{final_result}` |
| `workflow_result` | w1/w2 完成 | `{workflow, status, result, error, retry_count, all_completed}` |
| `heartbeat` | 30s 无事件 | `{status: "still_running"}` |
| `complete` | 全部完成 | `{status: "all_completed"}` |
| `error` | 出错 | `{error}` |

## 完成检测策略

在 `is_chatflow_completed(answer)` 中实现，按优先级检测：

### 策略 1: JSON 提取
1. 去除 markdown 代码块包裹（` ```json `）
2. 从文本中提取第一个 `{` 到最后一个 `}` 的内容
3. `json.loads()` 解析
4. 检查 `data["type"] in ("teaching_syllabus", "teaching_plan", "teaching_calendar")`

### 策略 2: Markdown 标题结构检测（降级）
当 LLM 未按 JSON 格式输出时，在整个文本中搜索标题模式：

```python
_DOC_HEADING_PATTERNS = [
    (r'#\s*《[^》]*》\s*(?:课程)?教学大纲', 'teaching_syllabus'),
    (r'#\s*《[^》]*》\s*教学教案',            'teaching_plan'),
    (r'#\s*《[^》]*》\s*教案',               'teaching_plan'),
    (r'#\s*《[^》]*》\s*(?:课程)?教学日历',   'teaching_calendar'),
    (r'#\s*第\d+次课.*教案',                 'teaching_plan'),
]
```

**重要**: 必须在**整个文本**中搜索（不是仅第一行），因为 LLM 可能在标题前添加介绍段落。

### `_extract_json` 兼容性
```python
# 兼容场景:
"{'text':..., 'type':'...'}"         # 纯 JSON
"```json\n{'text':...}\n```"          # Markdown 代码块包裹
"好的，已生成：\n{'text':..., 'type':'...'}"  # 前后有文本
"{'text': '含 { 和 } 的内容', ...}"   # 嵌套大括号
```

## 配置文件

### `.env`
```
DIFY_API_KEY=app-xxx                          # Chatflow 入口 API Key
DIFY_API_URL=http://localhost/v1
DIFY_WF_DOCGEN_API_KEY=app-yyy                # Workflow1（文档生成）
DIFY_WF_SEARCH_API_KEY=app-zzz                # Workflow2（联网检索）
```

### `config/chatflow_orchestration.yaml`
```yaml
agents:
  chatflow:  # Chatflow 入口 - type 为 chatflow
    type: "chatflow"
    app_id: "chatflow"
    api_key: "${DIFY_API_KEY}"

  workflow1:  # 文档生成 - type 为 workflow，输入字段 u_in
    type: "workflow"
    app_id: "workflow1"
    api_key: "${DIFY_WF_DOCGEN_API_KEY}"

  workflow2:  # 联网检索 - type 为 workflow，输入字段 u_in
    type: "workflow"
    app_id: "workflow2"
    api_key: "${DIFY_WF_SEARCH_API_KEY}"
```

## 前端组件

### Zustand Store: `orchestrationStore.ts`
- **状态字段**: `phase`, `messages`, `executionId`, `conversationId`, `workflowResults`, `error`, `isPending`
- **关键逻辑**:
  - `isPending` 控制输入框禁用状态（API 调用期间为 true，返回后为 false）
  - `phase === 'generating'` 时显示 workflow 卡片
  - SSE 连接在 `startChatflow` 成功后自动创建
  - `completed=true` 时关闭 SSE（不等待 w1/w2 全部完成）

### API 客户端: `orchestration.ts`
- `startChatflow(query)` → `POST /chatflow/start`
- `continueChatflow(executionId, query)` → `POST /chatflow/continue`
- `connectSse(executionId, onEvent, onError)` → `EventSource /stream/{id}`

### 组件: `App.tsx`
- 欢迎页面（3 个建议按钮）
- 聊天区域（ChatMessage + 打字指示器 + workflow cards + 完成/错误横幅）
- 输入区域（ChatInput 组件）
- 自动滚动 `useEffect` + `scrollIntoView`

## 关键陷阱修复

| 问题 | 表现 | 修复 |
|------|------|------|
| `httpx.Client` 非线程安全 | 多线程竞争导致连接异常 | 每次 `_call_chatflow_turn` 新建 `DifyClient` 实例 |
| SSE event type 不匹配 | `EventSource.onmessage` 只接收 `event: message` | 所有事件使用 `event: message`，type 放 data 里 |
| Workflow API 响应嵌套层级错误 | outputs 始终为 None | `normalizer` 访问 `data.get("data", {}).get("outputs")` |
| LLM 未按 JSON 格式输出 | `is_chatflow_completed` 永远返回 False | 增加 Markdown 标题结构检测 |
| 标题前有介绍段落 | 第一行匹配不到标题 | 全文搜索，非仅第一行 |
| `str(dict)` 得到 Python repr | workflow 输入变成 `{'text': '...'}` 非 JSON | 使用 `chatflow_result.get("text", ...)` 直接传字符串 |

## 自定义适配指南

要在新项目中使用此架构，需要修改：

1. `_CHATFLOW_COMPLETION_TYPES` — 设置为自己的完成类型
2. `_DOC_HEADING_PATTERNS` — 匹配自己的文档标题格式
3. `_call_workflow` 中的 `u_in` — 改为 Dify Workflow 实际需要的输入字段名
4. 前端 `orchestrationStore.ts` 中的 SSE 事件处理逻辑
5. 前端 `App.tsx` 中的 UI 文案和样式

## 文件清单

```
backend/
├── .env                                           # API Keys
├── config/chatflow_orchestration.yaml              # Agent 配置
└── src/
    ├── agents/
    │   ├── base.py                                 # AgentConfig, AgentResult
    │   └── dify_agent.py                           # DifyAgent 调用封装
    ├── dify/
    │   ├── client.py                               # Dify HTTP 客户端
    │   ├── response_normalizer.py                  # 响应标准化（已修复嵌套）
    │   └── types.py                                # DifyAppType 枚举
    ├── api/routes/orchestration.py                 # FastAPI 路由
    └── orchestration/
        ├── __init__.py                             # 导出声明
        ├── execution_registry.py                   # 执行状态 + SSE 队列
        ├── chatflow_conversation.py                # 多轮对话编排器
        └── workflow_executor.py                    # w1/w2 并行执行器

frontend/
└── src/
    ├── api/orchestration.ts                        # 后端 API 客户端
    ├── store/orchestrationStore.ts                 # Zustand 状态管理
    ├── App.tsx                                     # 主 UI 组件
    └── components/
        ├── ChatInput.tsx                           # 输入框组件
        └── ChatMessage.tsx                         # 消息气泡组件
```
