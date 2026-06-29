# RAG 知识库与多智能体教材集成设计规格说明书

本设计文档旨在为“一棵树 (OneTree)”系统引入一套基于 **PostgreSQL 特性 (JSONB + pgvector + tsvector)** 的原生 RAG/CAG 教材集成方案。本方案通过**“检索引导的 CAG（Retrieval-guided CAG）”**机制，消除原智能体链中依靠“大模型参数盲猜”生成课程及大纲的缺陷，将所有推荐与生成限制在管理员/教师审核通过的高质量教材范围内。

---

## 1. 项目愿景与使用流程 (Project Vision & Complete User Flows)

### 1.1 教师/管理员端流程与预期效果
1. **教材上传阶段**：
   * 教师登录后台，访问 `/admin/knowledge-base`。
   * 点击“上传教材”，在弹窗中选择 PDF 文件，输入教材名称（如《Python高级Web开发》），并添加专业标签（如：`["后端开发", "软件工程", "大三"]`）。
   * 提交后，教材进入“正在解析”状态。
   * **后台自动切片管道**：如果 PDF 页数超过 200 页或大小超过 30MB，系统在内存中自动使用 Python 进行分片处理，异步调用阿里云百炼文档解析 API，获取高保真 Markdown 全文。
2. **AI 从零创作生成阶段（AIGC 教材）**：
   * 如果教师手中没有 PDF 教材，可以直接点击“AI 创作教材”。
   * 输入创作 prompt（例如：“面向大三学生，生成一本 5 章的 Rust 智能合约开发教材”）。
   * 系统调用 AI，利用结构化输出快速生成推荐的大纲目录 JSON 并在网页呈现。
3. **大纲微调与定位阶段**：
   * 无论是 PDF 解析出来的目录还是 AI 创作出来的目录，均进入可视化的树形大纲编辑器（TOC Editor）。
   * 教师可以使用 **“AI 目录副驾驶 (Outline Copilot)”** 发出修改指令（如：“在这章增加两个关于安全漏洞的小节”），AI 自动修改对应的 JSON 目录树。
   * 确认大纲后，教师点击“生成教材内容”。系统启动后台异步任务，针对大纲中的每一个叶子小节，自动调用 LLM 撰写 2000-5000 字的高质量教学正文，并实时显示进度百分比。
   * 对于 PDF 解析出的教材，系统根据结构化大纲自动在 Markdown 全文里定位并切片小节正文，存入 `textbook_section_content`。

### 1.2 学生端流程与预期效果
1. **画像收集与推荐草稿**：
   * 学生完成初始画像对话后，表达了想学“后端开发”的意图。
   * 系统通过混合检索，从数据库粗筛出匹配的 Top 15-20 本教材元数据（书名、标签）。
   * **`learning_path_intake_agent` (草案 Agent)** 在聊天框中以卡片形式输出推荐课程草案（大模型整篇读入这 15-20 本教材的完整大纲作为上下文进行全局规划，绝不猜错书名）。
2. **草案微调与路径规划**：
   * 学生在对话框中反馈：“我不想学 Django，帮我换成 FastAPI”。
   * 草案 Agent 在候选教材中匹配到《FastAPI 高效开发指南》，在聊天框中更新推荐清单，并在下方显示「确认并生成路径」与「修改画像」按钮。
   * 学生点击「确认并生成路径」，**`learning_path_agent`** 将其编排为 4 年级课程规划，每个课程节点内置对应的 `textbook_id`。
3. **确定性章节展开**：
   * 学生进入“分支页（BranchPage）”查看 4 年路径，点击课程进入“展叶页（LeafPage）”。
   * **`course_knowledge_agent` (章节 Agent)** 直接从数据库读取对应的 `outline` JSON 渲染出目录，不经过任何大模型脑补，生成大纲是 **100% 确定且精准的**。
4. **Markdown 原文精读生成**：
   * 学生点击学习“第一章第二节：依赖注入”。
   * 触发 **`section_markdown_agent`**，后端直接查询该教材第一章该小节的完整正文（`textbook_section_content.content`，约 2000-5000 字），整篇塞入大模型上下文。
   * 由于精准定位到小节正文，避免了长达数万字的整章文本塞入，**彻底规避了大模型超时与 Token 浪费问题**。
   * 大模型输出的高保真 Markdown 文档有据可查，保证了教学内容的权威性与严肃性。

---

## 2. 数据库设计 (PostgreSQL Schema)

### 2.1 SQL DDL 结构
```sql
-- 启用向量扩展及模糊查询扩展
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 教材主表
CREATE TABLE textbook (
    id VARCHAR(64) PRIMARY KEY,
    title VARCHAR(256) NOT NULL,
    author VARCHAR(128),
    tags JSONB DEFAULT '[]',
    outline JSONB DEFAULT '{}',
    status VARCHAR(32) NOT NULL DEFAULT 'processing',
    source_link TEXT,
    embedding VECTOR(1536), -- 用于教材元数据的初筛检索 (对应千问/OpenAI embedding 维度)
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
);

-- 教材小节内容表 (颗粒度下沉至小节以保障 CAG 性能)
CREATE TABLE textbook_section_content (
    id VARCHAR(64) PRIMARY KEY,
    textbook_id VARCHAR(64) REFERENCES textbook(id) ON DELETE CASCADE,
    chapter_number INTEGER NOT NULL,
    section_id VARCHAR(64) NOT NULL,
    title VARCHAR(256) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
);

-- 建立索引
CREATE INDEX idx_textbook_title ON textbook (title);
CREATE INDEX idx_textbook_status ON textbook (status);
CREATE INDEX idx_textbook_outline_gin ON textbook USING gin (outline);
CREATE INDEX idx_textbook_embedding_hnsw ON textbook USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_textbook_section_textbook_id ON textbook_section_content (textbook_id);
CREATE UNIQUE INDEX idx_textbook_section_unique_id ON textbook_section_content (textbook_id, section_id);
```

### 2.2 SQLModel ORM 声明
```python
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field, Column
from sqlalchemy.dialects.postgresql import JSONB
import sqlalchemy as sa

# 动态配置向量维度防止 API 升级导致维数不兼容
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIMENSION", "1536"))

class Textbook(SQLModel, table=True):
    """教材主表（存储元数据及大纲结构）"""
    __tablename__ = "textbook"

    id: str = Field(primary_key=True, index=True)
    title: str = Field(index=True, nullable=False, description="教材书名")
    author: Optional[str] = Field(default=None, description="作者")
    tags: List[str] = Field(default_factory=list, sa_column=Column(JSONB), description="专业/方向标签")
    outline: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB), description="教材大纲目录结构 JSON")
    status: str = Field(default="processing", index=True, description="解析状态: pending_approval/processing/success/failed")
    source_link: Optional[str] = Field(default=None, description="下载/采购来源链接")
    embedding: Optional[List[float]] = Field(
        default=None, 
        sa_column=Column(sa.dialects.postgresql.ARRAY(sa.Float)), 
        description="教材元数据向量"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

class TextbookSectionContent(SQLModel, table=True):
    """教材小节内容表（分节细粒度存储，完美适配 CAG 上下文限制）"""
    __tablename__ = "textbook_section_content"

    id: str = Field(primary_key=True, index=True)
    textbook_id: str = Field(foreign_key="textbook.id", index=True, nullable=False)
    chapter_number: int = Field(index=True, nullable=False, description="章节编号")
    section_id: str = Field(index=True, nullable=False, description="小节 ID (对应大纲中的节点 ID)")
    title: str = Field(nullable=False, description="小节名称")
    content: str = Field(sa_column=sa.Column(sa.Text, nullable=False), description="小节完整正文内容")
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
```

---

## 3. 后端 API 路由设计与接口规范 (FastAPI Endpoints)

新增以下后台 API 路由，确保 `admin` 与 `teacher` 权限可以访问（复用已有的 `require_admin_user`）：

### 3.1 教材上传与普通管理
* **`POST /api/admin/knowledge-base/upload`**：上传 PDF 教材。
* **`GET /api/admin/knowledge-base/textbooks`**：获取教材元数据与大纲列表。
* **`GET /api/admin/knowledge-base/textbooks/{id}`**：获取特定教材大纲及其对应的章节列表。
* **`PUT /api/admin/knowledge-base/textbooks/{id}/outline`**：管理员/教师微调大纲 JSON。
* **`POST /api/admin/knowledge-base/textbooks/{id}/approve`**：审批通过 `admin_kb_agent` 搜集上来的待审教材并触发解析。
* **`DELETE /api/admin/knowledge-base/textbooks/{id}`**：物理删除教材以及联级删除章节正文。

### 3.2 AI 创作与生成端 API (新增)
* **`POST /api/admin/knowledge-base/generate-outline`**
  * **请求体 (JSON)**:
    ```json
    {
      "prompt": "面向大二学生，生成一本 4 章的 React Native 开发基础教材",
      "tags": ["前端", "移动端开发"]
    }
    ```
  * **返回结构 (200 OK)**:
    ```json
    {
      "id": "tb_generated_uuid_789",
      "title": "React Native 开发基础教程",
      "outline": {
        "chapters": [
          {
            "chapter_number": 1,
            "title": "第一章 React Native 架构与起步",
            "sections": [
              { "section_id": "sec_1_1", "title": "1.1 跨平台渲染引擎原理" },
              { "section_id": "sec_1_2", "title": "1.2 开发环境搭建与 Hello World" }
            ]
          }
        ]
      }
    }
    ```
* **`POST /api/admin/knowledge-base/textbooks/{id}/generate-content`**
  * **逻辑**：异步启动后台任务创作该大纲的全部正文，将其存入 `TextbookSectionContent` 中，返回 `task_id`。
  * **返回结构 (202 Accepted)**: `{ "status": "processing", "task_id": "task_content_gen_999" }`
* **`GET /api/admin/knowledge-base/textbooks/{id}/generation-progress`**
  * **返回结构**:
    ```json
    {
      "textbook_id": "tb_generated_uuid_789",
      "progress_percentage": 45.5,
      "status": "generating",
      "current_section_title": "1.2 开发环境搭建与 Hello World"
    }
    ```

---

## 4. 智能体输入输出规格与 CAG 接口协议 (Agents Input/Output & CAG Protocols)

### 4.1 `learning_path_intake_agent` (草案 Agent)
* **输入规格 (`OrchestrationState`)**：画像及 Top 15-20 本候选教材元数据 + 大纲 JSON。
* **输出结构 (`LearningPathIntakeOutput`)**：大模型决策后的课程推荐草稿。

### 4.2 `learning_path_agent` (路径 Agent)
* **输出结构 (`UserYearLearningPath` 保存格式)**：强绑定对应的 `textbook_id`。

### 4.3 `course_knowledge_agent` (章节 Agent)
* **输入规格**：`course_node_id` & `textbook_id`。
* **降级与防崩溃兼容逻辑**：按课程名称检索教材库补全 `textbook_id`，若无可绑定教材则降级为旧版大模型参数生成。

### 4.4 `section_markdown_agent` (小节 Markdown Agent)
* **输入规格**：小节正文（约 2000-5000 字）。
* **输出结构**：格式化的教学 Markdown 文本。

---

## 5. PostgreSQL 检索引导的 CAG 核心检索算法 (RRF Hybrid Search)

对于草案 Agent 匹配教材，后端在启动图（Graph）执行前，调用 SQL 拼接全文检索与向量相似度完成 Top 15-20 的初筛：

```sql
WITH vector_search AS (
    SELECT id, title, outline,
           ROW_NUMBER() OVER (ORDER BY embedding <=> :query_embedding) as rank
    FROM textbook
    WHERE embedding IS NOT NULL AND status = 'success'
    LIMIT 30
),
fts_search AS (
    SELECT id, title, outline,
           ROW_NUMBER() OVER (ORDER BY ts_rank(to_tsvector('chinese', title || ' ' || tags::text), to_tsquery('chinese', :query_fts)) DESC) as rank
    FROM textbook
    WHERE to_tsvector('chinese', title || ' ' || tags::text) @@ to_tsquery('chinese', :query_fts) AND status = 'success'
    LIMIT 30
)
SELECT COALESCE(v.id, f.id) as id,
       COALESCE(v.title, f.title) as title,
       COALESCE(v.outline, f.outline) as outline,
       (1.0 / (60.0 + COALESCE(v.rank, 100)) + 1.0 / (60.0 + COALESCE(f.rank, 100))) as rrf_score
FROM vector_search v
FULL OUTER JOIN fts_search f ON v.id = f.id
ORDER BY rrf_score DESC
LIMIT :limit;
```

---

## 6. 教材自动切片管道设计 (LLM-Guided Splitter)

系统采用 **“大模型结构化大纲 + Python 物理定位”** 管道进行切分：
1. **大纲语义提取**：提取 PDF 目录页送入大模型，使用强类型约束输出目录树大纲 JSON 标题清单。
2. **物理字符索引定位**：后端 Python 直接在 Markdown 全文中，以标题为关键词查找位置。
3. **入库**：切片后的小节文本与 `TextbookSectionContent` 绑定入库，规避大模型输出 Token 溢出瓶颈，保障数据完整。

---

## 7. 性能优化与高并发保障 (CAG Performance Optimizations)

### 7.1 LLM 缓存层设计 (KV Cache / Prompt Caching)
* **草案 Agent** 触发百炼的 **Prompt Cache**，使 TTFT 降低 80% 以上。
* **Markdown Agent** 自动对其进行 **KV 缓存**，极速响应同一章节内各个小节的后续生成请求。

---

## 8. 管理端 AI 教材创作与生成中心设计 (AIGC Center) (新增)

为了让管理员能直接利用大模型能力生成完整的教学资源，设计如下 AI 创作中心：

### 8.1 创作交互工作流
1. **初始化大纲**：管理员在 `/admin/knowledge-base` 点击 "AI 创作"，输入提示词与标签。调用 `/generate-outline` 生成初始大纲 JSON。
2. **人工审校/AI 协同微调 (Outline Copilot)**：
   * 大纲渲染在 `OutlineEditor.tsx` 中。
   * 提供 AI 大纲侧边栏。教师可选择某个大纲节点并发出指令（如：“在这章最后插入两个关于性能分析的知识点”）。
   * 目录 AI 助手（Outline Copilot）使用 structured_output 读取并重构此大纲 JSON 返回前端，渲染更新。
3. **正文异步生成任务 (Task Runner)**：
   * 点击“AI 生成内容”按钮，调用 `/generate-content` 接口。
   * 后端通过 `BackgroundTasks` 分发任务 `generate_textbook_contents_task(textbook_id)`。
   * **循环执行生成**：对于大纲中每一个小节：
     ```python
     # 异步循环，按节依次使用 LLM 生成正文
     for ch in outline["chapters"]:
         for sec in ch["sections"]:
             if exists_in_db(textbook_id, sec["section_id"]):
                 continue
             content = await run_llm_section_generation(textbook_title, ch["title"], sec["title"])
             save_to_section_content(textbook_id, ch["chapter_number"], sec["section_id"], sec["title"], content)
             update_progress_percentage()
     ```
   * 大语言模型只需单次输出 2000-5000 字的小节正文，完全处于安全 Output Token 限制内，避免任务由于输出超限崩溃。

---

## 9. 管理端与学生端前端界面设计

遵循 `AGENTS.md` 中 LXGW WenKai 字体规范与暗色模式/间距 Scale 要求。

### 9.1 管理员页面 (`/admin/knowledge-base`)
* **教材列表与状态看板 (`TextbookList.tsx`)**：展示解析队列与 AI 生成任务的实时进度条。
* **可视化大纲编辑器 (`OutlineEditor.tsx`)**：
  提供树状大纲展示，支持折叠/展开、直接点击修改、以及 Outline Copilot 侧边栏交互。

---

## 10. 修改代码硬性约束与注意事项 (Coding Safeguards)

### 10.1 现有契约测试 (Contract Tests) 兼容
* 在为 `course_nodes` 添加 `textbook_id` 属性时，必须在对应的 Pydantic 模型中将其定义为 **`Optional` 字段，或提供默认值 `None`**，防止破坏 CI/pytest 自动化测试。

### 10.2 全栈 API 类型自动生成
* 每次修改了后端的 Pydantic 结构或 API 返回结构后，**必须立即在前端目录下运行 `npm run gen:api`**，以编译出最新的 `src/types/api.ts`。

### 10.3 Biome 与 Ruff 代码格式化
* 修改后端 Python 后，使用 `ruff check --fix` 和 `ruff format`；修改前端 TSX/TS 后，使用 `npx biome check --write` 格式化。
