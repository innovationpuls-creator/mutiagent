# 动效与物理

> 核心方向：慢、柔、可预期。动效像一次深呼吸，不像工具软件的快速弹跳。

---

## 硬规则

- 动画只允许改变 `transform` 和 `opacity`。
- 禁止动画改变 `width`、`height`、`top`、`left`、`margin`、`padding`、`border-radius` 等布局属性。
- 所有动效必须提供 `prefers-reduced-motion` 降级。
- Framer Motion 默认使用 `type: "tween"`；除非有明确理由，不使用高硬度 spring。
- 微交互要轻，不制造晃动、过冲、抖动。

---

## Easing Tokens

| Token | 值 | 质感 | 用途 |
| --- | --- | --- | --- |
| `--ease-editorial` | `cubic-bezier(0.25, 1, 0.5, 1)` | 纸面浮现 | 内容入场、列表出现 |
| `--ease-lazy` | `cubic-bezier(0.33, 1, 0.68, 1)` | 慵懒悬浮 | hover、focus、轻反馈 |
| `--ease-flip` | `cubic-bezier(0.64, 0, 0.35, 1)` | 厚纸翻页 | 路由切换、共享元素 |
| `--ease-breathe` | `ease-in-out` | 呼吸循环 | 光晕、等待状态 |

---

## Duration Tokens

| Token | 值 | 用途 |
| --- | --- | --- |
| `--duration-instant` | `120ms` | 只用于必要的可用性反馈 |
| `--duration-lazy-hover` | `420ms` | hover、focus、press |
| `--duration-reveal` | `760ms` | 内容入场 |
| `--duration-route` | `980ms` | 路由转场 |
| `--duration-flip` | `1200ms` | 3D 翻页 |
| `--duration-breathe` | `4200ms` | 循环呼吸 |

---

## CSS 基线

```css
:root {
  --ease-editorial: cubic-bezier(0.25, 1, 0.5, 1);
  --ease-lazy: cubic-bezier(0.33, 1, 0.68, 1);
  --ease-flip: cubic-bezier(0.64, 0, 0.35, 1);
  --ease-breathe: ease-in-out;

  --duration-instant: 120ms;
  --duration-lazy-hover: 420ms;
  --duration-reveal: 760ms;
  --duration-route: 980ms;
  --duration-flip: 1200ms;
  --duration-breathe: 4200ms;
}
```

---

## 标准动作

### Lazy Hover

```css
.interactive-lazy {
  transition:
    transform var(--duration-lazy-hover) var(--ease-lazy),
    opacity var(--duration-lazy-hover) var(--ease-lazy);
}

.interactive-lazy:hover {
  transform: translateY(calc(var(--space-4) * -1)) scale(1.01);
}

.interactive-lazy:active {
  transform: translateY(0) scale(0.995);
}
```

### Editorial Reveal

```css
.editorial-reveal {
  opacity: 0;
  transform: translateY(var(--space-16));
}

.editorial-reveal[data-visible='true'] {
  opacity: 1;
  transform: translateY(0);
  transition:
    opacity var(--duration-reveal) var(--ease-editorial),
    transform var(--duration-reveal) var(--ease-editorial);
}
```

### Breathing

```css
.breathing {
  animation: breathe var(--duration-breathe) var(--ease-breathe) infinite alternate;
}

@keyframes breathe {
  from { transform: scale(0.98); opacity: 0.72; }
  to { transform: scale(1.03); opacity: 0.9; }
}
```

---

## Framer Motion 映射

```ts
export const motionTokens = {
  editorial: { duration: 0.76, ease: [0.25, 1, 0.5, 1] },
  lazy: { duration: 0.42, ease: [0.33, 1, 0.68, 1] },
  route: { duration: 0.98, ease: [0.64, 0, 0.35, 1] },
} as const;
```

使用示例：

```tsx
<motion.section
  initial={{ opacity: 0, y: 16 }}
  animate={{ opacity: 1, y: 0 }}
  exit={{ opacity: 0, y: -16 }}
  transition={motionTokens.editorial}
/>
```

---

## 骨架屏

骨架屏不做左右扫光。使用低频透明度呼吸，避免制造焦虑。

```css
.skeleton {
  background: var(--color-surface-inset);
  border-radius: var(--radius-md);
  animation: skeleton-breathe var(--duration-breathe) var(--ease-breathe) infinite alternate;
}

@keyframes skeleton-breathe {
  from { opacity: 0.56; }
  to { opacity: 0.86; }
}
```

---

## Reduced Motion

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation: none !important;
    transition: opacity var(--duration-instant) ease !important;
    transform: none !important;
    scroll-behavior: auto !important;
  }
}
```
