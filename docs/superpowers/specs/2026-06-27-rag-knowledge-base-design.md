# RAG 知识库与多智能体教材集成设计规格说明书

本设计文档旨在为“一棵树 (OneTree)”系统引入一套基于 **PostgreSQL 特性 (JSONB + pgvector + tsvector)** 的原生 RAG/CAG 教材集成方案。本方案通过**“检索引导的 CAG（Retrieval-guided CAG）”**机制，消除原智能体链中依靠“大模型参数盲猜”生成课程及大纲的缺陷，将所有推荐与生成限制在管理员/教师审核通过、已发布的高质量教材范围内。

---

## 1. 项目愿景与使用流程 (Project Vision & Complete User Flows)

### 1.1 教师/管理员端流程与预期效果
1. **教材发现与上传阶段**：
   * 管理员登录后台，访问 `/admin/knowledge-base`。
   * 管理员说一句话，Agent 自行到网上检索适合的教材来源；管理员也可以直接上传 PDF 教材。
   * 提交后，教材进入“待整理”或“正在解析”状态。
   * **后台自动切片管道**：如果 PDF 页数超过 200 页或大小超过 30MB，系统在内存中自动使用 Python 进行分片处理，异步调用阿里云百炼文档解析 API，获取高保真 Markdown 全文。
2. **Agent 整理阶段**：
   * Agent 将检索到的教材或上传的 PDF 整理到小节正文级别，形成可校对的大纲和正文切片。
   * 整理结果进入可视化的树形大纲编辑器（TOC Editor），供管理员人工校对。
3. **校对与发布阶段**：
   * 管理员确认大纲与正文切片后，点击“发布”。
   * 发布后的教材进入已发布知识库，成为后续草案智能体、路径智能体和章节生成的唯一来源。
   * 对于 PDF 解析出的教材，系统根据结构化大纲自动在 Markdown 全文里定位并切片小节正文，存入 `textbook_section_content`。

### 1.2 学生端流程与预期效果
1. **画像收集与推荐草稿**：
   * 学生完成初始画像对话后，表达了想学“后端开发”的意图。
   * 系统只从已发布知识库中进行混合检索，粗筛出匹配的 Top 15-20 本教材元数据（书名、标签）。
   * **`learning_path_intake_agent` (草案 Agent)** 在聊天框中以卡片形式输出课程主题 + 来源教材，推荐范围严格限制在已发布知识库内。
2. **草案微调与路径规划**：
   * 学生在对话框中反馈：“我不想学 Django，帮我换成 FastAPI”。
   * 草案 Agent 在已发布知识库中匹配到对应教材后更新推荐清单，并在下方显示「确认并生成路径」与「修改画像」按钮。
   * 学生点击「确认并生成路径」，**`learning_path_agent`** 将其编排为课程规划，每个课程节点回写并绑定对应的知识库来源。
3. **确定性章节展开**：
   * 学生进入“分支页（BranchPage）”查看路径，点击课程进入“展叶页（LeafPage）”。
   * **`course_knowledge_agent` (章节 Agent)** 直接从数据库读取对应教材的 `outline` JSON 渲染出目录，不经过任何大模型脑补。
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

### 3.2 后续阶段 AI 创作与生成端 API
* 本节能力不属于第一期主线，仅用于后续阶段。
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
* **输入规格 (`OrchestrationState`)**：画像及已发布知识库中检索出的 Top 15-20 本教材元数据 + 大纲 JSON。
* **输出结构 (`LearningPathIntakeOutput`)**：大模型决策后的课程推荐草稿。

### 4.2 `learning_path_agent` (路径 Agent)
* **输出结构 (`UserYearLearningPath` 保存格式)**：强绑定已发布知识库中的 `textbook_id` 与来源信息。

### 4.3 `course_knowledge_agent` (章节 Agent)
* **输入规格**：`course_node_id` & `textbook_id`。
* **逻辑**：按课程名称回到已发布知识库定位对应教材与大纲，不凭空生成课程内容。

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

## 8. 后续阶段：AI 教材创作与生成中心

AI 创作教材、`/generate-outline`、`/generate-content`、正文自动创作与 Outline Copilot 协同微调不属于第一期主线。第一期只保证“找教材/上传教材 -> 整理 -> 校对 -> 发布 -> 基于已发布知识库推荐与生成”闭环成立。

---

## 9. 管理端与学生端前端界面设计

遵循 `AGENTS.md` 中 LXGW WenKai 字体规范与暗色模式/间距 Scale 要求。

### 9.1 管理员页面 (`/admin/knowledge-base`)
* **教材列表与状态看板 (`TextbookList.tsx`)**：展示检索来源、上传队列、整理状态、校对状态与发布状态。
* **可视化大纲编辑器 (`OutlineEditor.tsx`)**：
  提供树状大纲展示，支持折叠/展开、直接点击修改，用于管理员人工校对教材整理结果。

---

## 10. 修改代码硬性约束与注意事项 (Coding Safeguards)

### 10.1 现有契约测试 (Contract Tests) 兼容
* 在为 `course_nodes` 添加 `textbook_id` 属性时，必须在对应的 Pydantic 模型中将其定义为 **`Optional` 字段，或提供默认值 `None`**，防止破坏 CI/pytest 自动化测试。

### 10.2 全栈 API 类型自动生成
* 每次修改了后端的 Pydantic 结构或 API 返回结构后，**必须立即在前端目录下运行 `npm run gen:api`**，以编译出最新的 `src/types/api.ts`。

### 10.3 Biome 与 Ruff 代码格式化
* 修改后端 Python 后，使用 `ruff check --fix` 和 `ruff format`；修改前端 TSX/TS 后，使用 `npx biome check --write` 格式化。
