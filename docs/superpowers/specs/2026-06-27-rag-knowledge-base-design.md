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
2. **大纲微调与定位阶段**：
   * 后台调用大模型，利用结构化输出（`with_structured_output`）提取整本书的规范大纲 JSON（包括章节及小节名称）。
   * 后台 Python 以此结构化大纲为引导，在 Markdown 全文里自动检索各章节、小节标题的物理位置（`index`），执行精准切片，存入 `textbook_section_content`（小节内容表）。
   * 教师点击“编辑大纲”，弹出一个可视化的树形大纲编辑器（TOC Editor）。如果发现某节标题有 OCR 解析误差，可以直接修改并保存，直接更新数据库大纲 JSON。
3. **教材自主采购队列（KB Agent 审批）**：
   * 当有学生在前端聊天框中请求了知识库目前尚未覆盖的主题时，后台触发 **`admin_kb_agent`**。
   * KB Agent 自动联网检索，找到公开优质的教材 PDF 和大纲，以 `pending_approval` 状态新增至教师后台的“待审采购教材”列表中。
   * 教师点击“同意采购”，系统自动下载、解析、切片并发布。

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
   * 由于精准定位到小节正文，避免了长达数万字的整章文本塞入，**彻底规避了大模型超时（FastAPI 180s超时限制）与 Token 浪费问题**。
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
    # sa_column 处动态指定向量维度
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

### 3.1 教材上传
* **`POST /api/admin/knowledge-base/upload`**
  * **请求体 (Form-Data)**:
    * `file`: UploadFile (PDF)
    * `title`: str (书名)
    * `tags`: str (JSON 格式标签数组)
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
              { "section_id": "sec_1_1", "title": "1.1 Virtual DOM 机制" },
              { "section_id": "sec_1_2", "title": "1.2 Fiber 架构深入" }
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

### 4.1 `learning_path_intake_agent` (草案 Agent)
* **输入规格 (`OrchestrationState`)**:
  * `profile`: 用户画像数据。
  * `query`: 用户的个性化学习诉求。
  * `candidate_textbooks`: **从数据库检索初筛出的 Top 15-20 本教材元数据 + 大纲 JSON**（作为 CAG 上下文）。
* **大模型 System Prompt / 契约约束**:
  * 必须且仅在 `candidate_textbooks` 列出的书目和大纲中进行挑选组合。
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
  * `course_node_id`: 课程节点 ID。
  * `textbook_id`: 绑定该课程的教材 ID。
* **降级与防崩溃兼容逻辑 (Vulnerability 4 修复)**:
  ```python
  # 章节 Agent 执行逻辑
  t_id = state.get("textbook_id")
  if not t_id:
      # 降级校准：按课程名称检索教材库
      course_name = state.get("course_or_chapter_theme")
      textbook = session.exec(select(Textbook).where(Textbook.title == course_name)).first()
      if textbook:
          t_id = textbook.id
          # 回写状态以修复旧数据
          state["textbook_id"] = t_id
      else:
          # 历史数据兜底降级：启动老版本 LLM 参数大纲生成
          return run_legacy_param_outline_generation(state)
  
  # 正常直接拉取 outline
  textbook = session.exec(select(Textbook).where(Textbook.id == t_id)).first()
  return {"outline_data": textbook.outline}
  ```

### 4.4 `section_markdown_agent` (小节 Markdown Agent)
* **输入规格**:
  * `course_node_id` & `chapter_section_id` & `textbook_id`。
  * `section_content`: **精准查询 `TextbookSectionContent` 表获取的小节正文（约 2000-5000 字）**。
* **输出结构**: 格式化的教学 Markdown 文本。

---

## 5. PostgreSQL 检索引导的 CAG 核心检索算法 (RRF Hybrid Search)

对于草案 Agent 匹配教材，后端在启动图（Graph）执行前，调用本 SQL 完成 Top 15-20 的初筛：

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
-- 3. 倒数排序融合 (RRF)，保证精确度与语义召回的平衡
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

## 6. 教材自动切片管道设计 (LLM-Guided Splitter)

为了规避正则表达式切片的 fragility（易碎性）和非标 PDF 带来的解析混乱，系统采用 **“大模型结构化大纲 + Python 物理定位”** 管道进行切分：

```
[管理员上传 PDF] ─► [阿里百炼 Document Mind API] ─► 获得 Markdown 纯文本
                                                            │
                                                            ▼
[Python 物理定位切片] ◄─── [大模型 JSON 目录提取] ◄───────  [全文/前言文本]
  (按标题位置 start:end 切片)    (with_structured_output 约束)
        │
        ▼
[写入数据库 `textbook_section_content`]
```

1. **大纲语义提取**：
   提取 PDF 的目录页 Markdown 送入大模型，使用强类型约束输出目录树大纲 JSON，包含所有小节标题的精确名称数组：`["1.1 什么是数据结构", "1.2 算法复杂度分析"]`。
2. **物理字符索引定位**：
   后端 Python 直接在 Markdown 全文中，以标题为关键词查找位置：
   ```python
   # 获取每个小节标题在 Markdown 全文中的字符起始和截止位置
   positions = []
   for title in section_titles:
       idx = markdown_text.find(title)
       if idx != -1:
           positions.append((title, idx))
   # 根据位置排序并对 markdown_text[start:end] 进行切片，获得纯净的小节正文
   ```
3. **入库**：切片后的小节文本与 `TextbookSectionContent` 绑定入库，规避大模型输出 Token 溢出瓶颈，保障数据完整。

---

## 7. 性能优化与高并发保障 (CAG Performance Optimizations)

### 7.1 LLM 缓存层设计 (KV Cache / Prompt Caching)
* **草案 Agent** 的候选列表文本结构固定化（格式、前缀一致），触发百炼的 **Prompt Cache**，使 TTFT 降低 80% 以上。
* **Markdown Agent** 在对同一小节进行生成时，通过保证小节正文文本放在 Prompt 的最前段（Prefix），通义千问模型会自动对其进行 **KV 缓存**，极速响应同一章节内各个小节的后续生成请求。

### 7.2 数据库索引与性能监控
* 为 `Textbook` 表的 `outline` 字段使用 `GIN` 索引，确保查询包含特定大纲节点的 SQL 响应在 5ms 以内。
* 向量字段 `embedding` 采用 `HNSW` 索引，以支持高并发下免训练（No Training）的实时相似度召回。

---

## 8. 管理端前端新组件设计规范 (Admin Frontend Specs)

管理端前端组件基于 **LXGW WenKai** 字体及暗色主题设计（遵循 `AGENTS.md` 规范）。

### 8.1 `/admin/knowledge-base` 主布局
* **配色系统**：
  * 主背景：`oklch(16% 0.015 280)`（暗黑色面板）
  * 文字颜色：`oklch(92% 0.005 280)`
  * 按钮悬浮交互：过渡动画动效控制在 200ms 内，仅允许使用 `transform` 与 `opacity` 的轻量缓动。
* **模块构成**：
  1. **教材上架上传区 (`UploadPanel.tsx`)**：支持拖拽 PDF、多选标签。
  2. **教材状态表格 (`TextbookTable.tsx`)**：展示解析队列。
  3. **采购待审队列 (`ApprovalQueue.tsx`)**：展示 `admin_kb_agent` 搜集回来的待审核条目。

### 8.2 可视化大纲编辑器 (`OutlineEditor.tsx`)
* **组件设计**：
  * 采用递归式组件 `OutlineNode` 渲染大纲树，支持折叠/展开。
  * 点击任意节点标题直接变为 `<input />` 状态，失焦（`onBlur`）时执行临时保存。
  * 提供拖拽手势图标，允许使用 `framer-motion` 的布局动画实现上下拖动调换顺序。
  * 提供「保存生效」按钮，点击时将整理好的树状结构以 JSON 形式通过 `PUT` API 发送到后台覆盖大纲。

---

## 9. 修改代码硬性约束与注意事项 (Coding Safeguards)

在具体修改代码时，必须遵守以下严格原则，防止破环现有系统：

### 9.1 现有契约测试 (Contract Tests) 兼容
* 运行 `pytest` 发现存在 `test_learning_path_agent_contract.py` 等大量针对 `learning_path_agent` 契约规范的测试。
* 在为 `course_nodes` 添加 `textbook_id` 属性时，必须在对应的 Pydantic 模型中将其定义为 **`Optional` 字段，或提供默认值 `None`**。
* 严禁打破旧契约测试中对课程生成格式的期望，否则持续集成（CI）将无法通过。

### 9.2 全栈 API 类型自动生成
* 每次修改了后端的 Pydantic 结构或 API 返回结构后，**必须立即在前端目录下运行 `npm run gen:api`**，以编译出最新的 `src/types/api.ts`。
* 严禁前端自行猜测 API 返回的字段，必须严格引用自动生成的 API 类型，保持全栈类型对齐。

### 9.3 Biome 与 Ruff 代码格式化
* 在修改任何后端 Python 文件后，必须使用 `ruff check --fix` 和 `ruff format` 格式化代码，清除未使用 imports。
* 在修改任何前端 TSX/TS 文件后，必须使用 `npx biome check --write` 清理残存垃圾和格式化代码。
