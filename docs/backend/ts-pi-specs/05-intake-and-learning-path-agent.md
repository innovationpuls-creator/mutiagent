# M5 开发文档：课程草案确认与按年学习路径生成

> 文档日期：2026-11-27  
> 对应里程碑：M5（前置依赖：M4）  
> 上位文档：`docs/backend/ts-pi-agent-redesign.md`、`docs/backend/ts-pi-specs/00-roadmap-and-milestones.md`

---

## 1. 目标范围与前置依赖

### 1.1 目标范围
在 `LangGraph.js` 主对话图中落地 **课程草案节点（`learning_path_intake_agent`）** 与 **按年学习路径节点（`learning_path_agent`）**，替代 Python 侧合计 2500 行的旧版实现；重点解决关键词硬判意图误触发、来源绑定靠模糊字符硬凑、知识缺口清空原草案，以及正式路径输出过重易超时四大痛点。

### 1.2 已锁定的业务决策
- **修改草案遇知识缺口**：保留当前已有草案不被清空，仅登记知识缺口上报管理员，并提示学生继续调整或确认原草案。
- **刷新路径时的旧大纲清理**：保持现有简单策略，生成/刷新该年级正式学习路径时按年级清空该年级旧课程大纲。

---

## 2. 现有源码盘点与必须兼容的边界约束

1. **知识库强绑定契约**（`backend/app/orchestration/agents/learning_path_intake.py`）
   - 课程数量必须在 **4–8 门**之间；每门课必须绑定已发布教材的 `source_textbook_id`、`source_textbook_title` 与 `source_outline_section_ids`（仅来自目录摘要 `outline_summary`，不喂正文）。
   - 无覆盖教材时，必须调用知识库服务记录 `KnowledgeGap`（返回 `gap_id`）进入管理员待办。
2. **防误删风险二次确认规则**（`backend/app/orchestration/agents/learning_path_intake.py`）
   - 拉取该学生已有 `UserCourseKnowledgeOutline` 课程名与已有学习路径中状态为 `in_progress` / `completed` 的课程名作为受保护集合。
   - 若新草案删掉或替换了任一受保护课程，状态必须强制置为 `risk_pending`、`requires_second_confirmation = true`，并列出 `risk_warnings`。
3. **正式路径 Schema 强契约**（`backend/app/orchestration/agents/learning_path.py`）
   - 必须严格输出 `schema_version = "learning_path.v2.course_node"`，包含 `grade_plans[grade_year].course_nodes`（4–8 门）、`chapter_nodes`、`core_knowledge_points`、`knowledge_relations`、`critical_paths`、`resource_generation_contract`、`dynamic_update_contract`、`current_learning_course`、`current_learning_courses`。
   - 每门课的标题、顺序、教材来源绑定必须 100% 继承已确认草案。
   - 若该年级已有进度快照（已完成课程数 / 下一门课程 ID），必须正确延续到 `current_learning_course`。

---

## 3. 业务模块设计与核心流转

### 3.1 课程草案节点（`learning_path_intake_agent`）

维护清晰四态（持久化在 `ConversationSession.session_state.learning_path_intake`）：
**`none`（无草案）→ `draft`（普通待确认）→ `risk_pending`（风险待二次确认）→ `confirmed`（已确认）**。

节点内部拆为 4 个协作子模块：
1. **交互意图决策器（Pi 节点内工具循环）**
   - 彻底移除旧版中文确认/修改/取消关键词表，按当前草案状态给 Pi Agent 注入 4 个精准动作工具：
     - **`propose_or_revise_draft`**：首次生成草案，或吸收学生提出的增删换课/换主题意见修订草案。
     - **`confirm_draft`**（仅当前存在 `draft` 或 `risk_pending` 时开放）：学生明确同意当前草案（或在风险提示后明确同意覆盖）时触发。
     - **`cancel_risk_revision`**（仅 `risk_pending` 态开放）：学生反悔、决定保留原路径时触发，回滚为普通草稿态并清空风险警告。
     - **纯文本直接回复（不调工具）**：学生只是追问某门课的难度、顺序理由或前置要求时，直接基于当前草案与教材摘要解答，**绝不改动草案状态**。
2. **教材目录检索与知识缺口保护模块**
   - 执行 `propose_or_revise_draft` 时，先调用 Python 内部教材检索接口获取目标方向的已发布教材目录摘要。
   - **知识缺口保护规则**：
     - 若此前已有有效草案（修改场景），且本次目标方向无匹配教材：**不覆盖、不清空原草案**，返回明确工具提示（含 `gap_id`），告知学生“该方向暂无已发布教材，已加入管理员待办，原有草案已为你保留，可以继续调整或直接确认原草案”。
     - 若此前无草案（首次规划），则明确提示暂无覆盖教材并已上报管理员，引导换方向或等待补充。
3. **来源绑定确定性校验器 + Pi 原地自纠**
   - 校验草案中的 4–8 门课是否全部引用本轮检索到的真实 `source_textbook_id` 与 `source_outline_section_ids`（严禁越界与编造）。
   - 取消旧版本地字符打分硬凑小节的兜底：校验失败直接把具体非法项作为工具错误反馈给 Pi 循环，由模型在同轮内重新选择真实小节（最多自纠 2 次）。
4. **确定性风险检测器**
   - 由程序对比新草案课程标题与 Python 内部接口返回的“受保护课程清单（已有大纲或已开始/已完成学习）”，命中删除/替换则强制置 `status = "risk_pending"` 并生成风险清单。
5. **图流转决策（`Command`）**
   - 当状态流转为 `confirmed` 时，持久化确认态并通过 `Command({ goto: "learning_path_agent" })` **同轮无缝跳转**至正式路径生成节点。
   - 其余状态（`draft` / `risk_pending` / 纯问答）则持久化后 `goto: END`，等待学生下一轮回复。

### 3.2 正式学习路径节点（`learning_path_agent`）

采用 **“模型做轻量教学规划 + 程序做确定性契约装配”** 架构，解决大 JSON 超时与字段漂移：
1. **轻量规划生成器（Pi 结构化输出 + 1 次自纠）**
   - 输入：学生画像、已确认草案（含课程标题、顺序与学习边界）、已有进度快照。
   - 模型**只输出核心规划语义**：学年总目标、目标类型、预期成果、四年成果、当前聚焦与下一步行动，以及与草案一一对应的课程规格列表（学期范围、预计周期、节奏理由、课程目标、阶段标题列表、核心知识点、重难点、验收标准、难度等级）。
   - 校验课程规格数量必须严格等于草案课程数；不匹配时触发 1 次原地自纠。
2. **路径图谱与契约装配器（纯确定性模块）**
   - 严格按草案顺序强制回填每门课的 `course_or_chapter_theme`、`source_textbook_id`、`source_textbook_title`、`source_outline_section_ids`。
   - 程序自动生成所有 `course_node_id`、`chapter_nodes`、`knowledge_hierarchy`、`knowledge_relations`（含 `contains` 与 `prerequisite` 边）、`critical_paths`、`resource_generation_contract`、`dynamic_update_contract`，确保 100% 符合 `learning_path.v2.course_node` 契约。
3. **已有进度延续器（纯确定性模块）**
   - 若该年级存在既有进度快照，自动将 `current_learning_course` 定位到对应进行中课程或已完成态。
4. **原子落库（调 Python 内部接口）**
   - 写入 `UserYearLearningPath` 并按既有简单策略清空该年级旧的 `UserCourseKnowledgeOutline`；同时更新会话状态并流式输出以 `"学习路径已生成"` 开头的收口摘要（兼容前端结构化卡片挂载）。

---

## 4. Python 内部接口契约新增

- `GET /internal/knowledge-base/published-textbooks`（全部已发布教材的紧凑目录）、`GET /internal/knowledge-base/published-textbooks/{id}/outline`（小节 ID 与标题）、`POST /internal/knowledge-base/gaps`（登记知识缺口，同一主题去重并返回 `gap_id`）。教材与小节由模型自己判断选哪些，Python 不再做关键词匹配（此段为 M5 原设计，M9 后由 agent 工具取代原 `textbook-context-for-intake` 检索接口）。
- `GET /internal/students/{user_uid}/protected-courses`：返回已有大纲或已开始/已完成学习的受保护课程标题及保护原因，供确定性风险检测使用。
- `GET /internal/students/{user_uid}/learning-paths/progress-snapshots`：返回各年级既有学习进度快照。
- `PUT /internal/students/{user_uid}/learning-paths/{grade_year}`：在单个数据库事务内保存新按年学习路径，并清空该年级旧的课程大纲。

---

## 5. 风险点与缓解策略

1. **草案确认后同轮生成正式路径耗时较长**：在 `learning_path_intake_agent` 跳转到 `learning_path_agent` 时立即推送 `agent_result`（草案已确认）与 `agent_calling`（学习路径智能体开始处理），配合 M1 SSE 心跳保活，避免前端误判超时。
2. **模型规划结果与草案数量不一致**：通过 TypeBox Schema 约束数组长度 + 确定性数量核验 + 1 次原地自纠，确保绝不落库错位路径。

---

## 6. M5 可执行验收清单

| 编号 | 验收维度 | 具体验证步骤 | 预期达成结果 |
|---|---|---|---|
| **AC-1** | 草案问答不误触发 | 生成草案后提问“第 2 门课会不会太难？为什么排在这里？” | 模型直接结合草案与教材目录解答，草案状态保持 `draft`，不误触发正式路径生成。 |
| **AC-2** | 来源绑定校验与自纠 | 单元测试中模拟模型首次输出伪造 `section_id`，验证 Pi 工具循环 | 确定性校验拦截伪造 ID，模型在同轮内自纠替换为目录中真实存在的 `section_id`。 |
| **AC-3** | 修改遇知识缺口保留原草案 | 已有草案后输入“把第 3 门换成量子力学” （知识库无对应教材） | 后端新增一条 `KnowledgeGap` 待办；原草案完整保留未被清空；回复明确提示并允许继续确认原草案。 |
| **AC-4** | 风险二次确认与取消回滚 | 对已有大纲或已开始学习的课程执行删除/替换修改 → 先回复“算了先不改” → 再重新修改并回复“确认覆盖” | 首次修改进入 `risk_pending` 并列出受影响课程；取消后回滚为普通草稿不改路径；确认覆盖后推进正式路径生成。 |
| **AC-5** | 草案确认同轮无缝出路径 | 回复“可以，按这个生成吧” | 同一次 SSE 请求内自动由草案节点跳至路径节点；生成路径严格满足 `learning_path.v2.course_node`、课程顺序与教材绑定 100% 一致、旧年级大纲被清空、繁枝页渲染正常。 |
| **AC-6** | 已有进度正确延续 | 在已有 1 门已完成课程的年级刷新路径 | 新路径 `current_learning_course` 准确延续定位到对应后续课程节点。 |
