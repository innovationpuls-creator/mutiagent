# 对话栏 Markdown 渲染增强设计

> 扩展 MarkdownRenderer 组件，添加语法高亮、数学公式、Mermaid 图表和流式光标支持。

---

## 问题背景

### 当前状态

对话栏使用 `MarkdownRenderer variant="compact"` 渲染消息，支持：
- 基础 markdown 语法（标题、列表、链接等）
- 代码块（无语法高亮）
- 表格
- 任务列表
- 引用块（支持 alert 变体）

### 需要增强的功能

1. **代码块语法高亮** - 使用 Prism.js
2. **数学公式支持** - 使用 MathJax
3. **Mermaid 图表** - 使用 Mermaid
4. **流式光标** - 在流式输出时显示闪烁光标

---

## 设计方案

### 技术选型

| 功能 | 库 | 包体积 | 说明 |
|------|-----|--------|------|
| 语法高亮 | Prism.js | ~200KB | 支持 190+ 语言 |
| 数学公式 | MathJax | ~400KB | 支持 LaTeX 语法 |
| 图表 | Mermaid | ~200KB | 支持流程图、序列图等 |

**总增加体积：** ~800KB（可通过懒加载优化初始加载）

### 组件接口扩展

```typescript
interface MarkdownRendererProps {
  content: string;
  className?: string;
  variant?: 'default' | 'editorial' | 'compact';
  enableSyntaxHighlight?: boolean;  // 启用语法高亮
  enableMath?: boolean;             // 启用数学公式
  enableMermaid?: boolean;          // 启用 Mermaid 图表
}
```

### 文件结构

```
frontend/src/components/markdown/
├── MarkdownRenderer.tsx      # 主组件（扩展）
├── markdown-styles.css       # 样式文件（扩展）
├── index.ts                  # 导出
├── hooks/
│   ├── usePrism.ts          # Prism.js 懒加载 hook
│   ├── useMathJax.ts        # MathJax 懒加载 hook
│   └── useMermaid.ts        # Mermaid 懒加载 hook
└── utils/
    ├── highlight.ts         # 语法高亮工具
    ├── math.ts              # 数学公式工具
    └── diagram.ts           # 图表工具
```

### 实现细节

#### 1. 语法高亮（Prism.js）

```typescript
// hooks/usePrism.ts
export function usePrism() {
  const highlight = useCallback(async (code: string, language: string) => {
    const Prism = await import('prismjs');
    await import(`prismjs/components/prism-${language}`);
    return Prism.highlight(code, Prism.languages[language], language);
  }, []);
  
  return { highlight };
}
```

**使用方式：**
- 后端返回：` ```python\nprint("hello")\n``` `
- 前端识别语言标签，调用 Prism.js 高亮
- 渲染为带颜色的代码块

#### 2. 数学公式（MathJax）

```typescript
// hooks/useMathJax.ts
export function useMathJax() {
  const renderMath = useCallback(async (content: string) => {
    const MathJax = await import('mathjax');
    // 配置 MathJax
    // 渲染行内公式 $...$ 和块级公式 $$...$$
  }, []);
  
  return { renderMath };
}
```

**使用方式：**
- 后端返回：`$E=mc^2$` 或 `$$\int_0^1 x dx$$`
- 前端识别 LaTeX 语法，调用 MathJax 渲染
- 渲染为可视化的数学公式

#### 3. Mermaid 图表

```typescript
// hooks/useMermaid.ts
export function useMermaid() {
  const renderDiagram = useCallback(async (code: string) => {
    const mermaid = await import('mermaid');
    mermaid.initialize({ startOnLoad: false, theme: 'default' });
    const { svg } = await mermaid.render('mermaid-graph', code);
    return svg;
  }, []);
  
  return { renderDiagram };
}
```

**使用方式：**
- 后端返回：` ```mermaid\ngraph TD\n    A-->B\n``` `
- 前端识别 mermaid 代码块，调用 Mermaid 渲染
- 渲染为 SVG 图表

#### 4. 流式光标

```css
/* 流式光标样式 */
.streaming-cursor::after {
  content: '▊';
  animation: blink 1s step-end infinite;
  color: var(--color-primary);
}

@keyframes blink {
  50% { opacity: 0; }
}

@media (prefers-reduced-motion: reduce) {
  .streaming-cursor::after {
    animation: none;
    opacity: 0.7;
  }
}
```

**使用方式：**
- 在 StreamingText 组件中，为正在流式输出的块添加 `streaming-cursor` 类
- 流式输出完成后移除该类

### 样式扩展

在 `markdown-styles.css` 中添加：

```css
/* 语法高亮主题 */
.markdown-renderer .token.comment { color: var(--color-text-whisper); }
.markdown-renderer .token.keyword { color: var(--color-primary); }
.markdown-renderer .token.string { color: var(--color-success); }
.markdown-renderer .token.number { color: var(--color-warning); }
.markdown-renderer .token.function { color: var(--color-info); }

/* 数学公式 */
.markdown-renderer .math-block {
  margin: var(--space-24) 0;
  padding: var(--space-16);
  background: var(--color-surface);
  border-radius: var(--radius-md);
  overflow-x: auto;
}

.markdown-renderer .math-inline {
  display: inline;
  font-size: var(--text-body-sm);
}

/* Mermaid 图表 */
.markdown-renderer .mermaid-container {
  margin: var(--space-24) 0;
  padding: var(--space-16);
  background: var(--color-surface);
  border-radius: var(--radius-md);
  text-align: center;
}

.markdown-renderer .mermaid-container svg {
  max-width: 100%;
  height: auto;
}
```

---

## 设计约束

- 所有颜色使用 OKLCH token
- 间距使用 `--space-*` 系列
- 动画只动 `transform` 和 `opacity`
- 支持 `prefers-reduced-motion`
- 字体使用 LXGW WenKai
- 懒加载所有依赖库

---

## 验证清单

- [ ] 代码块语法高亮正常工作
- [ ] 数学公式正确渲染
- [ ] Mermaid 图表正确显示
- [ ] 流式光标在流式输出时显示
- [ ] 所有样式使用设计 token
- [ ] 懒加载正常工作
- [ ] TypeScript 编译通过
- [ ] 构建成功

---

## 影响范围

### 文件变更

- 修改：`frontend/src/components/markdown/MarkdownRenderer.tsx`
- 修改：`frontend/src/components/markdown/markdown-styles.css`
- 新增：`frontend/src/components/markdown/hooks/usePrism.ts`
- 新增：`frontend/src/components/markdown/hooks/useMathJax.ts`
- 新增：`frontend/src/components/markdown/hooks/useMermaid.ts`
- 新增：`frontend/src/components/markdown/utils/highlight.ts`
- 新增：`frontend/src/components/markdown/utils/math.ts`
- 新增：`frontend/src/components/markdown/utils/diagram.ts`
- 修改：`frontend/package.json`（添加依赖）

### 依赖

- `prismjs`（新增）
- `mathjax`（新增）
- `mermaid`（新增）
- `react-markdown`（已安装）
- `remark-gfm`（已安装）

---

## 设计参考

- 颜色系统：`docs/01-颜色系统.md`
- 字体系统：`docs/02-字体系统.md`
- 间距系统：`docs/03-间距系统.md`
- 圆角与阴影：`docs/04-圆角与阴影.md`
- 材质与效果：`docs/06-materials-effects.md`
