# 对话栏 Markdown 渲染增强实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 扩展 MarkdownRenderer 组件，添加 Prism.js 语法高亮、MathJax 数学公式、Mermaid 图表和流式光标支持。

**Architecture:** 在现有 MarkdownRenderer 基础上，通过动态导入懒加载 Prism.js、MathJax、Mermaid 库，扩展组件接口支持新功能，添加相应的 CSS 样式。

**Tech Stack:** React 18, TypeScript, react-markdown, remark-gfm, Prism.js, MathJax, Mermaid

---

## 文件结构

| 文件 | 操作 | 用途 |
|------|------|------|
| `frontend/src/components/markdown/MarkdownRenderer.tsx` | 修改 | 扩展组件接口 |
| `frontend/src/components/markdown/markdown-styles.css` | 修改 | 添加新样式 |
| `frontend/src/components/markdown/hooks/usePrism.ts` | 新增 | Prism.js 懒加载 hook |
| `frontend/src/components/markdown/hooks/useMathJax.ts` | 新增 | MathJax 懒加载 hook |
| `frontend/src/components/markdown/hooks/useMermaid.ts` | 新增 | Mermaid 懒加载 hook |
| `frontend/src/components/markdown/utils/highlight.ts` | 新增 | 语法高亮工具 |
| `frontend/src/components/markdown/utils/math.ts` | 新增 | 数学公式工具 |
| `frontend/src/components/markdown/utils/diagram.ts` | 新增 | 图表工具 |
| `frontend/src/components/onboarding/StreamingText.tsx` | 修改 | 添加流式光标 |
| `frontend/package.json` | 修改 | 添加依赖 |

---

## Task 1: 添加依赖

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: 添加 Prism.js、MathJax、Mermaid 依赖**

Run: `cd frontend && npm install prismjs mathjax mermaid`

- [ ] **Step 2: 验证依赖安装成功**

Run: `cd frontend && npm ls prismjs mathjax mermaid`
Expected: 显示已安装的版本

- [ ] **Step 3: 添加类型定义**

Run: `cd frontend && npm install --save-dev @types/prismjs`

- [ ] **Step 4: 提交**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "feat: add prismjs, mathjax, mermaid dependencies"
```

---

## Task 2: 创建 Prism.js 懒加载 hook

**Files:**
- Create: `frontend/src/components/markdown/hooks/usePrism.ts`

- [ ] **Step 1: 创建 usePrism hook**

```typescript
import { useCallback, useState, useEffect } from 'react';

export function usePrism() {
  const [Prism, setPrism] = useState<any>(null);

  useEffect(() => {
    import('prismjs').then((module) => {
      setPrism(module.default || module);
    });
  }, []);

  const highlight = useCallback(
    async (code: string, language: string): Promise<string> => {
      if (!Prism) return code;

      try {
        await import(`prismjs/components/prism-${language}`);
        if (Prism.languages[language]) {
          return Prism.highlight(code, Prism.languages[language], language);
        }
      } catch (error) {
        console.warn(`Failed to load language: ${language}`, error);
      }

      return code;
    },
    [Prism]
  );

  return { highlight, isLoaded: !!Prism };
}
```

- [ ] **Step 2: 验证 TypeScript 编译**

Run: `cd frontend && npx tsc --noEmit src/components/markdown/hooks/usePrism.ts`
Expected: 无错误

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/markdown/hooks/usePrism.ts
git commit -m "feat: add usePrism hook for syntax highlighting"
```

---

## Task 3: 创建 MathJax 懒加载 hook

**Files:**
- Create: `frontend/src/components/markdown/hooks/useMathJax.ts`

- [ ] **Step 1: 创建 useMathJax hook**

```typescript
import { useCallback, useState, useEffect } from 'react';

export function useMathJax() {
  const [MathJax, setMathJax] = useState<any>(null);

  useEffect(() => {
    import('mathjax').then((module) => {
      setMathJax(module.default || module);
    });
  }, []);

  const renderMath = useCallback(
    async (content: string): Promise<string> => {
      if (!MathJax) return content;

      try {
        // 配置 MathJax
        if (!MathJax.config) {
          MathJax.startup = {
            typeset: true,
            ready: () => {
              MathJax.startup.defaultReady();
            },
          };
        }

        // 渲染行内公式 $...$
        const inlineRegex = /\$([^$]+)\$/g;
        const blockRegex = /\$\$([^$]+)\$\$/g;

        let result = content;

        // 渲染块级公式
        result = result.replace(blockRegex, (match, formula) => {
          try {
            return `<div class="math-block">${MathJax.tex2chtml(formula, { display: true }).outerHTML}</div>`;
          } catch (e) {
            return match;
          }
        });

        // 渲染行内公式
        result = result.replace(inlineRegex, (match, formula) => {
          try {
            return `<span class="math-inline">${MathJax.tex2chtml(formula, { display: false }).outerHTML}</span>`;
          } catch (e) {
            return match;
          }
        });

        return result;
      } catch (error) {
        console.warn('MathJax rendering failed', error);
        return content;
      }
    },
    [MathJax]
  );

  return { renderMath, isLoaded: !!MathJax };
}
```

- [ ] **Step 2: 验证 TypeScript 编译**

Run: `cd frontend && npx tsc --noEmit src/components/markdown/hooks/useMathJax.ts`
Expected: 无错误

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/markdown/hooks/useMathJax.ts
git commit -m "feat: add useMathJax hook for math formula rendering"
```

---

## Task 4: 创建 Mermaid 懒加载 hook

**Files:**
- Create: `frontend/src/components/markdown/hooks/useMermaid.ts`

- [ ] **Step 1: 创建 useMermaid hook**

```typescript
import { useCallback, useState, useEffect } from 'react';

export function useMermaid() {
  const [mermaid, setMermaid] = useState<any>(null);

  useEffect(() => {
    import('mermaid').then((module) => {
      const m = module.default || module;
      m.initialize({ startOnLoad: false, theme: 'default' });
      setMermaid(m);
    });
  }, []);

  const renderDiagram = useCallback(
    async (code: string): Promise<string> => {
      if (!mermaid) return code;

      try {
        const id = `mermaid-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        const { svg } = await mermaid.render(id, code);
        return svg;
      } catch (error) {
        console.warn('Mermaid rendering failed', error);
        return `<pre class="mermaid-error">${code}</pre>`;
      }
    },
    [mermaid]
  );

  return { renderDiagram, isLoaded: !!mermaid };
}
```

- [ ] **Step 2: 验证 TypeScript 编译**

Run: `cd frontend && npx tsc --noEmit src/components/markdown/hooks/useMermaid.ts`
Expected: 无错误

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/markdown/hooks/useMermaid.ts
git commit -m "feat: add useMermaid hook for diagram rendering"
```

---

## Task 5: 创建工具函数

**Files:**
- Create: `frontend/src/components/markdown/utils/highlight.ts`
- Create: `frontend/src/components/markdown/utils/math.ts`
- Create: `frontend/src/components/markdown/utils/diagram.ts`

- [ ] **Step 1: 创建 highlight.ts**

```typescript
export function extractLanguage(className: string | undefined): string {
  if (!className) return '';
  const match = /language-(\w+)/.exec(className);
  return match ? match[1] : '';
}

export function isCodeBlock(className: string | undefined): boolean {
  return !!className && className.includes('language-');
}
```

- [ ] **Step 2: 创建 math.ts**

```typescript
export function hasLatexSyntax(content: string): boolean {
  return /\$[^$]+\$|\$\$[^$]+\$\$/.test(content);
}

export function extractLatexBlocks(content: string): string[] {
  const blocks: string[] = [];
  const regex = /\$\$([^$]+)\$\$/g;
  let match;
  while ((match = regex.exec(content)) !== null) {
    blocks.push(match[1]);
  }
  return blocks;
}
```

- [ ] **Step 3: 创建 diagram.ts**

```typescript
export function isMermaidBlock(className: string | undefined, content: string): boolean {
  return !!className && className.includes('language-mermaid') && !!content;
}

export function extractMermaidCode(content: string): string {
  return content.replace(/^```mermaid\n/, '').replace(/\n```$/, '');
}
```

- [ ] **Step 4: 验证 TypeScript 编译**

Run: `cd frontend && npx tsc --noEmit src/components/markdown/utils/`
Expected: 无错误

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/markdown/utils/
git commit -m "feat: add utility functions for markdown rendering"
```

---

## Task 6: 扩展 MarkdownRenderer 组件

**Files:**
- Modify: `frontend/src/components/markdown/MarkdownRenderer.tsx`

- [ ] **Step 1: 更新组件接口**

在文件顶部添加新的 props：

```typescript
interface MarkdownRendererProps {
  content: string;
  className?: string;
  variant?: 'default' | 'editorial' | 'compact';
  enableSyntaxHighlight?: boolean;  // 新增
  enableMath?: boolean;             // 新增
  enableMermaid?: boolean;          // 新增
}
```

- [ ] **Step 2: 导入新的 hooks 和工具**

```typescript
import { usePrism } from './hooks/usePrism';
import { useMathJax } from './hooks/useMathJax';
import { useMermaid } from './hooks/useMermaid';
import { extractLanguage, isCodeBlock } from './utils/highlight';
import { hasLatexSyntax } from './utils/math';
import { isMermaidBlock, extractMermaidCode } from './utils/diagram';
```

- [ ] **Step 3: 更新组件实现**

```typescript
export function MarkdownRenderer({
  content,
  className = '',
  variant = 'default',
  enableSyntaxHighlight = false,
  enableMath = false,
  enableMermaid = false,
}: MarkdownRendererProps) {
  const { highlight } = usePrism();
  const { renderMath } = useMathJax();
  const { renderDiagram } = useMermaid();

  // 处理数学公式
  const processedContent = enableMath ? content : content;

  // 扩展 markdownComponents
  const enhancedComponents: Components = {
    ...markdownComponents,
    code: ({ node, className, children, ...props }) => {
      const inline = !className || !className.includes('language-');
      
      if (inline) {
        return <code {...props}>{children}</code>;
      }

      const lang = extractLanguage(className);
      const codeString = String(children).replace(/\n$/, '');

      // Mermaid 图表
      if (enableMermaid && lang === 'mermaid') {
        return <MermaidDiagram code={codeString} renderDiagram={renderDiagram} />;
      }

      // 语法高亮代码块
      if (enableSyntaxHighlight && lang) {
        return <HighlightedCodeBlock code={codeString} language={lang} highlight={highlight} />;
      }

      // 普通代码块
      return (
        <div className="code-block">
          <div className="code-block-header">
            <span className="code-block-lang">{lang || 'code'}</span>
            <button
              className="code-block-copy"
              onClick={(e) => {
                const button = e.currentTarget;
                navigator.clipboard.writeText(codeString).then(() => {
                  button.textContent = 'COPIED!';
                  button.ariaLabel = 'Code copied';
                  setTimeout(() => {
                    button.textContent = 'COPY';
                    button.ariaLabel = 'Copy code to clipboard';
                  }, 2000);
                }).catch(() => {
                  button.textContent = 'FAILED';
                  button.ariaLabel = 'Failed to copy code';
                  setTimeout(() => {
                    button.textContent = 'COPY';
                    button.ariaLabel = 'Copy code to clipboard';
                  }, 2000);
                });
              }}
            >
              COPY
            </button>
          </div>
          <pre>
            <code className={className} {...props}>
              {children}
            </code>
          </pre>
        </div>
      );
    },
  };

  const variantClass = variant !== 'default' ? variant : '';

  return (
    <div className={`markdown-renderer ${variantClass} ${className}`.trim()}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={enhancedComponents}>
        {processedContent}
      </ReactMarkdown>
    </div>
  );
}
```

- [ ] **Step 4: 创建 MermaidDiagram 组件**

```typescript
function MermaidDiagram({ code, renderDiagram }: { code: string; renderDiagram: (code: string) => Promise<string> }) {
  const [svg, setSvg] = useState<string>('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    renderDiagram(code).then((result) => {
      setSvg(result);
      setLoading(false);
    });
  }, [code, renderDiagram]);

  if (loading) {
    return <div className="mermaid-container">Loading diagram...</div>;
  }

  return (
    <div className="mermaid-container" dangerouslySetInnerHTML={{ __html: svg }} />
  );
}
```

- [ ] **Step 5: 创建 HighlightedCodeBlock 组件**

```typescript
function HighlightedCodeBlock({ code, language, highlight }: { code: string; language: string; highlight: (code: string, language: string) => Promise<string> }) {
  const [highlightedCode, setHighlightedCode] = useState<string>(code);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    highlight(code, language).then((result) => {
      setHighlightedCode(result);
      setLoading(false);
    });
  }, [code, language, highlight]);

  return (
    <div className="code-block">
      <div className="code-block-header">
        <span className="code-block-lang">{language}</span>
        <button
          className="code-block-copy"
          onClick={(e) => {
            const button = e.currentTarget;
            navigator.clipboard.writeText(code).then(() => {
              button.textContent = 'COPIED!';
              setTimeout(() => {
                button.textContent = 'COPY';
              }, 2000);
            }).catch(() => {
              button.textContent = 'FAILED';
              setTimeout(() => {
                button.textContent = 'COPY';
              }, 2000);
            });
          }}
        >
          COPY
        </button>
      </div>
      <pre>
        <code dangerouslySetInnerHTML={{ __html: highlightedCode }} />
      </pre>
    </div>
  );
}
```

- [ ] **Step 6: 验证 TypeScript 编译**

Run: `cd frontend && npx tsc --noEmit`
Expected: 无错误

- [ ] **Step 7: 提交**

```bash
git add frontend/src/components/markdown/MarkdownRenderer.tsx
git commit -m "feat: extend MarkdownRenderer with syntax highlighting, math, and mermaid support"
```

---

## Task 7: 添加 CSS 样式

**Files:**
- Modify: `frontend/src/components/markdown/markdown-styles.css`

- [ ] **Step 1: 添加语法高亮样式**

```css
/* =========================================
   Syntax Highlighting (Prism.js)
   ========================================= */

.markdown-renderer .token.comment,
.markdown-renderer .token.prolog,
.markdown-renderer .token.doctype,
.markdown-renderer .token.cdata {
  color: var(--color-text-whisper);
  font-style: italic;
}

.markdown-renderer .token.punctuation {
  color: var(--color-text-secondary);
}

.markdown-renderer .token.property,
.markdown-renderer .token.tag,
.markdown-renderer .token.boolean,
.markdown-renderer .token.number,
.markdown-renderer .token.constant,
.markdown-renderer .token.symbol,
.markdown-renderer .token.deleted {
  color: var(--color-warning);
}

.markdown-renderer .token.selector,
.markdown-renderer .token.attr-name,
.markdown-renderer .token.string,
.markdown-renderer .token.char,
.markdown-renderer .token.builtin,
.markdown-renderer .token.inserted {
  color: var(--color-success);
}

.markdown-renderer .token.operator,
.markdown-renderer .token.entity,
.markdown-renderer .token.url {
  color: var(--color-text-secondary);
}

.markdown-renderer .token.atrule,
.markdown-renderer .token.attr-value,
.markdown-renderer .token.keyword {
  color: var(--color-primary);
}

.markdown-renderer .token.function,
.markdown-renderer .token.class-name {
  color: var(--color-info);
}

.markdown-renderer .token.regex,
.markdown-renderer .token.important,
.markdown-renderer .token.variable {
  color: var(--color-warning);
}
```

- [ ] **Step 2: 添加数学公式样式**

```css
/* =========================================
   Math Formulas (MathJax)
   ========================================= */

.markdown-renderer .math-block {
  margin: var(--space-24) 0;
  padding: var(--space-16);
  background: var(--color-surface);
  border-radius: var(--radius-md);
  overflow-x: auto;
  text-align: center;
}

.markdown-renderer .math-inline {
  display: inline;
  font-size: var(--text-body-sm);
  vertical-align: middle;
}

.markdown-renderer mjx-container {
  overflow-x: auto;
  max-width: 100%;
}
```

- [ ] **Step 3: 添加 Mermaid 图表样式**

```css
/* =========================================
   Mermaid Diagrams
   ========================================= */

.markdown-renderer .mermaid-container {
  margin: var(--space-24) 0;
  padding: var(--space-16);
  background: var(--color-surface);
  border-radius: var(--radius-md);
  text-align: center;
  overflow-x: auto;
}

.markdown-renderer .mermaid-container svg {
  max-width: 100%;
  height: auto;
}

.markdown-renderer .mermaid-error {
  background: var(--color-error-bg);
  color: var(--color-error);
  padding: var(--space-16);
  border-radius: var(--radius-md);
  font-family: var(--font-mono);
  font-size: var(--text-body-sm);
}
```

- [ ] **Step 4: 验证 CSS 语法**

Run: `cd frontend && npx stylelint src/components/markdown/markdown-styles.css`
Expected: 无错误（如果有 stylelint 配置）

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/markdown/markdown-styles.css
git commit -m "feat: add styles for syntax highlighting, math formulas, and mermaid diagrams"
```

---

## Task 8: 添加流式光标

**Files:**
- Modify: `frontend/src/components/onboarding/StreamingText.tsx`

- [ ] **Step 1: 添加流式光标样式到 markdown-styles.css**

```css
/* =========================================
   Streaming Cursor
   ========================================= */

.markdown-renderer .streaming-cursor::after {
  content: '▊';
  animation: blink 1s step-end infinite;
  color: var(--color-primary);
  margin-left: 2px;
}

@keyframes blink {
  50% { opacity: 0; }
}

@media (prefers-reduced-motion: reduce) {
  .streamdown-cursor::after {
    animation: none;
    opacity: 0.7;
  }
}
```

- [ ] **Step 2: 更新 StreamingText 组件**

在 `StreamingText.tsx` 中，为正在流式输出的块添加 `streaming-cursor` 类：

```typescript
// 在 renderMessage 函数中
{blocks.map((block) => {
  if (!block.complete) {
    return <SkeletonBlock key={block.id} type={block.type} />;
  }

  const isLastBlock = block.id === blocks[blocks.length - 1]?.id;
  const showCursor = isStreaming && isLastBlock && block.complete;

  return (
    <div 
      key={block.id} 
      data-block-type={block.type}
      className={showCursor ? 'streaming-cursor' : ''}
    >
      <MarkdownRenderer content={block.content} variant="compact" />
    </div>
  );
})}
```

- [ ] **Step 3: 验证 TypeScript 编译**

Run: `cd frontend && npx tsc --noEmit`
Expected: 无错误

- [ ] **Step 4: 提交**

```bash
git add frontend/src/components/onboarding/StreamingText.tsx frontend/src/components/markdown/markdown-styles.css
git commit -m "feat: add streaming cursor for real-time output"
```

---

## Task 9: 运行 lint 和 typecheck

**Files:**
- 无（仅验证）

- [ ] **Step 1: 运行 TypeScript typecheck**

Run: `cd frontend && npm run typecheck`
Expected: 无错误

- [ ] **Step 2: 运行 build**

Run: `cd frontend && npm run build`
Expected: 构建成功

- [ ] **Step 3: 运行测试**

Run: `cd frontend && npm test`
Expected: 测试通过（忽略已有的失败测试）

---

## Task 10: 清理和优化

**Files:**
- 无（仅验证）

- [ ] **Step 1: 检查未使用的导入**

检查所有修改的文件，移除未使用的导入。

- [ ] **Step 2: 验证懒加载工作正常**

在浏览器中打开对话栏，检查：
1. 代码块是否正确高亮
2. 数学公式是否正确渲染
3. Mermaid 图表是否正确显示
4. 流式光标是否在流式输出时显示

- [ ] **Step 3: 最终提交**

```bash
git add -A
git commit -m "feat: complete chat markdown enhancement with syntax highlighting, math, mermaid, and streaming cursor"
```

---

## 自检清单

- [ ] 代码块语法高亮正常工作
- [ ] 数学公式正确渲染
- [ ] Mermaid 图表正确显示
- [ ] 流式光标在流式输出时显示
- [ ] 所有样式使用设计 token
- [ ] 懒加载正常工作
- [ ] TypeScript 编译通过
- [ ] 构建成功
- [ ] 测试通过

---

## 执行交接

计划完成并保存到 `.opencode/plans/2026-06-09-chat-markdown-enhancement.md`。两种执行方式：

**1. Subagent-Driven（推荐）** - 每个任务分派独立子代理执行，任务间审查，快速迭代

**2. Inline Execution** - 在当前会话中批量执行，带检查点

您希望使用哪种执行方式？
