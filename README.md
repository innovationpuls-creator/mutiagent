<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=6,11,14&height=230&section=header&text=OneTree&fontSize=76&fontColor=fff&animation=twinkling&fontAlignY=38&desc=%E4%B8%80%E6%A3%B5%E6%A0%91%20%C2%B7%20AI%20%E4%B8%AA%E6%80%A7%E5%8C%96%E5%AD%A6%E4%B9%A0%E7%B3%BB%E7%BB%9F&descSize=17&descAlignY=60&descColor=e8f5f0"/>

<br/>

<img src="./frontend/public/logo.png" alt="OneTree" width="96"/>

<h3>一 &nbsp; 棵 &nbsp; 树</h3>

<p><i>从一句轻声的提问，到一张自然舒展的学习地图。</i></p>

<br/>

<a href="https://github.com/innovationpuls-creator/mutiagent">
<img src="https://readme-typing-svg.demolab.com?font=Fira+Code&size=16&pause=1000&color=5BA391&center=true&vCenter=true&repeat=true&width=560&lines=7+AI+Agents+working+in+perfect+harmony.;Personalized+4-year+learning+path%2C+on+demand.;Interactive+animations%2C+auto-written+by+AI.;Let+your+knowledge+grow+like+a+tree." alt="Typing SVG"/>
</a>

<br/><br/>

<p>
<img src="https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react&logoColor=black"/>
<img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white"/>
<img src="https://img.shields.io/badge/LangGraph-FF8C42?style=for-the-badge&logoColor=white"/>
<img src="https://img.shields.io/badge/PostgreSQL-18-4169E1?style=for-the-badge&logo=postgresql&logoColor=white"/>
</p>

<p>
<img src="https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white"/>
<img src="https://img.shields.io/badge/uv-DE5D43?style=for-the-badge&logoColor=white"/>
<img src="https://img.shields.io/badge/Framer_Motion-0055FF?style=for-the-badge&logo=framer&logoColor=white"/>
<img src="https://img.shields.io/badge/License-MIT-5BA391?style=for-the-badge"/>
</p>

<p>
<a href="https://github.com/innovationpuls-creator/mutiagent/stargazers">
<img src="https://img.shields.io/github/stars/innovationpuls-creator/mutiagent?style=social&label=Stars"/>
</a>
&nbsp;&nbsp;
<a href="https://github.com/innovationpuls-creator/mutiagent/network/members">
<img src="https://img.shields.io/github/forks/innovationpuls-creator/mutiagent?style=social&label=Forks"/>
</a>
&nbsp;&nbsp;
<a href="https://github.com/innovationpuls-creator/mutiagent/issues">
<img src="https://img.shields.io/github/issues/innovationpuls-creator/mutiagent?style=social&label=Issues"/>
</a>
</p>

<br/>

**[🖥️ 产品预览](#️-产品预览)** &nbsp;·&nbsp; **[🚀 快速开始](#-快速开始)** &nbsp;·&nbsp; **[🌿 核心旅程](#-核心学习旅程)** &nbsp;·&nbsp; **[🛠️ 技术栈](#️-技术栈)**

</div>

---

## 🖥️ 产品预览

<div align="center">

| 登录 | 学生端 | 管理端 |
|:---:|:---:|:---:|
| <img src="./docs/screenshots/login.png" width="260"/> | <img src="./docs/screenshots/student.png" width="260"/> | <img src="./docs/screenshots/admin.png" width="260"/> |

</div>

---

## ✨ 这是什么

**一棵树**摒弃传统的"课程列表"，将学生的成长抽象成一棵真正生长的树。AI 在第一次对话里就开始构建你的专属学习画像，随后动态铺设 4 年路线，在每个知识节点生成图文讲解、匹配教学视频、渲染可交互动画，最后通过智能自测点亮你的知识地图。

<br/>

> **🤖 &nbsp; 7 个 AI 智能体协同**
> LangGraph Supervisor-Worker 拓扑 + 规则引擎前置拦截，多 Agent 状态转移完全确定。

> **⚡ &nbsp; 全链路实时流式**
> SSE 广播 `supervisor_thinking` 事件，AI 规划过程逐字可见，零等待焦虑。

> **🎨 &nbsp; 动画代码自动生成**
> 遇到物理阻尼、排序算法等抽象概念，AI 自动编写 HTML/JS 动画卡片，在页面内沙箱热加载运行。

> **🔒 &nbsp; 强类型全栈对齐**
> 前端 TypeScript Strict Mode + 后端 SQLModel/Pydantic，接口字段 `npm run gen:api` 自动同步，零猜测。

---

## 🌿 核心学习旅程

```mermaid
graph TD
    U([👤 学生]) --> A[🌱 破冰对话\n/onboarding]
    A --> PA((profile_agent))
    PA --> B[🌿 萌芽\n/sprout]
    B --> LPI((learning_path\nintake_agent))
    LPI --> C[🌳 出枝路线\n/branch]
    C --> LPA((learning_path\nagent))
    LPA --> D[🍃 展叶精读\n/leaf/:id]
    D --> CK((course_knowledge\nagent))
    D --> SM((section_markdown\nagent))
    D --> SV((section_video\nagent))
    D --> SH((html_animation\nagent))
    D --> E[🌲 成林自测\n/forest/:id]
    E -->|"通关点亮 ✓"| C
    W([🤖 全局助手]) -.->|全程陪伴| C
    W -.-> D

    style U fill:#5BA391,color:#fff,stroke:none
    style W fill:#88C5AD,color:#fff,stroke:none
    style A fill:#C8E6C9,stroke:#5BA391
    style B fill:#C8E6C9,stroke:#5BA391
    style C fill:#A5D6A7,stroke:#4CAF50
    style D fill:#81C784,stroke:#388E3C
    style E fill:#66BB6A,color:#fff,stroke:#2E7D32
```

| 阶段 | 路由 | 核心智能体 | 职责 |
| :--: | :--- | :---: | :--- |
| 🌱 破冰萌芽 | `/onboarding` → `/sprout` | `profile_agent` | 引导对话，构建学生画像，持久化至 JSONB |
| 🌳 出枝 | `/branch` | `learning_path_agent` | 实时生成 4 年分阶学习路线 |
| 🍃 展叶 | `/leaf/:id` | 4 个协同 Agent | 章节图文 · 教学视频 · 交互动画 |
| 🌲 成林 | `/forest/:id` | 自测引擎 | 交互答题，通关点亮知识节点 |
| 📊 管理端 | `/admin/*` | — | 培养方案 · 学情监控 · 账户管理 |

---

## 🚀 快速开始

### 生产部署

Ubuntu Server 24.04 x86_64 的 Docker 一键部署、数据迁移、更新、证书续期和回滚请按[中文生产部署文档](docs/deployment/docker-production.md)执行。

下面的 `uvicorn --reload` 和 `npm run dev` 仅用于本地开发，不是生产部署方式。

> [!IMPORTANT]
> **本地部署清单** — 开始前请确认以下工具已就绪：
> | 工具 | 用途 | 最低版本 |
> |:---|:---|:---|
> | [Node.js](https://nodejs.org) | 前端运行时 | v18+ |
> | [PostgreSQL](https://www.postgresql.org/download/) | 数据库 | v18 |
> | [uv](https://github.com/astral-sh/uv) | Python 管理（见第一步） | 最新 |
> | LLM API Key | 兼容 OpenAI 格式（如[阿里百炼](https://bailian.console.aliyun.com/)） | — |

### 第一步 · 安装 uv

uv 会自动下载 Python 并安装所有后端依赖，**你不需要手动安装 Python**。

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

验证：`uv --version` 有输出即成功。

### 第二步 · 克隆项目

```bash
git clone https://github.com/innovationpuls-creator/mutiagent.git
cd mutiagent
```

### 第三步 · 配置数据库

**macOS（Homebrew）：**
```bash
brew install postgresql@18 && brew services start postgresql@18
```

**Windows / Linux：** 参考 [PostgreSQL 官方下载页](https://www.postgresql.org/download/) 安装后启动服务。

**创建数据库（三行搞定）：**
```bash
psql postgres
```
```sql
CREATE USER mutiagent WITH PASSWORD 'mutiagent';
CREATE DATABASE mutiagent OWNER mutiagent;
GRANT ALL PRIVILEGES ON DATABASE mutiagent TO mutiagent; \q
```

### 第四步 · 启动后端

```bash
cd backend
cp .env.example .env
```

编辑 `.env`，填入你的 LLM 配置：

```ini
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=sk-xxxxxx
LLM_MODEL=qwen3.5-plus-2026-04-20
DATABASE_URL=postgresql://mutiagent:mutiagent@localhost:5432/mutiagent
```

```bash
uv run uvicorn app.main:app --reload --port 8000
```

> [!NOTE]
> 首次运行 uv 会自动下载 Python 环境（约1-3分钟）。看到 `Application startup complete` 即成功，同时会自动建表并写入测试账号。

### 第五步 · 启动前端

```bash
cd frontend && npm install && npm run dev
```

### 🎉 开始体验

打开 **[http://localhost:5173](http://localhost:5173)**

| 角色 | 账号 | 密码 |
| :--: | :--- | :--- |
| 🎓 学生 | `demo@mutiagent.local` | `demo123456` |

<details>
<summary>🔧 遇到问题？点击查看常见错误解决方案</summary>

**`psql: command not found`** — PostgreSQL 未加入 PATH，macOS 执行：
```bash
export PATH="/opt/homebrew/opt/postgresql@18/bin:$PATH"
```

**`database connection refused`** — 检查服务是否运行：`brew services list` 或 `pg_isready`

**`npm install` 失败** — 确认 `node --version` ≥ 18，否则用 [nvm](https://github.com/nvm-sh/nvm) 升级

**模型调用失败** — 检查 `.env` 中 `LLM_API_KEY` 与 `LLM_BASE_URL` 是否与服务商匹配

</details>

---

## 🛠️ 技术栈

<div align="center">

**前端**

<p>
<img src="https://img.shields.io/badge/React_18-20232A?style=for-the-badge&logo=react&logoColor=61DAFB"/>
<img src="https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white"/>
<img src="https://img.shields.io/badge/Vite-646CFF?style=for-the-badge&logo=vite&logoColor=white"/>
<img src="https://img.shields.io/badge/Framer_Motion-0055FF?style=for-the-badge&logo=framer&logoColor=white"/>
<img src="https://img.shields.io/badge/Tailwind_CSS-06B6D4?style=for-the-badge&logo=tailwindcss&logoColor=white"/>
</p>

**后端**

<p>
<img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white"/>
<img src="https://img.shields.io/badge/LangGraph-FF8C42?style=for-the-badge&logoColor=white"/>
<img src="https://img.shields.io/badge/LangChain-1C3C3C?style=for-the-badge&logoColor=white"/>
<img src="https://img.shields.io/badge/Python_uv-DE5D43?style=for-the-badge&logoColor=white"/>
</p>

**数据库 & 基础设施**

<p>
<img src="https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white"/>
<img src="https://img.shields.io/badge/SQLModel-4B8BBE?style=for-the-badge&logoColor=white"/>
<img src="https://img.shields.io/badge/Pydantic-E92063?style=for-the-badge&logo=pydantic&logoColor=white"/>
<img src="https://img.shields.io/badge/asyncio-3776AB?style=for-the-badge&logo=python&logoColor=white"/>
</p>

</div>

---

## 📊 项目统计

<div align="center">

<img src="https://github-readme-stats.vercel.app/api/top-langs/?username=innovationpuls-creator&langs_count=6&layout=compact&theme=tokyonight&bg_color=0D1117&border_color=30363D&title_color=7EC8B8&text_color=C9D1D9&hide_border=false" alt="Language Stats"/>

</div>

---

## 🤝 贡献

欢迎 Issue 和 PR。前端改动后请运行 `npx biome check --write`，后端改动后请运行 `ruff check --fix && ruff format`。

---

<div align="center">

<sub>Built with ❤️ · MIT License · 让学习像树一样自然生长 🌱</sub>

<br/>

<img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=6,11,14&height=100&section=footer"/>

</div>
