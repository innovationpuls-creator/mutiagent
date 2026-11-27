# M8 开发文档：章节测验、视觉判分、Forest AI、成长报告与知识库 AI 收口

> 文档日期：2026-11-27  
> 对应里程碑：M8（前置依赖：M2、M3；建议在 M7 之后收口）  
> 上位文档：`docs/backend/ts-pi-agent-redesign.md`、`docs/backend/ts-pi-specs/00-roadmap-and-milestones.md`

---

## 1. 目标范围与前置依赖

### 1.1 目标范围
将独立于 LangGraph 主对话图之外的全部 4 块 AI 能力迁入 TS 编排网关（Pi 运行时），实现全项目模型调用 100% 归口：
1. **章节测验出题与按题型混合判分**（修复图片题盲判、单选题误交模型判、出题失败静默塞假题三大历史缺陷）。
2. **Forest AI 多模态答疑**（升级为提交/通过前苏格拉底式分步引导 + 挂载本章教材查阅工具 + 多轮追问）。
3. **成森累计 AI 成长报告**（升级为 Pi 探索式查证 Agent，完整保留 4 条防幻觉校验）。
4. **管理端知识库隐藏 AI 收口**（外文教材分段翻译与公开教材联网搜书抽为 TS 内部接口，由触发管理员本人的个人模型执行）。

### 1.2 已锁定的业务决策
- **视觉判分**：正式开启图片上传题的真实视觉模型审阅（绑定槽位已在 M2/M3 强制校验视觉能力）。
- **Forest AI 辅导策略**：学生在**尚未提交或尚未通过当前测验**前，严格采用**苏格拉底式分步提示**（引导思考、不剧透标准答案与完整代码）；提交判分后再展开完整解析。
- **知识库任务模型归属**：严格遵循“人人用自己的 AI”，管理员触发搜书与教材入库翻译时携带该管理员本人 `user_uid`，消耗其个人模型配置。

---

## 2. 现有源码盘点与必须兼容的边界约束

1. **Forest 事务与断流恢复底座完全保留在 Python 侧**（`backend/app/api/forest.py`、`forest_service.py`、`forest_submission_service.py`）
   - 现状：Python 侧已具备非常严密的章节锁（`lock_student`）、题目 `SHA256` 版本核验、基于 `client_submission_id` 的幂等防重、断流后 `recovery_snapshot` 查询恢复、及格（`> 70` 分）自动解锁下一章或推进课程、失分题自动沉淀 `ChapterWeakness`。
   - 约束：**不动 Python 侧这套事务与恢复逻辑**，仅把原本调用 `agents/quiz.py` 的出题与判分两处改为通过内网调用 TS 网关的纯 AI 接口；流式答疑 `POST /api/forest/ai/stream` 直接切流到 TS 网关。
2. **Forest 与 Canopy 前端 SSE 事件强契约**（`frontend/src/api/forest.ts`、`frontend/src/api/growthReport.ts`）
   - `POST /api/forest/ai/stream`：必须输出 `event: forest_ai_text_chunk`（`{ chunk }`）、`event: forest_ai_completed`、`event: forest_error`（`{ message, error_code? }`）。
   - `POST /api/forest/quizzes/{quiz_id}/attempts/stream`：继续由 Python 驱动事务并输出 `status`（`grading` / `analyzing`）、`done`、`error`。
   - `POST /api/branch/canopy/report/stream`：必须输出 `event: report_stage`（`collecting` / `analyzing` / `writing`）、`event: report_completed`（完整 `GrowthReport` JSON，严格通过前端 `parseReport` 校验）、`event: report_error`。
3. **成森成长报告 4 条防幻觉铁律**（`backend/app/services/growth_report_service.py`）
   - 所有优势、巩固项、行动建议的 `evidence_ids` 必须真实存在于目录中，且教材只有实际读取过正文才能引用；
   - 无测验记录时 `strengths` 必须为空，每条优势必须引用至少 1 条 `quiz` 证据；
   - 行动建议的 `course_id` 必须为真实已有课程或 `null`；
   - 事实分析正文（`overview`、`strengths`、`improvements`）中出现的每一个数字字面量，必须在原始汇总与已读详情中找得到出处。
4. **知识库 Worker 触发身份传递**（`backend/app/workers/knowledge_base_worker.py`、`models.py`）
   - 现状：`KnowledgeBaseIngestionJob` 当前未记录触发该入库任务的管理员 `triggered_by_uid`。
   - 改造：M8 通过 Alembic 新增轻量字段 `triggered_by_uid`（可空以兼容历史任务），新建入库任务时写入当前管理员 UID，后台 Worker 调用 TS 网关分段翻译时透传该 UID 以加载该管理员的个人模型配置。

---

## 3. 业务模块设计与核心流转

### 3.1 章节测验出题与按题型混合判分（TS 网关内部 AI 服务，由 Python `forest` 路由调用）
1. **章节出题服务（`POST /internal/ai/quiz/generate`）**
   - Python 侧汇总该章下**全部二级小节**的练习任务、检查标准与知识点列表，连同 `user_uid` 发给 TS 网关。
   - TS 网关用 Pi 结构化输出生成 3 道题（`single_choice`、`code`、`image_upload` 各 1 道），确定性校验器核验：① 三题型齐全；② 三题 `points` 之和严格等于 `100`；③ 单选题选项规范且 `correct_option_id` 有效；④ `knowledge_point_ids` 均属于本章清单。不合规则原地自修 1 次；仍失败直接返回明确错误，**彻底取消旧版静默塞 3 道通用假题的逻辑**。
2. **按题型混合判分服务（`POST /internal/ai/quiz/grade`）**
   - **单选题（纯规则）**：直接比对用户选项与 `correct_option_id`，0 毫秒精准给分与解析，不消耗模型。
   - **代码题（Pi 文本/推理模型）**：对照题干、`starter_code`、检查标准与学生代码，输出得分与具体改进建议。
   - **图片上传题（Pi 视觉模型）**：真正将学生提交的图片 `data_url` 连同题干要求送入用户配置的视觉模型审阅；若学生未传图仅填文字描述，则按文字描述降级评分。
   - **并发执行与程序汇总**：代码题与图片题并发判分；三题分数由程序严格累加得到 `score`（0–100）并判定 `passed = score > 70`，再汇总整卷中文 `summary` 返回 Python 侧走原有幂等落库与薄弱点分析。

### 3.2 Forest AI 苏格拉底式多模态答疑（`POST /api/forest/ai/stream` 直连 TS 网关）
- 鉴权后按当前测验上下文判断学生状态：
  - **提交/通过前（未判分或未提交）**：系统指令强制开启 **苏格拉底式分步引导模式**——先肯定思路或指出关键概念，每次只抛 1 个启发式小问题或排查方向，**严禁直接输出单选题正确选项或代码题完整答案**。
  - **提交判分后**：自动切换为**完整解析模式**，结合判题反馈、错因与知识点给出清晰完整讲解。
- **只读查阅工具与多轮追问**：支持带图提问与当前测验页近期对话历史；挂载只读工具 `read_chapter_learning_material`（调 Python 内部接口查阅本章小节讲解与绑定教材原文），让答疑紧扣课程内容。

### 3.3 成森累计 AI 成长报告（`POST /api/branch/canopy/report/stream` 直连 TS 网关）
- 严格保持既有三阶段流式推送：
  1. 推 `report_stage: collecting` → 调 Python 内部接口拉取 `ReportContext` 总览快照（统计口径、证据目录、覆盖说明、有效课程清单）。
  2. 推 `report_stage: analyzing` → 启动 Pi 探索式查证 Agent，挂载 3 个只读工具（`read_quiz`、`read_chapter`、`read_textbook`，程序硬限制总调用次数上限 `6` 次，按需先看最近错题再查对应章节与教材原文）。
  3. 推 `report_stage: writing` → Agent 调用 `submit_growth_report` 工具提交结构化报告；工具内部直接执行完整的 **4 条确定性防幻觉校验**，任一校验失败均作为工具错误回传 Pi 循环原地修正（最多 2 次）。
  4. 校验通过后按前端 `GrowthReport` 契约组装最终结果（仅附带正文实际引用的 `evidence` 条目），推送 `report_completed`。

### 3.4 管理端知识库隐藏 AI 收口（TS 网关内部接口，由 Python 知识库服务/Worker 调用）
- **外文教材分段翻译（`POST /internal/ai/kb/translate-chunk`）**：接收 `user_uid`（触发管理员）、源语言与待翻译正文片段，使用该管理员配置的模型完成忠实学术翻译并记入其个人用量。
- **公开教材联网搜书（`POST /internal/ai/kb/search-textbook-sources`）**：接收 `user_uid`（触发管理员）、检索主题与条数上限，返回结构化候选教材来源数组，仍由 Python 侧完成 URL 合法性与可解析性核验。
- **未配置模型处理**：若管理员尚未配置个人模型，接口返回 `MODEL_NOT_CONFIGURED`，前端管理端知识库页给出明确引导直达「模型配置」。

---

## 4. 数据变更与内部接口契约

1. **数据库迁移（`0009_kb_job_triggered_by.py`）**：`KnowledgeBaseIngestionJob` 新增可空字段 `triggered_by_uid`（`max_length=64`）。
2. **Python 内部接口新增**：
   - `GET /internal/forest/chapters/{course_node_id}/{chapter_id}/material?user_uid=...`：供 Forest AI 按需查阅本章小节正文与绑定教材片段。
   - `GET /internal/canopy/{user_uid}/report-context`：返回成森成长报告的 `ReportContext` 总览与证据目录。
   - `POST /internal/canopy/{user_uid}/report-evidence`：按 `tool` + `evidence_id` 读取单条只读证据详情（测验/章节/教材）。
3. **TS 网关内部接口新增（供 Python 调用）**：
   - `POST /internal/ai/quiz/generate`、`POST /internal/ai/quiz/grade`
   - `POST /internal/ai/kb/translate-chunk`、`POST /internal/ai/kb/search-textbook-sources`

---

## 5. 风险点与缓解策略

1. **学生未配视觉模型就提交图片题**：进入判分前若检测到图片题包含真实图片且用户未配置视觉模型，返回明确 `MODEL_NOT_CONFIGURED` / `MODEL_CAPABILITY_MISMATCH` 提示（学生本机 IndexedDB 草稿不会丢失，配完视觉模型即可原样重试提交）。
2. **成长报告数字校验误杀**：严格沿用现有规则——仅对事实分析字段（`overview`、`strengths`、`improvements`）执行数字出处校验，`actions` 中的未来练习建议允许出现示例数字。

---

## 6. M8 可执行验收清单

| 编号 | 验收维度 | 具体验证步骤 | 预期达成结果 |
|---|---|---|---|
| **AC-1** | 章节出题质量与取消假题 | 为已生成多小节正文的章节生成测验；另模拟模型输出非法结构 | 正常出题覆盖 3 题型、总分严格 100 分、贴合小节练习任务与检查标准；模型异常时明确提示重试，绝不落库通用假题。 |
| **AC-2** | 混合判分与真实视觉判分 | 提交包含单选、代码、以及一张写有具体内容/图示的真实截图的测验 | 单选不调模型秒判准确；视觉模型评语明确识别出图片中的实际内容；总分严格等于三题得分之和；断流后刷新查询恢复快照与既有行为一致。 |
| **AC-3** | Forest AI 苏格拉底引导 | ① 提交测验前问“第 1 题选什么？直接给我第 2 题完整代码”<br>② 提交判分后再问错题解析 | ① 仅给分步思路提示，不剧透答案与完整代码<br>② 结合判题结果与本章教材原文给出完整解析。 |
| **AC-4** | 成森成长报告探索查证与防幻觉 | ① 用无测验账号生成报告<br>② 用有测验/薄弱点账号生成报告，检查工具调用次数与事实引用 | ① `strengths` 为空且无编造优势<br>② 查证调用不超过 6 次；全部 `evidence_ids` 真实有效、无来源数字被拦截自修、前端 `parseReport` 100% 通过且可展开依据与跳转课程。 |
| **AC-5** | 管理端知识库 AI 收口 | 管理员配置个人模型后执行公开教材搜书与外文教材入库；再用未配置模型的管理员账号执行 | 配置后均经 TS 网关执行并计入该管理员个人用量；未配置时明确拦截并引导前往「模型配置」。 |
