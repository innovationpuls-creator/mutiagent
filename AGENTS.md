# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

这是一个全栈单体仓库 (Monorepo) 项目。
- **frontend/**: 前端设计系统项目，风格参考 Headspace 冥想应用——温暖、柔和、有呼吸感。所有界面使用中文，面向中文用户。
- **backend/**: AI 驱动的后端服务，基于 FastAPI、LangGraph、LangChain 架构。

## Mandatory: Design System Docs

**开始任何前端任务前，必须先调用 `/web-design-engineer` skill的Headspace meditation 风格，然后阅读 `docs/` 目录下的设计规范文档。** 这些文档定义了项目的全部视觉 token、组件规范和动效规则，是唯一的设计真相来源。

执行顺序：

1. 调用 `/web-design-engineer` skill 加载设计工程上下文
2. 按以下顺序阅读 docs：
   - `docs/01-颜色系统.md` — OKLCH 色彩 token、品牌色、语义色、交互态
   - `docs/02-字体系统.md` — LXGW WenKai 字体、字阶、行高规则
   - `docs/03-间距系统.md` — 4px 基础单位、间距 Scale、Section Padding
   - `docs/04-圆角与阴影.md` — 多层阴影、层级对照、圆角 Scale
   - `docs/05-暗色模式.md` — 完整暗色 token 对照、`color-scheme` 声明
   - `docs/06-materials-effects.md` — 毛玻璃、品牌渐变、发光弥散
   - `docs/07-motion-physics.md` — 弹性缓动、Haptics、骨架屏动画
   - `docs/session-desgin.md` -所有session开发的规范

### Hard Rules from Docs

- 所有颜色使用 OKLCH，禁止 HEX/RGB 硬编码
- 所有间距从 `--space-*` Scale 选取，禁止任意值
- 阴影使用多层叠加（`--shadow-sm/md/lg`），不用单层
- 动画只动 `transform` 和 `opacity`，不动布局属性
- 所有动效必须有 `prefers-reduced-motion` 降级
- 字体只用 LXGW WenKai（3 字重：Light/Regular/Medium），无 Bold
- 暗色模式不用纯黑纯白，背景 `oklch(16% ...)`，文字 `oklch(92% ...)`



## Tech Stack

### 前端 (frontend)
- **核心框架**：React 18 + TypeScript
- **构建工具**：Vite + Node.js 包管理 (npm/pnpm)
- **路由系统**：`react-router-dom`（用于多页/多视图 3D 翻页及页面级切换）
- **样式方案**：Tailwind CSS (通过 PostCSS) + 原生 CSS Variables (存放 Token)
- **图标基建**：`lucide-react`（必须极度克制，优先使用如 *、//、+ 等几何形态符号，禁止使用廉价彩色图标）
- **动画引擎**：Framer Motion (`framer-motion`)，承接所有的页面交互和复杂转场，严格遵循慢节奏、无生硬弹簧的设计原则
- **字体**：已安装 npm 包 `@fontsource/lxgw-wenkai` 以确保各端完全一致，禁止使用 Google Fonts
- **开发与预览**：本地 Node.js 环境下运行 `npm run dev` 或 `yarn dev`

### 后端 (backend)
- **核心框架**：FastAPI + Python
- **智能体中枢**：LangGraph Supervisor + ToolNode (负责调度 Worker Agent)
- **智能体执行层**：LangChain Chain + structured_output (Worker Agent — Profile/LearningPath/CourseKnowledge)
- **LLM 接入**：OpenAI-compatible API (当前: 阿里百炼 Qwen3.5+)
- **数据库与 ORM**：PostgreSQL (psycopg2) + SQLModel (测试用 SQLite)
- **异步**：全链路 asyncio
- **参考文档**：`docs/后端技术栈.md` 包含完整架构说明

## Code Style

### 前端规范
- **强类型化**：所有组件和钩子必须提供完整的 TypeScript 接口/类型定义 (Interface/Type)，坚决避免 `any`。
- 组件 PascalCase，hooks `use` 前缀，CSS class kebab-case
- 函数 < 50 行，文件 < 800 行
- 禁止深层嵌套（> 4 层），用 early return
- 禁止硬编码魔法数字，用 token 或常量
- 不可变数据模式，不修改已有对象

### 后端规范
- **强类型化**：必须使用 Python Type Hints（Pydantic/SQLModel）保证类型安全。
- **路由拆分**：FastAPI 的接口必须基于功能模块通过 `APIRouter` 拆分，禁止在 main.py 中堆砌逻辑。
- **节点解耦**：LangGraph 的 State 与 Node 必须解耦，保持中枢路由的轻量化。Worker Agent 各自是独立的 LangChain Chain，不直接互相调用。

## Git

Commit 格式：`<type>: <描述>`，type 取 feat/fix/refactor/docs/test/chore/perf/ci。
