# OneTree 中国软件杯技术文档资料盘点报告

> 盘点日期：2026-07-14（Asia/Shanghai）  
> 本地基线：`main` / `3fdc6f2f44569a8d5af427f72f4e1476c88beb95`  
> 远程仓库：`innovationpuls-creator/mutiagent`，默认分支 `main`  
> 交付用途：为中国软件杯六章技术文档建立可追溯事实、数据需求、验证结果与人工资料清单。本文不是最终参赛技术文档。
> 工作区说明：任务开始时 `git status --short` 为空；2026-07-14 16:02 后另一个并发工作流写入 3 个视频资源生产文件和 1 个对应测试文件。本报告保留这些改动，不把它们归为本任务产物，并在相关结论中单独标注。

## 1. 执行摘要

本仓库已具备编写“核心技术”“系统架构与实现”主体的源码依据：React/FastAPI 双端结构、13 个 router factory、55 条 OpenAPI paths、19 张 SQLModel 表、1 个 supervisor 与 7 个 LangGraph worker、多阶段 SSE、资源质量与恢复字段、知识库准入/发布/缺口闭环、Docker 生产基线均可定位到当前生产源码。第三章可先写架构事实；第二章可写实现机制，但必须保留检索、引用、持久化和恢复限制。

第一章仍缺赛题原文、立项依据、用户调研和真实使用规模；第四章仍缺单模型对比、知识库启停对比、人工准确性评价；第五章已有本次真实测试结果，但缺性能、并发、安全和真实外部模型验证；第六章缺团队分工、开发时间线、用户反馈与经确认的未来规划。因此，当前可以开始撰写有源码依据的技术章节，不具备直接完成整份正式文档的证据条件。

最高优先级事实冲突如下：

- 现行角色只有 `student` 与 `admin`；`teacher` 已被迁移/规范为 `admin`，`/teacher` 只是重定向。人工 API/数据库文档仍描述三角色。证据：`backend/app/schemas.py:9-12`、`backend/app/schema_upgrades.py:564-570`、`frontend/src/types/auth.ts:3`、`frontend/src/App.tsx:102-116`。
- 当前主图是 1 个 `supervisor` + 7 个 worker；`compose_resource` 是确定性拼装阶段，不是第 8 个 LangGraph worker。旧后端文档仍描述 3 个 worker。证据：`backend/app/orchestration/graph.py:42-60,159-195`、`backend/app/orchestration/contracts.py:6-45`、`backend/app/orchestration/agents/course_resources/common.py:1135-1204`。
- 当前模型共 19 张表，旧数据库文档只列 11 张；知识库 8 张表的业务关联没有数据库外键。证据：`backend/app/models.py:73-471`、`docs/database/数据库表结构.md:12-229`。
- 设计稿要求 pgvector/HNSW；当前 `Textbook.embedding` 是 `FLOAT[]`，仓库没有 embedding 写入/回填路径。SQL 检索异常会回退到标题/tag 字符串匹配，不能写成“pgvector 混合检索已跑通”。证据：`backend/app/models.py:336`、`backend/app/schema_upgrades.py:804-813`、`backend/app/services/knowledge_base_service.py:1549-1637`。
- README 声明 MIT，但仓库没有 `LICENSE`、`LICENSE.md`、`LICENSE.txt` 或 `COPYING`。正式材料只能写“许可证正文未提供”。证据：`README.md:32,308` 与根目录文件盘点。

本次验证结果：在并发工作区改动出现前，后端 `798 passed`；前端 Vitest `244 passed`；TypeScript/Vite 构建成功；Playwright `5 passed, 3 failed`。并发改动稳定后，视频搜索“持续空结果”和“单节超时”2 个精确测试 `2 passed in 1.65s`；没有在新工作区状态下重跑后端全量。GitHub 最新 `Production readiness` run `29289628662` 为 failure：Ruff 68 errors、Biome 85 errors/172 warnings、ShellCheck `SC2317`，因此不能声明 CI 通过。远程 PR 与 Issue 均为空，本地 `HEAD` 与 `origin/main` 指向同一提交，但工作区当前包含 4 个非本任务的未提交文件差异。

数据质量结论：本地 PostgreSQL 18.3 的用户数在任务期间从 3 增至 4，最终角色聚合为 2 个 `admin`、2 个 `student`；新增记录时间与并发工作流时段重合。培养方案仍为2、教材2、教材小节339。数据性质未被业务负责人确认且开发库存在并发写入，不能作为正式用户规模。学习路径、课程大纲、测验、答题、章节进度、薄弱点与资源质量表在首次快照均为 0；本地库不足以支撑效果指标。Alembic head 是 `0003_repair_ingestion_job_leases`，本地 `alembic current` 无版本，生产模式会被 `assert_schema_at_head` 阻止。

报告验证结论：**可以使用但需要注明限制**。源码结构、接口、表、测试命令与冲突清单可直接用于后续写作；本地业务数字、创新效果、外部服务成功率、E2E 全通过和 CI 全通过均不能作为正式结论。

### 范围、方法与证据等级

- 当前实现事实以本次本地执行、生产源码、测试源码、内存生成 OpenAPI、SQLModel metadata 为序。
- 远程状态由 GitHub App、已认证 `gh` 和本地 `git` 只读核对；GitHub App 的 commits/PR/Issue 接口遇到 API rate limit，随后由 `gh` 补齐。
- README、技术文档、设计规格、实施计划仅作为待核材料；计划 checkbox 不作为完成证明。
- 本地数据库查询全部在 `BEGIN READ ONLY` 事务中执行，仅输出聚合计数。
- 报告没有图表：当前定量证据主要是精确审计值和单次测试结果，表格比趋势图更适合，且不存在可验证的历史序列。

## 2. 六章数据需求总表

| 章节 | 小节 | 所需数据 | 当前状态 | 仓库来源 | 是否需要运行验证 | 是否需要人工补充 | 后续动作 |
|---|---|---|---|---|---|---|---|
| 1 项目概述 | 背景与赛题 | 赛题原文、申报要求、立项原因 | 不能用于正式文档 | 仓库未提供权威原文 | 否 | 是 | 获取盖章/官方版本并存档 |
| 1 项目概述 | 目标用户与角色 | `student`、`admin` 角色及历史 teacher 合并 | 可以直接使用 | `backend/app/schemas.py:9-12`; `frontend/src/types/auth.ts:3`; `backend/app/schema_upgrades.py:564-570` | 否 | 否 | 正式文档统一为两角色 |
| 1 项目概述 | 用户痛点 | 问卷、访谈、痛点比例、使用反馈 | 不能用于正式文档 | 仓库没有真实调研数据 | 否 | 是 | 设计并执行调研 |
| 1 项目概述 | 功能与业务流程 | 登录→萌芽→繁枝→叶茂→测验→成森；管理员管理 | 可以使用但需要注明限制 | `frontend/src/App.tsx:97-136`; `README.md:89-124` | 是 | 否 | 用真实账号补录页面与异常态 |
| 1 项目概述 | 当前完成度 | 模块接入、Mock、占位、未验证项 | 可以直接使用 | 本报告第 3、11、12 节 | 是 | 否 | 按规定状态引用 |
| 2 核心技术 | 学习画像与草案 | 输入、输出、门禁、持久化、风险确认 | 可以直接使用 | `backend/app/orchestration/agents/profile.py`; `backend/app/orchestration/agents/learning_path_intake.py`; `backend/app/orchestration/guards.py` | 已做契约验证 | 否 | 补真实模型运行样例 |
| 2 核心技术 | 学习路径与课程大纲 | 路径/outline 生成、来源绑定、质量失败 | 可以使用但需要注明限制 | `backend/app/orchestration/agents/learning_path.py`; `backend/app/orchestration/agents/course_knowledge.py` | 已做契约验证 | 否 | 补不同画像对比实验 |
| 2 核心技术 | 多智能体编排 | 7 worker、Supervisor、规则、阶段顺序 | 可以直接使用 | `backend/app/orchestration/graph.py`; `backend/app/orchestration/contracts.py`; `backend/app/orchestration/rule_engine.py` | 已做 4 个定向测试 | 否 | 正式图中把 compose 标为程序阶段 |
| 2 核心技术 | 知识库检索 | 准入、发布、搜索、evidence pack | 可以使用但需要注明限制 | `backend/app/services/knowledge_base_service.py`; `backend/app/models.py` | 尚未验证真实向量分支 | 否 | 不宣称 pgvector；补检索实验 |
| 2 核心技术 | 资源生成 | Markdown、视频、动画、compose、来源 footer | 可以使用但需要注明限制 | `backend/app/orchestration/agents/course_resources/` | 未验证真实外部服务 | 否 | 采集成功率与相关性 |
| 2 核心技术 | 测验评估 | 生成、作答、评分、薄弱点、解锁 | 可以直接使用 | `backend/app/api/forest.py`; `backend/app/services/forest_service.py`; `backend/app/models.py:148-220` | 后端全量测试已通过 | 否 | 补人工正确性评估 |
| 2 核心技术 | SSE/恢复/预算 | 事件、trace、checkpoint、字符预算 | 可以使用但需要注明限制 | `backend/app/orchestration/events.py`; `backend/app/orchestration/observability.py`; `backend/app/orchestration/recovery.py`; `backend/app/orchestration/prompt_budget.py` | 定向测试已通过 | 否 | 记录真实耗时与恢复次数 |
| 3 系统架构与实现 | 前端架构 | 入口、路由、布局、权限、API/SSE | 可以直接使用 | `frontend/src/main.tsx`; `frontend/src/App.tsx`; `frontend/src/api/` | 前端测试/构建已运行 | 否 | 补当前页面截图 |
| 3 系统架构与实现 | 后端/API | 13 router factory、55 paths、认证、服务 | 可以直接使用 | `backend/app/main.py:34-81`; `frontend/openapi.json` | OpenAPI/类型已内存核对 | 否 | 以生成 OpenAPI 为契约 |
| 3 系统架构与实现 | 数据库/ER | 19 表、主键、外键、无 FK 关系 | 可以直接使用 | `backend/app/models.py:73-471`; SQLModel metadata | 本地关系完整性已检查 | 否 | 绘图时区分 FK 与业务关联 |
| 3 系统架构与实现 | 部署 | Docker、Nginx、Postgres、worker、迁移 | 可以使用但需要注明限制 | `deploy/compose.production.yml`; `docs/deployment/docker-production.md` | CI 容器链未通过 | 是 | 补实际部署环境与验收记录 |
| 4 技术和功能创新 | 多智能体分工 | 单模型对照、结构合格率、失败率 | 尚未验证 | 当前只有实现与测试 | 是 | 是 | 执行第 14 节实验 |
| 4 技术和功能创新 | 反幻觉 | 知识库启停、事实错误、来源引用 | 尚未验证 | 有来源绑定实现，无对照数据 | 是 | 是 | 盲评并保留逐项证据 |
| 4 技术和功能创新 | 个性化 | 不同画像路径差异与合理性 | 尚未验证 | 生成链存在，无成组结果 | 是 | 是 | 固定模型版本做配对实验 |
| 4 技术和功能创新 | 恢复与预算 | 恢复成功率、裁剪次数、质量影响 | 尚未验证 | 字段存在，无真实运行聚合 | 是 | 否 | 保存 trace JSONL 并统计 |
| 5 系统功能测试 | 单元/API/组件 | 测试数量、通过、失败、时间 | 可以直接使用 | 本报告第 9 节本次命令 | 已运行 | 否 | 引用本次结果与日期 |
| 5 系统功能测试 | 端到端 | 真实浏览器覆盖与失败 | 可以使用但需要注明限制 | Playwright 本次 `5 passed, 3 failed` | 已运行 | 否 | 修复后重新独立运行 |
| 5 系统功能测试 | 性能/并发/安全 | P95、吞吐、错误率、权限与安全审计 | 不能用于正式文档 | 仓库没有本次真实结果 | 是 | 是 | 设计环境并执行测试 |
| 5 系统功能测试 | AI 质量 | 准确性、幻觉率、相关性、人工评价 | 不能用于正式文档 | 仓库没有真实评价集 | 是 | 是 | 建立标注集和双人复核 |
| 6 总结与展望 | 已完成与限制 | 模块状态、Mock、占位、部署/CI限制 | 可以直接使用 | 本报告第 3、9、11、12 节 | 否 | 否 | 与正文用词一致 |
| 6 总结与展望 | 价值与反馈 | 用户反馈、教育价值、推广价值 | 不能用于正式文档 | 无真实反馈 | 否 | 是 | 用调研与试用记录支撑 |
| 6 总结与展望 | 团队与时间线 | 成员、分工、里程碑 | 不能用于正式文档 | Git 历史不能替代团队确认 | 否 | 是 | 团队签字确认 |
| 6 总结与展望 | 未来规划 | 已确认范围、优先级、验收标准 | 尚未验证 | 历史 plans 存在但未统一 | 否 | 是 | 由团队确认当前路线图 |

## 3. 仓库真实模块清单

### 学生端、教师端与管理员端

| 功能名称 | 用户角色 | 页面入口 | 接口入口 | 主要源码 | 依赖服务/数据表 | 对应测试 | 当前状态 | Mock/固定数据 | 运行验证与备注 |
|---|---|---|---|---|---|---|---|---|---|
| 登录/注册 | 公共 | `/login` | `POST /api/auth/register`; `POST /api/auth/login`; `GET /api/auth/me` | `frontend/src/components/auth/AuthPage.tsx`; `backend/app/api/auth.py` | `auth_service`; `user` | `backend/tests/test_auth_api.py`; `frontend/src/components/auth/AuthPage.test.tsx` | 已实现并接入主流程 | OAuth 为 Mock | 后端/前端测试已通过 |
| 破冰对话 | 公共入口，完成后需 student | `/onboarding` | `POST /api/chat/start`; `POST /api/chat/message` | `frontend/src/components/learning/IcebreakerFlow.tsx`; `frontend/src/components/onboarding/AiGreetingInput.tsx`; `backend/app/api/orchestration.py` | 会话与 agent graph；`conversationsession` | orchestration 与 onboarding tests | 已实现并接入主流程 | 否 | `/onboarding` 本身无认证门禁 |
| 萌芽画像 | student | `/sprout` | `GET /api/profile/dashboard` | `frontend/src/pages/SproutPage.tsx`; `frontend/src/components/home/SproutHero.tsx`; `backend/app/orchestration/agents/profile.py` | `profile_service`; `userprofile` | `backend/tests/test_profile_api.py`; `frontend/src/pages/SproutPage.test.tsx` | 已实现并有测试 | 否 | 后端接口未声明 response model |
| 繁枝路径 | student | `/branch` | `GET /api/branch/overview`; `GET /api/student/matched-program` | `frontend/src/pages/branch/BranchPage.tsx`; `backend/app/api/branch.py` | 路径/大纲/培养方案；`useryearlearningpath`,`usercourseknowledgeoutline`,`cultivationprogram` | `backend/tests/test_branch_api.py`; `frontend/src/pages/branch/BranchPage.test.tsx` | 已实现并接入主流程 | 否 | E2E 因未拦截 matched-program 跳登录 |
| 叶茂课程 | student | `/leaf/:courseNodeId` | `GET /api/leaf/courses/{course_node_id}` | `frontend/src/pages/leaf/LeafPage.tsx`; `backend/app/api/leaf.py`; `backend/app/services/leaf_service.py` | 大纲、进度、资源 JSONB | `backend/tests/test_leaf_api.py`; `frontend/src/pages/leaf/LeafPage.test.tsx` | 已实现并接入主流程 | 视频封面 fallback | E2E fixture 字段漂移导致失败 |
| 成林入口 | student | `/forest` | 无 | `frontend/src/components/home/BlankPage.tsx`; `frontend/src/App.tsx:124` | 无 | `frontend/src/App.test.tsx` | 页面占位 | 否 | 标题 opacity 0 |
| 章节测验 | student | `/forest/:courseNodeId?chapter_id=...` | Forest 5 个接口 | `frontend/src/pages/forest/ForestQuizPage.tsx`; `backend/app/api/forest.py`; `backend/app/services/forest_service.py` | quiz/attempt/progress/weakness 表 | `backend/tests/test_forest_api.py`; `frontend/src/pages/forest/ForestQuizPage.test.tsx` | 已实现并有测试 | 否 | 后端全量测试已通过 |
| 成森图谱 | student | `/canopy` | `GET /api/branch/canopy` | `frontend/src/pages/canopy/CanopyPage.tsx`; `backend/app/api/branch.py` | 路径、测验、资源质量 | `backend/tests/test_canopy_api.py`; `frontend/src/pages/canopy/CanopyPage.test.tsx` | 已实现并有测试 | 否 | 未做本次真实账号截图 |
| 学习画布 | student | `/canvas` | 仅追问调用 `POST /api/forest/ai/stream` | `frontend/src/pages/canvas/ScratchpadCanvas.tsx` | 本地 React state | `frontend/src/pages/canvas/ScratchpadCanvas.test.tsx` | 固定数据 | 是 | 无加载/保存 API，无 Navbar 入口 |
| 教师入口 | admin（历史兼容） | `/teacher` | `/api/teacher/program*` | `frontend/src/App.tsx:112-116`; `backend/app/services/cultivation_program_service.py` | `cultivationprogram` | `backend/tests/test_cultivation_program_api.py` | 已废弃 | 否 | 页面仅重定向 `/admin/programs` |
| 培养方案管理 | admin | `/admin/programs` | `GET/PUT/POST /api/teacher/program*` | `frontend/src/pages/admin/AdminProgramsPage.tsx`; `backend/app/api/teacher.py` | `cultivationprogram` | AdminPrograms 与 cultivation tests | Mock 数据 | 是 | 上传未解析文件，加载固定课程后可调用真实发布 API |
| 账号管理 | admin | `/admin/accounts` | `/api/admin/accounts*` | `frontend/src/pages/admin/AdminAccountsPage.tsx`; `backend/app/api/admin.py` | `admin_account_service`; `user` | admin account tests | 已实现并有测试 | 否 | CSV import/export 存在 |
| 数据管理 | admin | `/admin/data` | `/api/admin/data*` | `frontend/src/pages/admin/AdminDataPage.tsx`; `backend/app/api/admin_data.py` | 多张学习数据表 | cultivation/API tests | 已实现并有测试 | 否 | overview 漏计 attempts/weaknesses |
| 知识库管理 | admin | `/admin/knowledge-base` | `/api/admin/knowledge-base*` | `frontend/src/pages/admin/AdminKnowledgeBasePage.tsx`; `backend/app/api/knowledge_base.py` | KB service 与 8 张 KB 表 | KB API/service tests | 已实现并接入主流程 | 否 | multipart upload、extension create 等前端未接 |

### 全局 AI 助手、后端、多智能体、知识库、评估与数据管理

| 功能名称 | 用户角色 | 页面/接口入口 | 主要源码 | 依赖服务/数据表 | 智能体 | 对应测试 | 当前状态 | 限制 |
|---|---|---|---|---|---|---|---|---|
| 全局 AI 助手 | 已认证用户 | 多数页面；`POST /api/chat/message` SSE | `frontend/src/components/onboarding/GlobalAiWidget.tsx`; `frontend/src/api/orchestration.ts`; `backend/app/orchestration/graph.py` | `conversationsession` | supervisor + worker | orchestration/SSE/UI tests | 已实现并接入主流程 | 在 login/forest/admin 隐藏 |
| JWT/权限基础服务 | 公共/已认证/admin | Bearer 与 role dependency | `core/security.py`; route dependencies | `user` | 无 | auth/admin/KB tests | 已实现并有测试 | 公开注册允许 role=`admin`; 禁用用户仍能登录取得 token |
| 多智能体编排 | 已认证用户 | `/api/chat/message` | `backend/app/orchestration/graph.py`; `backend/app/orchestration/agents/supervisor.py`; `backend/app/orchestration/rule_engine.py` | 会话/画像/路径/大纲 | 7 worker | orchestration contract tests | 已实现并接入主流程 | 无 LangGraph checkpoint |
| 课程资源管线 | student | 对话资源请求 | `agents/course_resources/` | `usercourseknowledgeoutline.outline_data` | markdown/video/animation | course resource tests | 已实现并接入主流程 | 外部服务未做真实验证 |
| 知识来源准入 | admin | `/api/admin/knowledge-base/sources` | `backend/app/services/knowledge_base_service.py` | `knowledgesource` | KB admin agent | KB tests | 已实现并有测试 | 前端未接 source POST |
| 教材 ingestion worker | admin/后台 | ingestion jobs | `workers/knowledge_base_worker.py` | textbook/section/job | 无独立 LangGraph worker | worker tests | 已实现并有测试 | 本地 9 jobs 中 4 failed；原因需逐条审计 |
| 知识缺口闭环 | student/admin | gap follow/notices/admin gap API | KB API/service + onboarding UI | gap/follow/notice | intake agent | lifecycle/API tests | 已实现并接入主流程 | 前端未调用 notice read |
| 测验与薄弱点 | student | Forest 路由 | `backend/app/services/forest_service.py`; `backend/app/orchestration/agents/quiz.py` | quiz/attempt/progress/weakness | quiz agent（独立契约） | forest/quiz contract tests | 已实现并有测试 | quiz agent 不在 7-worker 主图 |
| 资源质量评分 | student/admin 汇总 | Canopy/admin data | `backend/app/services/resource_quality_service.py` | `courseresourcequality` | 无 | resource quality tests | 已实现并有测试 | 本地表为 0，无真实值 |
| 数据聚合管理 | admin | `/api/admin/data*` | `backend/app/services/admin_data_service.py` | 用户与学习表 | 无 | cultivation API tests | 已实现并有测试 | overview 不是全量事件仓库 |

## 4. 前端页面和路由表

唯一生产路由定义为 `frontend/src/App.tsx:97-136`。

| 路由 | 页面组件 | 用户角色 | 功能/布局 | 调用接口 | 当前状态 | 截图需求 | 证据路径 |
|---|---|---|---|---|---|---|---|
| `/login` | `AuthPage` | 公共 | 登录、注册、Mock OAuth；无布局 | auth APIs | 已实现并接入主流程 | 375/768/1280、登录/注册/暗色/reduced-motion | `frontend/src/App.tsx:98`; `frontend/src/components/auth/AuthPage.tsx` |
| `/onboarding` | `IcebreakerFlow` | 公共 | 破冰，完成后去 `/canvas`；无布局 | chat SSE | 已实现并接入主流程 | 对话、agent timeline、完成跳转 | `frontend/src/App.tsx:99`; `frontend/src/components/learning/IcebreakerFlow.tsx:12-22` |
| `/admin/programs` | `AdminProgramsPage` | admin | `AdminLayout` | admin data + teacher program | Mock 数据 | 上传→固定课程→发布全过程 | `frontend/src/App.tsx:101-105`; `frontend/src/pages/admin/AdminProgramsPage.tsx:24-169,358-455` |
| `/admin/accounts` | `AdminAccountsPage` | admin | `AdminLayout` | admin accounts APIs | 已实现并有测试 | 列表、抽屉、批量、import/export | `frontend/src/App.tsx:101-105`; `frontend/src/pages/admin/AdminAccountsPage.tsx` |
| `/admin/data` | `AdminDataPage` | admin | `AdminLayout` | admin data APIs | 已实现但未实际运行验证 | overview/cohort/user detail | `frontend/src/App.tsx:101-106`; `frontend/src/pages/admin/AdminDataPage.tsx` |
| `/admin/knowledge-base` | `AdminKnowledgeBasePage` | admin | `AdminLayout` | knowledge-base APIs/SSE | 已实现并有测试 | agent stream、教材、outline、发布 | `frontend/src/App.tsx:101-110`; `frontend/src/pages/admin/AdminKnowledgeBasePage.tsx` |
| `/teacher` | `Navigate` | admin | 重定向 `/admin/programs` | 无 | 已废弃 | 截图最终 URL，说明兼容重定向 | `frontend/src/App.tsx:112-116` |
| `/sprout` | `SproutPage` | student | `MainLayout`，画像首页 | `GET /api/profile/dashboard` | 已实现并有测试 | 正常/加载/错误/首次 overlay | `frontend/src/App.tsx:118-120`; `frontend/src/components/home/SproutHero.tsx:55-83` |
| `/branch` | `BranchPage` | student | `MainLayout`，四年路径 | branch/profile/matched-program | 已实现并接入主流程 | 四年级、locked/current、教师课程 | `frontend/src/App.tsx:121`; `frontend/src/pages/branch/BranchPage.tsx:1138-1207` |
| `/leaf` | `BranchPage` | student | `MainLayout`，实际复用 Branch | 同 Branch | 页面占位 | 截图证明路由错位 | `frontend/src/App.tsx:122` |
| `/leaf/:courseNodeId` | `LeafPage` | student | `MainLayout`，章节资源 | leaf API + chat SSE | 已实现并接入主流程 | 正文/生成中/locked/资源失败 | `frontend/src/App.tsx:123`; `frontend/src/pages/leaf/LeafPage.tsx:142-274` |
| `/forest` | `BlankPage` | student | `MainLayout`，不可见标题 | 无 | 页面占位 | 截图空白态 | `frontend/src/App.tsx:124`; `frontend/src/components/home/BlankPage.tsx:8-27` |
| `/forest/:courseNodeId` | `ForestQuizPage` | student | `MainLayout`，要求 query `chapter_id` | forest APIs/SSE | 已实现并有测试 | 未生成/答题/结果/错误 | `frontend/src/App.tsx:125-128`; `frontend/src/pages/forest/ForestQuizPage.tsx:521-790` |
| `/canopy` | `CanopyPage` | student | `MainLayout`，知识雨林/统计 | `GET /api/branch/canopy` | 已实现并有测试 | 正常/空/错误/窄屏 | `frontend/src/App.tsx:129`; `frontend/src/pages/canopy/CanopyPage.tsx:150-528` |
| `/canvas` | `ScratchpadCanvas` | student | `MainLayout`，本地画布 | forest AI SSE | 固定数据 | 初始固定卡片、框选追问 | `frontend/src/App.tsx:130`; `frontend/src/pages/canvas/ScratchpadCanvas.tsx:33-96,309-348` |
| `*` | `Navigate` | 公共 | 重定向 `/login` | 无 | 已实现并接入主流程 | 无 | `frontend/src/App.tsx:135` |

权限证据：`ProtectedRoute` 在无用户时去 `/login`；`RoleRoute` 的 `allowedRoles` 仅 `student`/`admin`。见 `frontend/src/App.tsx:33-63`。`MainLayout` 与 `AdminLayout` 分别见 `frontend/src/components/layout/MainLayout.tsx`、`frontend/src/components/layout/AdminLayout.tsx`。

当前未从 `frontend/src/main.tsx` 生产静态导入链到达的业务文件：`frontend/src/api/learningPath.ts`、`api/profileMock.ts`、`components/auth/AuthTabs.tsx`、`components/learning/EditorialMarkdown.tsx`、`components/learning/NodeLearningView.tsx`、`components/onboarding/AgentCollaborationPanel.tsx`、`components/onboarding/agentCollaboration.ts`、`pages/branch/views/FreshmanView.tsx`、`frontend/src/pages/branch/views/JuniorView.tsx`、`frontend/src/pages/branch/views/SophomoreView.tsx`、`frontend/src/pages/branch/views/SeniorView.tsx`。这些只能标记为“当前未被调用”，不能据文件名描述生产功能。

## 5. 后端接口表

当前应用由 `backend/app/main.py:63-79` 装配 13 个 router factory。内存生成 OpenAPI 与 `frontend/openapi.json` 完全相等：55 paths、69 schemas；临时重新生成并 Biome 格式化的 `frontend/src/types/api.ts` 与仓库文件逐字节一致。生成时因本地 Alembic 无 current revision，使用了仅限进程内的 `assert_schema_at_head` 空操作，没有修改源码或数据库。

| 模块 | HTTP 方法 | 接口路径 | 权限 | 请求结构 | 响应结构 | 服务/数据表 | 测试 | 状态 |
|---|---|---|---|---|---|---|---|---|
| health | GET | `/api/health/live` | 公开 | 无 | `LivenessResponse` | 无 DB | `backend/tests/test_health_api.py` | 已实现并有测试 |
| health | GET | `/api/health/ready` | 公开 | 无 | `HealthResponse` 或 503 | `SELECT 1`; schema check | `backend/tests/test_health_api.py` | 已实现并有测试 |
| health | GET | `/api/health` | 公开 | 无 | `HealthResponse` 或 503 | 同 ready | `backend/tests/test_health_api.py` | 已实现并有测试 |
| auth | POST | `/api/auth/register` | 公开 | `RegisterRequest` | `AuthResponse` 201 | `register_user`; `user` | `backend/tests/test_auth_api.py` | 已实现并有测试 |
| auth | POST | `/api/auth/login` | 公开 | `LoginRequest` | `AuthResponse` | `login_user`; `user` | `backend/tests/test_auth_api.py` | 已实现并有测试 |
| auth | POST | `/api/auth/oauth/mock` | 公开 | `OAuthRequest` | `AuthResponse` | `login_with_oauth`; `user` | `backend/tests/test_auth_api.py` | Mock 数据 |
| auth | GET | `/api/auth/me` | active Bearer | 无 | `UserRead` | `user` | `backend/tests/test_auth_api.py` | 已实现并有测试 |
| admin | GET | `/api/admin/accounts` | admin | 无 | `list[UserRead]` | `list_accounts`; `user` | `backend/tests/test_admin_account_api.py` | 已实现并有测试 |
| admin | POST | `/api/admin/accounts` | admin | `AdminAccountCreateRequest` | `UserRead` 201 | `create_account`; `user` | 同上 | 已实现并有测试 |
| admin | POST | `/api/admin/accounts/batch` | admin | `AdminAccountBatchRequest` | `list[UserRead]` | `batch_accounts`; 用户数据组 | 同上 | 已实现并有测试 |
| admin | POST | `/api/admin/accounts/import` | admin | `AdminAccountImportRequest` | `AdminAccountImportResponse` | `import_accounts`; `user` | 同上 | 已实现并有测试 |
| admin | GET | `/api/admin/accounts/export` | admin | 无 | CSV `Response` | `export_accounts`; `user` | 同上 | 已实现并有测试 |
| admin | PUT | `/api/admin/accounts/{uid}` | admin | `AdminAccountUpdateRequest` | `UserRead` | `update_account`; `user` | 同上 | 已实现并有测试 |
| admin | DELETE | `/api/admin/accounts/{uid}` | admin | 无 | 204 | `delete_account`; 用户数据组 | 同上 | 已实现并有测试 |
| admin_data | GET | `/api/admin/data/overview` | admin | 无 | `DataOverviewResponse` | `get_data_overview`; 多表 | `backend/tests/test_cultivation_program_api.py` | 已实现并有测试 |
| admin_data | GET | `/api/admin/data/cohorts` | admin | 无 | `list[DataCohortRead]` | `user`,`cultivationprogram` | 同上 | 已实现并有测试 |
| admin_data | GET | `/api/admin/data/programs` | admin | 无 | `list[CultivationProgramRead]` | `cultivationprogram`,`user` | 同上 | 已实现并有测试 |
| admin_data | GET | `/api/admin/data/users/{uid}/learning-data` | admin | 无 | `UserLearningDataRead` | 用户学习数据组 | 同上 | 已实现并有测试 |
| admin_data | DELETE | `/api/admin/data/users/{uid}/learning-data` | admin | 无 | 204 | `delete_user_learning_data` | 同上 | 已实现并有测试 |
| admin_data | DELETE | `/api/admin/data/cohorts/{school}/{major}/{class_name}/program` | admin | 无 | 204 | `cultivationprogram` | 同上 | 已实现并有测试 |
| teacher | GET | `/api/teacher/program` | active Bearer；服务要求 admin | 无 | `CultivationProgramRead \| None` | `get_program_for_teacher`; `cultivationprogram` | cultivation tests | 已实现并有测试 |
| teacher | PUT | `/api/teacher/program` | 同上 | `CultivationProgramSaveRequest` | `CultivationProgramRead` | `save_program_for_teacher` | 同上 | 已实现并有测试 |
| teacher | POST | `/api/teacher/program/publish` | 同上 | `CultivationProgramSaveRequest` | `CultivationProgramRead` | `publish_program_for_teacher` | 同上 | 已实现并有测试 |
| student | GET | `/api/student/matched-program` | active Bearer | 无 | `CultivationProgramRead \| None` | cohort match; `user`,`cultivationprogram` | cultivation tests | 已实现并有测试 |
| orchestration | POST | `/api/chat/start` | active Bearer | `ChatStartRequest` | `ChatResponse` | `load_or_create_session`; `conversationsession` | orchestration API tests | 已实现并有测试 |
| orchestration | POST | `/api/chat/message` | active Bearer；session owner | `ChatMessageRequest` | SSE `StreamingResponse` | handlers + graph；会话/画像/路径/大纲 | orchestration/SSE/multimodal tests | 已实现并有测试 |
| orchestration | GET | `/api/chat/sessions/{session_id}` | active Bearer；session owner | 无 | `SessionStateResponse` | conversation/profile/path/outline | orchestration API tests | 已实现并有测试 |
| profile | GET | `/api/profile/dashboard` | active Bearer | 无 | 未声明 response model，返回 `dict` | profile/path/outline | `backend/tests/test_profile_api.py` | 已实现并有测试 |
| learning_path | GET | `/api/learning-path/me` | active Bearer | 无 | `YearLearningPathsReadResponse` | `useryearlearningpath` | `backend/tests/test_learning_path_api.py` | 已实现并有测试 |
| branch | GET | `/api/branch/canopy` | active Bearer | 无 | `CanopyOverviewResponse` | path/quiz/quality | `backend/tests/test_canopy_api.py` | 已实现并有测试 |
| branch | GET | `/api/branch/overview` | active Bearer | 无 | `BranchOverviewReadResponse` | path + outline | `backend/tests/test_branch_api.py` | 已实现并有测试 |
| leaf | GET | `/api/leaf/courses/{course_node_id}` | active Bearer | 无 | `LeafCourseReadResponse` | path/outline/progress | `backend/tests/test_leaf_api.py` | 已实现并有测试 |
| forest | GET | `/api/forest/courses/{course_node_id}/chapters/{chapter_id}/quiz` | active Bearer | 无 | `ForestQuizSessionReadResponse` | quiz/attempt/progress | `backend/tests/test_forest_api.py` | 已实现并有测试 |
| forest | POST | `/api/forest/courses/{course_node_id}/chapters/{chapter_id}/quiz/generate` | active Bearer | `ForestQuizGenerateRequest` | `ForestQuizRead` | quiz agent/service | 同上 | 已实现并有测试 |
| forest | POST | `/api/forest/quizzes/{quiz_id}/attempts` | owner | `ForestQuizAttemptCreateRequest` | `ForestAttemptRead` | attempt/progress/weakness | 同上 | 已实现并有测试 |
| forest | POST | `/api/forest/quizzes/{quiz_id}/attempts/stream` | owner | `ForestQuizAttemptCreateRequest` | SSE | 同上 + next unlock | 同上 | 已实现并有测试 |
| forest | POST | `/api/forest/ai/stream` | active Bearer | `ForestAiStreamRequest` | SSE | `stream_forest_ai_response` | 同上 | 已实现并有测试 |
| KB admin | GET | `/api/admin/knowledge-base/sources` | admin | 无 | `list[KnowledgeSourceRead]` | `knowledgesource` | `backend/tests/test_knowledge_base_api.py` | 已实现并有测试 |
| KB admin | POST | `/api/admin/knowledge-base/sources` | admin | `KnowledgeSourceCreateRequest` | `KnowledgeSourceRead` 201 | `knowledgesource` | 同上 | 已实现并有测试 |
| KB admin | GET | `/api/admin/knowledge-base/textbooks` | admin | 无 | `list[TextbookRead]` | `textbook` | 同上 | 已实现并有测试 |
| KB admin | POST | `/api/admin/knowledge-base/textbooks` | admin | `StructuredTextbookCreateRequest` | `TextbookRead` 201 | textbook/sections | 同上 | 已实现并有测试 |
| KB admin | GET | `/api/admin/knowledge-base/textbooks/{textbook_id}/sections` | admin | 无 | `list[TextbookSectionContentRead]` | sections | 同上 | 已实现并有测试 |
| KB admin | POST | `/api/admin/knowledge-base/textbooks/{textbook_id}/publish` | admin | 无 | `TextbookRead` | publish/gap notices | API/lifecycle tests | 已实现并有测试 |
| KB admin | PUT | `/api/admin/knowledge-base/textbooks/{textbook_id}/outline` | admin | `dict[str, object]` | `TextbookRead` | route direct update | API tests | 已实现并有测试 |
| KB admin | POST | `/api/admin/knowledge-base/textbooks/{textbook_id}/unpublish` | admin | 无 | `TextbookRead` | textbook | lifecycle tests | 已实现并有测试 |
| KB admin | DELETE | `/api/admin/knowledge-base/textbooks/{textbook_id}` | admin | 无 | 204 | delete/archive | API/lifecycle tests | 已实现并有测试 |
| KB admin | POST | `/api/admin/knowledge-base/textbooks/{textbook_id}/agent-organize` | admin | 无 | `KnowledgeBaseIngestionJobRead` 201 | ingestion job | API tests | 已实现并有测试 |
| KB admin | POST | `/api/admin/knowledge-base/textbooks/{textbook_id}/agent-organize/run` | admin | 无 | `KnowledgeBaseIngestionJobRead` 202 | queue ingestion | API tests | 已实现并有测试 |
| KB admin | POST | `/api/admin/knowledge-base/ingestion-jobs/{job_id}/run` | admin | 无 | `KnowledgeBaseIngestionJobRead` 202 | queued job | API tests | 已实现并有测试 |
| KB admin | GET | `/api/admin/knowledge-base/ingestion-jobs/{job_id}` | admin | 无 | `KnowledgeBaseIngestionJobRead` | ingestion job | API tests | 已实现并有测试 |
| KB admin | POST | `/api/admin/knowledge-base/agent` | admin | `KnowledgeBaseAgentRequest` | `KnowledgeBaseAgentResponse` | KB agent/service | API tests | 已实现并有测试 |
| KB admin | POST | `/api/admin/knowledge-base/agent/stream` | admin | `KnowledgeBaseAgentRequest` | SSE | KB agent/service | 未发现精确 stream HTTP 测试 | 已实现但未实际运行验证 |
| KB admin | POST | `/api/admin/knowledge-base/source-results/confirm` | admin | `KnowledgeBaseSourceConfirmRequest` | `KnowledgeBaseSourceConfirmResponse` 201 | textbook/job | API tests | 已实现并有测试 |
| KB admin | POST | `/api/admin/knowledge-base/uploads` | admin | multipart | `KnowledgeBaseSourceConfirmResponse` 201 | upload/textbook/job | API tests | 已实现并有测试 |
| KB admin | GET | `/api/admin/knowledge-base/gaps` | admin | 无 | `list[KnowledgeGapAdminRead]` | gap/source | API tests | 已实现并有测试 |
| KB admin | POST | `/api/admin/knowledge-base/gaps/{gap_id}/find-materials` | admin | 无 | `KnowledgeGapFindMaterialsResponse` | gap status/source list | API tests | 仅存在后端接口 |
| KB admin | POST | `/api/admin/knowledge-base/gaps/{gap_id}/upload` | admin | `StructuredTextbookCreateRequest` | `KnowledgeGapUploadResponse` 201 | gap/textbook | API tests | 仅存在后端接口 |
| KB admin | GET | `/api/admin/knowledge-base/textbooks/{textbook_id}/extension-resources` | admin | query `section_id: list[str]` | `list[TextbookExtensionResourceRead]` | extension resources | API tests | 已实现并有测试 |
| KB admin | POST | `/api/admin/knowledge-base/textbooks/{textbook_id}/extension-resources` | admin | `TextbookExtensionResourceCreateRequest` | `TextbookExtensionResourceRead` 201 | extension resources | API tests | 仅存在后端接口 |
| KB student | POST | `/api/knowledge-base/gaps/{gap_id}/follow` | student | 无 | `KnowledgeGapFollowRead` | gap/follow | API tests | 已实现并接入主流程 |
| KB student | GET | `/api/knowledge-base/notices` | student | 无 | `list[KnowledgeGapNoticeRead]` | notices | API tests | 已实现并接入主流程 |
| KB student | POST | `/api/knowledge-base/notices/{notice_id}/read` | student | 无 | `KnowledgeGapNoticeRead` | notice update | API tests | 仅存在后端接口 |

接口风险：公开注册可创建 `admin`；禁用账号仍可登录取得 JWT，后续受保护接口才拒绝；`/api/student/matched-program` 不校验 student role；KB/Forest SSE 将 `str(exc)` 发给客户端。证据：`backend/tests/test_auth_api.py::test_register_can_create_admin_role`、`backend/app/services/auth_service.py:75-87`、`backend/app/core/security.py:80-84`、`backend/app/api/knowledge_base.py:417-423`、`backend/app/api/forest.py:76-77,261-262`。

## 6. 数据库表和关系表

SQLModel metadata 共 19 张表，模型证据集中于 `backend/app/models.py:73-471`。

| 表名 | 模型名 | 业务用途 | 主键 | 外键 | JSON/JSONB/ARRAY | 索引和约束 | 状态 |
|---|---|---|---|---|---|---|---|
| `user` | `User` | 账号、角色、cohort | `uid` | 无 | 无 | `identifier` unique；多字段索引 | 已实现并有测试 |
| `cultivationprogram` | `CultivationProgram` | cohort 培养方案 | `program_id` | `teacher_uid -> user.uid` | `courses` JSONB | cohort unique；teacher/cohort index | 已实现并有测试 |
| `userprofile` | `UserProfile` | 学习画像 | `user_uid` | `user_uid -> user.uid` | `profile_data` JSONB | PK 即用户 | 已实现并有测试 |
| `useryearlearningpath` | `UserYearLearningPath` | 学年路径 | `(user_uid,grade_year)` | `user_uid -> user.uid` | `path_data` JSONB | user/update index | 已实现并有测试 |
| `usercourseknowledgeoutline` | `UserCourseKnowledgeOutline` | 课程大纲与资源 | `(user_uid,course_id)` | `user_uid -> user.uid` | `outline_data` JSONB | user/grade index | 已实现并有测试 |
| `chapterquiz` | `ChapterQuiz` | 章节题目 | `quiz_id` | `user_uid -> user.uid` | `questions` JSONB | scope unique；user/course index | 已实现并有测试 |
| `chapterquizattempt` | `ChapterQuizAttempt` | 作答与评分 | `attempt_id` | quiz/user | `answers`,`grading_result` JSONB | user/quiz index | 已实现并有测试 |
| `chapterprogress` | `ChapterProgress` | 章节解锁/通过 | `(user_uid,course_node_id,chapter_id)` | `user_uid -> user.uid` | 无 | user/course index；`latest_attempt_id` 无 FK | 已实现并有测试 |
| `chapterweakness` | `ChapterWeakness` | 薄弱知识点 | `weakness_id` | `user_uid -> user.uid` | 无 | user/course、consumed index | 已实现并有测试 |
| `courseresourcequality` | `CourseResourceQuality` | 资源质量分 | `(user_uid,course_node_id)` | `user_uid -> user.uid` | `suggestions` JSONB | user/course index；分数 0-100 | 已实现并有测试 |
| `conversationsession` | `ConversationSession` | 会话消息 | `session_id` | `user_uid -> user.uid` | `messages` JSONB | user/time index | 已实现并有测试 |
| `knowledgesource` | `KnowledgeSource` | 来源准入状态 | `source_id` | 无 | 无 | 5 个状态 check；多状态索引 | 已实现并有测试 |
| `textbook` | `Textbook` | 教材元数据/outline | `textbook_id` | 无 | `tags`,`outline` JSONB；`embedding` FLOAT ARRAY | ingestion/outline/availability checks | 已实现并有测试 |
| `textbooksectioncontent` | `TextbookSectionContent` | 教材小节正文 | `section_content_id` | 无 | 无 | `(textbook_id,section_id)` unique | 已实现并有测试 |
| `textbookextensionresource` | `TextbookExtensionResource` | 小节扩展资源 | `resource_id` | 无 | 无 | render_mode check；多索引 | 已实现并有测试 |
| `knowledgegap` | `KnowledgeGap` | 知识缺口 | `gap_id` | 无 | `student_goal_summaries` JSONB | `normalized_topic` unique；status check | 已实现并有测试 |
| `knowledgegapfollow` | `KnowledgeGapFollow` | 学生关注缺口 | `follow_id` | 无 | 无 | `(gap_id,user_uid)` unique | 已实现并有测试 |
| `knowledgegapnotice` | `KnowledgeGapNotice` | 缺口解决通知 | `notice_id` | 无 | `action_payload` JSONB | `(gap,user,type)` unique；payload check | 已实现并有测试 |
| `knowledgebaseingestionjob` | `KnowledgeBaseIngestionJob` | 解析任务/租约 | `job_id` | 无 | 无 | status check；lease/worker/request indexes | 已实现并有测试 |

### ER 图关系描述

- 数据库 FK：`cultivationprogram.teacher_uid`、`userprofile.user_uid`、`useryearlearningpath.user_uid`、`usercourseknowledgeoutline.user_uid`、`chapterquiz.user_uid`、`chapterquizattempt.quiz_id/user_uid`、`chapterprogress.user_uid`、`chapterweakness.user_uid`、`courseresourcequality.user_uid`、`conversationsession.user_uid`。
- 业务关联但无数据库 FK：`textbook.source_id -> knowledgesource.source_id`；`textbooksectioncontent.textbook_id -> textbook.textbook_id`；`textbookextensionresource.textbook_id -> textbook.textbook_id`；`knowledgegap.resolved_textbook_id -> textbook.textbook_id`；follow/notice 的 gap/user；ingestion job 的 textbook。
- `chapterprogress.latest_attempt_id` 语义关联 `chapterquizattempt.attempt_id`，模型未声明 FK。
- 本地只读检查中上述 9 类无 FK 关系的孤儿数均为 0；这只证明当前本地数据，不证明服务外写入永远满足完整性。
- 首次快照表计数：`user=3`,`cultivationprogram=2`,`userprofile=1`,`conversationsession=1`,`knowledgesource=1`,`textbook=2`,`textbooksectioncontent=339`,`knowledgegap=1`,`knowledgebaseingestionjob=9`；其余学习/测验/质量表为 0。最终复核时 `user=4`，其余重点计数未变，证明开发库在盘点期间有并发写入。2 本教材均为 `ready_for_outline_review/approved/published`；9 个 job 为 5 completed、4 failed；1 个来源满足准入。数据性质未验证，不能用于正式规模数字。

### 迁移与生命周期

- Alembic revisions：`0001_production_baseline`、`0002_ingestion_job_leases`、`0003_repair_ingestion_job_leases`。
- 生产启动只执行 `assert_schema_at_head`；开发启动执行 `init_db`，包含 `run_schema_upgrades`、`create_all`、legacy migration 和可选 seed。证据：`backend/app/main.py:45-48`、`backend/app/database.py:58-84`。
- 本地 head 为 `0003_repair_ingestion_job_leases`，`alembic current` 无 revision；生产启动内存验证实际抛出“数据库迁移版本不是 Alembic head”。
- `backend/app/schema_upgrades.py` 包含没有逐项映射到 Alembic revision 的 legacy 修复；生产 head 检查与开发升级路径存在差异。

## 7. 智能体与阶段表

主图节点/边证据：`backend/app/orchestration/graph.py:42-60,66-120,159-198`。执行顺序契约：`backend/app/orchestration/contracts.py:17-45`。

| 顺序 | 智能体 | 阶段 | 输入 | 输出 | 前置条件 | 持久化 | 质量门禁 | 失败处理 | 测试 | 接入状态 |
|---:|---|---|---|---|---|---|---|---|---|---|
| 1 | `profile_agent` | `profile` | state、`conversation_summary` | `profile`,`response` | 无完整画像 | `userprofile`；删除旧 outlines | profile contract/repair | LLM 耗尽可降级 collecting；持久化异常只记录 | profile contracts | 已实现并接入主流程 |
| 2 | `learning_path_intake_agent` | `intake` | query/profile/intake/published context | `learning_path_intake`,`response` 或 gap | 完整 profile | session latest intake | risk pending/二次确认 | 无教材返回 gap；持久化异常只 warning | intake contracts | 已实现并接入主流程 |
| 3 | `learning_path_agent` | `path` | profile + confirmed intake | `year_learning_path`,`grade_year` | profile、confirmed、grade/topic | `useryearlearningpath`；删同年 outlines | structured output + contract | LLM/contract hard error；持久化异常只日志 | path contracts | 已实现并接入主流程 |
| 4 | `course_knowledge_agent` | `outline` | course/profile/path/published sections | `course_knowledge(s)` | source textbook + section IDs | `usercourseknowledgeoutline` | 来源连续/越权/长度/结构 | 命名/来源/保存失败 hard error | course knowledge contracts | 已实现并接入主流程 |
| 5 | `section_markdown_agent` | `markdown` | outline/section/evidence pack | markdowns + resource plan | published evidence，正文总量限制 | outline JSONB | 结构、来源、质量重试 | 失败写 `section_resource_errors` 并 hard error | resource contracts | 已实现并接入主流程 |
| 6 | `section_video_search_agent` | `video` | section evidence/query | links + plan IDs | markdown 之后 | outline JSONB | 元数据/主题质量，2 次 verified attempt | 无结果写 unavailable，继续管线；保存失败 hard error | resource contracts | 已实现并接入主流程 |
| 7 | `section_html_animation_agent` | `animation` | plan/section context | animations + composed markdown + result | video 阶段完成 | outline JSONB | 生成/修复/运行质量 | 缺动画/质量/保存失败 hard error | resource contracts | 已实现并接入主流程 |
| 8 | `compose_resource` | `compose` | markdown/video/animation blocks | composed content/checkpoint/event | animation 后 | 同 animation worker 写入 | 程序性占位替换 | 缺视频/动画写 unavailable | resource/event tests | 普通程序阶段，不是 LangGraph worker |

### Supervisor、规则、SSE、恢复与预算

- 图有 8 个节点：`supervisor` + 7 worker；`__start__ -> supervisor`，Supervisor 条件转 7 worker 或 END。worker 可回 supervisor，或自动走 video→animation→END。
- `force_call` 时 Supervisor 绕过 LLM；否则绑定 7 tools 调用 LLM，并再次过滤 blocked calls。证据：`backend/app/orchestration/agents/supervisor.py:683-743`。
- 资源主顺序是 outline→markdown→video→animation→compose；三个资源 worker 在章节 stream 中串行 await，各 worker 内部按小节并行。证据：`backend/app/orchestration/agents/course_resources/main.py:321,402,482,542-583`。
- `compose_resource` 的 `_compose_section_content` 是同步普通函数，无独立 prompt、LLM、tool 或 graph node。证据：`backend/app/orchestration/agents/course_resources/common.py:1135-1204`。
- 标准 SSE：`session_started`,`agent_calling`,`agent_result`,`supervisor_thinking`,`data_update`,`supervisor_plan`,`text_chunk`,`agent_progress`,`message_completed`,`session_completed`,`error`；资源统一事件字段为 `event,agent,agent_order,phase,status,stepId,depends_on,input_refs,output_refs,quality_result`。证据：`backend/app/orchestration/graph.py:427-618`、`backend/app/orchestration/events.py:6-36`。
- trace 字段为 `agent,phase,section_id,input_refs,output_refs,quality_result`，可加 `duration_ms`,`failure_reason`。证据：`backend/app/orchestration/observability.py:6-29`。
- 没有 LangGraph checkpoint；state 每轮从 DB 重建。资源 checkpoint 位于 `course_knowledge.section_resource_checkpoints[section_id][phase]`。当前 stream 只在成功后写 completed，错误不写 failed checkpoint；video unavailable 也写 completed，恢复语义有限。
- prompt limits：intake 8000、path 12000、outline 16000、markdown 28000、video 9000、animation 12000 字符；profile/compose 没有专用 limit。证据：`backend/app/orchestration/prompt_budget.py:7-58`。
- 本次定向命令 4 个 nodeid 全通过（`4 passed in 0.95s`）；全量后端结果见第 9 节。

## 8. 知识库能力表

| 能力 | 实现位置 | 数据表 | 接入状态 | 测试 | 限制 |
|---|---|---|---|---|---|
| 来源准入 | `backend/app/services/knowledge_base_service.py:46-52,306-318` | `knowledgesource` | 管理端后端/API | KB API/service | 必须 enabled+verified+supported+approved+reviewed；前端未接 source POST |
| 教材与正文 | `backend/app/models.py:297-357`; service upsert | textbook/section | 管理端与学生 evidence | KB models/service | 正文是独立表；section ID 必须来自 outline |
| 扩展资源 | `backend/app/models.py:360-380`; service `1298-1324` | extension | 管理端 API，学生未接 | API/service | 每小节最多 3 个 published；Leaf 不消费 |
| multipart 上传 | `backend/app/api/knowledge_base.py:76-107,457-490` | textbook/job | 仅后端接口 | API | PDF/DOCX，100 MiB；前端未封装；固定绑定首个准入来源 |
| 文档解析 | `backend/app/services/document_parser_service.py:105-506` | section/job | ingestion 主线 | parser/ingestion tests | MarkItDown；HTML 最多80页/深度<2；`language` 未被解析逻辑使用 |
| 翻译 | `backend/app/services/knowledge_base_service.py:600-651` | section | 当前主线未接 | 翻译函数单测 | ingestion 把原文同时写入 original/zh；英文可发布 |
| worker 租约 | `backend/app/workers/knowledge_base_worker.py:20-206` | ingestion job | 后台 worker | worker tests | `FOR UPDATE SKIP LOCKED`；10分钟租约；默认3次 |
| 审核/发布 | `backend/app/services/knowledge_base_service.py:1013-1045` | source/textbook/section/gap/notice | 主流程 | lifecycle tests | outline PUT 直接设 approved；unpublish 后旧内容仍可读 |
| 关键词/向量/混合检索 | `backend/app/services/knowledge_base_service.py:1549-1637` | textbook | intake 检索入口 | 仅异常 fallback 测试 | `FLOAT[]` 无写入路径；`<=>` 分支未跑通验证；异常退回字符串匹配 |
| 外部教材搜索 | service `73-227,1767-2090` | source/textbook/job | 管理员 Agent | API/service | 最多5结果；需 URL 可达/PDF或HTML；外部现时可用性未验证 |
| intake 来源绑定 | `backend/app/orchestration/agents/learning_path_intake.py:126-206,323-777` | textbook/section/gap | 学生主流程 | published/source tests | topic 提取范围有限；0 分也取首个扫描项，绑定不等于语义证明 |
| 大纲来源绑定 | `backend/app/orchestration/agents/course_knowledge.py:593-1051,1543-1779` | path/outline/textbook/section | 学生主流程 | contracts/published tests | 最多7节，深层单节≤8000，必须连续/不越权 |
| Markdown evidence | `backend/app/orchestration/agents/course_resources/common.py:638-872`; `backend/app/orchestration/agents/course_resources/markdown.py:47-110` | outline JSONB | 学生资源主流程 | resource tests | evidence 总量≤8000；缺证据创建 gap；footer 是绑定级引用，不是 quote span |
| 无教材处理 | service `1048-1195`; intake `169-175` | gap | 学生主流程 | KB/source tests | 返回 gap，不生成无来源草案 |
| 无视频处理 | `backend/app/orchestration/agents/course_resources/video.py:1363-1446` | outline JSONB | 学生资源主流程 | resource tests | 最多前3 query、2次；并发改动增加单节45秒 timeout；无结果写 unavailable，不伪造成功 |
| 缺口关注/通知 | service `1198-1277`; onboarding UI | gap/follow/notice | 部分主流程 | lifecycle/API/UI | 前端不调用 notice read；只显示首个 unread banner |
| 管理员知识库 UI | `frontend/src/pages/admin/AdminKnowledgeBasePage.tsx:439-603` | 8 张 KB 表 | 管理端核心已接 | admin KB tests | upload、gap find/upload、extension create 等未接 UI |

知识库不能用于正式文档的表述：`pgvector 已部署`、`HNSW 已建立`、`教材 embedding 已回填`、`中文正文是唯一事实源`、`扩展资源已进入学生 Leaf`、`正文片段级引用已实现`。这些均与当前源码不一致或尚未验证。

## 9. 测试执行结果

### 本次本地命令

| 命令 | 是否执行 | 退出状态 | 通过 | 失败 | 跳过 | 时间 | 环境问题 | 结论 |
|---|---|---:|---:|---:|---:|---|---|---|
| `cd backend && uv run pytest -q` | 是 | 0 | 798 | 0 | 0 | pytest 238.16s；process real 242.03s | 1 个 `StarletteDeprecationWarning`；本地 PostgreSQL 可用 | 可以直接使用：本次后端全量通过 |
| `cd frontend && npm test` | 是 | 0 | 244（43 files） | 0 | 0 | Vitest 17.92s；process real 18.39s | React Router v7 future flags；Node localstorage warning | 可以直接使用：本次前端单元/组件通过 |
| `cd frontend && npm run build` | 是 | 0 | TypeScript + Vite build | 0 | 0 | Vite 5.81s；process real 9.39s | 4806 modules；最大 chunk 1,360.01 kB，超过 500 kB warning | 可以使用但需要注明限制 |
| `cd frontend && npm run e2e` | 是 | 1 | 5 | 3 | 0 | Playwright 59.7s；process real 60.26s | 复用 2026-07-13 已运行的 Vite/Uvicorn；非隔离服务 | 不能标记为通过 |
| 4 个编排精确 nodeid | 是 | 0 | 4 | 0 | 0 | 0.95s | 禁用 bytecode/cache provider | 可以直接使用：契约、事件、SSE error、预算通过 |
| 并发改动后的 2 个视频搜索精确 nodeid | 是 | 0 | 2 | 0 | 0 | pytest 1.65s；process real 2.33s | 只覆盖持续空结果与单节 timeout | 可以直接使用：受影响的两个行为通过；未替代全量测试 |

Playwright 失败明细：

1. `frontend/e2e/auth.spec.ts:61:1 › dark mode uses dark material tokens`：30s timeout，停在 `page.goto("/")` 等待 `load`；未执行暗色 token 断言。测试后根 URL 返回 200，当前只确认单次导航超时。
2. `frontend/e2e/leaf.spec.ts:223:1 › branch opens current courses and explains locked courses`：5s 内找不到 heading `你的路径`，实际为登录页。fixture 没有拦截当前 `BranchPage` 并行请求的 `/api/student/matched-program`，假 token 请求真实本地后端。证据：`frontend/src/pages/branch/BranchPage.tsx:1157-1161`、`frontend/src/api/teacherProgram.ts:90-94`。
3. `frontend/e2e/leaf.spec.ts:247:1 › leaf renders generated resources and opens AI draft`：页面显示“叶茂数据加载失败 / 叶茂数据格式不正确”。fixture sections 缺当前解析器要求的 `source_textbook_id`,`source_textbook_title`,`source_section_ids`,`source_section_titles`,`source_content_chars`。证据：`frontend/e2e/leaf.spec.ts:118-152`、`frontend/src/api/leaf.ts:39-59`。

本次测试产物处理：测试代理对任务前的 `frontend/dist`、`frontend/test-results` 做备份，执行后删除本轮产物并恢复原目录；恢复后的 SHA-256 与任务前一致。测试代理结束时 `git status --short` 为空。此后并发工作流写入 `backend/app/orchestration/agents/course_resources/__init__.py`、`backend/app/orchestration/agents/course_resources/common.py`、`backend/app/orchestration/agents/course_resources/video.py` 和 `backend/tests/test_course_resource_agent_contract.py`；本任务没有恢复或修改这些文件。

### 测试配置与覆盖边界

- 后端：`backend/pyproject.toml` 配置 `testpaths=["tests"]`,`pythonpath=["."]`；52 个 `backend/tests/test_*.py`，覆盖 API、服务、迁移、agent contracts、SSE、知识库、部署 manifest；LLM 测试使用 fake/recording/mock，不证明真实外部模型。
- 前端：`frontend/vitest.config.ts` 使用 jsdom，include 为 `src/**/*.test.ts`,`src/**/*.test.tsx`；覆盖 App、API、auth/onboarding、学生页面、管理员账号/培养方案/KB；未发现 `AdminDataPage` 单测。
- E2E：`frontend/playwright.config.ts` 只有 Chromium/Desktop Chrome，8 项测试；大量 API 由 `page.route` fixture 提供，不代表真实业务数据；不覆盖管理员、Canopy、Canvas、Forest 真实后端和完整权限矩阵。
- CI：`.github/workflows/production.yml` 不运行 Playwright。最新 GitHub `Production readiness` run `29289628662` 在 Ruff、Biome、ShellCheck 失败，迁移 job 成功；backend/frontend tests 因前置 lint 失败被 skipped。
- 最近 8 次 `Production readiness` 记录均为 failure；较早的 `Dependency Graph` 记录为 success。不同 workflow 不能互相替代，正式测试章节只引用同名 job 的结论。
- GitHub：默认分支 `main`；最新提交 `3fdc6f2f44569a8d5af427f72f4e1476c88beb95`；本地 commit 与远端 ahead/behind 为 `0/0`；open/closed PR 与 Issue 查询结果均为空。最终工作区另有 4 个并发未提交文件差异，不属于远端提交。

尚未设计或没有本次结果：性能、并发、负载、真实 LLM、真实视频搜索、embedding 成功分支、安全渗透、跨浏览器、移动真机、无障碍审计。

## 10. 可采集量化指标表

“当前是否有真实值”仅评价本次可验证数据。凡标记“无”，统一含义为：**当前仓库能够支持采集该指标，但当前没有可验证的真实值。** 本地未确认性质的记录不作为正式值。

| 指标 | 数据来源 | 精确表或日志字段 | 当前是否有真实值 | 采集方式 | 用于文档章节 |
|---|---|---|---|---|---|
| 用户数量 | PostgreSQL | `user.uid` | 否；本地从3变为4，性质未确认 | `COUNT(*)`，排除已确认 seed/test 后复核 | 1、5、6 |
| 学生数量 | PostgreSQL | `user.role='student'` | 否；最终本地2条，性质未确认 | 按 role 聚合 | 1、5 |
| 管理员数量 | PostgreSQL | `user.role='admin'` | 否；最终本地2条且1条命中 admin seed UID | 按 role 聚合并标注 seed | 1、5 |
| 班级数量 | PostgreSQL | `user.school,major,class_name` | 否 | 对非空三元组去重 | 1、3 |
| 培养方案数量 | PostgreSQL | `cultivationprogram.program_id,published_at` | 否；本地2条性质未确认 | 总数/已发布分组 | 1、3 |
| 用户画像数量 | PostgreSQL | `userprofile.user_uid,updated_at` | 否；本地1条性质未确认 | 总数与最近更新时间 | 2、5 |
| 学年路径数量 | PostgreSQL | `useryearlearningpath.user_uid,grade_year` | 无 | 总数与按年级分组 | 2、4、5 |
| 课程大纲数量 | PostgreSQL | `usercourseknowledgeoutline.user_uid,course_id` | 无 | 总数/用户/年级 | 2、3、5 |
| 教材数量 | PostgreSQL | `textbook.textbook_id` | 否；本地2条性质未确认 | 总数与状态分组 | 2、3 |
| 已发布教材数量 | PostgreSQL | `textbook.student_availability_status='published'` | 否；本地2条性质未确认 | 状态聚合 | 2、4 |
| 教材小节数量 | PostgreSQL | `textbooksectioncontent.section_content_id,textbook_id` | 否；本地339条性质未确认 | 总数/教材 | 2、3 |
| 准入知识来源数量 | PostgreSQL | `knowledgesource` 5 个准入状态字段 | 否；本地1条性质未确认 | 精确准入 predicate 聚合 | 2、4 |
| 知识缺口数量 | PostgreSQL | `knowledgegap.gap_id,status,trigger_count` | 否；本地1条性质未确认 | 状态/触发次数聚合 | 2、4、5 |
| 测验数量 | PostgreSQL | `chapterquiz.quiz_id,status` | 无 | 状态/课程/日期聚合 | 2、5 |
| 作答次数 | PostgreSQL | `chapterquizattempt.attempt_id,created_at` | 无 | 总数/用户/测验/时间 | 5 |
| 平均测验分数 | PostgreSQL | `chapterquizattempt.score` | 无 | `AVG(score)`，同时报告样本数 | 4、5 |
| 章节通过数量/通过率 | PostgreSQL | `chapterprogress.state,passed_at` | 无 | `state='passed'` / 全部 progress | 4、5 |
| 薄弱知识点数量 | PostgreSQL | `chapterweakness.weakness_id,severity,consumed` | 无 | 总数/严重度/是否 consumed | 2、5 |
| 资源质量评分 | PostgreSQL | `courseresourcequality.accuracy_score,difficulty_fit_score,completeness_score,overall_score` | 无 | 平均/分布/课程，报告 N | 4、5 |
| 会话数量 | PostgreSQL | `conversationsession.session_id,created_at,updated_at` | 否；本地1条性质未确认 | 总数/活跃日期 | 3、5 |
| 智能体调用次数 | JSON trace/SSE | `agent`,`phase`,`agent_calling`,`agent_result` | 无 | 按 session/agent/phase 去重计数，保留调用起止 | 2、4、5 |
| 智能体阶段耗时 | JSON trace | `agent,phase,duration_ms` | 无 | 保存 JSONL 后按 phase 计算 P50/P95 | 2、4、5 |
| 智能体失败次数 | JSON trace/SSE | `failure_reason`; failed `agent_result`; `error` | 无 | 按 agent/phase/error 分类计数 | 4、5 |
| 恢复次数 | checkpoint + SSE | `section_resource_checkpoints`; generation status | 无 | 定义 retry/restart 事件后聚合 | 4、5 |
| Prompt 裁剪次数 | 运行时 budget | `prompt_budget_applied,original_chars,final_chars` | 无 | 将 `PromptBudgetResult` 写入 trace 后统计 | 2、4、5 |
| Markdown 生成成功率 | outline JSONB + event | `section_markdowns`,`section_resource_errors`, phase=`markdown` | 无 | 成功 section / 请求 section | 4、5 |
| 视频匹配成功率 | outline JSONB | `section_video_links.status`,`videos` | 无 | available / 请求 section | 4、5 |
| 动画生成成功率 | outline JSONB | `section_html_animations`，phase=`animation` | 无 | 有合格动画 / 请求 section | 4、5 |
| 资源合成成功率 | outline JSONB + event | `section_composed_markdowns`, phase=`compose` | 无 | completed compose / 请求 section | 4、5 |
| 来源引用覆盖率 | outline JSONB | `source_references` 与 Markdown `## 来源` | 无 | 同时满足绑定与来源段 / Markdown 数 | 4、5 |
| 学习路径完成率 | PostgreSQL | `chapterprogress.state`；路径总节点需从 `path_data` 按真实结构解析 | 无 | 每用户 passed / 可评估章节 | 4、5 |
| ingestion 成功率 | PostgreSQL | `knowledgebaseingestionjob.status,attempt_count` | 否；本地5 completed/4 failed，性质未确认 | completed / completed+failed，并按 job_type | 2、5 |

当前源码不支持直接形成“独立教师人数”“用户满意度”“事实准确率”“幻觉率”“人工评价”“并发吞吐”“模型调用成本”的真实值。`teacher` 已合并为 `admin`，若文档需要“承担教师业务的管理员人数”，必须另行定义可审计的人员标记；其余指标需要第 13、14 节的外部采集和实验数据。

## 11. Mock、固定数据、占位和未验证功能表

| 功能 | 当前性质 | 判断依据 | 对文档编写的影响 | 后续处理 |
|---|---|---|---|---|
| `/api/auth/oauth/mock` | Mock 数据 | `backend/app/api/auth.py`; `backend/app/services/auth_service.py:100-109`; 生产无环境开关 | 不能写真实 QQ/学习通 OAuth | 正式文档标 Mock；演示账号单独说明 |
| 管理培养方案上传 | Mock 数据 | `frontend/src/pages/admin/AdminProgramsPage.tsx:24-169,404-455` | 不能写“已解析上传文件” | 截图必须标固定课程；功能完成度标 Mock |
| `MOCK_TEACHER_COURSES` | 固定数据 | `frontend/src/pages/admin/AdminProgramsPage.tsx:24-123` | 固定课程可进入真实发布 API，存在数据混淆 | 正式演示前禁用 Mock 数据 |
| Scratchpad 初始 3 items | 固定数据 | `frontend/src/pages/canvas/ScratchpadCanvas.tsx:59-85` | 不能写“从用户资料自动加载” | 标明本地初始展示数据 |
| Scratchpad AI context | 固定数据 | `mockContext`,`canvas-scratchpad`,`global-canvas`，`frontend/src/pages/canvas/ScratchpadCanvas.tsx:315-329` | 不能写真实课程上下文绑定 | 增加真实上下文前保持限制说明 |
| `/forest` | 页面占位 | `frontend/src/App.tsx:124`; `frontend/src/components/home/BlankPage.tsx:8-27` | 导航“成林”根入口无内容 | 截图/完成度必须标占位 |
| `/leaf` | 页面占位 | `frontend/src/App.tsx:122` 实际渲染 `BranchPage` | 路由语义与页面不一致 | 正文只使用 `/leaf/:courseNodeId` |
| `/teacher` | 已废弃 | `Navigate` 到 `/admin/programs` | 不能作为独立教师页面 | 角色统一为 admin |
| `frontend/src/api/profileMock.ts` | 当前未被调用 | 不在 `frontend/src/main.tsx` 静态生产导入链 | 不作为生产功能证据 | 仅在历史/测试说明中出现 |
| Branch 年级 views | 当前未被调用 | 4 个 view 文件不在生产导入链 | 不能按文件名写生产页面 | 如无后续用途，由团队另行清理 |
| 视频封面 data SVG | 固定数据/fallback | `frontend/src/pages/leaf/LeafContent.tsx:25-58,95-103` | 只代表 UI fallback，不是视频成功 | 统计时排除 |
| E2E API fixtures | 测试固定数据 | `frontend/e2e/leaf.spec.ts`; `page.route` | 不能作为真实业务结果 | 仅用于测试方法说明 |
| KB structured fixtures | 测试固定数据 | `backend/tests/fixtures/knowledge_base.py`; `frontend/src/test/fixtures/knowledgeBase.ts` | 不能作为教材真实规模 | 统计时排除 |
| 教材翻译 | 已实现但未接入主流程 | ingestion 不调用翻译，英文可直接进入 `content_zh` | 不能写“自动翻译已上线” | 标为函数实现+单测 |
| 教材向量写入 | 仅存在数据库模型 | 只有 query embedding；无文档 embedding assignment | 不能写向量库已运行 | 完成写入/索引/成功分支测试后再写 |
| KB extension resources | 已实现但未接入主流程 | 后端 API 有，Leaf UI 无消费 | 不能写学生端已展示扩展资源 | 接入后运行验证 |
| KB notice read | 仅存在后端接口 | 前端没有调用 read POST | 未读通知不会由当前 UI 标已读 | 标为后端接口存在 |
| `find-materials` | 仅存在后端接口 | 只改 gap 状态并返回来源，不执行搜索 | 功能名超出实际行为 | 正文使用实际行为描述 |
| 管理数据 overview | 已实现但未实际运行验证 | 漏计 `chapterweakness`,`chapterquizattempt` | 不能称“全量学习数据” | 明确统计范围 |
| 真实 LLM/视频/embedding | 尚未验证 | 本次测试均未调用真实外部服务 | 不能声称真实成功率 | 执行第 14 节实验 |

## 12. 资料冲突表

| 冲突主题 | 来源 A | 来源 B | 源码实际情况 | 文档应采用的口径 |
|---|---|---|---|---|
| Agent 数量 | README：7 AI Agents | 后端文档：3 workers；contracts 含 compose | 1 supervisor + 7 worker；compose 是程序阶段 | “7 个 LangGraph worker + 1 supervisor；另有 compose 程序阶段” |
| 用户角色 | API/DB 文档：student/teacher/admin | schemas/frontend types | 仅 student/admin；teacher 迁移为 admin | 两角色；teacher 只作历史兼容说明 |
| 数据库表数 | DB 文档：11 | SQLModel metadata | 19 表，新增8张 KB 表 | 以19表为当前 ER 基线 |
| quiz/progress 状态 | DB/API 文档：`failed`,`unlocked` | `backend/app/schemas.py:678-680` | `error`,`available` | 使用 generated schema 字面量 |
| Auth identifier | 认证文档：email only | `backend/app/schemas.py:14-23` | email 或中国手机号 | 使用 schema 校验规则 |
| chat start body | 业务 API 文档：空 body | `ChatStartRequest` | `query` 必填 | 使用 OpenAPI DTO |
| chat message | 业务 API 文档漏字段 | `ChatMessageRequest` | 含 `image_attachment` | 使用 OpenAPI DTO |
| Learning path 状态 | 文档 `learning` | 当前 schema | `in_progress|completed` | 使用 schema 字面量 |
| Leaf/Forest DTO | 人工文档旧字段 | OpenAPI/源码 | 当前字段显著不同 | 以 OpenAPI 与 `src/types/api.ts` 为唯一接口契约 |
| KB API 范围 | 业务 API 文档未列 | 当前 router | 18 条 KB paths | 本报告第5节为当前清单 |
| pgvector | RAG 设计：VECTOR/HNSW | model/service | FLOAT[]，无写入/索引；异常 fallback | “混合检索尝试存在，向量分支尚未验证” |
| 中文事实源 | RAG 设计：中文正文唯一 | ingestion/service/tests | 英文可不翻译进入后续链 | “优先 `content_zh`，不存在时使用原文” |
| 扩展资源 | 设计：进入 Leaf | 当前 frontend | 学生端未消费 | 标为管理端/后端能力 |
| 资源生成 | README：动画自动生成 | 当前主线 | Markdown/动画用 LLM，视频不用 LLM，compose 是普通函数 | 按每阶段真实性质描述 |
| 模型名称 | README/后端文档 `qwen3.5-plus-2026-04-20` | 本地 env/Compose/code default | 部署时由 `LLM_MODEL` 注入；本地为另一版本；代码缺省 `gpt-4o` | 架构写 OpenAI-compatible + 部署配置，不固定本地快照 |
| Python 版本 | `pyproject >=3.11` | Dockerfile Python 3.12 | 开发最低3.11，生产镜像3.12 | 同时列明 |
| 生产建表/seed | README：首次自动建表/demo | `backend/app/main.py:45-48` | 生产只检查 Alembic head；开发才 init/seed | 生产以 migration 为准 |
| License | README：MIT | 根目录 | 没有许可证正文 | “许可证材料未提供” |
| UI字体 | 字体文档允许 Caveat/Google | session规范禁止；tokens 含 Caveat | 规范内部冲突，代码仍有 Caveat token | 正式文档写 LXGW 主字体并列遗留 |
| UI token 合规 | 规范：全 OKLCH/spacing tokens | 当前 CSS/TSX | 仍有 HEX/RGB、任意 px | 规范是目标，不写全量合规 |
| 部署模式 | 7/13 域名长期基线 | 7/14 IP HTTPS 设计/部署文档 | 当前为 ICP 前 production-ip 覆盖 | 区分当前临时模式与长期目标 |
| 本地/远程 | 本地 `HEAD`/任务开始工作区 | GitHub main/最终工作区 | commit 相同、0/0；任务开始时为空；最终有4个并发未提交文件差异 | 写“commit 同步；最终工作区含未提交视频超时改动” |
| 本地测试/CI | 本地后端/前端通过 | GitHub Production readiness | CI lint/shellcheck 失败，测试被 skipped | 分开报告，不能用本地通过替代 CI |
| OpenAPI/类型 | 前端多为手写类型 | generated files | 文件内容同步；生产仅 KB API 局部引用 generated components | 区分“生成文件同步”与“全调用强引用” |
| 计划 checkbox | merge-role plan 0/26 | 当前源码 | 两角色已落地 | checkbox 只反映计划维护，不反映实现状态 |
| 开发工具说明 | 本地忽略文件 `.github/code-review-graph.instruction.md` | 当前用户级工具 surface | 当前环境可调用 code-review-graph 工具，但该说明未被 Git 跟踪，工具也不属于 OneTree 产品运行链 | 只作开发环境说明，不用于产品架构章 |

## 13. 人工补充数据清单

下表“最少样例”是采集计划下限，不是当前已有数量。

| 数据名称 | 为什么需要 | 用于章节 | 采集方法 | 最少样例 | 保存格式 | 当前状态 |
|---|---|---|---|---:|---|---|
| 软件杯赛题原文 | 确认目标与验收边界 | 1 | 官方下载/盖章材料 | 1 份 | PDF+Markdown 摘要 | 未提供 |
| 项目申报要求 | 控制章节、字数、附件 | 1、6 | 官方通知 | 1 份 | PDF | 未提供 |
| 项目立项原因 | 建立真实问题链 | 1 | 团队访谈+会议纪要 | 1 份确认稿 | Markdown | 未提供 |
| 学生问卷 | 支撑痛点比例与需求排序 | 1、6 | 匿名问卷 | 30 份有效问卷 | CSV+问卷原稿 | 未提供 |
| 学生访谈 | 解释问卷原因与场景 | 1、6 | 半结构访谈 | 8 人 | 脱敏记录+编码表 | 未提供 |
| 教师/管理员访谈 | 验证培养方案、知识库流程 | 1、6 | 半结构访谈 | 5 人 | 脱敏 Markdown | 未提供 |
| 有效样本规则 | 防止只报总回收数 | 1、5 | 预注册排除规则 | 1 份 | Markdown | 未提供 |
| 用户试用反馈 | 证明可用性与价值 | 5、6 | 任务后量表+开放问题 | 20 名学生 | CSV+摘要 | 未提供 |
| 同类产品清单 | 建立对比范围 | 1、4 | 官方资料检索 | 5 个产品 | CSV+URL归档 | 未提供 |
| 竞品功能对比 | 支撑功能创新 | 4 | 统一任务脚本人工核对 | 5 个产品 | CSV+截图 | 未提供 |
| 竞品技术对比 | 避免宣传式创新 | 4 | 公开技术资料核对 | 3 个可核技术方案 | Markdown+来源 | 未提供 |
| 单模型/多智能体结果 | 证明编排收益 | 4、5 | 配对实验 | 每组30任务 | JSONL+评分CSV | 未提供 |
| 知识库启停结果 | 证明反幻觉收益 | 4、5 | 配对盲评 | 每组30任务 | JSONL+证据标注 | 未提供 |
| 人工内容准确性评价 | 验证 Markdown/测验 | 4、5 | 双人独立评分+仲裁 | 50 个输出 | CSV+rubric | 未提供 |
| 性能测试 | 给出 P50/P95/吞吐 | 5 | 固定环境压测 | 3轮×每档 | JSON/CSV+命令日志 | 未提供 |
| 并发测试 | 验证会话/worker/DB稳定 | 5 | 1/5/10/20 并发阶梯 | 每档10分钟 | 原始日志+汇总CSV | 未提供 |
| 安全测试 | 覆盖注册提权、JWT、SSE错误 | 5 | 权限矩阵+安全审计 | 全55 paths风险分层 | Markdown+测试日志 | 未提供 |
| 部署环境 | 复现实验与上线 | 3、5、6 | 资产清单 | 1 套当前环境 | Markdown+版本输出 | 未提供 |
| 团队成员与分工 | 支撑总结和申报 | 6 | 团队确认 | 全员 | Markdown | 未提供 |
| 开发时间线 | 解释里程碑 | 6 | Git历史+成员核对 | 1 条确认时间线 | CSV/Markdown | 未提供 |
| 当前页面截图 | 形成界面证据 | 1、3、5 | 真实账号逐路由截图 | 第4节所有核心路由 | PNG+manifest | 未提供当前版本 |
| 演示账号 | 复现实机流程 | 3、5 | 管理员创建并确认权限 | student/admin 各1 | 加密保管+说明 | 未提供 |
| 实际演示数据 | 避免 Mock/seed 混入 | 3、5 | 预置并标记来源 | 1套完整学习旅程 | SQL只读快照说明+JSON | 未提供 |
| License 正文 | 补足授权材料 | 1、6 | 团队/权利人确认 | 1 份 | `LICENSE` | 未提供 |
| 项目未来规划 | 形成可承诺展望 | 6 | 团队评审 | 1 份路线图 | Markdown | 未提供 |

## 14. 对比实验和质量评估计划

所有实验须固定 commit、`LLM_MODEL`、prompt 版本、教材版本和随机参数；原始输出只追加保存，评分者不知道实验组别。样本数量是最低计划值，不是当前结果。

| 实验 | 目的 | 输入 | 最少样本 | 评价指标 | 数据保存格式 | 用于章节 | 当前仓库是否已有数据 |
|---|---|---|---:|---|---|---|---|
| 多智能体 vs 单模型 | 验证分工/门禁收益 | 同一画像、教材、任务指令 | 30 配对任务/组 | 任务完成率、结构合格率、来源绑定率、阶段失败率、内容完整性、双人评分 | JSONL+CSV+rubric | 4、5 | 否 |
| 知识库启用 vs 禁用 | 验证反幻觉 | 30 个可由教材核对的问题 | 30 配对任务/组 | 事实错误数、引用率、教材匹配率、无依据内容比例、可追溯性、人工准确性 | JSONL+证据 span 表 | 4、5 | 否 |
| 不同画像路径 | 验证个性化差异 | 专业/年级/目标/每周时间/偏好正交组合 | 20 组画像，每组重复3次 | 课程集合差异、顺序差异、目标匹配、时间约束满足、专家合理性 | JSONL+pairwise CSV | 4 | 否 |
| Markdown 质量 | 验证结构与来源 | 已发布教材的多类小节 | 50 个小节 | 生成成功率、结构门禁、事实准确性、来源 footer、完整性、可读性 | Markdown+CSV | 4、5 | 否 |
| 视频相关性 | 验证诚实降级 | 30 个有资源/无资源混合小节 | 30 个小节 | 匹配率、可访问率、主题相关性、无结果诚实率 | JSONL+URL检查CSV | 4、5 | 否 |
| 动画可运行性 | 验证生成与教学价值 | 30 个适合/不适合动画的小节 | 30 个小节 | 生成率、沙箱运行率、控制台错误、教学相关性、无动画判断合理性 | HTML归档+运行日志+CSV | 4、5 | 否 |
| 资源合成 | 验证占位替换与降级 | Markdown+视频/动画四种可用组合 | 每组合10例 | 合成成功率、占位残留、顺序正确、unavailable 呈现 | JSON+截图 | 4、5 | 仅测试固定数据 |
| 测验题目正确性 | 验证 quiz agent | 已发布教材的章节 | 50 道题 | 题意正确、答案正确、分值合理、来源一致 | JSONL+双人评分 | 4、5 | 否 |
| 批改正确性 | 验证评分 | 正确/部分正确/错误/异常答案 | 100 份答卷 | 分数一致率、passed 一致率、解释正确性 | JSONL+gold CSV | 5 | 否 |
| 薄弱点识别 | 验证诊断 | 带预设错误模式的答卷 | 50 份 | precision、recall、severity 一致性 | CSV | 4、5 | 否 |
| 解锁状态 | 验证学习流程 | 章节顺序与通过/未通过组合 | 40 条状态转移 | `locked/available/passed` 状态正确率、下一章/下一课正确率 | JSONL | 5 | 仅自动测试，无人工集 |
| Prompt 预算 | 验证裁剪影响 | 低于/接近/超过各 phase limit 的输入 | 每 phase 20例 | 裁剪率、protected fragment 保留、结构合格率、准确性变化 | JSONL+CSV | 4、5 | 仅单元测试 |
| 恢复机制 | 验证失败后续跑 | 每阶段注入超时/网络/持久化失败 | 每阶段10例 | failed checkpoint 记录率、恢复成功率、重复写入、最终一致性 | trace JSONL+DB聚合 | 4、5 | 部分契约测试；真实错误 checkpoint 存在缺口 |

实验结论状态在采集前统一为“尚未验证”，不得用测试 fixture 或 README 表述替代。

## 15. 数据库只读查询方案

以下语句仅包含只读查询。执行前固定数据库 URL、记录时间与 commit；输出需标注是否排除 seed/test。表名与字段来自 `backend/app/models.py:73-471`。

### 账号、cohort、学习与测验

```sql
SELECT role, COUNT(*) AS user_count
FROM "user"
GROUP BY role
ORDER BY role;

SELECT school, major, class_name, COUNT(*) AS user_count
FROM "user"
WHERE school <> '' AND major <> '' AND class_name <> ''
GROUP BY school, major, class_name
ORDER BY school, major, class_name;

SELECT COUNT(*) AS profile_count FROM userprofile;

SELECT grade_year, COUNT(*) AS path_count
FROM useryearlearningpath
GROUP BY grade_year
ORDER BY grade_year;

SELECT grade_year, COUNT(*) AS outline_count
FROM usercourseknowledgeoutline
GROUP BY grade_year
ORDER BY grade_year;

SELECT status, COUNT(*) AS quiz_count
FROM chapterquiz
GROUP BY status
ORDER BY status;

SELECT COUNT(*) AS attempt_count,
       AVG(score) AS average_score,
       COUNT(*) FILTER (WHERE passed) AS passed_attempt_count
FROM chapterquizattempt;

SELECT state, COUNT(*) AS chapter_count
FROM chapterprogress
GROUP BY state
ORDER BY state;

SELECT severity, consumed, COUNT(*) AS weakness_count
FROM chapterweakness
GROUP BY severity, consumed
ORDER BY severity, consumed;

SELECT COUNT(*) AS scored_course_count,
       AVG(accuracy_score) AS average_accuracy,
       AVG(difficulty_fit_score) AS average_difficulty_fit,
       AVG(completeness_score) AS average_completeness,
       AVG(overall_score) AS average_overall
FROM courseresourcequality;
```

### 知识库、准入、发布与 ingestion

```sql
SELECT COUNT(*) AS admitted_source_count
FROM knowledgesource
WHERE status = 'enabled'
  AND download_status = 'verified'
  AND parse_status = 'supported'
  AND license_review_status = 'approved'
  AND human_review_status = 'reviewed';

SELECT ingestion_status,
       outline_review_status,
       student_availability_status,
       COUNT(*) AS textbook_count
FROM textbook
GROUP BY ingestion_status, outline_review_status, student_availability_status
ORDER BY ingestion_status, outline_review_status, student_availability_status;

SELECT textbook_id, COUNT(*) AS section_count, SUM(content_char_count) AS content_chars
FROM textbooksectioncontent
GROUP BY textbook_id
ORDER BY textbook_id;

SELECT status, COUNT(*) AS gap_count, SUM(trigger_count) AS trigger_count
FROM knowledgegap
GROUP BY status
ORDER BY status;

SELECT status, COUNT(*) AS job_count, AVG(attempt_count) AS average_attempt_count
FROM knowledgebaseingestionjob
GROUP BY status
ORDER BY status;
```

### 业务关联完整性

```sql
SELECT COUNT(*) AS textbook_source_orphans
FROM textbook t
LEFT JOIN knowledgesource s ON s.source_id = t.source_id
WHERE t.source_id IS NOT NULL AND s.source_id IS NULL;

SELECT COUNT(*) AS section_textbook_orphans
FROM textbooksectioncontent c
LEFT JOIN textbook t ON t.textbook_id = c.textbook_id
WHERE t.textbook_id IS NULL;

SELECT COUNT(*) AS extension_textbook_orphans
FROM textbookextensionresource r
LEFT JOIN textbook t ON t.textbook_id = r.textbook_id
WHERE t.textbook_id IS NULL;

SELECT COUNT(*) AS gap_textbook_orphans
FROM knowledgegap g
LEFT JOIN textbook t ON t.textbook_id = g.resolved_textbook_id
WHERE g.resolved_textbook_id IS NOT NULL AND t.textbook_id IS NULL;

SELECT COUNT(*) AS follow_gap_orphans
FROM knowledgegapfollow f
LEFT JOIN knowledgegap g ON g.gap_id = f.gap_id
WHERE g.gap_id IS NULL;

SELECT COUNT(*) AS notice_user_orphans
FROM knowledgegapnotice n
LEFT JOIN "user" u ON u.uid = n.user_uid
WHERE u.uid IS NULL;

SELECT COUNT(*) AS ingestion_textbook_orphans
FROM knowledgebaseingestionjob j
LEFT JOIN textbook t ON t.textbook_id = j.textbook_id
WHERE t.textbook_id IS NULL;
```

### 会话与时间粒度

```sql
SELECT DATE(created_at) AS created_date, COUNT(*) AS session_count
FROM conversationsession
GROUP BY DATE(created_at)
ORDER BY created_date;

SELECT DATE(created_at) AS attempt_date,
       COUNT(*) AS attempt_count,
       AVG(score) AS average_score
FROM chapterquizattempt
GROUP BY DATE(created_at)
ORDER BY attempt_date;
```

`usercourseknowledgeoutline.outline_data` 与 `useryearlearningpath.path_data` 的 JSONB 统计必须先依据当前对象结构建立版本化字段字典；本报告不猜测未核对的 JSON path。agent trace、Prompt budget 和 SSE 指标当前没有数据库事实表，需先以 JSONL 保留完整字段后再汇总。

## 16. 下一步执行顺序

### P0

1. 获取软件杯赛题原文、申报要求、技术文档模板与评分点；没有权威边界，第一章和整篇结构无法定稿。
2. 由团队确认项目名称、两角色口径、当前部署模式、团队成员/分工、开发时间线、License；删除正式文档中的 teacher 独立角色与未经授权的 MIT 断言。
3. 确认本地数据库 3 个用户、2 个培养方案、2 本教材等记录的数据性质；建立 seed/test/演示/真实数据标记。未确认前不得引用规模数字。
4. 解决本地 Alembic 无 current revision 的验收状态并保留迁移日志；这是生产启动的直接阻断证据。本阶段只记录，修复需另开任务。
5. 重新运行隔离 Playwright，处理 3 个当前失败后保留完整报告；本次不能声明 E2E 通过。
6. 收集当前版本的 student/admin 全流程截图，并为每张图记录路由、账号角色、数据来源、commit、是否 Mock。
7. 执行多智能体/单模型与知识库启停两项核心实验；没有对照数据，第四章不能形成可验证创新结论。

### P1

1. 执行学生问卷、学生/教师访谈和试用反馈，给出有效样本规则、原始数据和脱敏摘要。
2. 建立 50 个输出的人工准确性评价集，覆盖 Markdown、测验、薄弱点；双人评分并保留仲裁。
3. 完成性能、并发和安全测试，特别覆盖公开注册 admin、禁用账号登录、SSE 错误文本、55 条 API 权限矩阵。
4. 验证真实 embedding 写入、数据库 operator/索引与混合检索成功分支；验证前不使用“pgvector/RAG 混合检索已跑通”表述。
5. 运行真实 LLM、视频搜索、动画沙箱和 worker 长时任务，采集 trace、阶段耗时、失败/恢复、Prompt 裁剪、模型/Token/成本。
6. 更新或重写过时的 API、数据库、后端 agent 文档，所有字段以当前 OpenAPI/models/contracts 为准；计划 checkbox 与实现状态分开。
7. 检查最新 GitHub Actions，保存 Ruff/Biome/ShellCheck/测试/容器/smoke 各 job 结果；CI 全链通过前不得写“持续集成通过”。

### P2

1. 完成 5 个同类产品的功能对比与至少 3 个可核技术方案对比，保存官方来源与访问日期。
2. 补移动端、跨浏览器、无障碍、暗色/reduced-motion 截图与验证。
3. 将 UI 规范目标与当前遗留分开整理，统计 HEX/RGB、任意 px、Caveat token 等合规差距。
4. 绘制正式架构图、LangGraph 图、SSE 时序图和 ER 图；业务关联用虚线，数据库 FK 用实线。
5. 将视频制作、磁盘清理、历史缺陷账本等材料移入附录/归档索引，避免与当前技术事实混写。
6. 在团队确认后形成未来路线图，每项包含负责人、截止时间、验收标准和证据位置。

完成 P0 后，可开始正式技术文档的全章撰写；P1 决定第四、第五章可信度；P2 用于增强展示和可维护性。
