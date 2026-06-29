# RAG 知识库与多智能体教材集成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为一棵树 (OneTree) 系统开发完整的 PostgreSQL 专属 RAG/CAG 教材知识库，打通从管理员 PDF 解析/AI 生成、章节/Markdown 智能体强绑定教材生成的全流程闭环。

**Architecture:** 采用 PostgreSQL 原生 JSONB+GIN 索引、pgvector 向量索引、以及 tsvector 全文检索，在数据库端实现 RRF 混合检索初筛大纲，然后在各智能体端通过直接载入整篇大纲及小节原文进行 CAG，规避 Token 耗尽和超时崩溃。

**Tech Stack:** FastAPI, SQLModel, PostgreSQL (pgvector, tsvector, JSONB), alibabacloud-docmind-api, React 18, Tailwind CSS, framer-motion, Biome, Ruff

---

### Task 1: 数据库结构与迁移 (Database Models & Migrations)

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/schema_upgrades.py`
- Modify: `backend/app/database.py`
- Create: `backend/tests/test_kb_models.py`

- [ ] **Step 1: 编写测试用例验证数据模型定义与约束**
  创建 `backend/tests/test_kb_models.py` 并写入以下测试：
  ```python
  from sqlmodel import Session, select
  from app.models import Textbook, TextbookSectionContent
  
  def test_create_and_query_textbook(db_session: Session):
      textbook = Textbook(
          id="test_tb_01",
          title="测试教材",
          tags=["测试", "Python"],
          outline={"chapters": [{"chapter_number": 1, "title": "第一章", "sections": []}]},
          status="success"
      )
      db_session.add(textbook)
      db_session.commit()
      
      db_session.refresh(textbook)
      assert textbook.title == "测试教材"
      assert textbook.tags == ["测试", "Python"]
      assert textbook.outline["chapters"][0]["title"] == "第一章"
  ```

- [ ] **Step 2: 运行测试确保其失败**
  运行：`pytest backend/tests/test_kb_models.py -v`
  预期：FAIL（`ImportError`，找不到 `Textbook`）

- [ ] **Step 3: 在 `backend/app/models.py` 中添加 `Textbook` 和 `TextbookSectionContent`**
  ```python
  import sqlalchemy as sa
  from sqlalchemy.dialects.postgresql import JSONB
  
  class Textbook(SQLModel, table=True):
      __tablename__ = "textbook"
      id: str = Field(primary_key=True, index=True)
      title: str = Field(index=True, nullable=False)
      author: Optional[str] = Field(default=None)
      tags: List[str] = Field(default_factory=list, sa_column=Column(JSONB))
      outline: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
      status: str = Field(default="processing", index=True)
      source_link: Optional[str] = Field(default=None)
      embedding: Optional[List[float]] = Field(default=None, sa_column=Column(JSONB))
      created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
      updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
  
  class TextbookSectionContent(SQLModel, table=True):
      __tablename__ = "textbook_section_content"
      id: str = Field(primary_key=True, index=True)
      textbook_id: str = Field(foreign_key="textbook.id", index=True, nullable=False)
      chapter_number: int = Field(index=True, nullable=False)
      section_id: str = Field(index=True, nullable=False)
      title: str = Field(nullable=False)
      content: str = Field(sa_column=sa.Column(sa.Text, nullable=False))
      created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
      updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
  ```

- [ ] **Step 4: 在 `backend/app/schema_upgrades.py` 中写入 PostgreSQL 数据库迁移语句**
  在 `run_schema_upgrades` 函数中添加表及索引创建语句：
  ```python
  def upgrade_add_kb_tables(connection):
      connection.execute(sa.text("""
          CREATE EXTENSION IF NOT EXISTS vector;
          CREATE EXTENSION IF NOT EXISTS pg_trgm;
          
          CREATE TABLE IF NOT EXISTS textbook (
              id VARCHAR(64) PRIMARY KEY,
              title VARCHAR(256) NOT NULL,
              author VARCHAR(128),
              tags JSONB DEFAULT '[]',
              outline JSONB DEFAULT '{}',
              status VARCHAR(32) NOT NULL DEFAULT 'processing',
              source_link TEXT,
              embedding VECTOR(1536),
              created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
              updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
          );
          
          CREATE TABLE IF NOT EXISTS textbook_section_content (
              id VARCHAR(64) PRIMARY KEY,
              textbook_id VARCHAR(64) REFERENCES textbook(id) ON DELETE CASCADE,
              chapter_number INTEGER NOT NULL,
              section_id VARCHAR(64) NOT NULL,
              title VARCHAR(256) NOT NULL,
              content TEXT NOT NULL,
              created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
              updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
          );
          
          CREATE INDEX IF NOT EXISTS idx_textbook_title ON textbook (title);
          CREATE INDEX IF NOT EXISTS idx_textbook_status ON textbook (status);
          CREATE INDEX IF NOT EXISTS idx_textbook_outline_gin ON textbook USING gin (outline);
          CREATE INDEX IF NOT EXISTS idx_textbook_embedding_hnsw ON textbook USING hnsw (embedding vector_cosine_ops);
          CREATE INDEX IF NOT EXISTS idx_textbook_section_textbook_id ON textbook_section_content (textbook_id);
          CREATE UNIQUE INDEX IF NOT EXISTS idx_textbook_section_unique_id ON textbook_section_content (textbook_id, section_id);
      """))
  ```

- [ ] **Step 5: 运行并验证测试通过**
  运行：`pytest backend/tests/test_kb_models.py -v`
  预期：PASS
  Ruff 格式化：`ruff check --fix && ruff format`

---

### Task 2: 阿里云百炼文档解析与大纲引导切片管道 (Ingestion Pipeline)

**Files:**
- Create: `backend/app/services/document_parser_service.py`
- Create: `backend/tests/test_document_parser.py`

- [ ] **Step 1: 编写文档解析与定位切片测试**
  在 `backend/tests/test_document_parser.py` 中验证文本物理切片逻辑：
  ```python
  from app.services.document_parser_service import locate_and_slice_sections
  
  def test_locate_and_slice_sections():
      md_text = "# 第一章 绪论\n1.1 什么是数据结构\n数据结构是计算机存储、组织数据的方式。\n1.2 算法分析\n算法分析指的是..."
      outline = {
          "chapters": [
              {
                  "chapter_number": 1,
                  "title": "第一章 绪论",
                  "sections": [
                      {"section_id": "sec_1_1", "title": "1.1 什么是数据结构"},
                      {"section_id": "sec_1_2", "title": "1.2 算法分析"}
                  ]
              }
          ]
      }
      sections = locate_and_slice_sections(md_text, outline)
      assert len(sections) == 2
      assert "数据结构是" in sections["sec_1_1"]
      assert "算法分析指" in sections["sec_1_2"]
  ```

- [ ] **Step 2: 运行测试确保其失败**
  运行：`pytest backend/tests/test_document_parser.py -v`
  预期：FAIL（模块不存在）

- [ ] **Step 3: 实现 `locate_and_slice_sections` 逻辑**
  在 `backend/app/services/document_parser_service.py` 中编写切片定位器：
  ```python
  import re
  
  def locate_and_slice_sections(markdown_text: str, outline: dict) -> dict[str, str]:
      sections_content = {}
      all_titles = []
      
      for ch in outline.get("chapters", []):
          for sec in ch.get("sections", []):
              all_titles.append((sec["section_id"], sec["title"]))
              
      # 根据出现在文章中的字符位置排序
      found_positions = []
      for sec_id, title in all_titles:
          idx = markdown_text.find(title)
          if idx != -1:
              found_positions.append((sec_id, title, idx))
              
      found_positions.sort(key=lambda x: x[2])
      
      for i, (sec_id, title, start_idx) in enumerate(found_positions):
          end_idx = found_positions[i+1][2] if i + 1 < len(found_positions) else len(markdown_text)
          sections_content[sec_id] = markdown_text[start_idx:end_idx].strip()
          
      return sections_content
  ```

- [ ] **Step 4: 接入阿里云 Docmind 客户端并封装异步解析管道**
  在 `backend/app/services/document_parser_service.py` 中编写 `parse_and_slice_pdf` 异步任务：
  ```python
  import asyncio
  from alibabacloud_docmind_api20220711.client import Client
  from alibabacloud_docmind_api20220711.models import SubmitDocStructureJobRequest
  
  async def parse_and_slice_pdf(pdf_path: str, textbook_id: str, db_session):
      # 1. 提交阿里云解析任务并等待 Markdown
      # 2. 调用大模型结构化提取大纲 outline JSON
      # 3. 调用 locate_and_slice_sections 切片
      # 4. 存入 database
      pass
  ```

- [ ] **Step 5: 运行测试并用 Ruff 格式化**
  运行：`pytest backend/tests/test_document_parser.py -v`
  预期：PASS
  Ruff：`ruff check --fix && ruff format`

---

### Task 3: 管理端 API 接口与路由实现 (FastAPI Routing)

**Files:**
- Create: `backend/app/api/admin_kb.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_admin_kb_api.py`

- [ ] **Step 1: 编写 API 接口测试用例**
  创建 `backend/tests/test_admin_kb_api.py`：
  ```python
  from fastapi.testclient import TestClient
  
  def test_get_textbooks_list(client: TestClient, admin_token_headers):
      response = client.get("/api/admin/knowledge-base/textbooks", headers=admin_token_headers)
      assert response.status_code == 200
  ```

- [ ] **Step 2: 运行测试确保失败**
  运行：`pytest backend/tests/test_admin_kb_api.py -v`
  预期：FAIL（HTTP 404）

- [ ] **Step 3: 编写 `backend/app/api/admin_kb.py` 路由**
  实现 `/upload`、`/textbooks`、`/textbooks/{id}/outline` 等接口：
  ```python
  from fastapi import APIRouter, Depends, UploadFile, File
  from app.api.admin import require_admin_user
  from app.database import create_session_dependency
  
  router = APIRouter(prefix="/api/admin/knowledge-base", tags=["admin-kb"])
  
  @router.post("/upload")
  async def upload_textbook(
      title: str,
      tags: str,
      file: UploadFile = File(...),
      current_user = Depends(require_admin_user)
  ):
      # 保存 PDF 并触发异步 parse 任务
      return {"id": "new_id", "title": title, "status": "processing"}
  ```

- [ ] **Step 4: 将新路由注册到 `backend/app/main.py`**
  ```python
  from app.api.admin_kb import router as admin_kb_router
  app.include_router(admin_kb_router)
  ```

- [ ] **Step 5: 验证 API 测试通过**
  运行：`pytest backend/tests/test_admin_kb_api.py -v`
  预期：PASS
  Ruff 格式化。

---

### Task 4: AI 创作与生成中心异步机制 (AIGC Task Runner)

**Files:**
- Modify: `backend/app/api/admin_kb.py`
- Modify: `backend/app/services/document_parser_service.py`
- Create: `backend/tests/test_aigc_creator.py`

- [ ] **Step 1: 编写 AI 大纲创作与内容异步生成测试**
  在 `backend/tests/test_aigc_creator.py` 中测试 `/generate-outline` 与大纲 Copilot 接口响应。

- [ ] **Step 2: 运行测试确保失败**
  运行：`pytest backend/tests/test_aigc_creator.py -v`
  预期：FAIL

- [ ] **Step 3: 在后端 API 中实现大纲生成与大纲 Copilot 接口**
  ```python
  @router.post("/generate-outline")
  async def generate_outline_from_prompt(prompt: str, tags: list[str]):
      # 调用 LLM structured_output 产出 outline JSON
      return {"id": "generated_id", "title": "...", "outline": outline}
  ```

- [ ] **Step 4: 实现异步大章节生成任务 `generate_textbook_contents_task`**
  在 `document_parser_service.py` 中完成逐小节串行生成的任务调度器：
  ```python
  async def generate_textbook_contents_task(textbook_id: str, db_session):
      # 逐个 Section 生成 2k-5k 字正文并保存
      pass
  ```

- [ ] **Step 5: 验证 AI 生成逻辑测试通过**
  运行：`pytest backend/tests/test_aigc_creator.py -v`
  预期：PASS
  Ruff 格式化。

---

### Task 5: 检索引导的 CAG 粗筛算法 (RRF Hybrid Search)

**Files:**
- Create: `backend/app/services/hybrid_search_service.py`
- Create: `backend/tests/test_hybrid_search.py`

- [ ] **Step 1: 编写 RRF 混合初筛检索测试**
  在 `backend/tests/test_hybrid_search.py` 中验证基于 pgvector + tsvector 排序打分。

- [ ] **Step 2: 运行测试确保失败**
  运行：`pytest backend/tests/test_hybrid_search.py -v`
  预期：FAIL

- [ ] **Step 3: 在 `backend/app/services/hybrid_search_service.py` 中实现 RRF SQL 执行逻辑**
  ```python
  from sqlmodel import Session, select
  
  def hybrid_search_textbooks(session: Session, query: str, limit: int = 15) -> list[dict]:
      # 执行 RRF 联合查询，捞出相似元数据教科书
      # 返回包含大纲 JSON 的列表
      pass
  ```

- [ ] **Step 4: 验证检索测试通过**
  运行：`pytest backend/tests/test_hybrid_search.py -v`
  预期：PASS
  Ruff 格式化。

---

### Task 6: 改造智能体流 (Intake, Path & Chapters Agents)

**Files:**
- Modify: `backend/app/orchestration/agents/learning_path_intake.py`
- Modify: `backend/app/orchestration/agents/learning_path.py`
- Modify: `backend/app/orchestration/agents/course_knowledge.py`
- Modify: `backend/tests/test_learning_path_agent_contract.py`

- [ ] **Step 1: 编写契约测试验证 `textbook_id` 注入课程节点**
  在 `test_learning_path_agent_contract.py` 中加入包含 `textbook_id` 的课程结构断言。

- [ ] **Step 2: 运行契约测试确保失败**
  运行：`pytest backend/tests/test_learning_path_agent_contract.py -v`
  预期：FAIL

- [ ] **Step 3: 改造 `learning_path_intake_agent` (草案 Agent)**
  调用 `hybrid_search_textbooks` 捞出 Top 15-20 本教材元数据及大纲，作为 candidate_textbooks 塞入大模型上下文。

- [ ] **Step 4: 改造 `learning_path_agent` 和 `course_knowledge_agent` (章节 Agent)**
  章节 Agent 增加依据名称反向校准 `textbook_id` 的容错逻辑，防止老路径崩溃。

- [ ] **Step 5: 验证全套智能体契约测试通过**
  运行：`pytest backend/tests/test_learning_path_agent_contract.py -v`
  预期：PASS
  Ruff 格式化。

---

### Task 7: 改造 Markdown Agent 为细粒度 CAG 正文塞入

**Files:**
- Modify: `backend/app/orchestration/agents/course_resources.py`
- Modify: `backend/tests/test_course_resource_agent_contract.py`

- [ ] **Step 1: 编写测试用例，断言 Markdown 生成时输入中带有教材小节原文**
  在 `test_course_resource_agent_contract.py` 中验证入参包含小节正文。

- [ ] **Step 2: 运行测试确保失败**
  运行：`pytest backend/tests/test_course_resource_agent_contract.py -v`
  预期：FAIL

- [ ] **Step 3: 改造 `section_markdown_agent`**
  修改 `backend/app/orchestration/agents/course_resources.py`，根据 `textbook_id` 和 `section_id` 精准拉取 `TextbookSectionContent.content`，将其放入 System Message 最前面作为 CAG context。

- [ ] **Step 4: 运行测试验证大模型通过教材正文成功提炼生成 Markdown**
  运行：`pytest backend/tests/test_course_resource_agent_contract.py -v`
  预期：PASS
  Ruff 格式化。

---

### Task 8: 前端管理员界面与大纲微调编辑器 (Frontend UI)

**Files:**
- Create: `frontend/src/pages/admin/KnowledgeBasePage.tsx`
- Create: `frontend/src/pages/admin/OutlineEditor.tsx`
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/pages/admin/__tests__/KnowledgeBasePage.test.tsx`

- [ ] **Step 1: 编写前端大纲编辑器与状态列表测试用例**
  创建 `frontend/src/pages/admin/__tests__/KnowledgeBasePage.test.tsx` 验证树形节点修改渲染。

- [ ] **Step 2: 运行测试确保失败**
  运行：`npm run test frontend/src/pages/admin/__tests__/KnowledgeBasePage.test.tsx`
  预期：FAIL

- [ ] **Step 3: 实现 `KnowledgeBasePage.tsx` 管理端主页面**
  包括 PDF 拖拽上传、AIGC 创作表单、任务进度展示。支持 OKLCH 配色与暗色模式。

- [ ] **Step 4: 实现 `OutlineEditor.tsx` 树形大纲微调编辑器**
  利用递归渲染和 `onBlur` 失焦即时更新，嵌入大纲 AI Copilot 侧边栏，支持调用 `npm run gen:api` 产生的 types。

- [ ] **Step 5: 验证前端编译与测试通过**
  运行：`npm run gen:api`
  运行：`npm run test frontend/src/pages/admin/__tests__/KnowledgeBasePage.test.tsx`
  预期：PASS
  Biome 格式化：`npx biome check --write`

---

### Task 9: 全链路集成调试与前端类型同步

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/pages/branch/BranchPage.tsx`
- Modify: `frontend/src/pages/leaf/LeafPage.tsx`

- [ ] **Step 1: 运行全栈 API 契约生成**
  运行：`npm run gen:api` 并核对 `src/types/api.ts` 中的路径定义。

- [ ] **Step 2: 改造 BranchPage.tsx 与 LeafPage.tsx 接收 textbook_id 锚点**
  确保点亮和进入详情时正确携带 `textbook_id`，若缺失则通过旧版机制或自动匹配做平滑降级。

- [ ] **Step 3: 运行全栈打包校验**
  前端运行：`npm run build`
  后端运行：`pytest`
  检查 Biome 与 Ruff 格式，确保零错误残留。
  
- [ ] **Step 4: Commit**
  ```bash
  git add -A
  git commit -m "feat: complete full-stack postgres RAG/CAG integration and admin creator"
  ```
