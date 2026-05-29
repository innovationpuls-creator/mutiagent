# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

前端设计系统项目，风格参考 Headspace 冥想应用——温暖、柔和、有呼吸感。所有界面使用中文，面向中文用户。

## Mandatory: Design System Docs

**开始任何前端任务前，必须先调用 `/web-design-engineer` skill，然后阅读 `docs/` 目录下的设计规范文档。** 这些文档定义了项目的全部视觉 token、组件规范和动效规则，是唯一的设计真相来源。

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

### Hard Rules from Docs

- 所有颜色使用 OKLCH，禁止 HEX/RGB 硬编码
- 所有间距从 `--space-*` Scale 选取，禁止任意值
- 阴影使用多层叠加（`--shadow-sm/md/lg`），不用单层
- 动画只动 `transform` 和 `opacity`，不动布局属性
- 所有动效必须有 `prefers-reduced-motion` 降级
- 字体只用 LXGW WenKai（3 字重：Light/Regular/Medium），无 Bold
- 暗色模式不用纯黑纯白，背景 `oklch(16% ...)`，文字 `oklch(92% ...)`

## Mandatory: Playwright Verification After Frontend Changes

**任何前端任务改动完成后，必须调用独立的 subagent 使用 Playwright 进行验收。** 不可跳过。

执行流程：

```
1. 完成前端代码改动
2. 启动预览服务器（如有）或直接打开 HTML 文件
3. 调用 code-reviewer subagent 做代码审查
4. 调用 e2e-runner subagent 用 Playwright 验收：
   - 截图关键断点（375px / 768px / 1280px）
   - 验证是否达到开发计划要求
   - 检查 console 无报错
   - 验证 reduced-motion 行为
5. 验收通过后才算任务完成
```

## Tech Stack

- **单文件 HTML**：React 18 + Tailwind CSS + Babel Standalone，通过 CDN 引入，无构建步骤
- **字体**：LXGW WenKai 系统字体（`brew install font-lxgw-wenkai`），不使用 Google Fonts
- **设计 Token**：CSS Custom Properties，定义在各 HTML 文件的 `<style>` 中
- **预览**：直接浏览器打开 HTML 文件，或使用 Claude Preview MCP server

## Code Style

- 组件 PascalCase，hooks `use` 前缀，CSS class kebab-case
- 函数 < 50 行，文件 < 800 行
- 禁止深层嵌套（> 4 层），用 early return
- 禁止硬编码魔法数字，用 token 或常量
- 不可变数据模式，不修改已有对象

## Git

Commit 格式：`<type>: <描述>`，type 取 feat/fix/refactor/docs/test/chore/perf/ci。
