# OneTree AI 编排网关重构：小目标拆解与验收总纲

> 文档日期：2026-11-27  
> 上位设计文档：`docs/backend/ts-pi-agent-redesign.md`  
> 执行纪律：**先深读对应模块源码 → 产出该模块开发文档（`docs/backend/ts-pi-specs/0X-*.md`）→ 按文档实现 → 逐项通过验收达成点后进入下一目标。**

---

## 1. 目标依赖全景与执行顺序

```text
M1 (网关基座与跨服务协议)
 ├──▶ M2 (个人 Pi 模型配置后端与运行时)
 │     ├──▶ M3 (双端菜单栏模型配置页与快捷切换器)
 │     ├──▶ M4 (主对话图骨架 + Supervisor + 画像采集)
 │     │     └──▶ M5 (课程草案确认 + 按年学习路径)
 │     │           └──▶ M6 (课程章节大纲生成)
 │     │                 └──▶ M7 (小节多模态教学资源子图)
 │     └──▶ M8 (章节测验/视觉判分 + Forest AI + 成长报告 + 知识库 AI 收口)
 └───────────────────────────────────────────────────────────────┐
                                                                 ▼
                                   M9 (旧依赖清退 + 生产部署适配 + 全链路回归验收)
```

**推进原则**：
- 主链路严格按 **M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8 → M9** 顺序推进，确保每一阶段都能独立验证、可回滚、不破坏现有页面契约。
- 若多人并行，M3（前端模型配置页）可在 M2 完成后与 M4 并行；M8（测验/报告/知识库 AI）在 M2、M3 完成后可独立切流。

---

## 2. 逐目标拆解、必读源码清单与验收达成点

### M1：TS 编排网关骨架、跨服务协议与鉴权基础设施
- **前置依赖**：无
- **目标开发文档**：`docs/backend/ts-pi-specs/01-gateway-foundation.md`
- **编写文档前必读源码**：
  - `backend/app/main.py`、`backend/app/core/config.py`、`backend/app/core/security.py`、`backend/app/core/observability.py`
  - `backend/app/api/orchestration.py`、`backend/app/api/health.py`
  - `frontend/vite.config.ts`、`frontend/src/api/http.ts`、`frontend/src/api/orchestration.ts`
  - `deploy/nginx/conf.d/bootstrap.conf.template`、`deploy/nginx/conf.d/production.conf.template`、`deploy/compose.production.yml`
- **核心业务设计范围**：
  - 确立 `ai-gateway/` 独立服务工程规范、运行端口、健康检查、请求 ID 透传与结构化日志规范。
  - 确立 TS 网关与 Python 后端的双向安全通信协议（内部服务鉴权令牌、JWT 复用校验、统一超时与错误码规范，含“未配置个人模型”标准错误码）。
  - 确立本地 Vite 代理与生产 Nginx 的路由分流清单，明确哪些路径进 TS 网关、哪些保留在 Python 后端。
  - 确立前端既有 SSE 事件协议的统一适配规范。
- **验收达成点**：
  1. `ai-gateway` 可独立启动并通过存活/就绪健康检查，日志携带与 Python 后端一致的请求 ID。
  2. 通过 Vite 代理访问流式接口能正确路由到 TS 网关，有效 JWT 放行、无效/过期 JWT 返回 401。
  3. TS 网关调用 Python 内部接口必须携带有效内部令牌，未携带或令牌错误时 Python 侧拒绝访问（401/403）。
  4. 统一错误码契约（特别是“用户未配置可用模型”）在 TS 网关与前端 HTTP/SSE 封装层均可被准确识别。

### M2：全员个人 Pi 模型配置后端与运行时（API Key / 自定义端点 / Compat / Web OAuth / 用量）
- **前置依赖**：M1
- **目标开发文档**：`docs/backend/ts-pi-specs/02-personal-pi-model-config-backend.md`
- **编写文档前必读源码**：
  - `backend/app/models.py`、`backend/app/database.py`、`backend/app/migration_cli.py`、`backend/migrations/`（确认最新 Alembic 迁移基线）
  - `backend/app/services/student_lock.py`、`backend/app/orchestration/llm.py`
  - `backend/app/schemas.py`、`backend/app/export_openapi.py`
- **核心业务设计范围**：
  - **数据持久化层（Python）**：设计 4 张表（用户 Provider 凭证密文表、用户自定义模型表、用户场景槽位与偏好表、模型调用用量流水表）与 Alembic 迁移脚本；建立应用层密钥加密/脱敏服务、按「用户 + Provider」加行锁的 OAuth 并发刷新保护、以及供 TS 网关调用的内部配置读取与用量回写接口。
  - **Pi 运行时层（TS 网关）**：对接 Pi 内置模型目录与自定义模型注册（含协议族、自定义请求头、能力标签、Compat 兼容项）；实现多用户按请求模型装配、短周期缓存与保存即热失效机制；实现 6 档思考深度、Prompt 缓存与故障回退链（Fallback Chain）；实现一期 Web 端双模式 OAuth 授权（自动回调 + 手动粘贴授权码兜底）；实现三项能力连通性探针（文本/工具/视觉）与用量统计上报。
- **验收达成点**：
  1. 任意用户可独立增删改查内置及自定义 Provider（含 Compat 兼容参数），数据库内 API Key 与 OAuth Token 全程加密，所有对外响应绝不返回明文凭据。
  2. 能力防呆生效：未声明视觉能力的模型尝试绑定到「测验图片判分 / 多模态答疑」槽位时被服务端拒绝。
  3. Web 端 OAuth 双模式（自动回调与手动粘贴授权码）均能跑通；并发触发过期 Token 刷新时仅发起一次上游刷新请求，不发生 Refresh Token 互相顶掉失效。
  4. 三项连通性探针能准确返回文本、工具调用、视觉理解的可用状态与首字延迟。
  5. 故障回退链实测生效：主模型返回限流或 5xx 时自动无感切换备用模型，且调用用量（输入/输出/缓存/推理 Token 与估算费用）准确落库。
  6. 修改任意模型配置或思考深度后，热更新通知使 TS 网关即时失效对应用户缓存，无需重启服务，下一次调用立即生效。

### M3：双端菜单栏「模型配置」页面与工作区快捷切换器（前端）
- **前置依赖**：M2
- **目标开发文档**：`docs/backend/ts-pi-specs/03-personal-pi-model-config-frontend.md`
- **编写文档前必读源码**：
  - `frontend/src/App.tsx`、`frontend/src/components/layout/MainLayout.tsx`、`frontend/src/components/layout/AdminLayout.tsx`
  - `frontend/src/components/ui/Navbar.tsx`、`frontend/src/contexts/AuthContext.tsx`、`frontend/src/contexts/AiWidgetContext.tsx`
  - `frontend/src/components/onboarding/GlobalAiWidget.tsx`、`frontend/src/components/onboarding/AiGreetingInput.tsx`、`frontend/src/pages/forest/ForestQuizPanels.tsx`
  - `docs/ui-design/09-布局骨架与响应式.md`、`docs/ui-design/10-组件原语.md`
- **核心业务设计范围**：
  - 学生端导航栏与管理端顶部菜单统一新增「模型配置」独立页面（复同一套个人配置视图，严格遵循现有 UI 规范与响应式布局）。
  - 页面涵盖：内置/自定义 Provider 与 OAuth 登录卡片、自定义模型与 Compat 参数配置、极简模式（主力 + 视觉模型一键配置）与高级模式（分场景槽位 + 回退链 + 能力防呆提示）、一键三项探针测试反馈、个人按天/按场景用量与费用看板。
  - 在全局 AI 对话面板顶部与 Forest AI 答疑栏内新增「当前模型 + 6 档思考深度」快捷切换器。
  - 全站统一接入“未配置个人模型”引导提示与一键跳转，覆盖所有 AI 入口及管理端知识库 AI 入口。
- **验收达成点**：
  1. 学生与管理员均可在各自菜单栏进入「模型配置」页并独立完成配置，双方数据完全隔离。
  2. 极简模式 2 分钟内可完成首次配置；高级模式下不具备视觉能力的模型在图片判分槽位中被禁用或清晰提示。
  3. 在对话框与 Forest 答疑栏切换模型或拨动 6 档思考深度，下一条发送的消息立即按新配置执行并持久化偏好。
  4. 未配置模型的用户触发对话、资源生成、测验、成长报告或知识库搜书/翻译时，界面弹出明确提示并提供直达「模型配置」的按钮；OAuth 授权过期时提示带“重新登录”按钮。
  5. 同步执行 OpenAPI 生成，`frontend` 单元测试、`npm run build` 与移动端/桌面端响应式布局检查通过。

### M4：主对话图骨架、入口分流、Supervisor 路由与画像采集（功能 1）
- **前置依赖**：M1、M2
- **目标开发文档**：`docs/backend/ts-pi-specs/04-supervisor-and-profile-agent.md`
- **编写文档前必读源码**：
  - `backend/app/api/orchestration.py`、`backend/app/api/chat_handlers.py`
  - `backend/app/orchestration/graph.py`、`backend/app/orchestration/state.py`、`backend/app/orchestration/rule_engine.py`、`backend/app/orchestration/agents/supervisor.py`
  - `backend/app/orchestration/agents/profile.py`、`backend/app/orchestration/agents/models.py`、`backend/app/orchestration/agents/prompts.py`、`backend/app/orchestration/default_fill.py`、`backend/app/orchestration/grade_contract.py`
  - `backend/app/services/conversation_session_service.py`、`backend/app/services/profile_service.py`
  - `frontend/src/onboarding/hooks/useChatSession.ts`、`frontend/src/onboarding/chatReducer.ts`、`frontend/src/lib/profileContract.ts`
- **核心业务设计范围**：
  - 搭建 `LangGraph.js` 主对话状态图、节点跳转（`Command`）与 SSE 自定义流输出契约。
  - 扩展会话持久化模型，增加显式结构化会话状态字段（为后续草案态与资源重生成侧重点打底），补齐 Python 内部上下文装载与画像读写接口。
  - 极简化入口分流：仅保留显式协议动作直通；删除旧导航/大纲/路径自然语言拦截处理器，改为注册只读查询工具交由 Agent 按需调用。
  - 实现 `supervisor` 节点：彻底移除 900 行关键词规则，仅保留 3 阶段动态工具集门禁（无画像 / 有画像无路径 / 有画像有路径）。
  - 实现 `profile_agent` 节点：基于 Pi 工具循环拆分「追问卡片工具」与「保存画像工具」，保持 16 字段库表与前端 `question_box` 契约兼容，核心字段必问、次要字段可合理默认，支持确定性校验失败原地自纠与“默认快速生成”。
- **验收达成点**：
  1. 无完整画像时，系统在工具层硬隔离路径与大纲工具，模型绝对无法越权调用。
  2. 新学生对话完善画像时，前端正常渲染 `question_box` 单选卡片；中途零散信息增量落稿不丢失；填写不支持年级或缺失核心字段时，Pi 循环在单轮内自动自纠或转追问。
  3. 学生使用自由表述询问“我现在学到哪了 / 看看路径 / 看看大纲”或普通学习问答时，无需命中固定关键词即可准确查库回答。
  4. 本轮消息与画像按先落库后发完成事件的顺序执行，刷新页面恢复会话后状态与历史消息完整一致。

### M5：课程草案确认与按年学习路径生成（功能 2）
- **前置依赖**：M4
- **目标开发文档**：`docs/backend/ts-pi-specs/05-intake-and-learning-path-agent.md`
- **编写文档前必读源码**：
  - `backend/app/orchestration/agents/learning_path_intake.py`、`backend/app/orchestration/agents/learning_path.py`
  - `backend/app/orchestration/guards.py`、`backend/app/orchestration/prompt_budget.py`
  - `backend/app/services/learning_path_service.py`、`backend/app/services/knowledge_base_service.py`（教材目录摘要检索与知识缺口登记部分）
  - `frontend/src/onboarding/learningPathFlow.ts`、`frontend/src/api/learningPath.ts`
- **核心业务设计范围**：
  - **课程草案节点（`learning_path_intake_agent`）**：维护四态流转（无草案 → 普通待确认 → 风险待二次确认 → 已确认）；Pi 工具循环支持四类业务动作（生成/修订草案、确认草案、取消风险修改、纯解答疑问）；来源绑定强校验 + 最多 2 次原地自纠；确定性防误删风险检测（对比已有大纲和已开始/已完成课程）；修改草案遇知识缺口时**保留原草案不清空**，上报管理员待办并提示学生继续调整或确认。
  - **正式路径节点（`learning_path_agent`）**：草案确认后同轮由 LangGraph 无缝跳转；采用“模型输出轻量核心规划 + 程序确定性装配图谱节点与下游契约”；严格继承草案课程数量、顺序与教材绑定；自动延续既有学习进度；刷新路径时维持按年级清空旧课程大纲的简单策略。
- **验收达成点**：
  1. 学生针对草案追问“第 2 门课为什么排前面”时，仅解答疑问，不改动草案状态也不误触发路径生成。
  2. 修改草案若涉及删除/替换已有大纲或已开始学习的课程，必然进入风险待二次确认态；回复取消可完整回滚，回复确认才推进。
  3. 已有草案基础上要求换成知识库未覆盖方向时，系统登记管理员知识缺口，原草案保持完整不被清空，学生可继续修改或确认原草案。
  4. 模型编造不存在的教材小节 ID 时，在当轮内通过自纠修正为真实小节，不依赖模糊字符硬凑。
  5. 草案确认后同一次请求内自动生成正式路径，课程顺序与教材绑定与草案 100% 一致，已有学习进度正确衔接，繁枝页渲染完全正常。

### M6：课程章节大纲生成（功能 3）
- **前置依赖**：M5
- **目标开发文档**：`docs/backend/ts-pi-specs/06-course-knowledge-agent.md`
- **编写文档前必读源码**：
  - `backend/app/orchestration/agents/course_knowledge.py`、`backend/app/services/course_knowledge_service.py`
  - `backend/app/services/knowledge_base_service.py`（小节正文绑定上下文与教材学生可见性校验部分）
  - `backend/app/services/leaf_service.py`、`backend/app/api/leaf.py`
- **核心业务设计范围**：
  - 确定性大纲骨架构建器：基于课程绑定的教材小节生成一级章/二级小节骨架与溯源字段；**单小节正文超过 8000 字时自动按段落/篇幅拆分为多个学生端小节**。
  - Pi 中文教学命名与合规自纠器：只生成个性化说明与学生可见中文文案，拦截英文原标题直出与内部小节 ID 泄露，违规时原地自纠 1 次。
  - 全年多课受控并发与局部成功：支持单门课与当前年级全部课程双模式；全年多课按 2–3 门并发执行并逐门推送进度，采用**部分成功策略**（已成功课程正常落库，仅提示失败课程并支持单独补生成）。
  - 落库前调用 Python 内部接口加学生锁核验路径版本，防止学习路径变动期间脏写大纲。
- **验收达成点**：
  1. 针对绑定超 8000 字教材小节的课程，大纲生成不再报错中断，能自动按合理段落拆分为多个学生端小节且溯源完整。
  2. 生成的全部章名、小节名、说明与知识点均为自然中文教学表达，无内部编号或未翻译英文标题泄露。
  3. 全年批量生成 4–8 门课大纲时，前端可收到逐门完成进度；人为制造其中 1 门失败时，其余成功课程正常持久化可读，且失败课程支持单独补生成。
  4. 大纲生成过程中若该年级学习路径被修改，落库被一致性校验拒绝并给出清晰重生成提示。

### M7：小节多模态教学资源生成子图（功能 4）
- **前置依赖**：M6
- **目标开发文档**：`docs/backend/ts-pi-specs/07-course-resources-subgraph.md`
- **编写文档前必读源码**：
  - `backend/app/orchestration/agents/course_resources/main.py`、`common.py`、`markdown.py`、`video.py`、`animation.py`、`bilibili.py`、`aliyun_bilibili_search.py`
  - `backend/app/orchestration/contracts.py`、`events.py`、`observability.py`、`recovery.py`
  - `backend/app/services/course_generation_status_service.py`、`backend/app/services/resource_quality_service.py`
  - `frontend/src/pages/leaf/LeafPage.tsx`、`leafPrompt.ts`、`leafGenerationEvents.ts`、`leafContentParser.ts`
- **核心业务设计范围**：
  - 统一收口为一个 `LangGraph.js` 资源生成子图，叶茂页按钮点击与对话触发完全走同一入口，消除双轨维护。
  - 入口统一完成当前课程归属校验、上一章测验解锁门禁、教材可见性校验与章节级生成锁；**将重生成侧重点追问从 AI 回复隐藏文本标记升级为会话显式结构化字段**。
  - 单小节并行流水线（2–3 小节并发）：单小节内先由 Pi 生成 5 板块图文与视频/动画需求单（不合规则原地自修）→ **视频检索与 HTML 动画并发执行** → 单小节拼装即时落库并推送可读事件，同步落盘小节阶段检查点。
  - 视频检索质量保障与平稳降级：优先优化检索词构建、相关性筛选与链接有效性核验；在高质量检索前提下，确无合格视频的小节平稳降级（正文跳过视频占位并提示暂缺），不阻断图文和交互动画交付。
  - 整章结束后释放章节生成锁并触发课程资源质量打分。
- **验收达成点**：
  1. 叶茂页按钮触发与聊天框触发均进入同一子图，推送的阶段事件可被前端 `leafGenerationEvents` 完整消费。
  2. 同一小节的视频检索与 HTML 动画确认并行运行；首小节拼装完成后立即落库可读，无需等待整章结束。
  3. 模拟某小节在动画阶段失败后重试整章，系统自动跳过已通过校验的图文和视频阶段，仅补跑失败阶段。
  4. 高质量视频检索正常命中可播放教学视频；模拟全部视频不可用时，该小节图文与交互动画仍正常拼装交付，不导致整章报错。
  5. 重生成已有章节时，通过会话显式结构化字段记录待确认重生成状态，不再依赖对话文本里的隐藏标记。

### M8：章节测验、视觉判分、Forest AI、成长报告与知识库 AI 收口（功能 5 & 6）
- **前置依赖**：M2、M3（建议在 M7 后收口，确保完整小节上下文可用于出题与查证）
- **目标开发文档**：`docs/backend/ts-pi-specs/08-quiz-forest-growth-and-kb-ai.md`
- **编写文档前必读源码**：
  - `backend/app/api/forest.py`、`backend/app/services/forest_service.py`、`backend/app/services/forest_submission_service.py`、`backend/app/orchestration/agents/quiz.py`
  - `backend/app/api/branch.py`、`backend/app/services/growth_report_service.py`、`backend/app/services/growth_report_context.py`、`backend/app/report_schemas.py`
  - `backend/app/services/knowledge_base_service.py`、`backend/app/workers/knowledge_base_worker.py`、`backend/app/api/knowledge_base.py`
  - `frontend/src/pages/forest/ForestQuizPage.tsx`、`ForestQuizPanels.tsx`、`frontend/src/pages/canopy/CanopyPage.tsx`、`frontend/src/api/forest.ts`、`frontend/src/api/growthReport.ts`
- **核心业务设计范围**：
  - **章节测验与混合判分**：Python 侧汇总本章全部二级小节的练习任务、检查标准与知识点，继续全权负责章节锁、题目版本校验、幂等提交与断流恢复快照；TS/Pi 实现强约束出题（取消假题降级）与按题型混合判分（单选纯规则 + 代码文本判分 + 图片真实视觉判分 + 程序累加总分与判定及格）。
  - **Forest AI 多模态答疑**：Pi 轻量多模态 Agent，挂载本章小节与教材只读查阅工具，支持当前测验页多轮追问；**提交/通过前严格采用苏格拉底式分步提示**，判分后再展开完整解析。
  - **成森累计成长报告**：Pi 探索式查证 Agent（3 个只读工具：测验/章节/教材，总调用上限 6 次 + 内置 4 条防幻觉校验的提交工具），保持既有三阶段 SSE 协议与前端溯源跳转兼容。
  - **知识库隐藏 AI 收口**：将外文教材分段翻译与公开教材联网搜书抽为 TS 网关内部接口；Python 知识库服务与后台 Worker 携带触发管理员的用户身份，使用**该管理员本人配置的模型**执行并记入个人用量。
- **验收达成点**：
  1. 章节出题覆盖单选/代码/图片三题且总分严格为 100 分，知识点均归属本章；出题失败时明确提示重试，不再静默落库通用假题。
  2. 提交判分时：单选题不调用模型直接秒判；上传真实截图/架构图时视觉模型能基于图内实际内容给分与评语；总分严格等于各题得分之和；断流后刷新查询恢复快照与既有行为 100% 一致。
  3. 测验提交前向 Forest AI 直接索要答案或完整代码时，仅返回分步引导提示不剧透；提交判分后追问错题能给出结合本章讲解/教材原文的完整解析。
  4. 成长报告按需多轮查证不超过 6 次；无测验记录时不输出优势项；正文不出现无来源数字；每条结论均可追溯到真实证据与有效课程跳转。
  5. 管理员执行公开教材联网搜书与外文教材入库翻译时，均走 TS 网关并消耗该管理员本人配置的模型；若管理员未配置模型则明确引导配置。

### M9：旧架构清退、生产部署适配与全链路回归验收
- **前置依赖**：M3、M7、M8 全部完成
- **目标开发文档**：`docs/backend/ts-pi-specs/09-cleanup-deploy-and-e2e-verification.md`
- **编写文档前必读源码**：
  - `backend/pyproject.toml`、`backend/Dockerfile`、`deploy/compose.production.yml`、`deploy/compose.ci.yml`、`deploy/env.production.example`、`deploy/nginx/`、`deploy/bin/`
  - `docs/backend/agent逻辑.md`、`docs/backend/backend-tech-stack.md`、`docs/database/数据库表结构.md`、`docs/project-overview.md`
- **核心业务设计范围**：
  - 彻底清理 Python 侧 `app/orchestration/` 旧编排代码与 `pyproject.toml` 中的 `langchain`、`langgraph`、`langchain-openai` 依赖。
  - 补齐 `ai-gateway` 的容器构建、生产 Compose 编排、Nginx 路由模板、环境变量模板与 Smoke 探测。
  - 同步更新 OpenAPI、前端 API 类型以及项目核心技术文档。
- **验收达成点**：
  1. `backend/pyproject.toml` 与运行环境中完全不含 `langchain`、`langgraph`、`langchain-openai` 依赖，且 `backend` 全量 `pytest` 通过。
  2. `ai-gateway` 单元测试、集成测试与类型检查全绿。
  3. `frontend` 单元测试、`npm run build` 及关键路径 E2E（个人模型配置 → 萌芽画像 → 繁枝路径 → 叶茂大纲与资源 → 成林测验与答疑 → 成森成长报告 → 管理端知识库）全绿。
  4. 生产 Compose 启动与 Smoke 检查通过，全部配套文档与代码现状核对一致。

---

## 3. 单个核心目标的标准作业流程（每轮统一遵循）

每个小目标（M1–M9）均按以下 3 步闭环推进：

1. **源码精读阶段**：按本总纲列出的「必读源码清单」逐一深读现有前后端代码、数据模型与接口契约，盘点隐藏边界条件与历史坑点。
2. **开发文档编写阶段**：在 `docs/backend/ts-pi-specs/` 下产出对应编号的开发文档，固定包含 6 个章节：
   - ① 目标范围与前置依赖
   - ② 现有源码盘点与边界约束（含必须兼容的前端/数据库契约）
   - ③ 业务模块设计与核心流转（不堆砌大段代码，讲清模块职责、状态机、异常与降级策略）
   - ④ 跨服务接口与数据模型变更（新增/修改表结构、Python 内部接口、对外 HTTP/SSE 契约）
   - ⑤ 风险点与回滚/灰度方案
   - ⑥ 可执行验收清单（对照总纲验收达成点细化到具体测试场景）
3. **开发与验收阶段**：确认开发文档无误后再编码实现，逐条勾选验收清单通过后，锁定当前目标并进入下一目标。
