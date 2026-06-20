# 深色面板与微控件 Token

> 扩展 `01-颜色系统.md`。用于 Chat、进度卡、状态面板和数据可视化中的深色区域。

---

## 深色面板

| Token | 值 | 用途 |
| --- | --- | --- |
| `--dark-surface` | `oklch(16% 0.035 235)` | 深色面板底色 |
| `--dark-surface-raised` | `oklch(20% 0.04 235)` | 抬升深色卡片 |
| `--dark-surface-inset` | `oklch(12% 0.035 235)` | 进度条槽、滑块槽 |
| `--dark-border` | `oklch(92% 0.02 75 / 0.12)` | 深色面板边线 |
| `--dark-highlight` | `oklch(92% 0.02 75 / 0.08)` | hover / active 洗层 |

---

## 深色文字

| Token | 值 | 用途 |
| --- | --- | --- |
| `--dark-text-primary` | `oklch(92% 0.025 75)` | 深色面板主文字 |
| `--dark-text-secondary` | `oklch(80% 0.025 75)` | 次要文字 |
| `--dark-text-muted` | `oklch(64% 0.02 235)` | 辅助文字、说明 |

---

## 实心状态色

深色背景上的状态色必须 100% 不透明。不要用半透明填充做状态点或滑块拇指。

| Token | 值 | 状态 | 用途 |
| --- | --- | --- | --- |
| `--status-running` | `oklch(78% 0.08 145)` | Running | 运行中、成功 |
| `--status-waiting` | `oklch(85% 0.08 60)` | Waiting | 等待、排队 |
| `--status-neutral` | `oklch(75% 0.06 292)` | Neutral | 中性、未开始 |
| `--status-error` | `oklch(72% 0.13 28)` | Error | 错误、失败 |

---

## Pill-in-Pill Progress

进度条必须厚、圆、内嵌。禁止细线进度条。

```css
.progress-track {
  block-size: var(--space-40);
  padding: var(--space-4);
  border-radius: var(--radius-full);
  background: var(--dark-surface-inset);
  box-shadow: var(--shadow-inset);
}

.progress-fill {
  block-size: 100%;
  border-radius: var(--radius-full);
  background: var(--status-running);
  transition: transform var(--duration-lazy-hover) var(--ease-lazy);
  transform-origin: left center;
}
```

---

## Groove & Pebble Slider

滑块要像在凹槽里移动的实心圆石。拇指使用实色，不使用毛玻璃。

```css
.slider-track {
  block-size: var(--space-24);
  border-radius: var(--radius-full);
  background: var(--dark-surface-inset);
  box-shadow: var(--shadow-inset);
}

.slider-thumb {
  inline-size: var(--space-32);
  block-size: var(--space-32);
  border-radius: var(--radius-full);
  background: var(--dark-surface-raised);
  border: 1px solid var(--dark-border);
  box-shadow: var(--shadow-sm);
}
```
