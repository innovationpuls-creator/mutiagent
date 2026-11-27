# M4 开发文档：主对话图骨架、入口分流、Supervisor 路由与画像采集

> 文档日期：2026-11-27  
> 对应里程碑：M4（前置依赖：M1、M2）  
> 上位文档：`docs/backend/ts-pi-agent-redesign.md`、`docs/backend/ts-pi-specs/00-roadmap-and-milestones.md`

---

## 1. 目标范围与前置依赖

### 1.1 目标范围
在 TS 编排网关（`ai-gateway/`）搭建 `LangGraph.js` 主对话状态图，切流 `POST /api/chat/message` 入口，完成**极简化入口分流**、**3 阶段动态工具门禁 Supervisor** 与 **Pi 版画像采集节点（`profile_agent`）**；同步为会话表引入显式结构化状态字段，替代旧版在对话消息里夹带隐藏标记的做法。

### 1.2 灰度过渡说明
M4 切流 `POST /api/chat/message` 时，尚未迁完的下游节点（M5 课程草案/路径、M6 大纲、M7 资源）可暂留内部桥接或按开关分批切流，但 M4 完成后，**所有对话入口、自由问答、只读查库问答与画像采集全流程必须 100% 运行在 TS 网关上**。

---

## 2. 现有源码盘点与必须兼容的边界约束

1. **会话消息与结构化状态混存问题**（`backend/app/services/conversation_session_service.py`）
   - 现状：`ConversationSession` 仅有 `messages` JSONB 字段，旧代码把 `learning_path_intake` 草案对象直接混塞进 `messages` 数组，还把重生成待确认标记塞进 AI 文本。
   - 改造：M4 通过 Alembic 新增迁移 `0008_conversation_session_state.py`，给 `ConversationSession` 增加独立字段 `session_state`（JSONB，默认 `{}`），用于显式存放 `learning_path_intake`、`pending_leaf_regeneration`、`pending_profile_followup` 等结构化状态，同时兼容读取历史旧会话数据。
2. **画像 16 字段与前端卡片强契约**（`backend/app/orchestration/agents/profile.py`、`frontend/src/api/orchestration.ts`）
   - 现状：前端 `pickProfile()` 与 `hasCompleteBasicProfileRecord()` 强校验 16 个字段均存在且非空非 `"未知"`，并强校验 `type`（`"collecting"` / `"basic_profile"`）、`stage`、`question_mode`、`confirmed_info`、`defaulted_fields`、`question_md`、`question_box`（含 `question` 与 `options` 数组）、`text`、`summary_text`。
   - 约束：新 `profile_agent` 落库的 `profile_data` 必须 100% 满足上述结构契约，确保前端选项卡片渲染与会话恢复完全兼容。
3. **未消化薄弱点自动注入**（`backend/app/api/chat_handlers.py`）
   - 现状：装载对话上下文时，会查询当前课程下 `consumed = False` 的 `ChapterWeakness`，将其拼入画像 `weaknesses` 字段提示模型。
   - 约束：Python 内部上下文装载接口必须保留这一装配逻辑。
4. **先落库后发完成事件的持久性顺序**（`backend/app/api/chat_handlers.py`）
   - 现状：必须先把本轮 `human` 与 `ai` 消息写入 `ConversationSession`（若完整写入失败则至少兜底写入 `human` 消息），然后再发出 SSE `message_completed` 与 `session_completed`，防止前端收到完成事件后刷新页面丢消息。
5. **前端结构化卡片挂载匹配规则**（`frontend/src/api/orchestration.ts`）
   - 现状：前端刷新恢复会话时，依据助手回复文本是否等于 `profile.text` / `profile.summary_text` 或以特定前缀开头（如 `"学习路径已生成"`、`"课程大纲已生成"`）来挂载结构化卡片。TS 网关收口文案需沿用这些可识别格式。

---

## 3. 业务模块设计与核心流转

### 3.1 入口分流器（替代 813 行 `chat_handlers.py`）
收到 `POST /api/chat/message` 后，TS 网关依次执行：
1. JWT 鉴权与用户状态核验 → 调用 Python 内部上下文接口加载历史消息、`session_state`、画像、按年路径、当前大纲与未消化薄弱点（同时按既有节奏发出 `session_started` 与 `memory_loader` 进度事件）。
2. **仅保留显式协议动作直通**：
   - 若消息包含 `[LEAF_RESOURCE_GENERATION]` 或 `session_state.pending_leaf_regeneration` 存在待确认项，直接路由至资源生成子图（M7 接管）。
   - **彻底删除** `NavigationQueryHandler`、`OutlineReviewHandler`、`LearningPathReviewHandler` 三个关键词拦截器，全部交由主对话图通过只读工具智能处理。

### 3.2 `LangGraph.js` 主对话图与 `supervisor` 节点
1. **图状态与流转**：
   - 共享状态承载：`user_id`、`session_id`、`query`、`image_attachment`、`messages`、`session_state`、`profile`、`year_learning_paths`、`latest_grade_year`、`course_knowledge`、`response`。
   - 节点间流转统一采用 LangGraph.js `Command({ goto, update })`，彻底取消外层翻找最后一条 `ToolMessage` 的脆弱路由逻辑。
   - 所有实时事件（文本分片、工具调用开始/结果、数据加载提示）统一由节点内调用 `config.writer(...)` 通过 M1 的 SSE 适配器输出。
2. **3 阶段动态工具集门禁（替代 900 行 `rule_engine.py`）**：
   - 不再维护中文关键词表，也不靠提示词“恳求模型别调某工具”；直接按学生当前业务状态裁剪本轮传给 Pi 模型的工具清单：
     - **阶段 A（无完整画像）**：仅注入 `delegate_profile_agent`。
     - **阶段 B（有完整画像，无按年路径）**：注入 `delegate_profile_agent`、`delegate_learning_path_intake`、`get_student_progress_summary`。
     - **阶段 C（有完整画像 + 有按年路径）**：注入上述全部 + `get_learning_path`、`get_course_outline`、`delegate_course_knowledge`（已有大纲时再注入 `delegate_course_resources`）。
   - **只读查库工具原地执行**：当用户自由询问“我现在学到哪了 / 我的路径里有哪些课 / 看看大纲”时，Supervisor 直接调用只读工具拿库内真实数据并流式组织自然语言回复，顺便推送 `data_update` 事件，无需任何硬编码关键词。
   - **普通学习问答**：无需调业务工具时，直接流式输出文本并 `goto: END`。

### 3.3 `profile_agent` 节点（基于 Pi 工具循环，替代 2401 行旧 `profile.py`）
节点内部运行一个轻量 `pi-agent-core` 实例，挂载 2 个强类型 TypeBox 工具：
1. **`ask_profile_question`（收集追问态）**：
   - 入参包含本轮增量提取出的 `partial_confirmed`、`missing_fields`、`question_md` 与可选 `options`（保留常见字段如学习阶段、学习方式、学习节奏、内容偏好的标准预设选项，避免模型乱编）。
   - 行为：与已有草稿增量合并后落库为 `collecting` 态，返回符合前端 `question_box` 契约的结构并结束本轮，等待学生点选或输入。
2. **`save_student_profile`（完成 / 更新态）**：
   - 入参包含完整 16 字段 `confirmed_info`、`summary_text`、`use_defaults`（支持学生说“按默认快速生成”）。
   - **字段分层策略**：核心字段（年级、专业、学习阶段、学习目标、每周可用时间、学习方式）必须来自用户真实表达（除非用户明确要求按默认填充）；次要字段（如限制条件、优势/弱项、详细经历）在用户未提及时允许合理默认并记入 `defaulted_fields`。
   - **确定性校验 + 原地自纠**：工具内严格校验年级是否属于支持范围（大一~大四）、16 字段是否齐全非空；若不通过，直接返回 `isError: true` 与具体错误原因，由 Pi 循环在同一次请求内自动修正或改调 `ask_profile_question` 向学生确认（限制最多自纠 2 次）。
   - 校验通过后调 Python 内部接口持久化 `UserProfile`；若画像首次完成且无学习路径，可通过 `Command` 无缝流转至 `learning_path_intake_agent`（M5 上线后启用）。

---

## 4. 数据变更与内部接口契约

1. **数据库迁移（`0008_conversation_session_state.py`）**：`ConversationSession` 新增 `session_state`（JSONB，默认 `{}`，非空）。
2. **Python 内部接口新增**：
   - `GET /internal/chat/sessions/{session_id}/context?user_uid=...`：校验会话归属，一次性返回会话历史、`session_state`、画像（含未消化薄弱点拼接）、按年学习路径、当前课程大纲。
   - `POST /internal/chat/sessions/{session_id}/turn`：原子追加本轮消息（遵循先全量、异常兜底仅存用户消息原则）并更新 `session_state`。
   - `PUT /internal/students/{user_uid}/profile`：保存画像（支持 `collecting` 与 `basic_profile`），完成态更新时按既有逻辑清空过期当前大纲引用。
   - `GET /internal/students/{user_uid}/learning-overview`：供 Supervisor 只读工具查询进度、路径摘要与大纲摘要。

---

## 5. 风险点与缓解策略

1. **模型模型能力差异导致卡片格式漂移**：`ask_profile_question` 与 `save_student_profile` 的最终入库对象均由 TS 侧确定性组装器按前端 `pickProfile` 契约规范化，模型只填业务语义字段，不直接拼装前端协议外壳。
2. **未配置模型拦截**：进入 `supervisor` 前优先解析该用户「对话与画像」槽位配置，若未配置直接通过 SSE 推送 `MODEL_NOT_CONFIGURED` 错误事件并引导跳转，不写入空助手消息。

---

## 6. M4 可执行验收清单

| 编号 | 验收维度 | 具体验证步骤 | 预期达成结果 |
|---|---|---|---|
| **AC-1** | 3 阶段动态工具门禁 | 用无画像新账号发消息“直接帮我生成大纲和学习路径” | 工具列表仅含画像工具，模型无法越权调用路径/大纲节点，自然引导先完善画像。 |
| **AC-2** | 画像多轮采集与卡片渲染 | 新账号分 2–3 轮提供零散信息（年级、专业、目标），观察前端渲染与中途刷新 | 前端正常展示 `question_box` 单选卡片；中途刷新页面已填信息不丢失；收齐核心字段后自动落库为 `basic_profile`（16 字段齐全）。 |
| **AC-3** | 不支持年级与校验自纠 | 输入“我研二，软件工程，想学 AI” | 确定性校验拦截非大一~大四年级，Pi 循环自动转为礼貌追问/提示，不报错崩溃、不落库非法年级。 |
| **AC-4** | 默认快速填充通道 | 新账号输入“直接按默认帮我生成画像” | 一次对话完成画像落库，次要字段准确记入 `defaulted_fields`。 |
| **AC-5** | 自由表述只读查库 | 已有路径/大纲账号用非固定关键词提问（如“下个月我主要要学哪几门课？”） | Supervisor 自动调用只读查库工具基于真实数据回答，不依赖旧关键词表。 |
| **AC-6** | 持久化顺序与会话恢复 | 对话完成后立即刷新浏览器，检查历史消息与画像卡片挂载 | 历史消息完整无丢失，画像结构化卡片正确挂载在对应助手消息下。 |
| **AC-7** | 显式会话状态字段兼容 | 读取旧会话（`session_state` 为空、`messages` 含旧 `learning_path_intake`）与新会话 | 两者均正常解析恢复，无报错。 |
