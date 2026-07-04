# RAG 知识库与教材来源闭环重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构一棵树 (OneTree) 的知识库管理员端、教材整理链路和学生侧 Agent 契约，形成“管理员一句话/手动上传 -> Agent 在线找教材并整理 -> 管理员校对 -> 发布 -> 草案智能体只在已发布知识库推荐 -> 路径智能体回到知识库找来源”的完整闭环。

**Architecture:** 第一期只保留真实教材来源闭环，不把 AI 创作教材当成主线。管理员端用现有知识库数据模型承接来源发现、导入、整理、校对、发布与归档；后端以已发布教材为唯一学生可见来源，草案智能体只做已发布知识库检索后的推荐，路径智能体只做来源回写与关系编排，章节智能体只读教材大纲与正文切片。前端把 admin knowledge base 页面改成“来源/教材/待覆盖/扩展资料”四个工作区，移除第一期里的 AIGC 创作入口与正文生成入口。

**Tech Stack:** FastAPI, SQLModel, PostgreSQL, LangGraph / LangChain structured output, React 18, TypeScript, Vite, Biome, Ruff, Playwright, pytest

---

### Task 1: 锁定第一期产品边界并移除旧计划残留

**Files:**
- Modify: `docs/superpowers/specs/2026-06-27-rag-knowledge-base-design.md`
- Create: `docs/superpowers/plans/2026-06-29-rag-knowledge-base-plan.md`
- Delete: `docs/superpowers/plans/2026-06-27-rag-knowledge-base-implementation.md`

- [ ] **Step 1: 把第一期边界写死到 spec 和 plan**

```markdown
第一期只做：
管理员说一句话或手动上传
-> Agent 在线找教材并整理
-> 管理员校对
-> 发布到已发布知识库
-> 草案智能体只从已发布知识库推荐
-> 路径智能体回到知识库找来源

AI 创作教材、AI 生成正文、generate-outline、generate-content 全部移到后续阶段。
```

- [ ] **Step 2: 删除旧 implementation plan**

```bash
rm docs/superpowers/plans/2026-06-27-rag-knowledge-base-implementation.md
```

- [ ] **Step 3: 在 spec 中同步确认第一期不包含创作教材**
  检查并保留以下表述：
  - 管理员说一句话，Agent 自行到网上检索适合的教材来源
  - 管理员也可以直接上传 PDF 教材
  - Agent 将检索到的教材或上传的 PDF 整理到小节正文级别
  - 管理员确认大纲与正文切片后点击“发布”
  - 发布后的教材进入已发布知识库，成为唯一来源

- [ ] **Step 4: 验收**
  运行：`rg -n "AI 创作教材|generate-outline|generate-content|Outline Copilot|AIGC Center" docs/superpowers/specs/2026-06-27-rag-knowledge-base-design.md docs/superpowers/plans/2026-06-29-rag-knowledge-base-plan.md`
  预期：仅在后续阶段说明里出现，不在第一期主线里出现。

---

### Task 2: 统一知识库数据模型、状态机和迁移策略

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/schema_upgrades.py`
- Modify: `backend/app/services/knowledge_base_service.py`
- Modify: `backend/app/api/knowledge_base.py`
- Create: `backend/tests/test_knowledge_base_textbook_lifecycle.py`
- Create: `backend/tests/test_knowledge_base_source_to_publish.py`

- [ ] **Step 1: 写状态机测试，先锁教材生命周期**

```python
from sqlmodel import Session
from app.models import Textbook

def test_textbook_lifecycle_states(db_session: Session):
    textbook = Textbook(
        textbook_id="tb-001",
        source_id="source-001",
        title="测试教材",
    )
    db_session.add(textbook)
    db_session.commit()
    db_session.refresh(textbook)
    assert textbook.ingestion_status == "not_started"
    assert textbook.outline_review_status == "unreviewed"
    assert textbook.student_availability_status == "draft"
```

- [ ] **Step 2: 写发布/下架/删除测试，先锁行为**

```python
def test_publish_then_unpublish_then_archive(db_session: Session):
    ...
```

要求断言：
  - draft 教材可以发布
  - published 教材可以下架
  - draft 且没有学生绑定时可物理删除
  - 非 draft 或已绑定时只允许归档

- [ ] **Step 3: 扩展 `Textbook` 和 `TextbookSectionContent` 的字段约束**
  把数据模型与现有知识库真实字段对齐，明确保留：
  - `ingestion_status`
  - `outline_review_status`
  - `student_availability_status`
  - `published_at`
  - `unpublished_at`
  - `archived_at`
  - `embedding`

  如果需要新增字段，只加能支撑第一期闭环的字段，不加 AI 创作专用字段。

- [ ] **Step 4: 完成 schema upgrade，兼容旧库**
  在 `schema_upgrades.py` 里补齐：
  - `textbook` / `textbook_section_content` / `textbook_extension_resource` 的升级路径
  - `TEXTBOOK_STUDENT_AVAILABILITY_STATUS_VALUES` 的约束校验
  - `embedding` 类型的 PostgreSQL 兼容升级
  - 旧数据向新发布状态的迁移规则

- [ ] **Step 5: 验收**
  运行：
  - `pytest backend/tests/test_knowledge_base_textbook_lifecycle.py -v`
  - `pytest backend/tests/test_knowledge_base_source_to_publish.py -v`
  - `ruff check --fix backend/app/models.py backend/app/schema_upgrades.py backend/app/services/knowledge_base_service.py backend/app/api/knowledge_base.py backend/tests/test_knowledge_base_textbook_lifecycle.py backend/tests/test_knowledge_base_source_to_publish.py`
  - `ruff format backend/app/models.py backend/app/schema_upgrades.py backend/app/services/knowledge_base_service.py backend/app/api/knowledge_base.py backend/tests/test_knowledge_base_textbook_lifecycle.py backend/tests/test_knowledge_base_source_to_publish.py`

---

### Task 3: 重做教材来源发现、整理、校对、发布后端链路

**Files:**
- Modify: `backend/app/api/knowledge_base.py`
- Modify: `backend/app/services/knowledge_base_service.py`
- Modify: `backend/app/orchestration/agents/learning_path_intake.py`
- Modify: `backend/app/orchestration/agents/course_knowledge.py`
- Modify: `backend/app/orchestration/agents/models.py`
- Modify: `backend/app/orchestration/state.py`
- Create: `backend/tests/test_learning_path_intake_published_only.py`
- Create: `backend/tests/test_course_knowledge_source_binding.py`
- Create: `backend/tests/test_section_markdown_source_context.py`

- [ ] **Step 1: 锁定草案 Agent 只能看已发布知识库**

```python
def test_learning_path_intake_uses_published_textbooks_only(...):
    ...
```

要求断言：
  - 输入中存在未发布教材时，草案 Agent 不把它推荐给学生
  - 只有 `student_availability_status == "published"` 的教材能进入候选
  - 找不到已发布教材时返回明确的知识库覆盖缺口，不假造课程

- [ ] **Step 2: 锁定路径 Agent 的来源回写**

```python
def test_learning_path_agent_binds_source_textbook(...):
    ...
```

要求断言：
  - 每个课程节点都有 `source_textbook_id`
  - 每个课程节点都有 `source_textbook_title`
  - 每个课程节点都有 `source_outline_section_ids`
  - 不能从空值或未发布教材自动补出来源

- [ ] **Step 3: 锁定章节 Agent 只读已发布教材大纲**
  `course_knowledge_agent` 的契约要明确：
  - 输入是 `course_node_id` + 已绑定的 `source_textbook_id`
  - 输出直接基于教材 `outline`
  - 如果教材不是已发布状态，直接失败
  - 不保留“降级为旧版大模型参数生成”的路径

- [ ] **Step 4: 锁定小节 Markdown Agent 只读教材正文切片**
  `section_markdown_agent` 的契约要明确：
  - 输入是小节正文切片
  - 输出是格式化教学 Markdown
  - 不允许直接吃整本教材

- [ ] **Step 5: 扩展 orchestration state**
  把已发布教材检索结果、课程来源绑定信息、小节正文上下文纳入 state，保证三个 Agent 不再自行“猜来源”。

- [ ] **Step 6: 验收**
  运行：
  - `pytest backend/tests/test_learning_path_intake_published_only.py -v`
  - `pytest backend/tests/test_course_knowledge_source_binding.py -v`
  - `pytest backend/tests/test_section_markdown_source_context.py -v`

---

### Task 4: 重构管理员知识库 API，保留导入与整理，移除第一期生成入口

**Files:**
- Modify: `backend/app/api/knowledge_base.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/services/document_parser_service.py`
- Create: `backend/tests/test_admin_knowledge_base_routes.py`
- Create: `backend/tests/test_document_parser_service.py`

- [ ] **Step 1: 写 API 路由测试，先锁定需要保留和移除的接口**

```python
def test_admin_knowledge_base_routes(client: TestClient, admin_token_headers):
    ...
```

要求覆盖：
  - `POST /api/admin/knowledge-base/sources`
  - `GET /api/admin/knowledge-base/sources`
  - `GET /api/admin/knowledge-base/textbooks`
  - `POST /api/admin/knowledge-base/textbooks`
  - `POST /api/admin/knowledge-base/textbooks/{textbook_id}/publish`
  - `POST /api/admin/knowledge-base/textbooks/{textbook_id}/unpublish`
  - `DELETE /api/admin/knowledge-base/textbooks/{textbook_id}`
  - `PUT /api/admin/knowledge-base/textbooks/{textbook_id}/outline`
  - `POST /api/admin/knowledge-base/textbooks/{textbook_id}/agent-organize`
  - `POST /api/admin/knowledge-base/gaps/{gap_id}/find-materials`
  - `POST /api/admin/knowledge-base/gaps/{gap_id}/upload`

- [ ] **Step 2: 先删除第一期不该存在的 AI 生成接口**
  从后端 API 和 schemas 中移除或停用：
  - `generate-outline`
  - `generate-content`
  - `generation-progress`

  这些能力只保留到后续阶段文档，不出现在第一期实现里。

- [ ] **Step 3: 实现来源发现接口**
  管理员说一句话后，系统要能返回：
  - 检索到的教材来源
  - 进入待整理的教材草案
  - 可能的覆盖缺口

  这一步不是生成教材内容，而是把教材来源找出来并进入管理员可审校的队列。

- [ ] **Step 4: 实现整理和发布接口**
  让整理结果可以：
  - 更新 outline
  - 写入 section content
  - 切到待校对状态
  - 发布到学生可见状态

- [ ] **Step 5: 验收**
  运行：
  - `pytest backend/tests/test_admin_knowledge_base_routes.py -v`
  - `pytest backend/tests/test_document_parser_service.py -v`
  - `ruff check --fix backend/app/api/knowledge_base.py backend/app/schemas.py backend/app/services/document_parser_service.py backend/tests/test_admin_knowledge_base_routes.py backend/tests/test_document_parser_service.py`
  - `ruff format backend/app/api/knowledge_base.py backend/app/schemas.py backend/app/services/document_parser_service.py backend/tests/test_admin_knowledge_base_routes.py backend/tests/test_document_parser_service.py`

---

### Task 5: 重新定义 admin knowledge base 前端，不再主打 AIGC 创作

**Files:**
- Modify: `frontend/src/pages/admin/AdminKnowledgeBasePage.tsx`
- Modify: `frontend/src/pages/admin/AdminKnowledgeBasePage.test.tsx`
- Modify: `frontend/src/pages/admin/OutlineEditor.tsx`
- Modify: `frontend/src/pages/admin/admin.css`
- Modify: `frontend/src/api/knowledgeBase.ts`
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: 写页面级测试，先锁定管理员端信息架构**

```tsx
it("renders sources textbooks gaps and extension resources without AIGC creator entry", async () => {
  ...
});
```

要求断言：
  - 页面保留来源清单、教材列表、未覆盖待办、扩展资料绑定
  - 页面不再出现“AI 教材创作中心”
  - 页面不再出现“AI 生成内容”按钮
  - 页面不再把 outline editor 包成创作入口

- [ ] **Step 2: 重做 AdminKnowledgeBasePage 的首屏结构**
  首屏应该是一个工作台，不是创作落地页：
  - 来源清单
  - 教材列表
  - 未覆盖待办
  - 扩展资料绑定
  - 大纲校对区

- [ ] **Step 3: 调整 OutlineEditor 的职责**
  `OutlineEditor` 只负责：
  - 查看整理后的大纲
  - 修改大纲文本
  - 保留章节折叠与拖拽
  - 保存校对结果

  不再负责生成新教材，也不再持有生成正文的 UI。

- [ ] **Step 4: 同步 API 封装和类型**
  `frontend/src/api/knowledgeBase.ts` 与 `frontend/src/types/api.ts` 要和后端契约一致：
  - 只保留第一期需要的接口
  - 删掉前端对 generate-outline/generate-content 的调用
  - 保留 upload / outline / publish / unpublish / delete / gaps / extension resources

- [ ] **Step 5: 更新样式**
  `admin.css` 里把创作面板样式移除或替换为整理工作台样式，保证管理员页不再像“生成器控制台”。

- [ ] **Step 6: 验收**
  运行：
  - `npx biome check --write frontend/src/pages/admin/AdminKnowledgeBasePage.tsx frontend/src/pages/admin/AdminKnowledgeBasePage.test.tsx frontend/src/pages/admin/OutlineEditor.tsx frontend/src/pages/admin/admin.css frontend/src/api/knowledgeBase.ts frontend/src/types/api.ts frontend/src/App.tsx`
  - `npm run gen:api`
  - `npm test -- AdminKnowledgeBasePage`

---

### Task 6: 端到端回归，验证闭环和拒绝旧方向

**Files:**
- Modify: `backend/tests/test_orchestration_api.py`
- Modify: `frontend/src/App.test.tsx`
- Create: `backend/tests/test_rag_knowledge_base_e2e_flow.py`

- [ ] **Step 1: 写后端闭环测试**
  覆盖顺序：
  1. 管理员创建来源或上传教材
  2. Agent 整理到 outline / section content
  3. 管理员发布
  4. 学生草案只推荐已发布教材
  5. 路径 Agent 回写来源
  6. 章节 Agent 读取已发布教材大纲

- [ ] **Step 2: 写前端路由测试**
  断言：
  - `/admin/knowledge-base` 可访问
  - 管理员页面首屏是整理工作台
  - 不存在旧 AIGC 创作入口

- [ ] **Step 3: 跑全量验证**
  运行：
  - `pytest backend/tests/test_rag_knowledge_base_e2e_flow.py -v`
  - `pytest backend/tests/test_orchestration_api.py -v`
  - `npm test -- App`

---

### Task 7: 清理旧实现和文档漂移

**Files:**
- Modify: `docs/superpowers/specs/2026-06-27-rag-knowledge-base-design.md`
- Modify: `docs/superpowers/plans/2026-06-29-rag-knowledge-base-plan.md`
- Modify: `backend/app/api/knowledge_base.py`
- Modify: `frontend/src/pages/admin/AdminKnowledgeBasePage.tsx`
- Modify: `frontend/src/pages/admin/OutlineEditor.tsx`
- Modify: `frontend/src/api/knowledgeBase.ts`

- [ ] **Step 1: 清掉第一期里任何会误导实现方向的文案**
  把“创作中心”“生成内容”“一键生成正文”“Outline Copilot”之类描述从第一期主线移走。

- [ ] **Step 2: 清掉旧接口残留的调用路径**
  保证前后端没有任何 UI 入口会再调用 generate-outline / generate-content。

- [ ] **Step 3: 验收**
  运行：
  - `rg -n "generate-outline|generate-content|AIGC Center|AI 教材创作中心|Outline Copilot" backend frontend docs/superpowers`

---

### Task 8: 最终验证与交付

**Files:**
- No new files

- [ ] **Step 1: 跑后端测试全集**
  运行：`pytest backend/tests -v`

- [ ] **Step 2: 跑前端测试全集**
  运行：`npm test`

- [ ] **Step 3: 跑前端类型和格式化**
  运行：`npx biome check --write frontend/src`

- [ ] **Step 4: 跑后端格式化和静态检查**
  运行：`ruff check --fix backend && ruff format backend`

- [ ] **Step 5: 检查文档和代码一致性**
  确认：
  - spec 里第一期没有 AI 创作教材
  - plan 里第一期没有 AI 创作教材
  - admin 页没有创作入口
  - 草案智能体只看已发布知识库
  - 路径智能体强绑定来源教材

