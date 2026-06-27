# RAG 知识库与多智能体教材集成设计规格说明书

本设计文档旨在为“一棵树 (OneTree)”系统引入一套基于 **PostgreSQL 特性 (JSONB + pgvector + tsvector)** 的原生 RAG/CAG 教材集成方案。本方案通过**“检索引导的 CAG（Retrieval-guided CAG）”**机制，消除原智能体链中依靠“大模型参数盲猜”生成课程及大纲的缺陷，将所有推荐与生成限制在管理员/教师审核通过的高质量教材范围内。

---

## 1. 项目愿景与使用流程 (Project Vision & Complete User Flows)

### 1.1 教师/管理员端流程与预期效果
1. **教材上架阶段**：
   * 教师登录后台，访问 `/admin/knowledge-base`。
   * 点击“上传教材”，在弹窗中选择 PDF 文件，输入教材名称（如《Python高级Web开发》），并添加专业标签（如：`["后端开发", "软件工程", "大三"]`）。
   * 提交后，教材进入“正在解析”状态。后台异步调用阿里云百炼文档解析 API，将 PDF 解析为结构化的 Markdown 文本，并根据大纲自动切分章节，存储至 PostgreSQL 中。
2. **大纲微调阶段**：
   * 解析成功后，教师点击“编辑大纲”，弹出一个可视化的树形大纲编辑器（TOC Editor）。
   * 教师可以预览大模型解析出的第 1 章至第 N 章的大纲结构。如果发现某节标题（如“1.2 FastApi基础”）解析有 OCR 误差，可以直接在双击修改为“1.2 FastAPI 核心概念”，拖动节点调整顺序，点击保存后直接更新数据库大纲 JSON。
3. **教材自主采购队列（KB Agent 审批）**：
   * 当有学生在前端聊天框中请求了知识库目前尚未覆盖的主题（如“Flutter移动开发”）时，后台触发 **`admin_kb_agent`**。
   * KB Agent 自动联网检索，找到公开优质的《Flutter 开发实战 PDF》和目录大纲，以 `pending_approval` 状态新增至教师后台的“待审采购教材”列表中，并显示推荐理由和下载来源。
   * 教师在后台点击“同意采购”，系统自动执行下载、解析、切片并发布上线。

### 1.2 学生端流程与预期效果
1. **画像收集与推荐草稿**：
   * 学生完成初始画像对话后，表达了想学“后端开发”的意图。
   * 系统粗筛出知识库中与“后端开发”相关的 Top 15-20 本教材大纲。
   * **`learning_path_intake_agent` (草案 Agent)** 在聊天框中以精美的卡片形式输出推荐课程草案（全部取材于初筛的教材大纲）。
2. **草案微调与路径规划**：
   * 学生在对话框中打字反馈：“我不想学 Django，帮我换成 FastAPI”。
   * 草案 Agent 再次在候选教材中匹配到《FastAPI 高效开发指南》，在聊天框中动态更新推荐清单，并在下方显示「确认并生成路径」与「修改画像」按钮。
   * 学生点击「确认并生成路径」，**`learning_path_agent`** 将其编排为 4 年级课程规划，生成的每个课程节点内置对应的 `textbook_id`。
3. **确定性章节展开**：
   * 学生进入“分支页（BranchPage）”查看 4 年路径，点击《FastAPI 高效开发指南》进入“展叶页（LeafPage）”。
   * **`course_knowledge_agent` (章节 Agent)** 触发运行。它直接从数据库读取对应的 `outline` JSON 渲染出目录，不经过任何大模型脑补，生成大纲是 **100% 确定且精准的**。
4. **Markdown 原文精读生成**：
   * 学生点击学习“第一章第二节：依赖注入”。
   * 触发 **`section_markdown_agent`**，后端直接查询该教材第一章的完整正文（`TextbookChapter.content`），整篇塞入大模型上下文。
   * 大模型输出的高保真 Markdown 文档有据可查，严格尊重教材原文，保证了教学内容的权威性与严肃性。

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

-- 教材章节内容表
CREATE TABLE textbook_chapter (
    id VARCHAR(64) PRIMARY KEY,
    textbook_id VARCHAR(64) REFERENCES textbook(id) ON DELETE CASCADE,
    chapter_number INTEGER NOT NULL,
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
CREATE INDEX idx_textbook_chapter_textbook_id ON textbook_chapter (textbook_id);
CREATE UNIQUE INDEX idx_textbook_chapter_unique_num ON textbook_chapter (textbook_id, chapter_number);
```

### 2.2 SQLModel ORM 声明
```python
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field, Column
from sqlalchemy.dialects.postgresql import JSONB

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
    embedding: Optional[List[float]] = Field(default=None, sa_column=Column(JSONB), description="教材元数据向量")
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

class TextbookChapter(SQLModel, table=True):
    """教材章节内容表（按章切割存储，用于 CAG 生成）"""
    __tablename__ = "textbook_chapter"

    id: str = Field(primary_key=True, index=True)
    textbook_id: str = Field(foreign_key="textbook.id", index=True, nullable=False)
    chapter_number: int = Field(index=True, nullable=False, description="章节编号")
    title: str = Field(nullable=False, description="章节名称")
    content: str = Field(sa_column=Column(sa.Text, nullable=False), description="章节完整 Markdown 内容")
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
```

---

## 3. 后端 API 路由设计与接口规范 (FastAPI Endpoints)

新增以下后台 API 路由，确保 `admin` 与 `teacher` 权限可以访问（复用已有的 `require_admin_user`）：

### 3.1 教材上传
* **`POST /api/admin/knowledge-base/upload`**
  * **请求体 (Form-Data)**:
    * `file`: UploadFile (PDF)
    * `title`: str (书名)
    * `tags`: str (JSON 格式标签数组, 如 `["前端", "React"]`)
  * **返回结构 (201 Created)**:
    ```json
    {
      "id": "tb_uuid_123456",
      "title": "React 进阶技术指南",
      "status": "processing",
      "created_at": "2026-06-27T06:00:00Z"
    }
    ```

### 3.2 教材与大纲列表获取
* **`GET /api/admin/knowledge-base/textbooks`**
  * **返回结构**:
    ```json
    [
      {
        "id": "tb_uuid_123456",
        "title": "React 进阶技术指南",
        "author": "张三",
        "tags": ["前端", "React"],
        "status": "success",
        "source_link": null,
        "created_at": "2026-06-27T06:00:00Z"
      }
    ]
    ```

### 3.3 大纲微调更新
* **`PUT /api/admin/knowledge-base/textbooks/{id}/outline`**
  * **请求体 (JSON)**:
    ```json
    {
      "outline": {
        "chapters": [
          {
            "chapter_number": 1,
            "title": "第一章 React 核心设计理念",
            "sections": [
              { "title": "1.1 Virtual DOM 机制" },
              { "title": "1.2 Fiber 架构深入" }
            ]
          }
        ]
      }
    }
    ```
  * **返回结构**: `{ "status": "ok", "message": "大纲已成功更新并生效" }`

### 3.4 待审教材审批
* **`POST /api/admin/knowledge-base/textbooks/{id}/approve`**
  * **返回结构**: `{ "status": "ok", "message": "已审批通过，开始下载解析" }`

### 3.5 删除教材
* **`DELETE /api/admin/knowledge-base/textbooks/{id}`**
  * **返回结构 (204 No Content)**: 无返回体

---

## 4. 智能体输入输出规格与 CAG 接口协议 (Agents Input/Output & CAG Protocols)

在多智能体 Graph 运行中，各 Worker Agent 之间的输入、输出以及持久化机制进行了深度绑定：

```
OrchestrationState 
  ├── 搭载用户画像 (profile)
  ├── 检索初筛召回教材大纲列表 ─► (草案 Agent 的 Context 塞入)
  ├── 产出学习路径草案 (learning_path_intake)
  └── 点亮路径课程 ─► 读取指定教材章节内容 ─► (Markdown Agent 的 Context 塞入)
```

### 4.1 `learning_path_intake_agent` (草案 Agent)
* **输入规格 (`OrchestrationState`)**:
  * `profile`: 用户画像数据。
  * `query`: 用户的个性化学习诉求（如：“我想重点学 Python 后端开发”）。
  * `candidate_textbooks`: **从数据库检索过滤出的 Top 15-20 本教材元数据 + 大纲 JSON**（后端在将 State 传入图前预先装载，作为 CAG 上下文）。
* **大模型 System Prompt / 契约约束**:
  * 必须仅在 `candidate_textbooks` 列出的书目和大纲结构中进行挑选。
  * 禁止推荐任何在上下文中不存在的教材。
* **输出结构 (`LearningPathIntakeOutput`)**:
  ```json
  {
    "type": "learning_path_intake",
    "status": "draft",
    "grade_year": "year_3",
    "grade_name": "大三",
    "learning_topic": "Python后端开发",
    "courses": [
      {
        "title": "Python高级Web开发",
        "purpose": "掌握 FastAPI 和 Django 核心框架原理"
      }
    ],
    "recommendation_reasons": ["依据画像中对高性能API的需求，推荐FastAPI教材"],
    "risk_warnings": []
  }
  ```

### 4.2 `learning_path_agent` (路径 Agent)
* **输入规格**:
  * `learning_path_intake`: 经过学生确认（`status="confirmed"`）的教材推荐清单。
* **输出结构 (`UserYearLearningPath` 保存格式)**:
  在 `path_data` 的 `course_nodes` 中为每个课程节点强绑定对应的 `textbook_id`：
  ```json
  {
    "grade_plans": {
      "year_3": {
        "course_nodes": [
          {
            "course_node_id": "course-python-web",
            "course_or_chapter_theme": "Python高级Web开发",
            "textbook_id": "tb_uuid_123456",
            "status": "current",
            "has_outline": true,
            "time_arrangement": {
              "semester_scope": "上学期",
              "duration": "8周"
            }
          }
        ]
      }
    }
  }
  ```

### 4.3 `course_knowledge_agent` (章节 Agent)
* **输入规格**:
  * `course_node_id`: 学生点亮的课程节点 ID。
  * `textbook_id`: 绑定该课程的教材 ID。
* **业务逻辑 (不经过 LLM 盲猜)**:
  直接根据 `textbook_id` 从数据库 `Textbook` 表查询，并返回其 `outline` 大纲字段：
  ```python
  # 章节 Agent 直接读取，不执行大模型推理
  textbook = session.exec(select(Textbook).where(Textbook.id == textbook_id)).first()
  return {"outline_data": textbook.outline}
  ```

### 4.4 `section_markdown_agent` (小节 Markdown Agent)
* **输入规格**:
  * `course_node_id` & `chapter_section_id`。
  * `chapter_content`: **查询 `TextbookChapter` 表获取的整章 Markdown 原文（约 1-3 万字）**。
* **大模型 System Prompt 约束**:
  * “你正在生成教学文档。你的输入中附带了《教材章节原文》。你生成的 Markdown 教学内容必须严格基于原文中阐述的知识点和逻辑结构，禁止编造或脑补任何非原文提供的概念或 API。保证内容格式精美且有据可依。”
* **输出结构**: 格式化的教学 Markdown 文本。

### 4.5 `admin_kb_agent` (自主采购智能体)
* **输入规格**:
  * `missing_topic`: 学生请求但目前知识库无法覆盖的冷启动技术方向（如：“我想学 Rust 智能合约开发”）。
* **逻辑**:
  * 调用百炼 `get_search_worker_llm()`，使用内置 Search Tool 寻找优质公开 PDF 或官方 GitBook。
  * 解析出临时的大纲 JSON 和源下载地址。
* **输出结构 (待审教材实体存入数据库)**:
  `Textbook` 实体被插入，状态为 `status="pending_approval"`，等待管理员审核通过。

---

## 5. PostgreSQL 检索引导的 CAG 核心检索算法 (RRF Hybrid Search)

对于草案 Agent 匹配教材，后端在启动图（Graph）执行前，调用本 SQL 完成 Top 15-20 的初筛，并填充到 `candidate_textbooks` 状态中：

```sql
WITH vector_search AS (
    -- 1. 向量相似度初筛 (余弦相似度)
    SELECT id, title, outline,
           ROW_NUMBER() OVER (ORDER BY embedding <=> :query_embedding) as rank
    FROM textbook
    WHERE embedding IS NOT NULL AND status = 'success'
    LIMIT 30
),
fts_search AS (
    -- 2. 全文检索初筛 (支持中文分词及标签匹配)
    SELECT id, title, outline,
           ROW_NUMBER() OVER (ORDER BY ts_rank(to_tsvector('chinese', title || ' ' || tags::text), to_tsquery('chinese', :query_fts)) DESC) as rank
    FROM textbook
    WHERE to_tsvector('chinese', title || ' ' || tags::text) @@ to_tsquery('chinese', :query_fts) AND status = 'success'
    LIMIT 30
)
-- 3. 倒数排序融合 (RRF)，完美兼容向量与文本差异，保证精准度
SELECT COALESCE(v.id, f.id) as id,
       COALESCE(v.title, f.title) as title,
       COALESCE(v.outline, f.outline) as outline,
       (1.0 / (60.0 + COALESCE(v.rank, 100)) + 1.0 / (60.0 + COALESCE(f.rank, 100))) as rrf_score
FROM vector_search v
FULL OUTER JOIN fts_search f ON v.id = f.id
ORDER BY rrf_score DESC
LIMIT :limit; -- limit 设定为 15 或 20
```

---

## 6. 性能优化与高并发保障 (CAG Performance Optimizations)

整篇塞入大纲与正文面临的最大瓶颈是 **LLM 首字延迟 (Time to First Token, TTFT)** 以及 **Token 消耗成本**。本系统通过以下技术栈级优化保障高并发和低延迟：

### 6.1 LLM 缓存层设计 (KV Cache / Prompt Caching)
* **大模型 Prompt 缓存机制**：
  在百炼/OpenAI 调用中，首字延迟高主要是因为重新计算长文本的 KV。
  * **草案 Agent** 的候选大纲列表具有高度重复性（不同学生在同一段时间内的热门专业基本一致）。我们将候选列表的文本结构固定化（格式、前缀一致），从而使得百炼大模型能够命中 **Prompt Cache**，使 TTFT 降低 80% 以上，并节省 50% 的输入 Token 费用。
  * **Markdown Agent** 在对同一章的不同小节生成内容时，每次传入的 `TextbookChapter.content`（整章正文）是完全一样的。通过保证正文文本放在 Prompt 的最前段（Prefix），通义千问模型会自动对其进行 **KV 缓存**，极速响应同一章节内各个小节的后续生成请求。

### 6.2 数据库索引与性能监控
* 为 `Textbook` 表的 `outline` 字段使用 `GIN` 索引，确保查询包含特定大纲节点的 SQL 响应在 5ms 以内。
* 向量字段 `embedding` 采用 `HNSW` 索引而不是 `IVFFlat`，以支持高并发下免训练（No Training）的实时相似度召回。

---

## 7. 管理端前端新组件设计规范 (Admin Frontend Specs)

管理端前端组件基于 **LXGW WenKai** 字体及暗色主题设计（遵循 `AGENTS.md` 规范）。

### 7.1 `/admin/knowledge-base` 主布局
* **配色系统**：
  * 主背景：`oklch(16% 0.015 280)`（暗黑色面板）
  * 文字颜色：`oklch(92% 0.005 280)`
  * 按钮悬浮交互：过渡动画动效控制在 200ms 内，仅允许使用 `transform` 与 `opacity` 的缓动，不可变动布局。
* **模块构成**：
  1. **教材上架上传区 (`UploadPanel.tsx`)**：支持拖拽 PDF、多选标签。
  2. **教材状态表格 (`TextbookTable.tsx`)**：展示解析队列。
  3. **采购待审队列 (`ApprovalQueue.tsx`)**：展示 `admin_kb_agent` 搜集回来的待审核条目。

### 7.2 可视化大纲编辑器 (`OutlineEditor.tsx`)
大模型解析出来的教材大纲，必须能够微调保存。
* **组件设计**：
  * 采用递归式组件 `OutlineNode` 渲染大纲树，支持折叠/展开。
  * 点击任意节点标题直接变为 `<input />` 状态，失焦（`onBlur`）时执行临时保存。
  * 提供拖拽手势图标，允许使用 `framer-motion` 的布局动画实现上下拖动调换顺序。
  * 提供「保存生效」按钮，点击时将整理好的树状结构以 JSON 形式通过 `PUT` API 发送到后台覆盖大纲。

---

## 8. 修改代码硬性约束与注意事项 (Coding Safeguards)

在具体修改代码时，必须遵守以下严格原则，防止破环现有系统：

### 8.1 现有契约测试 (Contract Tests) 兼容
* 运行 `pytest` 发现存在 `test_learning_path_agent_contract.py` 等大量针对 `learning_path_agent` 契约规范的测试。
* 在为 `course_nodes` 添加 `textbook_id` 属性时，必须在对应的 Pydantic 模型（如 `backend/app/orchestration/agents/models.py` 里的 `LearningPathIntakeCourseOutput` 及 `BranchCourseNode`）中将其定义为 **`Optional` 字段，或提供默认值 `None`**。
* 严禁打破旧契约测试中对课程生成格式的期望，否则持续集成（CI）将无法通过。

### 8.2 全栈 API 类型自动生成
* 每次修改了后端的 Pydantic 结构或 API 返回结构后，**必须立即在前端目录下运行 `npm run gen:api`**，以编译出最新的 `src/types/api.ts`。
* 严禁前端自行猜测 API 返回的字段，必须严格引用自动生成的 API 类型，保持全栈类型对齐。

### 8.3 Biome 与 Ruff 代码格式化
* 在修改任何后端 Python 文件后，必须使用 `ruff check --fix` 和 `ruff format` 格式化代码，清除未使用 imports。
* 在修改任何前端 TSX/TS 文件后，必须使用 `npx biome check --write` 清理残存垃圾和格式化代码。
