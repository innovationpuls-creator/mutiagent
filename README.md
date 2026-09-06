<p align="center">
  <img src="./docs/readme/cover.svg" width="1200" alt="OneTree 一棵树 · AI 个性化学习系统，让学习像树一样自然生长" />
</p>

<p align="center">
  <a href="https://onetree.chat"><strong>在线体验 ↗</strong></a> &nbsp; / &nbsp;
  <a href="#产品预览">产品预览</a> &nbsp; / &nbsp;
  <a href="#系统架构">系统架构</a> &nbsp; / &nbsp;
  <a href="#快速开始">快速开始</a> &nbsp; / &nbsp;
  <a href="#文档导航">文档导航</a>
</p>

<br />

OneTree 面向学生，将 **「学什么、怎么学、学得怎样」** 连接成一条持续推进的学习流程。通过对话建立画像，以个性化路径组织课程，在图文、视频与交互动画中理解知识，再用测验反馈和成长报告回顾学习情况。

管理端提供培养方案、账号、学习数据与教材知识库管理，让学习体验与教学内容的组织衔接起来。

<br />

## 产品预览

### 从认识自己，到走出自己的学习路径

结合学习目标、基础与偏好建立画像，连接后续课程和学习路径。

[![学生端：学习画像、目标与课程推荐](./docs/screenshots/student.png)](./docs/screenshots/student.png)

<p align="center"><sub>学生端 · 学习画像与课程推荐　/　点击图片查看原图</sub></p>

<details>
<summary>展开查看管理端与登录界面</summary>

### 让教学内容有序生长

培养方案、账号、数据与知识库集中管理。教材浏览界面提供解析详情、大纲与发布入口。

[![管理端：教材知识库与解析详情](./docs/screenshots/admin.png)](./docs/screenshots/admin.png)

<p align="center"><sub>管理端 · 教材知识库</sub></p>

[![OneTree 登录界面](./docs/screenshots/login.png)](./docs/screenshots/login.png)

<p align="center"><sub>登录 · 进入学习空间</sub></p>

</details>

<br />

## 一条完整的学习旅程

> **萌芽 → 繁枝 → 叶茂 → 成林 → 成森**
>
> 认识自己，规划方向；逐节学习，自测巩固，回顾成长。

1. **建立画像** — 通过破冰对话收集学习目标、基础与偏好，形成个人学习画像。
2. **规划路径** — 从课程草案出发，生成按年组织的学习路径，查看课程与前置关系。
3. **深入课程** — 进入课程大纲，按小节获取图文讲解、教学视频与 HTML 交互动画。
4. **自测巩固** — 完成章节测验，查看批改与薄弱点，并继续接受 AI 辅导。
5. **回顾成长** — 查看学习进度，按需生成 AI 成长报告，展开来源并跳转相关课程。

<br />

## 支撑学习的核心能力

### 协作式规划，过程实时可见

LangGraph Supervisor 协调 **7 个专职 Worker**，分别处理画像、路径、课程大纲与小节资源。通过 SSE 展示任务进展和生成内容，让较长的规划与资源生成过程保持可见。

### 多形式课程，连接教材知识

**图文、视频与交互动画** 按阶段生成，经资源校验后组合为小节学习内容。教材知识库管理导入、整理、大纲与发布，独立后台 Worker 处理长时间的整理任务。

### 基于学习记录的反馈与回顾

章节测验提供批改、薄弱点与 AI 辅导。**成长报告** 结合真实学习记录生成回顾、待巩固内容与下一步建议，支持展开引用来源、跳转相关课程并重新生成。

<br />

## 系统架构

```mermaid
flowchart TB
    UI["React · 学生端 / 管理端"] -->|HTTP / SSE| API["FastAPI · API 与业务服务"]
    API --> GRAPH["LangGraph · Supervisor + 7 Workers"]
    GRAPH --> MODEL["OpenAI-compatible 模型服务"]
    GRAPH --> RES["课程大纲 · 图文 · 视频 · 交互动画"]
    API --> DB[("PostgreSQL")]
    WORKER["知识库后台 Worker"] --> DB
    WORKER --> KB["教材整理与发布"]

    style UI fill:#fff0df,stroke:#d89565,color:#49392c
    style API fill:#eaf3ee,stroke:#628b74,color:#243c30
    style GRAPH fill:#eaf3ee,stroke:#628b74,color:#243c30
    style DB fill:#eef2f8,stroke:#7891b2,color:#304460
```

<details>
<summary><strong>7 个 Worker 的具体分工</strong></summary>

| Worker | 职责 |
| :--- | :--- |
| `profile_agent` | 对话引导与学习画像采集 |
| `learning_path_intake_agent` | 学习路径需求收集与课程草案 |
| `learning_path_agent` | 按年学习路径生成 |
| `course_knowledge_agent` | 课程知识结构与大纲生成 |
| `section_markdown_agent` | 小节图文内容生成 |
| `section_video_search_agent` | 教学视频检索 |
| `section_html_animation_agent` | HTML 交互动画生成 |

知识库整理使用独立后台 Worker。成长报告复用现有模型服务，不计入上述 7 个 LangGraph Worker。

编排、事件与资源生成流程见 [Agent 执行逻辑](./docs/backend/agent逻辑.md)。

</details>

<br />

### 技术栈与工程实现

| 层级 | 技术与用途 |
| :--- | :--- |
| **前端** | React 18、TypeScript、Vite、Tailwind CSS、Framer Motion；Markdown、数学公式与 Mermaid 渲染。 |
| **后端** | Python、FastAPI、LangGraph、LangChain；HTTP API、SSE 与业务编排。 |
| **数据** | PostgreSQL 18、SQLModel、Pydantic、Alembic；数据持久化、结构校验与迁移。 |
| **接口协作** | 从后端导出 OpenAPI，生成前端 TypeScript 类型。 |
| **部署** | Docker Compose、Nginx；迁移、备份、证书管理、健康检查与回滚脚本。 |
| **桌面端** | Electron 与内置 PostgreSQL，提供 Windows 便携版打包流程。 |
| **验证** | pytest、Vitest、Playwright；Ruff、Biome 与 GitHub Actions。 |

<br />

## 快速开始

| 使用方式 | 入口 |
| :--- | :--- |
| **在线访问** | [onetree.chat](https://onetree.chat) |
| **本地开发** | 按以下步骤启动数据库、后端与前端。 |
| **服务器部署** | [Docker 生产部署指南](./docs/deployment/docker-production.md)，覆盖初始化、迁移、更新、证书与回滚。 |
| **Windows 桌面端** | [使用说明](./desktop/resources/使用说明.md) · [便携版构建工作流](./.github/workflows/windows-portable.yml) |

<details>
<summary><strong>本地开发 · 环境准备与启动步骤</strong></summary>

### 1. 准备环境

- **Node.js 22**：与仓库 CI 使用的版本一致。
- **Python 3.11+ 与 uv**：后端依赖由 uv 管理。
- **PostgreSQL 18**：本地数据库。
- **模型服务**：准备 OpenAI-compatible API 地址、API Key 与模型名称。

macOS 可通过 Homebrew 安装 uv 和 PostgreSQL：

```bash
brew install uv postgresql@18
brew services start postgresql@18
```

其他系统参考 [uv 安装说明](https://docs.astral.sh/uv/getting-started/installation/) 与 [PostgreSQL 下载页](https://www.postgresql.org/download/)。

### 2. 获取项目并创建数据库

```bash
git clone https://github.com/innovationpuls-creator/mutiagent.git
cd mutiagent
psql postgres
```

在 PostgreSQL 终端中执行：

```sql
CREATE USER mutiagent WITH PASSWORD 'mutiagent';
CREATE DATABASE mutiagent OWNER mutiagent;
```

输入 `\q` 退出。以上账号与密码对应仓库的本地开发配置。

### 3. 配置并启动后端

在仓库根目录执行：

```bash
cd backend
cp .env.example .env
```

编辑 `backend/.env`，填写模型服务配置：

```dotenv
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
DATABASE_URL=postgresql://mutiagent:mutiagent@localhost:5432/mutiagent
```

前三项分别填写服务商提供的兼容接口地址、密钥和模型名称。随后启动后端：

```bash
uv run uvicorn app.main:app --reload --port 8000
```

开发模式启动时会初始化数据库并写入演示账号。使用教材知识库整理功能时，另开终端，在仓库根目录执行：

```bash
cd backend
uv run python -m app.workers
```

### 4. 启动前端

另开终端，在仓库根目录执行：

```bash
cd frontend
npm ci
npm run dev
```

访问 [http://localhost:5173](http://localhost:5173)。本地学生演示账号为 `demo@mutiagent.local`，密码为 `demo123456`。

> 以上为本地开发流程。生产环境请使用 [部署指南](./docs/deployment/docker-production.md) 中的 `deploy/bin/bootstrap` 与 `deploy/bin/deploy`。

<details>
<summary><strong>常见启动问题</strong></summary>

- **找不到 `psql`**：确认 PostgreSQL 已安装并加入 PATH。Homebrew 安装后可运行 `export PATH="$(brew --prefix postgresql@18)/bin:$PATH"`。
- **数据库连接失败**：检查 PostgreSQL 服务是否启动，以及 `.env` 中的数据库账号、密码、库名是否一致。
- **模型调用失败**：检查 `LLM_BASE_URL`、`LLM_API_KEY` 与 `LLM_MODEL`，确认对应服务与模型可用。
- **知识库整理任务未推进**：确认已经在 `backend/` 启动 `uv run python -m app.workers`。

</details>

</details>

<br />

## 文档导航

| 想了解什么 | 从这里开始 |
| :--- | :--- |
| 项目全貌、页面与模块关系 | [项目概览](./docs/project-overview.md) |
| 后端架构与 API 分组 | [后端技术栈](./docs/backend/backend-tech-stack.md) |
| 多智能体如何协作 | [Agent 执行逻辑](./docs/backend/agent逻辑.md) |
| 接口字段与数据结构 | [API 文档](./docs/api-specs/) · [OpenAPI](./frontend/openapi.json) |
| 成长报告的数据与统计口径 | [AI 成长报告](./docs/api-specs/API-成长报告.md) |
| 数据库设计 | [数据库表结构](./docs/database/数据库表结构.md) |
| 视觉规范与交互设计 | [UI 设计文档](./docs/ui-design/) |
| 服务器安装、运维与回滚 | [生产部署指南](./docs/deployment/docker-production.md) |

<details>
<summary><strong>仓库目录</strong></summary>

```text
mutiagent/
├── frontend/     React 学生端与管理端
├── backend/      FastAPI、Agent 编排、业务服务与后台任务
├── desktop/      Windows 桌面端与打包配置
├── deploy/       容器、Nginx、迁移、备份与部署脚本
├── docs/         架构、API、数据库与设计文档
└── .github/      自动化验证与构建工作流
```

</details>

<br />

## 开发与贡献

欢迎通过 [Issue](https://github.com/innovationpuls-creator/mutiagent/issues) 反馈问题或提出建议，通过 [Pull Request](https://github.com/innovationpuls-creator/mutiagent/pulls) 参与改进。提交问题时，请附上复现步骤、运行环境与相关日志，并移除密钥和个人信息。

<details>
<summary><strong>开发验证与接口同步</strong></summary>

后端验证（在 `backend/` 执行）：

```bash
uv run pytest -q
uv run ruff check --fix
uv run ruff format
```

前端验证（在 `frontend/` 执行）：

```bash
npm test
npm run build
npm run e2e
npx biome check --write
```

修改后端请求或响应模型后，在 `frontend/` 运行 `npm run gen:api` 同步接口类型。提交格式为 `<type>: <描述>`，例如 `docs: 完善项目介绍`。

</details>

<br />

---

<div align="center">
  <strong>OneTree · 一棵树</strong><br />
  <sub>从一个问题开始，让知识逐渐成林。</sub>
</div>
