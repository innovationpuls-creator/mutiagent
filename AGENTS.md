# AGENTS.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.


## Mandatory: Design System Docs

**开始任何前端任务前，必须先调用 `/web-design-engineer` skill的Headspace meditation 风格** 

**参考文档，按需加载**：
   - `docs/ui-design/01-颜色系统.md` — OKLCH 色彩 token、品牌色、语义色、交互态
   - `docs/ui-design/02-字体系统.md` — LXGW WenKai 字体、字阶、行高规则
   - `docs/ui-design/03-间距系统.md` — 4px 基础单位、间距 Scale、Section Padding
   - `docs/ui-design/04-圆角与阴影.md` — 多层阴影、层级对照、圆角 Scale
   - `docs/ui-design/06-materials-effects.md` — 毛玻璃、品牌渐变、发光弥散
   - `docs/ui-design/07-motion-physics.md` — 弹性缓动、Haptics、骨架屏动画
   - `docs/ui-design/session-desgin.md` -所有session开发的规范

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
- **核心框架**：FastAPI + uv + Python
- **智能体中枢**：LangGraph Supervisor + ToolNode (负责调度 Worker Agent)
- **智能体执行层**：LangChain Chain + structured_output (Worker Agent — Profile/LearningPath/CourseKnowledge)
- **LLM 接入**：OpenAI-compatible API (当前: 阿里百炼 Qwen3.5+)
- **数据库**：PostgreSQL (psycopg2)
- **异步**：全链路 asyncio
- **参考文档，按需加载**：`docs/backend/backend-tech-stack.md` 包含完整架构说明

## Code Style

### 前端规范
- **强类型化**：所有组件和钩子必须提供完整的 TypeScript 接口/类型定义 (Interface/Type)，坚决避免 `any`。
- 组件 PascalCase，hooks `use` 前缀，CSS class kebab-case
- 函数 < 50 行，文件 < 800 行
- 禁止深层嵌套（> 4 层），用 early return
- 禁止硬编码魔法数字，用 token 或常量
- 不可变数据模式，不修改已有对象
- **Biome 规范**：所有修改后的前端代码（JS/TS/JSX/TSX）必须符合 Biome 的规则。AI（包括 Antigravity、Codex 和其他 Agent）在修改任何前端文件后，必须自动使用 Biome 进行格式化和代码清理（执行 `npx biome check --write`），以确保无残留垃圾代码或格式异常。

### 后端规范
- **强类型化**：必须使用 Python Type Hints（Pydantic/SQLModel）保证类型安全。
- **路由拆分**：FastAPI 的接口必须基于功能模块通过 `APIRouter` 拆分，禁止在 main.py 中堆砌逻辑。
- **节点解耦**：LangGraph 的 State 与 Node 必须解耦，保持中枢路由的轻量化。Worker Agent 各自是独立的 LangChain Chain，不直接互相调用。
- **Ruff 规范**：所有修改后的 Python 代码必须符合 Ruff 的规则。AI（包括 Antigravity、Codex 和其他 Agent）在修改任何 Python 文件后，必须使用 Ruff 进行格式化和代码清理（自动执行 `ruff check --fix` 和 `ruff format`），以清除未使用的导入、变量或不合规语法。
- **全栈接口类型对齐**：每当 AI 修改了后端的 Pydantic 数据模型（Schemas）、请求体或返回体，必须自动在前端目录下执行一次 `npm run gen:api`（以编译出最新的 `src/types/api.ts`）。严禁自行猜测或在前端硬编码 API 字段，所有接口请求必须强引用 `src/types/api.ts` 中导出的 paths 类型。

## Git

Commit 格式：`<type>: <描述>`，type 取 feat/fix/refactor/docs/test/chore/perf/ci。

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
| ------ | ---------- |
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.
