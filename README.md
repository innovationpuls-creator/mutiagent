<p align="center">
  <img src="./docs/readme/cover.svg" width="1200" alt="OneTree 一棵树 · AI 个性化学习系统，让学习像树一样自然生长" />
</p>

<p align="center">
  <a href="https://onetree.chat"><strong>在线体验 ↗</strong></a> &nbsp; / &nbsp;
   <a href="#功能概览">功能概览</a> &nbsp; / &nbsp;
  <a href="#产品预览">产品预览</a> &nbsp; / &nbsp;
  <a href="#工程设计">工程设计</a> &nbsp; / &nbsp;
  <a href="#快速开始">快速开始</a> &nbsp; / &nbsp;
  <a href="#文档导航">文档导航</a>
</p>

<br />

OneTree 面向学生，将 **「学什么、怎么学、学得怎样」** 连接成一条持续推进的学习流程。通过对话建立画像，以个性化路径组织课程，在图文、视频与交互动画中理解知识，再用测验反馈和成长报告回顾学习情况。

管理端提供培养方案、账号、学习数据与教材知识库管理，让学习体验与教学内容的组织衔接起来。

<br />



## 功能概览

| 角色 | 主要功能 |
| :--- | :--- |
| 学生端 | 学习画像对话 · 按年学习路径 · 图文 / 视频 / 交互动画 · 章节测验与薄弱点 · AI 成长报告 |
| 管理端 | 培养方案导入与发布 · 账号 / 班级 / 学习数据管理 · 教材知识库（上传、解析、大纲确认、发布） |

<br />




## 产品预览

**萌芽 → 繁枝 → 叶茂 → 成林 → 成森**

从明确学习目标，到走进课程，再到检验理解、回顾成长。

### 01 · 萌芽｜先认识学习者

学生通过破冰对话说明目标、基础和学习偏好，系统逐步建立画像，为课程草案与路径规划提供上下文。

<details>
<summary>查看学习画像界面</summary>

[![萌芽：学习画像、目标与课程推荐](./docs/screenshots/student.png)](./docs/screenshots/student.png)

</details>

### 02 · 繁枝｜把目标铺成可推进的路径

从课程草案出发，按年组织学习内容。学生可以切换年级，查看当前课程和相邻节点，从路径进入具体课程。

[![繁枝：按年组织的学习路径与当前课程节点](./docs/readme/learning-path.png)](./docs/readme/learning-path.png)

<p align="center"><sub>繁枝 · 年级切换、当前课程与后续节点　/　演示录屏画面</sub></p>

### 03 · 叶茂｜沿着章节，逐步理解知识

进入课程后，通过章节导航阅读小节内容。学习目标、概念讲解、代码示例与来源组织在同一页面，教学视频与 HTML 交互动画补充不同形式的解释。

[![叶茂：课程章节导航、学习目标与图文讲解](./docs/readme/course-reading.png)](./docs/readme/course-reading.png)

<p align="center"><sub>叶茂 · 从课程大纲进入小节讲解　/　演示录屏画面</sub></p>

<details>
<summary>查看课程内的交互动画</summary>

[![课程交互动画：数据结构接口与设计规范](./docs/readme/course-animation.png)](./docs/readme/course-animation.png)

<p align="center"><sub>课程内嵌 HTML 交互动画 · 通过节点查看概念与依据　/　演示录屏画面</sub></p>

</details>

### 04 · 成林｜用测验检验理解

完成章节测验后，查看批改结果与薄弱点，并继续接受 AI 辅导。测验与作答记录也为后续的学习回顾提供依据。

### 05 · 成森｜让成长回顾有据可查

按需生成累计 AI 成长报告，查看已经表现出的优势、值得巩固的内容和下一步建议。展开依据可以追溯相关学习记录，建议支持跳转已有课程。

[![成森：AI 成长报告、学习统计与展开的测验依据](./docs/readme/growth-report.png)](./docs/readme/growth-report.png)

<p align="center"><sub>成森 · 学习回顾与引用依据　/　真实界面，使用合成测试数据演示</sub></p>

<details>
<summary>查看管理端与登录界面</summary>

**管理端 · 组织教学内容**

导入与发布培养方案，维护账号、组织班级和学习数据；教材知识库提供教材浏览、解析详情、大纲确认与发布入口。

[![管理端：教材知识库与解析详情](./docs/screenshots/admin.png)](./docs/screenshots/admin.png)

**登录 · 进入学习空间**

[![OneTree 登录界面](./docs/screenshots/login.png)](./docs/screenshots/login.png)

</details>

<br />

## 工程设计

### 明确分工，并用状态约束任务衔接

画像采集、路径规划与小节资源具有不同的输入和输出。系统由 Supervisor 协调 **7 个专职 Worker**，结合规则引擎和当前状态选择执行节点；课程资源链路还会检查已完成阶段，再推进后续任务。前端通过 SSE 接收过程事件和生成内容。

[查看编排图与路由](./backend/app/orchestration/graph.py) · [查看 Supervisor](./backend/app/orchestration/agents/supervisor.py)

### 把资源生成拆成可检查的阶段

小节资源按 **图文 → 视频 → 动画 → 组合** 推进。视频阶段校验链接与来源，动画阶段检查 HTML 结构和内容要求，组合阶段汇集资源结果。分阶段处理使失败可以定位到具体资源环节。

[查看资源生成流程](./backend/app/orchestration/agents/course_resources/main.py) · [查看动画校验](./backend/app/orchestration/agents/course_resources/animation.py)

### 将长任务交给独立后台 Worker

教材整理需要持续运行，因此由独立 Worker 消费持久化任务。任务使用数据库锁领取，通过 **租约与心跳** 记录处理状态，并对过期租约和重试次数作出处理，让任务恢复不依赖原来的页面连接。

[查看知识库 Worker](./backend/app/workers/knowledge_base_worker.py)

### 先计算事实，再生成成长回顾

成长报告先汇总学习记录，再让模型选择并读取相关证据，生成结构化正文。后端校验 **引用是否存在、建议是否指向已有课程、事实分析中的数值是否有来源**；没有测验记录时，不生成已表现出的优势评价。前端提供依据展开和课程跳转。

[查看报告生成与校验](./backend/app/services/growth_report_service.py) · [查看统计口径](./docs/api-specs/API-成长报告.md)

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

本地开发需要 **Node.js 22、Python 3.11+、uv、PostgreSQL 18**，以及 OpenAI-compatible 模型服务的 API 地址、密钥与模型名称。

配置完成后，后端在 `backend/` 运行 `uv run uvicorn app.main:app --reload --port 8000`，前端在 `frontend/` 运行 `npm ci` 和 `npm run dev`。知识库整理另需在 `backend/` 启动 `uv run python -m app.workers`。

<details>
<summary><strong>首次运行 · 安装、数据库与配置步骤</strong></summary>

### 1. 安装工具

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

**了解架构**

[项目概览](./docs/project-overview.md) · [后端技术栈](./docs/backend/backend-tech-stack.md) · [Agent 执行逻辑](./docs/backend/agent逻辑.md) · [数据库设计](./docs/database/数据库表结构.md)

**部署运行**

[生产部署指南](./docs/deployment/docker-production.md) · [Windows 使用说明](./desktop/resources/使用说明.md)

**参与开发**

[API 文档](./docs/api-specs/) · [OpenAPI](./frontend/openapi.json) · [成长报告接口与口径](./docs/api-specs/API-成长报告.md) · [UI 设计规范](./docs/ui-design/)

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
