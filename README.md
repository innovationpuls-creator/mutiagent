<div align="center">

<img src="./docs/logo/ChatGPT%20Image%202026%E5%B9%B45%E6%9C%8831%E6%97%A5%2001_21_11.png" alt="OneTree Logo" width="140" style="border-radius: 20px; box-shadow: 0 8px 30px rgba(0,0,0,0.15);" />

# 一棵树 (OneTree)

### “从一句轻声的提问，到一张自然舒展的学习地图。”

---

[![Frontend: React 18](https://img.shields.io/badge/Frontend-React%2018-61DAFB?style=flat-square&logo=react&logoColor=black)](./frontend)
[![Backend: FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](./backend)
[![Agent: LangGraph](https://img.shields.io/badge/Orchestrator-LangGraph-orange?style=flat-square)](./backend/app/orchestration)
[![Database: PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL-4169E1?style=flat-square&logo=postgresql&logoColor=white)](./backend/app/database.py)
[![Environment: uv](https://img.shields.io/badge/Environment-uv-de5d43?style=flat-square)](https://github.com/astral-sh/uv)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](https://opensource.org/licenses/MIT)

---

[快速开始](#快速开始) · [核心学习旅程](#核心学习旅程) · [功能特性](#功能特性) · [技术栈](#技术栈) · [调试与-mcp](#调试与-mcp)

</div>

## 核心学习旅程

一棵树摒弃了传统“网盘式”的课程列表，将学生的成长流程抽象为**“破冰 ➡️ 萌芽 ➡️ 出枝 ➡️ 展叶 ➡️ 自测成林”**的自然演化旅程，后台由 **7 个 Worker 智能体** 协作支撑：

```mermaid
graph TD
    A[Onboarding 破冰会话] -->|收集兴趣与目标| B(Sprout 萌芽: 确定学习画像)
    B -->|构建成长树基底| C(Branch 出枝: 铺设学习路线)
    C -->|选择特定年级主题| D(Leaf 展叶: 研读核心大纲)
    D -->|获取详细知识点| E(Forest 成林: 进行智能自测)
    E -->|通过测试点亮节点| C

    F[Global AI Widget 全局助手] -.->|全流程陪伴答疑| A
    F -.->|同步灵感与草稿| G[Canvas 自由画板]
```

### 核心阶段与智能体分工

#### 1. 🌱 Onboarding & Sprout (破冰与萌芽)
*   **路由**：`/onboarding` ➡️ `/sprout`
*   **流程**：通过引导式多轮会话，收集学生的专业基础、核心偏好与预期目标。
*   **智能体**：`profile_agent` 提取对话特征，动态构建学生画像 (User Profile)，持久化至 PostgreSQL JSONB 字段。

#### 2. 🌿 Branch Path (动态出枝)
*   **路由**：`/branch`
*   **流程**：以四载路线图展示大纲结构，支持学生滑动掌控当前阶段。
*   **智能体**：`learning_path_intake_agent` 推荐初步的课程方向与草案；确认后由 `learning_path_agent` 动态生成完整的按年级学习路径 (Yearly Learning Path)。

#### 3. 🍃 Leaf Detail (精读展叶)
*   **路由**：`/leaf/:courseNodeId`
*   **流程**：学生精读特定节点的知识内容、观看推荐视频或操作交互动画。
*   **多智能体协同**：
    1. `course_knowledge_agent`：设计整体课程结构，划分章节与重点难点。
    2. `section_markdown_agent`：针对每个细分章节，生成详细的学习图文和要点解析。
    3. `section_video_search_agent`：自动联网搜索匹配与章节契合的教学视频。
    4. `section_html_animation_agent`：针对抽象概念（如物理阻尼、经典算法），自动编写代码并渲染可在页面上嵌入交互的 **HTML/JS 动画卡片**。

#### 4. 🌳 Forest Assessment (自测成林)
*   **路由**：`/forest/:courseNodeId`
*   **流程**：学完节点后进行交互式答题自测，通关点亮该节点，最终在地图上汇聚成代表技能熟练度的“知识森林”。

---

## 教师与管理端视图

*   **培养方案设计 (`/admin/programs`)**：供教师/管理员使用，用于配置基础大纲模板及课程方向属性。
*   **学情监控大屏 (`/admin/data`)**：统计班级培养方案的覆盖进度与学生的整体画像状态。
*   **账户管理后台 (`/admin/accounts`)**：支持单账号创建、批量创建以及导入/导出系统账号。

---

## 功能特性

*   **7 智能体协同拓扑**：基于 LangGraph 编排 Supervisor-Worker 决策网络，由内置规则引擎进行前置拦截，确保大模型规划与状态转移的确定性。
*   **交互式动画自动生成**：`section_html_animation_agent` 针对抽象科学或算法概念，实时编写代码并支持在前端沙箱中热加载，实现动手模拟操作。
*   **SSE 异步事件流广播**：基于 asyncio 异步执行链，利用 Server-Sent Events (SSE) 协议向前端流式传输 `supervisor_thinking` 规划事件、子智能体调度状态及生成块，消除加载等待焦虑。
*   **强类型数据约束**：前端 React 启用 TypeScript Strict Mode 避免 safe-type 污染；后端基于 SQLModel（SQLAlchemy/Pydantic）提供强类型 API，统一使用 JSONB 归档画像数据。

---

## 技术栈

| 分层 | 核心技术 | 职责说明 |
| :--- | :--- | :--- |
| **前端开发** | React 18 / TypeScript / Vite | 强类型视图构建，极速模块热重载 |
| **页面路由** | `react-router-dom` | 提供多视图平滑无感知路由切换 |
| **动效物理** | `framer-motion` | 承接具有“呼吸感”的 Headspace 柔和阻尼动效 |
| **样式体系** | Tailwind CSS / CSS Variables | 原生变量锁死全局 Token（基于 OKLCH 配色），Tailwind 用于基础排版 |
| **后端框架** | FastAPI / uvicorn | 提供高性能异步 Web API 与 SSE 流式事件流 |
| **智能体编排**| LangGraph | 基于图结构的状态机编排，实现多 Agent 灵活交互 |
| **大模型调用**| LangChain / structured_output | 实现 prompt 模板注入及 Pydantic 结构化输出解析 |
| **数据持久化**| PostgreSQL (JSONB) / SQLModel | JSONB 格式高效保存动态画像与路径，兼容轻量化 SQLite 测试 |

---

## 快速开始

> [!IMPORTANT]
> 开始前，请确保本地开发环境已安装 **Node.js (建议 v18+)** 和 **PostgreSQL**。后端环境及依赖由 **uv** 自动管理，**无需手动配置安装 Python**。

### 1. 下载与安装 uv

后端完全使用现代 Python 环境管理工具 **uv**（使用 Rust 编写）。它会自动下载最匹配的 Python 运行时及依赖。

*   **macOS / Linux**：
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # 或者使用 Homebrew
    brew install uv
    ```
*   **Windows (PowerShell)**：
    ```powershell
    powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```

验证安装：`uv --version`。

### 2. 数据库配置 (PostgreSQL)

系统默认使用 PostgreSQL 作为核心存储，并在启动时自动执行表结构升级与种子数据填充。

#### macOS 安装与启动
使用 Homebrew 安装并开启服务：
```bash
brew install postgresql@15
brew services start postgresql@15
```

#### 创建数据库与用户
登录 PostgreSQL 并创建满足默认连接串要求的数据库与用户：
```bash
# 进入 postgres 控制台
psql postgres

# 执行以下命令
CREATE USER mutiagent WITH PASSWORD 'mutiagent';
CREATE DATABASE mutiagent OWNER mutiagent;
GRANT ALL PRIVILEGES ON DATABASE mutiagent TO mutiagent;
\q
```

#### 💡 可选：本地免装 PostgreSQL (SQLite 回退)
如果您不想在本地安装 Postgres 服务，可以直接将 `.env` 配置文件中的 `DATABASE_URL` 设置为本地 SQLite 单文件地址：
```ini
DATABASE_URL=sqlite:///./app.db
```
后端检测到 sqlite 协议后会自动注入多线程兼容参数 `check_same_thread=False`。

### 3. 后端服务启动

1. 进入后端目录：
   ```bash
   cd backend
   ```
2. 配置环境变量：
   ```bash
   cp .env.example .env
   ```
   编辑 `.env`，配置大模型 API 密钥（兼容 OpenAI 格式接口，如阿里百炼 Qwen）：
   ```ini
   LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
   LLM_API_KEY=sk-xxxxxx
   LLM_MODEL=qwen3.5-plus-2026-04-20
   DATABASE_URL=postgresql://mutiagent:mutiagent@localhost:5432/mutiagent
   ```
3. 一键启动服务：
   ```bash
   uv run uvicorn app.main:app --reload --port 8000
   ```
   > [!NOTE]
   > 运行 `uv run` 时，uv 会自动读取 `pyproject.toml` 的 Python 版本限制并将其下载至本地 `.venv`，无需人工操作。服务启动时会触发 `create_app`，自动执行 Schema 升级并向库中播种测试学生账号：`demo@mutiagent.local` (密码: `demo123456`)。

### 4. 前端服务启动

1. 进入前端目录：
   ```bash
   cd frontend
   ```
2. 安装依赖并启动：
   ```bash
   npm install
   npm run dev
   ```
3. 浏览器访问：
   打开 [http://localhost:5173](http://localhost:5173)，使用测试账号 `demo@mutiagent.local` / `demo123456` 即可开始探索。

---

## 🛠️ 调试与 MCP (可选)

本项目原生配有 `code-review-graph` 语义图谱分析工具，可作为 MCP（Model Context Protocol）服务引入您的大模型开发客户端（如 Claude Desktop 或 Windsurf），用于自动索引、分析并生成代码调用链。

<details>
<summary>点击展开查看 MCP 配置方法</summary>

在大模型客户端配置文件中加入以下配置（二选一）：

#### 方法 A：基于本地虚拟环境的 `code-review-graph` 服务
```json
{
  "mcpServers": {
    "code-review-graph": {
      "command": "/Users/torch/torch/opt/mutiagent/backend/.venv/bin/code-review-graph",
      "args": ["serve"],
      "cwd": "/Users/torch/torch/opt/mutiagent",
      "type": "stdio"
    }
  }
}
```

#### 方法 B：基于全局 `uvx` 运行最新包
```json
{
  "mcpServers": {
    "code-review-graph": {
      "command": "uvx",
      "args": ["code-review-graph", "serve"],
      "cwd": "/Users/torch/torch/opt/mutiagent",
      "type": "stdio"
    }
  }
}
```

</details>
