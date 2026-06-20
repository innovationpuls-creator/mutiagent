# OneTree (一棵树) 多智能体对话与编排架构

一棵树系统的核心后端是一个本地运行的、基于 **FastAPI + LangGraph + LangChain** 的多智能体协作与决策网络。该系统弃用了任何外部 Dify Chatflow 依赖，完全通过本地代码以及规则引擎进行确定性的决策和状态流转。

---

## 1. 架构总览

本系统实现了一个基于 **Supervisor-Worker** 拓扑的多智能体协作系统：
* **输入入口**：用户在前端（通过全局 AI 助手）输入提问或指令 ➡️ 后端接收请求并从数据库加载上下文 ➡️ 拼接为单轮 Graph 运行状态。
* **中枢调度 (Supervisor)**：由大语言模型（绑定多个智能体工具）与硬性规则引擎共同担任。
* **智能体执行层 (Workers)**：每个 Worker 是一个独立的 LangChain 链（结合 `structured_output`），在 Supervisor 指示下执行特定任务并输出结构化结果。
* **异步事件广播 (SSE)**：LangGraph 执行过程中产生的所有中间步骤（思考、智能体调用、部分结果生成、大模型流式文本等）均通过 Server-Sent Events (SSE) 实时推送到前端。
* **状态持久化**：不使用 LangGraph 的内存或 Redis checkpoint。状态在每次请求前从数据库重构，执行完毕后将数据（画像、按年路径、课程大纲等）持久化至 PostgreSQL。

```
                    ┌────────────────────────┐
                    │ 前端界面 (React/Zustand)│
                    └───────────┬────────────┘
                                │
                      POST /api/chat/message
                                │
                                ▼
         ┌────────────────────────────────────────────────┐
         │              后端 API (FastAPI)                │
         │  1. 加载 DB 上下文 (画像/大纲/路径/会话历史)    │
         │  2. 构建单轮 OrchestrationState                │
         │  3. 启动 LangGraph 异步事件生成                │
         └──────────────────────┬─────────────────────────┘
                                │
                                ▼
         ┌────────────────────────────────────────────────┐
         │             LangGraph 编排流                   │
         │                                                │
         │            ┌───────────────────┐               │
         │            │    Supervisor     │               │
         │            └──────┬──────┬─────┘               │
         │                   │      ▲                     │
         │             路由选择│      │Worker 返回结果      │
         │                   ▼      │                     │
         │    ┌─────────────────────┴───────────────┐     │
         │    │  Worker Agents (7 个协同智能体)     │     │
         │    │  - profile_agent                    │     │
         │    │  - learning_path_intake_agent       │     │
         │    │  - learning_path_agent              │     │
         │    │  - course_knowledge_agent           │     │
         │    │  - section_markdown_agent           │     │
         │    │  - section_video_search_agent       │     │
         │    │  - section_html_animation_agent     │     │
         │    └─────────────────────────────────────┘     │
         └──────────────────────┬─────────────────────────┘
                                │
                      SSE 流式推送中间事件
                                │
                                ▼
                    ┌────────────────────────┐
                    │ 前端接收事件并更新状态 │
                    └────────────────────────┘
```

---

## 2. 核心状态：`OrchestrationState`

系统运行的状态存储在 `OrchestrationState` 中。因为系统设计为**单轮无 Checkpoint**，因此每一轮对话在进入图谱前，都会从数据库加载关联的历史记录来完整初始化该状态。

```python
class OrchestrationState(TypedDict, total=False):
    # 输入参数
    user_id: str
    session_id: str
    query: str

    # 会话历史消息（通过 LangGraph 的 add_messages 进行追加合并）
    messages: Annotated[list[BaseMessage], add_messages]

    # 从数据库中预加载的业务数据上下文
    profile: Optional[dict]                  # 用户画像数据
    learning_path_intake: Optional[dict]     # 学习路径意见收集状态
    year_learning_paths: Optional[dict]      # 按年学习路径：{ "year_1": ..., "year_2": ... }
    course_knowledge: Optional[dict]         # 最近生成的课程大纲/知识大纲
    course_knowledges: Optional[list[dict]]  # 全量课程大纲列表

    # 本轮运行期间各智能体的结构化输出
    response: Optional[str]                  # Supervisor 给用户的文本回复
    grade_year: Optional[str]                # 正在处理的目标学年 (如 year_1)
    latest_grade_year: Optional[str]         # 用户的最新活跃学年
    course_resource_plan: Optional[dict]     # 课程资源（文档/视频/动画）的生成计划
    course_resource_result: Optional[dict]   # 课程资源生成的结果
```

---

## 3. 图谱拓扑结构与路由逻辑

图谱的节点注册在 `backend/app/orchestration/graph.py` 中。

### 3.1 节点列表
1. **`supervisor`**：决策中枢，分析用户当前对话阶段和输入，选择调用哪一个 Worker 或是直接给用户文本答复。
2. **`profile_agent`**：破冰阶段，通过与用户的多轮问答补充画像数据。
3. **`learning_path_intake_agent`**：在画像生成后，与用户确认期望重点学习哪些课程方向，生成草案结构。
4. **`learning_path_agent`**：当草案确认后，由该智能体规划生成完整的 4 年课程节点及按学年分布的学习路径。
5. **`course_knowledge_agent`**：当用户点亮某一课程并进入精读时，该智能体负责划分该课程的章节大纲以及对应知识点 ID。
6. **`section_markdown_agent`**：为特定课程章节生成详细的文本和核心要点 Markdown。
7. **`section_video_search_agent`**：联网搜索匹配该章节内容的视频学习资源。
8. **`section_html_animation_agent`**：为该章节的抽象概念（如物理、算法）实时编写带控制交互的纯 HTML/JS 动画卡片代码。

### 3.2 路由规则
图谱的控制流主要依赖两个路由函数：

* **中枢后路由 (`route_after_supervisor`)**：
  * 分析 `supervisor` 节点的最近一条输出消息是否包含 Tool Call。
  * 如果包含，则直接跳转至对应的 Worker Agent 节点。
  * 如果不包含（表示 Supervisor 选择直接解答用户或已结束任务），则跳转至 `END`。

* **Worker 后路由 (`route_after_worker`)**：
  * **画像到路径**：当 `profile_agent` 刚收集满用户画像字段后，通过 `should_auto_continue_learning_path_after_profile` 自动跳回 `supervisor`，以此触发路径推荐。
  * **草案确认**：当 `learning_path_intake_agent` 完成收集并标记状态为 `confirmed` 时，跳回 `supervisor` 以自动触发完整的按年路径生成（`learning_path_agent`）。
  * **大纲资源生成链**：当 `course_knowledge_agent` 生成完章节后，如果该查询是资源生成指令，会跳转到 Supervisor，接着通过 conditional edge 顺次流转给 `section_markdown_agent` ➡️ `section_video_search_agent` ➡️ `section_html_animation_agent`，最终组装完成后跳转至 `END`。

---

## 4. SSE (Server-Sent Events) 事件协议

后端通过 FastAPI 的 `StreamingResponse` 建立 SSE 连接，以前端可直接捕获的事件格式实时推送执行细节。

### 4.1 SSE 消息格式
后端主要统一使用 `event: message` 的事件推送通道（为保持前端标准 `EventSource` 的跨端兼容），而具体事件的区分放在 data payload 中的 `type` 字段：

```text
event: message
data: {
  "type": "supervisor_thinking",
  "text": "规划中：我需要首先为您构建个人画像..."
}
```

### 4.2 常见事件类型定义

| 事件 (type) | 数据负载 (payload) 关键字段 | 说明 |
| :--- | :--- | :--- |
| `session_started` | `{ "session_id": "uuid" }` | SSE 通道已成功建立且会话启动 |
| `supervisor_thinking` | `{ "text": "思考字符串" }` | Supervisor 的中间思考与状态决策 |
| `agent_calling` | `{ "agent": "profile_agent", "label": "画像智能体" }` | 即将调用哪一个 Worker 节点 |
| `agent_progress` | `{ "agent": "...", "status": "running", "message": "正在生成..." }` | Worker 执行过程 of 流式进度更新 |
| `agent_result` | `{ "agent": "...", "success": true, "output_key": "..." }` | Worker 执行完毕并向 State 写入了对应输出 |
| `data_update` | `{ "profile?": ..., "year_paths?": ... }` | 告诉前端 State 中的数据已被更新，需同步至状态机 |
| `text_chunk` | `{ "chunk": "流式文本内容" }` | 最终回复给用户的文本流式输出 |
| `message_completed` | `{ "message": "本轮对话处理完毕" }` | 本轮会话完成，消息已被写入 ConversationSession 归档 |
| `session_completed` | `{ "session_id": "uuid" }` | SSE 通道即将关闭 |
| `error` | `{ "message": "错误原因" }` | 系统内部故障或 LLM 抛出异常 |

---

## 5. 状态同步与持久化细节

虽然 LangGraph 在图的节点间流动状态，但在 FastAPI 响应的最后阶段，系统会进行持久化以确保状态安全：
* 每一轮 Supervisor 或 Worker 执行对画像、按年级路径、课程大纲造成的修改，在单轮 Graph 执行结束后，会通过各自的 ORM 服务保存回 PostgreSQL。
* **消息历史**：用户的提问与 LLM 生成的 `text_chunk` 文本在单轮结束后会被包装为 `BaseMessage` 结构并整体追加持久化到 `ConversationSession`（存储在 SQLite/Postgre 的 JSONB 中），避免由于无 checkpoint 而遗忘历史对话。
