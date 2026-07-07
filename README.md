<div align=”center”>

<img src=”https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=6,11,14&height=220&section=header&text=OneTree&fontSize=72&fontColor=fff&animation=fadeIn&fontAlignY=38&desc=AI%20%E9%A9%B1%E5%8A%A8%20%C2%B7%20%E8%87%AA%E7%84%B6%E6%88%90%E9%95%BF%20%C2%B7%20%E4%B8%AA%E6%80%A7%E5%8C%96%E5%AD%A6%E4%B9%A0%E7%B3%BB%E7%BB%9F&descSize=16&descAlignY=62&descColor=rgba%28255%2C255%2C255%2C0.82%29”/>

<br/>

<img src=”./frontend/public/logo.png” alt=”OneTree Logo” width=”108”/>

<h2>一棵树</h2>

<i>从一句轻声的提问，到一张自然舒展的学习地图。</i>

<br/>

<img src=”https://readme-typing-svg.demolab.com?font=Fira+Code&size=16&pause=1100&color=7BBDAD&center=true&vCenter=true&width=560&lines=7+AI+Agents+working+in+harmony.;Personalized+learning+path%2C+generated+on+the+fly.;Interactive+animations%2C+auto-generated+by+AI.;Let+knowledge+grow+like+a+tree.” alt=”Typing SVG”/>

<br/><br/>

[![React 18](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=black)](./frontend)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white)](./backend)
[![LangGraph](https://img.shields.io/badge/LangGraph-Multi--Agent-FF8C42?style=flat-square)](./backend/app/orchestration)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?style=flat-square&logo=postgresql&logoColor=white)](./backend)
[![uv](https://img.shields.io/badge/uv-Python%20管理-DE5D43?style=flat-square)](https://github.com/astral-sh/uv)
[![License: MIT](https://img.shields.io/badge/License-MIT-98C5B0?style=flat-square)](LICENSE)
[![Stars](https://img.shields.io/github/stars/innovationpuls-creator/mutiagent?style=flat-square&logo=github&color=7BB9AD)](https://github.com/innovationpuls-creator/mutiagent/stargazers)

<br/>

[🚀 快速开始](#-快速开始) · [🌿 核心旅程](#-核心学习旅程) · [✨ 功能特性](#-功能特性) · [🛠️ 技术栈](#️-技术栈) · [🔬 MCP 调试](#-调试与-mcp可选)

</div>

---

## ✨ 这是什么

**一棵树** 是一个由 7 个 AI 智能体协同驱动的个性化学习系统。它不做"课程列表"，而是把学生的成长路径抽象成一棵真正生长的树——从第一次破冰对话开始，由 AI 实时构建专属学习画像，动态铺设 4 年学习路线，并在每个知识节点自动生成图文讲解、匹配教学视频、渲染交互动画，最后通过智能自测来点亮学习地图。

<br/>

<table>
<tr>
<td align="center" width="33%">

**🤖 7 智能体协同**

LangGraph Supervisor-Worker 拓扑，规则引擎前置拦截，确保多 Agent 状态转移的确定性

</td>
<td align="center" width="33%">

**⚡ 实时流式生成**

全链路 SSE 异步事件流，AI 规划过程可视化，消除等待感

</td>
<td align="center" width="33%">

**🎨 动画自动生成**

抽象概念（物理阻尼、经典算法）自动编写 HTML/JS 动画卡片，在页面内交互运行

</td>
</tr>
</table>

---

## 🖥️ 产品预览

<div align="center">

| 登录 | 学生端 | 管理端 |
|:---:|:---:|:---:|
| <img src="./docs/screenshots/login.png" width="280"/> | <img src="./docs/screenshots/student.png" width="280"/> | <img src="./docs/screenshots/admin.png" width="280"/> |

</div>

---

## 🌿 核心学习旅程

学生的成长被抽象为五个自然阶段，后台由 **7 个 Worker 智能体** 协作驱动：

```mermaid
graph LR
    A[🌱 破冰] -->|画像构建| B[🌿 萌芽]
    B -->|路线生成| C[🌳 出枝]
    C -->|节点精读| D[🍃 展叶]
    D -->|自测通关| E[🌲 成林]
    E -->|点亮节点| C
    F[🤖 全局助手] -.->|全程陪伴| C
```

| 阶段 | 路由 | 核心智能体 | 做什么 |
| :--: | :--- | :--- | :--- |
| 🌱 破冰萌芽 | `/onboarding` → `/sprout` | `profile_agent` | 引导式对话收集偏好，构建学习画像 |
| 🌳 出枝 | `/branch` | `learning_path_agent` | 动态生成 4 年分阶学习路线 |
| 🍃 展叶 | `/leaf/:id` | 4 个协同 Agent | 生成章节图文、搜索视频、渲染交互动画 |
| 🌲 成林 | `/forest/:id` | 自测引擎 | 交互答题，通关点亮知识节点 |
| 📊 管理端 | `/admin/*` | — | 培养方案配置、学情监控、账户管理 |

---

## ✨ 功能特性

- **7 智能体协同拓扑** — LangGraph Supervisor-Worker 决策网络 + 规则引擎前置拦截，大模型规划与状态转移完全确定
- **交互动画自动生成** — `section_html_animation_agent` 针对抽象概念实时生成 HTML/JS 卡片，在前端沙箱内热加载可操作
- **SSE 实时流式广播** — asyncio 全链路异步，`supervisor_thinking` 规划事件流式可视，消除等待焦虑
- **强类型全栈对齐** — 前端 TypeScript Strict Mode + 后端 SQLModel/Pydantic，接口字段自动生成，零猜测

---

## 🚀 快速开始

> [!IMPORTANT]
> **环境要求** — 开始前请确认已安装以下工具：
> - [Node.js v18+](https://nodejs.org) — 前端运行时
> - [PostgreSQL 15](https://www.postgresql.org/download/) — 数据库
> - [uv](https://github.com/astral-sh/uv) — Python 后端管理工具（见步骤一）
> - 一个兼容 OpenAI 格式的 LLM API Key（如[阿里百炼 Qwen](https://bailian.console.aliyun.com/)）

---

### 第一步：安装 uv（Python 环境管理）

uv 会帮你自动下载正确的 Python 版本并安装所有依赖，**无需手动安装 Python**。

<table>
<tr><th>macOS / Linux</th><th>Windows (PowerShell)</th></tr>
<tr>
<td>

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# 或
brew install uv
```

</td>
<td>

```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

</td>
</tr>
</table>

验证：`uv --version` 输出版本号即表示成功。

---

### 第二步：克隆项目

```bash
git clone https://github.com/innovationpuls-creator/mutiagent.git
cd mutiagent
```

---

### 第三步：配置 PostgreSQL 数据库

**macOS（Homebrew）：**
```bash
brew install postgresql@15
brew services start postgresql@15
```

**Windows / Linux：** 参考 [PostgreSQL 官方下载页](https://www.postgresql.org/download/) 安装并启动服务。

**创建数据库和用户（所有平台相同）：**
```bash
psql postgres
```
```sql
CREATE USER mutiagent WITH PASSWORD 'mutiagent';
CREATE DATABASE mutiagent OWNER mutiagent;
GRANT ALL PRIVILEGES ON DATABASE mutiagent TO mutiagent;
\q
```

---

### 第四步：启动后端

```bash
cd backend
cp .env.example .env
```

用任意文本编辑器打开 `.env`，填入你的 LLM API 配置：

```ini
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=sk-xxxxxx          # 替换为你的 API Key
LLM_MODEL=qwen3.5-plus-2026-04-20
DATABASE_URL=postgresql://mutiagent:mutiagent@localhost:5432/mutiagent
```

一键启动：
```bash
uv run uvicorn app.main:app --reload --port 8000
```

> [!NOTE]
> 首次运行时 uv 会自动下载 Python 并安装依赖（约 1-3 分钟）。服务启动后会自动建表并写入测试账号，看到 `Application startup complete` 即成功。

---

### 第五步：启动前端

打开新终端窗口：

```bash
cd frontend
npm install
npm run dev
```

---

### 🎉 开始探索

浏览器打开 **[http://localhost:5173](http://localhost:5173)**，使用以下测试账号登录：

| 角色 | 账号 | 密码 |
| :--: | :--- | :--- |
| 🎓 学生 | `demo@mutiagent.local` | `demo123456` |

<details>
<summary>🔧 常见问题排查</summary>

**`psql: command not found`**
PostgreSQL 未正确加入 PATH。macOS 用户需执行：
```bash
export PATH="/opt/homebrew/opt/postgresql@15/bin:$PATH"
```

**后端启动报 `database connection refused`**
检查 PostgreSQL 服务是否运行：`brew services list` 或 `pg_isready`。

**前端 `npm install` 报错**
确认 Node.js 版本 ≥ 18：`node --version`。版本过低请用 [nvm](https://github.com/nvm-sh/nvm) 升级。

**API Key 无效 / 模型调用失败**
检查 `.env` 中的 `LLM_API_KEY` 是否正确，以及 `LLM_BASE_URL` 是否与你的服务商匹配。

</details>

---

## 🛠️ 技术栈

| 分层 | 核心技术 | 职责说明 |
| :--- | :--- | :--- |
| ![React](https://img.shields.io/badge/-React%2018-61DAFB?style=flat-square&logo=react&logoColor=black) | React 18 / TypeScript / Vite | 强类型视图构建，极速模块热重载 |
| ![Router](https://img.shields.io/badge/-React%20Router-CA4245?style=flat-square&logo=reactrouter&logoColor=white) | `react-router-dom` | 多视图平滑路由切换 |
| ![Motion](https://img.shields.io/badge/-Framer%20Motion-0055FF?style=flat-square&logo=framer&logoColor=white) | `framer-motion` | Headspace 柔和阻尼动效 |
| ![Tailwind](https://img.shields.io/badge/-Tailwind%20CSS-06B6D4?style=flat-square&logo=tailwindcss&logoColor=white) | Tailwind CSS + CSS Variables | OKLCH 色彩 Token 体系 |
| ![FastAPI](https://img.shields.io/badge/-FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white) | FastAPI / uvicorn | 高性能异步 Web API + SSE 事件流 |
| ![LangGraph](https://img.shields.io/badge/-LangGraph-FF8C42?style=flat-square) | LangGraph | 图结构状态机，多 Agent 编排 |
| ![LangChain](https://img.shields.io/badge/-LangChain-1C3C3C?style=flat-square) | LangChain / structured_output | Prompt 注入 + Pydantic 结构化解析 |
| ![PostgreSQL](https://img.shields.io/badge/-PostgreSQL%2015-4169E1?style=flat-square&logo=postgresql&logoColor=white) | PostgreSQL (JSONB) / SQLModel | JSONB 动态画像存储，多级状态持久化 |

---

## 🔬 调试与 MCP（可选）

本项目内置 `code-review-graph` 语义图谱工具，可作为 MCP 服务接入 Claude Desktop、Windsurf 等客户端，用于自动索引代码并生成调用链分析。

<details>
<summary>点击展开 MCP 配置方法</summary>

在你的 AI 客户端配置文件中二选一添加：

**方法 A — 使用本地虚拟环境（需先启动过后端）**
```json
{
  "mcpServers": {
    "code-review-graph": {
      "command": "/path/to/mutiagent/backend/.venv/bin/code-review-graph",
      "args": ["serve"],
      "cwd": "/path/to/mutiagent",
      "type": "stdio"
    }
  }
}
```

**方法 B — 使用 uvx 直接运行（推荐）**
```json
{
  "mcpServers": {
    "code-review-graph": {
      "command": "uvx",
      "args": ["code-review-graph", "serve"],
      "cwd": "/path/to/mutiagent",
      "type": "stdio"
    }
  }
}
```

> 将 `/path/to/mutiagent` 替换为你本地的项目绝对路径。

</details>

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request。提交前请确保代码通过 Biome（前端）和 Ruff（后端）检查。

---

<div align="center">

<sub>MIT License · 用 ❤️ 构建 · 让学习像树一样自然生长</sub>

<img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=6,11,14&height=100&section=footer"/>

</div>
